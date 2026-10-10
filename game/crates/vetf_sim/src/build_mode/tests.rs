use super::collision::*;
use super::*;
use glam::{DMat4, DVec3};

fn assets() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../assets")
}
fn prop(id: &str) -> PropInstance {
    PropInstance {
        id: id.into(),
        prop_id: "concrete_barrier".into(),
        position: [1., 2., 0.],
        yaw_deg: 0.,
        tilt_deg: None,
        scale: 1.,
        color_variant: None,
        lootable: false,
        locked: false,
        mode: "all".into(),
    }
}
struct Temp {
    path: PathBuf,
    temp_root: PathBuf,
}
impl Temp {
    fn new() -> Self {
        let temp_root = std::env::temp_dir().canonicalize().unwrap();
        let stamp = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        let path = temp_root.join(format!(
            "vetf_build_mode_{}_{}_{}",
            std::process::id(),
            stamp,
            SAVE_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        // Never reuse or recursively create an existing test directory.
        fs::create_dir(&path).unwrap();
        Self { path, temp_root }
    }
}
impl Drop for Temp {
    fn drop(&mut self) {
        if let Ok(target) = self.path.canonicalize() {
            let own_name = target.file_name().is_some_and(|n| n.to_string_lossy().starts_with("vetf_build_mode_"));
            if target.parent() == Some(self.temp_root.as_path()) && own_name {
                let _ = fs::remove_dir_all(target);
            }
        }
    }
}

#[test]
fn build_mode_actual_ron_roundtrip_core_extension_and_implicit_some() {
    for relative in [
        "maps/showhome_v3/placements.ron",
        "maps/showhome_v3/placements.proposed.ron",
        "maps/showhome_v3/extension/placements.ron",
        "maps/showhome_v3/extension/placements.proposed.ron",
    ] {
        let doc = Placements::load(&assets().join(relative)).unwrap();
        assert!(doc.foliage_volumes.is_empty());
        let saved = doc.to_ron().unwrap();
        assert!(!saved.contains("foliage_volumes"));
        assert_eq!(Placements::from_ron(&saved).unwrap(), doc);
    }
    let text =
        r#"(schema:1,map_id:"test",instances:[(id:"blue",prop_id:"city_car",position:[0,0,0],color_variant:"blue")])"#;
    let doc = Placements::from_ron(text).unwrap();
    assert_eq!(doc.instances[0].color_variant.as_deref(), Some("blue"));
    assert_eq!(doc.instances[0].mode, "all");
    let catalog = PropCatalog::load(&assets().join("props/catalog.json")).unwrap();
    assert!(catalog.props.len() >= 47);
}

#[test]
fn build_mode_marker_data_roundtrip_and_edit_clip_preserves_size() {
    let text = r#"(schema:1,map_id:"markers",spawns:[(id:"s",position:[0,0,0],mode:"tdm",team:"A",group:"west")],extracts:[(id:"e",name:"Gate",position:[2,0,0],kind:"paid",parameters:(fee:100))],loot_spots:[(id:"l",position:[1,0,0],loot_table:"tools",spawn_chance:0.5,max_count:2)],player_clips:[(id:"c",min:[0,0,0],max:[2,4,6])])"#;
    let doc = Placements::from_ron(text).unwrap();
    assert_eq!(Placements::from_ron(&doc.to_ron().unwrap()).unwrap(), doc);
    let mut session = EditSession::new(doc.clone()).unwrap();
    session.apply(EditCommand::Move { id: "c".into(), position: [10., 20., 30.] }).unwrap();
    assert_eq!(session.document().player_clips[0].min, [9., 18., 27.]);
    assert_eq!(session.document().player_clips[0].max, [11., 22., 33.]);
    session.undo();
    assert_eq!(session.document(), &doc);
}

#[test]
fn build_mode_transactions_undo_redo_branch_and_locked_edits() {
    let mut doc = Placements::empty("test");
    doc.instances.push(prop("a"));
    let original = doc.clone();
    let mut session = EditSession::new(doc).unwrap();
    session
        .transaction(&[
            EditCommand::Move { id: "a".into(), position: [5., 6., 7.] },
            EditCommand::Rotate { id: "a".into(), yaw_deg: 45., tilt_deg: Some([10., 5.]) },
            EditCommand::Scale { id: "a".into(), scale: 1.2 },
        ])
        .unwrap();
    let changed = session.document().clone();
    assert!(session.undo());
    assert_eq!(session.document(), &original);
    assert!(session.redo());
    assert_eq!(session.document(), &changed);
    assert!(session.undo());
    session.apply(EditCommand::SetLocked { id: "a".into(), locked: true }).unwrap();
    assert!(!session.redo());
    let locked = session.document().clone();
    for command in [
        EditCommand::Move { id: "a".into(), position: [0.; 3] },
        EditCommand::Delete { id: "a".into() },
        EditCommand::SetLootable { id: "a".into(), lootable: true },
        EditCommand::Duplicate { id: "a".into(), new_id: "b".into(), offset: [0.; 3] },
    ] {
        assert!(matches!(session.apply(command), Err(BuildError::Locked(_))));
        assert_eq!(session.document(), &locked);
    }
    session.apply(EditCommand::SetLocked { id: "a".into(), locked: false }).unwrap();
    session.apply(EditCommand::Duplicate { id: "a".into(), new_id: "b".into(), offset: [1., 0., 0.] }).unwrap();
    assert_eq!(session.document().instances.len(), 2);
    let before = session.document().clone();
    assert!(
        session
            .transaction(&[
                EditCommand::Move { id: "a".into(), position: [10.; 3] },
                EditCommand::Scale { id: "b".into(), scale: 2. }
            ])
            .is_err()
    );
    assert_eq!(session.document(), &before);
}

#[test]
fn build_mode_proposals_never_apply_until_accepted_and_resolutions_undo() {
    let mut doc = Placements::empty("test");
    doc.instances.push(prop("a"));
    doc.instances.push(prop("deleted"));
    let mut proposal = doc.clone();
    proposal.instances[0].position = [8., 9., 0.];
    proposal.instances.retain(|p| p.id != "deleted");
    proposal.instances.push(prop("new"));
    let mut session = EditSession::new(doc.clone()).unwrap();
    session.set_proposal(proposal.clone()).unwrap();
    assert_eq!(session.document(), &doc);
    assert_eq!(session.proposals().unwrap().len(), 3);
    session.reject("a").unwrap();
    assert_eq!(session.document().instances[0].position, [1., 2., 0.]);
    assert!(session.proposals().unwrap().iter().find(|p| p.id == "a").unwrap().resolution.is_some());
    session.accept("new").unwrap();
    assert!(session.document().item("new").is_some());
    session.undo();
    assert!(session.document().item("new").is_none());
    session.redo();
    assert!(session.document().item("new").is_some());
    session.accept("deleted").unwrap();
    assert!(session.document().item("deleted").is_none());
    proposal.instances[0].position = [9., 9., 0.];
    session.set_proposal(proposal).unwrap();
    assert!(session.proposals().unwrap().iter().find(|p| p.id == "a").unwrap().resolution.is_none());
    session.accept("a").unwrap();
    assert_eq!(session.document().instances.iter().find(|p| p.id == "a").unwrap().position, [9., 9., 0.]);
}

#[test]
fn build_mode_snap_numbers_independent_and_scale_bounds() {
    let mut options = EditorOptions::default();
    assert_eq!(options.snap_position([0.13, -0.13, 1.12]), [0.25, -0.25, 1.]);
    assert_eq!(options.snap_yaw(23.), 30.);
    options.position_snap_m = 1.;
    assert_eq!(options.snap_yaw(23.), 30.);
    options.yaw_snap_deg = 90.;
    assert_eq!(options.snap_position([0.6, 0., 0.]), [1., 0., 0.]);
    let mut doc = Placements::empty("test");
    for scale in [0.8, 1.25] {
        let mut p = prop("a");
        p.scale = scale;
        doc.instances = vec![p];
        assert!(doc.validate().is_ok());
    }
    doc.instances[0].scale = 1.2501;
    assert!(doc.validate().is_err());
    assert_eq!(EditorOptions::load(&assets().join("data/build_mode.ron")).unwrap(), EditorOptions::default());
}

#[test]
fn build_mode_atomic_save_backups_last_ten_and_stale_writer() {
    let temp = Temp::new();
    let path = temp.path.join("placements.ron");
    let mut doc = Placements::empty("test");
    doc.instances.push(prop("a"));
    let options = EditorOptions::default();
    let saved = save_atomic(&path, &doc, &options, None).unwrap();
    assert!(saved.backup.is_none());
    let first = fs::read(&path).unwrap();
    doc.instances[0].position[0] = 3.;
    let second = save_atomic(&path, &doc, &options, Some(&sha256(&first))).unwrap();
    assert_eq!(fs::read(second.backup.unwrap()).unwrap(), first);
    assert!(matches!(save_atomic(&path, &doc, &options, Some("stale")), Err(BuildError::SaveConflict)));
    assert_eq!(Placements::load(&path).unwrap(), doc);
    for n in 0..12 {
        doc.instances[0].position[0] = n as f64;
        save_atomic(&path, &doc, &options, None).unwrap();
    }
    assert_eq!(fs::read_dir(temp.path.join(".build_mode_backups")).unwrap().count(), 10);
    assert_eq!(Placements::load(&path).unwrap(), doc);
    assert!(!fs::read_dir(&temp.path).unwrap().any(|e| e.unwrap().path().extension().is_some_and(|x| x == "tmp")));
}

#[test]
fn build_mode_hash_sorted_content_paths_and_user_placements() {
    let temp = Temp::new();
    fs::write(temp.path.join("a.glb"), b"a").unwrap();
    fs::write(temp.path.join("placements.ron"), b"p").unwrap();
    let files = vec![PathBuf::from("a.glb"), PathBuf::from("placements.ron")];
    let first = kit_placements_hash(&temp.path, &files).unwrap();
    assert_eq!(
        first,
        kit_placements_hash(&temp.path, &[files[1].clone(), files[0].clone(), files[0].clone()]).unwrap()
    );
    fs::write(temp.path.join("placements.ron"), b"q").unwrap();
    assert_ne!(first, kit_placements_hash(&temp.path, &files).unwrap());
    assert_eq!(sha256(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
}

#[test]
fn build_mode_real_convex_transform_origin_yaw_scale_tilt_and_stable_order() {
    let root = assets();
    let catalog = PropCatalog::load(&root.join("props/catalog.json")).unwrap();
    let source = CollisionDocument::load(&root.join(&catalog.get("concrete_barrier").unwrap().collision)).unwrap();
    let mut doc = Placements::empty("test");
    doc.origin = [330., 620., 0.];
    let mut p = prop("z");
    p.position = [334., 625., 1.];
    p.yaw_deg = 90.;
    p.scale = 1.2;
    p.tilt_deg = Some([8., 5.]);
    doc.instances.push(p.clone());
    let mut earlier = p.clone();
    earlier.id = "a".into();
    doc.instances.push(earlier);
    let output = instantiate_props(&root, &catalog, &doc, None).unwrap();
    assert!(output[0].name.starts_with("a__"));
    let matrix = design_to_bevy_matrix(doc.origin) * instance_design_matrix(&p);
    let row = output.iter().find(|r| r.name == format!("z__{}", source.volumes[0].name)).unwrap();
    assert_eq!(row.phys, source.volumes[0].phys);
    assert_eq!(row.walkable, source.volumes[0].walkable);
    assert_eq!(row.parent, source.volumes[0].parent);
    for (a, b) in source.volumes[0].vertices.iter().zip(&row.vertices) {
        assert!(matrix.transform_point3(DVec3::from_array(*a)).distance(DVec3::from_array(*b)) < 1e-9);
        assert!(row.contains(*b, 1e-5));
    }
    assert!((row.thickness_m - source.volumes[0].thickness_m * 1.2).abs() < 1e-5);
    assert_eq!(design_to_bevy([334., 625., 1.], doc.origin), [4., 1., -5.]);
    let rotation = design_basis() * DMat4::from_rotation_z(std::f64::consts::FRAC_PI_2) * design_basis().inverse();
    assert!((rotation.transform_vector3(DVec3::X) + DVec3::Z).length() < 1e-9);
}

#[test]
fn build_mode_closed_decor_uses_real_open_node_pivots_drawers_and_negative_lids() {
    let root = assets();
    let catalog = PropCatalog::load(&root.join("props/catalog.json")).unwrap();
    for pid in ["kitchen_base", "dresser", "ammo_box", "backpack"] {
        let descriptor = catalog.get(pid).unwrap();
        let source = CollisionDocument::load(&root.join(&descriptor.collision)).unwrap();
        let nodes = glb_node_world_matrices(&fs::read(root.join(&descriptor.glb)).unwrap()).unwrap();
        let parent = &descriptor.openable_parts[0].name;
        let delta = closed_container_delta(descriptor, parent, &nodes).unwrap();
        assert_ne!(delta, DMat4::IDENTITY);
        let mut doc = Placements::empty("test");
        let mut instance = prop("container");
        instance.prop_id = pid.into();
        instance.position = [0.; 3];
        doc.instances.push(instance.clone());
        let closed = instantiate_props(&root, &catalog, &doc, None).unwrap();
        doc.instances[0].lootable = true;
        let ajar = instantiate_props(&root, &catalog, &doc, None).unwrap();
        let source_row = source.volumes.iter().find(|r| r.parent.as_deref() == Some(parent)).unwrap();
        let closed_row = closed.iter().find(|r| r.name.ends_with(&source_row.name)).unwrap();
        let ajar_row = ajar.iter().find(|r| r.name.ends_with(&source_row.name)).unwrap();
        for ((original, a), b) in source_row.vertices.iter().zip(&closed_row.vertices).zip(&ajar_row.vertices) {
            let expected = design_basis() * delta;
            assert!(expected.transform_point3(DVec3::from_array(*original)).distance(DVec3::from_array(*a)) < 1e-9);
            assert!(
                design_basis().transform_point3(DVec3::from_array(*original)).distance(DVec3::from_array(*b)) < 1e-9
            );
        }
        assert_eq!(closed_row.planes.len(), source_row.planes.len());
        assert_eq!(closed_row.phys, source_row.phys);
    }
    // Structural OPEN gates retain their deliberately open authored pose.
    let mut doc = Placements::empty("test");
    let mut instance = prop("gate");
    instance.prop_id = "garden_gate".into();
    instance.position = [0.; 3];
    doc.instances.push(instance);
    let closed = instantiate_props(&root, &catalog, &doc, None).unwrap();
    doc.instances[0].lootable = true;
    assert_eq!(closed, instantiate_props(&root, &catalog, &doc, None).unwrap());
}

#[test]
fn build_mode_supplied_user_file_inspection_is_read_only() {
    let root = assets();
    let path = root.join("maps/showhome_v3/placements.ron");
    let before = fs::read(&path).unwrap();
    let report = inspect_map(&root, "showhome_v3").unwrap();
    assert!(report.valid);
    assert_eq!(report.catalog_props, PropCatalog::load(&root.join("props/catalog.json")).unwrap().props.len());
    let folder = root.join("maps/showhome_v3");
    let manifest: serde_json::Value =
        serde_json::from_slice(&fs::read(folder.join("map_manifest.json")).unwrap()).unwrap();
    let mut expected_fixed =
        CollisionDocument::load(&folder.join(manifest["collision"].as_str().unwrap())).unwrap().volumes.len();
    if let Some(layer) = manifest.get("extension") {
        expected_fixed +=
            CollisionDocument::load(&folder.join(layer["collision"].as_str().unwrap())).unwrap().volumes.len();
    }
    assert_eq!(report.fixed_collision_volumes, expected_fixed);
    assert!(report.prop_collision_volumes > 1000);
    assert!(report.pending_proposals > 0);
    assert_eq!(report.map_version_sha256.len(), 64);
    assert_eq!(fs::read(&path).unwrap(), before);
    assert!(report.deferred_client_features.iter().any(|s| s.contains("handshake")));
}

#[test]
fn build_mode_warnings_and_invalid_data_are_explicit() {
    let mut doc = Placements::empty("test");
    doc.instances = vec![prop("a"), prop("a")];
    assert!(doc.validate().is_err());
    doc.instances.pop();
    doc.instances[0].position[0] = f64::NAN;
    assert!(doc.validate().is_err());
    assert!(inspect_map(&assets(), "../showhome_v3").is_err());
    let report = inspect_map(&assets(), "showhome_v3").unwrap();
    assert!(report.warnings.iter().any(|w| w.code == "no_spawns"));
    assert!(report.warnings.iter().any(|w| w.code == "pending_proposals"));
}

#[test]
fn build_mode_foliage_defaults_and_ron_roundtrip() {
    let doc = Placements::from_ron(r#"(schema:1,map_id:"garden",foliage_volumes:[(id:"hedge")])"#).unwrap();
    let volume = &doc.foliage_volumes[0];
    assert_eq!(volume.kind, FoliageKind::Hedge);
    assert_eq!(volume.position, [0.; 3]);
    assert_eq!(volume.dimensions_m, [2., 1., 2.]);
    assert_eq!(volume.density, 1.);
    assert_eq!(volume.tint, "sage_hedge");
    assert_eq!(volume.mode, "all");
    assert_eq!(Placements::from_ron(&doc.to_ron().unwrap()).unwrap(), doc);
    assert!(
        Placements::from_ron(r#"(schema:1,map_id:"garden",foliage_volumes:[(id:"bad",kind:"grass_card")])"#).is_err()
    );
}

#[test]
fn build_mode_foliage_add_resize_scale_move_rotate_duplicate_delete_and_history() {
    let original = Placements::empty("garden");
    let mut session = EditSession::new(original.clone()).unwrap();
    let mut volume = FoliageVolume::new("run");
    volume.density = 1.7;
    volume.tint = "sage_hedge".into();
    session.apply(EditCommand::Add(EditableItem::Foliage(volume))).unwrap();
    let added = session.document().clone();
    session
        .transaction(&[
            EditCommand::Resize { id: "run".into(), dimensions_m: [12., 0.6, 3.] },
            EditCommand::Scale { id: "run".into(), scale: 2. },
            EditCommand::Move { id: "run".into(), position: [340., 646., 0.2] },
            EditCommand::Rotate { id: "run".into(), yaw_deg: 45., tilt_deg: None },
        ])
        .unwrap();
    let edited = session.document().clone();
    let v = &edited.foliage_volumes[0];
    assert_eq!(v.dimensions_m, [24., 1.2, 6.]);
    assert_eq!(v.position, [340., 646., 0.2]);
    assert_eq!(v.yaw_deg, 45.);
    assert_eq!(v.density, 1.7);
    assert_eq!(v.tint, "sage_hedge");
    assert!(session.undo());
    assert_eq!(session.document(), &added);
    assert!(session.redo());
    assert_eq!(session.document(), &edited);
    session.apply(EditCommand::Duplicate { id: "run".into(), new_id: "copy".into(), offset: [2., 3., 0.] }).unwrap();
    let duplicate = session.document().foliage_volumes[1].clone();
    assert_eq!(duplicate.position, [342., 649., 0.2]);
    assert_eq!(duplicate.dimensions_m, [24., 1.2, 6.]);
    session.apply(EditCommand::Delete { id: "run".into() }).unwrap();
    assert_eq!(session.document().foliage_volumes.len(), 1);
    assert!(session.undo());
    assert_eq!(session.document().foliage_volumes.len(), 2);
    assert!(session.undo());
    assert_eq!(session.document(), &edited);
    assert!(session.undo());
    assert_eq!(session.document(), &added);
    assert!(session.undo());
    assert_eq!(session.document(), &original);
}

#[test]
fn build_mode_foliage_locked_and_invalid_edits_never_change_state_or_prop_limits() {
    let mut doc = Placements::empty("garden");
    doc.foliage_volumes.push(FoliageVolume::new("run"));
    doc.instances.push(prop("prop"));
    let mut session = EditSession::new(doc).unwrap();
    session.apply(EditCommand::SetLocked { id: "run".into(), locked: true }).unwrap();
    let locked = session.document().clone();
    for command in [
        EditCommand::Resize { id: "run".into(), dimensions_m: [10., 1., 3.] },
        EditCommand::Scale { id: "run".into(), scale: 2. },
        EditCommand::Move { id: "run".into(), position: [10.; 3] },
        EditCommand::Rotate { id: "run".into(), yaw_deg: 90., tilt_deg: None },
        EditCommand::Delete { id: "run".into() },
        EditCommand::Duplicate { id: "run".into(), new_id: "copy".into(), offset: [0.; 3] },
    ] {
        assert!(matches!(session.apply(command), Err(BuildError::Locked(_))));
        assert_eq!(session.document(), &locked);
    }
    session.apply(EditCommand::SetLocked { id: "run".into(), locked: false }).unwrap();
    let before = session.document().clone();
    for dimensions_m in [[0., 1., 2.], [-1., 1., 2.], [1., f64::NAN, 2.], [1., 1., f64::INFINITY]] {
        assert!(session.apply(EditCommand::Resize { id: "run".into(), dimensions_m }).is_err());
        assert_eq!(session.document(), &before);
    }
    for scale in [0., -1., f64::NAN, f64::INFINITY] {
        assert!(session.apply(EditCommand::Scale { id: "run".into(), scale }).is_err());
        assert_eq!(session.document(), &before);
    }
    assert!(session.apply(EditCommand::Rotate { id: "run".into(), yaw_deg: 30., tilt_deg: Some([0., 5.]) }).is_err());
    assert!(session.apply(EditCommand::Resize { id: "prop".into(), dimensions_m: [10., 1., 2.] }).is_err());
    for scale in [0.79, 1.251, 2.] {
        assert!(session.apply(EditCommand::Scale { id: "prop".into(), scale }).is_err());
    }
    assert_eq!(session.document(), &before);
    session.apply(EditCommand::Resize { id: "run".into(), dimensions_m: [15., 0.1, 4.5] }).unwrap();
    assert_eq!(session.document().foliage_volumes[0].dimensions_m, [15., 0.1, 4.5]);
    let mut invalid = FoliageVolume::new("invalid");
    invalid.density = -1.;
    let valid_state = session.document().clone();
    assert!(session.apply(EditCommand::Add(EditableItem::Foliage(invalid.clone()))).is_err());
    invalid.density = f64::INFINITY;
    assert!(session.apply(EditCommand::Add(EditableItem::Foliage(invalid.clone()))).is_err());
    invalid.density = 1.;
    invalid.tint.clear();
    assert!(session.apply(EditCommand::Add(EditableItem::Foliage(invalid))).is_err());
    assert_eq!(session.document(), &valid_state);
}

#[test]
fn build_mode_foliage_export_matches_oriented_collision_origin_and_visual_envelope() {
    let mut doc = Placements::empty("garden");
    doc.origin = [330., 620., 0.];
    let mut volume = FoliageVolume::new("run");
    volume.position = [338., 640., 0.2];
    volume.dimensions_m = [12., 0.8, 4.];
    volume.yaw_deg = 45.;
    volume.density = 1.7;
    volume.tint = "sage_hedge".into();
    doc.foliage_volumes.push(volume.clone());
    let records = collision::instantiate_foliage(&doc, None).unwrap();
    let export = &records[0];
    assert_eq!(export.id, "run");
    assert_eq!(export.collision.phys, "foliage_dense");
    assert_eq!(export.density, 1.7);
    assert_eq!(export.tint, "sage_hedge");
    assert_eq!(export.mode, "all");
    assert_eq!(export.local_bounds_bevy.min, [-6., 0., -0.4]);
    assert_eq!(export.local_bounds_bevy.max, [6., 4., 0.4]);
    assert_eq!(export.collision.vertices.len(), 8);
    assert_eq!(export.collision.planes.len(), 6);
    let transform = DMat4::from_cols_array(&export.transform_bevy);
    assert!((transform.transform_point3(DVec3::ZERO) - DVec3::new(8., 0.2, -20.)).length() < 1e-10);
    for vertex in &export.collision.vertices {
        assert!(export.collision.contains(*vertex, 1e-8));
    }
    for plane in &export.collision.planes {
        let on_plane = export
            .collision
            .vertices
            .iter()
            .filter(|v| (plane[0] * v[0] + plane[1] * v[1] + plane[2] * v[2] - plane[3]).abs() < 1e-8)
            .count();
        assert_eq!(on_plane, 4);
    }
    for x in [-6., 6.] {
        for y in [0., 4.] {
            for z in [-0.4, 0.4] {
                let expected = transform.transform_point3(DVec3::new(x, y, z));
                assert!(export.collision.vertices.iter().any(|v| expected.distance(DVec3::from_array(*v)) < 1e-9));
            }
        }
    }
    let bounds = &export.world_bounds_bevy;
    let outside = [bounds.max[0] - 0.05, 2.2, bounds.max[2] - 0.05];
    assert!(!export.collision.contains(outside, 1e-8), "A rotated narrow hedge must not become its broad AABB");
    assert!((export.collision.thickness_m - 0.8).abs() < 1e-9);
    assert_eq!(export.collision.extras["density"], serde_json::json!(1.7));
    assert_eq!(export.collision.extras["tint"], serde_json::json!("sage_hedge"));
}

#[test]
fn build_mode_foliage_kinds_modes_order_and_explicit_authoring_import() {
    let mut doc = Placements::empty("garden");
    for (id, kind, mode) in [
        ("z", FoliageKind::Hedge, "all"),
        ("a", FoliageKind::Tree, "extraction"),
        ("b", FoliageKind::Climber, "tdm"),
        ("c", FoliageKind::Bush, "all"),
    ] {
        let mut v = FoliageVolume::new(id);
        v.kind = kind;
        v.mode = mode.into();
        v.tint = "custom_palette_token".into();
        v.density = 0.75;
        doc.foliage_volumes.push(v);
    }
    let all = foliage::export_foliage(&doc, None).unwrap();
    assert_eq!(all.iter().map(|v| v.id.as_str()).collect::<Vec<_>>(), vec!["a", "b", "c", "z"]);
    assert_eq!(all[0].collision.phys, "foliage_thin");
    assert_eq!(all[1].collision.phys, "foliage_thin");
    assert_eq!(all[2].collision.phys, "foliage_dense");
    assert_eq!(all[3].collision.phys, "foliage_dense");
    assert_eq!(
        foliage::export_foliage(&doc, Some("tdm")).unwrap().iter().map(|v| v.id.as_str()).collect::<Vec<_>>(),
        vec!["b", "c", "z"]
    );
    let path = assets().join("maps/showhome_v3/foliage.json");
    let before = fs::read(&path).unwrap();
    let json = std::str::from_utf8(&before).unwrap();
    let imported = foliage::import_authoring_foliage(json, "editable_").unwrap();
    assert!(!imported.is_empty());
    let source: serde_json::Value = serde_json::from_str(json).unwrap();
    let first = &source[0];
    assert!(imported[0].id.starts_with("editable_"));
    assert_eq!(imported[0].position[2], first["aabb"]["min"][2].as_f64().unwrap());
    assert_eq!(imported[0].density, first["density"].as_f64().unwrap());
    assert_eq!(imported[0].tint, first["tint"].as_str().unwrap());
    assert!(foliage::import_authoring_foliage(json, "").is_err());
    assert_eq!(fs::read(&path).unwrap(), before);
    let versioned = fs::read_to_string(assets().join("maps/showhome_v3/extension/foliage.json")).unwrap();
    assert!(!foliage::import_authoring_foliage(&versioned, "extension_").unwrap().is_empty());
    assert_eq!(
        Placements::load(&assets().join("maps/showhome_v3/placements.ron")).unwrap().foliage_volumes.len(),
        0,
        "Fixed foliage is never automatically duplicated into user placements"
    );
}

#[test]
fn build_mode_foliage_proposals_participate_in_stable_id_accept_reject_undo() {
    let mut current = Placements::empty("garden");
    current.foliage_volumes.push(FoliageVolume::new("run"));
    let mut proposed = current.clone();
    proposed.foliage_volumes[0].dimensions_m = [20., 1.2, 3.5];
    let mut session = EditSession::new(current.clone()).unwrap();
    session.set_proposal(proposed).unwrap();
    assert_eq!(session.document(), &current);
    assert_eq!(session.proposals().unwrap().len(), 1);
    session.reject("run").unwrap();
    assert_eq!(session.document().foliage_volumes[0].dimensions_m, [2., 1., 2.]);
    session.accept("run").unwrap();
    assert_eq!(session.document().foliage_volumes[0].dimensions_m, [20., 1.2, 3.5]);
    session.undo();
    assert_eq!(session.document().foliage_volumes[0].dimensions_m, [2., 1., 2.]);
    session.redo();
    assert_eq!(session.document().foliage_volumes[0].dimensions_m, [20., 1.2, 3.5]);
}
