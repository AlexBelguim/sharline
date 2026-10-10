//! Showhome art-kit scenes, in their exported design frame, with the painted cube sky.
//!
//! Bevy 0.19 calls glTF scene roots `WorldAssetRoot` (formerly `SceneRoot`). Original Showhome uses its four
//! exports at identity. V3 loads two fixed exports relative to its design origin and individual catalog props
//! from the same read-only placement snapshot as exact collision. Material names/extras remain available to
//! ground, surface-depth, grass and decal systems.

use crate::AppState;
use crate::config::CurrentLevel;
use crate::map_materials::{
    DepthQuality, ShowhomeMaterials, SurfaceDepthData, SurfaceDepthLevel, mip_chain, parallax_scale, r16_to_f16,
};
use crate::render::ViewCamera;
use bevy::asset::AssetId;
use bevy::asset::RenderAssetUsages;
use bevy::camera::primitives::Aabb;
use bevy::gltf::{GltfMaterialExtras, GltfMaterialName, GltfMeshName};
use bevy::image::{ImageAddressMode, ImageLoaderSettings, ImageSampler, ImageSamplerDescriptor};
use bevy::light::{NotShadowCaster, Skybox};
use bevy::prelude::*;
use bevy::render::render_resource::{TextureDataOrder, TextureFormat, TextureViewDescriptor, TextureViewDimension};
use bevy::tasks::{AsyncComputeTaskPool, Task, futures::check_ready};
use bevy::world_serialization::WorldInstanceReady;
use serde::Deserialize;
use std::collections::{HashMap, HashSet};
use vetf_sim::movement::collision::Look;

pub struct ShowhomeKitPlugin;

impl Plugin for ShowhomeKitPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<ShowhomeKitAssets>()
            .init_resource::<NormalStrengthState>()
            .init_resource::<KitDepthState>()
            .init_resource::<KitMipState>()
            .add_systems(OnEnter(AppState::InGame), (spawn_kit, spawn_test_props))
            .add_systems(
                Update,
                (
                    prepare_sky,
                    attach_sky,
                    apply_normal_strengths,
                    finish_kit_mips,
                    reuse_hedge_materials,
                    apply_kit_depth,
                    report_failed_scenes,
                    stop_flat_ground_casters,
                )
                    .chain()
                    .after(crate::video::apply_surface_depth)
                    .run_if(in_state(AppState::InGame)),
            );
    }
}

#[derive(Component, Clone, Copy, Debug, PartialEq, Eq)]
pub enum ShowhomeKitPart {
    Houses,
    Ground,
    Props,
    Backdrop,
}

/// Present on each actual mesh after its scene has spawned. The imported material extras stay on it.
#[derive(Component, Clone, Copy, Debug)]
pub struct ShowhomeKitMesh(pub ShowhomeKitPart);

#[derive(Component)]
struct ReusedHedgeMaterial;

#[derive(Component)]
struct NormalStrengths(std::collections::BTreeMap<String, f32>);
#[derive(Component)]
struct ImportedNormalStrength(f32);
#[derive(Resource, Default)]
struct NormalStrengthState {
    processed: HashSet<AssetId<StandardMaterial>>,
    images: HashMap<(AssetId<Image>, u32), Handle<Image>>,
}

struct KitScene {
    path: String,
    part: ShowhomeKitPart,
    handle: Handle<WorldAsset>,
    failure_reported: bool,
}

/// The kit's scenes and sky, kept after a match as a cache: the next Showhome match spawns at once instead of
/// reloading 200 MB of GLBs. What that keeps resident is mostly on the GPU: the textures' CPU copies are dropped
/// once their mips are built (`finish_kit_mips`), the meshes stay in both worlds (the bullet marks' surfaces
/// read them).
#[derive(Resource, Default)]
struct ShowhomeKitAssets {
    map: String,
    scenes: Vec<KitScene>,
    sky: Option<Handle<Image>>,
    sky_prepared: bool,
    sky_failure_reported: bool,
}

const SCENES: [(&str, ShowhomeKitPart); 4] = [
    ("maps/showhome/houses.glb", ShowhomeKitPart::Houses),
    ("maps/showhome/ground.glb", ShowhomeKitPart::Ground),
    ("maps/showhome/props_placed.glb", ShowhomeKitPart::Props),
    ("maps/showhome/backdrop.glb", ShowhomeKitPart::Backdrop),
];
const SKY: &str = "maps/showhome/sky/sky_cube_strip.png";
/// The delivered strip is right-handed: build_sky.py paints face +Z with the view toward world +Z (south). Bevy's
/// skybox samples cube maps left-handed (the direction times (1, 1, -1)), which showed the sky mirrored north to
/// south (map-kit review K6), so the faces are mirrored in z when the strip is prepared ([`mirror_cube_z`]). Set
/// this false once build_sky.py writes a left-handed strip.
const SKY_STRIP_RIGHT_HANDED: bool = true;
/// Physical brightness, following Bevy's PNG cube-sky example, with the look-dev's 0.65 sky strength.
const SKY_BRIGHTNESS: f32 = 650.0;

pub fn is_showhome(level: &CurrentLevel) -> bool {
    level.name.eq_ignore_ascii_case("showhome") || crate::showhome_v3::is_v3(&level.name)
}

#[derive(Component)]
struct PreviewProp {
    instance: vetf_sim::build_mode::PropInstance,
    descriptor: vetf_sim::build_mode::PropDescriptor,
}

#[derive(Component, Clone, Debug)]
pub struct PreviewInstanceId(pub String);

/// Spawn an editable catalog instance with the same pose, tint, depth and
/// authored normal-strength observers used by normal map loading.
pub fn spawn_preview_prop(
    commands: &mut Commands,
    server: &AssetServer,
    row: &vetf_sim::build_mode::PropInstance,
    descriptor: &vetf_sim::build_mode::PropDescriptor,
    origin: [f64; 3],
) -> Entity {
    let scales = crate::showhome_v3::normal_scales_for_path(&descriptor.glb).unwrap_or_default();
    spawn_preview_prop_with_scales(
        commands,
        server.load(GltfAssetLabel::Scene(0).from_asset(descriptor.glb.clone())),
        row,
        descriptor,
        origin,
        scales,
    )
}
fn spawn_preview_prop_with_scales(
    commands: &mut Commands,
    handle: Handle<WorldAsset>,
    row: &vetf_sim::build_mode::PropInstance,
    descriptor: &vetf_sim::build_mode::PropDescriptor,
    origin: [f64; 3],
    scales: std::collections::BTreeMap<String, f32>,
) -> Entity {
    commands
        .spawn((
            Name::new(row.id.clone()),
            PreviewInstanceId(row.id.clone()),
            ShowhomeKitPart::Props,
            NormalStrengths(scales),
            PreviewProp { instance: row.clone(), descriptor: descriptor.clone() },
            WorldAssetRoot(handle),
            preview_prop_transform(row, origin),
            Visibility::Inherited,
            DespawnOnExit(AppState::InGame),
        ))
        .observe(mark_scene_meshes)
        .observe(apply_preview_prop_pose)
        .id()
}

pub fn preview_prop_transform(row: &vetf_sim::build_mode::PropInstance, origin: [f64; 3]) -> Transform {
    let position = vetf_sim::build_mode::collision::design_to_bevy(row.position, origin);
    let [x, y] = row.tilt_deg.unwrap_or([0., 0.]);
    Transform::from_translation(Vec3::from_array(position.map(|v| v as f32)))
        .with_rotation(
            Quat::from_rotation_y(row.yaw_deg.to_radians() as f32)
                * Quat::from_axis_angle(Vec3::NEG_Z, y.to_radians() as f32)
                * Quat::from_rotation_x(x.to_radians() as f32),
        )
        .with_scale(Vec3::splat(row.scale as f32))
}

/// Sun compass azimuth is clockwise from design north; Bevy north is -Z. Light local -Z points groundward.
pub fn sun_transform() -> Transform {
    let (a, e) = (188.0_f32.to_radians(), 54.0_f32.to_radians());
    let toward_sun = Vec3::new(a.sin() * e.cos(), e.sin(), -a.cos() * e.cos());
    Transform::default().looking_to(-toward_sun, Vec3::Y)
}

fn spawn_kit(
    mut commands: Commands,
    level: Res<CurrentLevel>,
    server: Res<AssetServer>,
    mut assets: ResMut<ShowhomeKitAssets>,
    preview: Option<Res<crate::showhome_v3::CurrentV3Preview>>,
) {
    if !is_showhome(&level) {
        return;
    }
    if assets.map != level.name {
        *assets = ShowhomeKitAssets { map: level.name.clone(), ..default() };
    }
    if let Some(preview) = preview {
        let data = &preview.0;
        // Refresh paths from this session's snapshot, while retaining GPU handles between matches.
        let mut paths = data
            .kit_scenes
            .iter()
            .map(|p| {
                (p.clone(), if p.ends_with("houses.glb") { ShowhomeKitPart::Houses } else { ShowhomeKitPart::Ground })
            })
            .collect::<Vec<_>>();
        for row in &data.placements.instances {
            if row.mode != "all" && row.mode != data.asset_mode {
                continue;
            }
            let Ok(descriptor) = data.catalog.get(&row.prop_id) else { continue };
            if !paths.iter().any(|(p, _)| p == &descriptor.glb) {
                paths.push((descriptor.glb.clone(), ShowhomeKitPart::Props));
            }
        }
        assets.scenes.retain(|s| paths.iter().any(|(p, _)| p == &s.path));
        for (path, part) in paths {
            if !assets.scenes.iter().any(|s| s.path == path) {
                assets.scenes.push(KitScene {
                    handle: server.load(GltfAssetLabel::Scene(0).from_asset(path.clone())),
                    path,
                    part,
                    failure_reported: false,
                });
            }
        }
        if assets.sky.is_none() {
            assets.sky = Some(
                server
                    .load_builder()
                    .with_settings(|s: &mut ImageLoaderSettings| s.is_srgb = true)
                    .load("maps/showhome_v3/sky/sky_cube_strip.png"),
            );
        }
        let [x, y, z] = data.origin;
        for scene in assets.scenes.iter().filter(|s| s.part != ShowhomeKitPart::Props) {
            commands
                .spawn((
                    Name::new(format!("Showhome v3 {:?}", scene.part)),
                    scene.part,
                    NormalStrengths(preview.1.get(&scene.path).cloned().unwrap_or_default()),
                    WorldAssetRoot(scene.handle.clone()),
                    Transform::from_xyz(-x as f32, -z as f32, y as f32),
                    Visibility::Inherited,
                    DespawnOnExit(AppState::InGame),
                ))
                .observe(mark_scene_meshes);
        }
        for row in &data.placements.instances {
            if row.mode != "all" && row.mode != data.asset_mode {
                continue;
            }
            let Ok(descriptor) = data.catalog.get(&row.prop_id) else { continue };
            let Some(scene) = assets.scenes.iter().find(|s| s.path == descriptor.glb) else { continue };
            spawn_preview_prop_with_scales(
                &mut commands,
                scene.handle.clone(),
                row,
                descriptor,
                data.origin,
                preview.1.get(&scene.path).cloned().unwrap_or_default(),
            );
        }
        return;
    }
    if assets.scenes.is_empty() {
        assets.scenes = SCENES
            .into_iter()
            .map(|(path, part)| KitScene {
                path: path.into(),
                part,
                handle: server.load(GltfAssetLabel::Scene(0).from_asset(path)),
                failure_reported: false,
            })
            .collect();
        assets.sky =
            Some(server.load_builder().with_settings(|s: &mut ImageLoaderSettings| s.is_srgb = true).load(SKY));
    }
    for scene in &assets.scenes {
        commands
            .spawn((
                Name::new(format!("Showhome {:?}", scene.part)),
                scene.part,
                WorldAssetRoot(scene.handle.clone()),
                Transform::IDENTITY,
                Visibility::Inherited,
                DespawnOnExit(AppState::InGame),
            ))
            .observe(mark_scene_meshes);
    }
}

/// Local test props: `maps/showhome/test_props.ron` (not committed) lists glTF scenes to place by hand for a look in
/// game (e.g. the image-to-3D prop tests). Visual only, with no collision. Nothing happens when the file is missing.
#[derive(Deserialize)]
struct TestProps {
    props: Vec<TestProp>,
}

#[derive(Deserialize)]
struct TestProp {
    path: String,
    translation: (f32, f32, f32),
    yaw_deg: f32,
    scale: f32,
}

fn spawn_test_props(mut commands: Commands, level: Res<CurrentLevel>, server: Res<AssetServer>) {
    if !level.name.eq_ignore_ascii_case("showhome") {
        return;
    }
    let root = crate::config::assets_root();
    let Ok(text) = std::fs::read_to_string(root.join("maps/showhome/test_props.ron")) else { return };
    let list: TestProps = match ron::from_str(&text) {
        Ok(list) => list,
        Err(e) => {
            warn!("maps/showhome/test_props.ron: {e}");
            return;
        }
    };
    for prop in list.props {
        if !root.join(&prop.path).is_file() {
            warn!("test prop {} is missing", prop.path);
            continue;
        }
        let (x, y, z) = prop.translation;
        commands.spawn((
            WorldAssetRoot(server.load(GltfAssetLabel::Scene(0).from_asset(prop.path.clone()))),
            Transform::from_xyz(x, y, z)
                .with_rotation(Quat::from_rotation_y(prop.yaw_deg.to_radians()))
                .with_scale(Vec3::splat(prop.scale)),
            Visibility::Inherited,
            DespawnOnExit(AppState::InGame),
            Name::new(format!("test prop {}", prop.path)),
        ));
        info!("test prop {} placed", prop.path);
    }
}

fn mark_scene_meshes(
    ready: On<WorldInstanceReady>,
    mut commands: Commands,
    roots: Query<(&ShowhomeKitPart, Option<&NormalStrengths>)>,
    tree: Query<&Children>,
    meshes: Query<(), With<Mesh3d>>,
    names: Query<(&Name, Option<&GltfMeshName>, Option<&GltfMaterialName>)>,
) {
    let Ok((&part, strengths)) = roots.get(ready.entity) else { return };
    let mut count = 0;
    for entity in tree.iter_descendants(ready.entity) {
        if !meshes.contains(entity) {
            continue;
        }
        count += 1;
        commands.entity(entity).insert(ShowhomeKitMesh(part));
        if let Some(strengths) = strengths
            && let Ok((_, _, Some(material))) = names.get(entity)
            && let Some(scale) = strengths.0.get(&material.0)
        {
            commands.entity(entity).insert(ImportedNormalStrength(*scale));
        }
        if part == ShowhomeKitPart::Backdrop
            && names.get(entity).is_ok_and(|(name, mesh, _)| {
                name.as_str().starts_with("SHB_Far") || mesh.is_some_and(|n| n.0.starts_with("SHB_Far"))
            })
        {
            commands.entity(entity).insert(NotShadowCaster);
        }
    }
    debug!("Showhome {part:?} scene ready: {count} meshes");
}

/// Bevy 0.19's glTF loader ignores normalTexture.scale. Apply its specified XY scale to a private image,
/// preserving shared source images and the legacy map. The existing mip builder then processes this image.
fn scale_normal_image(source: &Image, scale: f32) -> Option<Image> {
    if !matches!(source.texture_descriptor.format, TextureFormat::Rgba8Unorm | TextureFormat::Rgba8UnormSrgb) {
        return None;
    }
    let mut result = source.clone();
    for pixel in result.data.as_mut()?.as_chunks_mut::<4>().0 {
        let n = Vec3::new(
            (pixel[0] as f32 / 255. * 2. - 1.) * scale,
            (pixel[1] as f32 / 255. * 2. - 1.) * scale,
            pixel[2] as f32 / 255. * 2. - 1.,
        )
        .normalize_or_zero();
        let n = if n == Vec3::ZERO { Vec3::Z } else { n };
        for (i, component) in n.to_array().iter().enumerate() {
            pixel[i] = ((component * 0.5 + 0.5) * 255.).round().clamp(0., 255.) as u8;
        }
    }
    result.asset_usage = RenderAssetUsages::MAIN_WORLD | RenderAssetUsages::RENDER_WORLD;
    Some(result)
}

fn apply_normal_strengths(
    meshes: Query<(&ImportedNormalStrength, &MeshMaterial3d<StandardMaterial>)>,
    mut state: ResMut<NormalStrengthState>,
    mut images: ResMut<Assets<Image>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut summary: Local<(usize, usize, usize, u8)>,
) {
    for (strength, material) in &meshes {
        if state.processed.contains(&material.0.id()) {
            continue;
        }
        let Some(source) = materials.get(&material.0).and_then(|m| m.normal_map_texture.clone()) else { continue };
        let key = (source.id(), strength.0.to_bits());
        let handle = if let Some(handle) = state.images.get(&key) {
            handle.clone()
        } else {
            let Some(image) = images.get(&source) else { continue };
            let Some(scaled) = scale_normal_image(image, strength.0) else { continue };
            let handle = images.add(scaled);
            state.images.insert(key, handle.clone());
            handle
        };
        if let Some(mut material) = materials.get_mut(&material.0) {
            material.normal_map_texture = Some(handle);
        }
        state.processed.insert(material.0.id());
    }
    let count = meshes.iter().count();
    if count == 0 {
        return;
    }
    let counts = (state.processed.len(), state.images.len(), count);
    if counts != (summary.0, summary.1, summary.2) {
        *summary = (counts.0, counts.1, counts.2, 0);
    } else if summary.3 < 60 {
        summary.3 += 1;
        if summary.3 == 60 {
            info!(
                "Showhome v3 supplied glTF normal strengths applied: {} materials, {} private images, {} tagged standard-mesh primitives",
                counts.0, counts.1, counts.2
            );
        }
    }
}

/// Match the authored preview's closed decorative containers. OPEN pivots remain at their actual glTF
/// node translations; only the authored hinge rotation or drawer translation is reset.
fn apply_preview_prop_pose(
    ready: On<WorldInstanceReady>,
    mut commands: Commands,
    roots: Query<&PreviewProp>,
    tree: Query<&Children>,
    mut nodes: Query<(&Name, &mut Transform)>,
    meshes: Query<(&GltfMaterialName, &MeshMaterial3d<StandardMaterial>)>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let Ok(prop) = roots.get(ready.entity) else { return };
    let close = prop.descriptor.category == "containers" && !prop.instance.lootable;
    let blue = prop.instance.prop_id == "city_car" && prop.instance.color_variant.as_deref() == Some("blue");
    let mut blue_materials = HashMap::new();
    for entity in tree.iter_descendants(ready.entity) {
        if close
            && let Ok((name, mut transform)) = nodes.get_mut(entity)
            && let Some(part) = prop.descriptor.openable_parts.iter().find(|p| p.name == name.as_str())
        {
            if part.properties.axis == "DRAWER" {
                if let Some(position) = part.properties.closed_location {
                    let p = vetf_sim::build_mode::collision::design_to_bevy(position, [0.; 3]);
                    transform.translation = Vec3::from_array(p.map(|v| v as f32));
                }
            } else {
                transform.rotation = Quat::IDENTITY;
            }
        }
        if blue
            && let Ok((name, source)) = meshes.get(entity)
            && name.0 == "M_CarSilver"
        {
            let handle = blue_materials.entry(source.0.id()).or_insert_with(|| {
                let mut material = materials.get(&source.0).cloned().unwrap_or_default();
                material.base_color = Color::linear_rgb(0.045, 0.19, 0.34);
                materials.add(material)
            });
            commands.entity(entity).insert(MeshMaterial3d(handle.clone()));
        }
    }
}

/// Kit ground meshes at most this tall (the lawn, paving, asphalt, edging, painted lines: a few millimetres of
/// relief) cast no shadow. They are the lowest surface, so their shadow could only fall on themselves, and they
/// are over half of the ground's triangles (about 200k of 370k, drawn into every shadow cascade). Kerbs (11 cm),
/// walls, sand heaps and everything else on the ground still cast.
pub const FLAT_GROUND_M: f32 = 0.03;

/// A mesh's height in the world: its bounds' vertical extent through its transform.
pub fn world_height(aabb: &Aabb, transform: &GlobalTransform) -> f32 {
    let m = transform.affine().matrix3;
    let up = Vec3A::new(m.x_axis.y, m.y_axis.y, m.z_axis.y);
    2.0 * up.abs().dot(aabb.half_extents)
}

fn stop_flat_ground_casters(
    mut commands: Commands,
    meshes: Query<
        (Entity, &ShowhomeKitMesh, &Aabb, &GlobalTransform),
        (Without<NotShadowCaster>, Or<(Added<Aabb>, Added<ShowhomeKitMesh>)>),
    >,
) {
    for (entity, part, aabb, transform) in &meshes {
        if part.0 == ShowhomeKitPart::Ground && world_height(aabb, transform) <= FLAT_GROUND_M {
            commands.entity(entity).insert(NotShadowCaster);
        }
    }
}

fn prepare_sky(
    level: Res<CurrentLevel>,
    mut assets: ResMut<ShowhomeKitAssets>,
    mut images: ResMut<Assets<Image>>,
    server: Res<AssetServer>,
) {
    if !is_showhome(&level) || assets.sky_prepared {
        return;
    }
    let Some(handle) = assets.sky.clone() else { return };
    if server.load_state(&handle).is_failed() && !assets.sky_failure_reported {
        warn!("Showhome cube sky could not load: {SKY}");
        assets.sky_failure_reported = true;
        return;
    }
    let Some(mut image) = images.get_mut(&handle) else { return };
    // Face order in the delivered strip is +X,-X,+Y,-Y,+Z,-Z, in glTF / Bevy axes, built right-handed
    // (`SKY_STRIP_RIGHT_HANDED`).
    if image.texture_descriptor.array_layer_count() == 1 {
        if image.height() != image.width() * 6 {
            if !assets.sky_failure_reported {
                error!("Showhome sky strip must be six square faces, found {}x{}", image.width(), image.height());
                assets.sky_failure_reported = true;
            }
            return;
        }
        if let Err(error) = image.reinterpret_stacked_2d_as_array(6) {
            error!("Cannot prepare Showhome cube sky: {error}");
            assets.sky_failure_reported = true;
            return;
        }
        let w = image.width() as usize;
        if SKY_STRIP_RIGHT_HANDED && let Some(data) = image.data.as_mut() {
            mirror_cube_z(data, w);
        }
    }
    image.texture_view_descriptor =
        Some(TextureViewDescriptor { dimension: Some(TextureViewDimension::Cube), ..default() });
    assets.sky_prepared = true;
}

/// Mirror a cube map's six stacked faces (+X, -X, +Y, -Y, +Z, -Z, each `w` x `w`, one mip) in z: the map then
/// shows at direction (x, y, z) what it showed at (x, y, -z). In the cube faces' own image axes (s right, t down;
/// +X: s = -z, -X: s = z, +Y: t = z, -Y: t = -z, +Z: s = x, -Z: s = -x) that is: the X faces flip left-right,
/// the Y faces flip top-bottom, and the Z faces swap and flip left-right.
pub fn mirror_cube_z(data: &mut [u8], w: usize) {
    let face = data.len() / 6;
    if w == 0 || face == 0 || !face.is_multiple_of(w * w) {
        return;
    }
    let px = face / (w * w);
    let row = w * px;
    let flip_rows = |f: &mut [u8]| {
        for r in f.chunks_exact_mut(row) {
            for x in 0..w / 2 {
                let (a, b) = (x * px, (w - 1 - x) * px);
                for k in 0..px {
                    r.swap(a + k, b + k);
                }
            }
        }
    };
    let (xs, rest) = data.split_at_mut(2 * face);
    let (ys, zs) = rest.split_at_mut(2 * face);
    flip_rows(xs);
    for f in ys.chunks_exact_mut(face) {
        for y in 0..w / 2 {
            let (top, bottom) = f.split_at_mut((w - 1 - y) * row);
            top[y * row..(y + 1) * row].swap_with_slice(&mut bottom[..row]);
        }
    }
    let (pz, nz) = zs.split_at_mut(face);
    pz.swap_with_slice(nz);
    flip_rows(zs);
}

fn attach_sky(
    mut commands: Commands,
    level: Res<CurrentLevel>,
    assets: Res<ShowhomeKitAssets>,
    cameras: Query<Entity, (With<ViewCamera>, Without<Skybox>)>,
) {
    if !is_showhome(&level) || !assets.sky_prepared {
        return;
    }
    let Some(handle) = assets.sky.as_ref() else { return };
    // ViewCamera is created by a different OnEnter system. Update sees it after deferred commands apply.
    for camera in &cameras {
        commands.entity(camera).insert((
            Skybox { image: Some(handle.clone()), brightness: SKY_BRIGHTNESS, rotation: Quat::IDENTITY },
            DistanceFog {
                color: Color::srgb(0.66, 0.76, 0.86),
                falloff: FogFalloff::Linear { start: 80.0, end: 420.0 },
                ..default()
            },
        ));
    }
}

fn reuse_hedge_materials(
    mut commands: Commands,
    level: Res<CurrentLevel>,
    library: Option<Res<ShowhomeMaterials>>,
    meshes: Query<(Entity, &GltfMeshName, &GltfMaterialName), (With<ShowhomeKitMesh>, Without<ReusedHedgeMaterial>)>,
) {
    if !is_showhome(&level) {
        return;
    }
    let Some(hedge) = library.and_then(|lib| lib.get(Look::Hedge)) else { return };
    for (entity, mesh, material) in &meshes {
        // The existing foliage plugin hides the plain hedge by this handle and keeps it visible on LOW.
        // Planter shrubs and backdrop trees have different ownership, so they remain ordinary kit materials.
        if ((mesh.0.starts_with("PROP_Hedge") || mesh.0.starts_with("PROP_Arbour"))
            && matches!(material.0.as_str(), "M_Hedge" | "M_Vine"))
            || (mesh.0.starts_with("FOL_") && material.0.starts_with("M_V3_FoliageProxy"))
            || (crate::showhome_v3::is_v3(&level.name)
                && matches!(material.0.as_str(), "M_V3_ExtensionHedge" | "M_V3_ExtensionTreeCanopy"))
        {
            // Reinsert the component so the foliage plugin's Added filter notices async scene arrivals.
            commands
                .entity(entity)
                .remove::<MeshMaterial3d<StandardMaterial>>()
                .insert((MeshMaterial3d(hedge.clone()), ReusedHedgeMaterial));
        }
    }
}

fn report_failed_scenes(level: Res<CurrentLevel>, server: Res<AssetServer>, mut assets: ResMut<ShowhomeKitAssets>) {
    if !is_showhome(&level) {
        return;
    }
    for scene in &mut assets.scenes {
        if !scene.failure_reported && server.load_state(&scene.handle).is_failed() {
            error!("Showhome {:?} art scene could not load: {}", scene.part, scene.path);
            scene.failure_reported = true;
        }
    }
}

#[derive(Resource, Default)]
struct KitMipState {
    /// Images that have their mips (or need none).
    done: HashSet<AssetId<Image>>,
    /// The last scan left nothing to do: scan again only when the kit's meshes, their materials or the ground
    /// materials change (scanning every kit material every frame cost about 0.06 ms a frame for nothing).
    settled: bool,
    ground_materials: usize,
    /// Mip chains being built off the main thread.
    jobs: Vec<MipJob>,
}

/// One image's mip chain in the making (on the async compute pool): the base level's bytes go in, the
/// layer-major chain and its level count come out.
struct MipJob {
    handle: Handle<Image>,
    bytes: usize,
    task: Task<Option<(Vec<u8>, u32)>>,
}

/// At most this many bytes of base levels are copied into mip jobs at once (one 39-layer ground array is
/// 156 MiB; its job holds that and the chain it builds).
const MIP_JOB_BYTES: usize = 200 << 20;
/// At most this many mip jobs start in one frame.
const MIP_JOBS_PER_FRAME: usize = 4;

/// Whether a mip job may start for an image of `bytes`: always when none runs, else within the byte budget.
fn mip_job_fits(running: &[usize], bytes: usize) -> bool {
    running.is_empty() || running.iter().sum::<usize>() + bytes <= MIP_JOB_BYTES
}

/// RGBA arrays are layer-major: all mips of layer 0, then all mips of layer 1, and so on.
pub(crate) fn rgba_layer_mips(
    base: Vec<u8>,
    width: usize,
    height: usize,
    layers: usize,
    srgb: bool,
) -> Option<(Vec<u8>, u32)> {
    let layer_bytes = width.checked_mul(height)?.checked_mul(4)?;
    if layer_bytes == 0 || layers == 0 || base.len() != layer_bytes.checked_mul(layers)? {
        return None;
    }
    let mut out = Vec::with_capacity(base.len() * 4 / 3 + 16 * layers);
    let mut levels = 1;
    for layer in base.chunks_exact(layer_bytes) {
        let (bytes, count) = mip_chain(layer.to_vec(), width, height, srgb);
        out.extend(bytes);
        levels = count;
    }
    Some((out, levels))
}

/// Builds the kit's and the ground arrays' missing mip chains (glTF-embedded PNGs and the packed arrays carry
/// none, and tiling textures shimmer without them) on the async compute pool, so the main thread (the host's
/// simulation on a listen server) never stalls: building them here took 0.45-0.83 s per ground array and 15-23
/// ms a frame for 7-8 s after a Showhome match started (map-kit review K2). A finished image then lives in the
/// render world only: its CPU copy (789 MiB for the kit, 624 MiB for the arrays) is dropped once uploaded
/// (map-kit review K3, K4).
#[allow(clippy::too_many_arguments)]
fn finish_kit_mips(
    level: Res<CurrentLevel>,
    mut state: ResMut<KitMipState>,
    server: Res<AssetServer>,
    mut images: ResMut<Assets<Image>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut ground: ResMut<Assets<crate::showhome_ground::ShowhomeGroundMaterial>>,
    used: Query<(&ShowhomeKitMesh, &MeshMaterial3d<StandardMaterial>)>,
    changed: Query<
        (),
        (With<ShowhomeKitMesh>, Or<(Added<ShowhomeKitMesh>, Changed<MeshMaterial3d<StandardMaterial>>)>),
    >,
) {
    if !is_showhome(&level) {
        return;
    }
    // Finished jobs: the chain goes into its image, which then lives in the render world only.
    let mut finished = Vec::new();
    state.jobs.retain_mut(|job| match check_ready(&mut job.task) {
        Some(out) => {
            finished.push((job.handle.clone(), out));
            false
        }
        None => true,
    });
    for (handle, out) in finished {
        state.done.insert(handle.id());
        let Some((data, levels)) = out else {
            warn!("Invalid kit RGBA mip input: {:?}", handle.id());
            continue;
        };
        let Some(mut image) = images.get_mut(&handle) else { continue };
        image.data = Some(data);
        image.data_order = TextureDataOrder::LayerMajor;
        image.texture_descriptor.mip_level_count = levels;
        image.sampler = ImageSampler::Descriptor(ImageSamplerDescriptor {
            address_mode_u: ImageAddressMode::Repeat,
            address_mode_v: ImageAddressMode::Repeat,
            anisotropy_clamp: 8,
            ..ImageSamplerDescriptor::linear()
        });
        image.asset_usage = RenderAssetUsages::RENDER_WORLD;
        refresh_materials(handle.id(), &mut materials, &mut ground);
        info!("Showhome image {:?} finished: {} mip levels", handle.id(), levels);
    }
    if state.jobs.is_empty() && state.settled && changed.is_empty() && ground.len() == state.ground_materials {
        return;
    }
    state.ground_materials = ground.len();
    state.settled = state.jobs.is_empty();
    let mut candidates = Vec::new();
    for (part, handle) in &used {
        let priority = match part.0 {
            ShowhomeKitPart::Houses => 1,
            ShowhomeKitPart::Props => 2,
            ShowhomeKitPart::Ground => 3,
            ShowhomeKitPart::Backdrop => 4,
        };
        let Some(material) = materials.get(&handle.0) else { continue };
        for image in [
            &material.base_color_texture,
            &material.normal_map_texture,
            &material.metallic_roughness_texture,
            &material.occlusion_texture,
            &material.emissive_texture,
        ]
        .into_iter()
        .flatten()
        {
            candidates.push((priority, image.clone()));
        }
    }
    for (_, material) in ground.iter() {
        for image in [&material.extension.albedo, &material.extension.normal, &material.extension.orm] {
            candidates.push((0, image.clone()));
        }
    }
    candidates.sort_by_key(|(priority, _)| *priority);
    let mut seen = HashSet::new();
    let mut started = 0;
    let KitMipState { done, jobs, settled, .. } = &mut *state;
    for (_, handle) in candidates {
        let id = handle.id();
        if done.contains(&id) || !seen.insert(id) || jobs.iter().any(|j| j.handle.id() == id) {
            continue;
        }
        let Some(image) = images.get(&handle) else {
            if handle.path().is_none() || server.is_loaded_with_dependencies(id) {
                done.insert(id);
            } else {
                *settled = false; // still loading
            }
            continue;
        };
        let format = image.texture_descriptor.format;
        let Some(base) = image.data.as_ref().filter(|_| {
            matches!(format, TextureFormat::Rgba8UnormSrgb | TextureFormat::Rgba8Unorm)
                && image.texture_descriptor.mip_level_count == 1
        }) else {
            done.insert(id);
            continue;
        };
        let running: Vec<usize> = jobs.iter().map(|j| j.bytes).collect();
        if started >= MIP_JOBS_PER_FRAME || !mip_job_fits(&running, base.len()) {
            *settled = false; // more next frame
            break;
        }
        // A copy, so the image stays as it is (and drawn) until its chain is ready.
        let (base, w, h) = (base.clone(), image.width() as usize, image.height() as usize);
        let (layers, srgb) =
            (image.texture_descriptor.array_layer_count() as usize, format == TextureFormat::Rgba8UnormSrgb);
        let bytes = base.len();
        let task = AsyncComputeTaskPool::get().spawn(async move { rgba_layer_mips(base, w, h, layers, srgb) });
        jobs.push(MipJob { handle, bytes, task });
        started += 1;
        *settled = false;
    }
}

/// Refresh the bind groups of the materials that may already reference an image's old single-level view.
fn refresh_materials(
    image: AssetId<Image>,
    materials: &mut Assets<StandardMaterial>,
    ground: &mut Assets<crate::showhome_ground::ShowhomeGroundMaterial>,
) {
    let changed: Vec<_> = materials
        .iter()
        .filter_map(|(id, material)| {
            [
                &material.base_color_texture,
                &material.normal_map_texture,
                &material.metallic_roughness_texture,
                &material.occlusion_texture,
                &material.emissive_texture,
            ]
            .into_iter()
            .flatten()
            .any(|h| h.id() == image)
            .then_some(id)
        })
        .collect();
    for id in changed {
        if let Some(material) = materials.get_mut(id) {
            let _ = material.into_inner();
        }
    }
    let changed: Vec<_> = ground
        .iter()
        .filter_map(|(id, material)| {
            [&material.extension.albedo, &material.extension.normal, &material.extension.orm]
                .into_iter()
                .any(|h| h.id() == image)
                .then_some(id)
        })
        .collect();
    for id in changed {
        if let Some(material) = ground.get_mut(id) {
            let _ = material.into_inner();
        }
    }
}

// ----------------------------------------------------------------------------------------- native kit depth
#[derive(Clone, Copy, Debug, Deserialize)]
struct HeightMetrics {
    repeat_m: f32,
    height_range_m: f32,
    #[serde(default)]
    metalness: f32,
}

#[derive(Deserialize)]
struct HeightManifest {
    materials: HashMap<String, HeightMetrics>,
}

#[derive(Clone, Debug)]
struct KitHeight {
    path: String,
    metrics: HeightMetrics,
    real_geometry: bool,
    geometry_scale: f32,
}

impl KitHeight {
    fn uv_depth(&self) -> f32 {
        parallax_scale(self.metrics.height_range_m * 100.0, self.metrics.repeat_m) * self.geometry_scale
    }
}

/// A kit height map: its PNG16 (kept in the main world only, read once on the CPU and dropped) until it has
/// become the depth image the materials sample (kept in the render world only).
struct PendingHeight {
    source: Option<Handle<Image>>,
    depth: Option<Handle<Image>>,
    failed: bool,
}

struct KitDepthTarget {
    material: Handle<StandardMaterial>,
    spec: KitHeight,
    shown: Option<DepthQuality>,
}

#[derive(Resource)]
struct KitDepthState {
    families: HashMap<String, HeightMetrics>,
    heights: HashMap<String, PendingHeight>,
    targets: HashMap<AssetId<StandardMaterial>, KitDepthTarget>,
    /// Materials that take no depth (glass, metal, untextured, no height map). That depends only on their glTF
    /// fields, which never change, so each is looked at once instead of re-parsed every frame.
    rejected: HashSet<AssetId<StandardMaterial>>,
}

impl Default for KitDepthState {
    fn default() -> Self {
        let manifest: HeightManifest =
            serde_json::from_str(include_str!("../../../assets/maps/showhome/textures/v2/manifest.json"))
                .expect("deployed Showhome v2 manifest is valid");
        Self {
            families: manifest.materials,
            heights: HashMap::new(),
            targets: HashMap::new(),
            rejected: HashSet::new(),
        }
    }
}

fn depth_allowed(name: &str, has_colour_map: bool, metallic: f32) -> bool {
    let name = name.to_ascii_lowercase();
    has_colour_map && metallic <= 0.1 && !name.contains("glass") && !name.contains("metal") && !name.contains("solar")
}

fn material_depth_allowed(name: &str, material: &StandardMaterial) -> bool {
    // For an ORM image the scalar is a multiplier, not the material's physical metalness.
    let metallic = if material.metallic_roughness_texture.is_some() { 0.0 } else { material.metallic };
    depth_allowed(name, material.base_color_texture.is_some(), metallic)
}

fn kit_height_spec(name: &str, extras: &str, families: &HashMap<String, HeightMetrics>) -> Option<KitHeight> {
    let extras: serde_json::Value = serde_json::from_str(extras).ok()?;
    let source = extras.get("height_source").or_else(|| extras.get("height_map"))?.as_str()?;
    let file = source.rsplit(['/', '\\']).next()?;
    let family = file.strip_suffix("_height.png")?;
    let mut metrics = *families.get(family)?;
    if let Some(repeat) = extras.get("repeat_m").and_then(|v| v.as_f64()) {
        metrics.repeat_m = repeat as f32;
    }
    if metrics.repeat_m <= 0.0 || metrics.height_range_m <= 0.0 || metrics.metalness > 0.1 {
        return None;
    }
    let real_geometry =
        matches!(name, "M_SH_FibreCementPaintedFace" | "M_SH_PrintedConcrete" | "M_SH_RoofShingle" | "M_SH_RidgeVerge");
    // Printed beads and roof butts already have geometric relief. Retain modest POM on their faces.
    // The neutral cladding face has only 0.35 mm paint relief; its 9 mm joints are separate geometry.
    let geometry_scale = if real_geometry && family != "fibercement_panel" { 0.35 } else { 1.0 };
    let path = if source.starts_with("maps/") || source.starts_with("props/") {
        source.into()
    } else {
        format!("maps/showhome/textures/v2/{file}")
    };
    Some(KitHeight { path, metrics, real_geometry, geometry_scale })
}

/// v2 white is HIGH; Bevy native POM expects white to be DEEP. Reuse the existing R16->F16 conversion.
fn height_to_depth_f16(bytes: &[u8]) -> Vec<u8> {
    let inverted: Vec<u8> =
        bytes.as_chunks::<2>().0.iter().flat_map(|b| (u16::MAX - u16::from_le_bytes(*b)).to_le_bytes()).collect();
    r16_to_f16(&inverted)
}

/// The depth map a kit material takes, `None` for one that never takes any.
fn kit_depth_target(
    name: &str,
    extras: &str,
    material: &StandardMaterial,
    families: &HashMap<String, HeightMetrics>,
) -> Option<KitHeight> {
    // A textured glTF ORM uses metallicFactor=1 even on a matte surface: its blue texels are zero.
    // Use the manifest's physical metalness in that case, and scalar metalness for untextured PBR.
    if !material_depth_allowed(name, material) {
        return None;
    }
    kit_height_spec(name, extras, families)
}

/// The PNG16 becomes a depth image: inverted, R16Float (filterable), repeating, and only in the render world.
fn depth_image(height: &Image) -> Option<Image> {
    let bytes = height.data.as_ref()?;
    let mut depth = height.clone();
    depth.data = Some(height_to_depth_f16(bytes));
    depth.texture_descriptor.format = TextureFormat::R16Float;
    depth.asset_usage = RenderAssetUsages::RENDER_WORLD;
    depth.sampler = ImageSampler::Descriptor(ImageSamplerDescriptor {
        address_mode_u: ImageAddressMode::Repeat,
        address_mode_v: ImageAddressMode::Repeat,
        ..ImageSamplerDescriptor::linear()
    });
    Some(depth)
}

fn apply_kit_depth(
    level: Res<CurrentLevel>,
    quality: Res<SurfaceDepthLevel>,
    data: Res<SurfaceDepthData>,
    mut state: ResMut<KitDepthState>,
    server: Res<AssetServer>,
    mut images: ResMut<Assets<Image>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    imported: Query<(&MeshMaterial3d<StandardMaterial>, &GltfMaterialName, &GltfMaterialExtras), With<ShowhomeKitMesh>>,
) {
    if !is_showhome(&level) {
        return;
    }
    for (handle, name, extras) in &imported {
        let id = handle.id();
        if state.targets.contains_key(&id) || state.rejected.contains(&id) {
            continue;
        }
        let Some(material) = materials.get(&handle.0) else { continue };
        match kit_depth_target(&name.0, &extras.value, material, &state.families) {
            Some(spec) => {
                state.targets.insert(id, KitDepthTarget { material: handle.0.clone(), spec, shown: None });
            }
            None => {
                state.rejected.insert(id);
            }
        }
    }
    let q = data.quality.of(quality.0);
    if q.on() {
        let KitDepthState { targets, heights, .. } = &mut *state;
        for target in targets.values() {
            heights.entry(target.spec.path.clone()).or_insert_with(|| PendingHeight {
                // Read once on the CPU (below) and never drawn: main world only.
                source: Some(
                    server
                        .load_builder()
                        .with_settings(|s: &mut ImageLoaderSettings| {
                            s.is_srgb = false;
                            s.asset_usage = RenderAssetUsages::MAIN_WORLD;
                        })
                        .load(target.spec.path.clone()),
                ),
                depth: None,
                failed: false,
            });
        }
    }
    // At most one height becomes a depth image per frame (several arriving together would hitch).
    for (path, pending) in &mut state.heights {
        let Some(source) = pending.source.as_ref() else { continue };
        if server.load_state(source).is_failed() {
            warn!("Showhome height could not load; retaining geometry and normals: {path}");
            (pending.failed, pending.source) = (true, None);
            continue;
        }
        let Some(height) = images.get(source) else { continue };
        if height.texture_descriptor.format != TextureFormat::R16Uint {
            warn!("Showhome height must be PNG16 grayscale; found {:?}: {path}", height.texture_descriptor.format);
            (pending.failed, pending.source) = (true, None);
            continue;
        }
        let Some(depth) = depth_image(height) else { continue };
        // The source is not needed any more (this was its last handle).
        if let Some(source) = pending.source.take() {
            images.remove(&source);
        }
        pending.depth = Some(images.add(depth));
        break;
    }
    let KitDepthState { targets, heights, .. } = &mut *state;
    for target in targets.values_mut() {
        let depth = heights.get(&target.spec.path).and_then(|h| h.depth.as_ref());
        if target.shown == Some(q) || (q.on() && depth.is_none()) {
            continue;
        }
        let Some(mut material) = materials.get_mut(&target.material) else { continue };
        material.depth_map = q.on().then(|| depth.cloned()).flatten();
        material.parallax_depth_scale = if q.on() { target.spec.uv_depth() } else { 0.0 };
        material.max_parallax_layer_count = q.layers.max(1.0);
        material.parallax_mapping_method = q.method();
        target.shown = Some(q);
        info!(
            "Showhome kit depth {:?}: {} m / {} m, geometric detail={}, quality {} layers",
            target.material.id(),
            target.spec.metrics.height_range_m,
            target.spec.metrics.repeat_m,
            target.spec.real_geometry,
            q.layers
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn v3_normal_strength_preserves_source_and_reuses_private_images() {
        let mut app = App::new();
        app.init_resource::<Assets<Image>>();
        app.init_resource::<Assets<StandardMaterial>>();
        app.init_resource::<NormalStrengthState>();
        app.add_systems(Update, apply_normal_strengths);
        let source = app.world_mut().resource_mut::<Assets<Image>>().add(Image::new_fill(
            bevy::render::render_resource::Extent3d { width: 1, height: 1, depth_or_array_layers: 1 },
            bevy::render::render_resource::TextureDimension::D2,
            &[204, 128, 230, 77],
            TextureFormat::Rgba8Unorm,
            RenderAssetUsages::MAIN_WORLD | RenderAssetUsages::RENDER_WORLD,
        ));
        let add = |app: &mut App| {
            app.world_mut()
                .resource_mut::<Assets<StandardMaterial>>()
                .add(StandardMaterial { normal_map_texture: Some(source.clone()), ..default() })
        };
        let legacy = add(&mut app);
        let first = add(&mut app);
        let second = add(&mut app);
        app.world_mut().spawn((ImportedNormalStrength(0.25), MeshMaterial3d(first.clone())));
        app.world_mut().spawn((ImportedNormalStrength(0.25), MeshMaterial3d(second.clone())));
        app.update();
        let materials = app.world().resource::<Assets<StandardMaterial>>();
        assert_eq!(materials.get(&legacy).unwrap().normal_map_texture.as_ref().unwrap(), &source);
        let scaled = materials.get(&first).unwrap().normal_map_texture.as_ref().unwrap();
        assert_ne!(scaled, &source);
        assert_eq!(materials.get(&second).unwrap().normal_map_texture.as_ref().unwrap(), scaled);
        let images = app.world().resource::<Assets<Image>>();
        assert_eq!(images.get(&source).unwrap().data.as_deref(), Some(&[204, 128, 230, 77][..]));
        let pixel = images.get(scaled).unwrap().data.as_ref().unwrap();
        assert_eq!(pixel[3], 77);
        assert!(pixel[0] < 160 && pixel[2] > 245, "XY scale reduces tangent-space slope");
        app.update();
        assert_eq!(app.world().resource::<NormalStrengthState>().images.len(), 1, "not repeatedly rescaled");
    }

    #[test]
    fn preview_prop_render_transform_matches_exact_collision_adapter() {
        use vetf_sim::build_mode::collision::{design_basis, design_to_bevy_matrix, instance_design_matrix};
        let preview = vetf_sim::maps::showhome_v3::load(crate::config::assets_root()).unwrap();
        for row in &preview.placements.instances {
            let render = preview_prop_transform(row, preview.origin).to_matrix();
            let collision =
                design_to_bevy_matrix(preview.origin) * instance_design_matrix(row) * design_basis().inverse();
            for point in [Vec3::ZERO, Vec3::ONE, Vec3::new(-0.37, 2.5, 0.83)] {
                let actual = render.transform_point3(point);
                let expected =
                    collision.transform_point3(bevy::math::DVec3::new(point.x as f64, point.y as f64, point.z as f64));
                assert!(
                    actual.abs_diff_eq(Vec3::new(expected.x as f32, expected.y as f32, expected.z as f32), 0.0001),
                    "{}",
                    row.id
                );
            }
        }
    }

    #[test]
    fn v3_material_height_paths_retain_shared_staged_family_and_repeat() {
        let mut families = HashMap::new();
        families
            .insert("wood_boards_stained".into(), HeightMetrics { repeat_m: 2., height_range_m: 0.008, metalness: 0. });
        let spec = kit_height_spec(
            "M_V3_Posts",
            r#"{"height_source":"maps/showhome_v3/height/wood_boards_stained_height.png","repeat_m":1.5}"#,
            &families,
        )
        .unwrap();
        assert_eq!(spec.path, "maps/showhome_v3/height/wood_boards_stained_height.png");
        assert_eq!(spec.metrics.repeat_m, 1.5);
    }

    /// Flat ground stops casting, anything with height keeps casting, through the mesh's transform.
    #[test]
    fn only_flat_ground_stops_casting() {
        let lawn = Aabb::from_min_max(Vec3::new(-40.0, 0.0, -30.0), Vec3::new(40.0, 0.006, 30.0));
        let kerb = Aabb::from_min_max(Vec3::new(0.0, 0.0, 0.0), Vec3::new(0.2, 0.11, 30.0));
        let at = GlobalTransform::IDENTITY;
        assert!(world_height(&lawn, &at) <= FLAT_GROUND_M);
        assert!(world_height(&kerb, &at) > FLAT_GROUND_M);
        // A flat card stood on its edge is tall: the transform counts.
        let stood = GlobalTransform::from(Transform::from_rotation(Quat::from_rotation_x(std::f32::consts::FRAC_PI_2)));
        assert!((world_height(&lawn, &stood) - 60.0).abs() < 1e-3);
    }

    #[test]
    fn array_mips_keep_layers_separate_and_layer_major() {
        let mut base = [255, 0, 0, 255].repeat(4);
        base.extend([0, 0, 255, 255].repeat(4));
        let (mips, levels) = rgba_layer_mips(base, 2, 2, 2, false).unwrap();
        assert_eq!(levels, 2);
        assert_eq!(&mips[..20], [255, 0, 0, 255].repeat(5));
        assert_eq!(&mips[20..], [0, 0, 255, 255].repeat(5));
    }

    #[test]
    fn png16_high_faces_become_zero_depth_and_grooves_become_deep() {
        let depths = height_to_depth_f16(&[255, 255, 0, 0, 255, 127]);
        assert_eq!(depths, [0, 0, 0, 60, 0, 56]); // F16: 0, 1, 0.5; no eight-bit quantization.
        // The depth image lives in the render world only (the PNG16 was the main world's, read once).
        let height = Image::new(
            bevy::render::render_resource::Extent3d { width: 3, height: 1, depth_or_array_layers: 1 },
            bevy::render::render_resource::TextureDimension::D2,
            vec![255, 255, 0, 0, 255, 127],
            TextureFormat::R16Uint,
            RenderAssetUsages::MAIN_WORLD,
        );
        let depth = depth_image(&height).unwrap();
        assert_eq!(depth.texture_descriptor.format, TextureFormat::R16Float);
        assert_eq!(depth.asset_usage, RenderAssetUsages::RENDER_WORLD);
        assert_eq!(depth.data.as_deref(), Some(&[0u8, 0, 0, 60, 0, 56][..]));
    }

    /// The cube face and texel (s right, t down) a direction samples, by the cube map rules wgpu follows.
    fn cube_texel(d: Vec3, w: usize) -> (usize, usize, usize) {
        let a = d.abs();
        let (face, sc, tc, ma) = if a.x >= a.y && a.x >= a.z {
            if d.x > 0.0 { (0, -d.z, -d.y, a.x) } else { (1, d.z, -d.y, a.x) }
        } else if a.y >= a.z {
            if d.y > 0.0 { (2, d.x, d.z, a.y) } else { (3, d.x, -d.z, a.y) }
        } else if d.z > 0.0 {
            (4, d.x, -d.y, a.z)
        } else {
            (5, -d.x, -d.y, a.z)
        };
        let texel = |c: f32| (((c / ma + 1.0) * 0.5 * w as f32) as usize).min(w - 1);
        (face, texel(sc), texel(tc))
    }

    /// Map-kit review K6: after the mirror, Bevy's skybox (which samples the direction times (1, 1, -1)) shows at
    /// every direction what the right-handed strip painted for it.
    #[test]
    fn the_mirrored_sky_shows_each_direction_its_own_texel() {
        let w = 8;
        // every texel holds its own (face, s, t), one byte each, plus a fourth
        let mut data = Vec::new();
        for face in 0..6u8 {
            for t in 0..w as u8 {
                for s in 0..w as u8 {
                    data.extend([face, s, t, 255]);
                }
            }
        }
        let painted = data.clone();
        mirror_cube_z(&mut data, w);
        let at = |d: &[u8], (f, s, t): (usize, usize, usize)| {
            let i = ((f * w + t) * w + s) * 4;
            [d[i], d[i + 1], d[i + 2]]
        };
        let mut rng = vetf_sim::rng::SplitMix::from_parts(&[3]);
        for _ in 0..500 {
            let d = Vec3::new(rng.next_signed(), rng.next_signed(), rng.next_signed()).normalize();
            let bevy = cube_texel(d * Vec3::new(1.0, 1.0, -1.0), w);
            assert_eq!(at(&data, bevy), at(&painted, cube_texel(d, w)), "direction {d}");
        }
    }

    /// The mip jobs keep their copies within a budget: one big array at a time, small images beside it.
    #[test]
    fn mip_jobs_stay_within_their_byte_budget() {
        let array = 156 << 20;
        assert!(mip_job_fits(&[], array), "the first job always starts");
        assert!(!mip_job_fits(&[array], array), "a second array waits");
        assert!(mip_job_fits(&[array], 4 << 20), "a 1024 px image fits beside it");
        assert!(mip_job_fits(&[], MIP_JOB_BYTES * 2), "an oversized image still gets its turn alone");
    }

    /// Materials that never take depth are remembered as such: glass, metal, untextured, no height map.
    #[test]
    fn materials_without_depth_are_rejected_once() {
        let mut families = HashMap::new();
        families
            .insert("concrete_smooth".into(), HeightMetrics { repeat_m: 2.0, height_range_m: 0.004, metalness: 0.0 });
        let textured = StandardMaterial { base_color_texture: Some(Handle::default()), ..default() };
        let extras = r#"{"height_map":"assets/maps/showhome/textures/v2/concrete_smooth_height.png"}"#;
        assert!(kit_depth_target("M_SH_Concrete", extras, &textured, &families).is_some());
        assert!(kit_depth_target("M_SH_GlassFrost", extras, &textured, &families).is_none());
        assert!(kit_depth_target("M_SH_Concrete", "{}", &textured, &families).is_none(), "no height map");
        assert!(kit_depth_target("M_SH_Concrete", extras, &StandardMaterial::default(), &families).is_none());
    }

    #[test]
    fn cladding_face_height_is_not_the_nine_millimetre_geometry_joint() {
        let mut families = HashMap::new();
        families.insert(
            "fibercement_panel".into(),
            HeightMetrics { repeat_m: 2.4, height_range_m: 0.00035, metalness: 0.0 },
        );
        let spec = kit_height_spec(
            "M_SH_FibreCementPaintedFace",
            r#"{"height_map":"assets/maps/showhome/textures/v2/fibercement_panel_height.png"}"#,
            &families,
        )
        .unwrap();
        assert!(spec.real_geometry);
        assert_eq!(spec.path, "maps/showhome/textures/v2/fibercement_panel_height.png");
        assert!((spec.uv_depth() - 0.00035 / 2.4).abs() < 1e-7);
    }

    #[test]
    fn physical_roof_depth_is_modest_beside_real_course_geometry() {
        let mut families = HashMap::new();
        families
            .insert("roof_shingle_dark".into(), HeightMetrics { repeat_m: 2.0, height_range_m: 0.010, metalness: 0.0 });
        let spec =
            kit_height_spec("M_SH_RoofShingle", r#"{"height_map":"roof_shingle_dark_height.png"}"#, &families).unwrap();
        assert!(spec.real_geometry);
        assert!((spec.uv_depth() - 0.0035 / 2.0).abs() < 1e-7);
    }

    #[test]
    fn glass_metal_solar_and_untextured_materials_never_receive_pom() {
        assert!(!depth_allowed("M_SH_GlassFrost", true, 0.0));
        assert!(!depth_allowed("M_SH_Metal", true, 0.8));
        assert!(!depth_allowed("M_SH_SolarPanel", true, 0.0));
        assert!(!depth_allowed("M_SH_Fabric", false, 0.0));
        assert!(depth_allowed("M_SH_PrintedConcrete", true, 0.0));
    }

    #[test]
    fn gltf_orm_metallic_factor_one_does_not_reject_matte_roofs() {
        let mut material = StandardMaterial {
            base_color_texture: Some(Handle::default()),
            metallic_roughness_texture: Some(Handle::default()),
            metallic: 1.0,
            ..default()
        };
        assert!(material_depth_allowed("M_SH_RoofShingle", &material));
        material.metallic_roughness_texture = None;
        assert!(!material_depth_allowed("M_SH_RoofShingle", &material));
        material.metallic = 0.0;
        material.base_color_texture = None;
        assert!(!material_depth_allowed("M_SH_Fabric", &material));
    }
}
