//! UI images: the mockup icons (white on transparent, rasterised from `design/ui/mockups/_src/icons.svg` by
//! `game/tools/ui_raster.cjs`), generated shapes (`game/tools/ui_shapes.py`) and the placeholder art.
//! Tint icons and shapes with `ImageNode.color`.

use bevy::prelude::*;
use std::collections::HashMap;

/// Every icon of `icons.svg` (file stem = symbol id without `i-`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Icon {
    Head,
    Torso,
    Arms,
    Legs,
    Grapple,
    Scan,
    KesUlt,
    Drone,
    Pulse,
    SolUlt,
    Bandage,
    Medkit,
    Energy,
    Food,
    Bleed,
    Heal,
    Jet,
    Headshot,
    ShieldBreak,
    Wall,
    Mako,
    Warden,
    Gl,
    Mag,
    Optic,
    Stock,
    Under,
    Side,
    GunShield,
    MagSlot,
    Crown,
    Check,
    Copy,
    Signal,
    Zipline,
    Swap,
    Chev,
}

impl Icon {
    pub const ALL: [Icon; 37] = [
        Icon::Head,
        Icon::Torso,
        Icon::Arms,
        Icon::Legs,
        Icon::Grapple,
        Icon::Scan,
        Icon::KesUlt,
        Icon::Drone,
        Icon::Pulse,
        Icon::SolUlt,
        Icon::Bandage,
        Icon::Medkit,
        Icon::Energy,
        Icon::Food,
        Icon::Bleed,
        Icon::Heal,
        Icon::Jet,
        Icon::Headshot,
        Icon::ShieldBreak,
        Icon::Wall,
        Icon::Mako,
        Icon::Warden,
        Icon::Gl,
        Icon::Mag,
        Icon::Optic,
        Icon::Stock,
        Icon::Under,
        Icon::Side,
        Icon::GunShield,
        Icon::MagSlot,
        Icon::Crown,
        Icon::Check,
        Icon::Copy,
        Icon::Signal,
        Icon::Zipline,
        Icon::Swap,
        Icon::Chev,
    ];

    pub fn file(self) -> &'static str {
        match self {
            Icon::Head => "head",
            Icon::Torso => "torso",
            Icon::Arms => "arms",
            Icon::Legs => "legs",
            Icon::Grapple => "grapple",
            Icon::Scan => "scan",
            Icon::KesUlt => "kes-ult",
            Icon::Drone => "drone",
            Icon::Pulse => "pulse",
            Icon::SolUlt => "sol-ult",
            Icon::Bandage => "bandage",
            Icon::Medkit => "medkit",
            Icon::Energy => "energy",
            Icon::Food => "food",
            Icon::Bleed => "bleed",
            Icon::Heal => "heal",
            Icon::Jet => "jet",
            Icon::Headshot => "headshot",
            Icon::ShieldBreak => "shieldbreak",
            Icon::Wall => "wall",
            Icon::Mako => "mako",
            Icon::Warden => "warden",
            Icon::Gl => "gl",
            Icon::Mag => "mag",
            Icon::Optic => "optic",
            Icon::Stock => "stock",
            Icon::Under => "under",
            Icon::Side => "side",
            Icon::GunShield => "gunshield",
            Icon::MagSlot => "magslot",
            Icon::Crown => "crown",
            Icon::Check => "check",
            Icon::Copy => "copy",
            Icon::Signal => "signal",
            Icon::Zipline => "zipline",
            Icon::Swap => "swap",
            Icon::Chev => "chev",
        }
    }

    /// The icon of a body zone.
    pub fn zone(z: vetf_sim::Zone) -> Icon {
        match z {
            vetf_sim::Zone::Head => Icon::Head,
            vetf_sim::Zone::Torso => Icon::Torso,
            vetf_sim::Zone::Arms => Icon::Arms,
            vetf_sim::Zone::Legs => Icon::Legs,
        }
    }
}

/// Generated shapes (white; tint them).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Shape {
    /// A tier pip leaning like '/', drawn at 9x10.
    Pip,
    /// An ammo-tier pip, drawn at 8x10.
    PipAmmo,
    /// A dashed 1 px border for 9-slicing (empty slots, unbound keys).
    Dash9Slice,
    /// The reload-wheel glyph: six sectors (slot 1 at the top, clockwise), drawn at 16x16.
    WheelRing,
    /// One sector of the wheel at 12 o'clock; rotate it by (slot - 1) x 60 degrees.
    WheelSector,
    /// A pointy-top hexagon.
    HexBadge,
    KestrelHex,
    SolaceHex,
    /// Up and down arrows for the [up/down] key cap.
    KeyUpDown,
}

impl Shape {
    pub const ALL: [Shape; 9] = [
        Shape::Pip,
        Shape::PipAmmo,
        Shape::Dash9Slice,
        Shape::WheelRing,
        Shape::WheelSector,
        Shape::HexBadge,
        Shape::KestrelHex,
        Shape::SolaceHex,
        Shape::KeyUpDown,
    ];

    pub fn file(self) -> &'static str {
        match self {
            Shape::Pip => "pip",
            Shape::PipAmmo => "pip_ammo",
            Shape::Dash9Slice => "dash_9slice",
            Shape::WheelRing => "wheel_ring",
            Shape::WheelSector => "wheel_sector",
            Shape::HexBadge => "hex_badge",
            Shape::KestrelHex => "kestrel_hex",
            Shape::SolaceHex => "solace_hex",
            Shape::KeyUpDown => "key_updown",
        }
    }
}

/// Placeholder art from the mockups (`game/assets/ui/img`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Art {
    /// 1920x1080 main-menu backdrop (Kestrel in the hangar).
    MenuKestrel,
    KestrelPortrait,
    SolacePortrait,
    /// 1920x1080 street scene (lobby map card, crosshair preview).
    HudStreet,
    /// 1280x720 Mako render: the Loadout preview until a 3D viewport exists.
    MakoDark,
}

impl Art {
    pub const ALL: [Art; 5] = [Art::MenuKestrel, Art::KestrelPortrait, Art::SolacePortrait, Art::HudStreet, Art::MakoDark];

    pub fn file(self) -> &'static str {
        match self {
            Art::MenuKestrel => "menu_kestrel.jpg",
            Art::KestrelPortrait => "kestrel_portrait.jpg",
            Art::SolacePortrait => "solace_portrait.jpg",
            Art::HudStreet => "hud_street.jpg",
            Art::MakoDark => "mako_dark.jpg",
        }
    }
}

/// Handles to every UI image (loaded at start-up from `game/assets/ui`).
#[derive(Resource, Default, Clone)]
pub struct UiImages {
    icons: HashMap<Icon, Handle<Image>>,
    shapes: HashMap<Shape, Handle<Image>>,
    art: HashMap<Art, Handle<Image>>,
}

impl UiImages {
    pub fn icon(&self, i: Icon) -> Handle<Image> {
        self.icons.get(&i).cloned().unwrap_or_default()
    }

    pub fn shape(&self, s: Shape) -> Handle<Image> {
        self.shapes.get(&s).cloned().unwrap_or_default()
    }

    pub fn art(&self, a: Art) -> Handle<Image> {
        self.art.get(&a).cloned().unwrap_or_default()
    }
}

pub(super) fn load_images(mut commands: Commands, assets: Res<AssetServer>) {
    let images = UiImages {
        icons: Icon::ALL.iter().map(|i| (*i, assets.load(format!("ui/icons/{}.png", i.file())))).collect(),
        shapes: Shape::ALL.iter().map(|s| (*s, assets.load(format!("ui/shapes/{}.png", s.file())))).collect(),
        art: Art::ALL.iter().map(|a| (*a, assets.load(format!("ui/img/{}", a.file())))).collect(),
    };
    commands.insert_resource(images);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    #[test]
    fn every_image_file_exists() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../assets/ui");
        for i in Icon::ALL {
            assert!(root.join(format!("icons/{}.png", i.file())).exists(), "{i:?}");
        }
        for s in Shape::ALL {
            assert!(root.join(format!("shapes/{}.png", s.file())).exists(), "{s:?}");
        }
        for a in Art::ALL {
            assert!(root.join(format!("img/{}", a.file())).exists(), "{a:?}");
        }
    }
}
