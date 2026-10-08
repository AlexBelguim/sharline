//! Textured materials for the Showhome map, from the texture library in `assets/maps/showhome/textures`
//! (its README gives each texture's use, metres per repeat and roughness). Brush meshes get world-space UVs in
//! metres (see `render::world_uvs`); each material scales them to its repeat. PNGs carry no mipmaps and tiling
//! textures shimmer without them, so the mip chain is built here once an image has loaded. A texture that
//! cannot load becomes one flat texel (the look's colour, or a flat normal), so its surfaces still draw: a
//! material whose image never arrives is not drawn at all.
//!
//! Parallax depth (`assets/data/surface_depth.ron`, see the section at the end): paving, printed walls, roofs,
//! cladding joints, gravel and lawn get a depth map, AO and sometimes a normal map made from the same heights.
//! How many parallax layers they march follows the quality preset ([`SurfaceDepthLevel`], set by `video.rs`).

use crate::render::team_color;
use crate::settings::Preset;
use bevy::asset::RenderAssetUsages;
use bevy::image::{ImageAddressMode, ImageLoaderSettings, ImageSampler, ImageSamplerDescriptor};
use bevy::math::Affine2;
use bevy::pbr::ParallaxMappingMethod;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};
use serde::Deserialize;
use std::collections::HashMap;
use vetf_sim::level::Team;
use vetf_sim::movement::collision::Look;

pub struct MapMaterialsPlugin;

impl Plugin for MapMaterialsPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<SurfaceDepthLevel>()
            .add_systems(Startup, load)
            .add_systems(Update, (build_mipmaps, apply_surface_depth));
    }
}

const DIR: &str = "textures/showhome";

/// A tiling texture: albedo, optional normal map, metres per repeat, roughness.
struct Surface {
    albedo: &'static str,
    normal: Option<&'static str>,
    repeat_m: f32,
    roughness: f32,
}

const fn s(albedo: &'static str, normal: Option<&'static str>, repeat_m: f32, roughness: f32) -> Surface {
    Surface { albedo, normal, repeat_m, roughness }
}

/// What each look is made of on Showhome (`assets/maps/showhome/layout/LAYOUT.md`). Props, metal and the
/// rest keep their flat colours.
fn surface(look: Look) -> Option<Surface> {
    let printed = s("printed_concrete_layers", Some("printed_concrete_layers_normal"), 1.28, 0.8);
    let joints = Some("fibercement_panel_joints_normal");
    Some(match look {
        Look::Ground => s("grass_lawn", None, 2.0, 0.9),
        Look::Asphalt => s("asphalt", None, 4.0, 0.85),
        Look::Paving | Look::TeamA | Look::TeamB => s("paving_slabs", Some("paving_slabs_normal"), 2.4, 0.8),
        Look::Gravel => s("gravel", None, 1.0, 0.9),
        Look::Wall | Look::Trim => printed,
        Look::CladSage => s("fibercement_sage", joints, 4.8, 0.65),
        Look::CladClay => s("fibercement_clay", joints, 4.8, 0.65),
        Look::Roof => s("roof_shingle_dark", Some("roof_shingle_dark_normal"), 2.0, 0.7),
        Look::Floor => s("wood_boards_stained", None, 2.0, 0.8),
        Look::Hedge => s("hedge_leaves", None, 1.5, 0.85),
        Look::Fence => s("picket_wood_white", None, 1.0, 0.6),
        Look::Vehicle => s("truck_paint_white", None, 3.0, 0.4),
        Look::Concrete => s("concrete_smooth", None, 2.0, 0.8),
        _ => return None,
    })
}

const LOOKS: [Look; 15] = [
    Look::Ground,
    Look::Asphalt,
    Look::Paving,
    Look::TeamA,
    Look::TeamB,
    Look::Gravel,
    Look::Wall,
    Look::Trim,
    Look::CladSage,
    Look::CladClay,
    Look::Roof,
    Look::Floor,
    Look::Hedge,
    Look::Fence,
    Look::Vehicle,
];

#[derive(Resource)]
pub struct ShowhomeMaterials {
    materials: HashMap<Look, Handle<StandardMaterial>>,
    /// PNGs waiting to become their finished images.
    pending: Vec<Pending>,
    /// The materials with parallax depth / AO, switched by [`apply_surface_depth`].
    relief: Vec<ReliefMaterial>,
    depth: SurfaceDepthData,
}

struct Pending {
    source: Handle<Image>,
    done: Handle<Image>,
    srgb: bool,
    /// The texel used when the PNG cannot load (RGBA8).
    fallback: [u8; 4],
}

impl ShowhomeMaterials {
    pub fn get(&self, look: Look) -> Option<Handle<StandardMaterial>> {
        self.materials.get(&look).cloned()
    }
}

/// The materials point at reserved image handles. Each is filled once, with the loaded PNG plus its mip chain
/// and a repeating sampler: editing an image after a material has used it does not reach that material.
fn load(
    mut commands: Commands,
    server: Res<AssetServer>,
    images: Res<Assets<Image>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let mut sources: HashMap<(String, bool), Pending> = HashMap::new();
    let mut image = |name: &str, srgb: bool, fallback: [u8; 4]| {
        sources
            .entry((name.to_string(), srgb))
            .or_insert_with(|| Pending {
                source: server
                    .load_builder()
                    .with_settings(move |s: &mut ImageLoaderSettings| s.is_srgb = srgb)
                    .load(format!("{DIR}/{name}.png")),
                done: images.reserve_handle(),
                srgb,
                fallback,
            })
            .done
            .clone()
    };
    let depth = SurfaceDepthData::load();
    let mut relief = Vec::new();
    let mut out = HashMap::new();
    for look in LOOKS {
        let Some(surf) = surface(look) else { continue };
        // Spawn zones stay readable: the paving is tinted toward the team colour.
        let tint = match look {
            Look::TeamA | Look::TeamB => {
                let team = if look == Look::TeamA { Team::A } else { Team::B };
                let c = team_color(Some(team)).to_linear();
                Color::from(LinearRgba::WHITE.mix(&c, 0.45))
            }
            _ => Color::WHITE,
        };
        let mut material = StandardMaterial {
            base_color: tint,
            base_color_texture: Some(image(
                surf.albedo,
                true,
                crate::render::look_color(look).0.to_srgba().to_u8_array(),
            )),
            normal_map_texture: surf.normal.map(|n| image(n, false, FLAT_NORMAL)),
            perceptual_roughness: surf.roughness,
            uv_transform: Affine2::from_scale(Vec2::splat(1.0 / surf.repeat_m)),
            ..default()
        };
        // Parallax depth, AO and a normal map made from the same heights (surface_depth.ron).
        let rel = depth.surfaces.get(surf.albedo).map(|r| {
            if let Some(n) = &r.normal {
                material.normal_map_texture = Some(image(n, false, FLAT_NORMAL));
            }
            material.parallax_depth_scale = parallax_scale(r.depth_cm, surf.repeat_m);
            let depth_map = (r.depth_cm > 0.0).then(|| image(&format!("{}_depth", r.maps), false, FLAT_DEPTH));
            let occlusion = r.occlusion.then(|| image(&format!("{}_orm", r.maps), false, OPEN_ORM));
            (depth_map, occlusion)
        });
        let handle = materials.add(material);
        if let Some((depth_map, occlusion)) = rel {
            relief.push(ReliefMaterial { material: handle.clone(), depth_map, occlusion });
        }
        out.insert(look, handle);
    }
    commands.insert_resource(ShowhomeMaterials {
        materials: out,
        pending: sources.into_values().collect(),
        relief,
        depth,
    });
}

/// A normal map texel that leaves the surface as it is (+Z in tangent space).
const FLAT_NORMAL: [u8; 4] = [128, 128, 255, 255];

/// One loaded PNG per frame becomes its finished image: mip chain, repeating anisotropic sampler. A PNG that
/// failed to load becomes its flat fallback texel.
fn build_mipmaps(mut lib: ResMut<ShowhomeMaterials>, mut images: ResMut<Assets<Image>>, server: Res<AssetServer>) {
    if let Some(i) = lib.pending.iter().position(|p| server.load_state(&p.source).is_failed()) {
        let p = lib.pending.swap_remove(i);
        warn!("map texture {:?} did not load; its surfaces use a flat colour", p.source.path());
        if let Err(e) = images.insert(&p.done, flat_texel(p.fallback, p.srgb)) {
            warn!("cannot fill a map texture: {e:?}");
        }
        return;
    }
    let Some(i) = lib.pending.iter().position(|p| images.contains(&p.source)) else { return };
    let Pending { source, done, srgb, .. } = lib.pending.swap_remove(i);
    let Some(mut image) = images.remove(&source) else { return };
    image.sampler = ImageSampler::Descriptor(ImageSamplerDescriptor {
        address_mode_u: ImageAddressMode::Repeat,
        address_mode_v: ImageAddressMode::Repeat,
        anisotropy_clamp: 8,
        ..ImageSamplerDescriptor::linear()
    });
    let format = image.texture_descriptor.format;
    // 16-bit greyscale PNGs (the depth maps) load as R16Uint, which cannot be filtered: R16Float can, and keeps
    // 11 bits. No mip chain: Bevy's parallax samples the depth map at level 0 only.
    if format == TextureFormat::R16Uint
        && let Some(data) = image.data.take()
    {
        image.data = Some(r16_to_f16(&data));
        image.texture_descriptor.format = TextureFormat::R16Float;
    }
    if matches!(format, TextureFormat::Rgba8UnormSrgb | TextureFormat::Rgba8Unorm)
        && image.texture_descriptor.mip_level_count == 1
        && let Some(base) = image.data.take()
    {
        let (data, levels) = mip_chain(base, image.width() as usize, image.height() as usize, srgb);
        image.data = Some(data);
        image.texture_descriptor.mip_level_count = levels;
    }
    if let Err(e) = images.insert(&done, image) {
        warn!("cannot finish a map texture: {e:?}");
    }
}

/// A 1x1 image of one texel.
fn flat_texel(rgba: [u8; 4], srgb: bool) -> Image {
    let format = if srgb { TextureFormat::Rgba8UnormSrgb } else { TextureFormat::Rgba8Unorm };
    Image::new_fill(
        Extent3d { width: 1, height: 1, depth_or_array_layers: 1 },
        TextureDimension::D2,
        &rgba,
        format,
        RenderAssetUsages::RENDER_WORLD,
    )
}

/// Box-filtered mip levels of an RGBA8 image, appended after the base level. sRGB colour is averaged in linear
/// light (alpha and linear data as they are).
pub fn mip_chain(base: Vec<u8>, mut w: usize, mut h: usize, srgb: bool) -> (Vec<u8>, u32) {
    let to_linear: Vec<f32> =
        (0..256).map(|v| if srgb { Color::srgb_u8(v as u8, 0, 0).to_linear().red } else { v as f32 / 255.0 }).collect();
    let to_byte = |c: f32| -> u8 {
        let c = if srgb { Color::linear_rgb(c, 0.0, 0.0).to_srgba().red } else { c };
        (c * 255.0).round().clamp(0.0, 255.0) as u8
    };
    let mut all = base.clone();
    let mut level = base;
    let mut levels = 1;
    while w > 1 || h > 1 {
        let (nw, nh) = ((w / 2).max(1), (h / 2).max(1));
        let mut next = vec![0u8; nw * nh * 4];
        for y in 0..nh {
            let (y0, y1) = (y * 2 * w, (y * 2 + 1).min(h - 1) * w);
            for x in 0..nw {
                let (x0, x1) = (x * 2, (x * 2 + 1).min(w - 1));
                let px = [(y0 + x0) * 4, (y0 + x1) * 4, (y1 + x0) * 4, (y1 + x1) * 4];
                let o = (y * nw + x) * 4;
                for c in 0..3 {
                    let sum: f32 = px.iter().map(|&p| to_linear[level[p + c] as usize]).sum();
                    next[o + c] = to_byte(sum * 0.25);
                }
                let a: u32 = px.iter().map(|&p| level[p + 3] as u32).sum();
                next[o + 3] = ((a + 2) / 4) as u8;
            }
        }
        all.extend_from_slice(&next);
        level = next;
        (w, h) = (nw, nh);
        levels += 1;
    }
    (all, levels)
}

// ---------------------------------------------------------------------------------------------- parallax depth

/// A depth texel at the top of the relief (no offset) and an ORM texel with no occlusion, for maps that fail.
const FLAT_DEPTH: [u8; 4] = [0, 0, 0, 255];
const OPEN_ORM: [u8; 4] = [255, 255, 0, 255];

/// The quality preset whose parallax the map's surfaces use. `video.rs` sets it from the VIDEO settings.
#[derive(Resource, Debug, Clone, Copy, PartialEq, Eq)]
pub struct SurfaceDepthLevel(pub Preset);

impl Default for SurfaceDepthLevel {
    fn default() -> Self {
        SurfaceDepthLevel(Preset::High)
    }
}

/// One preset's parallax: steep-parallax layers at a grazing view (0 = off) and relief refinement steps.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct DepthQuality {
    pub layers: f32,
    pub relief_steps: u32,
}

impl DepthQuality {
    pub fn on(self) -> bool {
        self.layers >= 1.0
    }

    pub fn method(self) -> ParallaxMappingMethod {
        if self.relief_steps > 0 {
            ParallaxMappingMethod::Relief { max_steps: self.relief_steps }
        } else {
            ParallaxMappingMethod::Occlusion
        }
    }
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct DepthQualities {
    pub low: DepthQuality,
    pub medium: DepthQuality,
    pub high: DepthQuality,
    pub ultra: DepthQuality,
}

impl DepthQualities {
    pub fn of(&self, p: Preset) -> DepthQuality {
        match p {
            Preset::Low => self.low,
            Preset::Medium => self.medium,
            Preset::High => self.high,
            Preset::Ultra => self.ultra,
        }
    }
}

/// One albedo's relief: `<maps>_depth.png` (white = `depth_cm` deep), `<maps>_orm.png` (R = AO), and a normal
/// map that replaces the surface's own (or gives it one).
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct SurfaceRelief {
    pub maps: String,
    pub depth_cm: f32,
    #[serde(default)]
    pub normal: Option<String>,
    #[serde(default = "yes")]
    pub occlusion: bool,
}

fn yes() -> bool {
    true
}

/// `game/assets/data/surface_depth.ron`.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct SurfaceDepthData {
    pub quality: DepthQualities,
    /// Keyed by the albedo name in [`surface`].
    pub surfaces: HashMap<String, SurfaceRelief>,
}

const DEPTH_RON: &str = include_str!("../../../assets/data/surface_depth.ron");

impl SurfaceDepthData {
    /// The copy compiled into the binary.
    pub fn embedded() -> Self {
        ron::from_str(DEPTH_RON).expect("game/assets/data/surface_depth.ron is valid")
    }

    /// The data folder's copy (tunable without a rebuild), else the built-in one.
    pub fn load() -> Self {
        let path = crate::config::assets_root().join("data").join("surface_depth.ron");
        match std::fs::read_to_string(&path).map(|t| ron::from_str(&t)) {
            Ok(Ok(d)) => d,
            Ok(Err(e)) => {
                error!("{} is invalid ({e}); using the built-in copy", path.display());
                Self::embedded()
            }
            Err(_) => Self::embedded(),
        }
    }
}

/// Bevy's `parallax_depth_scale` is in UV units, and one UV unit is `repeat_m` metres here.
pub fn parallax_scale(depth_cm: f32, repeat_m: f32) -> f32 {
    depth_cm.max(0.0) / 100.0 / repeat_m.max(1e-3)
}

/// A material with parallax depth and / or AO, and the maps it gets back when its level turns them on.
struct ReliefMaterial {
    material: Handle<StandardMaterial>,
    depth_map: Option<Handle<Image>>,
    occlusion: Option<Handle<Image>>,
}

/// Put one preset's parallax on a material. Off (LOW) takes the depth map and the AO away, so the surface costs
/// and looks exactly as it did without them.
fn set_relief(
    m: &mut StandardMaterial,
    q: DepthQuality,
    depth_map: Option<&Handle<Image>>,
    ao: Option<&Handle<Image>>,
) {
    m.depth_map = depth_map.filter(|_| q.on()).cloned();
    m.occlusion_texture = ao.filter(|_| q.on()).cloned();
    m.max_parallax_layer_count = q.layers.max(1.0);
    m.parallax_mapping_method = q.method();
}

/// The level changed (or the materials were just made): switch every relief material to it.
fn apply_surface_depth(
    level: Res<SurfaceDepthLevel>,
    lib: Option<Res<ShowhomeMaterials>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let Some(lib) = lib else { return };
    if !level.is_changed() && !lib.is_added() {
        return;
    }
    let q = lib.depth.quality.of(level.0);
    for r in &lib.relief {
        if let Some(mut m) = materials.get_mut(&r.material) {
            set_relief(&mut m, q, r.depth_map.as_ref(), r.occlusion.as_ref());
        }
    }
}

/// R16Uint texels (little-endian, 0..65535 = 0..1) as R16Float.
pub fn r16_to_f16(data: &[u8]) -> Vec<u8> {
    data.as_chunks::<2>()
        .0
        .iter()
        .flat_map(|b| f16_bits(u16::from_le_bytes(*b) as f32 / 65535.0).to_le_bytes())
        .collect()
}

/// IEEE half-precision bits of a value in 0..=1 (clamped), rounded to nearest.
pub fn f16_bits(v: f32) -> u16 {
    let v = v.clamp(0.0, 1.0);
    // Below the smallest normal half (2^-14): subnormal steps of 2^-24.
    if v < 6.103_515_6e-5 {
        return (v * 16_777_216.0).round() as u16;
    }
    let bits = v.to_bits();
    let exp = ((bits >> 23) & 0xff) as i32 - 127 + 15;
    let mant = bits & 0x7f_ffff;
    // Rounding may carry into the exponent, which is still the right value.
    ((exp as u32) << 10 | mant >> 13).wrapping_add((mant >> 12) & 1) as u16
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mip_chain_sizes_and_average() {
        // 4x2 image: left half white, right half black.
        let mut base = Vec::new();
        for _ in 0..2 {
            for x in 0..4 {
                let v = if x < 2 { 255 } else { 0 };
                base.extend_from_slice(&[v, v, v, 255]);
            }
        }
        let (data, levels) = mip_chain(base, 4, 2, false);
        assert_eq!(levels, 3, "4x2, 2x1, 1x1");
        assert_eq!(data.len(), (8 + 2 + 1) * 4);
        assert_eq!(&data[32..40], &[255, 255, 255, 255, 0, 0, 0, 255]);
        assert_eq!(data[40], 128);
        // sRGB averages in linear light: white + black is about 188 in sRGB, not 128.
        let (srgb, _) = mip_chain(vec![255, 255, 255, 255, 0, 0, 0, 255], 2, 1, true);
        assert!((186..=190).contains(&srgb[8]), "{}", srgb[8]);
    }

    /// Decode half-precision bits (test only).
    fn f16_value(h: u16) -> f32 {
        let (exp, mant) = ((h >> 10) & 0x1f, (h & 0x3ff) as f32);
        if exp == 0 { mant * 2f32.powi(-24) } else { (1.0 + mant / 1024.0) * 2f32.powi(exp as i32 - 15) }
    }

    #[test]
    fn depth_maps_convert_to_half_floats() {
        assert_eq!(f16_bits(0.0), 0);
        assert_eq!(f16_bits(1.0), 0x3C00);
        assert_eq!(f16_bits(0.5), 0x3800);
        assert_eq!(f16_bits(2.0), 0x3C00, "clamped to 1");
        // Every 16-bit depth survives within half a step of its 11-bit mantissa, in order.
        let mut last = 0;
        for v in (0..=65535u32).step_by(7) {
            let x = v as f32 / 65535.0;
            let h = f16_bits(x);
            assert!(h >= last, "monotonic at {v}");
            assert!((f16_value(h) - x).abs() <= x.max(6.1e-5) / 2048.0 + 1e-7, "{v}: {} vs {x}", f16_value(h));
            last = h;
        }
        assert_eq!(r16_to_f16(&[0, 0, 255, 255, 0, 128]), [0, 0, 0x00, 0x3C, 0x00, 0x38]);
    }

    #[test]
    fn surface_depth_data_is_complete() {
        let d = SurfaceDepthData::embedded();
        // LOW is off (the look without relief); the higher presets march more layers and refine.
        assert!(!d.quality.low.on());
        let (m, h, u) = (d.quality.medium, d.quality.high, d.quality.ultra);
        assert!(m.on() && m.layers <= h.layers && h.layers <= u.layers);
        assert!(matches!(h.method(), ParallaxMappingMethod::Relief { .. }));
        assert!(u.relief_steps >= h.relief_steps);
        // Every entry names an albedo the map uses and maps that exist next to it.
        let albedos: Vec<&str> = LOOKS.iter().filter_map(|l| surface(*l)).map(|s| s.albedo).collect();
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../assets").join(DIR);
        for (albedo, r) in &d.surfaces {
            assert!(albedos.contains(&albedo.as_str()), "{albedo} is not a Showhome albedo");
            assert!((0.0..=3.0).contains(&r.depth_cm), "{albedo}: {} cm", r.depth_cm);
            let mut files = vec![format!("{}_orm", r.maps)];
            files.extend((r.depth_cm > 0.0).then(|| format!("{}_depth", r.maps)));
            files.extend(r.normal.clone());
            for f in files {
                assert!(dir.join(format!("{f}.png")).is_file(), "{albedo}: {f}.png is missing");
            }
        }
        assert!(d.surfaces.contains_key("paving_slabs") && d.surfaces.contains_key("printed_concrete_layers"));
        // Bevy's depth scale is per UV unit: 1.2 cm over a 2.4 m repeat.
        assert!((parallax_scale(1.2, 2.4) - 0.005).abs() < 1e-7);
        assert_eq!(parallax_scale(-1.0, 2.0), 0.0);
    }

    #[test]
    fn low_takes_the_relief_away() {
        let d = SurfaceDepthData::embedded();
        let (depth, ao) = (Handle::<Image>::default(), Handle::<Image>::default());
        let mut m = StandardMaterial::default();
        set_relief(&mut m, d.quality.high, Some(&depth), Some(&ao));
        assert!(m.depth_map.is_some() && m.occlusion_texture.is_some());
        assert_eq!(m.max_parallax_layer_count, d.quality.high.layers);
        set_relief(&mut m, d.quality.low, Some(&depth), Some(&ao));
        assert!(m.depth_map.is_none() && m.occlusion_texture.is_none());
        // A surface with AO but no depth (asphalt) keeps no depth map on any level.
        set_relief(&mut m, d.quality.ultra, None, Some(&ao));
        assert!(m.depth_map.is_none() && m.occlusion_texture.is_some());
    }
}
