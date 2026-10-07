//! The halo widget (widgets.js `haloSVG`) as stacked white PNG layers tinted per arc: the core's arc shape,
//! a glow under lit arcs, the unlit hairline, Mender's inner arcs, Volt's spikes, the weight band and the
//! orbiting power cells. Layers come from `game/tools/halo_raster.cjs` (`game/assets/ui/halo`). Static
//! for the hub; the per-arc drain of the in-match widget needs a material later.

use crate::ui_kit::*;
use bevy::prelude::*;
use std::collections::HashMap;
use vetf_sim::Zone;
use vetf_sim::ZoneTable;
use vetf_sim::data::{Core, WeightClass};

/// SVG units of the widget's viewBox.
const VIEW: f32 = 120.0;
const R: f32 = 34.0;
const BAND: Color = Color::srgb(0x3A as f32 / 255.0, 0x3F as f32 / 255.0, 0x47 as f32 / 255.0);
const VOLT_TICK_UNLIT: Color = Color::srgb(0x33 as f32 / 255.0, 0x36 as f32 / 255.0, 0x3D as f32 / 255.0);
const LETTER_UNLIT: Color = Color::srgb(0x5A as f32 / 255.0, 0x60 as f32 / 255.0, 0x69 as f32 / 255.0);

fn core_file(c: Core) -> &'static str {
    match c {
        Core::Bulwark => "bulwark",
        Core::Mender => "mender",
        Core::Volt => "volt",
        Core::Phase => "phase",
    }
}

fn zone_file(z: Zone) -> &'static str {
    match z {
        Zone::Head => "head",
        Zone::Torso => "torso",
        Zone::Arms => "arms",
        Zone::Legs => "legs",
    }
}

/// Angle of an arc's centre on the widget (degrees, clockwise from +x; head is up).
fn zone_angle(z: Zone) -> f32 {
    match z {
        Zone::Head => -90.0,
        Zone::Legs => 0.0,
        Zone::Torso => 90.0,
        Zone::Arms => 180.0,
    }
}

/// Every halo layer image.
#[derive(Resource, Default, Clone)]
pub struct HaloImages(HashMap<String, Handle<Image>>);

impl HaloImages {
    pub fn names() -> Vec<String> {
        let mut v = Vec::new();
        for c in Core::ALL {
            for z in Zone::ALL {
                let base = format!("{}_{}", core_file(c), zone_file(z));
                for suffix in ["", "_glow", "_hair", "_rim"] {
                    v.push(format!("{base}{suffix}"));
                }
                match c {
                    Core::Mender => v.push(format!("{base}_inner")),
                    Core::Volt => v.push(format!("{base}_ticks")),
                    _ => {}
                }
            }
        }
        v.extend(["band_medium", "band_medium_line", "band_heavy", "band_heavy_line"].map(String::from));
        v
    }

    pub fn load(assets: &AssetServer) -> Self {
        Self(Self::names().into_iter().map(|n| (n.clone(), assets.load(format!("ui/halo/{n}.png")))).collect())
    }

    fn get(&self, name: &str) -> Handle<Image> {
        self.0.get(name).cloned().unwrap_or_default()
    }
}

/// What the centre of the widget shows.
#[derive(Debug, Clone, PartialEq)]
pub enum Centre {
    Nothing,
    /// Shield value with a sub-label (`T2 MENDER`) in a tier colour.
    Value {
        value: u32,
        sub: String,
        sub_color: Color,
    },
}

/// One halo to draw.
#[derive(Debug, Clone, PartialEq)]
pub struct HaloLook {
    pub core: Core,
    /// Tier per arc (0 = unlit).
    pub tiers: ZoneTable<u8>,
    /// Colour of each lit arc (normally its tier colour).
    pub colors: ZoneTable<Color>,
    pub weight: WeightClass,
    pub cells: u8,
    /// The band's tier line and the cells' colour.
    pub accent: Color,
    pub centre: Centre,
    /// Draw the H / T / A / L letters (the tier-mode widget: core cards).
    pub letters: bool,
    /// The arc being edited gets a TEXT_HI rim.
    pub selected: Option<Zone>,
}

/// The cells' orbit: one turn per `period` seconds.
#[derive(Component)]
pub struct HaloOrbit {
    pub period: f32,
}

fn layer(img: Handle<Image>, color: Color) -> impl Bundle {
    (
        ImageNode::new(img).with_color(color),
        Node {
            position_type: PositionType::Absolute,
            left: px(0),
            top: px(0),
            width: percent(100),
            height: percent(100),
            ..default()
        },
    )
}

/// Spawn a halo widget of `size` px as a child of `parent`.
pub fn spawn_halo(parent: &mut ChildSpawnerCommands, images: &HaloImages, fonts: &UiFonts, look: &HaloLook, size: f32) {
    let k = size / VIEW;
    let core = core_file(look.core);
    parent.spawn(Node { width: px(size), height: px(size), flex_shrink: 0.0, ..default() }).with_children(|w| {
        match look.weight {
            WeightClass::Medium => {
                w.spawn(layer(images.get("band_medium"), BAND));
                w.spawn(layer(images.get("band_medium_line"), translucent(look.accent, 0.25)));
            }
            WeightClass::Heavy => {
                w.spawn(layer(images.get("band_heavy"), BAND));
                w.spawn(layer(images.get("band_heavy_line"), translucent(look.accent, 0.30)));
            }
            _ => {}
        }
        for z in [Zone::Head, Zone::Legs, Zone::Torso, Zone::Arms] {
            let base = format!("{core}_{}", zone_file(z));
            let lit = look.tiers[z] > 0;
            let c = look.colors[z];
            if lit {
                w.spawn(layer(images.get(&format!("{base}_glow")), translucent(c, 0.35)));
                w.spawn(layer(images.get(&base), translucent(c, 0.85)));
                if look.core == Core::Mender {
                    w.spawn(layer(images.get(&format!("{base}_inner")), translucent(c, 0.8)));
                }
            } else {
                w.spawn(layer(images.get(&base), UNLIT));
                w.spawn(layer(images.get(&format!("{base}_hair")), W13));
                if look.core == Core::Mender {
                    w.spawn(layer(images.get(&format!("{base}_inner")), UNLIT));
                }
            }
            if look.core == Core::Volt {
                w.spawn(layer(images.get(&format!("{base}_ticks")), if lit { c } else { VOLT_TICK_UNLIT }));
            }
            if look.selected == Some(z) {
                w.spawn(layer(images.get(&format!("{base}_rim")), TEXT_HI));
            }
        }
        if look.letters {
            let r = R - if look.core == Core::Mender { 15.0 } else { 12.0 };
            let font = 9.5 * k;
            for z in Zone::ALL {
                let a = zone_angle(z).to_radians();
                let (x, y) = (60.0 + r * a.cos(), 60.0 + r * a.sin());
                let box_ = 12.0 * k;
                let lit = look.tiers[z] > 0;
                w.spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        left: px(x * k - box_ / 2.0),
                        top: px(y * k - box_ / 2.0),
                        width: px(box_),
                        height: px(box_),
                        justify_content: JustifyContent::Center,
                        align_items: AlignItems::Center,
                        ..default()
                    },
                    children![fonts.text(
                        &z.label()[..1],
                        Face::Display,
                        700,
                        font,
                        if lit { look.colors[z] } else { LETTER_UNLIT },
                        0.0
                    )],
                ));
            }
        }
        if look.cells > 0 {
            let n = look.cells as usize;
            let pills: Vec<_> = (0..n)
                .map(|i| {
                    let a = (-60.0 + i as f32 * 360.0 / n as f32).to_radians();
                    let (x, y) = (60.0 + (R + 19.0) * a.cos(), 60.0 + (R + 19.0) * a.sin());
                    (
                        Node {
                            position_type: PositionType::Absolute,
                            left: px((x - 3.0) * k),
                            top: px((y - 5.0) * k),
                            width: px(6.0 * k),
                            height: px(10.0 * k),
                            border_radius: BorderRadius::all(px(3.0 * k)),
                            ..default()
                        },
                        BackgroundColor(translucent(look.accent, 0.95)),
                    )
                })
                .collect();
            w.spawn((
                HaloOrbit { period: if n == 3 { 14.0 } else { 10.0 } },
                Node {
                    position_type: PositionType::Absolute,
                    left: px(0),
                    top: px(0),
                    width: percent(100),
                    height: percent(100),
                    ..default()
                },
                Children::spawn(SpawnIter(pills.into_iter())),
            ));
        }
        if let Centre::Value { value, sub, sub_color } = &look.centre {
            // Baselines at 62 and 73 units: the box top is the baseline minus the ascent (1 em).
            w.spawn((
                Node {
                    position_type: PositionType::Absolute,
                    left: px(0),
                    right: px(0),
                    top: px((62.0 - 21.0) * k),
                    justify_content: JustifyContent::Center,
                    ..default()
                },
                children![fonts.text_line(
                    value.to_string(),
                    Face::Display,
                    700,
                    21.0 * k,
                    TEXT_HI,
                    0.0,
                    bevy::text::LineHeight::RelativeToFont(1.2),
                )],
            ));
            w.spawn((
                Node {
                    position_type: PositionType::Absolute,
                    left: px(0),
                    right: px(0),
                    top: px((73.0 - 8.0) * k),
                    justify_content: JustifyContent::Center,
                    ..default()
                },
                children![fonts.text(sub.clone(), Face::Display, 600, 8.0 * k, *sub_color, 1.2 / 8.0)],
            ));
        }
    });
}

/// Turn the power cells (10 s a turn, 14 s with three cells).
pub fn orbit_cells(time: Res<Time>, mut q: Query<(&HaloOrbit, &mut UiTransform)>) {
    let t = time.elapsed_secs();
    for (o, mut tf) in &mut q {
        let turn = (t / o.period).fract() * std::f32::consts::TAU;
        tf.rotation = Rot2::radians(turn);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    #[test]
    fn every_halo_layer_exists() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../assets/ui/halo");
        let names = HaloImages::names();
        assert_eq!(names.len(), 4 * 4 * 4 + 4 + 4 + 4);
        for n in names {
            assert!(root.join(format!("{n}.png")).exists(), "{n}");
        }
    }
}
