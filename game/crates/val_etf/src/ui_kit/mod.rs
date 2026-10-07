//! Shared UI kit for the hub screens and the HUD, after `design/ui/mockups/_src/common.css` and the hub
//! UI spec: colour tokens, the Barlow fonts and type scale, interaction looks, icons and widgets.
//!
//! Mockup pixel values map 1:1 to `Val::Px`: `UiScale` follows the window, with 1920x1080 as the
//! reference (the smaller of height / 1080 and width / 1920, so 4:3 and 16:10 windows never clip).

// The whole palette and type scale of the mockups are here, used or not yet.
#![allow(dead_code)]

mod icons;
mod look;
mod text;
mod tokens;
mod widgets;

#[allow(unused_imports)]
pub use icons::*;
#[allow(unused_imports)]
pub use look::*;
pub use text::*;
pub use tokens::*;
pub use widgets::*;

use bevy::prelude::*;
use bevy::window::PrimaryWindow;

/// Reference size of the mockups.
pub const REF_HEIGHT: f32 = 1080.0;
pub const REF_WIDTH: f32 = 1920.0;

pub struct UiKitPlugin;

impl Plugin for UiKitPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, icons::load_images)
            .add_systems(Update, follow_window_scale)
            // After every system that sets text colours this frame (looks, screens).
            .add_systems(PostUpdate, text::thicken_dark_ink.before(bevy::ui::UiSystems::Prepare));
        look::plugin(app);
        widgets::plugin(app);
    }

    fn finish(&self, app: &mut App) {
        let fonts = UiFonts::load(&mut app.world_mut().resource_mut::<Assets<Font>>());
        app.insert_resource(fonts);
    }
}

/// The UI scale for a window: mockup px are 1080p px.
pub fn ui_scale_for(width: f32, height: f32) -> f32 {
    (height / REF_HEIGHT).min(width / REF_WIDTH).max(0.25)
}

fn follow_window_scale(windows: Query<&Window, With<PrimaryWindow>>, mut scale: ResMut<UiScale>) {
    let Some(w) = windows.iter().next() else { return };
    let s = ui_scale_for(w.width(), w.height());
    if (scale.0 - s).abs() > 1e-3 {
        scale.0 = s;
    }
}

/// An absolutely positioned node (px at 1080p; `None` = auto).
pub fn abs(left: Option<f32>, right: Option<f32>, top: Option<f32>, bottom: Option<f32>) -> Node {
    Node {
        position_type: PositionType::Absolute,
        left: left.map_or(Val::Auto, Val::Px),
        right: right.map_or(Val::Auto, Val::Px),
        top: top.map_or(Val::Auto, Val::Px),
        bottom: bottom.map_or(Val::Auto, Val::Px),
        ..default()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ui_scale_keeps_the_reference_canvas_inside_the_window() {
        assert_eq!(ui_scale_for(1920.0, 1080.0), 1.0);
        assert_eq!(ui_scale_for(2560.0, 1440.0), 2560.0 / 1920.0);
        // 4:3 is limited by width, so the 1824-wide pages never clip
        assert_eq!(ui_scale_for(1600.0, 1200.0), 1600.0 / 1920.0);
        // 21:9 is limited by height
        assert_eq!(ui_scale_for(3440.0, 1440.0), 1440.0 / 1080.0);
    }
}
