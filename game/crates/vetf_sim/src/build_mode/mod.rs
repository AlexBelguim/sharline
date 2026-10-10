//! Engine-free editable map layer. Loading/inspection never writes user placements.
//! Coordinates in saved documents are design world metres; collision adapters use
//! Bevy `(x,z,-y)` relative to the document origin. No client UI or handshake is wired here.

pub mod collision;
pub mod foliage;
pub use foliage::{FoliageKind, FoliageVolume};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

#[derive(Debug, thiserror::Error)]
pub enum BuildError {
    #[error("{0}")]
    Invalid(String),
    #[error("Item {0} is locked")]
    Locked(String),
    #[error("Item {0} does not exist")]
    Missing(String),
    #[error("User placements changed on disk; reload before saving")]
    SaveConflict,
    #[error("RON: {0}")]
    Ron(String),
    #[error("JSON: {0}")]
    Json(#[from] serde_json::Error),
    #[error("Filesystem: {0}")]
    Io(#[from] std::io::Error),
}

fn one() -> f64 {
    1.0
}
fn all_mode() -> String {
    "all".into()
}
fn is_false(value: &bool) -> bool {
    !*value
}
fn design_frame() -> String {
    "design world XYZ metres".into()
}
fn player_clip_kind() -> String {
    "player_clip".into()
}
fn concrete() -> String {
    "concrete".into()
}
fn sphere() -> String {
    "sphere".into()
}
fn always() -> String {
    "always".into()
}
fn one_count() -> u32 {
    1
}

// RON fixed arrays normally use tuples, but the handoff intentionally uses
// human-friendly [x,y,z] lists. Accept both without rewriting existing user RONs.
fn array<'de, D: serde::Deserializer<'de>, const N: usize>(deserializer: D) -> Result<[f64; N], D::Error> {
    struct Visitor<const N: usize>;
    impl<'de, const N: usize> serde::de::Visitor<'de> for Visitor<N> {
        type Value = [f64; N];
        fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
            write!(f, "a {N}-number list or tuple")
        }
        fn visit_seq<A: serde::de::SeqAccess<'de>>(self, mut values: A) -> Result<Self::Value, A::Error> {
            let mut result = [0.; N];
            for (i, v) in result.iter_mut().enumerate() {
                *v = values.next_element()?.ok_or_else(|| serde::de::Error::invalid_length(i, &self))?;
            }
            if values.next_element::<serde::de::IgnoredAny>()?.is_some() {
                return Err(serde::de::Error::invalid_length(N + 1, &self));
            }
            Ok(result)
        }
    }
    deserializer.deserialize_any(Visitor::<N>)
}
fn array3<'de, D: serde::Deserializer<'de>>(d: D) -> Result<[f64; 3], D::Error> {
    array::<D, 3>(d)
}
fn array4<'de, D: serde::Deserializer<'de>>(d: D) -> Result<[f64; 4], D::Error> {
    array::<D, 4>(d)
}
struct FlexibleArray<const N: usize>([f64; N]);
impl<'de, const N: usize> Deserialize<'de> for FlexibleArray<N> {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        array::<D, N>(d).map(Self)
    }
}
fn option_array2<'de, D: serde::Deserializer<'de>>(d: D) -> Result<Option<[f64; 2]>, D::Error> {
    Option::<FlexibleArray<2>>::deserialize(d).map(|v| v.map(|v| v.0))
}
fn option_array3<'de, D: serde::Deserializer<'de>>(d: D) -> Result<Option<[f64; 3]>, D::Error> {
    Option::<FlexibleArray<3>>::deserialize(d).map(|v| v.map(|v| v.0))
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PropInstance {
    pub id: String,
    pub prop_id: String,
    #[serde(deserialize_with = "array3")]
    pub position: [f64; 3],
    #[serde(default)]
    pub yaw_deg: f64,
    /// Optional local X/Y tilt in degrees; yaw is applied after tilt.
    #[serde(default, skip_serializing_if = "Option::is_none", deserialize_with = "option_array2")]
    pub tilt_deg: Option<[f64; 2]>,
    #[serde(default = "one")]
    pub scale: f64,
    #[serde(default)]
    pub color_variant: Option<String>,
    #[serde(default)]
    pub lootable: bool,
    #[serde(default)]
    pub locked: bool,
    #[serde(default = "all_mode")]
    pub mode: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlayerClip {
    pub id: String,
    #[serde(default = "player_clip_kind")]
    pub kind: String,
    #[serde(default = "concrete")]
    pub phys: String,
    #[serde(deserialize_with = "array3")]
    pub min: [f64; 3],
    #[serde(deserialize_with = "array3")]
    pub max: [f64; 3],
    #[serde(default = "all_mode")]
    pub mode: String,
    #[serde(default)]
    pub locked: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SpawnMarker {
    pub id: String,
    #[serde(deserialize_with = "array3")]
    pub position: [f64; 3],
    #[serde(default)]
    pub yaw_deg: f64,
    #[serde(default = "all_mode")]
    pub mode: String,
    #[serde(default)]
    pub team: Option<String>,
    #[serde(default)]
    pub group: Option<String>,
    #[serde(default)]
    pub locked: bool,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct ExtractParameters {
    pub opens_at_seconds: Option<f64>,
    pub duration_seconds: Option<f64>,
    pub required_item: Option<String>,
    pub condition: Option<String>,
    pub fee: Option<u32>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExtractMarker {
    pub id: String,
    pub name: String,
    #[serde(deserialize_with = "array3")]
    pub position: [f64; 3],
    #[serde(default)]
    pub yaw_deg: f64,
    #[serde(default = "sphere")]
    pub shape: String,
    #[serde(default = "one")]
    pub radius_m: f64,
    #[serde(default, deserialize_with = "option_array3")]
    pub size_m: Option<[f64; 3]>,
    #[serde(default = "always")]
    pub kind: String,
    #[serde(default)]
    pub parameters: ExtractParameters,
    #[serde(default = "all_mode")]
    pub mode: String,
    #[serde(default)]
    pub locked: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LootSpot {
    pub id: String,
    #[serde(deserialize_with = "array3")]
    pub position: [f64; 3],
    pub loot_table: String,
    #[serde(default)]
    pub tier: Option<String>,
    #[serde(default = "one")]
    pub spawn_chance: f64,
    #[serde(default = "one_count")]
    pub max_count: u32,
    #[serde(default)]
    pub container_id: Option<String>,
    #[serde(default = "all_mode")]
    pub mode: String,
    #[serde(default)]
    pub locked: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SuggestedSpawnRegion {
    pub team: String,
    pub suggested: bool,
    #[serde(deserialize_with = "array4")]
    pub aabb: [f64; 4],
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ProposalResolution {
    /// Digest of the proposed item; a changed proposal becomes pending again.
    pub digest: String,
    pub accepted: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Placements {
    pub schema: u32,
    pub map_id: String,
    #[serde(default)]
    pub phase: Option<u32>,
    #[serde(default = "design_frame")]
    pub frame: String,
    #[serde(default, deserialize_with = "array3")]
    pub origin: [f64; 3],
    #[serde(default)]
    pub instances: Vec<PropInstance>,
    #[serde(default)]
    pub player_clips: Vec<PlayerClip>,
    #[serde(default)]
    pub spawns: Vec<SpawnMarker>,
    #[serde(default)]
    pub extracts: Vec<ExtractMarker>,
    #[serde(default)]
    pub loot_spots: Vec<LootSpot>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub foliage_volumes: Vec<FoliageVolume>,
    /// Explicit editor migration: this foliage layer replaces authored fixed
    /// foliage collision/preview volumes, while preserving all other kit data.
    #[serde(default, skip_serializing_if = "is_false")]
    pub replaced_fixed_foliage: bool,
    #[serde(default)]
    pub suggested_spawn_regions: Vec<SuggestedSpawnRegion>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub proposal_resolutions: BTreeMap<String, ProposalResolution>,
}

impl Placements {
    pub fn empty(map_id: impl Into<String>) -> Self {
        Self {
            schema: 1,
            map_id: map_id.into(),
            phase: None,
            frame: design_frame(),
            origin: [0.; 3],
            instances: vec![],
            player_clips: vec![],
            spawns: vec![],
            extracts: vec![],
            loot_spots: vec![],
            foliage_volumes: vec![],
            replaced_fixed_foliage: false,
            suggested_spawn_regions: vec![],
            proposal_resolutions: BTreeMap::new(),
        }
    }
    pub fn from_ron(text: &str) -> Result<Self, BuildError> {
        let doc: Self = ron::Options::default()
            .with_default_extension(ron::extensions::Extensions::IMPLICIT_SOME)
            .from_str(text)
            .map_err(|e| BuildError::Ron(e.to_string()))?;
        doc.validate()?;
        Ok(doc)
    }
    pub fn load(path: &Path) -> Result<Self, BuildError> {
        Self::from_ron(&fs::read_to_string(path)?)
    }
    pub fn to_ron(&self) -> Result<String, BuildError> {
        self.validate()?;
        ron::ser::to_string_pretty(self, ron::ser::PrettyConfig::default()).map_err(|e| BuildError::Ron(e.to_string()))
    }
    pub fn validate(&self) -> Result<(), BuildError> {
        if self.schema != 1 {
            return Err(BuildError::Invalid(format!("Unsupported placements schema {}", self.schema)));
        }
        finite(&self.origin)?;
        let mut ids = BTreeSet::new();
        for item in self.items() {
            if item.id().is_empty() || !ids.insert(item.id().to_owned()) {
                return Err(BuildError::Invalid(format!("Empty or duplicate stable id {}", item.id())));
            }
            finite(&item.position())?;
            match &item {
                EditableItem::Prop(p) => {
                    validate_scale(p.scale)?;
                    finite(&[p.yaw_deg])?;
                    if let Some(t) = p.tilt_deg {
                        finite(&t)?;
                    }
                    if p.prop_id.is_empty() {
                        return Err(BuildError::Invalid("Empty prop_id".into()));
                    }
                }
                EditableItem::Clip(p) => {
                    finite(&p.min)?;
                    finite(&p.max)?;
                    if (0..3).any(|k| p.min[k] >= p.max[k]) {
                        return Err(BuildError::Invalid(format!("Clip {} has nonpositive size", p.id)));
                    }
                }
                EditableItem::Spawn(p) => finite(&[p.yaw_deg])?,
                EditableItem::Extract(p) => {
                    finite(&[p.yaw_deg, p.radius_m])?;
                    if p.radius_m <= 0. {
                        return Err(BuildError::Invalid("Extract radius must be positive".into()));
                    }
                    if let Some(size) = p.size_m {
                        finite(&size)?;
                        if size.iter().any(|v| *v <= 0.) {
                            return Err(BuildError::Invalid("Extract size must be positive".into()));
                        }
                    }
                }
                EditableItem::Loot(p) => {
                    if !p.spawn_chance.is_finite() || !(0.0..=1.).contains(&p.spawn_chance) || p.max_count == 0 {
                        return Err(BuildError::Invalid(format!("Loot {} has invalid chance/count", p.id)));
                    }
                    if let Some(id) = &p.container_id
                        && !self.instances.iter().any(|x| &x.id == id && x.lootable)
                    {
                        return Err(BuildError::Invalid(format!(
                            "Loot {} references a missing/non-lootable container",
                            p.id
                        )));
                    }
                }
                EditableItem::Foliage(p) => p.validate()?,
            }
        }
        Ok(())
    }
    pub fn items(&self) -> Vec<EditableItem> {
        self.instances
            .iter()
            .cloned()
            .map(EditableItem::Prop)
            .chain(self.player_clips.iter().cloned().map(EditableItem::Clip))
            .chain(self.spawns.iter().cloned().map(EditableItem::Spawn))
            .chain(self.extracts.iter().cloned().map(EditableItem::Extract))
            .chain(self.loot_spots.iter().cloned().map(EditableItem::Loot))
            .chain(self.foliage_volumes.iter().cloned().map(EditableItem::Foliage))
            .collect()
    }
    pub fn item(&self, id: &str) -> Option<EditableItem> {
        self.items().into_iter().find(|p| p.id() == id)
    }
    fn remove(&mut self, id: &str) {
        self.instances.retain(|p| p.id != id);
        self.player_clips.retain(|p| p.id != id);
        self.spawns.retain(|p| p.id != id);
        self.extracts.retain(|p| p.id != id);
        self.loot_spots.retain(|p| p.id != id);
        self.foliage_volumes.retain(|p| p.id != id);
    }
    fn insert(&mut self, item: EditableItem) {
        match item {
            EditableItem::Prop(p) => self.instances.push(p),
            EditableItem::Clip(p) => self.player_clips.push(p),
            EditableItem::Spawn(p) => self.spawns.push(p),
            EditableItem::Extract(p) => self.extracts.push(p),
            EditableItem::Loot(p) => self.loot_spots.push(p),
            EditableItem::Foliage(p) => self.foliage_volumes.push(p),
        }
    }
    fn replace(&mut self, item: EditableItem) {
        let id = item.id().to_owned();
        // Retain ordering of existing records so an edit changes only that record.
        match item {
            EditableItem::Prop(p) => replace_record(&mut self.instances, &id, p, |p| &p.id),
            EditableItem::Clip(p) => replace_record(&mut self.player_clips, &id, p, |p| &p.id),
            EditableItem::Spawn(p) => replace_record(&mut self.spawns, &id, p, |p| &p.id),
            EditableItem::Extract(p) => replace_record(&mut self.extracts, &id, p, |p| &p.id),
            EditableItem::Loot(p) => replace_record(&mut self.loot_spots, &id, p, |p| &p.id),
            EditableItem::Foliage(p) => replace_record(&mut self.foliage_volumes, &id, p, |p| &p.id),
        }
    }
}
fn replace_record<T>(rows: &mut Vec<T>, id: &str, value: T, key: impl Fn(&T) -> &str) {
    if let Some(index) = rows.iter().position(|p| key(p) == id) {
        rows[index] = value;
    } else {
        rows.push(value);
    }
}
fn finite(values: &[f64]) -> Result<(), BuildError> {
    if values.iter().all(|v| v.is_finite()) {
        Ok(())
    } else {
        Err(BuildError::Invalid("Non-finite editor number".into()))
    }
}
fn validate_scale(scale: f64) -> Result<(), BuildError> {
    if scale.is_finite() && (0.8..=1.25).contains(&scale) {
        Ok(())
    } else {
        Err(BuildError::Invalid("Uniform scale must be 0.8..1.25".into()))
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum EditableItem {
    Prop(PropInstance),
    Clip(PlayerClip),
    Spawn(SpawnMarker),
    Extract(ExtractMarker),
    Loot(LootSpot),
    Foliage(FoliageVolume),
}
impl EditableItem {
    pub fn id(&self) -> &str {
        match self {
            Self::Prop(p) => &p.id,
            Self::Clip(p) => &p.id,
            Self::Spawn(p) => &p.id,
            Self::Extract(p) => &p.id,
            Self::Loot(p) => &p.id,
            Self::Foliage(p) => &p.id,
        }
    }
    pub fn locked(&self) -> bool {
        match self {
            Self::Prop(p) => p.locked,
            Self::Clip(p) => p.locked,
            Self::Spawn(p) => p.locked,
            Self::Extract(p) => p.locked,
            Self::Loot(p) => p.locked,
            Self::Foliage(p) => p.locked,
        }
    }
    pub fn position(&self) -> [f64; 3] {
        match self {
            Self::Prop(p) => p.position,
            Self::Clip(p) => std::array::from_fn(|k| (p.min[k] + p.max[k]) / 2.),
            Self::Spawn(p) => p.position,
            Self::Extract(p) => p.position,
            Self::Loot(p) => p.position,
            Self::Foliage(p) => p.position,
        }
    }
    fn set_id(&mut self, id: String) {
        match self {
            Self::Prop(p) => p.id = id,
            Self::Clip(p) => p.id = id,
            Self::Spawn(p) => p.id = id,
            Self::Extract(p) => p.id = id,
            Self::Loot(p) => p.id = id,
            Self::Foliage(p) => p.id = id,
        }
    }
    fn set_locked(&mut self, locked: bool) {
        match self {
            Self::Prop(p) => p.locked = locked,
            Self::Clip(p) => p.locked = locked,
            Self::Spawn(p) => p.locked = locked,
            Self::Extract(p) => p.locked = locked,
            Self::Loot(p) => p.locked = locked,
            Self::Foliage(p) => p.locked = locked,
        }
    }
    fn move_to(&mut self, position: [f64; 3]) {
        let old = self.position();
        match self {
            Self::Prop(p) => p.position = position,
            Self::Clip(p) => {
                for k in 0..3 {
                    p.min[k] += position[k] - old[k];
                    p.max[k] += position[k] - old[k];
                }
            }
            Self::Spawn(p) => p.position = position,
            Self::Extract(p) => p.position = position,
            Self::Loot(p) => p.position = position,
            Self::Foliage(p) => p.position = position,
        }
    }
}

#[derive(Debug, Clone)]
#[allow(clippy::large_enum_variant)] // one command at a time; Add carries a whole item by design
pub enum EditCommand {
    Add(EditableItem),
    Delete {
        id: String,
    },
    Move {
        id: String,
        position: [f64; 3],
    },
    Rotate {
        id: String,
        yaw_deg: f64,
        tilt_deg: Option<[f64; 2]>,
    },
    Scale {
        id: String,
        scale: f64,
    },
    /// Absolute local X width / Y depth / Z height, independently editable.
    Resize {
        id: String,
        dimensions_m: [f64; 3],
    },
    SetLocked {
        id: String,
        locked: bool,
    },
    SetLootable {
        id: String,
        lootable: bool,
    },
    Duplicate {
        id: String,
        new_id: String,
        offset: [f64; 3],
    },
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub enum ProposalKind {
    Added,
    Changed,
    Removed,
}
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct ProposalChange {
    pub id: String,
    pub kind: ProposalKind,
    pub current: Option<EditableItem>,
    pub proposed: Option<EditableItem>,
    pub resolution: Option<ProposalResolution>,
}
pub fn compare_proposal(current: &Placements, proposed: &Placements) -> Result<Vec<ProposalChange>, BuildError> {
    current.validate()?;
    proposed.validate()?;
    let a: BTreeMap<_, _> = current.items().into_iter().map(|p| (p.id().to_owned(), p)).collect();
    let b: BTreeMap<_, _> = proposed.items().into_iter().map(|p| (p.id().to_owned(), p)).collect();
    let keys: BTreeSet<_> = a.keys().chain(b.keys()).cloned().collect();
    let mut changes = vec![];
    for id in keys {
        let old = a.get(&id).cloned();
        let new = b.get(&id).cloned();
        if old == new {
            continue;
        }
        let kind = if old.is_none() {
            ProposalKind::Added
        } else if new.is_none() {
            ProposalKind::Removed
        } else {
            ProposalKind::Changed
        };
        let digest = sha256(&serde_json::to_vec(&new)?);
        let resolution = current.proposal_resolutions.get(&id).filter(|r| r.digest == digest).cloned();
        changes.push(ProposalChange { id, kind, current: old, proposed: new, resolution });
    }
    Ok(changes)
}

#[derive(Debug, Clone, PartialEq)]
struct SessionState {
    document: Placements,
    proposal: Option<Placements>,
}
pub struct EditSession {
    state: SessionState,
    undo: Vec<SessionState>,
    redo: Vec<SessionState>,
}
impl EditSession {
    pub fn new(document: Placements) -> Result<Self, BuildError> {
        document.validate()?;
        Ok(Self { state: SessionState { document, proposal: None }, undo: vec![], redo: vec![] })
    }
    pub fn document(&self) -> &Placements {
        &self.state.document
    }
    pub fn set_proposal(&mut self, proposal: Placements) -> Result<(), BuildError> {
        proposal.validate()?;
        let mut next = self.state.clone();
        next.proposal = Some(proposal);
        self.commit(next);
        Ok(())
    }
    pub fn proposals(&self) -> Result<Vec<ProposalChange>, BuildError> {
        if let Some(p) = &self.state.proposal { compare_proposal(&self.state.document, p) } else { Ok(vec![]) }
    }
    pub fn apply(&mut self, command: EditCommand) -> Result<(), BuildError> {
        self.transaction(&[command])
    }
    pub fn transaction(&mut self, commands: &[EditCommand]) -> Result<(), BuildError> {
        let mut next = self.state.clone();
        for command in commands {
            apply_command(&mut next.document, command)?;
        }
        next.document.validate()?;
        self.commit(next);
        Ok(())
    }
    fn commit(&mut self, next: SessionState) {
        if next != self.state {
            self.undo.push(std::mem::replace(&mut self.state, next));
            self.redo.clear();
        }
    }
    pub fn undo(&mut self) -> bool {
        if let Some(previous) = self.undo.pop() {
            self.redo.push(std::mem::replace(&mut self.state, previous));
            true
        } else {
            false
        }
    }
    pub fn redo(&mut self) -> bool {
        if let Some(next) = self.redo.pop() {
            self.undo.push(std::mem::replace(&mut self.state, next));
            true
        } else {
            false
        }
    }
    pub fn accept(&mut self, id: &str) -> Result<(), BuildError> {
        self.resolve(id, true)
    }
    pub fn reject(&mut self, id: &str) -> Result<(), BuildError> {
        self.resolve(id, false)
    }
    fn resolve(&mut self, id: &str, accepted: bool) -> Result<(), BuildError> {
        let change =
            self.proposals()?.into_iter().find(|c| c.id == id).ok_or_else(|| BuildError::Missing(id.into()))?;
        let mut next = self.state.clone();
        if accepted {
            if change.current.as_ref().is_some_and(EditableItem::locked) {
                return Err(BuildError::Locked(id.into()));
            }
            next.document.remove(id);
            if let Some(p) = change.proposed.clone() {
                next.document.insert(p);
            }
        }
        let digest = sha256(&serde_json::to_vec(&change.proposed)?);
        next.document.proposal_resolutions.insert(id.into(), ProposalResolution { digest, accepted });
        next.document.validate()?;
        self.commit(next);
        Ok(())
    }
}
fn apply_command(doc: &mut Placements, command: &EditCommand) -> Result<(), BuildError> {
    if let EditCommand::Add(p) = command {
        if doc.item(p.id()).is_some() {
            return Err(BuildError::Invalid(format!("Duplicate id {}", p.id())));
        }
        doc.insert(p.clone());
        return Ok(());
    }
    let id = match command {
        EditCommand::Delete { id }
        | EditCommand::Move { id, .. }
        | EditCommand::Rotate { id, .. }
        | EditCommand::Scale { id, .. }
        | EditCommand::Resize { id, .. }
        | EditCommand::SetLocked { id, .. }
        | EditCommand::SetLootable { id, .. }
        | EditCommand::Duplicate { id, .. } => id,
        EditCommand::Add(_) => unreachable!(),
    };
    let mut item = doc.item(id).ok_or_else(|| BuildError::Missing(id.clone()))?;
    if item.locked() && !matches!(command, EditCommand::SetLocked { .. }) {
        return Err(BuildError::Locked(id.clone()));
    }
    match command {
        EditCommand::Delete { .. } => {
            doc.remove(id);
            return Ok(());
        }
        EditCommand::Move { position, .. } => item.move_to(*position),
        EditCommand::Rotate { yaw_deg, tilt_deg, .. } => match &mut item {
            EditableItem::Prop(p) => {
                p.yaw_deg = *yaw_deg;
                p.tilt_deg = *tilt_deg;
            }
            EditableItem::Spawn(p) => p.yaw_deg = *yaw_deg,
            EditableItem::Extract(p) => p.yaw_deg = *yaw_deg,
            EditableItem::Foliage(p) => {
                if tilt_deg.is_some() {
                    return Err(BuildError::Invalid("Foliage volumes stay upright; rotate yaw only".into()));
                }
                p.yaw_deg = *yaw_deg;
            }
            _ => return Err(BuildError::Invalid("This marker has no rotation".into())),
        },
        EditCommand::Scale { scale, .. } => {
            if matches!(&item, EditableItem::Foliage(_)) {
                if !scale.is_finite() || *scale <= 0.0 {
                    return Err(BuildError::Invalid("Foliage scale factor must be positive and finite".into()));
                }
            } else {
                validate_scale(*scale)?;
            }
            match &mut item {
                EditableItem::Prop(p) => p.scale = *scale,
                EditableItem::Clip(p) => {
                    let c = std::array::from_fn::<_, 3, _>(|k| (p.min[k] + p.max[k]) / 2.);
                    for (k, centre) in c.iter().enumerate() {
                        let h = (p.max[k] - p.min[k]) * scale / 2.;
                        p.min[k] = centre - h;
                        p.max[k] = centre + h;
                    }
                }
                EditableItem::Extract(p) => {
                    p.radius_m *= scale;
                    if let Some(size) = &mut p.size_m {
                        for v in size {
                            *v *= scale;
                        }
                    }
                }
                EditableItem::Foliage(p) => p.dimensions_m = p.dimensions_m.map(|v| v * scale),
                _ => return Err(BuildError::Invalid("This marker has no scale".into())),
            }
        }
        EditCommand::Resize { dimensions_m, .. } => {
            if let EditableItem::Foliage(p) = &mut item {
                p.dimensions_m = *dimensions_m;
            } else {
                return Err(BuildError::Invalid("Independent resize applies to foliage volumes".into()));
            }
        }
        EditCommand::SetLocked { locked, .. } => item.set_locked(*locked),
        EditCommand::SetLootable { lootable, .. } => {
            if let EditableItem::Prop(p) = &mut item {
                p.lootable = *lootable
            } else {
                return Err(BuildError::Invalid("Lootable applies to prop instances".into()));
            }
        }
        EditCommand::Duplicate { new_id, offset, .. } => {
            if doc.item(new_id).is_some() {
                return Err(BuildError::Invalid(format!("Duplicate id {new_id}")));
            }
            let p = item.position();
            item.set_id(new_id.clone());
            item.move_to(std::array::from_fn(|k| p[k] + offset[k]));
            doc.insert(item);
            return Ok(());
        }
        EditCommand::Add(_) => unreachable!(),
    }
    doc.replace(item);
    Ok(())
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct EditorOptions {
    pub position_snap_m: f64,
    pub yaw_snap_deg: f64,
    pub min_scale: f64,
    pub max_scale: f64,
    pub autosave_seconds: u64,
    pub backup_count: usize,
    /// The free-fly camera (the game's editor reads these too): metres a second, the fast multiplier (Shift)
    /// and mouse look in radians per pixel.
    pub camera_speed_mps: f64,
    pub camera_fast_mult: f64,
    pub mouse_radians_per_pixel: f64,
}
impl Default for EditorOptions {
    fn default() -> Self {
        Self {
            position_snap_m: 0.25,
            yaw_snap_deg: 15.,
            min_scale: 0.8,
            max_scale: 1.25,
            autosave_seconds: 120,
            backup_count: 10,
            camera_speed_mps: 10.,
            camera_fast_mult: 4.,
            mouse_radians_per_pixel: 0.0025,
        }
    }
}
impl EditorOptions {
    pub fn load(path: &Path) -> Result<Self, BuildError> {
        let result = if path.exists() {
            ron::from_str::<Self>(&fs::read_to_string(path)?).map_err(|e| BuildError::Ron(e.to_string()))?
        } else {
            Self::default()
        };
        result.validate()?;
        Ok(result)
    }
    pub fn validate(&self) -> Result<(), BuildError> {
        if !self.position_snap_m.is_finite()
            || self.position_snap_m <= 0.
            || !self.yaw_snap_deg.is_finite()
            || self.yaw_snap_deg <= 0.
            || self.min_scale != 0.8
            || self.max_scale != 1.25
            || !(1..=10).contains(&self.backup_count)
            || self.autosave_seconds == 0
            || !(self.camera_speed_mps > 0. && self.camera_fast_mult >= 1. && self.mouse_radians_per_pixel > 0.)
        {
            Err(BuildError::Invalid("Invalid numerical editor options".into()))
        } else {
            Ok(())
        }
    }
    pub fn snap_position(&self, p: [f64; 3]) -> [f64; 3] {
        p.map(|v| (v / self.position_snap_m).round() * self.position_snap_m)
    }
    pub fn snap_yaw(&self, yaw: f64) -> f64 {
        (yaw / self.yaw_snap_deg).round() * self.yaw_snap_deg
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OpenProperties {
    #[serde(default)]
    pub axis: String,
    #[serde(default)]
    pub closed_location: Option<[f64; 3]>,
    #[serde(flatten)]
    pub extras: BTreeMap<String, serde_json::Value>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OpenablePart {
    pub name: String,
    pub properties: OpenProperties,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PropDescriptor {
    pub id: String,
    pub category: String,
    pub glb: String,
    pub lod1: String,
    pub collision: String,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub openable_parts: Vec<OpenablePart>,
    #[serde(default)]
    pub loot_slots: Vec<String>,
    #[serde(default)]
    pub size_m: [f64; 3],
    #[serde(flatten)]
    pub extras: BTreeMap<String, serde_json::Value>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PropCatalog {
    pub schema: u32,
    pub props: Vec<PropDescriptor>,
    #[serde(flatten)]
    pub extras: BTreeMap<String, serde_json::Value>,
}
impl PropCatalog {
    pub fn load(path: &Path) -> Result<Self, BuildError> {
        let result: Self = serde_json::from_slice(&fs::read(path)?)?;
        if result.schema != 1 {
            return Err(BuildError::Invalid("Unsupported prop catalog schema".into()));
        }
        let mut ids = BTreeSet::new();
        if result.props.iter().any(|p| p.id.is_empty() || !ids.insert(&p.id)) {
            return Err(BuildError::Invalid("Duplicate/empty catalog id".into()));
        }
        Ok(result)
    }
    pub fn get(&self, id: &str) -> Result<&PropDescriptor, BuildError> {
        self.props.iter().find(|p| p.id == id).ok_or_else(|| BuildError::Missing(format!("catalog prop {id}")))
    }
}

pub fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
/// Hash ordered relative paths and length-delimited bytes; independent of root location,
/// filesystem enumeration order and input duplicate paths. Proposals are not user placements.
pub fn kit_placements_hash(assets_root: &Path, files: &[PathBuf]) -> Result<String, BuildError> {
    let root = assets_root.canonicalize()?;
    let mut sorted = BTreeMap::new();
    for file in files {
        let path = if file.is_absolute() { file.clone() } else { root.join(file) }.canonicalize()?;
        let rel = path
            .strip_prefix(&root)
            .map_err(|_| BuildError::Invalid("Hash file escapes assets root".into()))?
            .to_string_lossy()
            .replace('\\', "/");
        sorted.insert(rel, path);
    }
    let mut h = Sha256::new();
    for (name, path) in sorted {
        let data = fs::read(path)?;
        h.update((name.len() as u64).to_le_bytes());
        h.update(name.as_bytes());
        h.update((data.len() as u64).to_le_bytes());
        h.update(data);
    }
    Ok(format!("{:x}", h.finalize()))
}

static SAVE_SEQUENCE: AtomicU64 = AtomicU64::new(0);
#[derive(Debug, Clone, Serialize)]
pub struct SaveResult {
    pub content_sha256: String,
    pub backup: Option<PathBuf>,
    pub bytes_written: usize,
}
/// Same-directory atomic replacement. Only an explicit caller saves; inspect/load
/// do not create starter files or accept proposals. `expected_sha256` detects stale editors.
pub fn save_atomic(
    path: &Path,
    document: &Placements,
    options: &EditorOptions,
    expected_sha256: Option<&str>,
) -> Result<SaveResult, BuildError> {
    options.validate()?;
    let text = document.to_ron()?;
    let previous = if path.exists() { Some(fs::read(path)?) } else { None };
    if let Some(expected) = expected_sha256
        && previous.as_ref().is_none_or(|p| sha256(p) != expected)
    {
        return Err(BuildError::SaveConflict);
    }
    let dir = path.parent().ok_or_else(|| BuildError::Invalid("Save has no parent directory".into()))?;
    fs::create_dir_all(dir)?;
    let file_name =
        path.file_name().ok_or_else(|| BuildError::Invalid("Save has no file name".into()))?.to_string_lossy();
    let stamp =
        SystemTime::now().duration_since(UNIX_EPOCH).map_err(|e| BuildError::Invalid(e.to_string()))?.as_nanos();
    let sequence = SAVE_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    let temp = dir.join(format!(".{file_name}.{stamp:020}.{sequence:06}.tmp"));
    let mut writer = OpenOptions::new().create_new(true).write(true).open(&temp)?;
    if let Err(error) = writer.write_all(text.as_bytes()).and_then(|_| writer.sync_all()) {
        drop(writer);
        let _ = fs::remove_file(&temp);
        return Err(error.into());
    }
    drop(writer);
    let backup_dir = dir.join(".build_mode_backups");
    let backup = if let Some(bytes) = previous {
        fs::create_dir_all(&backup_dir)?;
        let target = backup_dir.join(format!("{file_name}.{stamp:020}.{sequence:06}.ron"));
        fs::write(&target, bytes)?;
        Some(target)
    } else {
        None
    };
    if let Err(error) = fs::rename(&temp, path) {
        let _ = fs::remove_file(&temp);
        return Err(error.into());
    }
    if let Ok(parent) = fs::File::open(dir) {
        let _ = parent.sync_all();
    }
    if backup_dir.exists() {
        let prefix = format!("{file_name}.");
        let mut backups = fs::read_dir(&backup_dir)?
            .filter_map(Result::ok)
            .map(|e| e.path())
            .filter(|p| p.file_name().is_some_and(|n| n.to_string_lossy().starts_with(&prefix)))
            .collect::<Vec<_>>();
        backups.sort();
        let count = backups.len().saturating_sub(options.backup_count);
        for p in backups.into_iter().take(count) {
            fs::remove_file(p)?;
        }
    }
    Ok(SaveResult { content_sha256: sha256(text.as_bytes()), backup, bytes_written: text.len() })
}

#[derive(Debug, Deserialize)]
struct LayerManifest {
    #[serde(default)]
    kit_scenes: Vec<String>,
    collision: String,
    #[serde(default)]
    foliage: Option<String>,
    placements: String,
    #[serde(default)]
    latest_placements_proposal: Option<String>,
}
#[derive(Debug, Deserialize)]
struct MapManifest {
    map_id: String,
    kit_scenes: Vec<String>,
    collision: String,
    #[serde(default)]
    foliage: Option<String>,
    placements: String,
    #[serde(default)]
    latest_placements_proposal: Option<String>,
    #[serde(default)]
    extension: Option<LayerManifest>,
    #[serde(default)]
    core_bounds_design: Option<[f64; 4]>,
}
#[derive(Debug, Clone, Serialize)]
pub struct Diagnostic {
    pub code: String,
    pub item_id: Option<String>,
    pub message: String,
}
#[derive(Debug, Clone, Serialize)]
pub struct MapInspection {
    pub schema: u32,
    pub map_id: String,
    pub valid: bool,
    pub catalog_props: usize,
    pub instances: usize,
    pub player_clips: usize,
    pub spawns: usize,
    pub extracts: usize,
    pub loot_spots: usize,
    pub editable_foliage_volumes: usize,
    pub fixed_collision_volumes: usize,
    pub prop_collision_volumes: usize,
    pub foliage_collision_volumes: usize,
    pub pending_proposals: usize,
    pub map_version_sha256: String,
    pub kit_sha256: String,
    pub placements_sha256: String,
    pub warnings: Vec<Diagnostic>,
    pub deferred_client_features: Vec<String>,
}

pub(crate) fn asset_path(assets_root: &Path, path: &Path) -> Result<PathBuf, BuildError> {
    let root = assets_root.canonicalize()?;
    let actual = if path.is_absolute() { path.to_owned() } else { root.join(path) }.canonicalize()?;
    if !actual.starts_with(&root) {
        return Err(BuildError::Invalid("Asset path escapes assets root".into()));
    }
    Ok(actual)
}
fn add_glb_hash_files(root: &Path, path: &Path, files: &mut Vec<PathBuf>) -> Result<(), BuildError> {
    let path = asset_path(root, path)?;
    files.push(path.clone());
    let j = collision::glb_json(&fs::read(&path)?)?;
    for image in j.get("images").and_then(|v| v.as_array()).into_iter().flatten() {
        if let Some(uri) = image.get("uri").and_then(|v| v.as_str()) {
            if uri.contains("://") || uri.starts_with("data:") {
                return Err(BuildError::Invalid("Hashing requires frozen local GLB images".into()));
            }
            files.push(asset_path(root, &path.parent().unwrap().join(uri))?);
        }
    }
    Ok(())
}
fn add_contract_hash_files(root: &Path, path: &Path, files: &mut Vec<PathBuf>) -> Result<(), BuildError> {
    fn visit(root: &Path, value: &serde_json::Value, files: &mut Vec<PathBuf>) -> Result<(), BuildError> {
        match value {
            serde_json::Value::String(v) if v.starts_with("maps/") || v.starts_with("props/") => {
                let p = root.join(v);
                if p.is_file() {
                    files.push(asset_path(root, &p)?);
                }
            }
            serde_json::Value::Array(v) => {
                for x in v {
                    visit(root, x, files)?;
                }
            }
            serde_json::Value::Object(v) => {
                for x in v.values() {
                    visit(root, x, files)?;
                }
            }
            _ => {}
        }
        Ok(())
    }
    if path.exists() {
        files.push(path.into());
        visit(root, &serde_json::from_slice(&fs::read(path)?)?, files)?;
    }
    Ok(())
}

/// Read-only diagnostic used by the future client/CLI. The actual user RON is
/// authoritative. Proposal changes are counted, never substituted for user data.
pub fn inspect_map(assets_root: &Path, map_id: &str) -> Result<MapInspection, BuildError> {
    if map_id.is_empty() || !map_id.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-') {
        return Err(BuildError::Invalid("Invalid map id".into()));
    }
    let dir = asset_path(assets_root, &PathBuf::from("maps").join(map_id))?;
    let manifest_path = dir.join("map_manifest.json");
    let manifest: MapManifest = serde_json::from_slice(&fs::read(&manifest_path)?)?;
    if manifest.map_id != map_id {
        return Err(BuildError::Invalid("Manifest map id mismatch".into()));
    }
    let catalog_path = asset_path(assets_root, Path::new("props/catalog.json"))?;
    let catalog = PropCatalog::load(&catalog_path)?;
    let mut layers = vec![LayerManifest {
        kit_scenes: manifest.kit_scenes,
        collision: manifest.collision,
        foliage: manifest.foliage,
        placements: manifest.placements,
        latest_placements_proposal: manifest.latest_placements_proposal,
    }];
    if let Some(layer) = manifest.extension {
        layers.push(layer);
    }
    let mut kit_files = vec![manifest_path, catalog_path];
    let mut placement_files = vec![];
    let mut used_props = BTreeSet::new();
    let mut documents = vec![];
    let mut fixed_count = 0;
    let mut prop_count = 0;
    let mut foliage_collision_count = 0;
    let mut pending = 0;
    let mut warnings = vec![];
    for (index, layer) in layers.iter().enumerate() {
        for scene in &layer.kit_scenes {
            add_glb_hash_files(assets_root, &dir.join(scene), &mut kit_files)?;
        }
        let collision_path = asset_path(assets_root, &dir.join(&layer.collision))?;
        let fixed = collision::CollisionDocument::load(&collision_path)?;
        fixed_count += fixed.volumes.len();
        kit_files.push(collision_path);
        if let Some(f) = &layer.foliage {
            kit_files.push(asset_path(assets_root, &dir.join(f))?);
        }
        let p = asset_path(assets_root, &dir.join(&layer.placements))?;
        let document = Placements::load(&p)?;
        placement_files.push(p);
        for instance in &document.instances {
            catalog.get(&instance.prop_id)?;
            used_props.insert(instance.prop_id.clone());
            if index == 0
                && let Some(bounds) = manifest.core_bounds_design
                && (instance.position[0] < bounds[0]
                    || instance.position[0] > bounds[2]
                    || instance.position[1] < bounds[1]
                    || instance.position[1] > bounds[3])
            {
                warnings.push(Diagnostic {
                    code: "off_core_bounds".into(),
                    item_id: Some(instance.id.clone()),
                    message: "Placement centre lies outside the TDM core; review its mode".into(),
                });
            }
        }
        prop_count += collision::instantiate_props(assets_root, &catalog, &document, None)?.len();
        foliage_collision_count += foliage::export_foliage(&document, None)?.len();
        if let Some(proposal) = &layer.latest_placements_proposal {
            let path = dir.join(proposal);
            if path.exists() {
                let proposed = Placements::load(&path)?;
                pending += compare_proposal(&document, &proposed)?.iter().filter(|c| c.resolution.is_none()).count();
            }
        }
        add_contract_hash_files(
            assets_root,
            &dir.join(Path::new(&layer.collision).parent().unwrap_or(Path::new(""))).join("ground_blend_contract.json"),
            &mut kit_files,
        )?;
        documents.push(document);
    }
    for pid in used_props {
        let p = catalog.get(&pid)?;
        add_glb_hash_files(assets_root, Path::new(&p.glb), &mut kit_files)?;
        add_glb_hash_files(assets_root, Path::new(&p.lod1), &mut kit_files)?;
        kit_files.push(asset_path(assets_root, Path::new(&p.collision))?);
    }
    let kit_sha256 = kit_placements_hash(assets_root, &kit_files)?;
    let placements_sha256 = kit_placements_hash(assets_root, &placement_files)?;
    kit_files.extend(placement_files);
    let map_version_sha256 = kit_placements_hash(assets_root, &kit_files)?;
    let spawns = documents.iter().map(|d| d.spawns.len()).sum();
    if spawns == 0 {
        warnings.push(Diagnostic {
            code: "no_spawns".into(),
            item_id: None,
            message: "User layer has no playable spawn markers yet".into(),
        });
    }
    if pending > 0 {
        warnings.push(Diagnostic {
            code: "pending_proposals".into(),
            item_id: None,
            message: format!("{pending} stable-id proposal changes await user review"),
        });
    }
    Ok(MapInspection {
        schema: 1,
        map_id: map_id.into(),
        valid: true,
        catalog_props: catalog.props.len(),
        instances: documents.iter().map(|d| d.instances.len()).sum(),
        player_clips: documents.iter().map(|d| d.player_clips.len()).sum(),
        spawns,
        extracts: documents.iter().map(|d| d.extracts.len()).sum(),
        loot_spots: documents.iter().map(|d| d.loot_spots.len()).sum(),
        editable_foliage_volumes: documents.iter().map(|d| d.foliage_volumes.len()).sum(),
        fixed_collision_volumes: fixed_count,
        prop_collision_volumes: prop_count,
        foliage_collision_volumes: foliage_collision_count,
        pending_proposals: pending,
        map_version_sha256,
        kit_sha256,
        placements_sha256,
        warnings,
        deferred_client_features: vec![
            "Client camera/browser/gizmos and play toggle".into(),
            "Editor preview loader and per-phys penetration tuning beyond the read-only TDM kit".into(),
            "Network join-handshake enforcement".into(),
            "Autosave scheduler; numerical interval is loaded".into(),
        ],
    })
}

#[cfg(test)]
mod tests;
