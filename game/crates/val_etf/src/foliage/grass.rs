//! Lawn grass on Showhome: a mown lawn over the art kit's lawn surfaces, and taller tufts at its edges.
//!
//! **Mown lawn** (shell texturing): the kit's lawn triangles (`ground.glb`, material `M_GND_Grass`) are cut into
//! chunks and drawn once per layer (a [`MeshTag`] per layer, so the layers of a chunk are one instanced draw).
//! The shader lifts each copy by its layer's height (3-5 cm in all) and keeps only the fragments inside a
//! strand, so the lawn reads as dense, very short fuzz. Layer 0 is a dark thatch, so the gaps between strands
//! are darker toward the roots. Colours come from the lawn's own ground texture; strands thin out where the
//! ground blend masks show worn dirt, gravel or mud, and with distance, where the colour also settles back to
//! the plain ground (no line where the grass ends). Chunks past the fade distance are not drawn.
//!
//! **Tufts** (10-25 cm): a few blade strips around a root, only where real lawns grow them: along the lawn's
//! edges (kerbs, edging, paths, beds) and the foot of anything standing on it (fences, walls, hedges, houses),
//! in irregular noise patches, thinning where the ground masks show worn dirt. They shrink into the lawn with
//! distance. One mesh per chunk.
//!
//! Neither casts shadows. Both sway in the wind (`assets/shaders/grass.wgsl`). Every number is in
//! `assets/data/foliage.ron` (`grass`), per VIDEO quality preset: LOW draws neither.
//!
//! `VETF_GRASS=off|lawn|tufts` keeps only that part (GPU cost measurements); `VETF_FOLIAGE` sets the level.

use super::{FoliageData, WindData, quality, smooth};
use crate::AppState;
use crate::config::CurrentLevel;
use crate::render::ViewCamera;
use crate::settings::{Preset, Settings};
use crate::showhome_ground::ShowhomeGroundMaterial;
use crate::showhome_kit::ShowhomeKitMesh;
use bevy::asset::RenderAssetUsages;
use bevy::camera::primitives::Aabb;
use bevy::gltf::GltfMaterialName;
use bevy::light::NotShadowCaster;
use bevy::mesh::{Indices, MeshTag, PrimitiveTopology, VertexAttributeValues};
use bevy::pbr::{ExtendedMaterial, MaterialExtension, MaterialPlugin};
use bevy::prelude::*;
use bevy::render::render_resource::{AsBindGroup, ShaderType};
use bevy::shader::ShaderRef;
use serde::Deserialize;
use std::collections::HashMap;
use vetf_sim::level::Level;
use vetf_sim::movement::collision::{BrushKind, Look};
use vetf_sim::rng::SplitMix;

const SHADER: &str = "shaders/grass.wgsl";
/// The kit's lawn material (ground.glb); `.001`-style suffixes are the same material.
const LAWN_MATERIAL: &str = "M_GND_Grass";

pub(super) fn plugin(app: &mut App) {
    app.add_plugins(MaterialPlugin::<GrassMaterial>::default())
        .init_resource::<GrassState>()
        .add_systems(Update, (build_grass, cull_grass, tick_grass).chain().run_if(in_state(AppState::InGame)))
        // The grass is despawned with the match; build it again next time.
        .add_systems(OnExit(AppState::InGame), |mut state: ResMut<GrassState>| *state = GrassState::default());
}

// ---------------------------------------------------------------------------------------------- data

/// `grass` in foliage.ron. Lists of four follow the quality preset LOW, MEDIUM, HIGH, ULTRA.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct GrassData {
    pub lawn: LawnData,
    pub tufts: TuftData,
}

/// The mown lawn (shells).
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct LawnData {
    /// Shell layers, the thatch included (0 = no lawn shells).
    pub layers: [u32; 4],
    /// Height of the top layer (m).
    pub height: f32,
    /// Strand cell size (m), root radius (share of a cell), shortest strand (share of `height`), tip lean
    /// (share of a cell).
    pub spacing: f32,
    pub radius: f32,
    pub shortest: f32,
    pub lean: f32,
    /// Strands thin out from fade_start to fade_end (m from the camera); the colour settles to the ground.
    pub fade_start: [f32; 4],
    pub fade_end: [f32; 4],
    pub root_shade: f32,
    pub tip_lift: f32,
    pub tip_tint: (f32, f32, f32),
    pub value_jitter: f32,
    pub patch_strength: f32,
    pub patch_scale: f32,
    pub dry_tint: (f32, f32, f32),
    pub lush_tint: (f32, f32, f32),
    /// Ground blend mask (worn dirt, gravel, mud) range over which strands thin out.
    pub dirt_thin: (f32, f32),
    pub chunk: f32,
    /// Tip sway (m) and the gust sheen over the lawn (share of brightness).
    pub wind_sway: f32,
    pub wind_sheen: f32,
    pub sway_speed: f32,
}

/// The taller tufts at the lawn's edges.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct TuftData {
    /// Tufts per square metre right at an edge, inside a patch (0 = none).
    pub density: [f32; 4],
    /// They grow up to this far from an edge (m), most right at it.
    pub band: f32,
    pub height: (f32, f32),
    pub blades: (u32, u32),
    pub blade_width: f32,
    /// Blade roots spread this far around the tuft's centre (m).
    pub spread: f32,
    pub lean_deg: (f32, f32),
    /// Noise patches along the edges: size (m) and the share of the lawn's outline they cover, and of the foot
    /// of fences, walls and hedges.
    pub patch_scale: f32,
    pub patch_cover: f32,
    pub foot_cover: f32,
    /// Ground blend mask range over which tufts give out (worn dirt, gravel, mud).
    pub dirt_limit: (f32, f32),
    pub fade_start: [f32; 4],
    pub fade_end: [f32; 4],
    pub root_shade: f32,
    pub tip_lift: f32,
    pub tip_tint: (f32, f32, f32),
    pub value_jitter: f32,
    pub wind_amplitude: f32,
    pub sway_speed: f32,
    pub chunk: f32,
    /// Tufts grow on lawns up to this far outside the play area (m).
    pub reach: f32,
}

// ---------------------------------------------------------------------------------------------- material

pub type GrassMaterial = ExtendedMaterial<StandardMaterial, GrassExt>;

/// The shader's `Grass` uniform (see grass.wgsl for each lane).
#[derive(Clone, Copy, Debug, Default, PartialEq, ShaderType, Reflect)]
pub struct GrassUniform {
    pub wind_dir: Vec4,
    pub wind: Vec4,
    pub time: Vec4,
    pub shape: Vec4,
    pub fade: Vec4,
    pub shade: Vec4,
    pub tip: Vec4,
    pub ground_tint: Vec4,
    pub ground: Vec4,
    pub dry: Vec4,
    pub lush: Vec4,
    pub layers: UVec4,
}

#[derive(Asset, AsBindGroup, Reflect, Debug, Clone)]
pub struct GrassExt {
    #[uniform(100)]
    pub params: GrassUniform,
    #[texture(101, dimension = "2d_array")]
    #[sampler(102)]
    pub albedo: Handle<Image>,
    #[texture(103, dimension = "2d_array")]
    pub normal: Handle<Image>,
    #[texture(104, dimension = "2d_array")]
    pub orm: Handle<Image>,
    #[texture(105, dimension = "2d_array", sample_type = "u_int")]
    pub height: Handle<Image>,
}

impl MaterialExtension for GrassExt {
    fn vertex_shader() -> ShaderRef {
        SHADER.into()
    }
    fn fragment_shader() -> ShaderRef {
        SHADER.into()
    }
    /// Out of the depth prepass: screen-space contact shadows would otherwise see the strands and speckle the
    /// lawn with their tiny shadows (grass casts no shadow of any kind).
    fn enable_prepass() -> bool {
        false
    }
    fn enable_shadows() -> bool {
        false
    }
}

/// The lawn's ground texture, as the installed Showhome ground material samples it.
#[derive(Clone, Debug)]
pub struct LawnLook {
    pub albedo: Handle<Image>,
    pub normal: Handle<Image>,
    pub orm: Handle<Image>,
    pub height: Handle<Image>,
    pub base_layer: u32,
    pub macro_layer: u32,
    pub tint: Vec3,
    pub macro_repeat: f32,
    pub macro_strength: f32,
    pub normal_scale: f32,
}

impl LawnLook {
    fn of(m: &ShowhomeGroundMaterial) -> Self {
        let p = &m.extension.params;
        Self {
            albedo: m.extension.albedo.clone(),
            normal: m.extension.normal.clone(),
            orm: m.extension.orm.clone(),
            height: m.extension.height.clone(),
            base_layer: p.indices.x,
            macro_layer: p.extra_indices.y,
            tint: p.tint.truncate(),
            macro_repeat: p.extra.z.max(0.01),
            macro_strength: p.extra.w,
            normal_scale: p.parallax.z,
        }
    }

    fn ground_lanes(&self) -> (Vec4, Vec4, UVec4) {
        (
            self.tint.extend(self.macro_strength),
            Vec4::new(self.macro_repeat, 0.0, self.normal_scale, 0.0),
            UVec4::new(self.base_layer, self.macro_layer, 0, 0),
        )
    }
}

fn wind_lanes(w: &WindData, amplitude: f32, speed: f32) -> (Vec4, Vec4) {
    (
        w.dir().extend(0.0),
        Vec4::new(
            amplitude,
            w.frequency * speed * std::f32::consts::TAU,
            std::f32::consts::TAU / w.wavelength.max(0.1),
            w.gust,
        ),
    )
}

/// The lawn (shell) uniform for quality level `q`.
pub fn lawn_uniform(d: &FoliageData, q: usize, look: &LawnLook) -> GrassUniform {
    let l = &d.grass.lawn;
    let (wind_dir, wind) = wind_lanes(&d.wind, l.wind_sway, l.sway_speed);
    let (ground_tint, mut ground, layers) = look.ground_lanes();
    ground.y = l.wind_sheen;
    GrassUniform {
        wind_dir,
        wind,
        time: Vec4::new(0.0, 0.0, l.layers[q] as f32, l.height),
        shape: Vec4::new(l.spacing, l.radius, l.shortest, l.lean),
        fade: Vec4::new(l.fade_start[q], l.fade_end[q], l.dirt_thin.0, l.dirt_thin.1),
        shade: Vec4::new(l.root_shade, l.tip_lift, l.value_jitter, l.patch_strength),
        tip: Vec4::new(l.tip_tint.0, l.tip_tint.1, l.tip_tint.2, l.patch_scale.max(0.1)),
        ground_tint,
        ground,
        dry: Vec4::new(l.dry_tint.0, l.dry_tint.1, l.dry_tint.2, 1.0),
        lush: Vec4::new(l.lush_tint.0, l.lush_tint.1, l.lush_tint.2, 1.0),
        layers,
    }
}

/// The tuft uniform for quality level `q`.
pub fn tuft_uniform(d: &FoliageData, q: usize, look: &LawnLook) -> GrassUniform {
    let t = &d.grass.tufts;
    let (wind_dir, wind) = wind_lanes(&d.wind, t.wind_amplitude, t.sway_speed);
    let (ground_tint, ground, layers) = look.ground_lanes();
    GrassUniform {
        wind_dir,
        wind,
        time: Vec4::ZERO,
        shape: Vec4::ZERO,
        fade: Vec4::new(t.fade_start[q], t.fade_end[q], 0.0, 0.0),
        shade: Vec4::new(t.root_shade, t.tip_lift, 0.0, 0.0),
        tip: Vec4::new(t.tip_tint.0, t.tip_tint.1, t.tip_tint.2, 1.0),
        ground_tint,
        ground,
        dry: Vec4::ONE,
        lush: Vec4::ONE,
        layers,
    }
}

fn grass_material(params: GrassUniform, look: &LawnLook, alpha_mode: AlphaMode, cull: bool) -> GrassMaterial {
    GrassMaterial {
        base: StandardMaterial {
            base_color: Color::WHITE,
            perceptual_roughness: 0.9,
            alpha_mode,
            double_sided: false,
            cull_mode: if cull { Some(bevy::render::render_resource::Face::Back) } else { None },
            ..default()
        },
        extension: GrassExt {
            params,
            albedo: look.albedo.clone(),
            normal: look.normal.clone(),
            orm: look.orm.clone(),
            height: look.height.clone(),
        },
    }
}

// ---------------------------------------------------------------------------------------------- lawn surfaces

/// Lawn triangles in world space, with the attributes the shells need (as exported in ground.glb).
#[derive(Clone, Debug, Default, PartialEq)]
pub struct LawnSurface {
    pub positions: Vec<Vec3>,
    pub normals: Vec<Vec3>,
    pub tangents: Vec<Vec4>,
    pub uvs: Vec<Vec2>,
    /// The ground blend masks (COLOR_0): R worn dirt, G gravel, B moss, A mud.
    pub masks: Vec<Vec4>,
    pub indices: Vec<u32>,
}

impl LawnSurface {
    /// A kit lawn mesh, moved to world space by its transform.
    pub fn from_mesh(mesh: &Mesh, transform: &GlobalTransform) -> Option<Self> {
        let positions = mesh.attribute(Mesh::ATTRIBUTE_POSITION)?.as_float3()?;
        let n = positions.len();
        let affine = transform.affine();
        let rotation = transform.rotation();
        let normals = match mesh.attribute(Mesh::ATTRIBUTE_NORMAL) {
            Some(VertexAttributeValues::Float32x3(v)) => {
                v.iter().map(|n| (rotation * Vec3::from(*n)).normalize_or(Vec3::Y)).collect()
            }
            _ => vec![Vec3::Y; n],
        };
        let tangents = match mesh.attribute(Mesh::ATTRIBUTE_TANGENT) {
            Some(VertexAttributeValues::Float32x4(v)) => {
                v.iter().map(|t| (rotation * Vec3::new(t[0], t[1], t[2])).extend(t[3])).collect()
            }
            _ => vec![Vec4::new(1.0, 0.0, 0.0, 1.0); n],
        };
        let uvs = match mesh.attribute(Mesh::ATTRIBUTE_UV_0) {
            Some(VertexAttributeValues::Float32x2(v)) => v.iter().map(|u| Vec2::from(*u)).collect(),
            _ => vec![Vec2::ZERO; n],
        };
        let masks = match mesh.attribute(Mesh::ATTRIBUTE_COLOR) {
            Some(VertexAttributeValues::Float32x4(v)) => v.iter().map(|c| Vec4::from(*c)).collect(),
            _ => vec![Vec4::ZERO; n],
        };
        let indices: Vec<u32> = match mesh.indices() {
            Some(i) => i.iter().map(|i| i as u32).collect(),
            None => (0..n as u32).collect(),
        };
        Some(Self {
            positions: positions.iter().map(|p| affine.transform_point3(Vec3::from(*p))).collect(),
            normals,
            tangents,
            uvs,
            masks,
            indices,
        })
    }

    pub fn triangles(&self) -> impl Iterator<Item = [usize; 3]> + '_ {
        self.indices.chunks_exact(3).map(|t| [t[0] as usize, t[1] as usize, t[2] as usize])
    }

    /// The triangle's corners.
    fn corners(&self, t: [usize; 3]) -> [Vec3; 3] {
        t.map(|i| self.positions[i])
    }

    /// Faces up (the lawn's top, not the thin side faces along its edges).
    fn is_top(&self, t: [usize; 3]) -> bool {
        let [a, b, c] = self.corners(t);
        (b - a).cross(c - a).normalize_or_zero().y.abs() > 0.7
    }

    /// The ground masks are past `hi` all over the triangle in one channel (bare dirt, gravel or mud).
    fn is_bare(&self, t: [usize; 3], hi: f32) -> bool {
        let m = t.map(|i| self.masks[i]);
        [0, 1, 3].into_iter().any(|c| m.iter().all(|v| v[c] >= hi))
    }
}

/// The lawn's top triangles cut into `chunk`-sized cells (by centroid), keeping those whose centroid passes
/// `keep` and that are not bare dirt; positions stay in world space.
pub fn split_chunks(
    surfaces: &[LawnSurface],
    chunk: f32,
    bare: f32,
    keep: impl Fn(Vec2) -> bool,
) -> Vec<((i32, i32), LawnSurface)> {
    let mut cells: HashMap<(i32, i32), (LawnSurface, HashMap<(usize, usize), u32>)> = HashMap::new();
    for (k, s) in surfaces.iter().enumerate() {
        for t in s.triangles() {
            if !s.is_top(t) || s.is_bare(t, bare) {
                continue;
            }
            let [a, b, c] = s.corners(t);
            let centroid = (a + b + c) / 3.0;
            let flat = Vec2::new(centroid.x, centroid.z);
            if !keep(flat) {
                continue;
            }
            let key = ((flat.x / chunk).floor() as i32, (flat.y / chunk).floor() as i32);
            let (out, remap) = cells.entry(key).or_default();
            for i in t {
                let j = *remap.entry((k, i)).or_insert_with(|| {
                    out.positions.push(s.positions[i]);
                    out.normals.push(s.normals[i]);
                    out.tangents.push(s.tangents[i]);
                    out.uvs.push(s.uvs[i]);
                    out.masks.push(s.masks[i]);
                    out.positions.len() as u32 - 1
                });
                out.indices.push(j);
            }
        }
    }
    let mut out: Vec<_> = cells.into_iter().map(|(k, (s, _))| (k, s)).collect();
    out.sort_by_key(|(k, _)| *k);
    out
}

/// A lawn chunk as a mesh (positions relative to `origin`), the kit lawn's own vertex layout.
fn shell_mesh(s: &LawnSurface, origin: Vec3) -> Mesh {
    Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::RENDER_WORLD)
        .with_inserted_attribute(
            Mesh::ATTRIBUTE_POSITION,
            s.positions.iter().map(|p| (*p - origin).to_array()).collect::<Vec<_>>(),
        )
        .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, s.normals.iter().map(|n| n.to_array()).collect::<Vec<_>>())
        .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, s.uvs.iter().map(|u| u.to_array()).collect::<Vec<_>>())
        .with_inserted_attribute(Mesh::ATTRIBUTE_TANGENT, s.tangents.iter().map(|t| t.to_array()).collect::<Vec<_>>())
        .with_inserted_attribute(Mesh::ATTRIBUTE_COLOR, s.masks.iter().map(|m| m.to_array()).collect::<Vec<_>>())
        .with_inserted_indices(Indices::U32(s.indices.clone()))
}

// ---------------------------------------------------------------------------------------------- edges

/// The outline of the lawn (x/z): edges of top triangles that only one triangle uses, after welding corners
/// within a millimetre (so separate lawn meshes that meet do not count as an edge).
pub fn lawn_edges(surfaces: &[LawnSurface]) -> Vec<(Vec2, Vec2)> {
    let weld = |p: Vec3| ((p.x * 1000.0).round() as i64, (p.z * 1000.0).round() as i64);
    let mut count: HashMap<((i64, i64), (i64, i64)), (u32, Vec2, Vec2)> = HashMap::new();
    for s in surfaces {
        for t in s.triangles() {
            if !s.is_top(t) {
                continue;
            }
            let c = s.corners(t);
            for (a, b) in [(c[0], c[1]), (c[1], c[2]), (c[2], c[0])] {
                let (ka, kb) = (weld(a), weld(b));
                if ka == kb {
                    continue;
                }
                let key = if ka < kb { (ka, kb) } else { (kb, ka) };
                count.entry(key).or_insert((0, Vec2::new(a.x, a.z), Vec2::new(b.x, b.z))).0 += 1;
            }
        }
    }
    let mut out: Vec<_> = count.into_values().filter(|(n, _, _)| *n == 1).map(|(_, a, b)| (a, b)).collect();
    out.sort_by(|x, y| {
        (x.0.x, x.0.y, x.1.x, x.1.y).partial_cmp(&(y.0.x, y.0.y, y.1.x, y.1.y)).unwrap_or(std::cmp::Ordering::Equal)
    });
    out
}

/// Footprints (x/z) of everything standing on the ground that a lawn grows long against: walls, fences,
/// hedges, houses, bins, sheds.
pub fn solid_footprints(level: &Level) -> Vec<Rect> {
    level
        .world
        .brushes
        .iter()
        .filter(|b| b.kind == BrushKind::Solid && b.look != Look::Invisible && b.ramp.is_none())
        .filter(|b| b.min.y < 0.3 && b.max.y > 0.3)
        .map(|b| Rect { min: Vec2::new(b.min.x, b.min.z), max: Vec2::new(b.max.x, b.max.z) })
        .collect()
}

fn segment_distance(p: Vec2, a: Vec2, b: Vec2) -> f32 {
    let ab = b - a;
    let t = ((p - a).dot(ab) / ab.length_squared().max(1e-12)).clamp(0.0, 1.0);
    p.distance(a + ab * t)
}

/// Distance to the nearest lawn edge or solid footprint, looked up on a grid.
pub struct EdgeField {
    cell: f32,
    reach: f32,
    segments: Vec<(Vec2, Vec2)>,
    solids: Vec<Rect>,
    grid: HashMap<(i32, i32), (Vec<u32>, Vec<u32>)>,
}

impl EdgeField {
    /// Distances are exact up to `reach` (further ones come back as `reach`).
    pub fn new(segments: Vec<(Vec2, Vec2)>, solids: Vec<Rect>, reach: f32) -> Self {
        let cell = 1.0;
        let mut grid: HashMap<(i32, i32), (Vec<u32>, Vec<u32>)> = HashMap::new();
        let mut cover = |lo: Vec2, hi: Vec2, f: &mut dyn FnMut(&mut (Vec<u32>, Vec<u32>))| {
            let (i0, j0) = (((lo.x - reach) / cell).floor() as i32, ((lo.y - reach) / cell).floor() as i32);
            let (i1, j1) = (((hi.x + reach) / cell).floor() as i32, ((hi.y + reach) / cell).floor() as i32);
            for i in i0..=i1 {
                for j in j0..=j1 {
                    f(grid.entry((i, j)).or_default());
                }
            }
        };
        for (k, (a, b)) in segments.iter().enumerate() {
            cover(a.min(*b), a.max(*b), &mut |c| c.0.push(k as u32));
        }
        for (k, r) in solids.iter().enumerate() {
            cover(r.min, r.max, &mut |c| c.1.push(k as u32));
        }
        Self { cell, reach, segments, solids, grid }
    }

    fn near(&self, p: Vec2) -> Option<&(Vec<u32>, Vec<u32>)> {
        self.grid.get(&((p.x / self.cell).floor() as i32, (p.y / self.cell).floor() as i32))
    }

    /// Distance (m) to the nearest edge or footprint, at most `reach`.
    pub fn distance(&self, p: Vec2) -> f32 {
        let (edge, foot) = self.distances(p);
        edge.min(foot)
    }

    /// Distances (m, at most `reach`) to the nearest lawn edge and to the nearest solid's foot.
    pub fn distances(&self, p: Vec2) -> (f32, f32) {
        let Some((segs, solids)) = self.near(p) else { return (self.reach, self.reach) };
        let (mut edge, mut foot) = (self.reach, self.reach);
        for &k in segs {
            let (a, b) = self.segments[k as usize];
            edge = edge.min(segment_distance(p, a, b));
        }
        for &k in solids {
            let r = self.solids[k as usize];
            foot = foot.min(p.distance(p.clamp(r.min, r.max)));
        }
        (edge, foot)
    }

    /// Inside (or within `margin` of) a solid footprint.
    pub fn inside_solid(&self, p: Vec2, margin: f32) -> bool {
        let Some((_, solids)) = self.near(p) else { return false };
        solids.iter().any(|&k| {
            let r = self.solids[k as usize];
            p.x > r.min.x - margin && p.x < r.max.x + margin && p.y > r.min.y - margin && p.y < r.max.y + margin
        })
    }
}

// ---------------------------------------------------------------------------------------------- tufts

/// One tuft: its root on the lawn, the lawn's UV there (its colour), its height and its own seed.
#[derive(Clone, Debug, PartialEq)]
pub struct Tuft {
    pub root: Vec3,
    pub uv: Vec2,
    pub height: f32,
    pub seed: u64,
}

fn hash01(i: i32, j: i32, salt: u64) -> f32 {
    SplitMix::from_parts(&[i as u32 as u64, j as u32 as u64, salt]).next_f32()
}

/// Smooth value noise (0..1), two octaves.
pub fn patch_noise(p: Vec2, seed: u64) -> f32 {
    let octave = |p: Vec2, salt: u64| {
        let (i, j) = (p.x.floor() as i32, p.y.floor() as i32);
        let f = p - p.floor();
        let u = f * f * (Vec2::splat(3.0) - 2.0 * f);
        let a = hash01(i, j, salt);
        let b = hash01(i + 1, j, salt);
        let c = hash01(i, j + 1, salt);
        let d = hash01(i + 1, j + 1, salt);
        (a + (b - a) * u.x) + ((c + (d - c) * u.x) - (a + (b - a) * u.x)) * u.y
    };
    octave(p, seed) * 0.7 + octave(p * 2.3 + Vec2::splat(31.7), seed ^ 0x5eed) * 0.3
}

/// Where tufts grow: random points on the lawn triangles (inside `area`, x/z), kept with a probability that
/// is highest right at an edge (`field`), only inside noise patches, and falls off where the ground masks
/// show dirt. `density` = tufts per m² at an edge in a patch. Same inputs, same tufts.
pub fn place_tufts(
    surfaces: &[LawnSurface],
    field: &EdgeField,
    t: &TuftData,
    density: f32,
    area: Rect,
    seed: u64,
) -> Vec<Tuft> {
    let mut out = Vec::new();
    if density <= 0.0 || t.band <= 0.0 {
        return out;
    }
    for (k, s) in surfaces.iter().enumerate() {
        for (n, tri) in s.triangles().enumerate() {
            if !s.is_top(tri) {
                continue;
            }
            let [a, b, c] = s.corners(tri);
            let centroid = (a + b + c) / 3.0;
            let flat = Vec2::new(centroid.x, centroid.z);
            if !area.contains(flat) {
                continue;
            }
            let span = a.distance(b).max(b.distance(c)).max(c.distance(a));
            if field.distance(flat) > t.band + span {
                continue;
            }
            let tri_area = 0.5 * (b - a).cross(c - a).length();
            let mut rng = SplitMix::from_parts(&[seed, k as u64, n as u64]);
            let expected = tri_area * density;
            let count = expected.floor() as u32 + u32::from(rng.next_f32() < expected.fract());
            for _ in 0..count {
                // Draw every number first, so a rejected tuft does not shift the next one.
                let (r1, r2, keep, r_height) = (rng.next_f32(), rng.next_f32(), rng.next_f32(), rng.next_f32());
                let tuft_seed = rng.next_u64();
                let (u, v) = if r1 + r2 > 1.0 { (1.0 - r1, 1.0 - r2) } else { (r1, r2) };
                let w = 1.0 - u - v;
                let p = a * w + b * u + c * v;
                let flat = Vec2::new(p.x, p.z);
                let [ia, ib, ic] = tri;
                let mask = s.masks[ia] * w + s.masks[ib] * u + s.masks[ic] * v;
                let uv = s.uvs[ia] * w + s.uvs[ib] * u + s.uvs[ic] * v;
                // Most right at an edge; in patches along the lawn's outline, nearly all along the foot of a
                // fence, wall or hedge (where no mower reaches).
                let (to_edge, to_foot) = field.distances(flat);
                let noise = patch_noise(flat / t.patch_scale, seed);
                let along = |d: f32, cover: f32| {
                    let near = 1.0 - smooth(0.0, t.band, d);
                    near.sqrt() * smooth(1.0 - cover - 0.08, 1.0 - cover + 0.08, noise)
                };
                let weight = along(to_edge, t.patch_cover).max(along(to_foot, t.foot_cover));
                let edge = 1.0 - smooth(0.0, t.band, to_edge.min(to_foot));
                let dirt = mask.x.max(mask.y).max(mask.w);
                let green = 1.0 - smooth(t.dirt_limit.0, t.dirt_limit.1, dirt);
                if keep >= weight * green || field.inside_solid(flat, 0.02) {
                    continue;
                }
                let height = (t.height.0 + (t.height.1 - t.height.0) * r_height.powf(1.3)) * (0.7 + 0.3 * edge);
                out.push(Tuft { root: p, uv, height, seed: tuft_seed });
            }
        }
    }
    out
}

/// Raw vertex arrays of the blade meshes (see grass.wgsl for the layout).
#[derive(Default)]
pub struct BladeMesh {
    pub positions: Vec<[f32; 3]>,
    pub offsets: Vec<[f32; 4]>,
    pub normals: Vec<[f32; 3]>,
    pub uvs: Vec<[f32; 2]>,
    pub values: Vec<[f32; 2]>,
    pub indices: Vec<u32>,
}

impl BladeMesh {
    fn into_mesh(self) -> Mesh {
        Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::RENDER_WORLD)
            .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, self.positions)
            .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, self.normals)
            .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, self.uvs)
            .with_inserted_attribute(Mesh::ATTRIBUTE_UV_1, self.values)
            .with_inserted_attribute(Mesh::ATTRIBUTE_COLOR, self.offsets)
            .with_inserted_indices(Indices::U32(self.indices))
    }
}

/// The blades of `tufts`, positions relative to `origin`. Each blade is a curved strip (root, middle, tip),
/// leaning out from the tuft's centre; normals mostly up so it lights like the lawn.
pub fn tuft_blades(tufts: &[Tuft], origin: Vec3, t: &TuftData) -> BladeMesh {
    let mut out = BladeMesh::default();
    for tuft in tufts {
        let mut rng = SplitMix::new(tuft.seed);
        let n = t.blades.0 + (rng.next_f32() * (t.blades.1.saturating_sub(t.blades.0) + 1) as f32) as u32;
        let root = (tuft.root - origin).to_array();
        for _ in 0..n.max(1) {
            let az = rng.next_f32() * std::f32::consts::TAU;
            let out_dir = Vec3::new(az.cos(), 0.0, az.sin());
            let base = out_dir * t.spread * rng.next_f32().sqrt();
            let turn = rng.next_signed() * 0.6;
            let dir = Vec3::new((az + turn).cos(), 0.0, (az + turn).sin());
            let lean = (t.lean_deg.0 + (t.lean_deg.1 - t.lean_deg.0) * rng.next_f32()).to_radians();
            let h = tuft.height * (0.55 + 0.45 * rng.next_f32());
            let w = t.blade_width * (0.8 + 0.45 * rng.next_f32());
            let value = 1.0 + rng.next_signed() * t.value_jitter;
            // The blade's broad side faces along its lean, a little twisted.
            let twist = rng.next_signed() * 0.5;
            let side = Quat::from_rotation_y(twist) * Vec3::new(-dir.z, 0.0, dir.x);
            let spine = |s: f32| base + Vec3::Y * (h * lean.cos() * s) + dir * (h * lean.sin() * s.powf(1.7));
            let face = side.cross(spine(0.6) - spine(0.0)).normalize_or(Vec3::Y);
            let face = if face.y < 0.0 { -face } else { face };
            let normal = (Vec3::Y * 0.65 + face * 0.35).normalize().to_array();
            let first = out.positions.len() as u32;
            for (s, half) in [(0.0, 0.5 * w), (0.5, 0.36 * w), (1.0, 0.0)] {
                let centre = spine(s);
                let corners: &[Vec3] =
                    if half > 0.0 { &[centre - side * half, centre + side * half] } else { &[centre] };
                for c in corners {
                    out.positions.push(root);
                    out.offsets.push([c.x, c.y, c.z, s]);
                    out.normals.push(normal);
                    out.uvs.push(tuft.uv.to_array());
                    out.values.push([value, 0.0]);
                }
            }
            let i = first;
            out.indices.extend_from_slice(&[i, i + 1, i + 3, i, i + 3, i + 2, i + 2, i + 3, i + 4]);
        }
    }
    out
}

// ---------------------------------------------------------------------------------------------- systems

/// What the grass is built for: level, quality level, lawn meshes found, parts kept by `VETF_GRASS`.
#[derive(Resource, Default)]
struct GrassState {
    built: Option<(String, Option<usize>, usize, (bool, bool))>,
    materials: Vec<Handle<GrassMaterial>>,
}

#[derive(Component)]
struct GrassRoot;

/// A grass chunk: its centre (x/z), half diagonal and how far away it is still drawn.
#[derive(Component)]
struct GrassChunk {
    centre: Vec2,
    radius: f32,
    reach: f32,
}

/// The playable area (x/z) grown by `margin`.
fn play_rect(level: &Level, margin: f32) -> Rect {
    super::play_area(level, margin)
}

/// `VETF_GRASS`: which parts to build (lawn, tufts).
fn parts(env: Option<&str>) -> (bool, bool) {
    match env.map(|e| e.trim().to_ascii_lowercase()).as_deref() {
        Some("off") => (false, false),
        Some("lawn") => (true, false),
        Some("tufts") => (false, true),
        _ => (true, true),
    }
}

fn is_lawn(name: &str) -> bool {
    let canonical = name
        .rsplit_once('.')
        .filter(|(_, suffix)| suffix.chars().all(|c| c.is_ascii_digit()))
        .map_or(name, |(base, _)| base);
    canonical == LAWN_MATERIAL
}

#[allow(clippy::too_many_arguments)]
fn build_grass(
    mut commands: Commands,
    level: Option<Res<CurrentLevel>>,
    settings: Option<Res<Settings>>,
    data: Res<FoliageData>,
    mut state: ResMut<GrassState>,
    roots: Query<Entity, With<GrassRoot>>,
    lawns: Query<
        (&Mesh3d, &MeshMaterial3d<ShowhomeGroundMaterial>, &GltfMaterialName, &GlobalTransform),
        With<ShowhomeKitMesh>,
    >,
    ground_materials: Res<Assets<ShowhomeGroundMaterial>>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<GrassMaterial>>,
) {
    let Some(level) = level else { return };
    if !level.name.eq_ignore_ascii_case("showhome") {
        return;
    }
    let preset = settings.map_or(Preset::High, |s| s.video.preset);
    let q = quality(preset, std::env::var("VETF_FOLIAGE").ok().as_deref());
    let keep = parts(std::env::var("VETF_GRASS").ok().as_deref());
    // The kit's lawns, once their ground material is installed and their meshes have loaded.
    let mut sources = Vec::new();
    let mut look = None;
    for (mesh, material, name, transform) in &lawns {
        if !is_lawn(&name.0) {
            continue;
        }
        let (Some(mesh), Some(material)) = (meshes.get(&mesh.0), ground_materials.get(&material.0)) else { return };
        look.get_or_insert_with(|| LawnLook::of(material));
        sources.push((mesh.clone(), *transform));
    }
    let want = (level.name.clone(), q, sources.len(), keep);
    if state.built.as_ref() == Some(&want) {
        return;
    }
    let Some(look) = look else { return };
    for e in &roots {
        commands.entity(e).despawn();
    }
    state.built = Some(want);
    state.materials.clear();
    let Some(q) = q else { return };
    let root = commands
        .spawn((
            GrassRoot,
            Name::new("Grass"),
            Transform::default(),
            Visibility::default(),
            DespawnOnExit(AppState::InGame),
        ))
        .id();
    let t0 = std::time::Instant::now();
    let surfaces: Vec<LawnSurface> = sources.iter().filter_map(|(m, t)| LawnSurface::from_mesh(m, t)).collect();
    let g = &data.grass;

    // Mown lawn: one mesh per chunk, one instance per layer.
    let (mut chunks, mut shell_tris) = (0usize, 0usize);
    let layers = g.lawn.layers[q];
    if keep.0 && layers >= 2 {
        let material = materials.add(grass_material(lawn_uniform(&data, q, &look), &look, AlphaMode::Mask(0.5), true));
        state.materials.push(material.clone());
        let reach = g.lawn.fade_end[q];
        let area = play_rect(&level, reach);
        for (key, s) in split_chunks(&surfaces, g.lawn.chunk, g.lawn.dirt_thin.1, |p| area.contains(p)) {
            let origin = Vec3::new(key.0 as f32 * g.lawn.chunk, 0.0, key.1 as f32 * g.lawn.chunk);
            let (lo, hi) = s.positions.iter().fold((Vec3::MAX, Vec3::MIN), |(lo, hi), p| (lo.min(*p), hi.max(*p)));
            let aabb = Aabb::from_min_max(lo - origin, hi - origin + Vec3::Y * (g.lawn.height + 0.01));
            let centre = Vec2::new(lo.x + hi.x, lo.z + hi.z) * 0.5;
            let radius = Vec2::new(hi.x - lo.x, hi.z - lo.z).length() * 0.5;
            shell_tris += s.indices.len() / 3;
            chunks += 1;
            let mesh = meshes.add(shell_mesh(&s, origin));
            // Top layer first: drawn front to back within the instanced draw where the GPU keeps the order.
            for layer in (0..layers).rev() {
                commands.spawn((
                    Name::new("Lawn shell"),
                    GrassChunk { centre, radius, reach },
                    Mesh3d(mesh.clone()),
                    MeshMaterial3d(material.clone()),
                    MeshTag(layer),
                    Transform::from_translation(origin),
                    aabb,
                    NotShadowCaster,
                    ChildOf(root),
                ));
            }
        }
    }

    // Tufts along the edges.
    let t = &g.tufts;
    let (mut tufts_n, mut blade_tris) = (0usize, 0usize);
    if keep.1 && t.density[q] > 0.0 {
        let material = materials.add(grass_material(tuft_uniform(&data, q, &look), &look, AlphaMode::Opaque, false));
        state.materials.push(material.clone());
        let field = EdgeField::new(lawn_edges(&surfaces), solid_footprints(&level), t.band + 1.0);
        let tufts = place_tufts(&surfaces, &field, t, t.density[q], play_rect(&level, t.reach), 0x7475_6674);
        tufts_n = tufts.len();
        let mut cells: HashMap<(i32, i32), Vec<Tuft>> = HashMap::new();
        for tuft in tufts {
            cells
                .entry(((tuft.root.x / t.chunk).floor() as i32, (tuft.root.z / t.chunk).floor() as i32))
                .or_default()
                .push(tuft);
        }
        let mut keys: Vec<_> = cells.keys().copied().collect();
        keys.sort();
        let lean = t.height.1 * 0.6 + t.spread + t.wind_amplitude;
        for key in keys {
            let origin = Vec3::new(key.0 as f32 * t.chunk, 0.0, key.1 as f32 * t.chunk);
            let blades = tuft_blades(&cells[&key], origin, t);
            blade_tris += blades.indices.len() / 3;
            let aabb = Aabb::from_min_max(
                Vec3::new(-lean, -0.05, -lean),
                Vec3::new(t.chunk + lean, t.height.1 + 0.05, t.chunk + lean),
            );
            commands.spawn((
                Name::new("Lawn tufts"),
                GrassChunk {
                    centre: Vec2::new(origin.x, origin.z) + Vec2::splat(t.chunk * 0.5),
                    radius: t.chunk * std::f32::consts::FRAC_1_SQRT_2 + lean,
                    reach: t.fade_end[q],
                },
                Mesh3d(meshes.add(blades.into_mesh())),
                MeshMaterial3d(material.clone()),
                Transform::from_translation(origin),
                aabb,
                NotShadowCaster,
                ChildOf(root),
            ));
        }
    }
    info!(
        "grass ({}): lawn {layers} layers over {shell_tris} triangles in {chunks} chunks, {tufts_n} tufts \
         ({blade_tris} triangles), built in {:.0} ms",
        Preset::from_index(q).label(),
        t0.elapsed().as_secs_f32() * 1000.0
    );
}

/// Grass chunks past their fade distance are not drawn.
fn cull_grass(camera: Query<&GlobalTransform, With<ViewCamera>>, mut chunks: Query<(&GrassChunk, &mut Visibility)>) {
    let Some(cam) = camera.iter().next() else { return };
    let eye = cam.translation();
    let eye = Vec2::new(eye.x, eye.z);
    for (c, mut v) in &mut chunks {
        let near = eye.distance(c.centre) - c.radius < c.reach;
        v.set_if_neq(if near { Visibility::Inherited } else { Visibility::Hidden });
    }
}

/// The shader's clock (the wind). Touching the materials also rebuilds their bind groups, so the lawn picks up the
/// ground arrays' mip chains once `showhome_kit` has made them.
fn tick_grass(time: Res<Time>, state: Res<GrassState>, mut materials: ResMut<Assets<GrassMaterial>>) {
    let t = time.elapsed_secs_wrapped();
    for h in &state.materials {
        if let Some(mut m) = materials.get_mut(h) {
            m.extension.params.time.x = t;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A flat lawn `w` x `d` metres at (x0, z0) on a 25 cm grid, with `mask(p)` as its ground masks.
    fn lawn(x0: f32, z0: f32, w: f32, d: f32, mask: impl Fn(Vec2) -> Vec4) -> LawnSurface {
        let step = 0.25;
        let (nx, nz) = ((w / step).round() as u32, (d / step).round() as u32);
        let mut s = LawnSurface::default();
        for j in 0..=nz {
            for i in 0..=nx {
                let p = Vec3::new(x0 + i as f32 * step, 0.006, z0 + j as f32 * step);
                s.positions.push(p);
                s.normals.push(Vec3::Y);
                s.tangents.push(Vec4::new(1.0, 0.0, 0.0, 1.0));
                s.uvs.push(Vec2::new(p.x, p.z) * 0.5);
                s.masks.push(mask(Vec2::new(p.x, p.z)));
            }
        }
        let row = nx + 1;
        for j in 0..nz {
            for i in 0..nx {
                let k = j * row + i;
                s.indices.extend_from_slice(&[k, k + row, k + 1, k + 1, k + row, k + row + 1]);
            }
        }
        s
    }

    fn tufts_data() -> TuftData {
        super::super::embedded().grass.tufts
    }

    #[test]
    fn the_lawn_outline_is_its_border_not_the_seam_between_two_meshes() {
        // Two 4 x 2 m lawns side by side make one 8 x 2 m lawn: its outline is 2 * (8 + 2) m long.
        let a = lawn(0.0, 0.0, 4.0, 2.0, |_| Vec4::ZERO);
        let b = lawn(4.0, 0.0, 4.0, 2.0, |_| Vec4::ZERO);
        let edges = lawn_edges(&[a, b]);
        let length: f32 = edges.iter().map(|(a, b)| a.distance(*b)).sum();
        assert!((length - 20.0).abs() < 1e-3, "{length}");
        for (a, b) in &edges {
            let on_border =
                |p: Vec2| p.x.abs() < 1e-4 || (p.x - 8.0).abs() < 1e-4 || p.y.abs() < 1e-4 || (p.y - 2.0).abs() < 1e-4;
            assert!(on_border(*a) && on_border(*b));
        }
    }

    #[test]
    fn tufts_grow_along_edges_in_patches_and_never_on_dirt_or_paths() {
        let t = tufts_data();
        // A 10 x 6 m lawn with a worn-dirt strip (R mask) at z 2.5..3.5 and a 2 m path cut out of it at x 4..6.
        let dirt = |p: Vec2| Vec4::new(if (2.5..=3.5).contains(&p.y) { 1.0 } else { 0.0 }, 0.0, 0.0, 0.0);
        let west = lawn(0.0, 0.0, 4.0, 6.0, dirt);
        let east = lawn(6.0, 0.0, 4.0, 6.0, dirt);
        let lawns = [west, east];
        // A fence across the middle of the east part.
        let fence = Rect { min: Vec2::new(7.0, 4.4), max: Vec2::new(9.0, 4.6) };
        let field = EdgeField::new(lawn_edges(&lawns), vec![fence], t.band + 1.0);
        let area = Rect { min: Vec2::splat(-1.0), max: Vec2::splat(20.0) };
        let tufts = place_tufts(&lawns, &field, &t, 40.0, area, 3);
        assert!(tufts.len() > 30, "{} tufts", tufts.len());
        for tuft in &tufts {
            let p = Vec2::new(tuft.root.x, tuft.root.z);
            // On the lawn, never on the path between the two halves.
            assert!(!(4.0..6.0).contains(&p.x), "a tuft on the path at {p}");
            assert!((0.0..=10.0).contains(&p.x) && (0.0..=6.0).contains(&p.y));
            // Never on the worn-dirt strip (well past dirt_limit there).
            assert!(!(2.6..=3.4).contains(&p.y), "a tuft on bare dirt at {p}");
            // Never inside the fence, always near an edge or the fence.
            assert!(!(fence.contains(p)), "a tuft inside the fence at {p}");
            assert!(field.distance(p) <= t.band + 1e-3, "a tuft {} m from any edge", field.distance(p));
            assert!(tuft.height >= t.height.0 * 0.7 - 1e-4 && tuft.height <= t.height.1 + 1e-4);
        }
        // Along the fence too (its foot is an edge).
        assert!(tufts.iter().any(|tf| (tf.root.z - 4.5).abs() < 0.3 && (7.0..9.0).contains(&tf.root.x)));
        // Never on a grid: positions are not quantised.
        let mut snapped = 0;
        for tf in &tufts {
            if ((tf.root.x * 20.0).fract().abs() < 1e-3) && ((tf.root.z * 20.0).fract().abs() < 1e-3) {
                snapped += 1;
            }
        }
        assert!(snapped * 10 < tufts.len(), "{snapped} of {} tufts on a 5 cm grid", tufts.len());
        // In patches: some stretches of edge have none (the patch cover is below one).
        let mut covered = 0;
        let mut stretches = 0;
        for k in 0..40 {
            let x = 0.1 + k as f32 * 0.25;
            if (4.0..6.0).contains(&x) {
                continue;
            }
            stretches += 1;
            if tufts.iter().any(|tf| (tf.root.x - x).abs() < 0.125 && tf.root.z < t.band) {
                covered += 1;
            }
        }
        assert!(covered > 0 && covered < stretches, "{covered} of {stretches} stretches of the south edge");
        // Same inputs, same tufts.
        assert_eq!(place_tufts(&lawns, &field, &t, 40.0, area, 3), tufts);
        // A different seed moves them.
        assert_ne!(place_tufts(&lawns, &field, &t, 40.0, area, 4), tufts);
        // No density, no tufts.
        assert!(place_tufts(&lawns, &field, &t, 0.0, area, 3).is_empty());
    }

    #[test]
    fn edge_distance_counts_lawn_edges_and_solid_feet() {
        let field = EdgeField::new(
            vec![(Vec2::new(0.0, 0.0), Vec2::new(10.0, 0.0))],
            vec![Rect { min: Vec2::new(4.0, 5.0), max: Vec2::new(6.0, 5.2) }],
            2.0,
        );
        assert!((field.distance(Vec2::new(5.0, 0.3)) - 0.3).abs() < 1e-5);
        assert!((field.distance(Vec2::new(5.0, 4.6)) - 0.4).abs() < 1e-5);
        assert_eq!(field.distance(Vec2::new(5.0, 2.5)), 2.0, "capped at reach");
        assert_eq!(field.distance(Vec2::new(50.0, 50.0)), 2.0);
        assert!(field.inside_solid(Vec2::new(5.0, 5.1), 0.0));
        assert!(!field.inside_solid(Vec2::new(5.0, 5.5), 0.0));
    }

    #[test]
    fn chunks_keep_lawn_tops_and_drop_bare_dirt() {
        // A lawn with a fully worn patch (R = 1) at x 2..3.
        let s =
            lawn(0.0, 0.0, 6.0, 2.0, |p| Vec4::new(if (2.0..=3.0).contains(&p.x) { 1.0 } else { 0.0 }, 0.0, 0.0, 0.0));
        let all = s.indices.len() / 3;
        let chunks = split_chunks(std::slice::from_ref(&s), 4.0, 0.9, |_| true);
        assert_eq!(chunks.iter().map(|(k, _)| *k).collect::<Vec<_>>(), vec![(0, 0), (1, 0)]);
        let kept: usize = chunks.iter().map(|(_, c)| c.indices.len() / 3).sum();
        // The 1 m worn patch's triangles are gone, the rest kept.
        assert_eq!(kept, all - all / 6, "{kept} of {all}");
        for (key, c) in &chunks {
            assert!(c.indices.iter().all(|&i| (i as usize) < c.positions.len()));
            for tri in c.triangles() {
                let centroid = c.corners(tri).iter().sum::<Vec3>() / 3.0;
                assert_eq!((centroid.x / 4.0).floor() as i32, key.0);
                assert!(!(2.0..3.0).contains(&centroid.x));
            }
        }
        // Outside `keep`, nothing.
        assert!(split_chunks(std::slice::from_ref(&s), 4.0, 0.9, |p| p.x > 100.0).is_empty());
    }

    #[test]
    fn blades_stand_on_their_root_and_stay_within_the_tuft_height() {
        let t = tufts_data();
        let tufts = vec![
            Tuft { root: Vec3::new(3.0, 0.006, 4.0), uv: Vec2::new(1.5, 2.0), height: 0.2, seed: 1 },
            Tuft { root: Vec3::new(5.0, 0.006, 1.0), uv: Vec2::new(2.5, 0.5), height: 0.12, seed: 2 },
        ];
        let origin = Vec3::new(0.0, 0.0, 0.0);
        let m = tuft_blades(&tufts, origin, &t);
        assert_eq!(m.positions.len(), m.offsets.len());
        assert_eq!(m.indices.len() % 3, 0);
        assert!(m.indices.iter().all(|&i| (i as usize) < m.positions.len()));
        let blades = m.positions.len() / 5;
        assert!(blades >= 2 * t.blades.0 as usize && blades <= 2 * t.blades.1 as usize);
        for ((p, o), n) in m.positions.iter().zip(&m.offsets).zip(&m.normals) {
            let tuft = tufts.iter().find(|tf| (Vec3::from(*p) - tf.root).length() < 1e-5).expect("POSITION is a root");
            // Height along the blade in 0..1; the blade's corner never rises above the tuft or sinks under it.
            assert!((0.0..=1.0).contains(&o[3]));
            assert!(o[1] >= -1e-5 && o[1] <= tuft.height + 1e-4, "{o:?}");
            if o[3] == 0.0 {
                assert!(Vec2::new(o[0], o[2]).length() <= t.spread + t.blade_width, "{o:?}");
            }
            assert!(Vec3::from(*n).y > 0.5, "normals lean up");
        }
        // Same seeds, same blades.
        assert_eq!(tuft_blades(&tufts, origin, &t).offsets, m.offsets);
    }

    #[test]
    fn lawn_material_names_match_with_blender_suffixes() {
        assert!(is_lawn("M_GND_Grass"));
        assert!(is_lawn("M_GND_Grass.001"));
        assert!(!is_lawn("M_GND_GrassFar"));
        assert!(!is_lawn("M_GND_Grass.far"));
    }

    #[test]
    fn grass_env_override_keeps_parts() {
        assert_eq!(parts(None), (true, true));
        assert_eq!(parts(Some("off")), (false, false));
        assert_eq!(parts(Some("Lawn")), (true, false));
        assert_eq!(parts(Some("tufts")), (false, true));
        assert_eq!(parts(Some("whatever")), (true, true));
    }

    #[test]
    fn the_real_map_grows_tufts_only_inside_the_reach() {
        // Showhome's collision footprints are found, and a tuft field over a stand-in lawn is deterministic.
        let level = vetf_sim::maps::showhome();
        let solids = solid_footprints(&level);
        assert!(solids.len() > 50, "{}", solids.len());
        // Nothing lying on the ground (lawn tops, paths) counts as a solid foot.
        for r in &solids {
            assert!(r.max.x > r.min.x && r.max.y > r.min.y);
        }
        let t = tufts_data();
        let s = lawn(20.0, -32.0, 8.0, 16.0, |_| Vec4::ZERO);
        let field = EdgeField::new(lawn_edges(std::slice::from_ref(&s)), solids, t.band + 1.0);
        let area = play_rect(&level, t.reach);
        let a = place_tufts(std::slice::from_ref(&s), &field, &t, t.density[2], area, 9);
        let b = place_tufts(std::slice::from_ref(&s), &field, &t, t.density[2], area, 9);
        assert_eq!(a, b);
        assert!(!a.is_empty());
        let none =
            place_tufts(std::slice::from_ref(&s), &field, &t, t.density[2], Rect::new(500.0, 500.0, 501.0, 501.0), 9);
        assert!(none.is_empty(), "outside the reach");
    }

    /// The kit's surfaces of one ground material read straight from ground.glb (a minimal GLB reader: float or
    /// normalised attributes, u16/u32 indices, meshes at identity as exported). None when the file is an LFS
    /// pointer.
    fn kit_surfaces(material: &str) -> Option<Vec<LawnSurface>> {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../assets/maps/showhome/ground.glb");
        let data = std::fs::read(path).ok()?;
        if !data.starts_with(b"glTF") {
            return None;
        }
        let u32_at = |o: usize| u32::from_le_bytes([data[o], data[o + 1], data[o + 2], data[o + 3]]) as usize;
        let json_len = u32_at(12);
        let js: serde_json::Value = serde_json::from_slice(&data[20..20 + json_len]).ok()?;
        let bin = &data[20 + json_len + 8..];
        let accessor = |i: usize| -> Vec<Vec<f32>> {
            let a = &js["accessors"][i];
            let view = &js["bufferViews"][a["bufferView"].as_u64().unwrap_or(0) as usize];
            let ty = a["componentType"].as_u64().unwrap_or(5126);
            let n = match a["type"].as_str().unwrap_or("SCALAR") {
                "SCALAR" => 1,
                "VEC2" => 2,
                "VEC3" => 3,
                _ => 4,
            };
            let size = match ty {
                5126 | 5125 => 4,
                5123 | 5122 => 2,
                _ => 1,
            };
            let start =
                view["byteOffset"].as_u64().unwrap_or(0) as usize + a["byteOffset"].as_u64().unwrap_or(0) as usize;
            let stride = view["byteStride"].as_u64().map_or(size * n, |s| s as usize);
            let norm = a["normalized"].as_bool().unwrap_or(false);
            (0..a["count"].as_u64().unwrap_or(0) as usize)
                .map(|k| {
                    (0..n)
                        .map(|c| {
                            let o = start + k * stride + c * size;
                            let b = &bin[o..o + size];
                            match ty {
                                5126 => f32::from_le_bytes([b[0], b[1], b[2], b[3]]),
                                5125 => u32::from_le_bytes([b[0], b[1], b[2], b[3]]) as f32,
                                5123 => u16::from_le_bytes([b[0], b[1]]) as f32 / if norm { 65535.0 } else { 1.0 },
                                _ => b[0] as f32 / if norm { 255.0 } else { 1.0 },
                            }
                        })
                        .collect()
                })
                .collect()
        };
        let mut out = Vec::new();
        for mesh in js["meshes"].as_array()? {
            for prim in mesh["primitives"].as_array()? {
                let m = prim["material"].as_u64()? as usize;
                if js["materials"][m]["name"].as_str()? != material {
                    continue;
                }
                let at = |name: &str| prim["attributes"][name].as_u64().map(|i| accessor(i as usize));
                let positions: Vec<Vec3> = at("POSITION")?.iter().map(|v| Vec3::new(v[0], v[1], v[2])).collect();
                let n = positions.len();
                let v3 = |v: Vec<Vec<f32>>| v.iter().map(|v| Vec3::new(v[0], v[1], v[2])).collect();
                out.push(LawnSurface {
                    normals: at("NORMAL").map_or(vec![Vec3::Y; n], v3),
                    tangents: vec![Vec4::new(1.0, 0.0, 0.0, 1.0); n],
                    uvs: at("TEXCOORD_0")
                        .map_or(vec![Vec2::ZERO; n], |v| v.iter().map(|v| Vec2::new(v[0], v[1])).collect()),
                    masks: at("COLOR_0")
                        .map_or(vec![Vec4::ZERO; n], |v| v.iter().map(|v| Vec4::new(v[0], v[1], v[2], v[3])).collect()),
                    indices: accessor(prim["indices"].as_u64()? as usize).iter().map(|v| v[0] as u32).collect(),
                    positions,
                });
            }
        }
        Some(out)
    }

    #[test]
    fn tufts_on_the_real_lawn_follow_its_edges_and_stay_off_dirt_and_paving() {
        let Some(lawns) = kit_surfaces(LAWN_MATERIAL) else {
            eprintln!("ground.glb is not checked out (LFS); skipped");
            return;
        };
        let level = vetf_sim::maps::showhome();
        let t = tufts_data();
        let field = EdgeField::new(lawn_edges(&lawns), solid_footprints(&level), t.band + 1.0);
        let area = play_rect(&level, t.reach);
        let tufts = place_tufts(&lawns, &field, &t, t.density[2], area, 0x7475_6674);
        // Paving, paths, gravel, asphalt and beds: none of their triangles holds a tuft.
        let hard: Vec<LawnSurface> = ["M_GND_Paving", "M_GND_Gravel", "M_GND_Asphalt", "M_GND_Mulch", "M_GND_Soil"]
            .iter()
            .flat_map(|m| kit_surfaces(m).unwrap_or_default())
            .collect();
        let inside = |s: &LawnSurface, p: Vec2| {
            s.triangles().any(|tri| {
                let [a, b, c] = s.corners(tri).map(|v| Vec2::new(v.x, v.z));
                let side = |o: Vec2, u: Vec2| (u - o).perp_dot(p - o);
                let (d1, d2, d3) = (side(a, b), side(b, c), side(c, a));
                let neg = d1 < -1e-6 || d2 < -1e-6 || d3 < -1e-6;
                let pos = d1 > 1e-6 || d2 > 1e-6 || d3 > 1e-6;
                !(neg && pos)
            })
        };
        // The Sage lawn's east fence (x 27.35, z -25..-14.4): green lawn right up to it.
        let near_fence = |p: Vec2| (26.9..27.35).contains(&p.x) && (-25.0..-14.4).contains(&p.y);
        let mut fence = 0;
        for tf in &tufts {
            let p = Vec2::new(tf.root.x, tf.root.z);
            assert!(field.distance(p) <= t.band + 1e-3);
            assert!(!field.inside_solid(p, 0.0), "a tuft inside a wall, fence or hedge at {p}");
            fence += usize::from(near_fence(p));
        }
        for tf in tufts.iter().step_by(7) {
            let p = Vec2::new(tf.root.x, tf.root.z);
            assert!(!hard.iter().any(|s| inside(s, p)), "a tuft on paving, gravel, asphalt or a bed at {p}");
        }
        eprintln!("{} tufts on the kit lawn (HIGH), {fence} along the Sage lawn's east fence", tufts.len());
        assert!(tufts.len() > 1000, "{}", tufts.len());
        assert!(fence > 20, "{fence} tufts along the fence");
    }
}
