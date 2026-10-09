//! The Loadout screen's 3D gun preview: the draft's gun built from its glTF model with the parts it would carry
//! (the same assembly the match uses, [`WeaponModels::spawn`]), shown in the weapon column's preview box. A
//! hovered (or arrow-key) popover row puts its part on at once, so the gun shows what a pick would look like.
//!
//! It is drawn by its own camera into an image (a [`ViewportNode`] shows it), on its own render layer far below
//! the map, with its own studio lights, and exists only while the screen's preview box does: the camera, the
//! lights and the gun are despawned with the screen. Dragging in the box turns the gun, the wheel zooms. The
//! slot hotspots sit on the gun's sockets and follow it as it turns. A gun without a model (the Skink), or one
//! whose files are still loading, keeps the 2D picture of `loadout_ui.ron`.
//!
//! A new pick builds the new gun hidden, and only swaps it in once all its parts are in the world, so the gun
//! never shows bare or blinks out. Its bounds then frame it: the gun's longest side fills `fill` of the width.
//!
//! The view's axes: the camera looks down -Z at the pivot, +X right, +Y up. Turned 0 and tilted 0, the gun lies
//! along +X (muzzle to the right) with its right side (glTF -X) toward the camera.

use super::model::Draft;
use super::popover::preview_part;
use super::ui_data::{GunPreviewSpec, LoadoutUiData, TagSide};
use super::view::Hotspot;
use super::{LoadoutEdit, LoadoutUi, PopPanel};
use crate::config::Data;
use crate::weapon_models::{Assembling, GunKey, WeaponModels};
use bevy::app::Propagate;
use bevy::asset::RenderAssetUsages;
use bevy::camera::RenderTarget;
use bevy::camera::primitives::Aabb;
use bevy::camera::visibility::RenderLayers;
use bevy::input::mouse::{AccumulatedMouseScroll, MouseScrollUnit};
use bevy::prelude::*;
use bevy::render::render_resource::{TextureDimension, TextureFormat, TextureUsages};
use bevy::ui::RelativeCursorPosition;
use bevy::ui::widget::ViewportNode;
use bevy::window::PrimaryWindow;
use std::f32::consts::{FRAC_PI_2, TAU};
use vetf_sim::GameData;
use vetf_sim::data::{AttachmentCategory, AttachmentSpec};

/// The render layer only the preview's camera, lights and gun are on.
pub const PREVIEW_LAYER: usize = 7;
/// Where the preview's stage stands: far below every map, so nothing of it is ever near the match's view.
const STAGE_AT: Vec3 = Vec3::new(0.0, -5000.0, 0.0);
/// The camera's near plane (m).
const NEAR: f32 = 0.05;

/// The UI node that shows the preview's camera (the box behind the hotspots).
#[derive(Component)]
pub struct PreviewViewport;

/// A studio light of the preview (the match's light settings leave it alone).
#[derive(Component)]
pub struct StudioLight;

/// A hotspot placed on its slot's socket: it follows the gun as it turns.
#[derive(Component, Debug, Clone, Copy)]
pub struct HotspotAt {
    pub slot: AttachmentCategory,
    pub side: TagSide,
}

/// How the gun is turned and zoomed (radians; zoom 1 = the framing of `fill`).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Pose {
    /// About the view's up axis; + turns the side toward the camera to the right.
    pub turn: f32,
    /// About the view's right axis; + tips the top toward the camera.
    pub tilt: f32,
    pub zoom: f32,
}

impl Pose {
    /// The default three-quarter view: the muzzle turned `yaw_deg` toward the viewer, the top `pitch_deg` up.
    pub fn default_view(spec: &GunPreviewSpec) -> Pose {
        Pose { turn: -spec.yaw_deg.to_radians(), tilt: spec.pitch_deg.to_radians(), zoom: 1.0 }
    }

    /// A drag of `delta` UI px: the side under the cursor follows it (all the way round, the tilt limited).
    pub fn drag(&mut self, delta: Vec2, spec: &GunPreviewSpec) {
        let k = spec.drag_deg_per_px.to_radians();
        self.turn = (self.turn + delta.x * k).rem_euclid(TAU);
        let lim = spec.pitch_limit_deg.to_radians().abs();
        self.tilt = (self.tilt + delta.y * k).clamp(-lim, lim);
    }

    /// `notches` of the wheel (+ away from you: zoom in).
    pub fn scroll(&mut self, notches: f32, spec: &GunPreviewSpec) {
        let (lo, hi) = spec.zoom;
        self.zoom = (self.zoom * (1.0 + notches * spec.zoom_per_notch)).clamp(lo.min(hi), hi.max(lo));
    }

    /// The gun's turn in view space (glTF gun axes: muzzle +Z, up +Y, its right -X).
    pub fn rotation(&self) -> Quat {
        Quat::from_rotation_x(self.tilt) * Quat::from_rotation_y(self.turn + FRAC_PI_2)
    }
}

/// The attachment ids the preview shows: the draft's parts, with the part of a hovered popover row in its slot
/// (`None` = that slot empty).
pub fn preview_attachments(
    draft: &Draft,
    preview: Option<(AttachmentCategory, Option<&AttachmentSpec>)>,
    data: &GameData,
) -> Vec<String> {
    let mut ids: Vec<String> = draft.equipped_all(data).iter().map(|a| a.id.clone()).collect();
    if let Some((cat, part)) = preview {
        ids.retain(|id| data.attachment(id).is_none_or(|a| a.cat != cat));
        ids.extend(part.map(|a| a.id.clone()));
    }
    ids
}

/// The camera's distance from the pivot that makes a gun of `radius` (half its longest side) fill `fill` of the
/// width of a view `aspect` wide (to 1 high) with a vertical field of view of `fov` (radians).
pub fn camera_distance(radius: f32, fov: f32, aspect: f32, fill: f32) -> f32 {
    radius / ((fov * 0.5).tan() * aspect.max(0.01) * fill.max(0.01))
}

/// Where a point (view axes, from the pivot) shows in the preview: 0..1 across and down. None behind the camera.
pub fn project(p: Vec3, distance: f32, fov: f32, aspect: f32) -> Option<Vec2> {
    let view = p - Vec3::Z * distance;
    if view.z > -NEAR {
        return None;
    }
    let clip = Mat4::perspective_infinite_reverse_rh(fov, aspect, NEAR) * view.extend(1.0);
    let ndc = clip.truncate() / clip.w;
    Some(Vec2::new((ndc.x + 1.0) * 0.5, (1.0 - ndc.y) * 0.5))
}

/// A gun's bounds in its own space: the centre and half its longest side.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Frame {
    pub center: Vec3,
    pub radius: f32,
}

impl Frame {
    /// Eases toward `to` by `k` (0..1), landing on it once within a tenth of a millimetre.
    fn toward(&mut self, to: Frame, k: f32) {
        self.center = self.center.lerp(to.center, k);
        self.radius += (to.radius - self.radius) * k;
        if self.center.distance(to.center) < 1e-4 && (self.radius - to.radius).abs() < 1e-4 {
            *self = to;
        }
    }
}

/// The preview while the screen shows it.
#[derive(Resource)]
pub struct GunPreview {
    viewport: Entity,
    stage: Entity,
    camera: Entity,
    pivot: Entity,
    /// Holds a gun being assembled, hidden.
    staging: Entity,
    shown: Option<(GunKey, Entity)>,
    pending: Option<(GunKey, Entity)>,
    pub pose: Pose,
    /// The zoom the view eases to.
    zoom_to: f32,
    frame: Option<Frame>,
    frame_to: Option<Frame>,
    /// The cursor of the drag in progress (UI px).
    drag: Option<Vec2>,
    /// Where each slot's socket shows (UI px in the preview box), while a model is shown.
    pub spots: Vec<(AttachmentCategory, Vec2)>,
    /// The draft's gun has a model (shown, or being built): no 2D picture.
    pub has_model: bool,
}

impl GunPreview {
    /// A model is shown (the 2D picture is not needed).
    pub fn live(&self) -> bool {
        self.shown.is_some() && self.frame.is_some()
    }

    pub fn spot(&self, slot: AttachmentCategory) -> Option<Vec2> {
        self.spots.iter().find(|(s, _)| *s == slot).map(|(_, p)| *p)
    }
}

/// The preview box appeared: its camera (into an image the box shows), lights and stage.
pub fn setup(
    mut commands: Commands,
    boxes: Query<Entity, (With<PreviewViewport>, Without<ViewportNode>)>,
    existing: Option<Res<GunPreview>>,
    ui: Res<LoadoutUiData>,
    mut images: ResMut<Assets<Image>>,
) {
    let Some(viewport) = boxes.iter().next() else { return };
    if existing.is_some() {
        return;
    }
    let spec = &ui.ui.gun_preview;
    // Sized to the box by `update_viewport_render_target_size`.
    let mut image =
        Image::new_uninit(default(), TextureDimension::D2, TextureFormat::Bgra8UnormSrgb, RenderAssetUsages::all());
    image.texture_descriptor.usage =
        TextureUsages::TEXTURE_BINDING | TextureUsages::COPY_DST | TextureUsages::RENDER_ATTACHMENT;
    let image = images.add(image);
    let layer = RenderLayers::layer(PREVIEW_LAYER);
    let stage = commands
        .spawn((
            Name::new("gun preview"),
            Transform::from_translation(STAGE_AT),
            Visibility::Visible,
            Propagate(layer.clone()),
        ))
        .id();
    let camera = commands
        .spawn((
            Name::new("gun preview camera"),
            Camera3d::default(),
            // Before the window's cameras; the clear is transparent, so the box's own background shows.
            Camera { order: -10, clear_color: ClearColorConfig::Custom(Color::NONE), ..default() },
            RenderTarget::Image(image.into()),
            Projection::Perspective(PerspectiveProjection { fov: spec.fov_deg.to_radians(), near: NEAR, ..default() }),
            AmbientLight { color: Color::WHITE, brightness: spec.ambient, affects_lightmapped_meshes: false },
            Msaa::Sample4,
            Transform::from_xyz(0.0, 0.0, 1.0),
            layer,
            ChildOf(stage),
        ))
        .id();
    for l in &spec.lights {
        let (yaw, pitch) = (l.yaw_deg.to_radians(), l.pitch_deg.to_radians());
        let from = Vec3::new(yaw.sin() * pitch.cos(), pitch.sin(), yaw.cos() * pitch.cos());
        commands.spawn((
            StudioLight,
            DirectionalLight {
                color: Color::linear_rgb(l.rgb.0, l.rgb.1, l.rgb.2),
                illuminance: l.lux,
                shadow_maps_enabled: false,
                ..default()
            },
            Transform::from_translation(from).looking_at(Vec3::ZERO, Vec3::Y),
            ChildOf(stage),
        ));
    }
    let pose = Pose::default_view(spec);
    let pivot = commands.spawn((Transform::from_rotation(pose.rotation()), Visibility::Inherited, ChildOf(stage))).id();
    let staging = commands.spawn((Transform::default(), Visibility::Hidden, ChildOf(stage))).id();
    commands.entity(viewport).insert(ViewportNode::new(camera));
    commands.insert_resource(GunPreview {
        viewport,
        stage,
        camera,
        pivot,
        staging,
        shown: None,
        pending: None,
        pose,
        zoom_to: 1.0,
        frame: None,
        frame_to: None,
        drag: None,
        spots: Vec::new(),
        has_model: false,
    });
}

/// The preview box is gone (the screen closed): the camera, the lights and the guns go with it.
pub fn teardown(mut commands: Commands, preview: Option<Res<GunPreview>>, boxes: Query<(), With<PreviewViewport>>) {
    let Some(p) = preview else { return };
    if boxes.contains(p.viewport) {
        return;
    }
    commands.entity(p.stage).try_despawn();
    commands.remove_resource::<GunPreview>();
}

/// Drag in the box to turn the gun; the wheel zooms. Not over the hotspots or the popover.
#[allow(clippy::too_many_arguments)]
pub fn drag_and_zoom(
    mouse: Res<ButtonInput<MouseButton>>,
    scroll: Res<AccumulatedMouseScroll>,
    windows: Query<&Window, With<PrimaryWindow>>,
    scale: Res<UiScale>,
    boxes: Query<&RelativeCursorPosition, With<PreviewViewport>>,
    panels: Query<&RelativeCursorPosition, With<PopPanel>>,
    hotspots: Query<&Interaction, With<Hotspot>>,
    (st, ui): (Res<LoadoutUi>, Res<LoadoutUiData>),
    mut p: ResMut<GunPreview>,
) {
    let spec = &ui.ui.gun_preview;
    let cursor = windows.iter().next().and_then(|w| w.cursor_position()).map(|c| c / scale.0.max(1e-3));
    let over = boxes.get(p.viewport).is_ok_and(|r| r.cursor_over())
        && !panels.iter().any(|r| r.cursor_over())
        && hotspots.iter().all(|i| *i == Interaction::None)
        && st.drag.is_none();
    if !mouse.pressed(MouseButton::Left) {
        p.drag = None;
    } else if mouse.just_pressed(MouseButton::Left) && over {
        p.drag = cursor;
    }
    if let (Some(last), Some(now)) = (p.drag, cursor) {
        if now != last {
            p.pose.drag(now - last, spec);
        }
        p.drag = Some(now);
    }
    if over && scroll.delta.y != 0.0 {
        let notches = match scroll.unit {
            MouseScrollUnit::Line => scroll.delta.y,
            MouseScrollUnit::Pixel => scroll.delta.y / spec.pixels_per_notch.max(1.0),
        };
        let mut to = Pose { zoom: p.zoom_to, ..p.pose };
        to.scroll(notches, spec);
        p.zoom_to = to.zoom;
    }
}

/// Builds the gun the draft (or the hovered row) asks for, hidden, and swaps it in once it is complete.
#[allow(clippy::too_many_arguments)]
pub fn sync_gun(
    mut commands: Commands,
    models: Res<WeaponModels>,
    data: Res<Data>,
    ui: Res<LoadoutUiData>,
    edit: Res<LoadoutEdit>,
    st: Res<LoadoutUi>,
    mut p: ResMut<GunPreview>,
    (assembling, tree, meshes, roots): (
        Query<(), With<Assembling>>,
        Query<&Children>,
        Query<(Option<&Aabb>, &GlobalTransform), With<Mesh3d>>,
        Query<&GlobalTransform>,
    ),
) {
    let preview = preview_part(&edit.draft, st.pop, st.hover_row.or(st.focus_row), &data, &ui);
    let ids = preview_attachments(&edit.draft, preview, &data);
    let wanted = models.data.key_for(&data, &edit.draft.weapon, &ids).filter(|k| models.loaded(k));
    let p = &mut *p;
    if p.has_model != wanted.is_some() {
        p.has_model = wanted.is_some();
    }
    let Some(key) = wanted else {
        for (_, e) in p.shown.take().into_iter().chain(p.pending.take()) {
            commands.entity(e).try_despawn();
        }
        p.frame = None;
        p.frame_to = None;
        p.spots.clear();
        return;
    };
    if p.shown.as_ref().is_some_and(|(k, _)| *k == key) {
        if let Some((_, e)) = p.pending.take() {
            commands.entity(e).try_despawn();
        }
    } else if p.pending.as_ref().is_none_or(|(k, _)| *k != key) {
        if let Some((_, e)) = p.pending.take() {
            commands.entity(e).try_despawn();
        }
        p.pending = models.spawn(&mut commands, p.staging, &key, Transform::IDENTITY, false).map(|e| (key, e));
    }
    // The new gun is complete (every part in, bounds known): it takes the old one's place.
    let Some((_, gun)) = p.pending.as_ref() else { return };
    let gun = *gun;
    if assembling.contains(gun) {
        return;
    }
    let Some(frame) = bounds(gun, &tree, &meshes, &roots) else { return };
    let Some(next) = p.pending.take() else { return };
    if let Some((_, old)) = p.shown.replace(next) {
        commands.entity(old).try_despawn();
    }
    commands.entity(gun).insert((ChildOf(p.pivot), Transform::from_translation(-p.frame.unwrap_or(frame).center)));
    p.frame_to = Some(frame);
    p.frame.get_or_insert(frame);
}

/// A gun's bounds in its own space, once every mesh of it has its bounds (None before, or with no mesh).
fn bounds(
    gun: Entity,
    tree: &Query<&Children>,
    meshes: &Query<(Option<&Aabb>, &GlobalTransform), With<Mesh3d>>,
    roots: &Query<&GlobalTransform>,
) -> Option<Frame> {
    let inverse = roots.get(gun).ok()?.affine().inverse();
    let (mut lo, mut hi) = (Vec3::splat(f32::MAX), Vec3::splat(f32::MIN));
    let mut any = false;
    for e in tree.iter_descendants(gun) {
        let Ok((aabb, at)) = meshes.get(e) else { continue };
        let aabb = aabb?;
        let local = inverse * at.affine();
        let (c, h) = (Vec3::from(aabb.center), Vec3::from(aabb.half_extents));
        for i in 0..8 {
            let corner = c + h * Vec3::new([-1.0, 1.0][i & 1], [-1.0, 1.0][(i >> 1) & 1], [-1.0, 1.0][i >> 2]);
            let q = local.transform_point3(corner);
            lo = lo.min(q);
            hi = hi.max(q);
        }
        any = true;
    }
    any.then(|| Frame { center: (lo + hi) * 0.5, radius: ((hi - lo).max_element() * 0.5).max(0.05) })
}

/// Turns the gun, eases the framing and the zoom, places the camera, and finds where each socket shows.
#[allow(clippy::too_many_arguments)]
pub fn pose(
    time: Res<Time>,
    models: Res<WeaponModels>,
    data: Res<Data>,
    ui: Res<LoadoutUiData>,
    boxes: Query<&ComputedNode, With<PreviewViewport>>,
    mut places: Query<&mut Transform>,
    mut p: ResMut<GunPreview>,
) {
    let spec = &ui.ui.gun_preview;
    let p = &mut *p;
    let k = 1.0 - (-time.delta_secs() / spec.settle_s.max(1e-3)).exp();
    if let (Some(f), Some(to)) = (p.frame.as_mut(), p.frame_to) {
        f.toward(to, k);
    }
    p.pose.zoom += (p.zoom_to - p.pose.zoom) * k;
    if (p.zoom_to - p.pose.zoom).abs() < 1e-4 {
        p.pose.zoom = p.zoom_to;
    }
    let rotation = p.pose.rotation();
    // Only real changes: an unchanged pose leaves the gun's transforms alone.
    if let Ok(mut t) = places.get_mut(p.pivot) {
        t.set_if_neq(Transform::from_rotation(rotation));
    }
    p.spots.clear();
    let (Some(frame), Some((key, gun))) = (p.frame, p.shown.as_ref()) else { return };
    if let Ok(mut t) = places.get_mut(*gun) {
        t.set_if_neq(Transform::from_translation(-frame.center));
    }
    let size = boxes.get(p.viewport).map_or(Vec2::new(870.0, 428.0), |n| n.size() * n.inverse_scale_factor());
    let aspect = size.x / size.y.max(1.0);
    let fov = spec.fov_deg.to_radians();
    let distance = camera_distance(frame.radius, fov, aspect, spec.fill) / p.pose.zoom.max(0.01);
    if let Ok(mut t) = places.get_mut(p.camera) {
        t.set_if_neq(Transform::from_translation(Vec3::Z * distance));
    }
    for slot in AttachmentCategory::ALL {
        let Some(socket) = models.slot_socket(&data, key, slot) else { continue };
        if let Some(uv) = project(rotation * (socket - frame.center), distance, fov, aspect) {
            p.spots.push((slot, uv * size));
        }
    }
}

/// Keeps each hotspot on its socket as the gun turns.
pub fn place_hotspots(preview: Option<Res<GunPreview>>, mut spots: Query<(&HotspotAt, &mut Node)>) {
    let Some(p) = preview else { return };
    for (at, mut node) in &mut spots {
        let Some(xy) = p.spot(at.slot) else { continue };
        let mut next = node.clone();
        super::view::place_hotspot(&mut next, at.side, xy);
        if *node != next {
            *node = next;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::weapon_models::ModelData;
    use std::collections::BTreeMap;

    fn spec() -> GunPreviewSpec {
        LoadoutUiData::embedded().ui.gun_preview
    }

    /// The preview box's inner size (`view::spawn_root`).
    const ASPECT: f32 = 870.0 / 428.0;

    fn draft(d: &GameData, fixed: bool) -> Draft {
        let c = crate::config::loadout_choice(&crate::loadout::tests::plain_cli(), d);
        let kit = if fixed { d.rules.fixed_loadout(vetf_net::MatchMode::Tdm).cloned() } else { None };
        Draft::from_choice(&c, &BTreeMap::new(), d, kit)
    }

    /// The part ids of the model the preview builds.
    fn built(d: &GameData, draft: &Draft, preview: Option<(AttachmentCategory, Option<&str>)>) -> Option<Vec<String>> {
        let preview = preview.map(|(c, id)| (c, id.and_then(|id| d.attachment(id))));
        let ids = preview_attachments(draft, preview, d);
        let m = ModelData::embedded();
        let key = m.key_for(d, &draft.weapon, &ids)?;
        let mut parts: Vec<String> = key.parts.iter().map(|&i| m.parts[i].id.clone()).collect();
        parts.sort();
        Some(parts)
    }

    fn sorted(ids: &[&str]) -> Vec<String> {
        let mut v: Vec<String> = ids.iter().map(|s| s.to_string()).collect();
        v.sort();
        v
    }

    #[test]
    fn the_preview_builds_the_drafts_gun_with_its_parts() {
        let d = GameData::embedded();
        let draft = draft(&d, false);
        assert_eq!(draft.weapon, "ar7_mako");
        assert_eq!(built(&d, &draft, None), Some(sorted(&["optic_holo", "mako_stock_standard", "mag_30"])));
        // The draft's own picks, as the screen sets them.
        let mut picked = draft.clone();
        picked.set_part(AttachmentCategory::Under, Some("grip_angled"), &d);
        picked.set_part(AttachmentCategory::Side, Some("laser"), &d);
        picked.set_part(AttachmentCategory::Shield, Some("shield_front"), &d);
        picked.set_part(AttachmentCategory::Mag, Some("mag_drum60"), &d);
        assert_eq!(
            built(&d, &picked, None),
            Some(sorted(&["optic_holo", "mako_stock_standard", "mag_drum60", "grip_angled", "laser", "shield_front"]))
        );
    }

    #[test]
    fn a_hovered_row_puts_its_part_on_the_preview() {
        let d = GameData::embedded();
        let draft = draft(&d, false);
        // A part in an empty slot, a part in place of another, and NONE.
        let grip = built(&d, &draft, Some((AttachmentCategory::Under, Some("grip_vertical")))).unwrap();
        assert!(grip.contains(&"grip_vertical".to_string()), "{grip:?}");
        let optic = built(&d, &draft, Some((AttachmentCategory::Optic, Some("optic_3x")))).unwrap();
        assert!(optic.contains(&"optic_3x".to_string()) && !optic.contains(&"optic_holo".to_string()), "{optic:?}");
        let bare = built(&d, &draft, Some((AttachmentCategory::Optic, None))).unwrap();
        assert_eq!(bare, sorted(&["mako_stock_standard", "mag_30"]));
        // The draft itself is left alone.
        assert_eq!(built(&d, &draft, None).unwrap().len(), 3);
    }

    #[test]
    fn the_preview_always_shows_a_stock_and_a_magazine() {
        let d = GameData::embedded();
        let mut draft = draft(&d, false);
        let none_stock = built(&d, &draft, Some((AttachmentCategory::Stock, None))).unwrap();
        assert!(none_stock.contains(&"mako_stock_standard".to_string()), "the gun's default stock: {none_stock:?}");
        let none_mag = built(&d, &draft, Some((AttachmentCategory::Mag, None))).unwrap();
        assert!(none_mag.contains(&"mag_30".to_string()), "the gun's default magazine: {none_mag:?}");
        // Another gun brings its own parts.
        draft.switch_weapon("vk50_warden", &d);
        assert_eq!(built(&d, &draft, None), Some(sorted(&["optic_sniper", "warden_stock_standard", "mag_5"])));
        // A gun without a model keeps the 2D picture.
        draft.switch_weapon("sk9_skink", &d);
        assert_eq!(built(&d, &draft, None), None);
    }

    #[test]
    fn the_deathmatch_preview_shows_the_picked_magazine_type() {
        let d = GameData::embedded();
        let mut draft = draft(&d, true);
        assert!(draft.fixed.is_some());
        let mag = draft.mag_options(&d).into_iter().find(|a| a.id == "mag_45").expect("the 45 is sold").id.clone();
        draft.set_part(AttachmentCategory::Mag, Some(&mag), &d);
        let parts = built(&d, &draft, None).unwrap();
        assert!(parts.contains(&"mag_45".to_string()) && !parts.contains(&"mag_30".to_string()), "{parts:?}");
    }

    #[test]
    fn every_slot_hotspot_has_a_socket() {
        let d = GameData::embedded();
        let m = ModelData::embedded();
        for (cat, socket) in [
            (AttachmentCategory::Optic, "Optic"),
            (AttachmentCategory::Stock, "Stock"),
            (AttachmentCategory::Mag, "Mag"),
            (AttachmentCategory::Under, "Under"),
            (AttachmentCategory::Side, "Side_R"),
            (AttachmentCategory::Shield, "Shield"),
        ] {
            assert_eq!(m.slot_socket(&d, cat), Some(socket), "{cat:?}");
        }
    }

    #[test]
    fn the_default_view_is_a_three_quarter_view_of_the_right_side() {
        let s = spec();
        let r = Pose::default_view(&s).rotation();
        // Muzzle (+Z) to the right of the stock end, and turned toward the viewer.
        let (muzzle, stock) = (r * Vec3::Z, r * Vec3::NEG_Z);
        assert!(muzzle.x > 0.5 && muzzle.z > 0.0, "{muzzle}");
        assert!(stock.x < 0.0);
        // The gun's right side (-X) and its top face the camera.
        assert!((r * Vec3::NEG_X).z > 0.5);
        assert!((r * Vec3::Y).z > 0.0 && (r * Vec3::Y).y > 0.5);
    }

    #[test]
    fn at_zoom_one_the_gun_fills_its_share_of_the_width() {
        let s = spec();
        let fov = s.fov_deg.to_radians();
        let radius = 0.5;
        let d = camera_distance(radius, fov, ASPECT, s.fill);
        // Turned 0, tilted 0: the gun lies across the view, its ends on the pivot's plane.
        let r = Pose { turn: 0.0, tilt: 0.0, zoom: 1.0 }.rotation();
        let a = project(r * Vec3::Z * radius, d, fov, ASPECT).unwrap();
        let b = project(r * Vec3::NEG_Z * radius, d, fov, ASPECT).unwrap();
        assert!(((a.x - b.x) - s.fill).abs() < 1e-4, "{a} {b}");
        assert!((a.y - 0.5).abs() < 1e-4 && a.x > b.x);
        assert_eq!(project(Vec3::ZERO, d, fov, ASPECT), Some(Vec2::splat(0.5)));
        assert_eq!(project(Vec3::Z * (d + 1.0), d, fov, ASPECT), None, "behind the camera");
    }

    #[test]
    fn the_default_view_shows_the_whole_gun() {
        // A rifle's box (half sizes, its long side along +Z): every corner inside the preview, with a margin.
        let s = spec();
        let fov = s.fov_deg.to_radians();
        let half = Vec3::new(0.05, 0.16, 0.5);
        let d = camera_distance(half.max_element(), fov, ASPECT, s.fill);
        let r = Pose::default_view(&s).rotation();
        for i in 0..8 {
            let c = half * Vec3::new([-1.0, 1.0][i & 1], [-1.0, 1.0][(i >> 1) & 1], [-1.0, 1.0][i >> 2]);
            let uv = project(r * c, d, fov, ASPECT).unwrap();
            assert!(uv.cmpge(Vec2::splat(0.03)).all() && uv.cmple(Vec2::splat(0.97)).all(), "corner {c}: {uv}");
        }
    }

    #[test]
    fn dragging_turns_the_side_under_the_cursor_with_it() {
        let s = spec();
        let fov = s.fov_deg.to_radians();
        let mut pose = Pose::default_view(&s);
        // A point on the side facing the camera.
        let near = Vec3::new(-0.05, 0.0, 0.0);
        let at = |p: &Pose| project(p.rotation() * near, 1.5, fov, ASPECT).unwrap();
        let before = at(&pose);
        pose.drag(Vec2::new(12.0, 0.0), &s);
        assert!(at(&pose).x > before.x, "drag right: the near side moves right");
        let before = at(&pose);
        pose.drag(Vec2::new(0.0, 12.0), &s);
        assert!(at(&pose).y > before.y, "drag down: the near side moves down");
        // The tilt stops at its limit; the turn goes all the way round.
        pose.drag(Vec2::new(0.0, 1e5), &s);
        assert!((pose.tilt - s.pitch_limit_deg.to_radians()).abs() < 1e-5);
        pose.drag(Vec2::new(0.0, -1e5), &s);
        assert!((pose.tilt + s.pitch_limit_deg.to_radians()).abs() < 1e-5);
        pose.drag(Vec2::new(360.0 / s.drag_deg_per_px, 0.0), &s);
        assert!((0.0..TAU).contains(&pose.turn));
    }

    /// The camera, lights and stage exist only while the preview box does, all on the preview's own layer (a
    /// gun put on the stage later too), and the box shows the camera's picture.
    #[test]
    fn the_preview_lives_only_while_its_box_does() {
        use bevy::app::HierarchyPropagatePlugin;
        let mut app = App::new();
        app.add_plugins((AssetPlugin::default(), HierarchyPropagatePlugin::<RenderLayers>::new(PostUpdate)))
            .init_asset::<Image>()
            .insert_resource(LoadoutUiData::embedded())
            .add_systems(Update, (teardown, setup).chain());
        app.update();
        assert!(app.world().get_resource::<GunPreview>().is_none(), "no box, no preview");
        let node = app.world_mut().spawn((PreviewViewport, Node::default())).id();
        app.update();
        let (stage, camera, pivot) = {
            let p = app.world().resource::<GunPreview>();
            (p.stage, p.camera, p.pivot)
        };
        let world = app.world();
        assert_eq!(world.get::<ViewportNode>(node).and_then(|v| v.camera), Some(camera));
        let image = world.get::<RenderTarget>(camera).and_then(|t| t.as_image()).expect("draws into an image").clone();
        assert!(world.resource::<Assets<Image>>().get(&image).is_some());
        let gun = app.world_mut().spawn((Transform::default(), ChildOf(pivot))).id();
        app.update();
        let world = app.world_mut();
        let layer = RenderLayers::layer(PREVIEW_LAYER);
        assert_eq!(world.get::<RenderLayers>(camera), Some(&layer));
        assert_eq!(world.get::<RenderLayers>(gun), Some(&layer), "a gun put on the stage later");
        let mut lights = world.query_filtered::<&RenderLayers, With<DirectionalLight>>();
        let lights: Vec<&RenderLayers> = lights.iter(world).collect();
        assert_eq!(lights.len(), spec().lights.len());
        assert!(lights.iter().all(|l| **l == layer), "the studio lights light the preview only");

        app.world_mut().entity_mut(node).despawn();
        app.update();
        let world = app.world();
        assert!(world.get_resource::<GunPreview>().is_none());
        for e in [stage, camera, pivot, gun] {
            assert!(world.get_entity(e).is_err(), "despawned with the screen");
        }
    }

    #[test]
    fn the_wheel_zooms_within_its_range() {
        let s = spec();
        let mut pose = Pose::default_view(&s);
        pose.scroll(1.0, &s);
        assert!(pose.zoom > 1.0, "away from you: closer");
        pose.scroll(-3.0, &s);
        assert!(pose.zoom < 1.0);
        pose.scroll(100.0, &s);
        assert_eq!(pose.zoom, s.zoom.1);
        for _ in 0..100 {
            pose.scroll(-1.0, &s);
        }
        assert_eq!(pose.zoom, s.zoom.0);
        assert!(s.zoom.0 < 1.0 && 1.0 < s.zoom.1, "zoom 1 (the framing) is in range");
        assert!(s.fill > 0.0 && s.fill <= 1.0 && s.settle_s > 0.0 && !s.lights.is_empty());
    }
}
