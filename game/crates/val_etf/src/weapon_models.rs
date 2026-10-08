//! Weapon models: the guns and attachments made in Blender (copies of the exports in
//! `game/assets/models/weapons/`), put together for a loadout.
//!
//! `game/assets/data/weapon_models.ron` maps each gun and each gameplay attachment id to its GLB and socket.
//! Every file is loaded once at start-up. A gun is its base scene; once that is in the world, each chosen part
//! (optic, stock, mag, under, side, shield) is spawned as a child of its socket node, found by name. The
//! nodes' places, read from the loaded files, also give the first-person poses ([`ViewmodelRig`]): the hip
//! pose from the data, the aimed pose that puts the optic's eye point on the camera, and the muzzle.
//!
//! Each part is dressed for the game as it spawns, by its node roles: a 1x sight's glass clears and its reticle
//! glows, the projector's flaps (its ADS_Open clip) and hologram follow the ADS blend, and a part can take a pose
//! from its extras (the folded bipod). Aimed through a magnified optic, a scope picture replaces the gun.
//!
//! glTF axes: the muzzle is +Z, up +Y, the shooter's right -X (Blender's -Y front becomes +Z). The view looks
//! down -Z with +X on the right, so a gun turns half a turn about Y to face ahead.

use crate::AppState;
use crate::render::ViewmodelRig;
use bevy::animation::graph::AnimationNodeIndex;
use bevy::gltf::{Gltf, GltfExtras, GltfNode};
use bevy::light::NotShadowCaster;
use bevy::prelude::*;
use bevy::render::render_resource::Face;
use bevy::world_serialization::WorldInstanceReady;
use lightyear::prelude::*;
use serde::Deserialize;
use std::collections::{HashMap, HashSet};
use std::f32::consts::PI;
use std::sync::OnceLock;
use vetf_net::*;
use vetf_sim::GameData;
use vetf_sim::data::{AttachmentCategory, WeaponClass};
use vetf_sim::weapon::{ADS_AIMED, WeaponLoadout};

pub struct WeaponModelsPlugin;

impl Plugin for WeaponModelsPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Dressed>()
            .add_systems(Startup, load_models)
            .add_systems(Update, read_layouts)
            .add_systems(Update, drive_projectors.run_if(in_state(AppState::InGame)))
            .add_systems(OnEnter(AppState::InGame), spawn_scope_overlay)
            .add_systems(Update, update_scope_overlay.run_if(in_state(AppState::InGame)));
    }
}

// ---------------------------------------------------------------------------------------------- data

/// `game/assets/data/weapon_models.ron`.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct ModelData {
    pub optics: OpticLook,
    pub guns: Vec<GunRow>,
    pub parts: Vec<PartRow>,
}

/// How the optics' see-through parts draw in the game.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct OpticLook {
    /// The 1x sights' window glass (alpha).
    pub glass_alpha: f32,
    /// Reticles glow at their emissive times this.
    pub reticle_glow: f32,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct GunRow {
    /// The weapon id in weapons.ron.
    pub weapon: String,
    /// Socket nodes are `<prefix>_SOCKET_<slot>`.
    pub prefix: String,
    pub base: String,
    pub hip: ViewPose,
    pub no_optic_eye: NoOpticEye,
    /// Third person: the grip in the right hand, in player space.
    pub hand: [f32; 3],
}

/// A pose in view space: where the grip sits and how the gun turns (degrees) from straight ahead.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct ViewPose {
    pub pos: [f32; 3],
    pub yaw: f32,
    pub pitch: f32,
    pub roll: f32,
}

/// Aimed with no optic: the eye this high over the optic socket and this far behind it (metres).
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct NoOpticEye {
    pub height: f32,
    pub behind: f32,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct PartRow {
    /// The gameplay attachment id (attachments.ron).
    pub id: String,
    pub file: String,
    /// The slot of the gun socket it snaps onto.
    pub socket: String,
    /// A magnified optic: aimed, the view goes through the scope (see [`spawn_scope_overlay`]).
    #[serde(default)]
    pub scope: Option<Scope>,
    /// The fold-out projector sight (see [`ProjectorState`]).
    #[serde(default)]
    pub projector: Option<ProjectorTiming>,
    /// A pose its moving nodes take instead of the exported one: each node whose extras give
    /// `pose_<pose>_quat_gltf_xyzw` turns to it (the bipod's legs fold).
    #[serde(default)]
    pub pose: Option<String>,
}

/// The picture of a magnified optic, aimed.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Scope {
    /// A compact prism: a round window, an ice ring and dot with drop marks under it.
    Prism,
    /// A rifle scope: a round window, fine cross hairs with heavy posts and mil dots.
    Rifle,
    /// A thermal sight's display: a 4:3 screen with a gapped white cross.
    Thermal,
}

/// The projector's timings: the flaps open over `flap_open_s`, the hologram shows from `hologram_from_ads` of
/// the ADS blend and fades in over `hologram_fade_s`.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct ProjectorTiming {
    pub flap_open_s: f32,
    pub hologram_from_ads: f32,
    pub hologram_fade_s: f32,
}

const EMBEDDED: &str = include_str!("../../../assets/data/weapon_models.ron");

impl ModelData {
    /// The copy compiled into the binary.
    pub fn embedded() -> &'static ModelData {
        static DATA: OnceLock<ModelData> = OnceLock::new();
        DATA.get_or_init(|| ron::from_str(EMBEDDED).expect("game/assets/data/weapon_models.ron is valid"))
    }

    /// From the data folder (so it can be tuned without a rebuild), else the built-in copy.
    pub fn load() -> ModelData {
        let path = crate::config::assets_root().join("data").join("weapon_models.ron");
        match std::fs::read_to_string(&path).map(|text| ron::from_str(&text)) {
            Ok(Ok(d)) => d,
            Ok(Err(e)) => {
                error!("{} is invalid ({e}); using the built-in copy", path.display());
                Self::embedded().clone()
            }
            Err(_) => Self::embedded().clone(),
        }
    }

    fn part(&self, id: &str) -> Option<usize> {
        self.parts.iter().position(|p| p.id == id)
    }

    /// The model of a loadout's gun: its row and the rows of its parts. A gun always shows a magazine and a
    /// stock (the weapon's default when the loadout names none); attachments without a model are left off.
    /// `None` for a gun without a model (the Skink).
    pub fn key(&self, data: &GameData, weapon: &WeaponLoadout) -> Option<GunKey> {
        let id = &weapon.spec(data).id;
        let gun = self.guns.iter().position(|g| &g.weapon == id)?;
        let mut parts: Vec<usize> = weapon.attachments.iter().filter_map(|a| self.part(a)).collect();
        for cat in [AttachmentCategory::Mag, AttachmentCategory::Stock] {
            if weapon.attachments.iter().any(|a| data.attachment(a).is_some_and(|a| a.cat == cat)) {
                continue;
            }
            let default = data.attachments.attachments.iter().find(|a| a.cat == cat && a.default_for.contains(id));
            parts.extend(default.and_then(|a| self.part(&a.id)));
        }
        Some(GunKey { gun, parts })
    }
}

/// Which rows of [`ModelData`] make one gun: the gun and its parts.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GunKey {
    pub gun: usize,
    pub parts: Vec<usize>,
}

/// What a gun looks like: its model, or placeholder boxes (no model, or its files are not loaded).
#[derive(Debug, Clone, PartialEq)]
pub enum GunLook {
    Model(GunKey),
    Boxes(WeaponClass),
}

// ---------------------------------------------------------------------------------------------- layouts

/// One node of a glTF file, as the layout needs it (indices are glTF node indices).
#[derive(Debug, Clone)]
pub struct RawNode {
    pub name: String,
    pub transform: Transform,
    pub children: Vec<usize>,
    /// The node's extras (JSON text).
    pub extras: Option<String>,
}

/// The named nodes of one GLB, each placed from the scene root (glTF axes), and an optic's ADS socket with its
/// eye relief (metres behind the socket, along the sight line).
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Layout {
    pub nodes: HashMap<String, Transform>,
    pub ads: Option<(Transform, f32)>,
}

impl Layout {
    pub fn from_nodes(nodes: &[RawNode]) -> Layout {
        let children: HashSet<usize> = nodes.iter().flat_map(|n| n.children.iter().copied()).collect();
        let mut stack: Vec<(usize, Transform)> =
            (0..nodes.len()).filter(|i| !children.contains(i)).map(|i| (i, nodes[i].transform)).collect();
        let mut layout = Layout::default();
        while let Some((i, place)) = stack.pop() {
            let n = &nodes[i];
            if n.name.ends_with("_SOCKET_ADS") {
                let relief = n
                    .extras
                    .as_deref()
                    .and_then(|e| serde_json::from_str::<serde_json::Value>(e).ok())
                    .and_then(|e| e.get("eye_relief_m")?.as_f64());
                layout.ads = Some((place, relief.unwrap_or(0.0) as f32));
            }
            layout.nodes.insert(n.name.clone(), place);
            stack.extend(n.children.iter().filter(|&&c| c < nodes.len()).map(|&c| (c, place * nodes[c].transform)));
        }
        layout
    }

    fn from_gltf(gltf: &Gltf, assets: &Assets<GltfNode>) -> Option<Layout> {
        let nodes: Vec<&GltfNode> = gltf.nodes.iter().map(|h| assets.get(h)).collect::<Option<_>>()?;
        let raw: Vec<RawNode> = nodes
            .iter()
            .map(|n| RawNode {
                name: n.name.clone(),
                transform: n.transform,
                children: n.children.iter().filter_map(|c| assets.get(c)).map(|c| c.index).collect(),
                extras: n.extras.as_ref().map(|e| e.value.clone()),
            })
            .collect();
        Some(Self::from_nodes(&raw))
    }
}

/// Half a turn about Y: glTF gun axes (muzzle +Z) to view axes (ahead -Z).
pub fn face_ahead() -> Quat {
    Quat::from_rotation_y(PI)
}

/// The first-person poses of a gun from its base layout and, if it has one, its optic's layout. Aimed, the
/// optic's eye point (the ADS socket plus the eye relief, behind it) sits on the camera, so the sight line is
/// the view axis and the reticle lies on the aim point. With no optic the eye sits over the optic socket
/// (`no_optic_eye`), the gun centred under the aim point.
pub fn first_person_rig(gun: &GunRow, base: &Layout, optic: Option<(&Layout, Option<Scope>)>) -> Option<ViewmodelRig> {
    let socket = |slot: &str| base.nodes.get(&format!("{}_SOCKET_{slot}", gun.prefix)).copied();
    let muzzle = socket("Muzzle")?.translation;
    let rail = socket("Optic")?;
    let eye = match optic.and_then(|(o, _)| o.ads) {
        // Behind = -Z in the socket's own axes (Blender +Y).
        Some((ads, relief)) => (rail * ads).transform_point(Vec3::NEG_Z * relief),
        None => rail.transform_point(Vec3::new(0.0, gun.no_optic_eye.height, -gun.no_optic_eye.behind)),
    };
    let turn = face_ahead();
    let h = gun.hip;
    let lean = Quat::from_euler(EulerRot::YXZ, h.yaw.to_radians(), h.pitch.to_radians(), h.roll.to_radians());
    Some(ViewmodelRig {
        hip: Transform::from_translation(Vec3::from(h.pos)).with_rotation(lean * turn),
        ads: Transform::from_translation(-(turn * eye)).with_rotation(turn),
        muzzle,
        scope: optic.and_then(|(_, scope)| scope),
    })
}

// ---------------------------------------------------------------------------------------------- dressing

/// What a part's node is for, from its name (`ATT_<part>_<Role>`, optics/NOTES.md): the engine treats these
/// on their own.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Role {
    /// A 1x sight's window pane.
    Glass,
    /// The aiming mark, facing the eye.
    Reticle,
    /// The projector's projected frame and dot.
    Hologram,
    Other,
}

impl Role {
    pub fn of(node: &str) -> Role {
        match node.rsplit('_').next() {
            Some("Glass") => Role::Glass,
            Some("Reticle") => Role::Reticle,
            Some("Hologram") => Role::Hologram,
            _ => Role::Other,
        }
    }
}

impl OpticLook {
    /// An optic's material as the game draws it: the glass clearer, with no clear coat to grey it; the reticle
    /// glowing, one-sided, and drawn after the glass it sits behind.
    pub fn dress(&self, role: Role, m: &mut StandardMaterial) {
        match role {
            Role::Glass => {
                m.base_color.set_alpha(self.glass_alpha);
                m.alpha_mode = AlphaMode::Blend;
                m.clearcoat = 0.0;
            }
            Role::Reticle => {
                m.emissive *= self.reticle_glow;
                m.double_sided = false;
                m.cull_mode = Some(Face::Back);
                m.depth_bias = 1.0;
            }
            Role::Hologram | Role::Other => {}
        }
    }
}

/// A node's turn in a named pose, from its extras (`pose_<pose>_quat_gltf_xyzw`, tactical/NOTES.md).
pub fn pose_rotation(extras: &str, pose: &str) -> Option<Quat> {
    let extras: serde_json::Value = serde_json::from_str(extras).ok()?;
    let q = extras.get(format!("pose_{pose}_quat_gltf_xyzw"))?.as_array()?;
    let q: Vec<f32> = q.iter().filter_map(|v| v.as_f64()).map(|v| v as f32).collect();
    match q[..] {
        [x, y, z, w] => Some(Quat::from_xyzw(x, y, z, w).normalize()),
        _ => None,
    }
}

/// The projector's moving parts: the flaps (0 folded .. 1 open) and the hologram (0 hidden .. 1 shown).
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct ProjectorState {
    pub flaps: f32,
    pub hologram: f32,
    ads: f32,
    raising: bool,
}

impl ProjectorState {
    /// One frame of `dt` seconds at ADS blend `ads`. The flaps open while the gun comes up or stays up and fold
    /// as soon as it goes down; the hologram fades in while they are opening past `hologram_from_ads`, and out
    /// at the same rate otherwise.
    pub fn step(&mut self, t: &ProjectorTiming, ads: f32, dt: f32) {
        // The blend moves on simulation ticks and holds between them, so the last direction is kept.
        if ads > self.ads || ads >= 1.0 {
            self.raising = true;
        } else if ads < self.ads || ads <= 0.0 {
            self.raising = false;
        }
        self.ads = ads;
        let toward = |v: f32, up: bool, secs: f32| {
            let rate = dt / secs.max(1e-3);
            (v + if up { rate } else { -rate }).clamp(0.0, 1.0)
        };
        self.flaps = toward(self.flaps, self.raising, t.flap_open_s);
        self.hologram = toward(self.hologram, self.raising && ads >= t.hologram_from_ads, t.hologram_fade_s);
    }
}

/// The projector's clip, played by the AnimationPlayer the glTF loader puts on the optic's root node.
#[derive(Clone)]
struct ProjectorClip {
    graph: Handle<AnimationGraph>,
    node: AnimationNodeIndex,
    clip: Handle<AnimationClip>,
}

/// The name of the projector's flap clip (optics/NOTES.md).
const PROJECTOR_CLIP: &str = "ADS_Open";

/// How one part instance is drawn: first person (no shadows), an optic (its glass and reticle dressed), the
/// projector, a pose.
#[derive(Clone)]
struct Dress {
    first_person: bool,
    optic: bool,
    look: OpticLook,
    projector: Option<(ProjectorTiming, ProjectorClip)>,
    pose: Option<String>,
}

/// The materials already dressed: a file's materials are shared by every instance of it, so each is changed
/// once.
#[derive(Resource, Default)]
struct Dressed(HashSet<AssetId<StandardMaterial>>);

/// A projector sight in the world, driven by its holder's ADS blend.
#[derive(Component)]
struct Projector {
    timing: ProjectorTiming,
    clip: ProjectorClip,
    first_person: bool,
    /// The node with the AnimationPlayer.
    player: Option<Entity>,
    hologram: Option<Hologram>,
    state: ProjectorState,
}

/// The hologram's node and its own copy of the material (faded per instance), with the full alpha and glow.
struct Hologram {
    node: Entity,
    material: Handle<StandardMaterial>,
    alpha: f32,
    emissive: LinearRgba,
    shown: f32,
}

/// Dresses a part once its scene is in the world (see [`Dress`]).
#[allow(clippy::type_complexity)]
fn dress(
    d: Dress,
) -> impl FnMut(
    On<WorldInstanceReady>,
    Commands,
    Query<&Children>,
    Query<&Name>,
    Query<&ChildOf>,
    Query<&MeshMaterial3d<StandardMaterial>>,
    Query<(), With<AnimationPlayer>>,
    Query<(&GltfExtras, &Transform)>,
    ResMut<Assets<StandardMaterial>>,
    ResMut<Dressed>,
) {
    move |ready, mut commands, tree, names, parents, meshes, players, extras, mut materials, mut dressed| {
        let mut projector = d.projector.clone().map(|(timing, clip)| Projector {
            timing,
            clip,
            first_person: d.first_person,
            player: None,
            hologram: None,
            state: ProjectorState::default(),
        });
        for e in tree.iter_descendants(ready.entity) {
            if let (Some(pose), Ok((extras, t))) = (&d.pose, extras.get(e))
                && let Some(rotation) = pose_rotation(&extras.value, pose)
            {
                commands.entity(e).insert(t.with_rotation(rotation));
            }
            if let Some(p) = projector.as_mut().filter(|_| players.contains(e)) {
                p.player = Some(e);
                commands.entity(e).insert(AnimationGraphHandle(p.clip.graph.clone()));
            }
            let Ok(mesh) = meshes.get(e) else { continue };
            if d.first_person {
                commands.entity(e).insert(NotShadowCaster);
            }
            // A mesh hangs under its node, which names its role.
            let Ok(node) = parents.get(e).map(ChildOf::parent) else { continue };
            let role = names.get(node).map_or(Role::Other, |n| Role::of(n));
            match role {
                Role::Hologram => {
                    let (Some(p), Some(m)) = (projector.as_mut(), materials.get(&mesh.0).cloned()) else { continue };
                    let material = materials.add(m.clone());
                    commands.entity(e).insert(MeshMaterial3d(material.clone()));
                    // Hidden until aimed (glTF has no visibility flag).
                    commands.entity(node).insert(Visibility::Hidden);
                    let alpha = m.base_color.alpha();
                    p.hologram = Some(Hologram { node, material, alpha, emissive: m.emissive, shown: -1.0 });
                }
                Role::Glass | Role::Reticle if d.optic && dressed.0.insert(mesh.id()) => {
                    if let Some(mut m) = materials.get_mut(&mesh.0) {
                        d.look.dress(role, &mut m);
                    }
                }
                _ => {}
            }
        }
        if let Some(p) = projector {
            commands.entity(ready.entity).insert(p);
        }
    }
}

/// Opens the projectors' flaps (seeking their clip) and fades their holograms with the holder's ADS blend. Others
/// never see the hologram: its double-sided frame would show them who is aiming, mirrored.
#[allow(clippy::type_complexity)]
fn drive_projectors(
    time: Res<Time>,
    me: Query<&PlayerWeapon, With<Controlled>>,
    weapons: Query<&PlayerWeapon>,
    parents: Query<&ChildOf>,
    clips: Res<Assets<AnimationClip>>,
    mut projectors: Query<(Entity, &mut Projector)>,
    mut players: Query<&mut AnimationPlayer>,
    mut visibility: Query<&mut Visibility>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    for (e, mut p) in &mut projectors {
        let weapon =
            if p.first_person { me.iter().next() } else { parents.iter_ancestors(e).find_map(|a| weapons.get(a).ok()) };
        let timing = p.timing;
        p.state.step(&timing, weapon.map_or(0.0, |w| w.0.ads), time.delta_secs());
        if let (Some(player), Some(clip)) = (p.player, clips.get(&p.clip.clip))
            && let Ok(mut player) = players.get_mut(player)
        {
            player.play(p.clip.node).pause().set_seek_time(p.state.flaps * clip.duration());
        }
        let shown = if p.first_person { p.state.hologram } else { 0.0 };
        let Some(h) = p.hologram.as_mut().filter(|h| h.shown != shown) else { continue };
        h.shown = shown;
        if let Ok(mut v) = visibility.get_mut(h.node) {
            v.set_if_neq(if shown > 0.0 { Visibility::Inherited } else { Visibility::Hidden });
        }
        if let Some(mut m) = materials.get_mut(&h.material) {
            m.base_color.set_alpha(h.alpha * shown);
            m.emissive = h.emissive * shown;
        }
    }
}

// ---------------------------------------------------------------------------------------------- loading

struct ModelFile {
    gltf: Handle<Gltf>,
    scene: Handle<WorldAsset>,
    layout: Option<Layout>,
    /// The projector's flap clip, if the file has one.
    clip: Option<ProjectorClip>,
    failed: bool,
}

/// The model table, every file's handles, and the layouts of those loaded so far.
#[derive(Resource)]
pub struct WeaponModels {
    pub data: ModelData,
    files: HashMap<String, ModelFile>,
}

fn load_models(mut commands: Commands, server: Res<AssetServer>) {
    let data = ModelData::load();
    let paths = data.guns.iter().map(|g| &g.base).chain(data.parts.iter().map(|p| &p.file));
    let files = paths
        .map(|path| {
            let file = ModelFile {
                gltf: server.load(path.clone()),
                scene: server.load(GltfAssetLabel::Scene(0).from_asset(path.clone())),
                layout: None,
                clip: None,
                failed: false,
            };
            (path.clone(), file)
        })
        .collect();
    commands.insert_resource(WeaponModels { data, files });
}

/// Reads each file's node layout (and the projector's clip) once it has loaded (a file that fails keeps its
/// gun on placeholder boxes).
fn read_layouts(
    mut models: ResMut<WeaponModels>,
    server: Res<AssetServer>,
    gltfs: Res<Assets<Gltf>>,
    nodes: Res<Assets<GltfNode>>,
    mut graphs: ResMut<Assets<AnimationGraph>>,
) {
    if models.files.values().all(|f| f.layout.is_some() || f.failed) {
        return;
    }
    for (path, f) in models.files.iter_mut().filter(|(_, f)| f.layout.is_none() && !f.failed) {
        if server.load_state(&f.gltf).is_failed() || server.recursive_dependency_load_state(&f.gltf).is_failed() {
            warn!("weapon model {path} did not load; that gun keeps its placeholder");
            f.failed = true;
        } else if server.is_loaded_with_dependencies(&f.gltf) {
            let gltf = gltfs.get(&f.gltf);
            f.layout = gltf.and_then(|g| Layout::from_gltf(g, &nodes));
            f.clip = gltf.and_then(|g| g.named_animations.get(PROJECTOR_CLIP)).map(|clip| {
                let (graph, node) = AnimationGraph::from_clip(clip.clone());
                ProjectorClip { graph: graphs.add(graph), node, clip: clip.clone() }
            });
        }
    }
}

impl WeaponModels {
    fn layout(&self, path: &str) -> Option<&Layout> {
        self.files.get(path)?.layout.as_ref()
    }

    /// How the gun of a loadout looks: its model once every file of it has loaded, else boxes.
    pub fn look(&self, data: &GameData, weapon: &WeaponLoadout) -> GunLook {
        match self.data.key(data, weapon) {
            Some(key) if self.rig(&key).is_some() => GunLook::Model(key),
            _ => GunLook::Boxes(weapon.spec(data).cls),
        }
    }

    /// The first-person poses of a gun, once its files have loaded.
    pub fn rig(&self, key: &GunKey) -> Option<ViewmodelRig> {
        let gun = &self.data.guns[key.gun];
        let mut optic = None;
        for &i in &key.parts {
            let part = &self.data.parts[i];
            let layout = self.layout(&part.file)?;
            if layout.ads.is_some() {
                optic = Some((layout, part.scope));
            }
        }
        first_person_rig(gun, self.layout(&gun.base)?, optic)
    }

    /// Third person: where the right hand holds the gun (player space).
    pub fn hand(&self, key: &GunKey) -> Vec3 {
        Vec3::from(self.data.guns[key.gun].hand)
    }

    /// Spawns a gun under `parent` at `place`: the base scene, then each part on its socket node once the base
    /// is in the world. First-person guns cast no shadows (they would shade the world from inside the camera).
    pub fn spawn(&self, commands: &mut Commands, parent: Entity, key: &GunKey, place: Transform, first_person: bool) {
        let gun = &self.data.guns[key.gun];
        let Some(base) = self.files.get(&gun.base).map(|f| f.scene.clone()) else { return };
        let parts: Vec<(String, Handle<WorldAsset>, Dress)> = key
            .parts
            .iter()
            .filter_map(|&i| {
                let part = &self.data.parts[i];
                let file = self.files.get(&part.file)?;
                let dress = Dress {
                    first_person,
                    optic: part.socket == "Optic",
                    look: self.data.optics,
                    projector: part.projector.zip(file.clip.clone()),
                    pose: part.pose.clone(),
                };
                Some((format!("{}_SOCKET_{}", gun.prefix, part.socket), file.scene.clone(), dress))
            })
            .collect();
        let snap = move |ready: On<WorldInstanceReady>,
                         mut commands: Commands,
                         tree: Query<&Children>,
                         names: Query<&Name>,
                         meshes: Query<(), With<Mesh3d>>| {
            for node in tree.iter_descendants(ready.entity) {
                if first_person && meshes.contains(node) {
                    commands.entity(node).insert(NotShadowCaster);
                }
                let Ok(name) = names.get(node) else { continue };
                for (socket, scene, d) in parts.iter().filter(|(s, ..)| s == name.as_str()) {
                    commands
                        .spawn((Name::new(socket.clone()), WorldAssetRoot(scene.clone()), ChildOf(node)))
                        .observe(dress(d.clone()));
                }
            }
        };
        commands.spawn((Name::new(gun.weapon.clone()), WorldAssetRoot(base), place, ChildOf(parent))).observe(snap);
    }
}

// ---------------------------------------------------------------------------------------------- scope view

/// Aimed through a magnified optic, the view is the scope's: black round its window, with its reticle. The
/// camera already zooms by the optic (`render::camera_fov`); the gun hides behind the overlay.
#[derive(Component)]
struct ScopeOverlay(Scope);

/// The round scope window's diameter (share of the screen height); the thermal screen is as tall, 4:3.
const SCOPE_WINDOW_VH: f32 = 92.0;
const SCOPE_LINE: Color = Color::srgba(0.02, 0.02, 0.03, 0.9);
const SCOPE_ICE: Color = Color::srgb(0.55, 0.88, 1.0);
const THERMAL_LINE: Color = Color::srgba(0.95, 0.96, 0.97, 0.9);

/// The gun is up to the eye with a magnified optic: the scope view replaces the viewmodel.
pub fn scoped(rig: &ViewmodelRig, ads: f32) -> bool {
    rig.scope.is_some() && ads >= ADS_AIMED
}

/// One mark of a reticle: its size, where its corner sits (left / top in percent of the window), the pixels it
/// is pulled back by so it centres on that point, its colour, and for a round mark the width of its ring (0
/// fills it).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Mark {
    pub w: Val,
    pub h: Val,
    pub at: (f32, f32),
    pub pull: (f32, f32),
    pub color: Color,
    pub round: Option<f32>,
}

impl Mark {
    /// A bar `w` x `h` with its top-left corner at `at`, centred across its thickness.
    fn bar(w: Val, h: Val, at: (f32, f32), color: Color) -> Mark {
        let half = |v: Val| if let Val::Px(p) = v { p * 0.5 } else { 0.0 };
        Mark { w, h, at, pull: (half(w), half(h)), color, round: None }
    }

    /// A round dot `px` across centred on `at`.
    fn dot(px: f32, at: (f32, f32), color: Color) -> Mark {
        Mark { w: Val::Px(px), h: Val::Px(px), at, pull: (px * 0.5, px * 0.5), color, round: Some(0.0) }
    }
}

/// The reticle of a scope picture, in percent of its window. Every one marks the aim point, the window's centre.
pub fn reticle(scope: Scope) -> Vec<Mark> {
    let (p, x) = (Val::Percent, Val::Px);
    let mut marks = Vec::new();
    match scope {
        Scope::Rifle => {
            // Fine cross hairs, heavy posts toward the rim, mil dots, an ice dot on the aim point.
            marks.push(Mark::bar(p(100.0), x(2.0), (0.0, 50.0), SCOPE_LINE));
            marks.push(Mark::bar(x(2.0), p(100.0), (50.0, 0.0), SCOPE_LINE));
            for at in [0.0, 70.0] {
                marks.push(Mark::bar(p(30.0), x(6.0), (at, 50.0), SCOPE_LINE));
                marks.push(Mark::bar(x(6.0), p(30.0), (50.0, at), SCOPE_LINE));
            }
            for k in [-3.0, -2.0, -1.0, 1.0, 2.0, 3.0] {
                marks.push(Mark::dot(5.0, (50.0 + 5.0 * k, 50.0), SCOPE_LINE));
                marks.push(Mark::dot(5.0, (50.0, 50.0 + 5.0 * k), SCOPE_LINE));
            }
            marks.push(Mark::dot(6.0, (50.0, 50.0), SCOPE_ICE));
        }
        Scope::Prism => {
            // Side stadia and a post from below, an ice ring round the aim dot, ice drop marks under it.
            marks.push(Mark::bar(p(36.0), x(3.0), (0.0, 50.0), SCOPE_LINE));
            marks.push(Mark::bar(p(36.0), x(3.0), (64.0, 50.0), SCOPE_LINE));
            marks.push(Mark::bar(x(5.0), p(22.0), (50.0, 78.0), SCOPE_LINE));
            let ring = 8.0;
            marks.push(Mark {
                w: p(ring),
                h: p(ring),
                at: (50.0 - ring * 0.5, 50.0 - ring * 0.5),
                pull: (0.0, 0.0),
                color: SCOPE_ICE,
                round: Some(3.0),
            });
            marks.push(Mark::dot(7.0, (50.0, 50.0), SCOPE_ICE));
            for (i, w) in [5.0, 4.0, 3.0].into_iter().enumerate() {
                marks.push(Mark::bar(p(w), x(3.0), (50.0 - w * 0.5, 58.0 + 6.0 * i as f32), SCOPE_ICE));
            }
        }
        Scope::Thermal => {
            // A white cross with a gap round the aim point and a small square on it.
            for (a, b) in [(8.0, 46.0), (54.0, 92.0)] {
                marks.push(Mark::bar(p(b - a), x(2.0), (a, 50.0), THERMAL_LINE));
                marks.push(Mark::bar(x(2.0), p(b - a), (50.0, a), THERMAL_LINE));
            }
            marks.push(Mark::bar(x(4.0), x(4.0), (50.0, 50.0), THERMAL_LINE));
        }
    }
    marks
}

fn spawn_scope_overlay(mut commands: Commands) {
    for scope in [Scope::Prism, Scope::Rifle, Scope::Thermal] {
        let root = commands
            .spawn((
                ScopeOverlay(scope),
                Node {
                    position_type: PositionType::Absolute,
                    width: percent(100),
                    height: percent(100),
                    align_items: AlignItems::Center,
                    justify_content: JustifyContent::Center,
                    ..default()
                },
                Visibility::Hidden,
                GlobalZIndex(-10),
                DespawnOnExit(AppState::InGame),
                Pickable::IGNORE,
            ))
            .id();
        // The window is a round node (the thermal's a rounded screen); its outline, wider than the screen, is
        // the black around it.
        let (width, radius) = match scope {
            Scope::Thermal => (SCOPE_WINDOW_VH * 4.0 / 3.0, BorderRadius::all(Val::Vh(2.5))),
            Scope::Prism | Scope::Rifle => (SCOPE_WINDOW_VH, BorderRadius::MAX),
        };
        let window = commands
            .spawn((
                Node {
                    width: Val::Vh(width),
                    height: Val::Vh(SCOPE_WINDOW_VH),
                    border: UiRect::all(px(10)),
                    border_radius: radius,
                    ..default()
                },
                BorderColor::all(Color::srgba(0.0, 0.0, 0.0, 0.55)),
                Outline::new(Val::Vw(150.0), px(0), Color::BLACK),
                ChildOf(root),
            ))
            .id();
        for m in reticle(scope) {
            let node = Node {
                position_type: PositionType::Absolute,
                width: m.w,
                height: m.h,
                left: percent(m.at.0),
                top: percent(m.at.1),
                margin: UiRect { left: px(-m.pull.0), top: px(-m.pull.1), ..default() },
                border: UiRect::all(px(m.round.unwrap_or(0.0))),
                border_radius: if m.round.is_some() { BorderRadius::MAX } else { BorderRadius::ZERO },
                ..default()
            };
            match m.round {
                // A ring: only its border is drawn.
                Some(ring) if ring > 0.0 => commands.spawn((node, BorderColor::all(m.color), ChildOf(window))),
                _ => commands.spawn((node, BackgroundColor(m.color), ChildOf(window))),
            };
        }
    }
}

fn update_scope_overlay(
    rig: Res<ViewmodelRig>,
    cli: Res<crate::config::Cli>,
    me: Query<(&PlayerWeapon, &Vitals), With<Controlled>>,
    mut overlay: Query<(&ScopeOverlay, &mut Visibility)>,
) {
    let show = cli.camera.is_none() && me.iter().next().is_some_and(|(w, v)| !v.health.dead && scoped(&rig, w.0.ads));
    for (o, mut vis) in &mut overlay {
        let on = show && rig.scope == Some(o.0);
        vis.set_if_neq(if on { Visibility::Inherited } else { Visibility::Hidden });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::f32::consts::FRAC_PI_2 as FRAC_PI_2_F32;

    /// The GLB's JSON chunk (the art exports are binary glTF).
    fn glb_json(path: &std::path::Path) -> Option<serde_json::Value> {
        let bytes = std::fs::read(path).ok()?;
        if bytes.get(..4)? != b"glTF" {
            return None; // a Git LFS pointer: the file itself is not checked out
        }
        let len = u32::from_le_bytes(bytes.get(12..16)?.try_into().ok()?) as usize;
        serde_json::from_slice(bytes.get(20..20 + len)?).ok()
    }

    /// The GLB's nodes as the layout reads them.
    fn glb_nodes(path: &std::path::Path) -> Option<Vec<RawNode>> {
        let json = glb_json(path)?;
        let f = |v: &serde_json::Value| v.as_f64().unwrap_or(0.0) as f32;
        let vec = |n: &serde_json::Value, key: &str, d: Vec<f32>| {
            n.get(key).and_then(|v| v.as_array()).map_or(d, |a| a.iter().map(f).collect())
        };
        let nodes = json.get("nodes")?.as_array()?;
        Some(
            nodes
                .iter()
                .map(|n| {
                    let t = vec(n, "translation", vec![0.0; 3]);
                    let r = vec(n, "rotation", vec![0.0, 0.0, 0.0, 1.0]);
                    let s = vec(n, "scale", vec![1.0; 3]);
                    RawNode {
                        name: n.get("name").and_then(|v| v.as_str()).unwrap_or_default().to_string(),
                        transform: Transform {
                            translation: Vec3::new(t[0], t[1], t[2]),
                            rotation: Quat::from_xyzw(r[0], r[1], r[2], r[3]),
                            scale: Vec3::new(s[0], s[1], s[2]),
                        },
                        children: n
                            .get("children")
                            .and_then(|c| c.as_array())
                            .map_or(Vec::new(), |c| c.iter().filter_map(|i| i.as_u64()).map(|i| i as usize).collect()),
                        extras: n.get("extras").map(|e| e.to_string()),
                    }
                })
                .collect(),
        )
    }

    fn asset(path: &str) -> std::path::PathBuf {
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../assets").join(path)
    }

    fn node(name: &str, t: Vec3, children: Vec<usize>, extras: Option<&str>) -> RawNode {
        RawNode {
            name: name.into(),
            transform: Transform::from_translation(t),
            children,
            extras: extras.map(str::to_string),
        }
    }

    #[test]
    fn the_model_table_matches_the_game_data() {
        let m = ModelData::embedded();
        assert_eq!(&ModelData::load(), m, "disk copy matches the built-in one");
        let d = GameData::embedded();
        for g in &m.guns {
            assert!(d.weapon_index(&g.weapon).is_some(), "{}", g.weapon);
        }
        for p in &m.parts {
            let a = d.attachment(&p.id).unwrap_or_else(|| panic!("{} is not in attachments.ron", p.id));
            let magnified = matches!(a.zoom.as_ref(), Some(z) if zoom_of(z) > 2.0);
            assert_eq!(p.scope.is_some(), magnified, "{}: scope", p.id);
        }
        // Every registered part with a model of a modelled gun has a row.
        for a in d.attachments.attachments.iter().filter(|a| a.fits.iter().any(|w| w != "sk9_skink")) {
            assert!(m.part(&a.id).is_some(), "{} has no model row", a.id);
        }
    }

    fn zoom_of(z: &vetf_sim::data::Zoom) -> f32 {
        match z {
            vetf_sim::data::Zoom::Fixed(v) => *v,
            vetf_sim::data::Zoom::Levels(v) => v[0],
        }
    }

    /// A loadout's model: its attachments with a model row, and a magazine and stock even when it names none.
    #[test]
    fn a_loadout_picks_its_parts() {
        let m = ModelData::embedded();
        let d = GameData::embedded();
        let ids = |key: &GunKey| key.parts.iter().map(|&i| m.parts[i].id.as_str()).collect::<Vec<_>>();
        let attach = ["grip_vertical", "laser", "mag_drum60", "mako_stock_light"].map(String::from);
        let mako = WeaponLoadout::resolve(&d, "ar7_mako", &[], &attach).unwrap();
        let key = m.key(&d, &mako).unwrap();
        assert_eq!(m.guns[key.gun].weapon, "ar7_mako");
        let parts = ids(&key);
        for want in ["grip_vertical", "laser", "mag_drum60", "mako_stock_light", "optic_holo"] {
            assert!(parts.contains(&want), "{want} in {parts:?}");
        }
        assert!(!parts.contains(&"mag_30") && !parts.contains(&"mako_stock_standard"), "{parts:?}");
        let mut bare = WeaponLoadout::resolve(&d, "vk50_warden", &[], &[]).unwrap();
        bare.attachments.clear();
        assert_eq!(ids(&m.key(&d, &bare).unwrap()), ["mag_5", "warden_stock_standard"]);
        let skink = WeaponLoadout::resolve(&d, "sk9_skink", &[], &[]).unwrap();
        assert_eq!(m.key(&d, &skink), None, "the Skink has no model");
    }

    /// Node places add up from the root, and an ADS socket brings its eye relief.
    #[test]
    fn layouts_place_nodes_from_the_root() {
        let nodes = vec![
            node("ATT_x", Vec3::new(0.0, 0.01, 0.0), vec![1], None),
            node("ATT_x_SOCKET_ADS", Vec3::new(0.0, 0.04, -0.03), vec![], Some(r#"{"eye_relief_m": 0.05}"#)),
        ];
        let l = Layout::from_nodes(&nodes);
        assert!(l.nodes["ATT_x_SOCKET_ADS"].translation.distance(Vec3::new(0.0, 0.05, -0.03)) < 1e-6);
        assert_eq!(l.ads.map(|a| a.1), Some(0.05));
    }

    /// Aimed, the optic's eye point is the camera: the ADS socket lies on the view axis, eye relief ahead,
    /// so the reticle is on the aim point. From the hip the muzzle is right of and below the centre, ahead.
    #[test]
    fn aimed_the_sight_line_is_the_view_axis() {
        let m = ModelData::embedded();
        for (gun, base, optic) in [
            ("ar7_mako", "models/weapons/mako/mako_base.glb", "models/weapons/optics/ATT_optic_holo.glb"),
            ("ar7_mako", "models/weapons/mako/mako_base.glb", "models/weapons/optics/ATT_optic_3x.glb"),
            ("vk50_warden", "models/weapons/warden/warden_base.glb", "models/weapons/optics/ATT_optic_sniper.glb"),
        ] {
            let (Some(b), Some(o)) = (glb_nodes(&asset(base)), glb_nodes(&asset(optic))) else {
                eprintln!("{base} / {optic} not checked out (Git LFS); skipped");
                continue;
            };
            let row = m.guns.iter().find(|g| g.weapon == gun).unwrap();
            let (base, optic) = (Layout::from_nodes(&b), Layout::from_nodes(&o));
            let (ads, relief) = optic.ads.expect("the optic has an ADS socket");
            assert!(relief > 0.03, "{gun}: eye relief {relief}");
            let rig = first_person_rig(row, &base, Some((&optic, None))).unwrap();
            let rail = base.nodes[&format!("{}_SOCKET_Optic", row.prefix)];
            let sight = rig.ads.transform_point((rail * ads).translation);
            assert!(sight.truncate().length() < 1e-5, "{gun}: ADS socket on the view axis: {sight}");
            assert!((sight.z + relief).abs() < 1e-5, "{gun}: eye relief ahead of the eye: {sight}");
            let aimed = rig.pose(1.0).transform_point(rig.muzzle);
            assert!(aimed.x.abs() < 1e-4 && aimed.y < 0.0 && aimed.z < -0.4, "{gun}: aimed muzzle {aimed}");
            let hip = rig.pose(0.0).transform_point(rig.muzzle);
            assert!(hip.x > 0.05 && hip.y < -0.05 && hip.z < -0.5, "{gun}: hip muzzle {hip}");
            // The gun faces ahead: the muzzle is further ahead than the grip, and the shooter's right is +X.
            let right = rig.ads.rotation * Vec3::NEG_X;
            assert!(right.x > 0.99, "{gun}: shooter's right {right}");
        }
    }

    /// No optic: the eye sits over the bare rail, the gun centred under the aim point.
    #[test]
    fn with_no_optic_the_gun_sits_centred_low() {
        let row = &ModelData::embedded().guns[0];
        let socket = |slot: &str, t: Vec3| node(&format!("{}_SOCKET_{slot}", row.prefix), t, vec![], None);
        let base = Layout::from_nodes(&[
            socket("Optic", Vec3::new(0.0, 0.084, 0.0855)),
            socket("Muzzle", Vec3::new(0.0, 0.05, 0.565)),
        ]);
        let rig = first_person_rig(row, &base, None).unwrap();
        assert_eq!(rig.scope, None);
        let rail = rig.ads.transform_point(Vec3::new(0.0, 0.084, 0.0855));
        assert!(rail.x.abs() < 1e-6, "centred: {rail}");
        assert!((rail.y + row.no_optic_eye.height).abs() < 1e-5 && rail.z < 0.0, "under and ahead: {rail}");
    }

    /// The projector is a pickable 1x optic for both modelled guns, drawn from its own export with its flap clip,
    /// and aimed its hologram floats on the aim point in front of the eye.
    #[test]
    fn the_projector_is_a_1x_sight_with_its_hologram_on_the_aim_point() {
        let d = GameData::embedded();
        let a = d.attachment("optic_projector").expect("in attachments.ron");
        assert_eq!((a.cat, a.name.as_str()), (AttachmentCategory::Optic, "PROJECTOR"));
        assert!(matches!(a.zoom, Some(vetf_sim::data::Zoom::Fixed(z)) if (z - 1.2).abs() < 1e-6));
        for gun in ["ar7_mako", "vk50_warden"] {
            let l = WeaponLoadout::resolve(&d, gun, &[], &["optic_projector".into()]).unwrap();
            assert!(l.attachments.contains(&"optic_projector".to_string()), "{gun}");
            assert!((l.zoom - 1.2).abs() < 1e-6, "{gun}");
        }
        let m = ModelData::embedded();
        let row = &m.parts[m.part("optic_projector").unwrap()];
        assert_eq!((row.socket.as_str(), row.scope), ("Optic", None));
        let t = row.projector.expect("projector timings");
        assert!(t.flap_open_s > 0.0 && t.hologram_fade_s > 0.0 && (0.0..1.0).contains(&t.hologram_from_ads));

        let path = asset(&row.file);
        let (Some(json), Some(nodes), Some(base)) =
            (glb_json(&path), glb_nodes(&path), glb_nodes(&asset("models/weapons/mako/mako_base.glb")))
        else {
            eprintln!("{} not checked out (Git LFS); skipped", row.file);
            return;
        };
        let clips: Vec<&str> =
            json["animations"].as_array().unwrap().iter().filter_map(|a| a["name"].as_str()).collect();
        assert!(clips.contains(&PROJECTOR_CLIP), "{clips:?}");
        let optic = Layout::from_nodes(&nodes);
        let hologram = optic.nodes.keys().find(|n| Role::of(n) == Role::Hologram).expect("a hologram node");
        let gun = m.guns.iter().find(|g| g.weapon == "ar7_mako").unwrap();
        let base = Layout::from_nodes(&base);
        let rig = first_person_rig(gun, &base, Some((&optic, None))).unwrap();
        let rail = base.nodes["MAKO_SOCKET_Optic"];
        let at = rig.ads.transform_point((rail * optic.nodes[hologram]).translation);
        assert!(at.truncate().length() < 1e-4, "on the aim point: {at}");
        assert!((-0.18..-0.1).contains(&at.z), "a hand's width ahead of the eye: {at}");
    }

    /// Optic parts are told apart by their node names; the glass clears, the reticle glows one-sided.
    #[test]
    fn optic_glass_and_reticles_are_dressed_for_the_game() {
        assert_eq!(Role::of("ATT_optic_holo_Glass"), Role::Glass);
        assert_eq!(Role::of("ATT_optic_reddot_Reticle"), Role::Reticle);
        assert_eq!(Role::of("ATT_optic_projector_Hologram"), Role::Hologram);
        assert_eq!(Role::of("ATT_optic_holo_Glint"), Role::Other);
        assert_eq!(Role::of("ATT_optic_3x_Ocular"), Role::Other);

        let look = ModelData::embedded().optics;
        assert!(look.glass_alpha > 0.0 && look.glass_alpha < 0.3, "clearer than the export's 0.30");
        let mut glass = StandardMaterial {
            base_color: Color::srgba(0.03, 0.07, 0.09, 0.3),
            alpha_mode: AlphaMode::Blend,
            clearcoat: 1.0,
            ..default()
        };
        look.dress(Role::Glass, &mut glass);
        assert_eq!((glass.base_color.alpha(), glass.clearcoat), (look.glass_alpha, 0.0));
        let mut reticle =
            StandardMaterial { emissive: LinearRgba::rgb(0.2, 0.8, 1.0), double_sided: true, ..default() };
        look.dress(Role::Reticle, &mut reticle);
        assert!((reticle.emissive.green - 0.8 * look.reticle_glow).abs() < 1e-5);
        assert!(!reticle.double_sided && reticle.cull_mode == Some(Face::Back) && reticle.depth_bias > 0.0);
        let body = StandardMaterial::default();
        let mut other = body.clone();
        look.dress(Role::Other, &mut other);
        assert_eq!(other.base_color, body.base_color);
    }

    /// The flaps open over their time as the gun comes up and stay open while it is up, also between simulation
    /// ticks; the hologram waits for most of the ADS blend, then fades in. Letting go folds them again.
    #[test]
    fn the_projector_opens_with_the_ads_blend() {
        let t = ProjectorTiming { flap_open_s: 0.12, hologram_from_ads: 0.8, hologram_fade_s: 0.08 };
        let mut s = ProjectorState::default();
        let dt = 0.01;
        s.step(&t, 0.0, dt);
        assert_eq!((s.flaps, s.hologram), (0.0, 0.0), "hip: folded, hidden");
        // ADS rises over 0.3 s; frames run twice per tick, so every other frame sees the same blend.
        let mut ads = 0.0;
        for frame in 0..10 {
            if frame % 2 == 0 {
                ads += 0.05;
            }
            s.step(&t, ads, dt);
        }
        assert!((s.flaps - 10.0 * dt / 0.12).abs() < 1e-5, "opening steadily: {}", s.flaps);
        assert_eq!(s.hologram, 0.0, "not before {} ADS", t.hologram_from_ads);
        while ads < 0.85 {
            ads += 0.025;
            s.step(&t, ads, dt);
        }
        assert_eq!(s.flaps, 1.0);
        assert!(s.hologram > 0.0 && s.hologram < 1.0, "fading in: {}", s.hologram);
        for _ in 0..10 {
            s.step(&t, 1.0, dt);
        }
        assert_eq!((s.flaps, s.hologram), (1.0, 1.0), "held up: open and shown");
        s.step(&t, 0.97, dt);
        assert!(s.flaps < 1.0 && s.hologram < 1.0, "letting go folds and fades at once");
        for _ in 0..20 {
            s.step(&t, 0.97, dt);
        }
        assert_eq!((s.flaps, s.hologram), (0.0, 0.0), "between ticks the gun is still going down");
    }

    /// The bipod rides folded: its legs, splay and feet take the export's folded pose, which tucks the feet up
    /// under the handguard.
    #[test]
    fn a_pose_turns_the_moving_nodes() {
        assert_eq!(pose_rotation(r#"{"pose_open_quat_gltf_xyzw": [0, 0, 0, 1]}"#, "folded"), None);
        assert_eq!(pose_rotation(r#"{"pose_folded_quat_gltf_xyzw": [0, 0]}"#, "folded"), None);
        let half = pose_rotation(r#"{"pose_folded_quat_gltf_xyzw": [0, 0, 1, 1]}"#, "folded").unwrap();
        assert!(half.abs_diff_eq(Quat::from_rotation_z(FRAC_PI_2_F32), 1e-5), "{half}");

        let m = ModelData::embedded();
        let row = &m.parts[m.part("bipod").unwrap()];
        assert_eq!(row.pose.as_deref(), Some("folded"));
        let Some(nodes) = glb_nodes(&asset(&row.file)) else {
            eprintln!("{} not checked out (Git LFS); skipped", row.file);
            return;
        };
        let folded: Vec<RawNode> = nodes
            .iter()
            .map(|n| {
                let mut n = n.clone();
                if let Some(q) = n.extras.as_deref().and_then(|e| pose_rotation(e, "folded")) {
                    n.transform.rotation = q;
                }
                n
            })
            .collect();
        let feet = |l: &Layout| l.nodes["ATT_bipod_Foot_L"].translation;
        let (deployed, folded) = (feet(&Layout::from_nodes(&nodes)), feet(&Layout::from_nodes(&folded)));
        assert!(deployed.y < -0.15, "exported deployed: {deployed}");
        assert!(folded.y > -0.06 && folded.z > 0.1, "folded up and forward, along the barrel: {folded}");
    }

    /// Every scope picture marks the aim point: a mark centred on the window's middle.
    #[test]
    fn scope_reticles_mark_the_aim_point() {
        for scope in [Scope::Prism, Scope::Rifle, Scope::Thermal] {
            let centred = reticle(scope).iter().any(|m| {
                let half = |v: Val| if let Val::Px(p) = v { p * 0.5 } else { -1.0 };
                m.at == (50.0, 50.0) && m.pull == (half(m.w), half(m.h))
            });
            assert!(centred, "{scope:?}");
        }
        let m = ModelData::embedded();
        let scope = |id: &str| m.parts[m.part(id).unwrap()].scope;
        assert_eq!(scope("optic_3x"), Some(Scope::Prism));
        assert_eq!(scope("optic_sniper"), Some(Scope::Rifle));
        assert_eq!(scope("optic_thermal"), Some(Scope::Thermal));
    }
}
