//! Showhome's hedge material, and the parallax quality the map's surfaces follow.
//!
//! - **Hedge.** The texture library's `hedge_leaves` (`assets/textures/showhome`, see its README) on the plain
//!   hedge boxes: the foliage plugin hides those boxes behind its leaf shells (and shows them again on LOW), and
//!   the kit's hedges take the same material. PNGs carry no mipmaps and tiling textures shimmer without them, so
//!   the mip chain is built here once the image has loaded; a PNG that cannot load becomes one flat texel.
//!   The rest of the library painted the old blockout brushes, which Showhome no longer draws (the art kit does),
//!   so it is not loaded.
//! - **Parallax quality** (`assets/data/surface_depth.ron`): the quality PRESET ([`SurfaceDepthLevel`], set by
//!   `video.rs`) picks how far the kit's depth maps (`showhome_kit`) and the ground's relief (`showhome_ground`)
//!   march; LOW turns both off.

use crate::settings::Preset;
use bevy::asset::RenderAssetUsages;
use bevy::image::{ImageAddressMode, ImageLoaderSettings, ImageSampler, ImageSamplerDescriptor};
use bevy::math::Affine2;
use bevy::pbr::ParallaxMappingMethod;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};
use serde::Deserialize;
use std::collections::HashMap;
use vetf_sim::movement::collision::Look;

mod strafe;

pub struct MapMaterialsPlugin;

impl Plugin for MapMaterialsPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(SurfaceDepthData::load())
            .init_resource::<SurfaceDepthLevel>()
            .add_systems(Startup, load)
            .add_systems(Update, build_mipmaps);
        strafe::plugin(app);
    }
}

const DIR: &str = "textures/showhome";

/// The hedge: its albedo, metres per repeat and roughness.
const HEDGE: (&str, f32, f32) = ("hedge_leaves", 1.5, 0.85);

#[derive(Resource)]
pub struct ShowhomeMaterials {
    materials: HashMap<Look, Handle<StandardMaterial>>,
    /// PNGs waiting to become their finished images.
    pending: Vec<Pending>,
}

struct Pending {
    source: Handle<Image>,
    done: Handle<Image>,
    srgb: bool,
    /// The texel used when the PNG cannot load (RGBA8).
    fallback: [u8; 4],
}

impl ShowhomeMaterials {
    /// The material of a look on Showhome: only the hedge has one.
    pub fn get(&self, look: Look) -> Option<Handle<StandardMaterial>> {
        self.materials.get(&look).cloned()
    }
}

/// The hedge material points at a reserved image handle, filled once with the loaded PNG plus its mip chain and
/// a repeating sampler: editing an image after a material has used it does not reach that material.
fn load(
    mut commands: Commands,
    server: Res<AssetServer>,
    images: Res<Assets<Image>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let (albedo, repeat_m, roughness) = HEDGE;
    let fallback = crate::render::look_color(Look::Hedge).0.to_srgba().to_u8_array();
    let pending = request(&server, &images, albedo, true, fallback);
    let hedge = materials.add(StandardMaterial {
        base_color_texture: Some(pending.done.clone()),
        perceptual_roughness: roughness,
        uv_transform: Affine2::from_scale(Vec2::splat(1.0 / repeat_m)),
        ..default()
    });
    commands.insert_resource(ShowhomeMaterials {
        materials: HashMap::from([(Look::Hedge, hedge)]),
        pending: vec![pending],
    });
}

/// Start loading `textures/showhome/<name>.png`; `build_mipmaps` fills the reserved handle once it has loaded.
fn request(server: &AssetServer, images: &Assets<Image>, name: &str, srgb: bool, fallback: [u8; 4]) -> Pending {
    Pending {
        source: server
            .load_builder()
            .with_settings(move |s: &mut ImageLoaderSettings| s.is_srgb = srgb)
            .load(format!("{DIR}/{name}.png")),
        done: images.reserve_handle(),
        srgb,
        fallback,
    }
}

/// One loaded PNG per frame becomes its finished image: mip chain, repeating anisotropic sampler. A PNG that
/// failed to load becomes its flat fallback texel.
fn build_mipmaps(mut lib: ResMut<ShowhomeMaterials>, mut images: ResMut<Assets<Image>>, server: Res<AssetServer>) {
    if lib.pending.is_empty() {
        return;
    }
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

    /// Relief mapping with this preset's refinement steps (plain occlusion parallax without any).
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

/// The Showhome ground's relief (`showhome_ground.wgsl`): it marches `steps_per_px` steps per pixel that its
/// deepest shift spans on screen (at most the preset's `layers`), and none where that shift is under `min_px`.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct GroundRelief {
    pub steps_per_px: f32,
    pub min_px: f32,
}

/// `game/assets/data/surface_depth.ron`.
#[derive(Resource, Debug, Clone, PartialEq, Deserialize)]
pub struct SurfaceDepthData {
    pub quality: DepthQualities,
    pub ground: GroundRelief,
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
        assert!(m.relief_steps <= h.relief_steps && h.relief_steps <= u.relief_steps);
        // Every enabled preset is relief mapping, so a preset change never compiles another shader variant.
        for q in [m, h, u] {
            assert!(matches!(q.method(), ParallaxMappingMethod::Relief { .. }), "{q:?}");
        }
        assert_eq!(d.quality.low.method(), ParallaxMappingMethod::Occlusion);
        // The ground's relief: at least a step per pixel of shift, and off only below a pixel.
        assert!(d.ground.steps_per_px >= 1.0, "{:?}", d.ground);
        assert!((0.0..=1.0).contains(&d.ground.min_px), "{:?}", d.ground);
        // Bevy's depth scale is per UV unit: 1.2 cm over a 2.4 m repeat.
        assert!((parallax_scale(1.2, 2.4) - 0.005).abs() < 1e-7);
        assert_eq!(parallax_scale(-1.0, 2.0), 0.0);
    }

    /// Only the hedge's albedo is loaded from the texture library (the rest painted the old brushes).
    #[test]
    fn only_the_hedge_texture_is_used() {
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../assets").join(DIR);
        assert!(dir.join(format!("{}.png", HEDGE.0)).is_file());
        assert!(HEDGE.1 > 0.0 && (0.0..=1.0).contains(&HEDGE.2));
    }
}
