//! Weapon models: the guns and attachments made in Blender (copies of the exports in
//! `game/assets/models/weapons/`), put together for a loadout.
//!
//! `game/assets/data/weapon_models.ron` maps each gun and each gameplay attachment id to its GLB and socket.
//! Every file is loaded once at start-up. A gun is its base scene; once that is in the world, each chosen part
//! (optic, stock, mag, under, side, shield) is spawned as a child of its socket node, found by name. The
//! nodes' places, read from the loaded files, also give the first-person poses ([`ViewmodelRig`]): the hip
//! pose from the data, the aimed pose that puts the optic's eye point on the camera, and the muzzle.
//!
//! glTF axes: the muzzle is +Z, up +Y, the shooter's right -X (Blender's -Y front becomes +Z). The view looks
//! down -Z with +X on the right, so a gun turns half a turn about Y to face ahead.

use crate::AppState;
use crate::render::ViewmodelRig;
use bevy::gltf::{Gltf, GltfNode};
use bevy::light::NotShadowCaster;
use bevy::prelude::*;
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
        app.add_systems(Startup, load_models)
            .add_systems(Update, read_layouts)
            .add_systems(OnEnter(AppState::InGame), spawn_scope_overlay)
            .add_systems(Update, update_scope_overlay.run_if(in_state(AppState::InGame)));
    }
}

// ---------------------------------------------------------------------------------------------- data

/// `game/assets/data/weapon_models.ron`.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct ModelData {
    pub guns: Vec<GunRow>,
    pub parts: Vec<PartRow>,
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
    pub scope: bool,
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
pub fn first_person_rig(gun: &GunRow, base: &Layout, optic: Option<(&Layout, bool)>) -> Option<ViewmodelRig> {
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
        scope: optic.is_some_and(|(_, scope)| scope),
    })
}

// ---------------------------------------------------------------------------------------------- loading

struct ModelFile {
    gltf: Handle<Gltf>,
    scene: Handle<WorldAsset>,
    layout: Option<Layout>,
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
                failed: false,
            };
            (path.clone(), file)
        })
        .collect();
    commands.insert_resource(WeaponModels { data, files });
}

/// Reads each file's node layout once it has loaded (a file that fails keeps its gun on placeholder boxes).
fn read_layouts(
    mut models: ResMut<WeaponModels>,
    server: Res<AssetServer>,
    gltfs: Res<Assets<Gltf>>,
    nodes: Res<Assets<GltfNode>>,
) {
    if models.files.values().all(|f| f.layout.is_some() || f.failed) {
        return;
    }
    for (path, f) in models.files.iter_mut().filter(|(_, f)| f.layout.is_none() && !f.failed) {
        if server.load_state(&f.gltf).is_failed() || server.recursive_dependency_load_state(&f.gltf).is_failed() {
            warn!("weapon model {path} did not load; that gun keeps its placeholder");
            f.failed = true;
        } else if server.is_loaded_with_dependencies(&f.gltf) {
            f.layout = gltfs.get(&f.gltf).and_then(|g| Layout::from_gltf(g, &nodes));
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
        let parts: Vec<(String, Handle<WorldAsset>)> = key
            .parts
            .iter()
            .filter_map(|&i| {
                let part = &self.data.parts[i];
                Some((format!("{}_SOCKET_{}", gun.prefix, part.socket), self.files.get(&part.file)?.scene.clone()))
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
                for (socket, scene) in parts.iter().filter(|(s, _)| s == name.as_str()) {
                    let mut part =
                        commands.spawn((Name::new(socket.clone()), WorldAssetRoot(scene.clone()), ChildOf(node)));
                    if first_person {
                        part.observe(no_shadows);
                    }
                }
            }
        };
        commands.spawn((Name::new(gun.weapon.clone()), WorldAssetRoot(base), place, ChildOf(parent))).observe(snap);
    }
}

fn no_shadows(
    ready: On<WorldInstanceReady>,
    mut commands: Commands,
    tree: Query<&Children>,
    meshes: Query<(), With<Mesh3d>>,
) {
    for e in tree.iter_descendants(ready.entity).filter(|e| meshes.contains(*e)) {
        commands.entity(e).insert(NotShadowCaster);
    }
}

// ---------------------------------------------------------------------------------------------- scope view

/// Aimed through a magnified optic, the view is the scope's: black round a circular window, with a reticle.
/// The camera already zooms by the optic (`render::camera_fov`); the gun hides behind the overlay.
#[derive(Component)]
struct ScopeOverlay;

/// The scope window's diameter (share of the screen height).
const SCOPE_WINDOW_VH: f32 = 92.0;
const SCOPE_LINE: Color = Color::srgba(0.02, 0.02, 0.03, 0.9);
const SCOPE_DOT: Color = Color::srgb(0.55, 0.88, 1.0);

/// The gun is up to the eye with a magnified optic: the scope view replaces the viewmodel.
pub fn scoped(rig: &ViewmodelRig, ads: f32) -> bool {
    rig.scope && ads >= ADS_AIMED
}

fn spawn_scope_overlay(mut commands: Commands) {
    let root = commands
        .spawn((
            ScopeOverlay,
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
    // The window is a round node; its outline, wider than the screen, is the black around it.
    let window = commands
        .spawn((
            Node {
                width: Val::Vh(SCOPE_WINDOW_VH),
                height: Val::Vh(SCOPE_WINDOW_VH),
                border: UiRect::all(px(10)),
                border_radius: BorderRadius::MAX,
                align_items: AlignItems::Center,
                justify_content: JustifyContent::Center,
                ..default()
            },
            BorderColor::all(Color::srgba(0.0, 0.0, 0.0, 0.55)),
            Outline::new(Val::Vw(150.0), px(0), Color::BLACK),
            ChildOf(root),
        ))
        .id();
    // Fine cross hairs with heavier posts toward the rim, and a small ice dot on the aim point. Each piece is
    // placed by its corner (left / top in percent of the window) and centred on the line by a margin.
    let piece = |w: Val, h: Val, at: (f32, f32), centre: (f32, f32), color: Color| {
        let node = Node {
            position_type: PositionType::Absolute,
            width: w,
            height: h,
            left: percent(at.0),
            top: percent(at.1),
            margin: UiRect { left: px(-centre.0), top: px(-centre.1), ..default() },
            border_radius: if color == SCOPE_DOT { BorderRadius::MAX } else { BorderRadius::ZERO },
            ..default()
        };
        (node, BackgroundColor(color), ChildOf(window))
    };
    commands.spawn(piece(percent(100), px(2), (0.0, 50.0), (0.0, 1.0), SCOPE_LINE));
    commands.spawn(piece(px(2), percent(100), (50.0, 0.0), (1.0, 0.0), SCOPE_LINE));
    for at in [0.0, 70.0] {
        commands.spawn(piece(percent(30), px(6), (at, 50.0), (0.0, 3.0), SCOPE_LINE));
        commands.spawn(piece(px(6), percent(30), (50.0, at), (3.0, 0.0), SCOPE_LINE));
    }
    commands.spawn(piece(px(6), px(6), (50.0, 50.0), (3.0, 3.0), SCOPE_DOT));
}

fn update_scope_overlay(
    rig: Res<ViewmodelRig>,
    cli: Res<crate::config::Cli>,
    me: Query<(&PlayerWeapon, &Vitals), With<Controlled>>,
    mut overlay: Query<&mut Visibility, With<ScopeOverlay>>,
) {
    let show = cli.camera.is_none() && me.iter().next().is_some_and(|(w, v)| !v.health.dead && scoped(&rig, w.0.ads));
    for mut vis in &mut overlay {
        vis.set_if_neq(if show { Visibility::Inherited } else { Visibility::Hidden });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The GLB's JSON chunk (the art exports are binary glTF): its nodes as the layout reads them.
    fn glb_nodes(path: &std::path::Path) -> Option<Vec<RawNode>> {
        let bytes = std::fs::read(path).ok()?;
        if bytes.get(..4)? != b"glTF" {
            return None; // a Git LFS pointer: the file itself is not checked out
        }
        let len = u32::from_le_bytes(bytes.get(12..16)?.try_into().ok()?) as usize;
        let json: serde_json::Value = serde_json::from_slice(bytes.get(20..20 + len)?).ok()?;
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
            assert_eq!(p.scope, matches!(a.zoom.as_ref(), Some(z) if zoom_of(z) > 2.0), "{}: scope", p.id);
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
            let rig = first_person_rig(row, &base, Some((&optic, false))).unwrap();
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
        assert!(!rig.scope);
        let rail = rig.ads.transform_point(Vec3::new(0.0, 0.084, 0.0855));
        assert!(rail.x.abs() < 1e-6, "centred: {rail}");
        assert!((rail.y + row.no_optic_eye.height).abs() < 1e-5 && rail.z < 0.0, "under and ahead: {rail}");
    }
}
