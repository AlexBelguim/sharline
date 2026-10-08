//! The art kit's surface under a bullet mark (Showhome).
//!
//! The collision brushes say where a shot hit and on which face, but the art kit draws its own surface there,
//! often a few millimetres in front of the brush face (lawn +6 mm, paving +10 mm, interior concrete +8 mm,
//! shingles +5-10 mm, solar panels +20 mm) or behind it, and made of something other than the brush's look
//! guessed (the sage fibre-cement garden wall is a `Wall` brush, paving lies on `Ground` brushes, the kerbs are
//! invisible steps). A mark lifted off the brush face alone was buried under the kit, and its kind was often the
//! wrong material.
//!
//! So once the kit's houses, ground and props have spawned, every kit triangle inside the level's bounds goes
//! into a bounding-volume hierarchy, built off the main thread. A mark casts a short segment along its face
//! normal through its centre and corners: the nearest kit surface facing the shot gives its height over the face
//! (the mark sits on the highest), and the centre's triangle gives the material: `kit` in `data/impacts.ron`
//! maps every kit material to a kind (or none: hedges, plants) and its average colour, which the triangle's
//! vertex colour tints (the houses paint their cladding with vertex colours; on the blended ground they are
//! masks, so those triangles are white).

use crate::config::CurrentLevel;
use crate::showhome_kit::{ShowhomeKitMesh, ShowhomeKitPart, is_showhome};
use bevy::gltf::GltfMaterialName;
use bevy::mesh::{PrimitiveTopology, VertexAttributeValues};
use bevy::prelude::*;
use bevy::tasks::{AsyncComputeTaskPool, Task, futures::check_ready};
use std::collections::HashMap;
use vetf_sim::movement::collision::CollisionWorld;

/// How far in front of (and behind) a brush face the kit's surface is looked for.
pub const REACH_M: f32 = 0.04;
/// A corner of a mark raises it at most this far above the kit surface at its centre (a drainpipe or a sill in
/// front of a wall must not lift the whole mark off the wall).
pub const CORNER_RISE_M: f32 = 0.02;
/// Kit triangles this far outside the level's bullet-blocking brushes are left out (the skirt, the backdrop).
const BOUNDS_MARGIN_M: f32 = 0.25;
/// Frames without a new kit mesh before the triangles are gathered (their transforms have propagated).
const SETTLE_FRAMES: u32 = 3;
/// Triangles per BVH leaf.
const LEAF: usize = 4;

/// One kit triangle in world space: its corners, its material (an index into [`KitSurfaces::materials`]) and the
/// vertex colour that tints it, linear, 0-255 (white where the vertex colours are blend masks).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct KitTri {
    pub v: [Vec3; 3],
    pub material: u16,
    pub color: [u8; 3],
}

impl KitTri {
    fn centroid(&self, axis: usize) -> f32 {
        self.v[0][axis] + self.v[1][axis] + self.v[2][axis]
    }

    /// Möller-Trumbore, front faces only (wound counter-clockwise toward the segment's start): the distance along
    /// `dir` from `from`, if within `len`.
    fn hit(&self, from: Vec3, dir: Vec3, len: f32) -> Option<f32> {
        let [a, b, c] = self.v;
        let (e1, e2) = (b - a, c - a);
        let p = dir.cross(e2);
        let det = e1.dot(p);
        if det <= 1e-12 {
            return None;
        }
        let inv = 1.0 / det;
        let s = from - a;
        let u = s.dot(p) * inv;
        if !(0.0..=1.0).contains(&u) {
            return None;
        }
        let q = s.cross(e1);
        let v = dir.dot(q) * inv;
        if v < 0.0 || u + v > 1.0 {
            return None;
        }
        let t = e2.dot(q) * inv;
        (0.0..=len).contains(&t).then_some(t)
    }
}

#[derive(Clone, Copy, Debug, Default)]
struct Node {
    min: Vec3,
    max: Vec3,
    /// A leaf's first triangle, or an inner node's left child (its right child follows it).
    first: u32,
    /// Triangles in a leaf; 0 for an inner node.
    count: u32,
}

/// Triangles in a bounding-volume hierarchy (median splits along the longest axis), for short segment casts.
#[derive(Default)]
pub struct SurfaceBvh {
    tris: Vec<KitTri>,
    nodes: Vec<Node>,
}

impl SurfaceBvh {
    pub fn build(mut tris: Vec<KitTri>) -> SurfaceBvh {
        if tris.is_empty() {
            return SurfaceBvh::default();
        }
        let mut nodes = Vec::with_capacity(tris.len() / LEAF * 2 + 1);
        nodes.push(Node::default());
        let mut stack = vec![(0usize, 0usize, tris.len())];
        while let Some((at, start, end)) = stack.pop() {
            let (mut min, mut max) = (Vec3::splat(f32::MAX), Vec3::splat(f32::MIN));
            let (mut cmin, mut cmax) = (Vec3::splat(f32::MAX), Vec3::splat(f32::MIN));
            for t in &tris[start..end] {
                for v in t.v {
                    (min, max) = (min.min(v), max.max(v));
                }
                let c = Vec3::new(t.centroid(0), t.centroid(1), t.centroid(2));
                (cmin, cmax) = (cmin.min(c), cmax.max(c));
            }
            nodes[at].min = min;
            nodes[at].max = max;
            let extent = cmax - cmin;
            let axis = if extent.x >= extent.y && extent.x >= extent.z {
                0
            } else if extent.y >= extent.z {
                1
            } else {
                2
            };
            if end - start <= LEAF || extent[axis] <= 0.0 {
                (nodes[at].first, nodes[at].count) = (start as u32, (end - start) as u32);
                continue;
            }
            let mid = start + (end - start) / 2;
            tris[start..end].select_nth_unstable_by(mid - start, |a, b| a.centroid(axis).total_cmp(&b.centroid(axis)));
            let left = nodes.len();
            nodes.push(Node::default());
            nodes.push(Node::default());
            (nodes[at].first, nodes[at].count) = (left as u32, 0);
            stack.push((left, start, mid));
            stack.push((left + 1, mid, end));
        }
        SurfaceBvh { tris, nodes }
    }

    pub fn len(&self) -> usize {
        self.tris.len()
    }

    /// The nearest front face along the segment from `from` along the unit `dir`, at most `len` away.
    pub fn cast(&self, from: Vec3, dir: Vec3, len: f32) -> Option<(f32, &KitTri)> {
        if self.nodes.is_empty() {
            return None;
        }
        let inv = dir.recip();
        let mut best: Option<(f32, usize)> = None;
        let mut stack = vec![0usize];
        while let Some(i) = stack.pop() {
            let node = &self.nodes[i];
            let reach = best.map_or(len, |(t, _)| t);
            if !slab(from, inv, node.min, node.max, reach) {
                continue;
            }
            if node.count == 0 {
                stack.push(node.first as usize);
                stack.push(node.first as usize + 1);
                continue;
            }
            for k in node.first as usize..(node.first + node.count) as usize {
                if let Some(t) = self.tris[k].hit(from, dir, reach)
                    && best.is_none_or(|(b, _)| t < b)
                {
                    best = Some((t, k));
                }
            }
        }
        best.map(|(t, k)| (t, &self.tris[k]))
    }
}

/// Whether the segment from `from` (direction reciprocal `inv`) meets the box within `len`.
fn slab(from: Vec3, inv: Vec3, min: Vec3, max: Vec3, len: f32) -> bool {
    let (a, b) = ((min - from) * inv, (max - from) * inv);
    let (near, far) = (a.min(b), a.max(b));
    // NaN (a zero direction on a box face) is ignored by max / min
    let enter = near.x.max(near.y).max(near.z).max(0.0);
    let exit = far.x.min(far.y).min(far.z).min(len);
    enter <= exit + 1e-6
}

enum Build {
    /// Waiting for the kit to spawn; the frames since a kit mesh last appeared.
    Waiting(u32),
    Building(Task<SurfaceBvh>),
    Ready(SurfaceBvh),
}

impl Default for Build {
    fn default() -> Self {
        Build::Waiting(0)
    }
}

/// The kit's surfaces for marks, once built (kept across matches: the kit does not move).
#[derive(Resource, Default)]
pub struct KitSurfaces {
    /// Material names (without Blender's `.001` suffixes), indexed by [`KitTri::material`].
    pub materials: Vec<String>,
    build: Build,
}

/// The kit's surface found under a point of a face.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct KitHit<'a> {
    /// How far in front of the face it is (negative: behind it).
    pub offset: f32,
    pub tri: &'a KitTri,
}

impl KitSurfaces {
    /// Surfaces ready at once for the given triangles.
    #[cfg(test)]
    pub fn ready(materials: Vec<String>, tris: Vec<KitTri>) -> KitSurfaces {
        KitSurfaces { materials, build: Build::Ready(SurfaceBvh::build(tris)) }
    }

    pub fn bvh(&self) -> Option<&SurfaceBvh> {
        match &self.build {
            Build::Ready(b) => Some(b),
            _ => None,
        }
    }

    /// The kit's surface over `point` (on a face with outward normal `n`), within [`REACH_M`] of the face.
    pub fn at(&self, point: Vec3, n: Vec3) -> Option<KitHit<'_>> {
        let (t, tri) = self.bvh()?.cast(point + n * REACH_M, -n, 2.0 * REACH_M)?;
        Some(KitHit { offset: REACH_M - t, tri })
    }

    pub fn material(&self, tri: &KitTri) -> &str {
        self.materials.get(tri.material as usize).map_or("", String::as_str)
    }
}

/// A glTF material name without Blender's numeric suffix (`M_GND_Paving.001` -> `M_GND_Paving`).
pub fn canonical(name: &str) -> &str {
    name.rsplit_once('.')
        .filter(|(_, suffix)| !suffix.is_empty() && suffix.chars().all(|c| c.is_ascii_digit()))
        .map_or(name, |(base, _)| base)
}

/// The box the level's bullet-blocking brushes fill, grown by `margin`.
fn level_bounds(world: &CollisionWorld, margin: f32) -> Option<(Vec3, Vec3)> {
    let mut it = world.brushes.iter().filter(|b| b.blocks_bullets());
    let first = it.next()?;
    let (min, max) = it.fold((first.min, first.max), |(a, b), br| (a.min(br.min), b.max(br.max)));
    Some((min - Vec3::splat(margin), max + Vec3::splat(margin)))
}

/// A mesh's triangles in world space, those touching `bounds` only; `color` false leaves them white.
pub fn mesh_triangles(
    mesh: &Mesh,
    transform: &GlobalTransform,
    material: u16,
    color: bool,
    bounds: (Vec3, Vec3),
    out: &mut Vec<KitTri>,
) {
    if mesh.primitive_topology() != PrimitiveTopology::TriangleList {
        return;
    }
    let Some(positions) = mesh.attribute(Mesh::ATTRIBUTE_POSITION).and_then(|a| a.as_float3()) else { return };
    let colors: Option<Vec<[u8; 3]>> = match mesh.attribute(Mesh::ATTRIBUTE_COLOR).filter(|_| color) {
        Some(VertexAttributeValues::Float32x4(c)) => Some(c.iter().map(|c| linear_u8([c[0], c[1], c[2]])).collect()),
        Some(VertexAttributeValues::Float32x3(c)) => Some(c.iter().map(|c| linear_u8(*c)).collect()),
        _ => None,
    };
    let affine = transform.affine();
    let world: Vec<Vec3> = positions.iter().map(|p| affine.transform_point3(Vec3::from(*p))).collect();
    let mut push = |i: [usize; 3]| {
        if i.iter().any(|&k| k >= world.len()) {
            return;
        }
        let v = [world[i[0]], world[i[1]], world[i[2]]];
        let (lo, hi) = (v[0].min(v[1]).min(v[2]), v[0].max(v[1]).max(v[2]));
        if lo.cmpgt(bounds.1).any() || hi.cmplt(bounds.0).any() {
            return;
        }
        let color = colors.as_ref().map_or([255; 3], |c| {
            let [a, b, d] = [c[i[0]], c[i[1]], c[i[2]]];
            std::array::from_fn(|k| ((a[k] as u32 + b[k] as u32 + d[k] as u32) / 3) as u8)
        });
        out.push(KitTri { v, material, color });
    };
    match mesh.indices() {
        Some(indices) => {
            let idx: Vec<usize> = indices.iter().collect();
            for t in idx.as_chunks::<3>().0 {
                push(*t);
            }
        }
        None => {
            for k in (0..world.len() / 3).map(|t| t * 3) {
                push([k, k + 1, k + 2]);
            }
        }
    }
}

fn linear_u8(c: [f32; 3]) -> [u8; 3] {
    c.map(|v| (v.clamp(0.0, 1.0) * 255.0).round() as u8)
}

/// Gathers the kit's triangles once the houses, ground and props have spawned and settled, builds their BVH off
/// the main thread, and picks it up when done.
#[allow(clippy::type_complexity)]
pub fn build_kit_surfaces(
    level: Option<Res<CurrentLevel>>,
    mut kit: ResMut<KitSurfaces>,
    meshes: Res<Assets<Mesh>>,
    parts: Query<(&ShowhomeKitMesh, &Mesh3d, &GlobalTransform, &GltfMaterialName)>,
    added: Query<(), Added<ShowhomeKitMesh>>,
) {
    let Some(level) = level.filter(|l| is_showhome(l)) else { return };
    let kit = &mut *kit;
    match &mut kit.build {
        Build::Ready(_) => {}
        Build::Building(task) => {
            if let Some(bvh) = check_ready(task) {
                info!("Showhome kit surfaces for bullet marks: {} triangles", bvh.len());
                kit.build = Build::Ready(bvh);
            }
        }
        Build::Waiting(quiet) => {
            *quiet = if added.is_empty() { *quiet + 1 } else { 0 };
            let needed = [ShowhomeKitPart::Houses, ShowhomeKitPart::Ground, ShowhomeKitPart::Props];
            let spawned = needed.iter().all(|p| parts.iter().any(|(m, ..)| m.0 == *p));
            let loaded = parts.iter().all(|(_, mesh, ..)| meshes.contains(&mesh.0));
            if *quiet < SETTLE_FRAMES || !spawned || !loaded {
                return;
            }
            let Some(bounds) = level_bounds(&level.world, BOUNDS_MARGIN_M) else { return };
            let mut names: HashMap<String, u16> = HashMap::new();
            let mut tris = Vec::new();
            for (part, mesh, transform, name) in &parts {
                if part.0 == ShowhomeKitPart::Backdrop {
                    continue;
                }
                let Some(mesh) = meshes.get(&mesh.0) else { continue };
                let name = canonical(&name.0);
                let next = names.len() as u16;
                let material = *names.entry(name.to_string()).or_insert(next);
                // The blended ground's vertex colours are its layer masks, not a colour.
                let color = !crate::showhome_ground::is_ground_blend(name);
                mesh_triangles(mesh, transform, material, color, bounds, &mut tris);
            }
            let mut materials = vec![String::new(); names.len()];
            for (name, i) in names {
                materials[i as usize] = name;
            }
            kit.materials = materials;
            kit.build = Build::Building(AsyncComputeTaskPool::get().spawn(async move { SurfaceBvh::build(tris) }));
        }
    }
}

/// A square in the plane y = `h` facing +Y (two triangles wound counter-clockwise seen from above), white.
#[cfg(test)]
pub fn test_floor(min: Vec2, max: Vec2, h: f32, material: u16) -> [KitTri; 2] {
    let p = |x: f32, z: f32| Vec3::new(x, h, z);
    let tri = |v: [Vec3; 3]| KitTri { v, material, color: [255; 3] };
    [tri([p(min.x, min.y), p(min.x, max.y), p(max.x, max.y)]), tri([p(min.x, min.y), p(max.x, max.y), p(max.x, min.y)])]
}

#[cfg(test)]
mod tests {
    use super::*;
    use vetf_sim::rng::SplitMix;

    fn tri(a: Vec3, b: Vec3, c: Vec3, material: u16) -> KitTri {
        KitTri { v: [a, b, c], material, color: [255; 3] }
    }

    fn v3(rng: &mut SplitMix, s: Vec3) -> Vec3 {
        Vec3::new(rng.next_f32() - 0.5, rng.next_f32() - 0.5, rng.next_f32() - 0.5) * s
    }

    /// The BVH finds the same nearest front face as testing every triangle, on a random soup.
    #[test]
    fn the_bvh_agrees_with_brute_force() {
        let mut rng = SplitMix::from_parts(&[7]);
        let tris: Vec<KitTri> = (0..3000)
            .map(|i| {
                let c = v3(&mut rng, Vec3::new(20.0, 4.0, 20.0));
                let s = Vec3::splat(0.6);
                tri(c + v3(&mut rng, s), c + v3(&mut rng, s), c + v3(&mut rng, s), (i % 7) as u16)
            })
            .collect();
        let bvh = SurfaceBvh::build(tris.clone());
        assert_eq!(bvh.len(), tris.len());
        let mut hits = 0;
        for _ in 0..400 {
            let from = v3(&mut rng, Vec3::new(22.0, 6.0, 22.0));
            let dir = v3(&mut rng, Vec3::splat(2.0)).normalize_or(Vec3::Y);
            let brute =
                tris.iter().filter_map(|t| t.hit(from, dir, 8.0).map(|d| (d, *t))).min_by(|a, b| a.0.total_cmp(&b.0));
            let fast = bvh.cast(from, dir, 8.0).map(|(d, t)| (d, *t));
            assert_eq!(brute.map(|b| b.0), fast.map(|f| f.0), "from {from} along {dir}");
            hits += brute.is_some() as u32;
        }
        assert!(hits > 20, "the test casts hit something: {hits}");
    }

    /// Only faces wound toward the segment count, within its length.
    #[test]
    fn a_cast_takes_front_faces_within_reach() {
        let kit =
            KitSurfaces::ready(vec!["M_A".into()], test_floor(Vec2::splat(-1.0), Vec2::splat(1.0), 0.01, 0).to_vec());
        let hit = kit.at(Vec3::ZERO, Vec3::Y).expect("the floor 1 cm over the face");
        assert!((hit.offset - 0.01).abs() < 1e-5, "{}", hit.offset);
        assert_eq!(kit.material(hit.tri), "M_A");
        // from below the floor faces away
        assert!(kit.at(Vec3::new(0.0, 0.02, 0.0), Vec3::NEG_Y).is_none());
        // beyond the reach
        assert!(kit.at(Vec3::new(0.0, -0.06, 0.0), Vec3::Y).is_none());
        // off its edge
        assert!(kit.at(Vec3::new(1.5, 0.0, 0.0), Vec3::Y).is_none());
    }

    #[test]
    fn material_names_drop_blender_suffixes() {
        assert_eq!(canonical("M_GND_Paving.001"), "M_GND_Paving");
        assert_eq!(canonical("M_GND_Paving"), "M_GND_Paving");
        assert_eq!(canonical("M_v1.a"), "M_v1.a");
    }

    /// A mesh's triangles come out in world space, tinted by their vertex colours, and only inside the bounds.
    #[test]
    fn mesh_triangles_in_world_space() {
        use bevy::asset::RenderAssetUsages;
        use bevy::mesh::Indices;
        let mesh = Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default())
            .with_inserted_attribute(
                Mesh::ATTRIBUTE_POSITION,
                vec![[0.0f32, 0.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [50.0, 0.0, 0.0], [50.0, 0.0, 1.0]],
            )
            .with_inserted_attribute(Mesh::ATTRIBUTE_COLOR, vec![[1.0f32, 0.5, 0.0, 1.0]; 5])
            .with_inserted_indices(Indices::U32(vec![0, 1, 2, 3, 4, 2]));
        let at = GlobalTransform::from_xyz(0.0, 2.0, 0.0);
        let mut out = Vec::new();
        mesh_triangles(&mesh, &at, 3, true, (Vec3::splat(-5.0), Vec3::splat(5.0)), &mut out);
        assert_eq!(out.len(), 2, "the second triangle reaches into the bounds");
        assert_eq!(out[0].v[1], Vec3::new(0.0, 2.0, 1.0));
        assert_eq!((out[0].material, out[0].color), (3, [255, 128, 0]));
        out.clear();
        mesh_triangles(&mesh, &at, 3, false, (Vec3::splat(-5.0), Vec3::new(5.0, 1.0, 5.0)), &mut out);
        assert!(out.is_empty(), "above the bounds");
        mesh_triangles(&mesh, &GlobalTransform::IDENTITY, 3, false, (Vec3::splat(-5.0), Vec3::splat(5.0)), &mut out);
        assert_eq!(out[0].color, [255; 3], "masks, not colours: white");
    }
}
