//! Fluffy hedges and lawn grass on Showhome.
//!
//! **Hedges** (`Look::Hedge` brushes): the textured hedge box is hidden and replaced by an opaque, dark core (the
//! box shrunk a little, top and side edges rounded) wrapped in a shell of alpha-masked leaf-cluster cards. The
//! cards are scattered over every face a player can see, jittered in place, size, roll and tilt, and poke out of
//! the box so the outline is bumpy and the top edges read round. Their normals are bent outward from the hedge's
//! rounded volume (not the cards' own), their corners darken with depth into the hedge (AO in the vertex colour)
//! and toward the ground, and the shader adds light wrap and sun-through-leaves translucency. One mesh per hedge
//! for the cards, one for the core; only the core casts shadows.
//!
//! **Grass**: the mown lawn (shells over the art kit's lawn surfaces) and the taller tufts at its edges, in
//! [`grass`] (`assets/shaders/grass.wgsl`).
//!
//! The hedge cards sway in the wind in the vertex shader (`assets/shaders/foliage.wgsl`, a StandardMaterial
//! extension, used for the prepass too so depth and motion vectors match). Every look number is in
//! `assets/data/foliage.ron`, per VIDEO quality preset: LOW keeps the plain boxes and the flat lawn. The leaf card
//! atlas is built by `assets/fx/foliage/build_atlas.py` from Krea2 raws.
//!
//! `VETF_FOLIAGE=off|low|medium|high|ultra` overrides the preset (before/after screenshots).

pub mod grass;

use crate::AppState;
use crate::config::CurrentLevel;
use crate::map_materials::{ShowhomeMaterials, mip_chain};
use crate::settings::{Preset, Settings};
use bevy::asset::RenderAssetUsages;
use bevy::image::{ImageLoaderSettings, ImageSampler, ImageSamplerDescriptor};
use bevy::light::NotShadowCaster;
use bevy::mesh::{Indices, PrimitiveTopology};
use bevy::pbr::{ExtendedMaterial, MaterialExtension, MaterialPlugin};
use bevy::prelude::*;
use bevy::render::render_resource::{AsBindGroup, ShaderType, TextureFormat};
use bevy::shader::ShaderRef;
use grass::GrassData;
use serde::Deserialize;
use vetf_sim::level::Level;
use vetf_sim::movement::collision::{Brush, BrushKind, Look};
use vetf_sim::rng::SplitMix;

pub struct FoliagePlugin;

impl Plugin for FoliagePlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins(MaterialPlugin::<FoliageMaterial>::default())
            .insert_resource(load_data())
            .init_resource::<FoliageState>()
            .add_systems(Startup, load_assets)
            .add_systems(Update, finish_textures)
            .add_systems(
                Update,
                (build_foliage, show_hedge_boxes, tick_wind).chain().run_if(in_state(AppState::InGame)),
            );
        grass::plugin(app);
        // `VETF_GPU_PROFILE=1`: GPU time per render pass in the log every two seconds (measuring foliage cost).
        if std::env::var_os("VETF_GPU_PROFILE").is_some() {
            app.add_plugins(bevy::render::diagnostic::RenderDiagnosticsPlugin).add_systems(Update, log_gpu_passes);
        }
    }
}

const SHADER: &str = "shaders/foliage.wgsl";
const HEDGE_ATLAS: &str = "textures/foliage/hedge_cards.png";
const HEDGE_NORMALS: &str = "textures/foliage/hedge_cards_normal.png";
/// Card cells in the atlas (columns, rows); see `build_atlas.py`.
const HEDGE_CELLS: (u32, u32) = (4, 4);
/// UV inset of a card inside its atlas cell, so small mips do not pull in the neighbouring card.
const CELL_INSET: f32 = 0.004;

// ---------------------------------------------------------------------------------------------- data

/// `game/assets/data/foliage.ron`. Lists of four follow the quality preset LOW, MEDIUM, HIGH, ULTRA.
#[derive(Resource, Debug, Clone, PartialEq, Deserialize)]
pub struct FoliageData {
    pub hedge: HedgeData,
    pub grass: GrassData,
    pub wind: WindData,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct HedgeData {
    pub density: [f32; 4],
    pub card_size: (f32, f32),
    pub core_inset: f32,
    pub core_radius: f32,
    pub shell_inset: f32,
    pub shell_radius: f32,
    pub poke: (f32, f32),
    pub tilt_deg: f32,
    pub roll_deg: f32,
    pub normal_radius: f32,
    pub normal_card_mix: f32,
    pub normal_clump_mix: f32,
    pub ao_depth: f32,
    pub ao_min: f32,
    pub clump_shade: f32,
    pub ground_ao: f32,
    pub ground_ao_height: f32,
    pub value_jitter: f32,
    pub hue_jitter: f32,
    pub tint: (f32, f32, f32),
    pub core_tint: (f32, f32, f32),
    pub roughness: f32,
    pub reflectance: f32,
    pub alpha_cutoff: f32,
    pub wrap: f32,
    pub translucency: f32,
    pub translucency_power: f32,
    pub shadow_probe: f32,
    pub wind_amplitude: f32,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct WindData {
    pub direction_deg: f32,
    pub frequency: f32,
    pub wavelength: f32,
    pub gust: f32,
}

impl WindData {
    /// The direction the wind blows toward, in Bevy's frame (design 0° = east = +X, 90° = north = −Z).
    pub fn dir(&self) -> Vec3 {
        let a = self.direction_deg.to_radians();
        Vec3::new(a.cos(), 0.0, -a.sin())
    }
}

const EMBEDDED: &str = include_str!("../../../assets/data/foliage.ron");

pub fn embedded() -> FoliageData {
    ron::from_str(EMBEDDED).expect("game/assets/data/foliage.ron is valid")
}

/// foliage.ron from the data folder (tunable without a rebuild), else the built-in copy.
fn load_data() -> FoliageData {
    let path = crate::config::assets_root().join("data").join("foliage.ron");
    match std::fs::read_to_string(&path).map(|t| ron::from_str::<FoliageData>(&t)) {
        Ok(Ok(d)) => d,
        Ok(Err(e)) => {
            error!("{} is invalid ({e}); using the built-in copy", path.display());
            embedded()
        }
        Err(_) => embedded(),
    }
}

/// The quality level foliage is built for: the VIDEO preset (0 LOW .. 3 ULTRA), or `VETF_FOLIAGE`. `None` = off.
pub fn quality(preset: Preset, env: Option<&str>) -> Option<usize> {
    match env.map(|e| e.trim().to_ascii_lowercase()) {
        Some(e) if e == "off" => None,
        Some(e) if !e.is_empty() => match e.as_str() {
            "low" => Some(0),
            "medium" => Some(1),
            "high" => Some(2),
            "ultra" => Some(3),
            _ => Some(preset.index()),
        },
        _ => Some(preset.index()),
    }
}

// ---------------------------------------------------------------------------------------------- material

pub type FoliageMaterial = ExtendedMaterial<StandardMaterial, FoliageExt>;

/// The shader's `Foliage` uniform (see foliage.wgsl for each lane).
#[derive(Clone, Copy, Debug, Default, PartialEq, ShaderType, Reflect)]
pub struct FoliageUniform {
    pub wind_dir: Vec4,
    pub wind: Vec4,
    pub time: Vec4,
    pub fade: Vec4,
    pub light: Vec4,
    pub root_tint: Vec4,
    pub tip_tint: Vec4,
}

#[derive(Asset, AsBindGroup, Reflect, Debug, Clone, Default)]
pub struct FoliageExt {
    #[uniform(100)]
    pub params: FoliageUniform,
}

impl MaterialExtension for FoliageExt {
    fn vertex_shader() -> ShaderRef {
        SHADER.into()
    }
    fn fragment_shader() -> ShaderRef {
        SHADER.into()
    }
    fn prepass_vertex_shader() -> ShaderRef {
        SHADER.into()
    }
}

/// The hedge card uniform.
pub fn hedge_uniform(d: &FoliageData) -> FoliageUniform {
    let h = &d.hedge;
    let w = &d.wind;
    FoliageUniform {
        wind_dir: d.wind.dir().extend(0.0),
        wind: Vec4::new(h.wind_amplitude, w.frequency * std::f32::consts::TAU, wave_number(w), w.gust),
        light: Vec4::new(h.wrap, h.translucency, h.shadow_probe, h.translucency_power),
        root_tint: Vec4::ONE,
        tip_tint: Vec4::ONE,
        ..default()
    }
}

fn wave_number(w: &WindData) -> f32 {
    std::f32::consts::TAU / w.wavelength.max(0.1)
}

// ---------------------------------------------------------------------------------------------- textures

/// The card atlases (reserved handles, filled with mips once loaded) and the hedge card material.
#[derive(Resource)]
struct FoliageAssets {
    hedge: Handle<FoliageMaterial>,
    pending: Vec<PendingImage>,
}

struct PendingImage {
    source: Handle<Image>,
    done: Handle<Image>,
    srgb: bool,
    /// Alpha-tested: keep each mip's coverage at the cutoff (else cards thin out with distance).
    cutoff: Option<f32>,
    fallback: [u8; 4],
}

fn load_assets(
    mut commands: Commands,
    server: Res<AssetServer>,
    images: Res<Assets<Image>>,
    data: Res<FoliageData>,
    mut materials: ResMut<Assets<FoliageMaterial>>,
) {
    let mut pending = Vec::new();
    let mut image = |path: &'static str, srgb: bool, cutoff: Option<f32>, fallback: [u8; 4]| {
        let done = images.reserve_handle();
        pending.push(PendingImage {
            source: server.load_builder().with_settings(move |s: &mut ImageLoaderSettings| s.is_srgb = srgb).load(path),
            done: done.clone(),
            srgb,
            cutoff,
            fallback,
        });
        done
    };
    let h = &data.hedge;
    let hedge_albedo = image(HEDGE_ATLAS, true, Some(h.alpha_cutoff), [98, 112, 52, 255]);
    let hedge_normals = image(HEDGE_NORMALS, false, None, [128, 128, 255, 255]);
    // Before any level: the materials are rebuilt for the quality level when the foliage is built.
    let card =
        |texture: Handle<Image>, normals: Option<Handle<Image>>, tint: Color, rough: f32, refl: f32, cut: f32| {
            StandardMaterial {
                base_color: tint,
                base_color_texture: Some(texture),
                normal_map_texture: normals,
                perceptual_roughness: rough,
                reflectance: refl,
                alpha_mode: AlphaMode::Mask(cut),
                // Both faces drawn, but the normal is never flipped: the bent normals light both faces alike.
                double_sided: false,
                cull_mode: None,
                ..default()
            }
        };
    let hedge = materials.add(FoliageMaterial {
        base: card(
            hedge_albedo,
            Some(hedge_normals),
            Color::linear_rgb(h.tint.0, h.tint.1, h.tint.2),
            h.roughness,
            h.reflectance,
            h.alpha_cutoff,
        ),
        extension: FoliageExt { params: hedge_uniform(&data) },
    });
    commands.insert_resource(FoliageAssets { hedge, pending });
}

/// One loaded atlas per frame becomes its finished image: mip chain (alpha coverage kept for the cards) and a
/// clamped, anisotropic sampler. One that cannot load becomes a flat texel.
fn finish_textures(assets: Option<ResMut<FoliageAssets>>, mut images: ResMut<Assets<Image>>, server: Res<AssetServer>) {
    let Some(mut assets) = assets else { return };
    if let Some(i) = assets.pending.iter().position(|p| server.load_state(&p.source).is_failed()) {
        let p = assets.pending.swap_remove(i);
        warn!("foliage texture {:?} did not load; its cards draw flat", p.source.path());
        let format = if p.srgb { TextureFormat::Rgba8UnormSrgb } else { TextureFormat::Rgba8Unorm };
        let texel = Image::new_fill(
            bevy::render::render_resource::Extent3d { width: 1, height: 1, depth_or_array_layers: 1 },
            bevy::render::render_resource::TextureDimension::D2,
            &p.fallback,
            format,
            RenderAssetUsages::RENDER_WORLD,
        );
        let _ = images.insert(&p.done, texel);
        return;
    }
    let Some(i) = assets.pending.iter().position(|p| images.contains(&p.source)) else { return };
    let p = assets.pending.swap_remove(i);
    let Some(mut image) = images.remove(&p.source) else { return };
    image.sampler =
        ImageSampler::Descriptor(ImageSamplerDescriptor { anisotropy_clamp: 8, ..ImageSamplerDescriptor::linear() });
    let format = image.texture_descriptor.format;
    if matches!(format, TextureFormat::Rgba8UnormSrgb | TextureFormat::Rgba8Unorm)
        && image.texture_descriptor.mip_level_count == 1
        && let Some(base) = image.data.take()
    {
        let (w, h) = (image.width() as usize, image.height() as usize);
        let (mut data, levels) = mip_chain(base, w, h, p.srgb);
        if let Some(cutoff) = p.cutoff {
            keep_alpha_coverage(&mut data, w, h, levels, cutoff);
        }
        image.data = Some(data);
        image.texture_descriptor.mip_level_count = levels;
    }
    if let Err(e) = images.insert(&p.done, image) {
        warn!("cannot finish a foliage texture: {e:?}");
    }
}

/// Share of texels whose alpha reaches `cutoff` (alpha scaled by `scale`).
fn coverage(alpha: impl Iterator<Item = u8>, cutoff: f32, scale: f32) -> f32 {
    let (mut n, mut hit) = (0usize, 0usize);
    let limit = cutoff * 255.0;
    for a in alpha {
        n += 1;
        if a as f32 * scale >= limit {
            hit += 1;
        }
    }
    if n == 0 { 0.0 } else { hit as f32 / n as f32 }
}

/// Scale each mip level's alpha so the share of texels passing the alpha test matches the full-size image
/// (box-filtered alpha drops below the cutoff, and alpha-tested cards would thin out and vanish with distance).
pub fn keep_alpha_coverage(data: &mut [u8], w: usize, h: usize, levels: u32, cutoff: f32) {
    let base_n = w * h;
    let target = coverage(data[..base_n * 4].iter().skip(3).step_by(4).copied(), cutoff, 1.0);
    let (mut lw, mut lh, mut offset) = (w, h, base_n * 4);
    for _ in 1..levels {
        (lw, lh) = ((lw / 2).max(1), (lh / 2).max(1));
        let len = lw * lh * 4;
        let level = &mut data[offset..offset + len];
        let (mut lo, mut hi) = (1.0f32, 4.0f32);
        for _ in 0..12 {
            let mid = 0.5 * (lo + hi);
            if coverage(level.iter().skip(3).step_by(4).copied(), cutoff, mid) < target {
                lo = mid;
            } else {
                hi = mid;
            }
        }
        let scale = 0.5 * (lo + hi);
        for a in level.iter_mut().skip(3).step_by(4) {
            *a = (*a as f32 * scale).round().min(255.0) as u8;
        }
        offset += len;
    }
}

// ---------------------------------------------------------------------------------------------- geometry

/// A box with its top and side edges rounded by `r` (the bottom stays square: hedges stand on the ground).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RoundBox {
    pub min: Vec3,
    pub max: Vec3,
    pub r: f32,
}

impl RoundBox {
    /// The box `min..max` shrunk by `inset` on the top and sides, edges rounded by `radius` (capped so it fits).
    pub fn new(min: Vec3, max: Vec3, inset: f32, radius: f32) -> Self {
        let min = Vec3::new(min.x + inset, min.y, min.z + inset);
        let max = (max - Vec3::splat(inset)).max(min + Vec3::splat(0.02));
        let size = max - min;
        let r = radius.min(size.x * 0.5).min(size.z * 0.5).min(size.y).max(0.0);
        Self { min, max, r }
    }

    /// The box the rounding is measured from; it reaches far down so the bottom is never rounded.
    fn inner(&self) -> (Vec3, Vec3) {
        (Vec3::new(self.min.x + self.r, self.min.y - 1.0e4, self.min.z + self.r), self.max - Vec3::splat(self.r))
    }

    /// Signed distance to the surface (positive outside).
    pub fn sdf(&self, p: Vec3) -> f32 {
        let (lo, hi) = self.inner();
        let d = p - p.clamp(lo, hi);
        if d.length_squared() > 1e-12 { d.length() - self.r } else { -(p - lo).min(hi - p).min_element() - self.r }
    }

    /// The outward normal of the rounded volume at (or near) `p`.
    pub fn normal(&self, p: Vec3) -> Vec3 {
        let (lo, hi) = self.inner();
        let d = p - p.clamp(lo, hi);
        if d.length_squared() > 1e-12 {
            return d.normalize();
        }
        // Inside the inner box: toward the nearest face (never down).
        let to_lo = p - lo;
        let to_hi = hi - p;
        let options = [
            (to_hi.x, Vec3::X),
            (to_lo.x, Vec3::NEG_X),
            (to_hi.y, Vec3::Y),
            (to_hi.z, Vec3::Z),
            (to_lo.z, Vec3::NEG_Z),
        ];
        options.iter().min_by(|a, b| a.0.total_cmp(&b.0)).map_or(Vec3::Y, |o| o.1)
    }

    /// A point on the box's (unrounded) surface moved onto the rounded surface, and the normal there.
    pub fn project(&self, p: Vec3) -> (Vec3, Vec3) {
        let (lo, hi) = self.inner();
        let q = p.clamp(lo, hi);
        let n = self.normal(p);
        (q + n * self.r, n)
    }
}

/// The five faces a hedge shows (not the bottom): outward normal, and the two axes spanning it.
const FACES: [(Vec3, Vec3, Vec3); 5] = [
    (Vec3::X, Vec3::Z, Vec3::Y),
    (Vec3::NEG_X, Vec3::Z, Vec3::Y),
    (Vec3::Z, Vec3::X, Vec3::Y),
    (Vec3::NEG_Z, Vec3::X, Vec3::Y),
    (Vec3::Y, Vec3::X, Vec3::Z),
];

/// A point on a face of the box `min..max`: `u`, `v` in 0..1 along the face's axes.
fn face_point(min: Vec3, max: Vec3, face: (Vec3, Vec3, Vec3), u: f32, v: f32) -> Vec3 {
    let (n, a, b) = face;
    let pick = |axis: Vec3, t: f32| axis * (min.dot(axis) + (max - min).dot(axis) * t);
    let fixed = if n.max_element() > 0.0 { max.dot(n.abs()) } else { min.dot(n.abs()) };
    n.abs() * fixed + pick(a, u) + pick(b, v)
}

fn face_size(min: Vec3, max: Vec3, face: (Vec3, Vec3, Vec3)) -> (f32, f32) {
    let s = max - min;
    (s.dot(face.1), s.dot(face.2))
}

/// Raw vertex arrays of a card mesh.
#[derive(Default)]
pub struct CardMesh {
    pub positions: Vec<[f32; 3]>,
    pub normals: Vec<[f32; 3]>,
    pub tangents: Vec<[f32; 4]>,
    pub uvs: Vec<[f32; 2]>,
    pub colors: Vec<[f32; 4]>,
    pub indices: Vec<u32>,
}

impl CardMesh {
    pub fn cards(&self) -> usize {
        self.positions.len() / 4
    }

    fn into_mesh(self) -> Mesh {
        let mut mesh = Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::RENDER_WORLD)
            .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, self.positions)
            .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, self.normals)
            .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, self.uvs)
            .with_inserted_attribute(Mesh::ATTRIBUTE_COLOR, self.colors)
            .with_inserted_indices(Indices::U32(self.indices));
        if !self.tangents.is_empty() {
            mesh.insert_attribute(Mesh::ATTRIBUTE_TANGENT, self.tangents);
        }
        mesh
    }
}

/// The UV rectangle of atlas cell `i` (top-left, size), inset a little.
fn cell_uv(i: u32, cells: (u32, u32)) -> (Vec2, Vec2) {
    let size = Vec2::new(1.0 / cells.0 as f32, 1.0 / cells.1 as f32);
    let corner = Vec2::new((i % cells.0) as f32, ((i / cells.0) % cells.1) as f32) * size;
    (corner + size * CELL_INSET, size * (1.0 - 2.0 * CELL_INSET))
}

/// Smoothstep.
fn smooth(e0: f32, e1: f32, x: f32) -> f32 {
    let t = ((x - e0) / (e1 - e0)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

/// The leaf-card shell of one hedge box `min..max` (world), positions relative to `origin`. `visible(p, n)` says
/// whether a card at `p` facing `n` can be seen (not buried in a wall, not facing out of the map).
pub fn hedge_shell(
    min: Vec3,
    max: Vec3,
    origin: Vec3,
    h: &HedgeData,
    density: f32,
    seed: u64,
    visible: impl Fn(Vec3, Vec3) -> bool,
) -> CardMesh {
    let mut out = CardMesh::default();
    if density <= 0.0 {
        return out;
    }
    let shell = RoundBox::new(min, max, h.shell_inset, h.shell_radius);
    let thickness = (max - min).x.min((max - min).z);
    let soft = RoundBox::new(min, max, 0.0, h.normal_radius.min(thickness * 0.5));
    let spacing = 1.0 / density.sqrt();
    let tilt = h.tilt_deg.to_radians();
    let mut rng = SplitMix::from_parts(&[seed, 0x0048_4544_4745]);
    for face in FACES {
        let (su, sv) = face_size(min, max, face);
        let (nu, nv) = ((su / spacing).round().max(1.0) as u32, (sv / spacing).round().max(1.0) as u32);
        for i in 0..nu {
            for j in 0..nv {
                let u = (i as f32 + rng.next_f32()) / nu as f32;
                let v = (j as f32 + rng.next_f32()) / nv as f32;
                let (centre, n) = shell.project(face_point(min, max, face, u, v));
                // Draw every random number first, so skipping a card does not shift the others.
                let r: [f32; 10] = std::array::from_fn(|_| rng.next_f32());
                if !visible(centre, n) {
                    continue;
                }
                // Card frame: up along the surface (world up projected; random on the top), a random roll about
                // the normal, then a tilt away from it about a random axis in the surface.
                let reference = if n.y.abs() > 0.9 { Vec3::new(r[0] - 0.5, 0.0, r[1] - 0.5) } else { Vec3::Y };
                let up0 =
                    (reference - n * reference.dot(n)).try_normalize().unwrap_or_else(|| n.any_orthonormal_vector());
                let roll = if n.y > 0.9 { std::f32::consts::PI } else { h.roll_deg.to_radians() };
                let up_rolled = Quat::from_axis_angle(n, (r[2] * 2.0 - 1.0) * roll) * up0;
                let tilt_axis = Quat::from_axis_angle(n, r[3] * std::f32::consts::TAU) * up_rolled;
                let tilt_q = Quat::from_axis_angle(tilt_axis, r[4] * tilt);
                let card_n = tilt_q * n;
                let up = (tilt_q * up_rolled).normalize();
                let right = up.cross(card_n).normalize();
                let size = h.card_size.0 + (h.card_size.1 - h.card_size.0) * r[5];
                let centre = centre + n * (h.poke.0 + (h.poke.1 - h.poke.0) * r[6]);
                let variant = (r[7] * (HEDGE_CELLS.0 * HEDGE_CELLS.1) as f32) as u32;
                let flip = r[8] < 0.5;
                let value = 1.0 + (r[9] * 2.0 - 1.0) * h.value_jitter;
                let hue = ((r[9] * 7.31).fract() * 2.0 - 1.0) * h.hue_jitter;
                let tint = Vec3::new(1.0 + hue, 1.0, 1.0 - hue) * value;
                push_hedge_card(
                    &mut out,
                    centre,
                    right,
                    up,
                    size,
                    variant,
                    flip,
                    tint,
                    (min, origin),
                    &shell,
                    &soft,
                    h,
                );
            }
        }
    }
    out
}

/// One hedge card: four corners with bent normals, tangents, AO and sway weight.
#[allow(clippy::too_many_arguments)]
fn push_hedge_card(
    out: &mut CardMesh,
    centre: Vec3,
    right: Vec3,
    up: Vec3,
    size: f32,
    variant: u32,
    flip: bool,
    tint: Vec3,
    (min, origin): (Vec3, Vec3),
    shell: &RoundBox,
    soft: &RoundBox,
    h: &HedgeData,
) {
    let base = out.positions.len() as u32;
    let card_n = right.cross(up);
    let (uv0, uv_size) = cell_uv(variant, HEDGE_CELLS);
    let half = size * 0.5;
    // The card is the front of a little sphere of leaves.
    let clump = centre - card_n * half;
    let volume_mix = 1.0 - h.normal_card_mix - h.normal_clump_mix;
    // Corners: top-left, top-right, bottom-right, bottom-left (image top = card up).
    for (sx, sy) in [(-1.0f32, 1.0f32), (1.0, 1.0), (1.0, -1.0), (-1.0, -1.0)] {
        let p = centre + right * (sx * half) + up * (sy * half);
        let sphere = (p - clump).normalize_or_zero();
        let bent = (soft.normal(p) * volume_mix + card_n * h.normal_card_mix + sphere * h.normal_clump_mix).normalize();
        // The tangent runs along dP/du: `right`, or against it when the card is mirrored. Bevy's bitangent
        // (w * N x T) points to the image top, which is the card's up (V grows down the card).
        let du = if flip { -right } else { right };
        let t = (du - bent * du.dot(bent)).normalize_or_zero();
        let w = if bent.cross(t).dot(up) >= 0.0 { 1.0 } else { -1.0 };
        let u = if (sx > 0.0) != flip { uv0.x + uv_size.x } else { uv0.x };
        let v = if sy > 0.0 { uv0.y } else { uv0.y + uv_size.y };
        let depth = shell.sdf(p);
        let ao = h.ao_min + (1.0 - h.ao_min) * smooth(-h.ao_depth, 0.08, depth);
        let ground = h.ground_ao + (1.0 - h.ground_ao) * smooth(0.0, h.ground_ao_height, p.y - min.y);
        let under = h.clump_shade + (1.0 - h.clump_shade) * smooth(-0.75, 0.6, sphere.y);
        let c = tint * ao * ground * under;
        let sway = (0.25 + (depth + 0.08) / 0.3).clamp(0.0, 1.0);
        out.positions.push((p - origin).to_array());
        out.normals.push(bent.to_array());
        out.tangents.push([t.x, t.y, t.z, w]);
        out.uvs.push([u, v]);
        out.colors.push([c.x, c.y, c.z, sway]);
    }
    out.indices.extend_from_slice(&[base, base + 1, base + 2, base, base + 2, base + 3]);
}

/// The opaque core of a hedge: a rounded box (no bottom) with world-space UVs in metres. Its own normals (not the
/// cards' softer ones): the core casts and receives shadows, and bent normals would make it shadow itself.
pub fn hedge_core(min: Vec3, max: Vec3, origin: Vec3, h: &HedgeData) -> Mesh {
    let core = RoundBox::new(min, max, h.core_inset, h.core_radius);
    let mut positions = Vec::new();
    let mut normals = Vec::new();
    let mut uvs = Vec::new();
    let mut indices = Vec::new();
    for face in FACES {
        let (n, a, b) = face;
        let samples = |axis: Vec3, rounded_lo: bool| {
            axis_samples(core.min.dot(axis), core.max.dot(axis), if rounded_lo { core.r } else { 0.0 }, core.r, 1.0)
        };
        // The vertical axis is never rounded at the bottom.
        let us = samples(a, a != Vec3::Y);
        let vs = samples(b, b != Vec3::Y);
        let base = positions.len() as u32;
        for &v in &vs {
            for &u in &us {
                let fixed = if n.max_element() > 0.0 { core.max.dot(n.abs()) } else { core.min.dot(n.abs()) };
                let p0 = n.abs() * fixed + a * u + b * v;
                let (p, normal) = core.project(p0);
                positions.push((p - origin).to_array());
                normals.push(normal.to_array());
                uvs.push(if n.y.abs() > 0.5 { [p.x, p.z] } else { [p.dot(a), -p.y] });
            }
        }
        let row = us.len() as u32;
        // Wind each quad so it faces out of the box.
        let flip = a.cross(b).dot(n) < 0.0;
        for j in 0..vs.len() as u32 - 1 {
            for i in 0..row - 1 {
                let (k0, k1, k2, k3) = (
                    base + j * row + i,
                    base + j * row + i + 1,
                    base + (j + 1) * row + i + 1,
                    base + (j + 1) * row + i,
                );
                if flip {
                    indices.extend_from_slice(&[k0, k2, k1, k0, k3, k2]);
                } else {
                    indices.extend_from_slice(&[k0, k1, k2, k0, k2, k3]);
                }
            }
        }
    }
    Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::RENDER_WORLD)
        .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, positions)
        .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, normals)
        .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, uvs)
        .with_inserted_indices(Indices::U32(indices))
}

/// Sample positions along one axis of a rounded box face: denser across the rounded edges (so the arc is
/// smooth), about every `step` metres across the flat middle.
pub fn axis_samples(lo: f32, hi: f32, r_lo: f32, r_hi: f32, step: f32) -> Vec<f32> {
    // Points on the flat face that project to 0°, 15°, 30° and 45° of the edge arc.
    let arc = [0.0f32, 15.0, 30.0, 45.0].map(|d| d.to_radians().tan());
    let mut out = vec![lo];
    if r_lo > 0.0 {
        for t in arc.iter().rev().skip(1) {
            out.push(lo + r_lo - r_lo * t);
        }
    }
    let (a, b) = (lo + r_lo, hi - r_hi);
    let n = ((b - a) / step).ceil().max(1.0) as usize;
    for k in 1..n {
        out.push(a + (b - a) * k as f32 / n as f32);
    }
    if r_hi > 0.0 {
        for t in arc.iter() {
            out.push(hi - r_hi + r_hi * t);
        }
    } else {
        out.push(hi);
    }
    out.sort_by(f32::total_cmp);
    out.dedup_by(|x, y| (*x - *y).abs() < 1e-4);
    out
}

/// The playable area (x/z): the spawn points' bounds grown by `margin`.
pub fn play_area(level: &Level, margin: f32) -> Rect {
    let mut r = Rect { min: Vec2::splat(f32::MAX), max: Vec2::splat(f32::MIN) };
    for s in &level.spawns {
        let p = Vec2::new(s.pos.x, s.pos.z);
        r.min = r.min.min(p);
        r.max = r.max.max(p);
    }
    if r.min.x > r.max.x {
        return Rect { min: Vec2::splat(-1e4), max: Vec2::splat(1e4) };
    }
    Rect { min: r.min - Vec2::splat(margin), max: r.max + Vec2::splat(margin) }
}

/// Whether a surface at `p` facing `n` can face any point of the play area (x/z) at a player's heights.
pub fn faces_play_area(p: Vec3, n: Vec3, play: Rect, max_eye: f32) -> bool {
    let xs = [play.min.x, play.max.x];
    let zs = [play.min.y, play.max.y];
    let ys = [0.0, max_eye];
    xs.iter().any(|&x| ys.iter().any(|&y| zs.iter().any(|&z| (Vec3::new(x, y, z) - p).dot(n) > 0.0)))
}

// ---------------------------------------------------------------------------------------------- systems

/// What the foliage is built for (level and quality level); `hedges` = the hedge boxes are replaced.
#[derive(Resource, Default)]
struct FoliageState {
    built: Option<(String, Option<usize>)>,
    hedges: bool,
}

#[derive(Component)]
struct FoliageRoot;

/// The highest eye a player reaches on Showhome (the pylon pad perch, z 4 + 1.6 m) plus a margin.
const MAX_EYE: f32 = 7.0;

/// Build (or rebuild, when the preset changes) the hedge shells and cores and the lawn chunks.
fn build_foliage(
    mut commands: Commands,
    level: Option<Res<CurrentLevel>>,
    settings: Option<Res<Settings>>,
    data: Res<FoliageData>,
    lib: Option<Res<ShowhomeMaterials>>,
    assets: Option<Res<FoliageAssets>>,
    mut state: ResMut<FoliageState>,
    roots: Query<Entity, With<FoliageRoot>>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut std_materials: ResMut<Assets<StandardMaterial>>,
    mut materials: ResMut<Assets<FoliageMaterial>>,
) {
    let (Some(level), Some(assets)) = (level, assets) else { return };
    let preset = settings.map_or(Preset::High, |s| s.video.preset);
    let env = std::env::var("VETF_FOLIAGE").ok();
    let q = quality(preset, env.as_deref());
    let want = (level.name.clone(), q);
    if !roots.is_empty() && state.built.as_ref() == Some(&want) {
        return;
    }
    for e in &roots {
        commands.entity(e).despawn();
    }
    let root = commands
        .spawn((
            FoliageRoot,
            Name::new("Foliage"),
            Transform::default(),
            Visibility::default(),
            DespawnOnExit(AppState::InGame),
        ))
        .id();
    state.built = Some(want);
    state.hedges = false;
    let Some(q) = q.filter(|_| level.name.eq_ignore_ascii_case("showhome")) else { return };
    let t0 = std::time::Instant::now();
    if let Some(mut m) = materials.get_mut(&assets.hedge) {
        m.extension.params = FoliageUniform { time: m.extension.params.time, ..hedge_uniform(&data) };
    }
    let play = play_area(&level, 2.0);
    let solids: Vec<&Brush> = level
        .world
        .brushes
        .iter()
        .filter(|b| b.kind == BrushKind::Solid && b.look != Look::Invisible && b.ramp.is_none())
        .collect();

    // Hedges.
    let h = &data.hedge;
    let density = h.density[q];
    let mut cards = 0;
    let mut tris = 0;
    let mut draws = 0;
    if density > 0.0 {
        let core_material =
            lib.as_ref().and_then(|l| l.get(Look::Hedge)).and_then(|m| std_materials.get(&m).cloned()).unwrap_or_else(
                || StandardMaterial { base_color: crate::render::look_color(Look::Hedge).0, ..default() },
            );
        let core_material = std_materials.add(StandardMaterial {
            base_color: Color::linear_rgb(h.core_tint.0, h.core_tint.1, h.core_tint.2),
            perceptual_roughness: 0.95,
            ..core_material
        });
        for (k, hedge) in
            level.world.brushes.iter().enumerate().filter(|(_, b)| b.look == Look::Hedge && b.ramp.is_none())
        {
            let centre = (hedge.min + hedge.max) * 0.5;
            let others: Vec<&&Brush> = solids.iter().filter(|b| !std::ptr::eq(**b, hedge)).collect();
            let visible = |p: Vec3, n: Vec3| {
                let probe = p + n * 0.15;
                faces_play_area(p, n, play, MAX_EYE)
                    && !others.iter().any(|b| probe.cmpgt(b.min).all() && probe.cmplt(b.max).all())
            };
            let shell = hedge_shell(hedge.min, hedge.max, centre, h, density, k as u64, visible);
            cards += shell.cards();
            tris += shell.indices.len() / 3;
            let core = hedge_core(hedge.min, hedge.max, centre, h);
            tris += core.indices().map_or(0, |i| i.len() / 3);
            draws += 2;
            commands.spawn((
                Name::new("Hedge core"),
                Mesh3d(meshes.add(core)),
                MeshMaterial3d(core_material.clone()),
                Transform::from_translation(centre),
                ChildOf(root),
            ));
            commands.spawn((
                Name::new("Hedge leaves"),
                Mesh3d(meshes.add(shell.into_mesh())),
                MeshMaterial3d(assets.hedge.clone()),
                Transform::from_translation(centre),
                NotShadowCaster,
                ChildOf(root),
            ));
        }
        state.hedges = true;
    }
    info!(
        "foliage ({}): {cards} hedge cards, {draws} hedge meshes, {tris} triangles, built in {:.0} ms",
        Preset::from_index(q).label(),
        t0.elapsed().as_secs_f32() * 1000.0
    );
}

/// The textured hedge boxes are hidden while the leaf shells stand in for them (shown again on LOW).
fn show_hedge_boxes(
    state: Res<FoliageState>,
    lib: Option<Res<ShowhomeMaterials>>,
    added: Query<(), Added<MeshMaterial3d<StandardMaterial>>>,
    mut boxes: Query<(&MeshMaterial3d<StandardMaterial>, &mut Visibility)>,
) {
    if !state.is_changed() && added.is_empty() {
        return;
    }
    let Some(hedge) = lib.and_then(|l| l.get(Look::Hedge)) else { return };
    let want = if state.hedges { Visibility::Hidden } else { Visibility::Inherited };
    for (m, mut v) in &mut boxes {
        if m.0 == hedge {
            v.set_if_neq(want);
        }
    }
}

/// The shader's clock (this frame and the last, for motion vectors).
fn tick_wind(time: Res<Time>, assets: Option<Res<FoliageAssets>>, mut materials: ResMut<Assets<FoliageMaterial>>) {
    let Some(assets) = assets else { return };
    let t = time.elapsed_secs_wrapped();
    if let Some(mut m) = materials.get_mut(&assets.hedge) {
        let last = m.extension.params.time.x;
        m.extension.params.time = Vec4::new(t, last, 0.0, 0.0);
    }
}

/// Logs the smoothed GPU time of every render pass, and the frame time (`VETF_GPU_PROFILE`).
fn log_gpu_passes(store: Res<bevy::diagnostic::DiagnosticsStore>, time: Res<Time>, mut next: Local<f32>) {
    if time.elapsed_secs() < *next {
        return;
    }
    *next = time.elapsed_secs() + 2.0;
    let mut parts: Vec<String> = store
        .iter()
        .filter(|d| d.path().as_str().ends_with("elapsed_gpu"))
        .filter_map(|d| Some(format!("{} {:.3}", d.path().as_str(), d.smoothed()?)))
        .collect();
    parts.sort();
    let frame = store
        .get(&bevy::diagnostic::FrameTimeDiagnosticsPlugin::FRAME_TIME)
        .and_then(|d| d.smoothed())
        .unwrap_or_default();
    info!("gpu profile: frame {frame:.2} ms | {}", parts.join(" | "));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_data_file_parses_and_low_is_off() {
        let d = embedded();
        // The copy in the data folder is the same file.
        let on_disk = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../../assets/data/foliage.ron"))
            .expect("foliage.ron");
        assert_eq!(ron::from_str::<FoliageData>(&on_disk).expect("foliage.ron parses"), d);
        assert_eq!(d.hedge.density[0], 0.0, "LOW keeps the plain hedge boxes");
        for q in 1..4 {
            assert!(d.hedge.density[q] > 0.0);
            assert!(d.hedge.density[q] >= d.hedge.density[q - 1]);
        }
    }

    #[test]
    fn grass_presets_step_up_from_off() {
        let g = embedded().grass;
        let (l, t) = (&g.lawn, &g.tufts);
        // LOW: the flat lawn only. MEDIUM: fewer layers and tufts. HIGH and ULTRA: the full lawn.
        assert_eq!(l.layers[0], 0, "LOW draws no lawn shells");
        assert_eq!(t.density[0], 0.0, "LOW draws no tufts");
        assert!(l.layers[1] >= 3 && l.layers[1] < l.layers[2] && l.layers[2] <= l.layers[3]);
        assert!(t.density[1] > 0.0 && t.density[1] < t.density[2] && t.density[2] <= t.density[3]);
        for q in 1..4 {
            assert!(l.fade_start[q] < l.fade_end[q] && t.fade_start[q] < t.fade_end[q]);
            assert!(l.fade_end[q] >= l.fade_end[q - 1] && t.fade_end[q] >= t.fade_end[q - 1]);
            // Tufts are bigger, so they are drawn further than the lawn fuzz.
            assert!(t.fade_end[q] >= l.fade_end[q]);
        }
        // A mown lawn is 3-5 cm; tufts 10-25 cm, never enough to hide a crouched player.
        assert!((0.03..=0.05).contains(&l.height), "{}", l.height);
        assert!(t.height.0 >= 0.1 - 1e-6 && t.height.1 <= 0.25 + 1e-6);
        assert!(t.fade_end[3] <= 40.0 && l.fade_end[3] <= 30.0);
        assert!(l.root_shade < 1.0 && l.tip_lift >= 1.0, "darker toward the roots");
        assert!(l.dirt_thin.0 < l.dirt_thin.1 && t.dirt_limit.0 < t.dirt_limit.1);
        assert!(t.blades.0 >= 2 && t.blades.0 <= t.blades.1);
    }

    #[test]
    fn the_env_override_picks_the_quality() {
        assert_eq!(quality(Preset::High, None), Some(2));
        assert_eq!(quality(Preset::Low, None), Some(0));
        assert_eq!(quality(Preset::High, Some("off")), None);
        assert_eq!(quality(Preset::High, Some("Ultra")), Some(3));
        assert_eq!(quality(Preset::Medium, Some("")), Some(1));
        assert_eq!(quality(Preset::Medium, Some("nonsense")), Some(1));
    }

    #[test]
    fn rounded_box_rounds_the_top_but_not_the_bottom() {
        let rb = RoundBox::new(Vec3::ZERO, Vec3::new(1.0, 2.0, 4.0), 0.1, 0.3);
        assert!((rb.min - Vec3::new(0.1, 0.0, 0.1)).length() < 1e-6, "no inset at the bottom");
        assert!((rb.max - Vec3::new(0.9, 1.9, 3.9)).length() < 1e-6);
        // Face centres are on the surface with the face normal.
        assert!(rb.sdf(Vec3::new(0.9, 1.0, 2.0)).abs() < 1e-5);
        assert!((rb.normal(Vec3::new(0.95, 1.0, 2.0)) - Vec3::X).length() < 1e-5);
        // The top edge is rounded: the box corner is outside, its normal diagonal.
        assert!(rb.sdf(Vec3::new(0.9, 1.9, 2.0)) > 0.05);
        let n = rb.normal(Vec3::new(0.9, 1.9, 2.0));
        assert!((n - Vec3::new(1.0, 1.0, 0.0).normalize()).length() < 1e-4);
        // The bottom edge is square (no rounding near the ground).
        assert!(rb.sdf(Vec3::new(0.9, 0.0, 2.0)).abs() < 1e-5);
        assert!((rb.normal(Vec3::new(0.95, 0.0, 2.0)) - Vec3::X).length() < 1e-5);
        // A projected edge point lands on the rounded surface.
        let (p, n) = rb.project(Vec3::new(0.9, 1.9, 2.0));
        assert!(rb.sdf(p).abs() < 1e-4 && n.y > 0.5 && n.x > 0.5);
        // Inside: negative distance.
        assert!(rb.sdf(Vec3::new(0.5, 1.0, 2.0)) < -0.3);
        // A thin hedge caps the radius at half its thickness.
        assert!(RoundBox::new(Vec3::ZERO, Vec3::new(0.4, 2.0, 4.0), 0.0, 1.0).r <= 0.2 + 1e-6);
    }

    fn test_hedge() -> HedgeData {
        embedded().hedge
    }

    #[test]
    fn hedge_cards_cover_the_faces_and_poke_out_a_little() {
        let h = test_hedge();
        let (min, max) = (Vec3::new(0.0, 0.0, 0.0), Vec3::new(1.0, 2.0, 5.0));
        let centre = (min + max) * 0.5;
        let shell = hedge_shell(min, max, centre, &h, 20.0, 1, |_, _| true);
        // About density x shown area (sides, ends and top; no bottom).
        let area = 2.0 * (5.0 * 2.0) + 2.0 * (1.0 * 2.0) + 5.0;
        let n = shell.cards() as f32;
        assert!((n - 20.0 * area).abs() < 0.15 * 20.0 * area, "{n} cards for {area} m²");
        assert_eq!(shell.indices.len(), shell.cards() * 6);
        let rb = RoundBox::new(min, max, 0.0, 0.0);
        let mut outside = 0.0f32;
        for p in &shell.positions {
            let p = Vec3::from(*p) + centre;
            outside = outside.max(rb.sdf(p));
        }
        // Card corners stick out of the box by roughly 8-20 cm, never much more.
        assert!(outside > 0.08 && outside < 0.3, "{outside}");
        // Bent normals point out of the hedge; tangents are unit and orthogonal to them; AO within range.
        for ((p, n), (t, c)) in shell.positions.iter().zip(&shell.normals).zip(shell.tangents.iter().zip(&shell.colors))
        {
            let (p, n, t) = (Vec3::from(*p), Vec3::from(*n), Vec3::new(t[0], t[1], t[2]));
            assert!((n.length() - 1.0).abs() < 1e-3 && (t.length() - 1.0).abs() < 1e-3);
            assert!(n.dot(t).abs() < 1e-3);
            let out = p.normalize_or_zero();
            assert!(n.dot(out) > -0.2, "a bent normal points into the hedge");
            assert!(c[0] >= h.ao_min * h.ground_ao * h.clump_shade * 0.8 && c[0] <= 1.2);
            assert!((0.0..=1.0).contains(&c[3]));
        }
        // Invisible spots get no cards.
        let none = hedge_shell(min, max, centre, &h, 20.0, 1, |_, _| false);
        assert_eq!(none.cards(), 0);
        // The same seed builds the same hedge.
        let again = hedge_shell(min, max, centre, &h, 20.0, 1, |_, _| true);
        assert_eq!(again.positions, shell.positions);
    }

    #[test]
    fn hedge_core_is_inside_the_box_and_closed_at_the_edges() {
        let h = test_hedge();
        let (min, max) = (Vec3::new(2.0, 0.0, -6.0), Vec3::new(3.0, 3.0, 0.0));
        let centre = (min + max) * 0.5;
        let mesh = hedge_core(min, max, centre, &h);
        let pos = mesh.attribute(Mesh::ATTRIBUTE_POSITION).and_then(|a| a.as_float3()).unwrap();
        let core = RoundBox::new(min, max, h.core_inset, h.core_radius);
        for p in pos {
            let p = Vec3::from(*p) + centre;
            assert!(core.sdf(p).abs() < 1e-3, "every vertex on the rounded core");
            assert!(p.cmpge(min - 1e-4).all() && p.cmple(max + 1e-4).all());
        }
        // Faces meet: every vertex on a top edge arc is shared by two faces (same position twice).
        let mut on_arc = 0;
        for p in pos {
            let q = Vec3::from(*p);
            if pos.iter().filter(|o| (Vec3::from(**o) - q).length() < 1e-4).count() >= 2 {
                on_arc += 1;
            }
        }
        assert!(on_arc > 8);
    }

    #[test]
    fn axis_samples_bunch_up_over_the_rounded_edges() {
        let s = axis_samples(0.0, 4.0, 0.3, 0.3, 1.0);
        assert_eq!(s.first(), Some(&0.0));
        assert_eq!(s.last(), Some(&4.0));
        assert!(s.windows(2).all(|w| w[1] > w[0]));
        assert!(s.iter().filter(|&&x| x < 0.3).count() >= 3);
        let flat_bottom = axis_samples(0.0, 2.0, 0.0, 0.3, 1.0);
        assert!(flat_bottom.iter().filter(|&&x| x < 0.3).count() == 1);
    }

    #[test]
    fn faces_out_of_the_map_are_skipped() {
        let play = Rect { min: Vec2::new(0.5, -47.5), max: Vec2::new(71.5, -0.5) };
        // The boundary hedge's outer face (x = 0, facing -x) faces nothing a player can stand on.
        assert!(!faces_play_area(Vec3::new(0.0, 1.5, -20.0), Vec3::NEG_X, play, MAX_EYE));
        assert!(faces_play_area(Vec3::new(1.0, 1.5, -20.0), Vec3::X, play, MAX_EYE));
        // Its top can be seen from the upper floors.
        assert!(faces_play_area(Vec3::new(0.2, 3.0, -20.0), Vec3::Y, play, MAX_EYE));
        // Never from below the ground.
        assert!(!faces_play_area(Vec3::new(5.0, 0.0, -20.0), Vec3::NEG_Y, play, MAX_EYE));
    }

    #[test]
    fn mips_keep_the_alpha_coverage() {
        // 8x8: a disc of opaque texels in transparent ones, with a soft edge.
        let (w, h) = (8usize, 8usize);
        let mut base = Vec::new();
        for y in 0..h {
            for x in 0..w {
                let d = ((x as f32 - 3.5).powi(2) + (y as f32 - 3.5).powi(2)).sqrt();
                let a = (255.0 * (1.0 - (d - 2.0).clamp(0.0, 1.0))) as u8;
                base.extend_from_slice(&[100, 120, 50, a]);
            }
        }
        let target = coverage(base.iter().skip(3).step_by(4).copied(), 0.5, 1.0);
        let (mut data, levels) = mip_chain(base, w, h, true);
        let before = coverage(data[256..256 + 64].iter().skip(3).step_by(4).copied(), 0.5, 1.0);
        keep_alpha_coverage(&mut data, w, h, levels, 0.5);
        let after = coverage(data[256..256 + 64].iter().skip(3).step_by(4).copied(), 0.5, 1.0);
        assert!((after - target).abs() <= (before - target).abs() + 1e-6);
        assert!((after - target).abs() < 0.2, "{after} vs {target}");
    }

    #[test]
    fn wind_points_where_the_data_says() {
        let w = WindData { direction_deg: 90.0, frequency: 1.0, wavelength: 5.0, gust: 0.0 };
        assert!((w.dir() - Vec3::NEG_Z).length() < 1e-6, "90° = north = -Z in Bevy");
        let d = embedded();
        let hu = hedge_uniform(&d);
        assert_eq!(hu.wind_dir.w, 0.0);
        assert!((hu.wind_dir.truncate() - d.wind.dir()).length() < 1e-6);
    }
}
