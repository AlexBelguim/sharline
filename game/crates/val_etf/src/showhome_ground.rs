//! Painted Showhome ground: imported COLOR_0 is four independent blend masks.
//! The four arrays retain sRGB albedo, linear normal/ORM and exact PNG16 heights.
//! Only named ground materials are replaced; props keep their ordinary vertex colour.
//! The base layer's relief follows the parallax quality preset (`surface_depth.ron`): off on LOW, at most the
//! preset's layers elsewhere, and only as many steps as it moves pixels on screen (see the shader).

use crate::map_materials::{DepthQuality, GroundRelief, SurfaceDepthData, SurfaceDepthLevel};
use bevy::asset::{AssetId, RenderAssetUsages};
use bevy::gltf::{GltfMaterialExtras, GltfMaterialName};
use bevy::image::{ImageAddressMode, ImageArrayLayout, ImageLoaderSettings, ImageSampler, ImageSamplerDescriptor};
use bevy::pbr::{ExtendedMaterial, MaterialExtension};
use bevy::prelude::*;
use bevy::render::render_resource::{AsBindGroup, ShaderType, TextureFormat};
use bevy::shader::ShaderRef;
use serde::Deserialize;
use std::collections::HashMap;
use std::sync::OnceLock;

pub type ShowhomeGroundMaterial = ExtendedMaterial<StandardMaterial, GroundExtension>;

pub struct ShowhomeGroundPlugin;

impl Plugin for ShowhomeGroundPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins(MaterialPlugin::<ShowhomeGroundMaterial>::default())
            .init_resource::<GroundMaterialCache>()
            .add_systems(Startup, load_ground_arrays)
            .add_systems(
                Update,
                (apply_ground_depth, install_ground_materials).chain().after(crate::video::apply_surface_depth),
            );
    }
}

#[derive(Clone, Copy, Debug, Default, Reflect, ShaderType)]
pub struct GroundParams {
    /// Base, R, G, B array layer indices.
    pub indices: UVec4,
    /// A, macro, unused, unused array layer indices.
    pub extra_indices: UVec4,
    /// Physical repeats for base, R, G, B.
    pub repeats: Vec4,
    /// Height ranges in metres for base, R, G, B.
    pub heights: Vec4,
    /// A repeat, A height range, macro repeat, macro strength.
    pub extra: Vec4,
    pub tint: Vec4,
    /// Relief on (0 = off), most relief steps (the preset's layers), base normal repeat correction, unused.
    pub parallax: Vec4,
    /// Relief steps per pixel of its whole shift on screen, no relief below this many pixels, unused, unused.
    pub relief: Vec4,
}

#[derive(Asset, AsBindGroup, Reflect, Clone, Debug)]
pub struct GroundExtension {
    #[uniform(100)]
    pub params: GroundParams,
    #[texture(101, dimension = "2d_array")]
    #[sampler(102)]
    pub albedo: Handle<Image>,
    #[texture(103, dimension = "2d_array")]
    pub normal: Handle<Image>,
    #[texture(104, dimension = "2d_array")]
    pub orm: Handle<Image>,
    // Native R16Uint avoids optional float16-filter support and preserves all PNG16 values.
    #[texture(105, dimension = "2d_array", sample_type = "u_int")]
    pub height: Handle<Image>,
}

impl MaterialExtension for GroundExtension {
    fn fragment_shader() -> ShaderRef {
        "shaders/showhome_ground.wgsl".into()
    }

    fn deferred_fragment_shader() -> ShaderRef {
        Self::fragment_shader()
    }

    fn alpha_mode() -> Option<AlphaMode> {
        Some(AlphaMode::Opaque)
    }
}

#[derive(Deserialize)]
struct ArrayManifest {
    colour_rows: u32,
    height_rows: u32,
    macro_layer: u32,
    materials: HashMap<String, ArrayLayer>,
}

#[derive(Deserialize)]
struct ArrayLayer {
    index: u32,
    repeat_m: f32,
    height_range_m: f32,
}

fn array_manifest() -> &'static ArrayManifest {
    static MANIFEST: OnceLock<ArrayManifest> = OnceLock::new();
    MANIFEST.get_or_init(|| {
        serde_json::from_str(include_str!("../../../assets/maps/showhome/ground_arrays/arrays.json"))
            .expect("Showhome ground array manifest must match pack_ground_arrays.py")
    })
}

#[derive(Resource)]
struct GroundArrays {
    albedo: Handle<Image>,
    normal: Handle<Image>,
    orm: Handle<Image>,
    height: Handle<Image>,
    ready: bool,
    failed: bool,
}

#[derive(Resource, Default)]
struct GroundMaterialCache(HashMap<AssetId<StandardMaterial>, Handle<ShowhomeGroundMaterial>>);

#[derive(Component)]
pub struct GroundBlendInstalled;

fn load_ground_arrays(mut commands: Commands, server: Res<AssetServer>) {
    let info = array_manifest();
    let load = |name: &str, srgb: bool, rows: u32, height: bool| {
        server
            .load_builder()
            .with_settings(move |s: &mut ImageLoaderSettings| {
                s.is_srgb = srgb;
                s.array_layout = Some(ImageArrayLayout::RowCount { rows });
                s.asset_usage = if height {
                    RenderAssetUsages::RENDER_WORLD
                } else {
                    RenderAssetUsages::MAIN_WORLD | RenderAssetUsages::RENDER_WORLD
                };
                s.sampler = ImageSampler::Descriptor(ImageSamplerDescriptor {
                    address_mode_u: ImageAddressMode::Repeat,
                    address_mode_v: ImageAddressMode::Repeat,
                    ..ImageSamplerDescriptor::linear()
                });
                if height {
                    s.texture_format = Some(TextureFormat::R16Uint);
                }
            })
            .load(format!("maps/showhome/ground_arrays/{name}_array.png"))
    };
    commands.insert_resource(GroundArrays {
        albedo: load("albedo", true, info.colour_rows, false),
        normal: load("normal", false, info.colour_rows, false),
        orm: load("orm", false, info.colour_rows, false),
        height: load("height", false, info.height_rows, true),
        ready: false,
        failed: false,
    });
}

/// Contract fallback for older GLBs. Fresh kit exports include this in material extras.
/// Whether the named kit material is drawn by the ground blend (its vertex colours are layer masks).
pub(crate) fn is_ground_blend(name: &str) -> bool {
    fallback(name).is_some()
}

fn fallback(name: &str) -> Option<(&'static str, f32, &'static str)> {
    let canonical = name
        .rsplit_once('.')
        .filter(|(_, suffix)| suffix.chars().all(|c| c.is_ascii_digit()))
        .map_or(name, |(base, _)| base);
    Some(match canonical {
        "M_GND_Asphalt" => ("asphalt", 4., "hard"),
        "M_GND_AsphaltOld" => ("asphalt_cracked", 4., "hard"),
        "M_GND_Paving" | "M_GND_PavingSage" | "M_GND_PavingClay" => ("paving_slabs", 2.4, "hard"),
        "M_GND_Grass" => ("grass_lawn", 2., "lawn"),
        "M_GND_GrassFar" => ("grass_lawn", 5., "lawn"),
        "M_GND_Soil" => ("garden_soil", 1., "earth"),
        "M_GND_SoilFar" => ("garden_soil", 3., "earth"),
        "M_GND_Gravel" => ("gravel", 1., "earth"),
        "M_GND_Sand" => ("construction_sand", 6., "earth"),
        "M_GND_Concrete" => ("concrete_smooth", 2., "hard"),
        "M_GND_Kerb" => ("kerb_concrete", 2., "hard"),
        "M_GND_Edging" => ("edging_strip", 2., "hard"),
        "M_GND_SteelEdging" => ("metal_scaffold_tube", 1., "hard"),
        "M_GND_Mulch" => ("bark_mulch", 1., "earth"),
        "M_GND_PaintSage" | "M_GND_PaintClay" => ("fibercement_panel", 2.4, "hard"),
        _ => return None,
    })
}

#[derive(Deserialize)]
struct GroundContract {
    base_texture: String,
    base_repeat_m: f32,
    surface_class: String,
}

fn contract(extras: Option<&GltfMaterialExtras>) -> Option<GroundContract> {
    let root: serde_json::Value = serde_json::from_str(&extras?.value).ok()?;
    let value = root.get("showhome_ground_blend")?;
    if let Some(text) = value.as_str() {
        serde_json::from_str(text).ok()
    } else {
        serde_json::from_value(value.clone()).ok()
    }
}

/// The relief's switch and step count for a preset (LOW: off), and its screen-space steps (`surface_depth.ron`).
fn depth_params(q: DepthQuality, relief: GroundRelief) -> (f32, f32, Vec4) {
    let on = if q.on() { 1.0 } else { 0.0 };
    (on, q.layers.max(1.0), Vec4::new(relief.steps_per_px.max(0.0), relief.min_px.max(0.0), 0.0, 0.0))
}

fn params(texture: &str, repeat: f32, class: &str, tint: Color, depth: (f32, f32, Vec4)) -> Option<GroundParams> {
    let info = array_manifest();
    let moss = if class == "earth" { "worksite_mud_tracks" } else { "grass_verge_weeds" };
    let spill = if class == "hard" { "construction_sand" } else { "worksite_mud_tracks" };
    let names = [texture, "worn_dirt", "gravel", moss, spill];
    let layers: Vec<_> = names.iter().map(|n| info.materials.get(*n)).collect::<Option<_>>()?;
    let tint = tint.to_linear();
    Some(GroundParams {
        indices: UVec4::new(layers[0].index, layers[1].index, layers[2].index, layers[3].index),
        extra_indices: UVec4::new(layers[4].index, info.macro_layer, 0, 0),
        repeats: Vec4::new(repeat, layers[1].repeat_m, layers[2].repeat_m, layers[3].repeat_m),
        heights: Vec4::new(
            layers[0].height_range_m,
            layers[1].height_range_m,
            layers[2].height_range_m,
            layers[3].height_range_m,
        ),
        extra: Vec4::new(layers[4].repeat_m, layers[4].height_range_m, 32., 0.12),
        tint: Vec4::new(tint.red, tint.green, tint.blue, 1.),
        // Physical base height / repeat drives restrained relief.
        parallax: Vec4::new(depth.0, depth.1, layers[0].repeat_m / repeat, 0.),
        relief: depth.2,
    })
}

/// Keep every ground material's relief at the preset's (`SurfaceDepthLevel`): materials made before a preset
/// change are updated, new ones are made with it (`install_ground_materials`).
fn apply_ground_depth(
    level: Res<SurfaceDepthLevel>,
    data: Res<SurfaceDepthData>,
    mut materials: ResMut<Assets<ShowhomeGroundMaterial>>,
) {
    if !level.is_changed() && !data.is_changed() {
        return;
    }
    let (on, layers, relief) = depth_params(data.quality.of(level.0), data.ground);
    for (_, m) in materials.iter_mut() {
        let p = &mut m.extension.params;
        if p.parallax.x != on || p.parallax.y != layers || p.relief != relief {
            (p.parallax.x, p.parallax.y, p.relief) = (on, layers, relief);
        }
    }
}

fn install_ground_materials(
    mut commands: Commands,
    server: Res<AssetServer>,
    level: Res<SurfaceDepthLevel>,
    depth: Res<SurfaceDepthData>,
    mut arrays: ResMut<GroundArrays>,
    standards: Res<Assets<StandardMaterial>>,
    mut materials: ResMut<Assets<ShowhomeGroundMaterial>>,
    mut cache: ResMut<GroundMaterialCache>,
    primitives: Query<
        (Entity, &MeshMaterial3d<StandardMaterial>, &GltfMaterialName, Option<&GltfMaterialExtras>),
        Without<GroundBlendInstalled>,
    >,
) {
    if arrays.failed {
        return;
    }
    if !arrays.ready {
        let handles = [&arrays.albedo, &arrays.normal, &arrays.orm, &arrays.height];
        if handles.iter().any(|h| server.load_state(h.id()).is_failed()) {
            arrays.failed = true;
            error!("Showhome ground arrays failed to load; run pack_ground_arrays.py and deploy ground_arrays");
            return;
        }
        if !handles.iter().all(|h| server.is_loaded_with_dependencies(h.id())) {
            return;
        }
        arrays.ready = true;
        info!("Showhome ground arrays ready: {} surfaces, native16-bit height masks", array_manifest().colour_rows);
    }
    for (entity, source, name, extras) in &primitives {
        let Some((fallback_texture, fallback_repeat, fallback_class)) = fallback(&name.0) else {
            continue;
        };
        let Some(standard) = standards.get(&source.0) else {
            continue;
        };
        let handle = if let Some(handle) = cache.0.get(&source.0.id()) {
            handle.clone()
        } else {
            let contract = contract(extras);
            let (texture, repeat, class) =
                contract.as_ref().map_or((fallback_texture, fallback_repeat, fallback_class), |c| {
                    (c.base_texture.as_str(), c.base_repeat_m, c.surface_class.as_str())
                });
            let depth = depth_params(depth.quality.of(level.0), depth.ground);
            let Some(params) = params(texture, repeat, class, standard.base_color, depth) else {
                error!("Showhome ground surface {texture} is missing from the packed arrays");
                continue;
            };
            let mut base = standard.clone();
            base.alpha_mode = AlphaMode::Opaque;
            base.base_color = Color::WHITE;
            base.base_color_texture = None;
            base.normal_map_texture = None;
            base.metallic_roughness_texture = None;
            base.occlusion_texture = None;
            // The exact PNG16 array provides the physical parallax in this shader.
            base.depth_map = None;
            let handle = materials.add(ExtendedMaterial {
                base,
                extension: GroundExtension {
                    params,
                    albedo: arrays.albedo.clone(),
                    normal: arrays.normal.clone(),
                    orm: arrays.orm.clone(),
                    height: arrays.height.clone(),
                },
            });
            cache.0.insert(source.0.id(), handle.clone());
            handle
        };
        commands
            .entity(entity)
            .remove::<MeshMaterial3d<StandardMaterial>>()
            .insert((MeshMaterial3d(handle), GroundBlendInstalled));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::settings::Preset;

    #[test]
    fn contract_layer_order_and_physical_ranges() {
        let depth = depth_params(SurfaceDepthData::embedded().quality.high, SurfaceDepthData::embedded().ground);
        let p = params("paving_slabs", 2.4, "hard", Color::WHITE, depth).unwrap();
        let info = array_manifest();
        assert_eq!(p.indices.y, info.materials["worn_dirt"].index);
        assert_eq!(p.indices.z, info.materials["gravel"].index);
        assert_eq!(p.indices.w, info.materials["grass_verge_weeds"].index);
        assert_eq!(p.extra_indices.x, info.materials["construction_sand"].index);
        assert_eq!(p.extra_indices.y, info.macro_layer);
        assert!((p.heights.x - 0.010).abs() < 1e-6);
        let lawn = params("grass_lawn", 2., "lawn", Color::WHITE, depth).unwrap();
        assert_eq!(lawn.extra_indices.x, info.materials["worksite_mud_tracks"].index);
    }

    /// The relief follows the preset: off on LOW (finding: LOW never reached the ground), the preset's layers as
    /// the most steps elsewhere, and the screen-space steps from the data.
    #[test]
    fn the_relief_follows_the_depth_preset() {
        let d = SurfaceDepthData::embedded();
        let at = |p: Preset| {
            let depth = depth_params(d.quality.of(p), d.ground);
            params("paving_slabs", 2.4, "hard", Color::WHITE, depth).unwrap()
        };
        assert_eq!(at(Preset::Low).parallax.x, 0.0, "LOW: no relief");
        for p in [Preset::Medium, Preset::High, Preset::Ultra] {
            let g = at(p);
            assert_eq!(g.parallax.x, 1.0, "{p:?}");
            assert_eq!(g.parallax.y, d.quality.of(p).layers, "{p:?}: the preset's layers");
            assert_eq!((g.relief.x, g.relief.y), (d.ground.steps_per_px, d.ground.min_px));
        }
        assert!(at(Preset::Medium).parallax.y < at(Preset::Ultra).parallax.y);
    }

    #[test]
    fn only_ground_primitives_are_eligible() {
        assert!(fallback("M_GND_Paving.001").is_some());
        assert!(fallback("M_Printed").is_none());
        assert!(fallback("M_GND_WallPrinted").is_none());
        assert!(fallback("M_GND_LineYellow").is_none());
    }
}
