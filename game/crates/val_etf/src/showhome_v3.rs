//! Frozen, read-only current-kit snapshot for a Showhome v3 TDM session.
use bevy::prelude::*;
use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;
use vetf_sim::maps::showhome_v3::{CorePreview, FULL_MAP_ID};

#[derive(Resource, Clone)]
pub struct CurrentV3Preview(pub Arc<CorePreview>, pub BTreeMap<String, BTreeMap<String, f32>>);

impl CurrentV3Preview {
    pub fn from_snapshot(snapshot: CorePreview) -> Result<Self, String> {
        let scales = normal_scales(&snapshot)?;
        Ok(Self(Arc::new(snapshot), scales))
    }
}

fn normal_scales(preview: &CorePreview) -> Result<BTreeMap<String, BTreeMap<String, f32>>, String> {
    let mut paths = preview.kit_scenes.iter().cloned().collect::<BTreeSet<_>>();
    for instance in &preview.placements.instances {
        if instance.mode == "all" || instance.mode == preview.asset_mode {
            paths.insert(preview.catalog.get(&instance.prop_id).map_err(|e| e.to_string())?.glb.clone());
        }
    }
    let mut result = BTreeMap::new();
    for path in paths {
        result.insert(path.clone(), normal_scales_for_path(&path)?);
    }
    Ok(result)
}

pub(crate) fn normal_scales_for_path(path: &str) -> Result<BTreeMap<String, f32>, String> {
    let bytes = std::fs::read(crate::config::assets_root().join(path)).map_err(|e| e.to_string())?;
    let json = vetf_sim::build_mode::collision::glb_json(&bytes).map_err(|e| e.to_string())?;
    let mut result = BTreeMap::new();
    for material in json["materials"].as_array().into_iter().flatten() {
        if let (Some(name), Some(scale)) = (material["name"].as_str(), material["normalTexture"]["scale"].as_f64())
            && scale.is_finite()
            && scale >= 0.
            && scale != 1.
        {
            result.insert(name.into(), scale as f32);
        }
    }
    Ok(result)
}

pub fn is_v3(name: &str) -> bool {
    vetf_sim::maps::showhome_v3::canonical_id(name).is_some()
}
pub fn map_title(name: &str) -> &str {
    if vetf_sim::maps::showhome_v3::canonical_id(name) == Some(FULL_MAP_ID) {
        "ShowhomeFull"
    } else if is_v3(name) {
        "Showhome v3 Core"
    } else if name.eq_ignore_ascii_case("showhome") {
        "Showhome"
    } else if name.eq_ignore_ascii_case("range") {
        "Gun range"
    } else {
        name
    }
}

/// Map-local look-development overrides. They leave saved video settings and other maps untouched.
pub fn preview_sun() -> DirectionalLight {
    sun_options(
        std::env::var("VETF_V3_SHADOW_MAPS").ok().as_deref(),
        std::env::var("VETF_V3_SHADOW_DEPTH_BIAS").ok().as_deref(),
        std::env::var("VETF_V3_SHADOW_NORMAL_BIAS").ok().as_deref(),
    )
}

fn sun_options(maps: Option<&str>, depth: Option<&str>, normal: Option<&str>) -> DirectionalLight {
    let number = |value: Option<&str>, fallback: f32, limit: f32| {
        value
            .and_then(|v| v.parse::<f32>().ok())
            .filter(|v| v.is_finite() && *v >= 0. && *v <= limit)
            .unwrap_or(fallback)
    };
    DirectionalLight {
        color: Color::linear_rgb(1., 0.84, 0.66),
        illuminance: 9000.,
        shadow_maps_enabled: !maps
            .is_some_and(|v| matches!(v.trim().to_ascii_lowercase().as_str(), "off" | "false" | "0")),
        shadow_depth_bias: number(depth, DirectionalLight::DEFAULT_SHADOW_DEPTH_BIAS, 0.5),
        shadow_normal_bias: number(normal, DirectionalLight::DEFAULT_SHADOW_NORMAL_BIAS, 10.),
        ..default()
    }
}

pub fn load(name: &str, commands: &mut Commands) -> Result<vetf_sim::level::Level, String> {
    if is_v3(name) {
        let preview = Arc::new(
            vetf_sim::maps::showhome_v3::load_with_placements(crate::config::assets_root(), name, None)
                .map_err(|e| e.to_string())?,
        );
        info!(
            "Authored Showhome map: {} instances, {} convex volumes, {} distributed safe spawns; read {}",
            preview.placements.instances.len(),
            preview.volumes.len(),
            preview.level.spawns.len(),
            preview.placements_source.display()
        );
        let level = preview.level.clone();
        let scales = normal_scales(&preview)?;
        commands.insert_resource(CurrentV3Preview(preview, scales));
        Ok(level)
    } else {
        commands.remove_resource::<CurrentV3Preview>();
        Ok(crate::config::level_by_name(name))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn v3_normal_strengths_read_actual_glb_spec_without_extension() {
        let preview = vetf_sim::maps::showhome_v3::load(crate::config::assets_root()).unwrap();
        let scales = normal_scales(&preview).unwrap();
        assert_eq!(scales["maps/showhome_v3/houses.glb"]["M_SH_PrintedConcrete"], 0.25);
        assert!(scales.keys().all(|p| !p.contains("extension/")));
    }
    #[test]
    fn v3_shadow_diagnostics_keep_defaults_and_reject_invalid_biases() {
        let light = sun_options(None, None, None);
        assert!(light.shadow_maps_enabled);
        assert_eq!(light.shadow_depth_bias, DirectionalLight::DEFAULT_SHADOW_DEPTH_BIAS);
        assert_eq!(light.shadow_normal_bias, DirectionalLight::DEFAULT_SHADOW_NORMAL_BIAS);
        let off = sun_options(Some("off"), Some("0.08"), Some("0"));
        assert!(!off.shadow_maps_enabled);
        assert_eq!((off.shadow_depth_bias, off.shadow_normal_bias), (0.08, 0.));
        assert_eq!(sun_options(None, Some("NaN"), Some("-1")).shadow_normal_bias, light.shadow_normal_bias);
    }
}
