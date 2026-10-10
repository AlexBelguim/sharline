//! What smoke grenades and molotovs look like (item 10b; the game side is `throwables.rs`).
//!
//! The user asked for smoke that uses "the same system like the foliage": so a cloud is built the way a hedge is
//! (`foliage.rs`), a cluster of soft painted cards filling the volume, merged into ONE mesh per cloud and lit with
//! light wrap, and a fire is the same with flame and ember cards plus a little light. The cards and their motion
//! live in `assets/shaders/throwables.wgsl` (a StandardMaterial extension like the hedges'):
//!
//! - **Smoke** puffs face the camera, grow with the cloud, drift and roll slowly, and thin out with it. They are
//!   lit per corner (wrap, light through the smoke toward the sun, the ambient), with a sun visibility per puff
//!   baked here against the level, so a cloud in a house's shadow is in shadow. Puffs right at the camera vanish,
//!   so standing in a cloud fills the screen with the puffs ahead and the GPU work stays bounded (a fixed number
//!   of cards per cloud, no per-fragment lighting). The puffs are sorted back to front when the view of the cloud
//!   turns.
//! - **Bullet tunnels**: every shot this client sees through a cloud is kept in the cloud's small ring of recent
//!   lines (`vetf_sim::throwable::Tunnels`); the fragment stage fades the puffs near those lines, so a see-through
//!   tube opens along the bullet's path and fills back in.
//! - **Fire**: flame cards stand up from the burning ground and flicker, embers rise, additive and unlit; a point
//!   light (no shadows) flickers over it. Flames shrink away as it burns out or when smoke puts it out.
//! - **Grenades** in flight: a tumbling canister or bottle (the molotov's rag glows).
//!
//! The card atlas (puffs, flames, embers) is painted procedurally at start-up ([`build_atlas`]): soft lumpy puffs
//! with a lit top, flame tongues and ember dots. Every look number is in `assets/data/throwable_fx.ron`.

use super::ViewCamera;
use crate::AppState;
use crate::config::{CurrentLevel, Data};
use crate::settings::Settings;
use crate::throwables::ThrowView;
use bevy::asset::RenderAssetUsages;
use bevy::camera::Exposure;
use bevy::camera::visibility::NoFrustumCulling;
use bevy::image::{ImageSampler, ImageSamplerDescriptor};
use bevy::light::{NotShadowCaster, NotShadowReceiver};
use bevy::mesh::{Indices, PrimitiveTopology};
use bevy::pbr::{ExtendedMaterial, MaterialExtension, MaterialPlugin};
use bevy::prelude::*;
use bevy::render::render_resource::{AsBindGroup, Extent3d, ShaderType, TextureDimension, TextureFormat};
use bevy::shader::ShaderRef;
use lightyear::prelude::Controlled;
use serde::Deserialize;
use std::f32::consts::{PI, TAU};
use vetf_net::PlayerId;
use vetf_sim::level::Team;
use vetf_sim::rng::SplitMix;
use vetf_sim::throwable::{MolotovSpec, SmokeSpec, TUNNELS, ThrowId, ThrowKind};

pub struct ThrowFxPlugin;

impl Plugin for ThrowFxPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins(MaterialPlugin::<ThrowFxMaterial>::default())
            .insert_resource(ThrowFxData::load())
            .add_systems(Startup, setup_assets)
            .add_systems(
                Update,
                (sync_clouds, sync_fires, sync_grenades, sync_held_grenade)
                    .after(crate::throwables::ThrowViewSystems)
                    .run_if(in_state(AppState::InGame)),
            );
    }
}

const SHADER: &str = "shaders/throwables.wgsl";
/// The atlas: 4 x 4 cells of CELL px. Cells 0-7 smoke puffs, 8-13 flames, 14-15 embers.
const CELLS: u32 = 4;
const CELL: usize = 128;
const PUFF_CELLS: std::ops::Range<u32> = 0..8;
const FLAME_CELLS: std::ops::Range<u32> = 8..14;
const EMBER_CELLS: std::ops::Range<u32> = 14..16;
/// The preset whose card count the data's card sizes are for (HIGH).
const SIZE_PRESET: usize = 2;

// ---------------------------------------------------------------------------------------------- data

/// `game/assets/data/throwable_fx.ron`.
#[derive(Resource, Debug, Clone, PartialEq, Deserialize)]
pub struct ThrowFxData {
    pub smoke: SmokeLook,
    pub fire: FireLook,
    pub grenade: GrenadeLook,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct SmokeLook {
    pub cards: [usize; 4],
    pub card_size: (f32, f32),
    pub fill: f32,
    pub min_card_scale: f32,
    pub tint: (f32, f32, f32),
    pub value_jitter: f32,
    pub ao_bottom: f32,
    pub ao_core: f32,
    pub wrap: f32,
    pub translucency: f32,
    pub translucency_power: f32,
    pub ambient: f32,
    pub sun_shade: f32,
    pub opacity: f32,
    pub drift_m: f32,
    pub swirl: f32,
    pub spin: f32,
    pub fade_spread: f32,
    pub near_fade: (f32, f32),
    pub soft_depth_m: f32,
    pub resort_deg: f32,
    pub tunnel: TunnelLook,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct TunnelLook {
    pub radius_m: f32,
    pub soft_m: f32,
    pub life_s: f32,
    pub refill_s: f32,
    pub reach: f32,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct FireLook {
    pub flames: [usize; 4],
    pub embers: [usize; 4],
    pub flame_size: (f32, f32),
    pub flame_aspect: f32,
    pub flicker: f32,
    pub flicker_hz: (f32, f32),
    pub tint: (f32, f32, f32),
    pub glow: f32,
    pub ember_tint: (f32, f32, f32),
    pub ember_glow: f32,
    pub ember_size: f32,
    pub ember_rise_m: f32,
    pub ember_rise_s: f32,
    pub fade_s: f32,
    pub light_color: (f32, f32, f32),
    pub light_lumens: f32,
    pub light_range_m: f32,
    pub light_flicker: f32,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct GrenadeLook {
    pub smoke_color: (f32, f32, f32),
    pub molotov_color: (f32, f32, f32),
    pub held_scale: f32,
    pub held_charge_offset: (f32, f32, f32),
    pub held_tilt_deg: f32,
    pub rag_glow: f32,
    pub tumble_rps: f32,
}

const EMBEDDED: &str = include_str!("../../../../assets/data/throwable_fx.ron");

impl ThrowFxData {
    pub fn embedded() -> Self {
        ron::from_str(EMBEDDED).expect("game/assets/data/throwable_fx.ron is valid")
    }

    /// From the data folder (tunable without a rebuild), else the built-in copy.
    pub fn load() -> Self {
        let path = crate::config::assets_root().join("data").join("throwable_fx.ron");
        match std::fs::read_to_string(&path).map(|t| ron::from_str::<ThrowFxData>(&t)) {
            Ok(Ok(d)) => d,
            Ok(Err(e)) => {
                error!("{} is invalid ({e}); using the built-in copy", path.display());
                Self::embedded()
            }
            Err(_) => Self::embedded(),
        }
    }
}

fn rgb(c: (f32, f32, f32)) -> Vec3 {
    Vec3::new(c.0, c.1, c.2)
}

// ---------------------------------------------------------------------------------------------- material

pub type ThrowFxMaterial = ExtendedMaterial<StandardMaterial, ThrowFxExt>;

/// The shader's `ThrowFx` uniform (see throwables.wgsl for each lane).
#[derive(Clone, Copy, Debug, Default, PartialEq, ShaderType, Reflect)]
pub struct FxUniform {
    pub state: Vec4,
    pub motion: Vec4,
    pub shape: Vec4,
    pub tint: Vec4,
    pub tint2: Vec4,
    pub sun_dir: Vec4,
    pub sun: Vec4,
    pub ambient: Vec4,
    pub fade: Vec4,
    pub tunnel: Vec4,
    pub tunnel_a: [Vec4; TUNNELS],
    pub tunnel_b: [Vec4; TUNNELS],
}

#[derive(Asset, AsBindGroup, Reflect, Debug, Clone, Default)]
pub struct ThrowFxExt {
    #[uniform(100)]
    pub params: FxUniform,
    #[texture(101)]
    #[sampler(102)]
    pub atlas: Handle<Image>,
}

impl MaterialExtension for ThrowFxExt {
    fn vertex_shader() -> ShaderRef {
        SHADER.into()
    }
    fn fragment_shader() -> ShaderRef {
        SHADER.into()
    }
}

/// The light the clouds are lit with (the shader cannot read the scene's lights in its vertex stage).
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct SceneLight {
    /// Toward the sun (unit), if there is one.
    pub to_sun: Option<Vec3>,
    /// The sun's diffuse light over PI, exposed.
    pub sun: Vec3,
    /// The ambient light, exposed.
    pub ambient: Vec3,
}

/// A cloud's uniform at `age_s`: its size and density now, its look and light, and its live bullet tunnels.
pub fn smoke_uniform(
    look: &SmokeLook,
    growth: f32,
    density: f32,
    age_s: f32,
    light: &SceneLight,
    tunnels: &[(Vec3, Vec3, f32)],
) -> FxUniform {
    let mut u = FxUniform {
        state: Vec4::new(0.0, growth, density, age_s),
        motion: Vec4::new(look.min_card_scale, look.drift_m, look.swirl, look.spin),
        shape: Vec4::new(look.wrap, look.translucency, look.translucency_power, look.fade_spread),
        tint: rgb(look.tint).extend(look.opacity),
        sun_dir: light.to_sun.map_or(Vec4::new(0.0, 1.0, 0.0, 0.0), |d| d.extend(1.0)),
        sun: light.sun.extend(0.0),
        ambient: (light.ambient * look.ambient).extend(0.0),
        fade: Vec4::new(look.near_fade.0, look.near_fade.1, look.soft_depth_m, 0.0),
        tunnel: Vec4::new(look.tunnel.radius_m, look.tunnel.soft_m, 0.0, 0.0),
        ..default()
    };
    let n = tunnels.len().min(TUNNELS);
    for (i, (a, b, open)) in tunnels.iter().take(n).enumerate() {
        u.tunnel_a[i] = a.extend(*open);
        u.tunnel_b[i] = b.extend(0.0);
    }
    u.fade.w = n as f32;
    u
}

/// Stable owner-team colours. FFA uses the own accent and neutral colour for other owners.
pub fn smoke_team_tint(
    team: Option<Team>,
    owner: u64,
    viewer: Option<u64>,
    settings: Option<&Settings>,
    neutral: Vec3,
) -> Vec3 {
    let (a, b) = settings.map_or((crate::ui_kit::ALLY, crate::ui_kit::ENEMY), Settings::team_colors);
    let color = match team {
        Some(Team::A) => a,
        Some(Team::B) => b,
        None if viewer == Some(owner) => a,
        None => return neutral,
    };
    Vec3::from_slice(&color.to_linear().to_f32_array()[..3])
}

/// A fire's uniform: spread (0..1), burn-out alpha, age.
pub fn fire_uniform(look: &FireLook, spread: f32, alpha: f32, age_s: f32) -> FxUniform {
    FxUniform {
        state: Vec4::new(1.0, spread, alpha, age_s),
        motion: Vec4::new(look.flicker, look.flicker_hz.0, look.flicker_hz.1, look.ember_size),
        shape: Vec4::new(look.ember_rise_m, look.ember_rise_s, look.glow, look.ember_glow),
        tint: rgb(look.tint).extend(1.0),
        tint2: rgb(look.ember_tint).extend(1.0),
        ..default()
    }
}

// ---------------------------------------------------------------------------------------------- the atlas

fn hash(x: i32, y: i32, seed: u32) -> f32 {
    let mut h = SplitMix::from_parts(&[x as u32 as u64, y as u32 as u64, seed as u64]);
    h.next_f32()
}

/// Smooth value noise in 0..1.
fn value_noise(p: Vec2, seed: u32) -> f32 {
    let i = p.floor();
    let f = p - i;
    let u = f * f * (Vec2::splat(3.0) - 2.0 * f);
    let (x, y) = (i.x as i32, i.y as i32);
    let a = hash(x, y, seed);
    let b = hash(x + 1, y, seed);
    let c = hash(x, y + 1, seed);
    let d = hash(x + 1, y + 1, seed);
    let top = a + (b - a) * u.x;
    let bottom = c + (d - c) * u.x;
    top + (bottom - top) * u.y
}

fn fbm(p: Vec2, seed: u32) -> f32 {
    let (mut sum, mut amp, mut freq, mut norm) = (0.0, 0.5, 1.0, 0.0);
    for o in 0..4 {
        sum += value_noise(p * freq, seed.wrapping_add(o * 101)) * amp;
        norm += amp;
        amp *= 0.5;
        freq *= 2.0;
    }
    sum / norm
}

fn smoothstep(e0: f32, e1: f32, x: f32) -> f32 {
    let t = ((x - e0) / (e1 - e0)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

/// One texel of a smoke puff at `p` (0..1 in its cell, y down): a lumpy cluster of soft blobs with broken edges,
/// lighter toward its top in a few soft painted steps. (rgb value, alpha)
fn puff_texel(p: Vec2, blobs: &[(Vec2, f32)], seed: u32) -> (f32, f32) {
    let field: f32 = blobs.iter().map(|(c, r)| (-(p - *c).length_squared() / (r * r)).exp()).sum();
    let n = fbm(p * 5.0, seed);
    let d = field + (n - 0.5) * 0.7;
    let edge = (p.x.min(1.0 - p.x).min(p.y).min(1.0 - p.y) / 0.08).clamp(0.0, 1.0);
    let alpha = smoothstep(0.3, 0.95, d) * edge;
    // Lit from above: brighter at the top and where the puff is thick; posterised a little, like a painting.
    let lit = (field * 0.45 + (1.0 - p.y) * 0.55 + (n - 0.5) * 0.25).clamp(0.0, 1.0);
    let steps = (lit * 4.0).round() / 4.0;
    let value = 0.68 + 0.32 * (lit * 0.5 + steps * 0.5);
    (value, alpha)
}

/// One texel of a flame tongue at `p` (y down): a flickering teardrop, hottest at its core and foot. (heat, alpha)
fn flame_texel(p: Vec2, seed: u32) -> (f32, f32) {
    let x = (p.x - 0.5) * 2.0;
    let y = 1.0 - p.y;
    let warp = (fbm(Vec2::new(y * 3.0, seed as f32 * 0.37), seed) - 0.5) * 0.7 * y;
    let width = 0.85 * (1.0 - y).max(0.0).powf(0.75) * (0.55 + 0.45 * smoothstep(0.0, 0.25, y));
    let inside = 1.0 - (x - warp).abs() / width.max(1e-3);
    let n = fbm(Vec2::new(p.x * 6.0, p.y * 4.0 + seed as f32), seed.wrapping_add(7));
    let alpha = smoothstep(0.0, 0.4, inside + (n - 0.5) * 0.35) * smoothstep(1.0, 0.82, y) * smoothstep(0.0, 0.06, y);
    let heat = (inside * 1.1 - y * 0.55 + 0.25).clamp(0.0, 1.0);
    (heat, alpha)
}

/// The card atlas: `CELLS` x `CELLS` cells of `CELL` px, RGBA8 (linear). Puff cells carry their painted value in
/// rgb, flame and ember cells their heat.
pub fn build_atlas() -> (Vec<u8>, usize) {
    let size = CELL * CELLS as usize;
    let mut out = vec![0u8; size * size * 4];
    for cell in 0..CELLS * CELLS {
        let (cx, cy) = ((cell % CELLS) as usize * CELL, (cell / CELLS) as usize * CELL);
        let mut rng = SplitMix::from_parts(&[cell as u64, 0x5300_4b45]);
        let blobs: Vec<(Vec2, f32)> = (0..7)
            .map(|k| {
                let a = rng.next_f32() * TAU;
                let r = rng.next_f32().sqrt() * if k == 0 { 0.0 } else { 0.2 };
                (Vec2::new(0.5 + a.cos() * r, 0.52 + a.sin() * r * 0.8), 0.13 + rng.next_f32() * 0.1)
            })
            .collect();
        for y in 0..CELL {
            for x in 0..CELL {
                let p = Vec2::new((x as f32 + 0.5) / CELL as f32, (y as f32 + 0.5) / CELL as f32);
                let (v, a) = if PUFF_CELLS.contains(&cell) {
                    puff_texel(p, &blobs, cell)
                } else if FLAME_CELLS.contains(&cell) {
                    flame_texel(p, cell)
                } else {
                    let d = (p - Vec2::splat(0.5)).length() / 0.5;
                    let a = (1.0 - d).clamp(0.0, 1.0).powi(2);
                    (1.0, a)
                };
                let i = ((cy + y) * size + cx + x) * 4;
                let byte = |f: f32| (f.clamp(0.0, 1.0) * 255.0).round() as u8;
                out[i..i + 4].copy_from_slice(&[byte(v), byte(v), byte(v), byte(a)]);
            }
        }
    }
    (out, size)
}

/// The UV rectangle of atlas cell `i` (top-left, size), inset half a texel's worth so mips do not bleed.
fn cell_uv(i: u32) -> (Vec2, Vec2) {
    let size = Vec2::splat(1.0 / CELLS as f32);
    let corner = Vec2::new((i % CELLS) as f32, (i / CELLS) as f32) * size;
    let inset = size * 0.01;
    (corner + inset, size - inset * 2.0)
}

// ---------------------------------------------------------------------------------------------- the cards

/// Raw vertex arrays of a card mesh, and each card's centre.
#[derive(Default, Debug, Clone)]
pub struct Cards {
    pub centres: Vec<Vec3>,
    pub positions: Vec<[f32; 3]>,
    pub normals: Vec<[f32; 3]>,
    pub uv0: Vec<[f32; 2]>,
    pub uv1: Vec<[f32; 2]>,
    pub colors: Vec<[f32; 4]>,
}

impl Cards {
    /// How many cards.
    pub fn count(&self) -> usize {
        self.centres.len()
    }

    /// Four corners (bottom-left, bottom-right, top-right, top-left as `offsets`) of one card.
    fn push(&mut self, centre: Vec3, normal: Vec3, cell: u32, flip: bool, offsets: [Vec2; 4], color: [f32; 4]) {
        let (uv0, size) = cell_uv(cell);
        let (l, r) = if flip { (uv0.x + size.x, uv0.x) } else { (uv0.x, uv0.x + size.x) };
        let (top, bottom) = (uv0.y, uv0.y + size.y);
        let uvs = [[l, bottom], [r, bottom], [r, top], [l, top]];
        self.centres.push(centre);
        for (o, uv) in offsets.iter().zip(uvs) {
            self.positions.push(centre.to_array());
            self.normals.push(normal.to_array());
            self.uv0.push(uv);
            self.uv1.push(o.to_array());
            self.colors.push(color);
        }
    }

    fn into_mesh(self, indices: Vec<u32>) -> Mesh {
        Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::RENDER_WORLD | RenderAssetUsages::MAIN_WORLD)
            .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, self.positions)
            .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, self.normals)
            .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, self.uv0)
            .with_inserted_attribute(Mesh::ATTRIBUTE_UV_1, self.uv1)
            .with_inserted_attribute(Mesh::ATTRIBUTE_COLOR, self.colors)
            .with_inserted_indices(Indices::U32(indices))
    }
}

/// Card indices in `order` (two triangles per card).
pub fn card_indices(order: impl IntoIterator<Item = usize>) -> Vec<u32> {
    order
        .into_iter()
        .flat_map(|c| {
            let b = c as u32 * 4;
            [b, b + 1, b + 2, b, b + 2, b + 3]
        })
        .collect()
}

/// The cards from the farthest to the nearest to `eye` (mesh space): the blending order.
pub fn back_to_front(centres: &[Vec3], eye: Vec3) -> Vec<usize> {
    let mut order: Vec<usize> = (0..centres.len()).collect();
    order.sort_by(|a, b| centres[*b].distance_squared(eye).total_cmp(&centres[*a].distance_squared(eye)));
    order
}

/// The puffs of one cloud at full size, around its centre: `look.cards[q]` puffs filling the ellipsoid (none
/// below the ground it popped on), each with its outward normal, a shade (darker toward the bottom and the core,
/// jittered) and its sun visibility (`sunlit(p)`, p in mesh space).
pub fn smoke_cards(look: &SmokeLook, sim: &SmokeSpec, q: usize, seed: u64, sunlit: impl Fn(Vec3) -> bool) -> Cards {
    let n = look.cards[q.min(3)].max(1);
    let scale = (look.cards[SIZE_PRESET] as f32 / n as f32).sqrt();
    let radii = Vec3::new(sim.radius_m, sim.height_m, sim.radius_m);
    let mut rng = SplitMix::from_parts(&[seed, 0x534d_4f4b]);
    let mut out = Cards::default();
    for _ in 0..n {
        let r: [f32; 8] = std::array::from_fn(|_| rng.next_f32());
        // A point in the unit ball, spread evenly through the volume.
        let dir = {
            let z = r[0] * 2.0 - 1.0;
            let a = r[1] * TAU;
            let s = (1.0 - z * z).max(0.0).sqrt();
            Vec3::new(s * a.cos(), z, s * a.sin())
        };
        let unit = dir * r[2].cbrt() * look.fill;
        let size = (look.card_size.0 + (look.card_size.1 - look.card_size.0) * r[3]) * scale;
        let mut p = unit * radii;
        // Never below the ground it popped on.
        p.y = p.y.max(-sim.lift_m + size * 0.3);
        let normal = (p / (radii * radii)).try_normalize().unwrap_or(Vec3::Y);
        let height = (p.y + sim.lift_m) / (sim.lift_m + sim.height_m);
        let core = (p / radii).length();
        let shade = (look.ao_bottom + (1.0 - look.ao_bottom) * smoothstep(0.0, 0.85, height))
            * (look.ao_core + (1.0 - look.ao_core) * smoothstep(0.2, 0.9, core))
            * (1.0 + (r[4] * 2.0 - 1.0) * look.value_jitter);
        let sun = if sunlit(p) { 1.0 } else { look.sun_shade };
        let cell = PUFF_CELLS.start + (r[5] * PUFF_CELLS.len() as f32) as u32 % PUFF_CELLS.len() as u32;
        let h = size * 0.5;
        let corners = [Vec2::new(-h, -h), Vec2::new(h, -h), Vec2::new(h, h), Vec2::new(-h, h)];
        out.push(p, normal, cell, r[6] < 0.5, corners, [sun, shade, 0.0, r[7]]);
    }
    out
}

/// The flames and embers of one fire at full spread, around its ground point: flames stand on the disc (their
/// foot at the ground, hotter toward the middle), embers start among them.
pub fn fire_cards(look: &FireLook, sim: &MolotovSpec, q: usize, seed: u64) -> Cards {
    let flames = look.flames[q.min(3)].max(1);
    let scale = (look.flames[SIZE_PRESET] as f32 / flames as f32).sqrt();
    let mut rng = SplitMix::from_parts(&[seed, 0x4649_5245]);
    let mut out = Cards::default();
    for _ in 0..flames {
        let r: [f32; 6] = std::array::from_fn(|_| rng.next_f32());
        let d = r[0].sqrt() * sim.radius_m * 0.92;
        let a = r[1] * TAU;
        let p = Vec3::new(a.cos() * d, 0.0, a.sin() * d);
        let w = (look.flame_size.0 + (look.flame_size.1 - look.flame_size.0) * r[2]) * scale;
        let h = w * look.flame_aspect * (1.0 - 0.35 * d / sim.radius_m);
        let corners =
            [Vec2::new(-w * 0.5, 0.0), Vec2::new(w * 0.5, 0.0), Vec2::new(w * 0.5, h), Vec2::new(-w * 0.5, h)];
        let heat = 1.0 - 0.6 * d / sim.radius_m;
        let cell = FLAME_CELLS.start + (r[3] * FLAME_CELLS.len() as f32) as u32 % FLAME_CELLS.len() as u32;
        out.push(p, Vec3::Y, cell, r[4] < 0.5, corners, [heat, 1.0, 0.0, r[5]]);
    }
    for _ in 0..look.embers[q.min(3)] {
        let r: [f32; 4] = std::array::from_fn(|_| rng.next_f32());
        let d = r[0].sqrt() * sim.radius_m * 0.8;
        let a = r[1] * TAU;
        let p = Vec3::new(a.cos() * d, 0.1, a.sin() * d);
        let corners = [Vec2::new(-0.5, -0.5), Vec2::new(0.5, -0.5), Vec2::new(0.5, 0.5), Vec2::new(-0.5, 0.5)];
        let cell = EMBER_CELLS.start + (r[2] * 2.0) as u32 % 2;
        out.push(p, Vec3::Y, cell, false, corners, [1.0, 1.0, 1.0, r[3]]);
    }
    out
}

// ---------------------------------------------------------------------------------------------- systems

/// The atlas and the grenades' meshes and materials.
#[derive(Resource)]
struct FxAssets {
    atlas: Handle<Image>,
    can: Handle<Mesh>,
    bottle: Handle<Mesh>,
    rag: Handle<Mesh>,
    can_material: Handle<StandardMaterial>,
    bottle_material: Handle<StandardMaterial>,
    rag_material: Handle<StandardMaterial>,
}

fn setup_assets(
    mut commands: Commands,
    fx: Res<ThrowFxData>,
    mut images: ResMut<Assets<Image>>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let (base, size) = build_atlas();
    let (data, levels) = crate::map_materials::mip_chain(base, size, size, false);
    let mut image = Image::new_fill(
        Extent3d { width: size as u32, height: size as u32, depth_or_array_layers: 1 },
        TextureDimension::D2,
        &[0, 0, 0, 0],
        TextureFormat::Rgba8Unorm,
        RenderAssetUsages::RENDER_WORLD,
    );
    image.data = Some(data);
    image.texture_descriptor.mip_level_count = levels;
    image.sampler = ImageSampler::Descriptor(ImageSamplerDescriptor::linear());
    let g = &fx.grenade;
    let solid = |c: (f32, f32, f32), rough: f32| StandardMaterial {
        base_color: Color::linear_rgb(c.0, c.1, c.2),
        perceptual_roughness: rough,
        ..default()
    };
    let glow = Color::linear_rgb(1.0, 0.5, 0.15);
    commands.insert_resource(FxAssets {
        atlas: images.add(image),
        can: meshes.add(Cylinder::new(0.035, 0.13)),
        bottle: meshes.add(Cylinder::new(0.037, 0.2)),
        rag: meshes.add(Sphere::new(0.03).mesh().ico(1).expect("a small ico sphere")),
        can_material: materials.add(solid(g.smoke_color, 0.6)),
        bottle_material: materials.add(solid(g.molotov_color, 0.15)),
        rag_material: materials.add(StandardMaterial {
            base_color: glow,
            emissive: glow.to_linear() * g.rag_glow,
            unlit: true,
            ..default()
        }),
    });
}

/// The scene's sun and ambient, exposed for the camera, for the clouds' own lighting.
fn scene_light(
    suns: &Query<(&DirectionalLight, &GlobalTransform)>,
    ambient: Option<&GlobalAmbientLight>,
    exposure: f32,
) -> SceneLight {
    let sun = suns.iter().next();
    SceneLight {
        to_sun: sun.map(|(_, t)| t.back().as_vec3()),
        sun: sun.map_or(Vec3::ZERO, |(l, _)| {
            Vec3::from_slice(&l.color.to_linear().to_f32_array()[..3]) * l.illuminance * exposure / PI
        }),
        ambient: ambient.map_or(Vec3::ZERO, |a| {
            Vec3::from_slice(&a.color.to_linear().to_f32_array()[..3]) * a.brightness * exposure
        }),
    }
}

/// A cloud on screen.
#[derive(Component)]
struct CloudFx {
    id: ThrowId,
    centres: Vec<Vec3>,
    mesh: Handle<Mesh>,
    material: Handle<ThrowFxMaterial>,
    /// The direction (mesh space) the cards were last sorted for.
    sorted_for: Vec3,
}

/// A fire on screen, and its light.
#[derive(Component)]
struct FireFx {
    id: ThrowId,
    material: Handle<ThrowFxMaterial>,
    light: Entity,
}

/// A grenade in flight on screen.
#[derive(Component)]
struct GrenadeFx(ThrowId);

fn base_material(alpha_mode: AlphaMode) -> StandardMaterial {
    StandardMaterial { alpha_mode, unlit: true, cull_mode: None, double_sided: true, ..default() }
}

fn preset_index(settings: Option<&Settings>) -> usize {
    settings.map_or(2, |s| s.video.preset.index()).min(3)
}

#[allow(clippy::too_many_arguments)]
fn sync_clouds(
    mut commands: Commands,
    data: Res<Data>,
    fx: Res<ThrowFxData>,
    view: Res<ThrowView>,
    level: Option<Res<CurrentLevel>>,
    settings: Option<Res<Settings>>,
    me: Query<&PlayerId, With<Controlled>>,
    assets: Option<Res<FxAssets>>,
    suns: Query<(&DirectionalLight, &GlobalTransform)>,
    ambient: Option<Res<GlobalAmbientLight>>,
    camera: Query<(&GlobalTransform, Option<&Exposure>), With<ViewCamera>>,
    mut clouds: Query<(Entity, &mut CloudFx)>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<ThrowFxMaterial>>,
) {
    let (Some(level), Some(assets)) = (level, assets) else { return };
    let sim = &data.throwables.smoke;
    let dt = data.tick_dt();
    let look = &fx.smoke;
    let (eye, exposure) = camera.iter().next().map_or((Vec3::ZERO, Exposure::default().exposure()), |(t, e)| {
        (t.translation(), e.copied().unwrap_or_default().exposure())
    });
    let light = scene_light(&suns, ambient.as_deref(), exposure);
    for (e, c) in &clouds {
        if !view.smokes.iter().any(|s| s.smoke.id == c.id) {
            commands.entity(e).despawn();
        }
    }
    let blend = view.blend(dt);
    for s in &view.smokes {
        let centre = s.smoke.centre(sim);
        let age_s = (s.smoke.age as f32 + blend) * dt;
        let tunnels: Vec<(Vec3, Vec3, f32)> = s
            .tunnels
            .live(view.now_s, look.tunnel.life_s, look.tunnel.refill_s)
            .map(|(t, open)| (t.a, t.b, open))
            .collect();
        let mut params =
            smoke_uniform(look, s.smoke.growth(sim, dt), s.smoke.density(sim, dt), age_s, &light, &tunnels);
        params.tint = smoke_team_tint(
            s.team,
            s.smoke.id.owner,
            me.iter().next().map(|id| id.0),
            settings.as_deref(),
            rgb(look.tint),
        )
        .extend(params.tint.w);
        match clouds.iter_mut().find(|(_, c)| c.id == s.smoke.id) {
            Some((_, mut c)) => {
                if let Some(mut m) = materials.get_mut(&c.material) {
                    m.extension.params = params;
                }
                // Back to front again once the view of the cloud has turned far enough.
                let dir = (eye - centre).normalize_or_zero();
                if dir.angle_between(c.sorted_for) > look.resort_deg.to_radians()
                    && let Some(mut mesh) = meshes.get_mut(&c.mesh)
                {
                    mesh.insert_indices(Indices::U32(card_indices(back_to_front(&c.centres, eye - centre))));
                    c.sorted_for = dir;
                }
            }
            None => {
                let seed = s.smoke.id.owner ^ ((s.smoke.id.seq as u64) << 48);
                let world = &level.world;
                let to_sun = light.to_sun;
                let sunlit = |p: Vec3| to_sun.is_none_or(|d| world.raycast(centre + p, d, 80.0).is_none());
                let cards = smoke_cards(look, sim, preset_index(settings.as_deref()), seed, sunlit);
                let centres = cards.centres.clone();
                let indices = card_indices(back_to_front(&centres, eye - centre));
                let mesh = meshes.add(cards.into_mesh(indices));
                let material = materials.add(ThrowFxMaterial {
                    base: base_material(AlphaMode::Blend),
                    extension: ThrowFxExt { params, atlas: assets.atlas.clone() },
                });
                commands.spawn((
                    Name::new("Smoke cloud"),
                    CloudFx {
                        id: s.smoke.id,
                        centres,
                        mesh: mesh.clone(),
                        material: material.clone(),
                        sorted_for: (eye - centre).normalize_or_zero(),
                    },
                    Mesh3d(mesh),
                    MeshMaterial3d(material),
                    Transform::from_translation(centre),
                    NotShadowCaster,
                    NotShadowReceiver,
                    NoFrustumCulling,
                    DespawnOnExit(AppState::InGame),
                ));
            }
        }
    }
}

/// A fire's burn-out alpha: full while it burns, shrinking over the last `fade_s` and once doused.
pub fn fire_alpha(look: &FireLook, sim: &MolotovSpec, age_s: f32, doused_s: Option<f32>) -> f32 {
    let fade = look.fade_s.max(1e-3);
    let end = ((sim.burn_s - age_s) / fade).clamp(0.0, 1.0);
    let out = doused_s.map_or(1.0, |d| (1.0 - d / fade).clamp(0.0, 1.0));
    end.min(out)
}

#[allow(clippy::too_many_arguments)]
fn sync_fires(
    mut commands: Commands,
    data: Res<Data>,
    fx: Res<ThrowFxData>,
    view: Res<ThrowView>,
    settings: Option<Res<Settings>>,
    assets: Option<Res<FxAssets>>,
    fires: Query<(Entity, &FireFx)>,
    mut lights: Query<&mut PointLight>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<ThrowFxMaterial>>,
) {
    let Some(assets) = assets else { return };
    let sim = &data.throwables.molotov;
    let dt = data.tick_dt();
    let look = &fx.fire;
    for (e, f) in &fires {
        if !view.fires.iter().any(|v| v.fire.id == f.id) {
            commands.entity(e).despawn();
        }
    }
    let blend = view.blend(dt);
    for v in &view.fires {
        let age_s = (v.fire.age as f32 + blend) * dt;
        let spread = (v.fire.radius(sim, dt) / sim.radius_m.max(1e-3)).clamp(0.0, 1.0);
        let alpha = fire_alpha(look, sim, age_s, v.doused_s);
        let params = fire_uniform(look, spread, alpha, age_s);
        let flicker = 1.0 + look.light_flicker * ((age_s * 13.0).sin() * 0.6 + (age_s * 31.0).sin() * 0.4);
        match fires.iter().find(|(_, f)| f.id == v.fire.id) {
            Some((_, f)) => {
                if let Some(mut m) = materials.get_mut(&f.material) {
                    m.extension.params = params;
                }
                if let Ok(mut l) = lights.get_mut(f.light) {
                    l.intensity = look.light_lumens * alpha * spread.max(0.3) * flicker;
                }
            }
            None => {
                let seed = v.fire.id.owner ^ ((v.fire.id.seq as u64) << 48);
                let cards = fire_cards(look, sim, preset_index(settings.as_deref()), seed);
                let indices = card_indices(0..cards.count());
                let mesh = meshes.add(cards.into_mesh(indices));
                let material = materials.add(ThrowFxMaterial {
                    base: base_material(AlphaMode::Add),
                    extension: ThrowFxExt { params, atlas: assets.atlas.clone() },
                });
                let c = look.light_color;
                let fire = commands
                    .spawn((
                        Name::new("Fire"),
                        Mesh3d(mesh),
                        MeshMaterial3d(material.clone()),
                        Transform::from_translation(v.fire.at),
                        NotShadowCaster,
                        NotShadowReceiver,
                        NoFrustumCulling,
                        DespawnOnExit(AppState::InGame),
                    ))
                    .id();
                // A little light over the flames (no shadows).
                let light = commands
                    .spawn((
                        PointLight {
                            color: Color::linear_rgb(c.0, c.1, c.2),
                            intensity: 0.0,
                            range: look.light_range_m,
                            radius: 0.4,
                            shadow_maps_enabled: false,
                            ..default()
                        },
                        Transform::from_translation(Vec3::Y * 0.7),
                        ChildOf(fire),
                    ))
                    .id();
                commands.entity(fire).insert(FireFx { id: v.fire.id, material, light });
            }
        }
    }
}

#[derive(Component)]
struct HeldGrenade(ThrowKind);

fn sync_held_grenade(
    mut commands: Commands,
    data: Res<Data>,
    fx: Res<ThrowFxData>,
    assets: Option<Res<FxAssets>>,
    me: Query<(&vetf_net::PlayerItems, &vetf_net::Vitals), With<Controlled>>,
    camera: Query<Entity, With<ViewCamera>>,
    mut held: Query<(Entity, &HeldGrenade, &mut Transform)>,
) {
    let Some(assets) = assets else { return };
    let hand = me.iter().next().filter(|(_, v)| !v.health.dead).map(|(it, _)| it.0.throw);
    let kind = hand.and_then(|h| h.selected.or(h.windup.map(|w| w.kind)));
    let camera = camera.iter().next();
    for (entity, current, _) in &held {
        if kind != Some(current.0) || camera.is_none() {
            commands.entity(entity).despawn();
        }
    }
    let (Some(kind), Some(camera), Some(hand)) = (kind, camera, hand) else { return };
    let charge = hand.charge_fraction(&data.throwables.throw, data.net.tick_hz);
    let (r, u, f) = data.throwables.throw.hand;
    let pose = Transform::from_translation(Vec3::new(r, u, -f) + rgb(fx.grenade.held_charge_offset) * charge)
        .with_rotation(Quat::from_rotation_z(-fx.grenade.held_tilt_deg.to_radians() * charge))
        .with_scale(Vec3::splat(fx.grenade.held_scale));
    if let Some((_, _, mut transform)) = held.iter_mut().find(|(_, h, _)| h.0 == kind) {
        *transform = pose;
        return;
    }
    let (mesh, material) = match kind {
        ThrowKind::Smoke => (assets.can.clone(), assets.can_material.clone()),
        ThrowKind::Molotov => (assets.bottle.clone(), assets.bottle_material.clone()),
    };
    let mut entity = commands.spawn((
        Name::new("Grenade in hand"),
        HeldGrenade(kind),
        Mesh3d(mesh),
        MeshMaterial3d(material),
        pose,
        ChildOf(camera),
        NotShadowCaster,
        DespawnOnExit(AppState::InGame),
    ));
    if kind == ThrowKind::Molotov {
        entity.with_child((
            Mesh3d(assets.rag.clone()),
            MeshMaterial3d(assets.rag_material.clone()),
            Transform::from_xyz(0., 0.12, 0.),
            NotShadowCaster,
        ));
    }
}

fn sync_grenades(
    mut commands: Commands,
    data: Res<Data>,
    fx: Res<ThrowFxData>,
    view: Res<ThrowView>,
    assets: Option<Res<FxAssets>>,
    mut grenades: Query<(Entity, &GrenadeFx, &mut Transform)>,
) {
    let Some(assets) = assets else { return };
    let dt = data.tick_dt();
    let blend = view.blend(dt);
    for (e, g, _) in &grenades {
        if !view.flying.iter().any(|f| f.p.id == g.0) {
            commands.entity(e).despawn();
        }
    }
    for f in &view.flying {
        let pos = f.prev.lerp(f.p.pos, if f.landed || f.p.resting { 1.0 } else { blend });
        // Tumbling end over end about an axis across its flight; lying on its side once it rests.
        let across = f.p.vel.cross(Vec3::Y).try_normalize().unwrap_or(Vec3::X);
        let turns = if f.p.resting || f.landed { 0.25 } else { (f.p.age as f32 + blend) * dt * fx.grenade.tumble_rps };
        let rot = Quat::from_axis_angle(across, turns * TAU);
        match grenades.iter_mut().find(|(_, g, _)| g.0 == f.p.id) {
            Some((_, _, mut t)) => {
                t.translation = pos;
                t.rotation = rot;
            }
            None => {
                let (mesh, material) = match f.p.kind {
                    ThrowKind::Smoke => (assets.can.clone(), assets.can_material.clone()),
                    ThrowKind::Molotov => (assets.bottle.clone(), assets.bottle_material.clone()),
                };
                let mut entity = commands.spawn((
                    Name::new("Grenade"),
                    GrenadeFx(f.p.id),
                    Mesh3d(mesh),
                    MeshMaterial3d(material),
                    Transform::from_translation(pos).with_rotation(rot),
                    NotShadowCaster,
                    DespawnOnExit(AppState::InGame),
                ));
                if f.p.kind == ThrowKind::Molotov {
                    entity.with_child((
                        Mesh3d(assets.rag.clone()),
                        MeshMaterial3d(assets.rag_material.clone()),
                        Transform::from_xyz(0.0, 0.12, 0.0),
                        NotShadowCaster,
                    ));
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn smoke_keeps_owner_team_colour_for_every_viewer_and_ffa_is_neutral() {
        let neutral = Vec3::splat(0.5);
        for palette in crate::settings::TeamColours::ALL {
            let mut settings = Settings::default();
            settings.hud.team_colours = *palette;
            let a = smoke_team_tint(Some(Team::A), 7, Some(7), Some(&settings), neutral);
            let b = smoke_team_tint(Some(Team::B), 7, Some(8), Some(&settings), neutral);
            assert_ne!(a, b);
            assert_eq!(b, smoke_team_tint(Some(Team::B), 7, Some(7), Some(&settings), neutral));
            assert_eq!(a, smoke_team_tint(None, 7, Some(7), Some(&settings), neutral));
            assert_eq!(neutral, smoke_team_tint(None, 7, Some(8), Some(&settings), neutral));
        }
    }
    use vetf_sim::GameData;

    fn data() -> (ThrowFxData, GameData) {
        (ThrowFxData::embedded(), GameData::embedded())
    }

    #[test]
    fn the_data_file_parses_and_matches_the_one_on_disk() {
        let d = ThrowFxData::embedded();
        let on_disk =
            std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../../assets/data/throwable_fx.ron"))
                .unwrap();
        assert_eq!(ron::from_str::<ThrowFxData>(&on_disk).unwrap(), d);
        for q in 0..4 {
            assert!(d.smoke.cards[q] > 0 && d.fire.flames[q] > 0);
            assert!(d.smoke.cards[q] <= 160, "bounded GPU work: {} puffs", d.smoke.cards[q]);
            if q > 0 {
                assert!(d.smoke.cards[q] >= d.smoke.cards[q - 1]);
            }
        }
        assert!(d.smoke.near_fade.0 < d.smoke.near_fade.1);
        let t = &d.smoke.tunnel;
        assert!(t.refill_s <= t.life_s && t.life_s <= 4.0, "a couple of seconds, then it refills");
        assert!(t.radius_m > 0.2 && t.radius_m < 1.5);
    }

    /// The puffs fill the cloud: inside its radii (plus half a card at the rim), none under the ground, about as
    /// many as the preset says; fewer puffs on LOW are bigger so the cloud stays as covered. Deterministic.
    #[test]
    fn puffs_fill_the_cloud() {
        let (fx, g) = data();
        let sim = &g.throwables.smoke;
        let all = smoke_cards(&fx.smoke, sim, 2, 7, |_| true);
        assert_eq!(all.count(), fx.smoke.cards[2]);
        assert_eq!(all.positions.len(), all.count() * 4);
        for c in &all.centres {
            let e = Vec3::new(c.x / sim.radius_m, c.y / sim.height_m, c.z / sim.radius_m).length();
            assert!(e <= 1.0 + 1e-4, "inside the cloud: {c}");
            assert!(c.y >= -sim.lift_m - 1e-4, "above its ground: {c}");
        }
        let covered = |cards: &Cards| cards.uv1.iter().step_by(4).map(|o| (o[0] * 2.0).powi(2)).sum::<f32>();
        let low = smoke_cards(&fx.smoke, sim, 0, 7, |_| true);
        assert!(low.count() < all.count());
        let ratio = covered(&low) / covered(&all);
        assert!((0.75..1.33).contains(&ratio), "LOW covers about as much: {ratio}");
        assert_eq!(smoke_cards(&fx.smoke, sim, 2, 7, |_| true).positions, all.positions, "deterministic");
        // Shaded puffs carry the sun share.
        let shaded = smoke_cards(&fx.smoke, sim, 2, 7, |_| false);
        assert!(shaded.colors.iter().all(|c| (c[0] - fx.smoke.sun_shade).abs() < 1e-6));
        // Darker at the bottom than at the top, on average.
        let avg = |f: &dyn Fn(f32) -> bool| {
            let v: Vec<f32> =
                all.colors.iter().zip(&all.positions).filter(|(_, p)| f(p[1])).map(|(c, _)| c[1]).collect();
            v.iter().sum::<f32>() / v.len().max(1) as f32
        };
        assert!(avg(&|y| y < -0.5) < avg(&|y| y > 1.0));
    }

    #[test]
    fn flames_stand_on_the_fire_and_embers_rise_from_it() {
        let (fx, g) = data();
        let sim = &g.throwables.molotov;
        let c = fire_cards(&fx.fire, sim, 2, 3);
        assert_eq!(c.count(), fx.fire.flames[2] + fx.fire.embers[2]);
        for (i, p) in c.centres.iter().enumerate() {
            assert!(Vec2::new(p.x, p.z).length() <= sim.radius_m, "{p}");
            let ember = c.colors[i * 4][2] > 0.5;
            if !ember {
                // A flame's foot is on the ground: its lower corners at height 0.
                assert_eq!(c.uv1[i * 4][1], 0.0);
                assert!(c.uv1[i * 4 + 2][1] > 0.3, "it stands up");
            }
        }
        // Burn-out: full while burning, fading at the end and once doused.
        assert_eq!(fire_alpha(&fx.fire, sim, 1.0, None), 1.0);
        assert!(fire_alpha(&fx.fire, sim, sim.burn_s - fx.fire.fade_s * 0.5, None) < 0.6);
        assert_eq!(fire_alpha(&fx.fire, sim, 1.0, Some(fx.fire.fade_s)), 0.0);
    }

    /// The cards draw back to front: the farthest first.
    #[test]
    fn cards_sort_back_to_front() {
        let centres = [Vec3::new(0.0, 0.0, -1.0), Vec3::new(0.0, 0.0, 5.0), Vec3::new(0.0, 0.0, 1.0)];
        let order = back_to_front(&centres, Vec3::new(0.0, 0.0, 10.0));
        assert_eq!(order, vec![0, 2, 1]);
        assert_eq!(card_indices(order)[..6], [0, 1, 2, 0, 2, 3]);
    }

    /// The uniform carries the cloud's state and at most TUNNELS bullet lines, each with how open it is.
    #[test]
    fn the_uniform_carries_the_tunnels() {
        let (fx, _) = data();
        let light = SceneLight { to_sun: Some(Vec3::Y), sun: Vec3::ONE, ambient: Vec3::splat(0.5) };
        let lines: Vec<(Vec3, Vec3, f32)> = (0..12).map(|i| (Vec3::ZERO, Vec3::X * i as f32, 0.5)).collect();
        let u = smoke_uniform(&fx.smoke, 0.5, 1.0, 3.0, &light, &lines);
        assert_eq!(u.fade.w, TUNNELS as f32);
        assert_eq!(u.tunnel_a[1].w, 0.5);
        assert_eq!(u.tunnel_b[3].x, 3.0);
        assert_eq!((u.state.y, u.state.z, u.state.w), (0.5, 1.0, 3.0));
        assert_eq!(u.sun_dir, Vec4::new(0.0, 1.0, 0.0, 1.0));
        let none = smoke_uniform(&fx.smoke, 1.0, 1.0, 3.0, &SceneLight::default(), &[]);
        assert_eq!((none.fade.w, none.sun_dir.w), (0.0, 0.0));
    }

    /// The atlas has a soft puff in every puff cell, a flame in every flame cell (open at the top, solid at the
    /// foot), and stays clear at the cells' borders (no bleeding between cards).
    #[test]
    fn the_atlas_paints_puffs_flames_and_embers() {
        let (atlas, size) = build_atlas();
        assert_eq!(atlas.len(), size * size * 4);
        let alpha = |cell: u32, x: usize, y: usize| {
            let (cx, cy) = ((cell % CELLS) as usize * CELL, (cell / CELLS) as usize * CELL);
            atlas[((cy + y) * size + cx + x) * 4 + 3]
        };
        for cell in 0..CELLS * CELLS {
            let cover = (0..CELL)
                .flat_map(|y| (0..CELL).map(move |x| (x, y)))
                .filter(|(x, y)| alpha(cell, *x, *y) > 128)
                .count();
            let share = cover as f32 / (CELL * CELL) as f32;
            assert!(share > 0.05 && share < 0.8, "cell {cell}: {share}");
            for i in 0..CELL {
                assert!(alpha(cell, i, 0) < 8 && alpha(cell, 0, i) < 8, "cell {cell} border");
            }
        }
        for cell in FLAME_CELLS {
            assert!(alpha(cell, CELL / 2, CELL * 9 / 10) > alpha(cell, CELL / 2, CELL / 10), "flame {cell}");
        }
    }

    /// The shader compiles and validates (naga, as Bevy builds it), its vertex and fragment entry points both,
    /// with and without a depth prepass and under MSAA. Bevy's own modules are stood in for by stubs with the same
    /// signatures (`mesh_functions`, the view, `forward_io`, `pbr_types`, `pbr_functions`, `prepass_utils`).
    #[test]
    fn the_shader_compiles() {
        use naga_oil::compose::{
            ComposableModuleDescriptor, Composer, NagaModuleDescriptor, ShaderDefValue, ShaderLanguage, ShaderType,
        };
        use std::collections::HashMap;
        const STUBS: &[&str] = &[
            "#define_import_path bevy_pbr::mesh_functions
            @group(1) @binding(0) var<storage> meshes: array<mat4x4<f32>>;
            fn get_world_from_local(instance_index: u32) -> mat4x4<f32> { return meshes[instance_index]; }",
            "#define_import_path bevy_pbr::mesh_view_bindings
            struct View { world_position: vec3<f32>, world_from_view: mat4x4<f32>, clip_from_world: mat4x4<f32>, exposure: f32 }
            @group(0) @binding(0) var<uniform> view: View;",
            "#define_import_path bevy_pbr::view_transformations
            #import bevy_pbr::mesh_view_bindings::view
            fn position_world_to_clip(world_pos: vec3<f32>) -> vec4<f32> { return view.clip_from_world * vec4(world_pos, 1.0); }
            fn depth_ndc_to_view_z(ndc_depth: f32) -> f32 { return -0.1 / ndc_depth; }",
            "#define_import_path bevy_pbr::forward_io
            struct Vertex {
                @builtin(instance_index) instance_index: u32,
            #ifdef VERTEX_POSITIONS
                @location(0) position: vec3<f32>,
            #endif
            #ifdef VERTEX_NORMALS
                @location(1) normal: vec3<f32>,
            #endif
            #ifdef VERTEX_UVS_A
                @location(2) uv: vec2<f32>,
            #endif
            #ifdef VERTEX_UVS_B
                @location(3) uv_b: vec2<f32>,
            #endif
            #ifdef VERTEX_COLORS
                @location(5) color: vec4<f32>,
            #endif
            };
            struct VertexOutput {
                @builtin(position) position: vec4<f32>,
                @location(0) world_position: vec4<f32>,
                @location(1) world_normal: vec3<f32>,
            #ifdef VERTEX_UVS_A
                @location(2) uv: vec2<f32>,
            #endif
            #ifdef VERTEX_UVS_B
                @location(3) uv_b: vec2<f32>,
            #endif
            #ifdef VERTEX_COLORS
                @location(5) color: vec4<f32>,
            #endif
            #ifdef VERTEX_OUTPUT_INSTANCE_INDEX
                @location(6) @interpolate(flat) instance_index: u32,
            #endif
            }
            struct FragmentOutput { @location(0) color: vec4<f32>, }",
            "#define_import_path bevy_pbr::pbr_types
            struct StandardMaterial { base_color: vec4<f32>, flags: u32, }
            struct PbrInput { material: StandardMaterial, world_position: vec4<f32>, frag_coord: vec4<f32>, is_orthographic: bool, }
            const STANDARD_MATERIAL_FLAGS_FOG_ENABLED_BIT: u32 = 1u << 8u;
            const STANDARD_MATERIAL_FLAGS_ALPHA_MODE_ADD: u32 = 4u << 29u;
            fn pbr_input_new() -> PbrInput {
                var p: PbrInput;
                p.material.base_color = vec4(1.0);
                p.material.flags = 0u;
                return p;
            }",
            "#define_import_path bevy_pbr::pbr_functions
            #import bevy_pbr::pbr_types
            fn main_pass_post_lighting_processing(pbr_input: pbr_types::PbrInput, input_color: vec4<f32>) -> vec4<f32> {
                return input_color * f32(pbr_input.material.flags & 1u);
            }",
            "#define_import_path bevy_pbr::prepass_utils
            @group(0) @binding(9) var depth_prepass_texture: texture_depth_2d;
            fn prepass_depth(frag_coord: vec4<f32>, sample_index: u32) -> f32 {
                return textureLoad(depth_prepass_texture, vec2<i32>(frag_coord.xy), 0);
            }",
        ];
        let source =
            std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../../assets/shaders/throwables.wgsl"))
                .expect("throwables.wgsl");
        let base = ["VERTEX_POSITIONS", "VERTEX_NORMALS", "VERTEX_UVS_A", "VERTEX_UVS_B", "VERTEX_COLORS"];
        for extra in [&[][..], &["DEPTH_PREPASS"][..], &["DEPTH_PREPASS", "MULTISAMPLED"][..]] {
            let mut defs: HashMap<String, ShaderDefValue> =
                base.iter().chain(extra).map(|d| (d.to_string(), ShaderDefValue::Bool(true))).collect();
            defs.insert("MATERIAL_BIND_GROUP".into(), ShaderDefValue::UInt(3));
            let mut composer = Composer::default();
            for (i, stub) in STUBS.iter().enumerate() {
                composer
                    .add_composable_module(ComposableModuleDescriptor {
                        source: stub,
                        file_path: &format!("stub_{i}.wgsl"),
                        language: ShaderLanguage::Wgsl,
                        shader_defs: defs.clone(),
                        ..Default::default()
                    })
                    .unwrap_or_else(|e| panic!("stub {i}: {e:?}"));
            }
            let module = composer
                .make_naga_module(NagaModuleDescriptor {
                    source: &source,
                    file_path: "shaders/throwables.wgsl",
                    shader_type: ShaderType::Wgsl,
                    shader_defs: defs,
                    ..Default::default()
                })
                .unwrap_or_else(|e| panic!("{extra:?}: {}", e.emit_to_string(&composer)));
            let mut v =
                naga::valid::Validator::new(naga::valid::ValidationFlags::all(), naga::valid::Capabilities::all());
            v.validate(&module).unwrap_or_else(|e| panic!("{extra:?}: {e:?}"));
            let entries: Vec<&str> = module.entry_points.iter().map(|e| e.name.as_str()).collect();
            assert!(entries.contains(&"vertex") && entries.contains(&"fragment"), "{entries:?}");
        }
    }
}
