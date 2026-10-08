//! Bullet impacts on the level: a hole or mark per surface kind, with depth, and a short debris puff.
//!
//! Every shot that meets the level arrives in [`Feedback::impacts`] (point, surface normal): our own shots
//! (`client::fire_claims`), other players' on the host (`server`) and the host's shot fx on a client
//! (`client::receive_feedback`). Each becomes a [`Mark`]:
//!
//! - **Surface.** The brush face the point lies on ([`find_face`]); its look picks a [`SurfaceKind`]
//!   (`data/impacts.ron`). Hedges, water and clips take none; players never do (only level hits arrive here).
//! - **Art.** One atlas (`textures/fx/impacts/`, built by `assets/fx/impacts/_src/build_atlas.py`) with 4 variants
//!   per kind. A mark has two layers sharing one normal map and one depth map: the core (what the shot exposes:
//!   crater, bore, bare metal, fresh wood, cracks, dust) and the paint (the surface itself bent or lifted: shards,
//!   a dent, splinters), tinted with the surface's colour so one atlas fits every wall. The depth map drives
//!   Bevy's parallax (`StandardMaterial::depth_map`), so a hole looks deep at an angle.
//! - **Shape.** A square on the face at a random variant, turn and size, clipped to the face's edges so it never
//!   hangs off a box into the air (where a coplanar neighbour continues the surface it is not clipped), lifted a
//!   few millimetres, alpha-blended, fading out at the end of its life.
//!
//! Cost: every mark is in two meshes (core, paint) rebuilt only when the set changes, so all marks are two draw
//! calls whatever their number (at most 2 x `max_marks` quads, 4-8 vertices each). The debris (dust puffs and
//! chips in one mesh, sparks in another) is two more draw calls while it flies. PARTICLES (VIDEO) picks the cap on
//! marks, the parallax layers (the per-pixel cost of a mark) and whether there is debris.

use crate::AppState;
use crate::client::Feedback;
use crate::config::{Cli, CurrentLevel};
use crate::render::{ViewCamera, look_color};
use crate::settings::Settings;
use bevy::asset::RenderAssetUsages;
use bevy::image::{ImageAddressMode, ImageLoaderSettings, ImageSampler, ImageSamplerDescriptor};
use bevy::light::NotShadowCaster;
use bevy::mesh::{Indices, PrimitiveTopology};
use bevy::pbr::ParallaxMappingMethod;
use bevy::prelude::*;
use bevy::render::render_resource::TextureFormat;
use serde::Deserialize;
use std::collections::{HashMap, VecDeque};
use std::f32::consts::TAU;
use vetf_sim::movement::collision::{Brush, CollisionWorld, Look};
use vetf_sim::rng::SplitMix;

pub struct ImpactsPlugin;

impl Plugin for ImpactsPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(ImpactData::load())
            .insert_resource(AtlasData::load())
            .init_resource::<Marks>()
            .init_resource::<Debris>()
            .add_systems(Startup, load_assets)
            .add_systems(Update, finish_images)
            .add_systems(OnEnter(AppState::InGame), spawn_layers)
            .add_systems(OnExit(AppState::InGame), clear)
            .add_systems(
                Update,
                (apply_quality, demo_shots, demo_live, spawn_marks, age_marks, rebuild_marks, fly_debris)
                    .chain()
                    .run_if(in_state(AppState::InGame)),
            );
    }
}

// ---------------------------------------------------------------------------------------------- data

/// What a surface is made of, for its bullet marks.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
pub enum SurfaceKind {
    /// Printed concrete and plaster: a chipped crater, hairline cracks, a dust ring.
    Plaster,
    /// Fibre-cement cladding and slate: a sharp punched hole, cracked shards.
    Cladding,
    /// Wood: a splintered hole, fibres torn along the grain.
    Wood,
    /// Painted metal: a clean punched hole, a bright bare-metal rim, a ring of chipped paint.
    Metal,
    /// Glass: a small star crack.
    Glass,
    /// Asphalt, paving, kerbs: a chipped pock mark, no deep hole.
    Pavement,
    /// Lawn, soil, gravel: a dark scuffed puff, no hole.
    Soil,
}

impl SurfaceKind {
    pub const ALL: [SurfaceKind; 7] = [
        SurfaceKind::Plaster,
        SurfaceKind::Cladding,
        SurfaceKind::Wood,
        SurfaceKind::Metal,
        SurfaceKind::Glass,
        SurfaceKind::Pavement,
        SurfaceKind::Soil,
    ];
}

/// How a mark is turned on its face.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
pub enum Spin {
    /// Any angle.
    Free,
    /// Along the wood grain: up on walls, along the boards (world Z) on floors, a few degrees either way.
    Grain,
}

#[derive(Debug, Clone, Deserialize)]
pub struct KindLook {
    pub size_m: f32,
    pub spin: Spin,
    pub dust: (u8, u8, u8),
    pub chip: (u8, u8, u8),
    pub puffs: u32,
    pub chips: u32,
    pub sparks: u32,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DebrisTuning {
    pub max: usize,
    pub gravity: f32,
    pub puff_life_s: (f32, f32),
    pub puff_speed: (f32, f32),
    pub puff_size_m: (f32, f32),
    pub puff_drag: f32,
    pub puff_alpha: f32,
    pub chip_life_s: (f32, f32),
    pub chip_speed: (f32, f32),
    pub chip_size_m: (f32, f32),
    pub spark_life_s: (f32, f32),
    pub spark_speed: (f32, f32),
    pub spark_streak_s: f32,
    pub spark_width_m: f32,
    pub spark_color: (f32, f32, f32),
}

/// `game/assets/data/impacts.ron`.
#[derive(Resource, Debug, Clone, Deserialize)]
pub struct ImpactData {
    pub life_s: f32,
    pub fade_s: f32,
    /// Per PARTICLES level (LOW, HIGH).
    pub max_marks: [usize; 2],
    pub parallax_layers: [f32; 2],
    pub relief_steps: [u32; 2],
    pub debris_on: [bool; 2],
    pub lift_m: f32,
    pub size_jitter: f32,
    pub grain_jitter_deg: f32,
    pub kinds: HashMap<SurfaceKind, KindLook>,
    pub looks: HashMap<Look, SurfaceKind>,
    pub tints: HashMap<Look, (u8, u8, u8)>,
    pub far: FarLook,
    pub debris: DebrisTuning,
}

/// How marks read from afar: from mip `from_mip` on, every smaller mip of the core albedo is darker and more
/// opaque, so a hole stays a dark dot at range instead of melting into the wall. Close up nothing changes.
#[derive(Debug, Clone, Deserialize)]
pub struct FarLook {
    pub from_mip: u32,
    pub darken_per_mip: f32,
    pub darken_max: f32,
    pub alpha_per_mip: f32,
}

/// Darken and thicken the mips of an sRGB RGBA8 atlas mip chain (`levels` levels from `w` x `h`, `grid` x
/// `grid` cells) from `far.from_mip` on (see [`FarLook`]), except in the cells `keep_cells` (the debris
/// sprites, which share the atlas: a dust puff 10-20 m away is mip 3-4 and must stay pale, sparks bright).
/// Levels where a cell is under a pixel are left alone (the cells blend there).
pub fn far_mips(
    data: &mut [u8],
    mut w: usize,
    mut h: usize,
    levels: u32,
    far: &FarLook,
    grid: u32,
    keep_cells: &[u32],
) {
    let to_linear: Vec<f32> = (0..256).map(|v| Color::srgb_u8(v as u8, 0, 0).to_linear().red).collect();
    let to_byte = |c: f32| (Color::linear_rgb(c, 0.0, 0.0).to_srgba().red * 255.0).round().clamp(0.0, 255.0) as u8;
    let grid = grid.max(1) as usize;
    let mut offset = 0;
    for level in 0..levels {
        let len = w * h * 4;
        if level >= far.from_mip && w >= grid && h >= grid && offset + len <= data.len() {
            let steps = (level - far.from_mip + 1) as f32;
            let keep = 1.0 - (far.darken_per_mip * steps).clamp(0.0, far.darken_max.clamp(0.0, 1.0));
            let gain = 1.0 + far.alpha_per_mip.max(0.0) * steps;
            for (i, px) in data[offset..offset + len].as_chunks_mut::<4>().0.iter_mut().enumerate() {
                let (x, y) = (i % w, i / w);
                let cell = (y * grid / h) * grid + x * grid / w;
                if keep_cells.contains(&(cell as u32)) {
                    continue;
                }
                for c in &mut px[..3] {
                    *c = to_byte(to_linear[*c as usize] * keep);
                }
                px[3] = (px[3] as f32 * gain).round().min(255.0) as u8;
            }
        }
        offset += len;
        (w, h) = ((w / 2).max(1), (h / 2).max(1));
    }
}

const EMBEDDED_DATA: &str = include_str!("../../../assets/data/impacts.ron");
const EMBEDDED_ATLAS: &str = include_str!("../../../assets/textures/fx/impacts/impacts_atlas.ron");

/// A data file from the asset folder (tunable without a rebuild), else the copy compiled into the binary.
fn load_ron<T: for<'a> Deserialize<'a>>(rel: &str, embedded: &str) -> T {
    let path = crate::config::assets_root().join(rel);
    match std::fs::read_to_string(&path).map(|text| ron::from_str(&text)) {
        Ok(Ok(d)) => return d,
        Ok(Err(e)) => error!("{} is invalid ({e}); using the built-in copy", path.display()),
        Err(_) => {}
    }
    ron::from_str(embedded).unwrap_or_else(|e| panic!("the built-in {rel} is invalid: {e}"))
}

impl ImpactData {
    #[cfg(test)]
    pub fn embedded() -> ImpactData {
        ron::from_str(EMBEDDED_DATA).expect("game/assets/data/impacts.ron is valid")
    }

    pub fn load() -> ImpactData {
        load_ron("data/impacts.ron", EMBEDDED_DATA)
    }

    pub fn kind(&self, look: Look) -> Option<SurfaceKind> {
        self.looks.get(&look).copied()
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct Sprites {
    pub puff: u32,
    pub chip: u32,
    pub spark: u32,
}

/// `textures/fx/impacts/impacts_atlas.ron`, written with the atlas: which cell holds what.
#[derive(Resource, Debug, Clone, Deserialize)]
pub struct AtlasData {
    /// Cells per row and column (the atlas is square).
    pub grid: u32,
    /// The depth map's 1.0 in half-widths of a mark.
    pub depth_ref: f32,
    pub kinds: HashMap<SurfaceKind, Vec<u32>>,
    /// Kinds whose cells have a paint layer.
    pub paint: Vec<SurfaceKind>,
    pub sprites: Sprites,
}

impl AtlasData {
    #[cfg(test)]
    pub fn embedded() -> AtlasData {
        ron::from_str(EMBEDDED_ATLAS).expect("textures/fx/impacts/impacts_atlas.ron is valid")
    }

    pub fn load() -> AtlasData {
        load_ron("textures/fx/impacts/impacts_atlas.ron", EMBEDDED_ATLAS)
    }

    /// A cell's top-left UV and its width (and height) in UV.
    pub fn cell(&self, index: u32) -> (Vec2, f32) {
        let w = 1.0 / self.grid as f32;
        (Vec2::new((index % self.grid) as f32 * w, (index / self.grid) as f32 * w), w)
    }

    /// `StandardMaterial::parallax_depth_scale`: depth in UV units, for a cell of `1 / grid` UV: a depth map value
    /// of 1 is `depth_ref` half-widths of the mark, whatever its size.
    pub fn parallax_depth_scale(&self) -> f32 {
        self.depth_ref * 0.5 / self.grid as f32
    }
}

// ---------------------------------------------------------------------------------------------- faces

/// The face a level point lies on: the brush and its plane whose normal is `normal`, the point on (or a few
/// millimetres in front of) that plane and inside the brush. `None` when no brush face is there.
pub fn find_face(world: &CollisionWorld, point: Vec3, normal: Vec3) -> Option<(usize, usize)> {
    const ON: f32 = 0.01;
    world.brushes.iter().enumerate().filter(|(_, b)| b.blocks_bullets()).find_map(|(i, b)| {
        let k =
            b.planes.iter().position(|p| p.normal.dot(normal) > 0.999 && (p.normal.dot(point) - p.dist).abs() < ON)?;
        let inside = b.planes.iter().enumerate().all(|(j, p)| j == k || p.normal.dot(point) <= p.dist + ON);
        inside.then_some((i, k))
    })
}

/// Whether `point` (on a plane facing `normal`) lies on a coplanar face of another brush than `skip`: the surface
/// goes on past `skip`'s edge there.
fn covered(world: &CollisionWorld, skip: usize, point: Vec3, normal: Vec3) -> bool {
    const ON: f32 = 0.003;
    world.brushes.iter().enumerate().any(|(i, b)| {
        i != skip
            && b.look != Look::Invisible
            && b.planes
                .iter()
                .position(|p| p.normal.dot(normal) > 0.999 && (p.normal.dot(point) - p.dist).abs() < ON)
                .is_some_and(|k| {
                    b.planes.iter().enumerate().all(|(j, p)| j == k || p.normal.dot(point) <= p.dist + 0.001)
                })
    })
}

/// A mark's frame on its face: `t` its right (+U), `b` its up (image top), `n` out of the face; b = n x t.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Frame {
    pub t: Vec3,
    pub b: Vec3,
    pub n: Vec3,
}

impl Frame {
    /// Turned by `angle` from an arbitrary start.
    pub fn free(n: Vec3, angle: f32) -> Frame {
        let t0 = n.any_orthonormal_vector();
        let b0 = n.cross(t0);
        let t = t0 * angle.cos() + b0 * angle.sin();
        Frame { t, b: n.cross(t), n }
    }

    /// Up along the wood grain (world up on walls, world Z on floors and ceilings, as the board textures run),
    /// flipped or not, turned by `jitter` radians.
    pub fn grain(n: Vec3, flip: bool, jitter: f32) -> Frame {
        let g = if n.y.abs() > 0.9 { Vec3::Z } else { Vec3::Y };
        let b = (g - n * n.dot(g)).normalize_or(n.any_orthonormal_vector());
        let b = if flip { -b } else { b };
        let t = b.cross(n);
        let (s, c) = jitter.sin_cos();
        let t2 = t * c + b * s;
        Frame { t: t2, b: n.cross(t2), n }
    }
}

/// The outline of a square mark of half-size `half` centred on `point` (on face `plane` of brush `brush`), in
/// `frame`: clipped to the face's edges except where a coplanar neighbour continues the surface, lifted `lift`
/// off it. Each vertex carries its UV in the atlas cell (`uv0` top-left, `uw` wide).
pub fn mark_outline(
    world: &CollisionWorld,
    brush: usize,
    plane: usize,
    point: Vec3,
    frame: Frame,
    half: f32,
    lift: f32,
    uv0: Vec2,
    uw: f32,
) -> Vec<(Vec3, Vec2)> {
    let b: &Brush = &world.brushes[brush];
    let face = b.planes[plane];
    let n = face.normal;
    // the centre on the face itself (a trace stops a skin short of it)
    let c = point - n * (n.dot(point) - face.dist);
    let mut poly = vec![Vec2::new(-half, -half), Vec2::new(half, -half), Vec2::new(half, half), Vec2::new(-half, half)];
    for (j, p) in b.planes.iter().enumerate() {
        if j == plane || p.normal.dot(n).abs() > 0.999 {
            continue;
        }
        // in the face's 2D frame: f(x, y) = f0 + x gx + y gy <= 0 keeps a point
        let f0 = p.normal.dot(c) - p.dist;
        let g = Vec2::new(p.normal.dot(frame.t), p.normal.dot(frame.b));
        if poly.iter().all(|q| f0 + q.dot(g) <= 0.0) {
            continue;
        }
        // the surface may go on past this edge on a neighbour's face
        let out = (p.normal - n * p.normal.dot(n)).normalize_or_zero();
        let reach = -f0 / g.length().max(1e-6);
        if covered(world, brush, c + out * (reach + 0.01), n) {
            continue;
        }
        poly = clip(&poly, f0, g);
        if poly.len() < 3 {
            return Vec::new();
        }
    }
    poly.iter()
        .map(|q| {
            let pos = c + frame.t * q.x + frame.b * q.y + n * lift;
            let uv = uv0 + Vec2::new(q.x / half * 0.5 + 0.5, 0.5 - q.y / half * 0.5) * uw;
            (pos, uv)
        })
        .collect()
}

/// Sutherland-Hodgman: the part of a convex polygon where f0 + p.g <= 0.
fn clip(poly: &[Vec2], f0: f32, g: Vec2) -> Vec<Vec2> {
    let f = |p: Vec2| f0 + p.dot(g);
    let mut out = Vec::with_capacity(poly.len() + 1);
    for i in 0..poly.len() {
        let (a, b) = (poly[i], poly[(i + 1) % poly.len()]);
        let (fa, fb) = (f(a), f(b));
        if fa <= 0.0 {
            out.push(a);
        }
        if (fa <= 0.0) != (fb <= 0.0) {
            out.push(a + (b - a) * (fa / (fa - fb)));
        }
    }
    out
}

/// The signed area of an outline on a plane facing `n`.
#[cfg(test)]
pub fn outline_area(verts: &[(Vec3, Vec2)], n: Vec3) -> f32 {
    let mut s = Vec3::ZERO;
    for i in 0..verts.len() {
        s += verts[i].0.cross(verts[(i + 1) % verts.len()].0);
    }
    0.5 * s.dot(n)
}

// ---------------------------------------------------------------------------------------------- marks

/// One bullet mark on the level.
#[derive(Debug, Clone)]
pub struct Mark {
    pub kind: SurfaceKind,
    /// The clipped outline, world space, with atlas UVs.
    pub verts: Vec<(Vec3, Vec2)>,
    pub frame: Frame,
    /// The surface's colour (linear) for the paint layer.
    pub tint: LinearRgba,
    pub paint: bool,
    pub age_s: f32,
}

/// Forces a kind, variant and turn (`--demo-ui impacts-sheet`).
#[derive(Debug, Clone, Copy)]
pub struct Force {
    pub kind: SurfaceKind,
    pub variant: usize,
    pub angle: f32,
    pub scale: f32,
}

#[derive(Resource, Default)]
pub struct Marks {
    pub list: VecDeque<Mark>,
    dirty: bool,
    shots: u64,
    /// The last variant per kind, so the same one never comes twice in a row.
    last: HashMap<SurfaceKind, u32>,
}

impl Marks {
    /// A mark for an impact at `point` on a surface facing `normal`, if that surface takes marks. The oldest
    /// marks past `max` go.
    #[allow(clippy::too_many_arguments)]
    pub fn add(
        &mut self,
        world: &CollisionWorld,
        data: &ImpactData,
        atlas: &AtlasData,
        showhome: bool,
        point: Vec3,
        normal: Vec3,
        max: usize,
        force: Option<Force>,
    ) -> Option<&Mark> {
        let (brush, plane) = find_face(world, point, normal)?;
        let look = world.brushes[brush].look;
        let kind = match force {
            Some(f) => f.kind,
            None => data.kind(look)?,
        };
        let tuning = data.kinds.get(&kind)?;
        let cells = atlas.kinds.get(&kind).filter(|c| !c.is_empty())?;
        self.shots += 1;
        let mut rng = SplitMix::from_parts(&[self.shots, point.x.to_bits() as u64, point.z.to_bits() as u64]);
        let cell = match force {
            Some(f) => cells[f.variant % cells.len()],
            None => {
                let len = cells.len();
                let mut i = (rng.next_u64() % len as u64) as usize;
                if Some(cells[i]) == self.last.get(&kind).copied() && len > 1 {
                    i = (i + 1 + (rng.next_u64() % (len as u64 - 1)) as usize) % len;
                }
                cells[i]
            }
        };
        self.last.insert(kind, cell);
        let n = world.brushes[brush].planes[plane].normal;
        let frame = match (force, tuning.spin) {
            (Some(f), Spin::Grain) => Frame::grain(n, false, f.angle),
            (Some(f), Spin::Free) => Frame::free(n, f.angle),
            (None, Spin::Free) => Frame::free(n, rng.next_f32() * TAU),
            (None, Spin::Grain) => {
                Frame::grain(n, rng.next_f32() < 0.5, rng.next_signed() * data.grain_jitter_deg.to_radians())
            }
        };
        let scale = force.map_or(1.0 + rng.next_signed() * data.size_jitter, |f| f.scale);
        let (uv0, uw) = atlas.cell(cell);
        let verts = mark_outline(world, brush, plane, point, frame, tuning.size_m * scale * 0.5, data.lift_m, uv0, uw);
        if verts.len() < 3 {
            return None;
        }
        let tint = match data.tints.get(&look).filter(|_| showhome) {
            Some(&(r, g, b)) => Color::srgb_u8(r, g, b).to_linear(),
            None => look_color(look).0.to_linear(),
        };
        while self.list.len() >= max.max(1) {
            self.list.pop_front();
        }
        self.list.push_back(Mark { kind, verts, frame, tint, paint: atlas.paint.contains(&kind), age_s: 0.0 });
        self.dirty = true;
        self.list.back()
    }

    /// Age the marks; the expired go. True when the meshes must be rebuilt (a mark went or is fading).
    pub fn age(&mut self, dt: f32, life_s: f32, fade_s: f32) -> bool {
        let before = self.list.len();
        for m in &mut self.list {
            m.age_s += dt;
        }
        self.list.retain(|m| m.age_s < life_s);
        let fading = self.list.iter().any(|m| m.age_s > life_s - fade_s);
        self.dirty |= fading || self.list.len() != before;
        self.dirty
    }
}

/// A mark's opacity at its age: 1, then down to 0 over the last `fade_s` of its life.
pub fn mark_alpha(age_s: f32, life_s: f32, fade_s: f32) -> f32 {
    ((life_s - age_s) / fade_s.max(1e-3)).clamp(0.0, 1.0)
}

/// The two meshes and their entities: the core layer and the paint layer, then the debris.
#[derive(Resource)]
struct ImpactAssets {
    core: (Handle<Mesh>, Handle<StandardMaterial>),
    paint: (Handle<Mesh>, Handle<StandardMaterial>),
    dust: (Handle<Mesh>, Handle<StandardMaterial>),
    sparks: (Handle<Mesh>, Handle<StandardMaterial>),
    /// PNGs waiting for their mip chain and sampler: (source, finished, sRGB, far mips darkened).
    pending: Vec<(Handle<Image>, Handle<Image>, bool, bool)>,
}

#[derive(Component, Clone, Copy, PartialEq, Eq)]
enum Layer {
    Core,
    Paint,
    Dust,
    Sparks,
}

const DIR: &str = "textures/fx/impacts";

fn load_assets(
    mut commands: Commands,
    server: Res<AssetServer>,
    images: Res<Assets<Image>>,
    atlas: Res<AtlasData>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let mut pending = Vec::new();
    let mut image = |name: &str, srgb: bool, far: bool| {
        let source: Handle<Image> = server
            .load_builder()
            .with_settings(move |s: &mut ImageLoaderSettings| s.is_srgb = srgb)
            .load(format!("{DIR}/{name}.png"));
        let done = images.reserve_handle();
        pending.push((source, done.clone(), srgb, far));
        done
    };
    let albedo = image("impacts_albedo", true, true);
    let paint = image("impacts_paint", true, false);
    let normal = image("impacts_normal", false, false);
    let depth_mr = image("impacts_depth_mr", false, false);
    let mark = |base: Handle<Image>, bias: f32| StandardMaterial {
        base_color_texture: Some(base),
        normal_map_texture: Some(normal.clone()),
        depth_map: Some(depth_mr.clone()),
        metallic_roughness_texture: Some(depth_mr.clone()),
        perceptual_roughness: 1.0,
        metallic: 1.0,
        parallax_depth_scale: atlas.parallax_depth_scale(),
        max_parallax_layer_count: 16.0,
        parallax_mapping_method: ParallaxMappingMethod::Occlusion,
        alpha_mode: AlphaMode::Blend,
        // Drawn after what is behind them; the core over the paint (it sorts as nearer).
        depth_bias: bias,
        ..default()
    };
    let core_mat = materials.add(mark(albedo.clone(), 2.0));
    let paint_mat = materials.add(mark(paint, 1.0));
    let dust_mat = materials.add(StandardMaterial {
        base_color_texture: Some(albedo.clone()),
        perceptual_roughness: 1.0,
        alpha_mode: AlphaMode::Blend,
        cull_mode: None,
        double_sided: true,
        depth_bias: 3.0,
        ..default()
    });
    // Blended, not added: added to a white truck an orange spark would only saturate to white.
    let spark_mat = materials.add(StandardMaterial {
        base_color_texture: Some(albedo),
        unlit: true,
        alpha_mode: AlphaMode::Blend,
        depth_bias: 4.0,
        cull_mode: None,
        double_sided: true,
        fog_enabled: false,
        ..default()
    });
    // A degenerate triangle with every attribute until there is something to draw (an empty mesh upsets the
    // mesh allocator); the layers start hidden.
    let mut empty = || {
        let z = vec![[0.0f32; 3]; 3];
        meshes.add(
            Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default())
                .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, z.clone())
                .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, z)
                .with_inserted_attribute(Mesh::ATTRIBUTE_TANGENT, vec![[1.0f32, 0.0, 0.0, 1.0]; 3])
                .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, vec![[0.0f32; 2]; 3])
                .with_inserted_attribute(Mesh::ATTRIBUTE_COLOR, vec![[0.0f32; 4]; 3])
                .with_inserted_indices(Indices::U32(vec![0, 1, 2])),
        )
    };
    commands.insert_resource(ImpactAssets {
        core: (empty(), core_mat),
        paint: (empty(), paint_mat),
        dust: (empty(), dust_mat),
        sparks: (empty(), spark_mat),
        pending,
    });
}

/// One loaded PNG per frame becomes its finished image: mip chain (`map_materials::mip_chain`, the albedo's far
/// mips darkened: [`FarLook`]), clamped anisotropic sampler (the cells must not wrap into each other).
fn finish_images(
    mut assets: ResMut<ImpactAssets>,
    mut images: ResMut<Assets<Image>>,
    server: Res<AssetServer>,
    data: Res<ImpactData>,
    atlas: Res<AtlasData>,
) {
    if let Some(i) = assets.pending.iter().position(|p| server.load_state(&p.0).is_failed()) {
        let (source, ..) = assets.pending.swap_remove(i);
        warn!("impact texture {:?} did not load; bullet marks will not draw", source.path());
        return;
    }
    let Some(i) = assets.pending.iter().position(|p| images.contains(&p.0)) else { return };
    let (source, done, srgb, far) = assets.pending.swap_remove(i);
    let Some(mut image) = images.remove(&source) else { return };
    image.sampler = ImageSampler::Descriptor(ImageSamplerDescriptor {
        address_mode_u: ImageAddressMode::ClampToEdge,
        address_mode_v: ImageAddressMode::ClampToEdge,
        anisotropy_clamp: 8,
        ..ImageSamplerDescriptor::linear()
    });
    let format = image.texture_descriptor.format;
    if matches!(format, TextureFormat::Rgba8UnormSrgb | TextureFormat::Rgba8Unorm)
        && image.texture_descriptor.mip_level_count == 1
        && let Some(base) = image.data.take()
    {
        let (w, h) = (image.width() as usize, image.height() as usize);
        let (mut chain, levels) = crate::map_materials::mip_chain(base, w, h, srgb);
        if far {
            let sprites = [atlas.sprites.puff, atlas.sprites.chip, atlas.sprites.spark];
            far_mips(&mut chain, w, h, levels, &data.far, atlas.grid, &sprites);
        }
        image.data = Some(chain);
        image.texture_descriptor.mip_level_count = levels;
    }
    if let Err(e) = images.insert(&done, image) {
        warn!("cannot finish an impact texture: {e:?}");
    }
}

fn spawn_layers(mut commands: Commands, assets: Res<ImpactAssets>) {
    for (layer, (mesh, material)) in [
        (Layer::Paint, &assets.paint),
        (Layer::Core, &assets.core),
        (Layer::Dust, &assets.dust),
        (Layer::Sparks, &assets.sparks),
    ] {
        commands.spawn((
            Name::new("Impact layer"),
            layer,
            Mesh3d(mesh.clone()),
            MeshMaterial3d(material.clone()),
            Transform::IDENTITY,
            Visibility::Hidden,
            NotShadowCaster,
            DespawnOnExit(AppState::InGame),
        ));
    }
}

fn clear(mut marks: ResMut<Marks>, mut debris: ResMut<Debris>) {
    marks.list.clear();
    marks.dirty = true;
    debris.list.clear();
}

/// PARTICLES level 0 (LOW) or 1 (HIGH).
fn particles_level(settings: &Settings) -> usize {
    settings.video.particles.index().min(1)
}

/// PARTICLES sets the parallax on the mark materials: its layers (0 turns it off) and relief refinement steps.
fn apply_quality(
    settings: Res<Settings>,
    data: Res<ImpactData>,
    assets: Res<ImpactAssets>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut applied: Local<Option<usize>>,
) {
    let l = particles_level(&settings);
    if *applied == Some(l) {
        return;
    }
    *applied = Some(l);
    let layers = data.parallax_layers[l];
    let method = match data.relief_steps[l] {
        0 => ParallaxMappingMethod::Occlusion,
        max_steps => ParallaxMappingMethod::Relief { max_steps },
    };
    for h in [&assets.core.1, &assets.paint.1] {
        if let Some(mut m) = materials.get_mut(h) {
            m.max_parallax_layer_count = layers;
            m.parallax_mapping_method = method;
        }
    }
}

/// New impacts become marks (and throw debris).
#[allow(clippy::too_many_arguments)]
fn spawn_marks(
    mut feedback: ResMut<Feedback>,
    level: Option<Res<CurrentLevel>>,
    data: Res<ImpactData>,
    atlas: Res<AtlasData>,
    settings: Res<Settings>,
    mut marks: ResMut<Marks>,
    mut debris: ResMut<Debris>,
) {
    if feedback.impacts.is_empty() {
        return;
    }
    let impacts = std::mem::take(&mut feedback.impacts);
    let Some(level) = level else { return };
    let showhome = level.name.eq_ignore_ascii_case("showhome");
    let l = particles_level(&settings);
    let max = data.max_marks[l];
    let skip = impacts.len().saturating_sub(max);
    for (point, normal) in impacts.into_iter().skip(skip) {
        if normal == Vec3::ZERO {
            continue;
        }
        let Some(mark) = marks.add(&level.world, &data, &atlas, showhome, point, normal, max, None) else { continue };
        if data.debris_on[l] {
            let (kind, n) = (mark.kind, mark.frame.n);
            debris.throw(&data, kind, point, n);
        }
    }
}

fn age_marks(time: Res<Time>, data: Res<ImpactData>, mut marks: ResMut<Marks>) {
    marks.age(time.delta_secs(), data.life_s, data.fade_s);
}

/// The marks' meshes, when the set changed: every mark's outline in both layers (the paint layer only for kinds
/// that have one), its frame as normal and tangent, its fade (and the paint layer's tint) as vertex colour.
fn rebuild_marks(
    data: Res<ImpactData>,
    mut marks: ResMut<Marks>,
    assets: Res<ImpactAssets>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut layers: Query<(&Layer, &mut Visibility)>,
) {
    if !marks.dirty {
        return;
    }
    marks.dirty = false;
    for (layer, handle) in [(Layer::Core, &assets.core.0), (Layer::Paint, &assets.paint.0)] {
        let paint = layer == Layer::Paint;
        let mesh = marks_mesh(marks.list.iter().filter(|m| !paint || m.paint), paint, data.life_s, data.fade_s);
        let empty = mesh.as_ref().is_none();
        if let Some(mesh) = mesh
            && let Err(e) = meshes.insert(handle, mesh)
        {
            warn!("cannot update the impact marks: {e:?}");
        }
        for (l, mut v) in &mut layers {
            if *l == layer {
                v.set_if_neq(if empty { Visibility::Hidden } else { Visibility::Visible });
            }
        }
    }
}

/// One mesh of marks (`None` when there are none): a triangle fan per outline.
pub fn marks_mesh<'a>(marks: impl Iterator<Item = &'a Mark>, paint: bool, life_s: f32, fade_s: f32) -> Option<Mesh> {
    let (mut pos, mut nor, mut tan, mut uv, mut col, mut idx) =
        (Vec::new(), Vec::new(), Vec::new(), Vec::new(), Vec::new(), Vec::new());
    for m in marks {
        let a = mark_alpha(m.age_s, life_s, fade_s);
        let c = if paint { [m.tint.red, m.tint.green, m.tint.blue, a] } else { [1.0, 1.0, 1.0, a] };
        let base = pos.len() as u32;
        for (p, t) in &m.verts {
            pos.push(p.to_array());
            nor.push(m.frame.n.to_array());
            tan.push([m.frame.t.x, m.frame.t.y, m.frame.t.z, 1.0]);
            uv.push(t.to_array());
            col.push(c);
        }
        for i in 1..m.verts.len() as u32 - 1 {
            idx.extend_from_slice(&[base, base + i, base + i + 1]);
        }
    }
    (!idx.is_empty()).then(|| {
        Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default())
            .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, pos)
            .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, nor)
            .with_inserted_attribute(Mesh::ATTRIBUTE_TANGENT, tan)
            .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, uv)
            .with_inserted_attribute(Mesh::ATTRIBUTE_COLOR, col)
            .with_inserted_indices(Indices::U32(idx))
    })
}

// ---------------------------------------------------------------------------------------------- debris

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PieceKind {
    Puff,
    Chip,
    Spark,
}

#[derive(Debug, Clone)]
pub struct Piece {
    pub kind: PieceKind,
    pub pos: Vec3,
    pub vel: Vec3,
    pub age_s: f32,
    pub life_s: f32,
    pub size: (f32, f32),
    pub color: LinearRgba,
    /// The surface's normal (dust and chips are lit like the surface they came off).
    pub normal: Vec3,
    pub spin: f32,
}

#[derive(Resource, Default)]
pub struct Debris {
    pub list: VecDeque<Piece>,
    shots: u64,
}

impl Debris {
    /// What one shot throws off a surface of `kind` at `point` (facing `n`): dust puffs drifting off it, chips flying
    /// out and falling, sparks off metal.
    pub fn throw(&mut self, data: &ImpactData, kind: SurfaceKind, point: Vec3, n: Vec3) {
        let Some(k) = data.kinds.get(&kind) else { return };
        let d = &data.debris;
        self.shots += 1;
        let mut rng = SplitMix::from_parts(&[self.shots, point.y.to_bits() as u64]);
        let range = |r: &mut SplitMix, (a, b): (f32, f32)| a + (b - a) * r.next_f32();
        let t0 = n.any_orthonormal_vector();
        let b0 = n.cross(t0);
        let aside = |r: &mut SplitMix, spread: f32| {
            let a = r.next_f32() * TAU;
            (n + (t0 * a.cos() + b0 * a.sin()) * spread * r.next_f32()).normalize()
        };
        let rgb = |c: (u8, u8, u8)| Color::srgb_u8(c.0, c.1, c.2).to_linear();
        for _ in 0..k.puffs {
            let dir = aside(&mut rng, 0.6);
            self.push(
                d.max,
                Piece {
                    kind: PieceKind::Puff,
                    pos: point + n * 0.02,
                    vel: dir * range(&mut rng, d.puff_speed),
                    age_s: 0.0,
                    life_s: range(&mut rng, d.puff_life_s),
                    size: (
                        d.puff_size_m.0 * (0.8 + 0.4 * rng.next_f32()),
                        d.puff_size_m.1 * (0.7 + 0.5 * rng.next_f32()),
                    ),
                    color: rgb(k.dust).with_alpha(d.puff_alpha),
                    normal: n,
                    spin: rng.next_f32() * TAU,
                },
            );
        }
        for _ in 0..k.chips {
            let dir = aside(&mut rng, 1.4);
            let s = range(&mut rng, d.chip_size_m);
            self.push(
                d.max,
                Piece {
                    kind: PieceKind::Chip,
                    pos: point + n * 0.01,
                    vel: dir * range(&mut rng, d.chip_speed),
                    age_s: 0.0,
                    life_s: range(&mut rng, d.chip_life_s),
                    size: (s, s),
                    color: rgb(k.chip),
                    normal: n,
                    spin: rng.next_f32() * TAU,
                },
            );
        }
        let hot = LinearRgba::rgb(d.spark_color.0, d.spark_color.1, d.spark_color.2);
        for _ in 0..k.sparks {
            let dir = aside(&mut rng, 1.8);
            self.push(
                d.max,
                Piece {
                    kind: PieceKind::Spark,
                    pos: point + n * 0.01,
                    vel: dir * range(&mut rng, d.spark_speed),
                    age_s: 0.0,
                    life_s: range(&mut rng, d.spark_life_s),
                    size: (d.spark_width_m, d.spark_width_m),
                    color: hot,
                    normal: n,
                    spin: 0.0,
                },
            );
        }
    }

    fn push(&mut self, max: usize, p: Piece) {
        while self.list.len() >= max.max(1) {
            self.list.pop_front();
        }
        self.list.push_back(p);
    }

    /// Move every piece on by `dt`: gravity on chips and sparks, drag on the dust; the spent go.
    pub fn step(&mut self, dt: f32, d: &DebrisTuning) {
        let drag = d.puff_drag.clamp(1e-4, 1.0).powf(dt);
        for p in &mut self.list {
            p.age_s += dt;
            match p.kind {
                PieceKind::Puff => p.vel = p.vel * drag + Vec3::Y * 0.15 * dt,
                PieceKind::Chip | PieceKind::Spark => p.vel -= Vec3::Y * d.gravity * dt,
            }
            p.pos += p.vel * dt;
            if p.kind == PieceKind::Chip {
                p.spin += dt * 14.0;
            }
        }
        self.list.retain(|p| p.age_s < p.life_s);
    }
}

/// Moves the debris and rebuilds its two meshes, facing the camera, while any flies.
fn fly_debris(
    time: Res<Time>,
    data: Res<ImpactData>,
    atlas: Res<AtlasData>,
    assets: Res<ImpactAssets>,
    mut debris: ResMut<Debris>,
    mut meshes: ResMut<Assets<Mesh>>,
    camera: Query<&GlobalTransform, With<ViewCamera>>,
    mut layers: Query<(&Layer, &mut Visibility)>,
    mut shown: Local<bool>,
) {
    if debris.list.is_empty() && !*shown {
        return;
    }
    debris.step(time.delta_secs(), &data.debris);
    let Ok(cam) = camera.single() else { return };
    let (dust, sparks) = debris_meshes(&debris, &atlas, &data.debris, cam);
    *shown = dust.is_some() || sparks.is_some();
    for (layer, handle, mesh) in [(Layer::Dust, &assets.dust.0, dust), (Layer::Sparks, &assets.sparks.0, sparks)] {
        let visible = mesh.is_some();
        if let Some(mesh) = mesh
            && let Err(e) = meshes.insert(handle, mesh)
        {
            warn!("cannot update the impact debris: {e:?}");
        }
        for (l, mut v) in &mut layers {
            if *l == layer {
                v.set_if_neq(if visible { Visibility::Visible } else { Visibility::Hidden });
            }
        }
    }
}

/// The debris as quads: dust and chips facing the camera (one mesh), sparks as streaks along their flight (the
/// other).
fn debris_meshes(
    debris: &Debris,
    atlas: &AtlasData,
    d: &DebrisTuning,
    cam: &GlobalTransform,
) -> (Option<Mesh>, Option<Mesh>) {
    let mut dust = Quads::default();
    let mut sparks = Quads::default();
    let (right, up) = (cam.right().as_vec3(), cam.up().as_vec3());
    let eye = cam.translation();
    for p in &debris.list {
        let t = (p.age_s / p.life_s).clamp(0.0, 1.0);
        match p.kind {
            PieceKind::Puff | PieceKind::Chip => {
                let (cell, size, alpha) = if p.kind == PieceKind::Puff {
                    let grow = 1.0 - (1.0 - t).powi(2);
                    (
                        atlas.sprites.puff,
                        p.size.0 + (p.size.1 - p.size.0) * grow,
                        (1.0 - t).powf(1.6) * (t / 0.08).min(1.0),
                    )
                } else {
                    (atlas.sprites.chip, p.size.0, ((1.0 - t) / 0.25).min(1.0))
                };
                let (s, c) = p.spin.sin_cos();
                let (r, u) = ((right * c + up * s) * size, (up * c - right * s) * size);
                let color = p.color.with_alpha(p.color.alpha * alpha);
                dust.quad(
                    [p.pos - r - u, p.pos + r - u, p.pos + r + u, p.pos - r + u],
                    p.normal,
                    atlas.cell(cell),
                    color,
                );
            }
            PieceKind::Spark => {
                let speed = p.vel.length();
                if speed < 1e-3 {
                    continue;
                }
                let dir = p.vel / speed;
                let len = (speed * d.spark_streak_s).clamp(0.02, 0.25);
                let side = dir.cross(eye - p.pos).normalize_or_zero() * p.size.0 * 0.5;
                let tail = p.pos - dir * len;
                let color = p.color.with_alpha(1.0 - t * t);
                sparks.quad(
                    [tail - side, p.pos - side, p.pos + side, tail + side],
                    p.normal,
                    atlas.cell(atlas.sprites.spark),
                    color,
                );
            }
        }
    }
    (dust.mesh(), sparks.mesh())
}

#[derive(Default)]
struct Quads {
    pos: Vec<[f32; 3]>,
    nor: Vec<[f32; 3]>,
    uv: Vec<[f32; 2]>,
    col: Vec<[f32; 4]>,
    idx: Vec<u32>,
}

impl Quads {
    /// Corners bottom-left, bottom-right, top-right, top-left of the cell `(top-left UV, width)`.
    fn quad(&mut self, corners: [Vec3; 4], n: Vec3, (uv0, w): (Vec2, f32), color: LinearRgba) {
        let base = self.pos.len() as u32;
        let uvs = [Vec2::new(0.0, 1.0), Vec2::new(1.0, 1.0), Vec2::new(1.0, 0.0), Vec2::new(0.0, 0.0)];
        for (p, t) in corners.iter().zip(uvs) {
            self.pos.push(p.to_array());
            self.nor.push(n.to_array());
            self.uv.push((uv0 + t * w).to_array());
            self.col.push(color.to_f32_array());
        }
        self.idx.extend_from_slice(&[base, base + 1, base + 2, base, base + 2, base + 3]);
    }

    fn mesh(self) -> Option<Mesh> {
        (!self.idx.is_empty()).then(|| {
            Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default())
                .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, self.pos)
                .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, self.nor)
                .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, self.uv)
                .with_inserted_attribute(Mesh::ATTRIBUTE_COLOR, self.col)
                .with_inserted_indices(Indices::U32(self.idx))
        })
    }
}

// ---------------------------------------------------------------------------------------------- demo

/// Seconds into the match before the demo shots (the fixed camera has settled by then).
const DEMO_AFTER_S: f32 = 1.0;
/// `--demo-ui impacts`: shots across this grid of the view (columns, rows), over this share of it.
const DEMO_GRID: (u32, u32) = (9, 5);
const DEMO_SPAN: f32 = 0.8;
/// `--demo-ui impacts-sheet`: the gap between marks, in metres.
const SHEET_STEP_M: f32 = 0.24;

/// `--demo-ui impacts`: once, shots from the camera through a grid over the view hit whatever is there, through
/// the same path real shots take (`Feedback::impacts`). `--demo-ui impacts-sheet`: on the face under the centre
/// of the view (`impacts-sheet:x,y,z`: toward that point), every kind (rows, top to bottom in
/// [`SurfaceKind::ALL`] order) in every variant (columns), upright, through the same placement as a shot's.
#[allow(clippy::too_many_arguments)]
fn demo_shots(
    cli: Res<Cli>,
    time: Res<Time>,
    level: Option<Res<CurrentLevel>>,
    data: Res<ImpactData>,
    atlas: Res<AtlasData>,
    camera: Query<(&GlobalTransform, &Projection), With<ViewCamera>>,
    mut feedback: ResMut<Feedback>,
    mut marks: ResMut<Marks>,
    mut since: Local<Option<f32>>,
    mut done: Local<bool>,
) {
    let Some(demo) = cli.demo_ui.as_deref().filter(|d| *d == "impacts" || d.starts_with("impacts-sheet")) else {
        return;
    };
    if *done {
        return;
    }
    let start = *since.get_or_insert(time.elapsed_secs());
    if time.elapsed_secs() - start < DEMO_AFTER_S {
        return;
    }
    let (Some(level), Ok((cam, Projection::Perspective(p)))) = (level, camera.single()) else { return };
    *done = true;
    let origin = cam.translation();
    if let Some(rest) = demo.strip_prefix("impacts-sheet") {
        // `impacts-sheet:x,y,z`: centred where the line from the camera toward that point meets the level
        let aim: Vec<f32> = rest.trim_start_matches(':').split(',').filter_map(|v| v.trim().parse().ok()).collect();
        let ahead = match aim[..] {
            [x, y, z] => (Vec3::new(x, y, z) - origin).normalize_or(cam.forward().as_vec3()),
            _ => cam.forward().as_vec3(),
        };
        let Some((d, n)) = level.world.raycast(origin, ahead, 100.0) else { return };
        let centre = origin + ahead * d;
        let face = Frame::grain(n, false, 0.0);
        let showhome = level.name.eq_ignore_ascii_case("showhome");
        let rows = SurfaceKind::ALL.len() as f32;
        for (row, kind) in SurfaceKind::ALL.into_iter().enumerate() {
            let variants = atlas.kinds.get(&kind).map_or(0, Vec::len);
            for col in 0..variants {
                let x = (col as f32 - (variants as f32 - 1.0) * 0.5) * SHEET_STEP_M;
                let y = ((rows - 1.0) * 0.5 - row as f32) * SHEET_STEP_M;
                let at = centre + face.t * x + face.b * y;
                let force = Force { kind, variant: col, angle: 0.0, scale: 1.0 };
                marks.add(&level.world, &data, &atlas, showhome, at, n, usize::MAX, Some(force));
            }
        }
        info!("demo: impact sheet of {} marks", marks.list.len());
        return;
    }
    let half_h = (p.fov * 0.5).tan();
    let half_w = half_h * p.aspect_ratio;
    let (cols, rows) = DEMO_GRID;
    for j in 0..rows {
        for i in 0..cols {
            let x = (i as f32 + 0.5) / cols as f32 * 2.0 - 1.0;
            let y = (j as f32 + 0.5) / rows as f32 * 2.0 - 1.0;
            let local = Vec3::new(x * half_w * DEMO_SPAN, y * half_h * DEMO_SPAN, -1.0).normalize();
            let dir = cam.rotation() * local;
            if let Some((d, normal)) = level.world.raycast(origin, dir, 300.0) {
                feedback.impacts.push((origin + dir * d, normal));
            }
        }
    }
    info!("demo: {} impacts", feedback.impacts.len());
}

/// `--demo-ui impacts-live`: shots per second, at random points over the view, for as long as the run lasts.
const LIVE_RATE_HZ: f32 = 12.0;
/// How often the live demos log their numbers.
const LIVE_LOG_S: f32 = 2.0;

/// `--demo-ui impacts-live`: a steady stream of shots at random points over the view (marks pile up to the cap,
/// debris flies all the time), through the same path real shots take. `--demo-ui impacts-idle`: the same view
/// without shots. Both log the marks, the debris and the frame rate every few seconds, to measure what the marks
/// cost.
#[allow(clippy::too_many_arguments)]
fn demo_live(
    cli: Res<Cli>,
    time: Res<Time>,
    level: Option<Res<CurrentLevel>>,
    marks: Res<Marks>,
    debris: Res<Debris>,
    diagnostics: Res<bevy::diagnostic::DiagnosticsStore>,
    camera: Query<(&GlobalTransform, &Projection), With<ViewCamera>>,
    mut feedback: ResMut<Feedback>,
    mut state: Local<(f32, f32, u64)>,
) {
    let live = match cli.demo_ui.as_deref() {
        Some("impacts-live") => true,
        Some("impacts-idle") => false,
        _ => return,
    };
    let (next_shot, next_log, shots) = &mut *state;
    let now = time.elapsed_secs();
    if live && let (Some(level), Ok((cam, Projection::Perspective(p)))) = (level, camera.single()) {
        let half_h = (p.fov * 0.5).tan() * DEMO_SPAN;
        let half_w = half_h * p.aspect_ratio;
        while *next_shot <= now {
            *next_shot = next_shot.max(now - 1.0) + 1.0 / LIVE_RATE_HZ;
            *shots += 1;
            let mut rng = SplitMix::from_parts(&[*shots, 77]);
            let local = Vec3::new(rng.next_signed() * half_w, rng.next_signed() * half_h, -1.0).normalize();
            let dir = cam.rotation() * local;
            let origin = cam.translation();
            if let Some((d, normal)) = level.world.raycast(origin, dir, 300.0) {
                feedback.impacts.push((origin + dir * d, normal));
            }
        }
    }
    if now >= *next_log {
        *next_log = now + LIVE_LOG_S;
        use bevy::diagnostic::FrameTimeDiagnosticsPlugin as Frames;
        let fps = diagnostics.get(&Frames::FPS).and_then(|d| d.smoothed()).unwrap_or(0.0);
        let ms = diagnostics.get(&Frames::FRAME_TIME).and_then(|d| d.smoothed()).unwrap_or(0.0);
        info!(
            "impacts demo: {} shots, {} marks, {} debris pieces, {fps:.0} fps, {ms:.2} ms",
            shots,
            marks.list.len(),
            debris.list.len()
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use vetf_sim::movement::collision::BrushKind;

    fn world() -> CollisionWorld {
        let mut w = CollisionWorld::default();
        // a wall 4 m long (x), 3 m tall, its south face at z = 0.5 facing +Z
        w.push(
            Brush::cuboid(Vec3::new(0.0, 0.0, 0.0), Vec3::new(4.0, 3.0, 0.5), BrushKind::Solid).with_look(Look::Wall),
        );
        // a second wall piece continuing it (same face plane) from x = 4 to 6
        w.push(
            Brush::cuboid(Vec3::new(4.0, 0.0, 0.0), Vec3::new(6.0, 3.0, 0.5), BrushKind::Solid).with_look(Look::Wall),
        );
        // a hedge and a player clip
        w.push(
            Brush::cuboid(Vec3::new(-6.0, 0.0, 3.0), Vec3::new(-4.0, 2.0, 4.0), BrushKind::Solid)
                .with_look(Look::Hedge),
        );
        w.push(Brush::cuboid(Vec3::new(10.0, 0.0, 0.0), Vec3::new(11.0, 3.0, 1.0), BrushKind::PlayerClip));
        w
    }

    /// A shot's hit through the real raycast (the trace stops a skin in front of the face).
    fn hit(w: &CollisionWorld, from: Vec3, to: Vec3) -> (Vec3, Vec3) {
        let dir = (to - from).normalize();
        let (d, n) = w.raycast(from, dir, 100.0).expect("a hit");
        (from + dir * d, n)
    }

    #[test]
    fn the_data_and_the_atlas_parse_and_agree() {
        let data = ImpactData::embedded();
        let atlas = AtlasData::embedded();
        for kind in SurfaceKind::ALL {
            let k = data.kinds.get(&kind).unwrap_or_else(|| panic!("{kind:?} has no tuning"));
            assert!(k.size_m > 0.02 && k.size_m < 0.5, "{kind:?}");
            let cells = &atlas.kinds[&kind];
            assert!(cells.len() >= 3, "{kind:?}: 3-4 variants");
            assert!(cells.iter().all(|&c| c < atlas.grid * atlas.grid));
        }
        let s = &atlas.sprites;
        assert!([s.puff, s.chip, s.spark].iter().all(|&c| c < atlas.grid * atlas.grid));
        assert!(data.max_marks[0] <= data.max_marks[1] && data.max_marks[0] > 0);
        assert!(data.parallax_layers[0] <= data.parallax_layers[1]);
        // a cell is 1/grid wide and the depth map's 1.0 is depth_ref half-widths of it
        let (uv0, w) = atlas.cell(atlas.grid + 1);
        assert_eq!((uv0, w), (Vec2::splat(1.0 / atlas.grid as f32), 1.0 / atlas.grid as f32));
        assert!((atlas.parallax_depth_scale() - atlas.depth_ref * w * 0.5).abs() < 1e-6);
    }

    /// Every visible look of the levels takes a mark, except the hedges and water; clips and invisible bounds never.
    #[test]
    fn looks_map_to_surface_kinds() {
        let data = ImpactData::embedded();
        assert_eq!(data.kind(Look::Wall), Some(SurfaceKind::Plaster));
        assert_eq!(data.kind(Look::CladSage), Some(SurfaceKind::Cladding));
        assert_eq!(data.kind(Look::Fence), Some(SurfaceKind::Wood));
        assert_eq!(data.kind(Look::Vehicle), Some(SurfaceKind::Metal));
        assert_eq!(data.kind(Look::Accent), Some(SurfaceKind::Metal));
        assert_eq!(data.kind(Look::Asphalt), Some(SurfaceKind::Pavement));
        assert_eq!(data.kind(Look::Ground), Some(SurfaceKind::Soil));
        assert_eq!(data.kind(Look::Gravel), Some(SurfaceKind::Soil));
        for none in [Look::Hedge, Look::Water, Look::Invisible] {
            assert_eq!(data.kind(none), None, "{none:?}");
        }
        // every look on Showhome is either mapped or one of those
        for b in &vetf_sim::maps::showhome().world.brushes {
            assert!(
                data.kind(b.look).is_some() || matches!(b.look, Look::Hedge | Look::Water | Look::Invisible),
                "{:?}",
                b.look
            );
        }
    }

    #[test]
    fn a_shot_finds_the_face_it_hit() {
        let w = world();
        let (p, n) = hit(&w, Vec3::new(2.0, 1.5, 5.0), Vec3::new(2.0, 1.5, 0.0));
        assert_eq!(n, Vec3::Z);
        let (b, k) = find_face(&w, p, n).unwrap();
        assert_eq!((b, w.brushes[b].planes[k].normal), (0, Vec3::Z));
        // the top of the wall
        let (p, n) = hit(&w, Vec3::new(5.0, 6.0, 0.25), Vec3::new(5.0, 0.0, 0.25));
        assert_eq!(find_face(&w, p, n).map(|(b, _)| b), Some(1));
        // the hedge is found (its look then takes no mark), thin air is not
        let (p, n) = hit(&w, Vec3::new(-5.0, 1.0, 8.0), Vec3::new(-5.0, 1.0, 3.5));
        assert_eq!(find_face(&w, p, n).map(|(b, _)| w.brushes[b].look), Some(Look::Hedge));
        assert_eq!(find_face(&w, Vec3::new(2.0, 1.5, 2.0), Vec3::Z), None);
    }

    fn outline(w: &CollisionWorld, p: Vec3, n: Vec3, angle: f32, half: f32) -> Vec<(Vec3, Vec2)> {
        let (b, k) = find_face(w, p, n).unwrap();
        mark_outline(w, b, k, p, Frame::free(n, angle), half, 0.003, Vec2::new(0.5, 0.25), 0.25)
    }

    /// In the middle of a face a mark is its whole square: four corners lifted off the face, UVs on its cell.
    #[test]
    fn a_mark_is_a_square_on_its_cell() {
        let w = world();
        let (p, n) = hit(&w, Vec3::new(2.0, 1.5, 5.0), Vec3::new(2.0, 1.5, 0.0));
        let o = outline(&w, p, n, 0.7, 0.06);
        assert_eq!(o.len(), 4);
        for (v, uv) in &o {
            assert!((v.z - 0.503).abs() < 1e-5, "lifted 3 mm: {v}");
            assert!((v.xy() - Vec2::new(2.0, 1.5)).length() < 0.06 * 1.42);
            assert!(uv.x >= 0.5 - 1e-5 && uv.x <= 0.75 + 1e-5 && uv.y >= 0.25 - 1e-5 && uv.y <= 0.5 + 1e-5, "{uv}");
        }
        assert!((outline_area(&o, n) - 0.12 * 0.12).abs() < 1e-5);
        // the frame: b = n x t, so the image's top is the mark's up
        let f = Frame::free(n, 0.7);
        assert!(f.b.abs_diff_eq(f.n.cross(f.t), 1e-6) && f.t.dot(n).abs() < 1e-6);
    }

    /// At the top edge of a wall a mark is cut along the edge, never hanging in the air above it; its UVs are
    /// cut with it (the cell's part that stays).
    #[test]
    fn a_mark_at_an_edge_is_clipped_to_the_face() {
        let w = world();
        let (p, n) = hit(&w, Vec3::new(1.0, 2.97, 5.0), Vec3::new(1.0, 2.97, 0.0));
        let o = outline(&w, p, n, 0.3, 0.06);
        assert!(o.len() >= 3);
        assert!(o.iter().all(|(v, _)| v.y <= 3.0 + 1e-4), "{o:?}");
        let area = outline_area(&o, n);
        assert!(area > 0.0 && area < 0.12 * 0.12 * 0.8, "{area}");
        // at the wall's west end (x = 0) too
        let (p, n) = hit(&w, Vec3::new(0.02, 1.0, 5.0), Vec3::new(0.02, 1.0, 0.0));
        assert!(outline(&w, p, n, 0.0, 0.06).iter().all(|(v, _)| v.x >= -1e-4));
        // the top face of the wall is only 0.5 m deep: a mark there is cut on both sides
        let (p, n) = hit(&w, Vec3::new(1.0, 5.0, 0.03), Vec3::new(1.0, 0.0, 0.03));
        assert!(outline(&w, p, n, 0.4, 0.06).iter().all(|(v, _)| v.z >= -1e-4 && v.z <= 0.5 + 1e-4));
    }

    /// Where the next wall piece goes on in the same plane the mark is not cut at the seam.
    #[test]
    fn a_mark_crosses_a_seam_between_coplanar_faces() {
        let w = world();
        let (p, n) = hit(&w, Vec3::new(3.98, 1.5, 5.0), Vec3::new(3.98, 1.5, 0.0));
        let o = outline(&w, p, n, 0.0, 0.06);
        assert_eq!(o.len(), 4, "{o:?}");
        assert!(o.iter().any(|(v, _)| v.x > 4.0));
    }

    #[test]
    fn wood_runs_along_the_grain() {
        // a wall: up along world up (or down), a little either way
        let f = Frame::grain(Vec3::X, false, 0.0);
        assert!(f.b.abs_diff_eq(Vec3::Y, 1e-6) && f.b.abs_diff_eq(f.n.cross(f.t), 1e-6));
        let f = Frame::grain(Vec3::X, true, 0.1);
        assert!(f.b.dot(Vec3::NEG_Y) > 0.99 && f.b.abs_diff_eq(f.n.cross(f.t), 1e-6));
        // a floor: along the boards (world Z)
        let f = Frame::grain(Vec3::Y, false, 0.0);
        assert!(f.b.dot(Vec3::Z).abs() > 0.999 && f.b.abs_diff_eq(f.n.cross(f.t), 1e-6));
    }

    #[test]
    fn marks_take_their_surface_and_the_oldest_go() {
        let w = world();
        let data = ImpactData::embedded();
        let atlas = AtlasData::embedded();
        let mut marks = Marks::default();
        let (p, n) = hit(&w, Vec3::new(2.0, 1.5, 5.0), Vec3::new(2.0, 1.5, 0.0));
        let m = marks.add(&w, &data, &atlas, true, p, n, 3, None).expect("a mark on the wall").clone();
        assert_eq!(m.kind, SurfaceKind::Plaster);
        assert!(!m.paint, "concrete does not bend: no paint layer");
        assert!(m.tint.to_f32_array()[0] > 0.5, "tinted with the wall's cream");
        // the kinds that bend or lift the surface have one
        for kind in [SurfaceKind::Cladding, SurfaceKind::Wood, SurfaceKind::Metal] {
            assert!(atlas.paint.contains(&kind), "{kind:?}");
        }
        let cells = &atlas.kinds[&SurfaceKind::Plaster];
        let mut seen = Vec::new();
        for i in 0..20 {
            let q = p + Vec3::X * (i as f32 * 0.01 - 0.1);
            let m = marks.add(&w, &data, &atlas, true, q, n, 3, None).unwrap();
            let cell = cells.iter().copied().find(|&c| {
                let (c0, cw) = atlas.cell(c);
                m.verts.iter().all(|(_, uv)| {
                    uv.x >= c0.x - 1e-5 && uv.x <= c0.x + cw + 1e-5 && uv.y >= c0.y - 1e-5 && uv.y <= c0.y + cw + 1e-5
                })
            });
            seen.push(cell.expect("on one of plaster's cells"));
        }
        assert!(seen.windows(2).all(|p| p[0] != p[1]), "never the same variant twice in a row: {seen:?}");
        assert!(cells.iter().all(|c| seen.contains(c)), "every variant comes up");
        assert_eq!(marks.list.len(), 3, "at most max");
        // the hedge takes none
        let (p, n) = hit(&w, Vec3::new(-5.0, 1.0, 8.0), Vec3::new(-5.0, 1.0, 3.5));
        assert!(marks.add(&w, &data, &atlas, true, p, n, 3, None).is_none());
    }

    #[test]
    fn marks_fade_out_and_expire() {
        assert_eq!(mark_alpha(0.0, 30.0, 1.0), 1.0);
        assert_eq!(mark_alpha(29.0, 30.0, 1.0), 1.0);
        assert!((mark_alpha(29.5, 30.0, 1.0) - 0.5).abs() < 1e-6);
        let w = world();
        let (data, atlas) = (ImpactData::embedded(), AtlasData::embedded());
        let mut marks = Marks::default();
        let (p, n) = hit(&w, Vec3::new(2.0, 1.5, 5.0), Vec3::new(2.0, 1.5, 0.0));
        marks.add(&w, &data, &atlas, true, p, n, 10, None);
        marks.dirty = false;
        assert!(!marks.age(10.0, 30.0, 1.0), "nothing to redraw mid-life");
        assert!(marks.age(19.5, 30.0, 1.0), "fading: redraw");
        marks.age(1.0, 30.0, 1.0);
        assert!(marks.list.is_empty());
        // the mesh carries the fade and, on the paint layer, the tint
        marks.add(&w, &data, &atlas, true, p, n, 10, None);
        let mesh = marks_mesh(marks.list.iter(), true, 30.0, 1.0).unwrap();
        assert_eq!(mesh.count_vertices(), 4);
        assert!(marks_mesh(std::iter::empty(), false, 30.0, 1.0).is_none());
    }

    /// Far mips of the albedo get darker and more opaque, step by step; the near ones stay as they are.
    #[test]
    fn far_mips_darken_and_thicken() {
        let far = FarLook { from_mip: 1, darken_per_mip: 0.3, darken_max: 0.5, alpha_per_mip: 0.5 };
        // 4x4 grey at half alpha: levels 4x4, 2x2, 1x1
        let (mut chain, levels) = crate::map_materials::mip_chain([128u8, 128, 128, 100].repeat(16), 4, 4, true);
        assert_eq!(levels, 3);
        let before = chain.clone();
        far_mips(&mut chain, 4, 4, levels, &far, 1, &[]);
        assert_eq!(chain[..64], before[..64], "level 0 untouched");
        let (l1, l2) = (&chain[64..68], &chain[80..84]);
        assert!(l1[0] < before[64] && l2[0] < l1[0], "darker step by step: {l1:?} {l2:?}");
        assert_eq!((l1[3], l2[3]), (150, 200), "more opaque");
        let lin = |b: u8| Color::srgb_u8(b, 0, 0).to_linear().red;
        assert!((lin(l2[0]) / lin(before[80]) - 0.5).abs() < 0.02, "never darker than darken_max");
        // the data file's values are sane
        let f = ImpactData::embedded().far;
        assert!(f.from_mip >= 2 && f.darken_max <= 0.8 && f.alpha_per_mip >= 0.0);
    }

    /// The debris sprites share the atlas with the marks: their cells keep every mip as it is (a puff at fighting
    /// range must stay pale dust, a spark bright), while the marks' cells darken.
    #[test]
    fn far_mips_leave_the_sprite_cells_alone() {
        let far = FarLook { from_mip: 1, darken_per_mip: 0.3, darken_max: 0.5, alpha_per_mip: 0.5 };
        // a 3x3 grid of 4 px cells (12x12), the middle cell a sprite: levels 12, 6, 3 (a cell 1 px), 1
        let (mut chain, levels) = crate::map_materials::mip_chain([200u8, 200, 200, 100].repeat(144), 12, 12, true);
        assert_eq!(levels, 4);
        let before = chain.clone();
        far_mips(&mut chain, 12, 12, levels, &far, 3, &[4]);
        // level 1 (6x6, cells 2 px) starts after level 0's 576 bytes
        let at = |x: usize, y: usize| 576 + (y * 6 + x) * 4;
        assert_eq!(chain[at(2, 2)..at(2, 2) + 4], before[at(2, 2)..at(2, 2) + 4], "the sprite cell is untouched");
        assert_eq!(chain[at(3, 3)..at(3, 3) + 4], before[at(3, 3)..at(3, 3) + 4], "all of it");
        assert!(
            chain[at(0, 0)] < before[at(0, 0)] && chain[at(0, 0) + 3] > before[at(0, 0) + 3],
            "a mark cell darkens"
        );
        // level 2 (3x3, a pixel per cell): the middle pixel is the sprite's
        let at2 = 576 + 144 + 4 * 4;
        assert_eq!(chain[at2..at2 + 4], before[at2..at2 + 4]);
        assert!(chain[576 + 144] < before[576 + 144]);
        // level 3 (1x1): cells under a pixel, left alone
        assert_eq!(chain[chain.len() - 4..], before[before.len() - 4..]);
        // the real atlas's sprite cells are on its grid
        let atlas = AtlasData::embedded();
        let s = &atlas.sprites;
        assert!([s.puff, s.chip, s.spark].iter().all(|&c| c < atlas.grid * atlas.grid));
    }

    #[test]
    fn debris_flies_and_settles() {
        let data = ImpactData::embedded();
        let mut debris = Debris::default();
        debris.throw(&data, SurfaceKind::Metal, Vec3::ZERO, Vec3::Z);
        let k = &data.kinds[&SurfaceKind::Metal];
        assert_eq!(debris.list.len(), (k.puffs + k.chips + k.sparks) as usize);
        assert!(
            debris.list.iter().filter(|p| p.kind == PieceKind::Spark).all(|p| p.vel.dot(Vec3::Z) > 0.0),
            "off the face"
        );
        for _ in 0..100 {
            debris.step(0.01, &data.debris);
        }
        assert!(debris.list.is_empty(), "all spent within a second");
        for _ in 0..200 {
            debris.throw(&data, SurfaceKind::Soil, Vec3::ZERO, Vec3::Y);
        }
        assert_eq!(debris.list.len(), data.debris.max);
    }
}
