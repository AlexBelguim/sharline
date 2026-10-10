//! Current authored Showhome v3 core and full-campus map snapshots.
//! Loading never writes source/user placements; editor overlays are explicit.
use crate::build_mode::collision::{CollisionDocument, ConvexVolume, design_to_bevy, instantiate_props};
use crate::build_mode::foliage::{FoliageExport, export_foliage};
use crate::build_mode::{BuildError, FoliageVolume, Placements, PlayerClip, PropCatalog};
use crate::level::{Level, SpawnPoint, Team};
use crate::movement::collision::{Brush, BrushKind, CollisionWorld, Look, Plane, SKIN};
use glam::Vec3;
use serde::Deserialize;
use std::{
    fs,
    path::{Path, PathBuf},
};

pub const MAP_ID: &str = "showhome_v3";
pub const FULL_MAP_ID: &str = "showhome_full";
pub const TITLE: &str = "Showhome v3 Core";
pub const FULL_TITLE: &str = "ShowhomeFull";

pub fn canonical_id(name: &str) -> Option<&'static str> {
    match name.trim().to_ascii_lowercase().as_str() {
        "showhome_v3" | "showhome_v3_core" => Some(MAP_ID),
        "showhome_full" | "showhomefull" | "showhome_v3_full" => Some(FULL_MAP_ID),
        _ => None,
    }
}

#[derive(Debug, Clone)]
pub struct CorePreview {
    pub level: Level,
    pub placements: Placements,
    pub catalog: PropCatalog,
    pub placements_source: PathBuf,
    pub origin: [f64; 3],
    pub volumes: Vec<ConvexVolume>,
    pub kit_scenes: Vec<String>,
    pub play_bounds_design: [f64; 4],
    pub fixed_foliage: Vec<FoliageVolume>,
    pub foliage: Vec<FoliageExport>,
    pub asset_mode: String,
}
#[derive(Deserialize)]
struct Manifest {
    kit_scenes: Vec<String>,
    collision: String,
    #[serde(default)]
    foliage: Option<String>,
    #[serde(default)]
    tdm_play_bounds_design: Option<[f64; 4]>,
}

pub fn editor_path(assets_root: &Path, variant_id: &str) -> PathBuf {
    assets_root.join("maps").join(canonical_id(variant_id).unwrap_or(MAP_ID)).join("placements.editor.ron")
}
fn read_placements(folder: &Path, candidates: &[&str]) -> Result<(Placements, PathBuf), BuildError> {
    let path = candidates
        .iter()
        .map(|name| folder.join(name))
        .find(|p| p.is_file())
        .ok_or_else(|| BuildError::Missing(format!("Placements in {}", folder.display())))?;
    let p = if path.extension().is_some_and(|e| e == "json") {
        let p: Placements = serde_json::from_slice(&fs::read(&path)?)?;
        p.validate()?;
        p
    } else {
        Placements::load(&path)?
    };
    Ok((p, path))
}
fn fixed_foliage(path: &Path) -> Result<Vec<FoliageVolume>, BuildError> {
    if !path.is_file() {
        return Ok(vec![]);
    }
    crate::build_mode::foliage::import_authoring_foliage(&fs::read_to_string(path)?, "fixed_")
}
fn merge(base: &mut Placements, other: Placements) -> Result<(), BuildError> {
    if base.origin != other.origin {
        return Err(BuildError::Invalid("Core/extension placement origins differ".into()));
    }
    base.instances.extend(other.instances);
    base.player_clips.extend(other.player_clips);
    base.spawns.extend(other.spawns);
    base.extracts.extend(other.extracts);
    base.loot_spots.extend(other.loot_spots);
    base.foliage_volumes.extend(other.foliage_volumes);
    base.validate()
}

/// Explicit, once-only editor promotion. Even deletion of every promoted
/// record remains distinguishable from an untouched authored foliage layer.
pub fn promote_fixed_foliage(p: &mut Placements, fixed: &[FoliageVolume]) -> Result<(), BuildError> {
    if !p.replaced_fixed_foliage {
        for v in fixed {
            if !p.foliage_volumes.iter().any(|old| old.id == v.id) {
                p.foliage_volumes.push(v.clone());
            }
        }
        p.replaced_fixed_foliage = true;
    }
    p.validate()
}

pub fn load(assets_root: &Path) -> Result<CorePreview, BuildError> {
    load_with_placements(assets_root, MAP_ID, None)
}

/// An ephemeral document or the separate editor file replaces the editable
/// combined layer. Fixed exported geometry remains read-only in both variants.
pub fn load_with_placements(
    assets_root: &Path,
    variant_id: &str,
    overlay: Option<&Placements>,
) -> Result<CorePreview, BuildError> {
    let id =
        canonical_id(variant_id).ok_or_else(|| BuildError::Invalid(format!("Unknown authored map {variant_id}")))?;
    let full = id == FULL_MAP_ID;
    let mode = if full { "extraction" } else { "tdm" };
    let folder = assets_root.join("maps").join(MAP_ID);
    let manifest: Manifest = serde_json::from_slice(&fs::read(folder.join("map_manifest.json"))?)?;
    let editor = editor_path(assets_root, id);
    let combined_default = overlay.is_none() && !(full && editor.is_file());
    let (mut p, source) = if let Some(p) = overlay {
        (p.clone(), editor.clone())
    } else if full && editor.is_file() {
        (Placements::load(&editor)?, editor.clone())
    } else {
        let (mut p, path) = read_placements(
            &folder,
            &["placements.editor.ron", "placements.reference.json", "placements.proposed.ron", "placements.ron"],
        )?;
        if full {
            let (extra, _) = read_placements(
                &folder.join("extension"),
                &["placements.reference.json", "placements.generated.json", "placements.proposed.ron"],
            )?;
            merge(&mut p, extra)?;
        }
        (p, path)
    };
    p.map_id = id.into();
    p.instances.retain(|r| r.mode == "all" || r.mode == mode);
    p.player_clips.retain(|r| r.mode == "all" || r.mode == mode);
    if full {
        full_boundary(&mut p)
    }
    p.validate()?;
    let catalog = PropCatalog::load(&assets_root.join("props/catalog.json"))?;
    let mut volumes = CollisionDocument::load(&folder.join(&manifest.collision))?.in_bevy(p.origin)?;
    let mut kit_scenes = manifest
        .kit_scenes
        .into_iter()
        .filter(|s| !s.starts_with("extension/"))
        .map(|s| format!("maps/{MAP_ID}/{s}"))
        .collect::<Vec<_>>();
    let mut fixed = fixed_foliage(&folder.join(manifest.foliage.as_deref().unwrap_or("foliage.json")))?;
    if full {
        let ext = folder.join("extension");
        let extra: Manifest = serde_json::from_slice(&fs::read(ext.join("manifest.json"))?)?;
        volumes.extend(CollisionDocument::load(&ext.join(extra.collision))?.in_bevy(p.origin)?);
        kit_scenes.extend(extra.kit_scenes.into_iter().map(|s| format!("maps/{MAP_ID}/extension/{s}")));
        let extra_foliage = fixed_foliage(&ext.join(extra.foliage.as_deref().unwrap_or("foliage.json")))?;
        if combined_default && p.replaced_fixed_foliage {
            for v in &extra_foliage {
                if !p.foliage_volumes.iter().any(|old| old.id == v.id) {
                    p.foliage_volumes.push(v.clone());
                }
            }
        }
        fixed.extend(extra_foliage);
    }
    if kit_scenes.len() != (if full { 3 } else { 2 }) || kit_scenes.iter().any(|s| !assets_root.join(s).is_file()) {
        return Err(BuildError::Invalid("Authored map fixed GLB scenes are missing".into()));
    }
    if p.replaced_fixed_foliage {
        volumes.retain(|v| v.phys != "foliage_dense" && v.phys != "foliage_thin");
    }
    volumes.extend(instantiate_props(assets_root, &catalog, &p, Some(mode))?);
    let editable = export_foliage(&p, Some(mode))?;
    volumes.extend(editable.iter().map(|f| f.collision.clone()));
    let mut fixed_document = Placements::empty(id);
    fixed_document.origin = p.origin;
    fixed_document.foliage_volumes = fixed.clone();
    let mut foliage = if p.replaced_fixed_foliage { vec![] } else { export_foliage(&fixed_document, None)? };
    foliage.extend(editable);
    let mut world = CollisionWorld::default();
    for v in &volumes {
        world.push(brush(v))
    }
    for clip in &p.player_clips {
        let a = Vec3::from_array(design_to_bevy(clip.min, p.origin).map(|v| v as f32));
        let b = Vec3::from_array(design_to_bevy(clip.max, p.origin).map(|v| v as f32));
        world.push(Brush::cuboid(a.min(b), a.max(b), BrushKind::PlayerClip));
    }
    let bounds = if full {
        [290., 600., 483., 908.]
    } else {
        manifest.tdm_play_bounds_design.unwrap_or([330., 620., 410., 670.35])
    };
    let mut level = Level { name: id.into(), world, ziplines: vec![], spawns: vec![], kill_y: -10. };
    level.spawns = distributed_spawns(&level.world, &p, bounds, full)?;
    Ok(CorePreview {
        level,
        origin: p.origin,
        placements: p,
        catalog,
        placements_source: source,
        volumes,
        kit_scenes,
        play_bounds_design: bounds,
        fixed_foliage: fixed,
        foliage,
        asset_mode: mode.into(),
    })
}

fn full_boundary(p: &mut Placements) {
    p.player_clips.retain(|c| !c.id.starts_with("full_bounds_"));
    // Match the L-shaped playable ground union, not the presentation skirt.
    let walls = [
        ("west_core", [289.9, 600., -8.], [290.1, 685., 40.]),
        ("west_campus", [309.9, 685., -8.], [310.1, 908., 40.]),
        ("east_core", [449.9, 600., -8.], [450.1, 685., 40.]),
        ("east_campus", [482.9, 685., -8.], [483.1, 908., 40.]),
        ("south", [290., 599.9, -8.], [450., 600.1, 40.]),
        ("north", [310., 907.9, -8.], [483., 908.1, 40.]),
        ("west_step", [290., 684.9, -8.], [310., 685.1, 40.]),
        ("east_step", [450., 684.9, -8.], [483., 685.1, 40.]),
        ("ceiling", [290., 600., 40.], [483., 908., 40.2]),
    ];
    p.player_clips.extend(walls.into_iter().map(|(name, min, max)| PlayerClip {
        id: format!("full_bounds_{name}"),
        kind: "player_clip".into(),
        phys: "concrete".into(),
        min,
        max,
        mode: "all".into(),
        locked: true,
    }));
}

pub fn look_for_phys(phys: &str) -> Look {
    match phys {
        "grass" | "soil" | "sand" => Look::Ground,
        "gravel" => Look::Gravel,
        "asphalt" => Look::Asphalt,
        "paving" => Look::Paving,
        "wood_thin" | "wood_thick" => Look::Floor,
        "sheet_metal" | "metal_heavy" => Look::Metal,
        "foliage_dense" | "foliage_thin" => Look::Hedge,
        "glass" => Look::Glass,
        "water" => Look::Water,
        "concrete" | "brick" => Look::Concrete,
        "drywall" | "cladding" => Look::Wall,
        _ => Look::Prop,
    }
}

pub fn brush(volume: &ConvexVolume) -> Brush {
    let min = Vec3::from_array(volume.aabb.min.map(|v| v as f32));
    let max = Vec3::from_array(volume.aabb.max.map(|v| v as f32));
    let kind = if volume.kind == "player_clip" {
        BrushKind::PlayerClip
    } else if volume.phys == "glass" || volume.phys == "water" || volume.phys == "foliage_thin" {
        BrushKind::BulletOnly
    } else if !volume.walkable {
        BrushKind::SolidNonWalkable
    } else {
        BrushKind::Solid
    };
    let mut result = Brush {
        planes: volume
            .planes
            .iter()
            .map(|p| Plane { normal: Vec3::new(p[0] as f32, p[1] as f32, p[2] as f32), dist: p[3] as f32 })
            .collect(),
        min,
        max,
        kind,
        look: look_for_phys(&volume.phys),
        ramp: None,
    };
    // Axial bevels prevent swept-box false contacts at corners of rotated hulls.
    // They supplement the actual convex planes; they never substitute an AABB.
    if result.planes.iter().any(|p| p.normal.abs().max_element() < 0.999) {
        for (normal, dist) in [
            (Vec3::X, max.x),
            (Vec3::NEG_X, -min.x),
            (Vec3::Y, max.y),
            (Vec3::NEG_Y, -min.y),
            (Vec3::Z, max.z),
            (Vec3::NEG_Z, -min.z),
        ] {
            if !result.planes.iter().any(|p| p.normal.abs_diff_eq(normal, 1e-4)) {
                result.planes.push(Plane { normal, dist });
            }
        }
    }
    result
}

fn safe_spawn(world: &CollisionWorld, origin: [f64; 3], position: [f64; 3], team: Team) -> Option<SpawnPoint> {
    let base = Vec3::from_array(design_to_bevy(position, origin).map(|v| v as f32));
    let ground = world.trace_box(base + Vec3::Y * 0.3, base - Vec3::Y * 0.6, Vec3::ZERO);
    if !ground.hit() || ground.start_solid || !ground.walkable || ground.normal.y < 0.97 {
        return None;
    }
    let feet = ground.end + Vec3::Y * (SKIN * 3.);
    let centre = feet + Vec3::Y * 0.9;
    if world.trace_solid(centre, centre, Vec3::new(0.32, 0.9, 0.32)).start_solid {
        return None;
    }
    Some(SpawnPoint {
        pos: feet,
        yaw: if team == Team::A { -std::f32::consts::FRAC_PI_2 } else { std::f32::consts::FRAC_PI_2 },
        team: Some(team),
    })
}
fn distributed_spawns(
    world: &CollisionWorld,
    p: &Placements,
    bounds: [f64; 4],
    full: bool,
) -> Result<Vec<SpawnPoint>, BuildError> {
    let mut out = vec![];
    for team in [Team::A, Team::B] {
        for y in [624., 632., 640., 648., 660., 667.] {
            let mut accepted = None;
            'band: for dy in [0., -0.8, 0.8, -1.6, 1.6, -2.4, 2.4] {
                for west in [336., 340., 344., 332.75, 346.5] {
                    let x = if team == Team::A { west } else { 740. - west };
                    if x <= bounds[0] || x >= bounds[2] || y + dy <= bounds[1] || y + dy >= bounds[3] {
                        continue;
                    }
                    if let Some(s) = safe_spawn(world, p.origin, [x, y + dy, 0.], team)
                        && out.iter().all(|old: &SpawnPoint| old.pos.distance(s.pos) > 2.)
                    {
                        accepted = Some(s);
                        break 'band;
                    }
                }
            }
            if let Some(spawn) = accepted {
                out.push(spawn);
            }
        }
    }
    if full {
        for (team, positions) in [
            (
                Team::A,
                [
                    [337., 714., 0.],
                    [363., 719., 0.],
                    [332., 800., 0.],
                    [335., 836., 0.],
                    [357., 811., 0.],
                    [353., 781., 3.2],
                    [353., 868., 6.4],
                    [375., 814., -3.2],
                ],
            ),
            (
                Team::B,
                [
                    [401., 714., 0.],
                    [377., 719., 0.],
                    [464., 815., 0.],
                    [473., 887., 0.],
                    [417., 828., 0.],
                    [405., 781., 3.2],
                    [409., 868., -3.2],
                    [438., 804., -3.2],
                ],
            ),
        ] {
            for [x, y, z] in positions {
                let mut accepted = None;
                'candidate: for dy in [0., 1., -1., 2., -2.] {
                    for dx in [0., 1., -1., 2., -2.] {
                        if let Some(s) = safe_spawn(world, p.origin, [x + dx, y + dy, z], team)
                            && out.iter().all(|old| old.pos.distance(s.pos) > 2.)
                        {
                            accepted = Some(s);
                            break 'candidate;
                        }
                    }
                }
                if let Some(spawn) = accepted {
                    out.push(spawn);
                }
            }
        }
    }
    // Authored editor markers are additional validated choices. The default
    // team-labelled pool is also the FFA pool via Level::spawns_for(None).
    for marker in &p.spawns {
        if marker.mode != "all" && marker.mode != "tdm" && marker.mode != "ffa" {
            continue;
        }
        let team = if marker.team.as_deref() == Some("B") { Team::B } else { Team::A };
        if let Some(mut s) = safe_spawn(world, p.origin, marker.position, team) {
            s.yaw = (marker.yaw_deg as f32 - 90.).to_radians();
            s.team = marker.team.as_ref().map(|_| team);
            if out.iter().all(|old| old.pos.distance(s.pos) > 1.) {
                out.push(s)
            }
        }
    }
    for team in [Team::A, Team::B] {
        if !out.iter().any(|s| s.team.is_none() || s.team == Some(team)) {
            return Err(BuildError::Invalid(format!("Map has no collision-free spawn for {team:?}")));
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn assets() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../assets")
    }
    #[test]
    fn current_tdm_core_loads_reference_and_exact_collision_without_extension() {
        let path = assets().join("maps/showhome_v3/placements.ron");
        let before = fs::read(&path).unwrap();
        let p = load(&assets()).unwrap();
        assert!(p.placements_source.ends_with("placements.reference.json"));
        assert!(p.placements.instances.len() > 100);
        assert!(p.volumes.len() > 2000);
        assert_eq!(p.kit_scenes.len(), 2);
        assert!(p.kit_scenes.iter().all(|s| !s.contains("extension")));
        assert_eq!(fs::read(path).unwrap(), before);
        assert!(p.level.world.brushes.iter().any(|b| b.planes.len() > 6));
        assert!(p.level.world.brushes.iter().any(|b| b.kind == BrushKind::SolidNonWalkable));
        for s in &p.level.spawns {
            let c = s.pos + Vec3::Y * 0.9;
            assert!(!p.level.world.trace_solid(c, c, Vec3::new(0.32, 0.9, 0.32)).start_solid);
        }
        assert!(p.level.spawns_for(Some(Team::A)).count() >= 1);
        assert!(p.level.spawns_for(Some(Team::B)).count() >= 1);
        for team in [Team::A, Team::B] {
            let points = p.level.spawns_for(Some(team)).collect::<Vec<_>>();
            assert_eq!(points.len(), 6);
            let north = points.iter().map(|s| -s.pos.z + p.origin[1] as f32).fold(f32::NEG_INFINITY, f32::max);
            let south = points.iter().map(|s| -s.pos.z + p.origin[1] as f32).fold(f32::INFINITY, f32::min);
            assert!(north >= 660. && north - south >= 38., "spawns must cover both homes and the upper garden");
        }
    }
    #[test]
    fn nonwalkable_authored_surface_stays_solid_but_not_standing_ground() {
        let mut world = CollisionWorld::default();
        world.push(Brush::cuboid(Vec3::ZERO, Vec3::ONE, BrushKind::SolidNonWalkable));
        let hit = world.trace_box(Vec3::new(0.5, 2., 0.5), Vec3::new(0.5, 0., 0.5), Vec3::ZERO);
        assert!(hit.hit());
        assert!(!hit.walkable);
        assert!(world.raycast(Vec3::new(0.5, 2., 0.5), Vec3::NEG_Y, 3.).is_some());
    }

    #[test]
    fn full_map_loads_campus_without_inner_tdm_traps_and_distributes_ffa_pool() {
        let p = load_with_placements(&assets(), FULL_MAP_ID, None).unwrap();
        assert_eq!(p.level.name, FULL_MAP_ID);
        assert_eq!(p.kit_scenes.len(), 3);
        assert!(p.kit_scenes.iter().any(|s| s.ends_with("extension/extension.glb")));
        assert!(p.placements.instances.iter().all(|r| r.mode != "tdm"));
        assert!(p.placements.player_clips.iter().all(|r| r.mode != "tdm"));
        assert!(p.placements.player_clips.iter().any(|r| r.id == "full_bounds_ceiling" && r.min[2] > 16.));
        assert!(p.placements.instances.iter().any(|r| r.prop_id == "organic_planter_bench"));
        assert!(p.fixed_foliage.len() > 100 && p.foliage.len() >= p.fixed_foliage.len());
        let pool = p.level.spawns_for(None).collect::<Vec<_>>();
        assert_eq!(pool.len(), 28);
        assert!(pool.iter().any(|s| s.pos.y < -3.));
        assert!(pool.iter().any(|s| s.pos.y > 6.));
        assert!(pool.iter().any(|s| -s.pos.z + p.origin[1] as f32 >= 880.));
        for s in pool {
            let c = s.pos + Vec3::Y * 0.9;
            assert!(!p.level.world.trace_solid(c, c, Vec3::new(0.32, 0.9, 0.32)).start_solid);
        }
    }

    #[test]
    fn ephemeral_overlay_changes_exact_collision_without_writing_user_document() {
        let before = fs::read(assets().join("maps/showhome_v3/placements.ron")).unwrap();
        let initial = load(&assets()).unwrap();
        let mut overlay = initial.placements.clone();
        let row = overlay.instances.iter_mut().find(|p| p.prop_id == "city_car").unwrap();
        let id = row.id.clone();
        row.position[1] += 1.;
        let changed = load_with_placements(&assets(), MAP_ID, Some(&overlay)).unwrap();
        assert_eq!(
            changed.placements.instances.iter().find(|r| r.id == id).unwrap().position,
            overlay.instances.iter().find(|r| r.id == id).unwrap().position
        );
        assert_ne!(
            initial.volumes.iter().find(|v| v.name.contains(&id)).unwrap().aabb,
            changed.volumes.iter().find(|v| v.name.contains(&id)).unwrap().aabb
        );
        assert_eq!(fs::read(assets().join("maps/showhome_v3/placements.ron")).unwrap(), before);
        assert!(editor_path(&assets(), FULL_MAP_ID).ends_with("showhome_full/placements.editor.ron"));
    }

    #[test]
    fn promoted_fixed_foliage_can_be_moved_or_deleted_without_phantom_collision() {
        let initial = load(&assets()).unwrap();
        let mut p = initial.placements.clone();
        promote_fixed_foliage(&mut p, &initial.fixed_foliage).unwrap();
        let n = p.foliage_volumes.len();
        promote_fixed_foliage(&mut p, &initial.fixed_foliage).unwrap();
        assert_eq!(p.foliage_volumes.len(), n);
        p.foliage_volumes.clear();
        let changed = load_with_placements(&assets(), MAP_ID, Some(&p)).unwrap();
        assert!(changed.foliage.is_empty());
        assert!(!changed.volumes.iter().any(|v| v.phys == "foliage_dense" || v.phys == "foliage_thin"));
        assert!(changed.volumes.iter().any(|v| v.phys == "cladding"));
        assert!(Placements::from_ron(&p.to_ron().unwrap()).unwrap().replaced_fixed_foliage);
    }

    #[test]
    fn edited_blocked_spawn_band_does_not_block_world_refresh_but_empty_arena_does() {
        let initial = load(&assets()).unwrap();
        let mut p = initial.placements.clone();
        let mut blocker = FoliageVolume::new("user_blocks_south_spawn_band");
        blocker.position = [339., 624., 0.];
        blocker.dimensions_m = [20., 6., 2.];
        p.foliage_volumes.push(blocker);
        let edited = load_with_placements(&assets(), MAP_ID, Some(&p)).unwrap();
        assert_eq!(edited.level.spawns_for(Some(Team::A)).count(), 5);
        assert_eq!(edited.level.spawns_for(Some(Team::B)).count(), 6);
        p.foliage_volumes[0].position = [370., 645., 0.];
        p.foliage_volumes[0].dimensions_m = [90., 55., 9.];
        assert!(load_with_placements(&assets(), MAP_ID, Some(&p)).is_err());
    }

    #[test]
    fn neutral_ffa_marker_remains_neutral_and_extraction_markers_stay_out_of_arena() {
        let initial = load(&assets()).unwrap();
        let mut p = initial.placements.clone();
        let mut candidate = None;
        'find: for point in &initial.level.spawns {
            for (dx, dy) in [(1.2, 1.2), (-1.2, 1.2), (1.8, 0.), (0., 1.8)] {
                let position = [point.pos.x as f64 + p.origin[0] + dx, -point.pos.z as f64 + p.origin[1] + dy, 0.];
                if let Some(s) = safe_spawn(&initial.level.world, p.origin, position, Team::A)
                    && initial.level.spawns.iter().all(|old| old.pos.distance(s.pos) > 1.)
                {
                    candidate = Some(position);
                    break 'find;
                }
            }
        }
        let position = candidate.unwrap();
        p.spawns.push(crate::build_mode::SpawnMarker {
            id: "extract_marker".into(),
            position,
            yaw_deg: 0.,
            mode: "extraction".into(),
            team: Some("A".into()),
            group: None,
            locked: false,
        });
        p.spawns.push(crate::build_mode::SpawnMarker {
            id: "ffa_marker".into(),
            position,
            yaw_deg: 0.,
            mode: "ffa".into(),
            team: None,
            group: None,
            locked: false,
        });
        let edited = load_with_placements(&assets(), MAP_ID, Some(&p)).unwrap();
        assert_eq!(edited.level.spawns.len(), initial.level.spawns.len() + 1);
        assert!(edited.level.spawns.iter().any(|s| s.team.is_none()));
    }

    #[test]
    fn full_world_player_boxes_follow_authored_standing_and_basement_routes() {
        let art = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../assets/maps/showhome_v3/extension");
        let full = load_with_placements(&assets(), FULL_MAP_ID, None).unwrap();
        let mut paths = vec![];
        let stairs: serde_json::Value =
            serde_json::from_slice(&fs::read(art.join("stairs_route.json")).unwrap()).unwrap();
        for route in stairs["building_routes"].as_array().unwrap() {
            paths.extend(route["supported_path"].as_array().unwrap().iter().cloned());
        }
        let parking: serde_json::Value =
            serde_json::from_slice(&fs::read(art.join("parking_report.json")).unwrap()).unwrap();
        paths.extend(parking["integrated_route_qa"]["supported_path"].as_array().unwrap().iter().cloned());
        let half = Vec3::new(0.32, 0.89, 0.32);
        for point in &paths {
            let p = std::array::from_fn(|k| point[k].as_f64().unwrap());
            let foot = Vec3::from_array(design_to_bevy(p, full.origin).map(|v| v as f32));
            let support = full.level.world.trace_box(foot + Vec3::Y * 1.25, foot + Vec3::Y * 0.4, half);
            assert!(
                support.hit() && !support.start_solid && support.walkable,
                "game route lacks support at{p:?}: {support:?}"
            );
            let centre = support.end + Vec3::Y * (SKIN * 2.);
            assert!(
                !full.level.world.trace_solid(centre, centre, half).start_solid,
                "game route player blocked at{p:?}"
            );
        }
        assert!(paths.len() > 1500);
    }

    #[test]
    fn transformed_preview_matches_independently_assembled_closed_convex_source() {
        let source = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../../assets/maps/showhome_v3/collision_assembled_qa.json");
        // Independent art QA is present in the authoring checkout, not a packaged game.
        if !source.is_file() {
            return;
        }
        let preview = load(&assets()).unwrap();
        let assembled = CollisionDocument::load(&source).unwrap().in_bevy(preview.origin).unwrap();
        assert_eq!(assembled.len(), preview.volumes.len());
        let lookup = assembled.iter().map(|v| (v.name.as_str(), v)).collect::<std::collections::BTreeMap<_, _>>();
        for volume in &preview.volumes {
            let name = if volume.extras.contains_key("instance_id") {
                format!("COL_{}", volume.name)
            } else {
                volume.name.clone()
            };
            let actual = lookup.get(name.as_str()).unwrap_or_else(|| panic!("Missing assembled {name}"));
            assert_eq!(volume.phys, actual.phys, "{name}");
            assert_eq!(volume.walkable, actual.walkable, "{name}");
            for point in &volume.vertices {
                assert!(
                    actual.vertices.iter().any(|other| point.iter().zip(other).all(|(a, b)| (a - b).abs() < 0.002)),
                    "{name}: actual closed vertex differs {point:?}"
                );
            }
            // Blender reconstructs hull planes from world-space f32 vertices. Thin glass can magnify
            // coefficient rounding; mutual containment verifies the actual solids rather than coefficients.
            assert!(
                volume.vertices.iter().all(|p| actual.contains(*p, 0.002)),
                "{name}: runtime vertices outside assembled hull"
            );
            assert!(
                actual.vertices.iter().all(|p| volume.contains(*p, 0.002)),
                "{name}: assembled vertices outside runtime hull"
            );
        }
    }
}
