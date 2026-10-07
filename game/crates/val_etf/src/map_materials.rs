//! Textured materials for the Showhome map, from the texture library in `assets/maps/showhome/textures`
//! (its README gives each texture's use, metres per repeat and roughness). Brush meshes get world-space UVs in
//! metres (see `render::world_uvs`); each material scales them to its repeat. PNGs carry no mipmaps and tiling
//! textures shimmer without them, so the mip chain is built here once an image has loaded. A texture that
//! cannot load becomes one flat texel (the look's colour, or a flat normal), so its surfaces still draw: a
//! material whose image never arrives is not drawn at all.

use crate::render::team_color;
use bevy::asset::RenderAssetUsages;
use bevy::image::{ImageAddressMode, ImageLoaderSettings, ImageSampler, ImageSamplerDescriptor};
use bevy::math::Affine2;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};
use std::collections::HashMap;
use vetf_sim::level::Team;
use vetf_sim::movement::collision::Look;

pub struct MapMaterialsPlugin;

impl Plugin for MapMaterialsPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, load).add_systems(Update, build_mipmaps);
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
    let mut sources: HashMap<(&str, bool), Pending> = HashMap::new();
    let mut image = |name: &'static str, srgb: bool, fallback: [u8; 4]| {
        sources
            .entry((name, srgb))
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
        let material = StandardMaterial {
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
        out.insert(look, materials.add(material));
    }
    commands.insert_resource(ShowhomeMaterials { materials: out, pending: sources.into_values().collect() });
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
}
