//! Editable envelopes for the existing foliage system. This module creates data
//! and matching convex collision; it does not create leaf cards or modify a kit.
use super::collision::{Aabb, ConvexVolume, design_basis, design_to_bevy_matrix};
use super::{BuildError, Placements, array3, finite};
use glam::{DMat4, DVec3};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub enum FoliageKind {
    #[default]
    Hedge,
    Bush,
    Tree,
    Climber,
}
impl FoliageKind {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Hedge => "hedge",
            Self::Bush => "bush",
            Self::Tree => "tree",
            Self::Climber => "climber",
        }
    }
    pub fn phys(self) -> &'static str {
        match self {
            Self::Hedge | Self::Bush => "foliage_dense",
            Self::Tree | Self::Climber => "foliage_thin",
        }
    }
}
impl From<FoliageKind> for String {
    fn from(value: FoliageKind) -> Self {
        value.as_str().into()
    }
}
impl TryFrom<String> for FoliageKind {
    type Error = String;
    fn try_from(value: String) -> Result<Self, Self::Error> {
        match value.as_str() {
            "hedge" => Ok(Self::Hedge),
            "bush" => Ok(Self::Bush),
            "tree" => Ok(Self::Tree),
            "climber" => Ok(Self::Climber),
            _ => Err(format!("Unknown foliage kind {value}")),
        }
    }
}
fn dimensions() -> [f64; 3] {
    [2.0, 1.0, 2.0]
}
fn density() -> f64 {
    1.0
}
fn tint() -> String {
    "sage_hedge".into()
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FoliageVolume {
    pub id: String,
    #[serde(default)]
    pub kind: FoliageKind,
    /// Ground-centre pivot in design world XYZ metres; Z is the envelope bottom.
    #[serde(default, deserialize_with = "array3")]
    pub position: [f64; 3],
    #[serde(default)]
    pub yaw_deg: f64,
    /// Local X run width, local Y depth and Z height. All must be positive/finite.
    #[serde(default = "dimensions", deserialize_with = "array3")]
    pub dimensions_m: [f64; 3],
    /// Nonnegative multiplier for existing leaf density; zero retains the envelope.
    #[serde(default = "density")]
    pub density: f64,
    /// Existing foliage palette token, carried unchanged to the renderer adapter.
    #[serde(default = "tint")]
    pub tint: String,
    #[serde(default)]
    pub locked: bool,
    #[serde(default = "super::all_mode")]
    pub mode: String,
}
impl FoliageVolume {
    pub fn new(id: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            kind: FoliageKind::default(),
            position: [0.; 3],
            yaw_deg: 0.,
            dimensions_m: dimensions(),
            density: density(),
            tint: tint(),
            locked: false,
            mode: super::all_mode(),
        }
    }
    pub fn validate(&self) -> Result<(), BuildError> {
        finite(&self.position)?;
        finite(&self.dimensions_m)?;
        finite(&[self.yaw_deg, self.density])?;
        if self.id.is_empty() || self.dimensions_m.iter().any(|v| *v <= 0.) || self.density < 0. || self.tint.is_empty()
        {
            return Err(BuildError::Invalid(format!(
                "Foliage {} needs a stable id, positive dimensions, nonnegative density and tint",
                self.id
            )));
        }
        Ok(())
    }
    /// Explicit caller-controlled conversion; no kit volume is automatically copied.
    pub fn from_authoring_aabb(
        id: impl Into<String>,
        kind: FoliageKind,
        aabb: &Aabb,
        density: f64,
        tint: String,
    ) -> Result<Self, BuildError> {
        finite(&aabb.min)?;
        finite(&aabb.max)?;
        let mut volume = Self::new(id);
        volume.kind = kind;
        volume.position = [(aabb.min[0] + aabb.max[0]) / 2., (aabb.min[1] + aabb.max[1]) / 2., aabb.min[2]];
        volume.dimensions_m = std::array::from_fn(|k| aabb.max[k] - aabb.min[k]);
        volume.density = density;
        volume.tint = tint;
        volume.validate()?;
        Ok(volume)
    }
}

/// Adapter output for the existing mesh builders: generate within the local Bevy
/// bounds and apply transform_bevy. world_bounds_bevy is broad-phase information;
/// it must not replace the rotated convex collider or inflate the rendered hedge.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FoliageExport {
    pub id: String,
    pub kind: FoliageKind,
    pub position_design: [f64; 3],
    pub dimensions_m: [f64; 3],
    pub yaw_deg: f64,
    pub density: f64,
    pub tint: String,
    pub locked: bool,
    pub mode: String,
    pub local_bounds_bevy: Aabb,
    /// Column-major affine transform, including document origin and positive Y yaw.
    pub transform_bevy: [f64; 16],
    pub world_bounds_bevy: Aabb,
    pub collision: ConvexVolume,
}

pub fn export_foliage(document: &Placements, active_mode: Option<&str>) -> Result<Vec<FoliageExport>, BuildError> {
    document.validate()?;
    let mut volumes = document
        .foliage_volumes
        .iter()
        .filter(|v| active_mode.is_none_or(|m| v.mode == "all" || v.mode == m))
        .collect::<Vec<_>>();
    volumes.sort_by(|a, b| a.id.cmp(&b.id));
    let mut result = vec![];
    for volume in volumes {
        let [width, depth, height] = volume.dimensions_m;
        let (rx, ry) = (width / 2., depth / 2.);
        let vertices = vec![
            [-rx, -ry, 0.],
            [rx, -ry, 0.],
            [rx, ry, 0.],
            [-rx, ry, 0.],
            [-rx, -ry, height],
            [rx, -ry, height],
            [rx, ry, height],
            [-rx, ry, height],
        ];
        let planes = vec![
            [-1., 0., 0., rx],
            [1., 0., 0., rx],
            [0., -1., 0., ry],
            [0., 1., 0., ry],
            [0., 0., -1., 0.],
            [0., 0., 1., height],
        ];
        let local = ConvexVolume {
            name: format!("COL_FOL_{}_{}", volume.kind.as_str(), volume.id),
            phys: volume.kind.phys().into(),
            kind: "solid".into(),
            walkable: true,
            planes,
            vertices,
            aabb: Aabb { min: [-rx, -ry, 0.], max: [rx, ry, height] },
            thickness_m: width.min(depth).min(height),
            parent: None,
            extras: BTreeMap::from([
                ("editable_id".into(), volume.id.clone().into()),
                ("foliage".into(), volume.kind.as_str().into()),
                ("density".into(), volume.density.into()),
                ("tint".into(), volume.tint.clone().into()),
                ("mode".into(), volume.mode.clone().into()),
            ]),
        };
        let local_design = DMat4::from_translation(DVec3::from_array(volume.position))
            * DMat4::from_rotation_z(volume.yaw_deg.to_radians());
        let world_design_to_bevy = design_to_bevy_matrix(document.origin) * local_design;
        let collision = local.transformed(world_design_to_bevy)?;
        // The renderer builds in local Bevy axes; remove the source design basis.
        let transform = world_design_to_bevy * design_basis().inverse();
        result.push(FoliageExport {
            id: volume.id.clone(),
            kind: volume.kind,
            position_design: volume.position,
            dimensions_m: volume.dimensions_m,
            yaw_deg: volume.yaw_deg,
            density: volume.density,
            tint: volume.tint.clone(),
            locked: volume.locked,
            mode: volume.mode.clone(),
            local_bounds_bevy: Aabb { min: [-rx, 0., -ry], max: [rx, height, ry] },
            transform_bevy: transform.to_cols_array(),
            world_bounds_bevy: collision.aabb.clone(),
            collision,
        });
    }
    Ok(result)
}

/// Read an authoring foliage.json into proposed editable records, only when a
/// caller explicitly requests migration. The source kit/file is never modified.
pub fn import_authoring_foliage(json: &str, id_prefix: &str) -> Result<Vec<FoliageVolume>, BuildError> {
    #[derive(Deserialize)]
    #[serde(untagged)]
    enum Source {
        Versioned { schema: u32, volumes: Vec<SourceVolume> },
        Legacy(Vec<SourceVolume>),
    }
    #[derive(Deserialize)]
    struct SourceVolume {
        name: String,
        foliage: FoliageKind,
        aabb: Aabb,
        #[serde(default = "density")]
        density: f64,
        #[serde(default = "tint")]
        tint: String,
    }
    if id_prefix.is_empty() {
        return Err(BuildError::Invalid("Editable foliage import needs an explicit id prefix".into()));
    }
    let source: Source = serde_json::from_str(json)?;
    let volumes = match source {
        Source::Versioned { schema: 1, volumes } | Source::Legacy(volumes) => volumes,
        Source::Versioned { .. } => return Err(BuildError::Invalid("Unsupported authoring foliage schema".into())),
    };
    let mut result = vec![];
    let mut ids = std::collections::BTreeSet::new();
    for v in volumes {
        let id = format!("{id_prefix}{}", v.name);
        if !ids.insert(id.clone()) {
            return Err(BuildError::Invalid("Duplicate authoring foliage name".into()));
        }
        result.push(FoliageVolume::from_authoring_aabb(id, v.foliage, &v.aabb, v.density, v.tint)?);
    }
    Ok(result)
}
