//! Exact convex-plane adapters. AABBs remain broad-phase metadata only.
pub use super::foliage::export_foliage as instantiate_foliage;
use super::{BuildError, Placements, PropCatalog, PropDescriptor, PropInstance, asset_path};
use glam::{DMat4, DQuat, DVec3, DVec4};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, fs, path::Path};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Aabb {
    pub min: [f64; 3],
    pub max: [f64; 3],
}
fn solid() -> String {
    "solid".into()
}
fn walkable() -> bool {
    true
}
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ConvexVolume {
    pub name: String,
    pub phys: String,
    #[serde(default = "solid")]
    pub kind: String,
    #[serde(default = "walkable")]
    pub walkable: bool,
    pub planes: Vec<[f64; 4]>,
    pub vertices: Vec<[f64; 3]>,
    pub aabb: Aabb,
    pub thickness_m: f64,
    #[serde(default)]
    pub parent: Option<String>,
    #[serde(flatten)]
    pub extras: BTreeMap<String, serde_json::Value>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CollisionDocument {
    pub schema: u32,
    pub frame: String,
    #[serde(default)]
    pub plane_convention: Option<String>,
    pub volumes: Vec<ConvexVolume>,
    #[serde(flatten)]
    pub extras: BTreeMap<String, serde_json::Value>,
}
impl CollisionDocument {
    pub fn load(path: &Path) -> Result<Self, BuildError> {
        let doc: Self = serde_json::from_slice(&fs::read(path)?)?;
        doc.validate()?;
        Ok(doc)
    }
    pub fn validate(&self) -> Result<(), BuildError> {
        if self.schema != 1 {
            return Err(BuildError::Invalid("Unsupported collision schema".into()));
        }
        for v in &self.volumes {
            let allowed = [
                "glass",
                "wood_thin",
                "wood_thick",
                "sheet_metal",
                "metal_heavy",
                "drywall",
                "concrete",
                "brick",
                "cladding",
                "foliage_thin",
                "foliage_dense",
                "fabric",
                "plastic",
                "soil",
                "grass",
                "gravel",
                "sand",
                "asphalt",
                "paving",
                "water",
            ];
            if !allowed.contains(&v.phys.as_str())
                || v.planes.len() < 4
                || v.vertices.len() < 4
                || !v.thickness_m.is_finite()
                || v.thickness_m <= 0.0
            {
                return Err(BuildError::Invalid(format!("Invalid convex volume {}", v.name)));
            }
            for p in &v.planes {
                if !p.iter().all(|x| x.is_finite()) || DVec3::new(p[0], p[1], p[2]).length() < 0.99 {
                    return Err(BuildError::Invalid(format!("Invalid plane in {}", v.name)));
                }
            }
            for point in &v.vertices {
                if !point.iter().all(|x| x.is_finite()) || !v.contains(*point, 0.002) {
                    return Err(BuildError::Invalid(format!("Vertex outside convex planes in {}", v.name)));
                }
            }
        }
        Ok(())
    }
    pub fn in_bevy(&self, origin: [f64; 3]) -> Result<Vec<ConvexVolume>, BuildError> {
        let matrix = design_to_bevy_matrix(origin);
        let mut rows = self.volumes.iter().map(|v| v.transformed(matrix)).collect::<Result<Vec<_>, _>>()?;
        rows.sort_by(|a, b| a.name.cmp(&b.name));
        Ok(rows)
    }
}
impl ConvexVolume {
    pub fn contains(&self, p: [f64; 3], epsilon: f64) -> bool {
        self.planes.iter().all(|q| q[0] * p[0] + q[1] * p[1] + q[2] * p[2] <= q[3] + epsilon)
    }
    /// Covectors transform with inverse-transpose, including translation and scale.
    pub fn transformed(&self, matrix: DMat4) -> Result<Self, BuildError> {
        if !matrix.is_finite() || matrix.determinant().abs() < 1e-12 {
            return Err(BuildError::Invalid("Singular collision transform".into()));
        }
        let covector = matrix.inverse().transpose();
        let mut out = self.clone();
        out.vertices =
            self.vertices.iter().map(|v| matrix.transform_point3(DVec3::from_array(*v)).to_array()).collect();
        out.planes = self
            .planes
            .iter()
            .map(|q| {
                let p = covector * DVec4::new(q[0], q[1], q[2], -q[3]);
                let length = p.truncate().length();
                [p.x / length, p.y / length, p.z / length, -p.w / length]
            })
            .collect();
        out.aabb = Aabb {
            min: std::array::from_fn(|k| out.vertices.iter().map(|v| v[k]).fold(f64::INFINITY, f64::min)),
            max: std::array::from_fn(|k| out.vertices.iter().map(|v| v[k]).fold(f64::NEG_INFINITY, f64::max)),
        };
        out.thickness_m = out
            .planes
            .iter()
            .map(|q| {
                let dots: Vec<_> = out.vertices.iter().map(|v| q[0] * v[0] + q[1] * v[1] + q[2] * v[2]).collect();
                dots.iter().copied().fold(f64::NEG_INFINITY, f64::max)
                    - dots.iter().copied().fold(f64::INFINITY, f64::min)
            })
            .fold(f64::INFINITY, f64::min);
        Ok(out)
    }
}

pub fn design_basis() -> DMat4 {
    DMat4::from_cols(DVec4::new(1., 0., 0., 0.), DVec4::new(0., 0., -1., 0.), DVec4::new(0., 1., 0., 0.), DVec4::W)
}
pub fn design_to_bevy_matrix(origin: [f64; 3]) -> DMat4 {
    design_basis() * DMat4::from_translation(-DVec3::from_array(origin))
}
pub fn design_to_bevy(point: [f64; 3], origin: [f64; 3]) -> [f64; 3] {
    design_to_bevy_matrix(origin).transform_point3(DVec3::from_array(point)).to_array()
}
pub fn instance_design_matrix(instance: &PropInstance) -> DMat4 {
    let tilt = instance.tilt_deg.unwrap_or([0., 0.]);
    let rotation = DQuat::from_rotation_z(instance.yaw_deg.to_radians())
        * DQuat::from_rotation_y(tilt[1].to_radians())
        * DQuat::from_rotation_x(tilt[0].to_radians());
    DMat4::from_scale_rotation_translation(DVec3::splat(instance.scale), rotation, DVec3::from_array(instance.position))
}

/// Only GLB's JSON chunk is required; geometry stays in the render asset.
pub fn glb_json(bytes: &[u8]) -> Result<serde_json::Value, BuildError> {
    let u32_at = |offset: usize| -> Result<u32, BuildError> {
        let slice = bytes.get(offset..offset + 4).ok_or_else(|| BuildError::Invalid("Truncated GLB".into()))?;
        Ok(u32::from_le_bytes(slice.try_into().unwrap()))
    };
    if u32_at(0)? != 0x46546c67 || u32_at(4)? != 2 || u32_at(8)? as usize != bytes.len() {
        return Err(BuildError::Invalid("Invalid GLB header".into()));
    }
    let mut offset = 12;
    while offset + 8 <= bytes.len() {
        let count = u32_at(offset)? as usize;
        let kind = u32_at(offset + 4)?;
        let end = (offset + 8).checked_add(count).ok_or_else(|| BuildError::Invalid("GLB chunk overflow".into()))?;
        let chunk = bytes.get(offset + 8..end).ok_or_else(|| BuildError::Invalid("Truncated GLB chunk".into()))?;
        if kind == 0x4e4f534a {
            return Ok(serde_json::from_slice(chunk)?);
        }
        offset = end;
    }
    Err(BuildError::Invalid("GLB has no JSON chunk".into()))
}

#[derive(Debug, Deserialize)]
struct Node {
    #[serde(default)]
    name: String,
    #[serde(default)]
    translation: Option<[f64; 3]>,
    #[serde(default)]
    rotation: Option<[f64; 4]>,
    #[serde(default)]
    scale: Option<[f64; 3]>,
    #[serde(default)]
    matrix: Option<[f64; 16]>,
    #[serde(default)]
    children: Vec<usize>,
}
impl Node {
    fn local(&self) -> DMat4 {
        if let Some(matrix) = self.matrix {
            DMat4::from_cols_array(&matrix)
        } else {
            DMat4::from_scale_rotation_translation(
                DVec3::from_array(self.scale.unwrap_or([1.; 3])),
                DQuat::from_array(self.rotation.unwrap_or([0., 0., 0., 1.])),
                DVec3::from_array(self.translation.unwrap_or([0.; 3])),
            )
        }
    }
}
#[derive(Debug, Deserialize)]
struct Nodes {
    nodes: Vec<Node>,
}
pub fn glb_node_world_matrices(bytes: &[u8]) -> Result<BTreeMap<String, DMat4>, BuildError> {
    let graph: Nodes = serde_json::from_value(glb_json(bytes)?)?;
    let mut parents = vec![None; graph.nodes.len()];
    for (parent, node) in graph.nodes.iter().enumerate() {
        for &child in &node.children {
            if child >= parents.len() || parents[child].replace(parent).is_some() {
                return Err(BuildError::Invalid("Invalid GLB node hierarchy".into()));
            }
        }
    }
    fn world(
        i: usize,
        nodes: &[Node],
        parents: &[Option<usize>],
        cache: &mut [Option<DMat4>],
        visiting: &mut [bool],
    ) -> Result<DMat4, BuildError> {
        if let Some(matrix) = cache[i] {
            return Ok(matrix);
        }
        if visiting[i] {
            return Err(BuildError::Invalid("GLB node cycle".into()));
        }
        visiting[i] = true;
        let matrix = if let Some(parent) = parents[i] {
            world(parent, nodes, parents, cache, visiting)? * nodes[i].local()
        } else {
            nodes[i].local()
        };
        if !matrix.is_finite() {
            return Err(BuildError::Invalid("Non-finite GLB node transform".into()));
        }
        cache[i] = Some(matrix);
        visiting[i] = false;
        Ok(matrix)
    }
    let mut cache = vec![None; graph.nodes.len()];
    let mut visiting = vec![false; graph.nodes.len()];
    let mut result = BTreeMap::new();
    for (i, node) in graph.nodes.iter().enumerate() {
        let matrix = world(i, &graph.nodes, &parents, &mut cache, &mut visiting)?;
        if !node.name.is_empty() && result.insert(node.name.clone(), matrix).is_some() {
            return Err(BuildError::Invalid(format!("Duplicate GLB node {}", node.name)));
        }
    }
    Ok(result)
}

/// Source COLL vertices already contain the authored ajar/open pose. This delta
/// closes a container using the OPEN node's actual pivot and world matrix.
/// Structural gates/toilets are outside category=containers and remain authored.
pub fn closed_container_delta(
    descriptor: &PropDescriptor,
    parent: &str,
    nodes: &BTreeMap<String, DMat4>,
) -> Result<DMat4, BuildError> {
    let part = descriptor
        .openable_parts
        .iter()
        .find(|p| p.name == parent)
        .ok_or_else(|| BuildError::Missing(format!("OPEN metadata {parent}")))?;
    let old_glb = *nodes.get(parent).ok_or_else(|| BuildError::Missing(format!("OPEN GLB node {parent}")))?;
    let basis = design_basis();
    let old = basis.inverse() * old_glb * basis;
    let pivot = if parent.starts_with("OPEN_DRAWER_") {
        part.properties
            .closed_location
            .ok_or_else(|| BuildError::Invalid(format!("Drawer {parent} lacks closed_location")))?
    } else {
        old.w_axis.truncate().to_array()
    };
    let closed = DMat4::from_translation(DVec3::from_array(pivot));
    if old.determinant().abs() < 1e-12 {
        return Err(BuildError::Invalid("Singular OPEN world matrix".into()));
    }
    Ok(closed * old.inverse())
}

/// Deterministic order: stable instance id, then source volume name. The complete
/// affine transform is applied to planes/vertices. `None` inspects all modes;
/// `Some("tdm")` emits default-all and tdm instances only.
pub fn instantiate_props(
    assets_root: &Path,
    catalog: &PropCatalog,
    placements: &Placements,
    active_mode: Option<&str>,
) -> Result<Vec<ConvexVolume>, BuildError> {
    placements.validate()?;
    let mut instances = placements
        .instances
        .iter()
        .filter(|p| active_mode.is_none_or(|m| p.mode == "all" || p.mode == m))
        .collect::<Vec<_>>();
    instances.sort_by(|a, b| a.id.cmp(&b.id));
    let mut documents: BTreeMap<String, CollisionDocument> = BTreeMap::new();
    let mut graphs: BTreeMap<String, BTreeMap<String, DMat4>> = BTreeMap::new();
    let mut output = vec![];
    for instance in instances {
        let descriptor = catalog.get(&instance.prop_id)?;
        if !documents.contains_key(&descriptor.id) {
            documents.insert(
                descriptor.id.clone(),
                CollisionDocument::load(&asset_path(assets_root, Path::new(&descriptor.collision))?)?,
            );
        }
        let close = descriptor.category == "containers" && !instance.lootable;
        if close && !graphs.contains_key(&descriptor.id) {
            graphs.insert(
                descriptor.id.clone(),
                glb_node_world_matrices(&fs::read(asset_path(assets_root, Path::new(&descriptor.glb))?)?)?,
            );
        }
        let matrix = design_to_bevy_matrix(placements.origin) * instance_design_matrix(instance);
        let mut rows = documents[&descriptor.id].volumes.iter().collect::<Vec<_>>();
        rows.sort_by(|a, b| a.name.cmp(&b.name));
        for row in rows {
            let delta = if close {
                if let Some(parent) = row.parent.as_deref().filter(|name| name.starts_with("OPEN_")) {
                    closed_container_delta(descriptor, parent, &graphs[&descriptor.id])?
                } else {
                    DMat4::IDENTITY
                }
            } else {
                DMat4::IDENTITY
            };
            let mut transformed = row.transformed(matrix * delta)?;
            transformed.name = format!("{}__{}", instance.id, row.name);
            transformed.extras.insert("instance_id".into(), instance.id.clone().into());
            transformed.extras.insert("mode".into(), instance.mode.clone().into());
            output.push(transformed);
        }
    }
    Ok(output)
}
