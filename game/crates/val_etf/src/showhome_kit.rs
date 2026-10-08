//! Showhome art-kit scenes, in their exported design frame, with the painted cube sky.
//!
//! Bevy 0.19 calls glTF scene roots `WorldAssetRoot` (formerly `SceneRoot`). The four exports already use
//! Bevy's `(design.x, design.z, -design.y)` axes, so every scene is loaded at identity. Collision remains
//! the simulation layout. Material names/extras are retained for the ground and surface-depth systems.

use crate::AppState;
use crate::config::CurrentLevel;
use crate::map_materials::{
    DepthQuality, ShowhomeMaterials, SurfaceDepthData, SurfaceDepthLevel, mip_chain, parallax_scale, r16_to_f16,
};
use crate::render::ViewCamera;
use bevy::asset::AssetId;
use bevy::camera::primitives::Aabb;
use bevy::gltf::{GltfMaterialExtras, GltfMaterialName, GltfMeshName};
use bevy::image::{ImageAddressMode, ImageLoaderSettings, ImageSampler, ImageSamplerDescriptor};
use bevy::light::{NotShadowCaster, Skybox};
use bevy::prelude::*;
use bevy::render::render_resource::{TextureDataOrder, TextureFormat, TextureViewDescriptor, TextureViewDimension};
use bevy::world_serialization::WorldInstanceReady;
use serde::Deserialize;
use std::collections::{HashMap, HashSet};
use vetf_sim::movement::collision::Look;

pub struct ShowhomeKitPlugin;

impl Plugin for ShowhomeKitPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<ShowhomeKitAssets>()
            .init_resource::<KitDepthState>()
            .init_resource::<KitMipState>()
            .add_systems(OnEnter(AppState::InGame), spawn_kit)
            .add_systems(
                Update,
                (
                    prepare_sky,
                    attach_sky,
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

struct KitScene {
    path: &'static str,
    part: ShowhomeKitPart,
    handle: Handle<WorldAsset>,
    failure_reported: bool,
}

#[derive(Resource, Default)]
struct ShowhomeKitAssets {
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
/// Physical brightness, following Bevy's PNG cube-sky example, with the look-dev's 0.65 sky strength.
const SKY_BRIGHTNESS: f32 = 650.0;

pub fn is_showhome(level: &CurrentLevel) -> bool {
    level.name.eq_ignore_ascii_case("showhome")
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
) {
    if !is_showhome(&level) {
        return;
    }
    if assets.scenes.is_empty() {
        assets.scenes = SCENES
            .into_iter()
            .map(|(path, part)| KitScene {
                path,
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

fn mark_scene_meshes(
    ready: On<WorldInstanceReady>,
    mut commands: Commands,
    roots: Query<&ShowhomeKitPart>,
    tree: Query<&Children>,
    meshes: Query<(), With<Mesh3d>>,
    names: Query<(&Name, Option<&GltfMeshName>)>,
) {
    let Ok(&part) = roots.get(ready.entity) else { return };
    let mut count = 0;
    for entity in tree.iter_descendants(ready.entity) {
        if !meshes.contains(entity) {
            continue;
        }
        count += 1;
        commands.entity(entity).insert(ShowhomeKitMesh(part));
        if part == ShowhomeKitPart::Backdrop
            && names.get(entity).is_ok_and(|(name, mesh)| {
                name.as_str().starts_with("SHB_Far") || mesh.is_some_and(|n| n.0.starts_with("SHB_Far"))
            })
        {
            commands.entity(entity).insert(NotShadowCaster);
        }
    }
    info!("Showhome {part:?} scene ready: {count} meshes at identity");
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
    // Face order in the delivered strip is +X,-X,+Y,-Y,+Z,-Z, already in glTF / Bevy axes.
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
    }
    image.texture_view_descriptor =
        Some(TextureViewDescriptor { dimension: Some(TextureViewDimension::Cube), ..default() });
    assets.sky_prepared = true;
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
        if (mesh.0.starts_with("PROP_Hedge") || mesh.0.starts_with("PROP_Arbour"))
            && matches!(material.0.as_str(), "M_Hedge" | "M_Vine")
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
struct KitMipState(HashSet<AssetId<Image>>);

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

fn finish_kit_mips(
    level: Res<CurrentLevel>,
    mut state: ResMut<KitMipState>,
    server: Res<AssetServer>,
    mut images: ResMut<Assets<Image>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut ground: ResMut<Assets<crate::showhome_ground::ShowhomeGroundMaterial>>,
    used: Query<(&ShowhomeKitMesh, &MeshMaterial3d<StandardMaterial>)>,
) {
    if !is_showhome(&level) {
        return;
    }
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
    for (_, handle) in candidates {
        if state.0.contains(&handle.id()) || !seen.insert(handle.id()) {
            continue;
        }
        let Some(mut image) = images.get_mut(&handle) else {
            if handle.path().is_none() || server.is_loaded_with_dependencies(handle.id()) {
                state.0.insert(handle.id());
            }
            continue;
        };
        let format = image.texture_descriptor.format;
        if !matches!(format, TextureFormat::Rgba8UnormSrgb | TextureFormat::Rgba8Unorm) {
            state.0.insert(handle.id());
            continue;
        }
        if image.texture_descriptor.mip_level_count > 1 {
            state.0.insert(handle.id());
            continue;
        }
        let Some(base) = image.data.as_ref() else {
            state.0.insert(handle.id());
            continue;
        };
        let Some((data, levels)) = rgba_layer_mips(
            base.clone(),
            image.width() as usize,
            image.height() as usize,
            image.texture_descriptor.array_layer_count() as usize,
            format == TextureFormat::Rgba8UnormSrgb,
        ) else {
            warn!("Invalid kit RGBA mip input: {:?}", handle.id());
            state.0.insert(handle.id());
            continue;
        };
        image.data = Some(data);
        image.data_order = TextureDataOrder::LayerMajor;
        image.texture_descriptor.mip_level_count = levels;
        image.sampler = ImageSampler::Descriptor(ImageSamplerDescriptor {
            address_mode_u: ImageAddressMode::Repeat,
            address_mode_v: ImageAddressMode::Repeat,
            anisotropy_clamp: 8,
            ..ImageSamplerDescriptor::linear()
        });
        state.0.insert(handle.id());
        // Refresh material bind groups that may already reference the old single-level texture view.
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
                .any(|image| image.id() == handle.id())
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
                    .any(|image| image.id() == handle.id())
                    .then_some(id)
            })
            .collect();
        for id in changed {
            if let Some(material) = ground.get_mut(id) {
                let _ = material.into_inner();
            }
        }
        info!("Showhome image {:?} finished: {} mip levels", handle.id(), levels);
        break; // One image per frame keeps asynchronous kit loading responsive.
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

struct PendingHeight {
    source: Handle<Image>,
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
    settings: SurfaceDepthData,
    families: HashMap<String, HeightMetrics>,
    heights: HashMap<String, PendingHeight>,
    targets: HashMap<AssetId<StandardMaterial>, KitDepthTarget>,
}

impl Default for KitDepthState {
    fn default() -> Self {
        let manifest: HeightManifest =
            serde_json::from_str(include_str!("../../../assets/maps/showhome/textures/v2/manifest.json"))
                .expect("deployed Showhome v2 manifest is valid");
        Self {
            settings: SurfaceDepthData::load(),
            families: manifest.materials,
            heights: HashMap::new(),
            targets: HashMap::new(),
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
    let file = extras.get("height_map")?.as_str()?.rsplit(['/', '\\']).next()?;
    let family = file.strip_suffix("_height.png")?;
    let metrics = *families.get(family)?;
    if metrics.repeat_m <= 0.0 || metrics.height_range_m <= 0.0 || metrics.metalness > 0.1 {
        return None;
    }
    let real_geometry =
        matches!(name, "M_SH_FibreCementPaintedFace" | "M_SH_PrintedConcrete" | "M_SH_RoofShingle" | "M_SH_RidgeVerge");
    // Printed beads and roof butts already have geometric relief. Retain modest POM on their faces.
    // The neutral cladding face has only 0.35 mm paint relief; its 9 mm joints are separate geometry.
    let geometry_scale = if real_geometry && family != "fibercement_panel" { 0.35 } else { 1.0 };
    Some(KitHeight { path: format!("maps/showhome/textures/v2/{file}"), metrics, real_geometry, geometry_scale })
}

/// v2 white is HIGH; Bevy native POM expects white to be DEEP. Reuse the existing R16->F16 conversion.
fn height_to_depth_f16(bytes: &[u8]) -> Vec<u8> {
    let inverted: Vec<u8> =
        bytes.as_chunks::<2>().0.iter().flat_map(|b| (u16::MAX - u16::from_le_bytes(*b)).to_le_bytes()).collect();
    r16_to_f16(&inverted)
}

fn apply_kit_depth(
    level: Res<CurrentLevel>,
    quality: Res<SurfaceDepthLevel>,
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
        if state.targets.contains_key(&handle.id()) {
            continue;
        }
        let Some(material) = materials.get(&handle.0) else { continue };
        // A textured glTF ORM uses metallicFactor=1 even on a matte surface: its blue texels are zero.
        // Use the manifest's physical metalness in that case, and scalar metalness for untextured PBR.
        if !material_depth_allowed(&name.0, material) {
            continue;
        }
        let Some(spec) = kit_height_spec(&name.0, &extras.value, &state.families) else { continue };
        state.targets.insert(handle.id(), KitDepthTarget { material: handle.0.clone(), spec, shown: None });
    }
    let q = state.settings.quality.of(quality.0);
    if q.on() {
        let paths: Vec<String> = state.targets.values().map(|t| t.spec.path.clone()).collect();
        for path in paths {
            state.heights.entry(path.clone()).or_insert_with(|| PendingHeight {
                source: server.load_builder().with_settings(|s: &mut ImageLoaderSettings| s.is_srgb = false).load(path),
                depth: None,
                failed: false,
            });
        }
    }
    for (path, pending) in &mut state.heights {
        if pending.depth.is_some() || pending.failed {
            continue;
        }
        if server.load_state(&pending.source).is_failed() {
            warn!("Showhome height could not load; retaining geometry and normals: {path}");
            pending.failed = true;
            continue;
        }
        let Some(mut image) = images.get(&pending.source).cloned() else { continue };
        if image.texture_descriptor.format != TextureFormat::R16Uint {
            warn!("Showhome height must be PNG16 grayscale; found {:?}: {path}", image.texture_descriptor.format);
            pending.failed = true;
            continue;
        }
        let Some(bytes) = image.data.as_ref() else { continue };
        image.data = Some(height_to_depth_f16(bytes));
        image.texture_descriptor.format = TextureFormat::R16Float;
        image.sampler = ImageSampler::Descriptor(ImageSamplerDescriptor {
            address_mode_u: ImageAddressMode::Repeat,
            address_mode_v: ImageAddressMode::Repeat,
            ..ImageSamplerDescriptor::linear()
        });
        pending.depth = Some(images.add(image));
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
