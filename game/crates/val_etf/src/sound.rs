//! Sound: what plays when, through Bevy's audio (OGG Vorbis files under `game/assets/audio/`).
//!
//! `game/assets/data/sounds.ron` maps each sound id to its files (one to three variations), category, volume,
//! pitch jitter and range ([`SoundData`]). Files are named `<category>/<name>.ogg` or `<category>/<name>_<n>.ogg`
//! after the id, so real sounds go in by copying the files over and listing them in `files`. This module
//! decides when each id plays:
//!
//! - **Your own player** (never spatial): each simulation tick's events ([`LocalPlayerEvents`]: shots, reloads,
//!   mag checks, fire mode, jumps, landings, slides, mantles, items) and the trigger after the tick
//!   ([`TriggerTick`]: the dry click, once per trigger pull, [`DryFire`]); plus footsteps, the jetpack and
//!   zipline loops and the equip sound from the movement and weapon state.
//! - **Other players** (spatial at their position): the same sounds read from their replicated state as it
//!   changes (shot counter, weapon action, fire mode, trigger, movement mode, item in use). A shot past the
//!   sound's `far.beyond_m` plays the distant variant instead ([`by_distance`]).
//! - **Footsteps** follow how fast a player actually moves on the ground ([`Footsteps`]), never the keys:
//!   walking and crouching are silent, running is louder the faster it goes.
//! - **Hits** you land and take ([`FeedbackSound`], from the host's `HitConfirm` and `DamageTaken`).
//! - **Menus**: any `Button` hovered or pressed, hub screens closing, and a sample of the category when a
//!   Settings ▸ AUDIO volume slider comes to rest.
//! - **Ambience**: one loop per map while in a match.
//!
//! The AUDIO tab drives the mix: MASTER is [`GlobalVolume`], each category slider scales its sounds, SHIELD-HIT
//! and HEADSHOT switch those cues, LOW-MAG CUE adds a lighter click under shots while the magazine would check
//! ALMOST EMPTY (a mag-check band, never a count), and PLAY IN BACKGROUND mutes the game while the window is
//! not focused. Sliders map to gain as (value / 100)², so 50 sounds about half as loud.
//!
//! Scripted runs (`--screenshot`, `--demo-ui`, `--exit-after`) play every sound muted, so tests on the user's
//! desktop stay quiet, and log each sound at info level (`sound: <id> ...`); `VETF_SOUND=1` makes them audible
//! (also while the test window is in the background). `--host ... --bot --demo-ui dry-fire` empties the host's
//! magazine now and then, so the log shows shots, dry clicks, reloads and steps.

use crate::AppState;
use crate::config::{Cli, CurrentLevel, Data};
use crate::render::ViewCamera;
use crate::screens::{Screen, Screens};
use crate::settings::{AudioSettings, Settings};
use crate::shared::LocalPlayerEvents;
use crate::ui_kit::{BTN_ALLY, BTN_PRIMARY, Disabled, Looks};
use bevy::asset::LoadState;
use bevy::audio::{
    AudioPlayer, AudioSink, AudioSinkPlayback, AudioSource, DefaultSpatialScale, GlobalVolume, PlaybackMode,
    PlaybackSettings, SpatialAudioSink, SpatialListener, SpatialScale, Volume,
};
use bevy::ecs::system::SystemParam;
use bevy::prelude::*;
use bevy::window::PrimaryWindow;
use lightyear::prelude::Controlled;
use serde::Deserialize;
use std::collections::{BTreeMap, HashMap, HashSet};
use std::sync::OnceLock;
use vetf_net::{
    DamageTaken, HitConfirm, HitKind, PlayerId, PlayerItems, PlayerLoadout, PlayerMove, PlayerWeapon, Vitals,
};
use vetf_sim::Zone;
use vetf_sim::data::FireMode;
use vetf_sim::input::Buttons;
use vetf_sim::movement::MoveMode;
use vetf_sim::movement::collision::{CollisionWorld, Look};
use vetf_sim::player::PlayerEvents;
use vetf_sim::weapon::{ADS_AIMED, MagEstimate, ReloadKind, WeaponAction, WeaponEvents, WeaponState};

/// Rodio's own spatial fall-off is 1/d², far too steep for a shooter; positions are scaled down this much so it
/// never applies within a kilometre, and the fall-off comes from the data instead ([`attenuation`]). Panning
/// is unaffected by the scale.
const SPATIAL_SCALE: f32 = 0.001;

pub struct SoundPlugin;

impl Plugin for SoundPlugin {
    fn build(&self, app: &mut App) {
        let data = SoundData::load();
        for problem in data.problems() {
            warn!("sounds.ron: {problem}");
        }
        app.insert_resource(SoundBank { data, handles: HashMap::new() })
            .insert_resource(DefaultSpatialScale(SpatialScale::new(SPATIAL_SCALE)))
            .init_resource::<SoundMix>()
            .init_resource::<Ear>()
            .init_resource::<Voices>()
            .init_resource::<Delayed>()
            .add_message::<FeedbackSound>()
            .add_systems(Startup, (load_sounds, setup_mix))
            .add_systems(
                Update,
                (
                    (follow_listener, apply_mix),
                    (player_sounds, feedback_sounds, ui_sounds, preview_volume, ambience, play_delayed),
                    update_voices,
                )
                    .chain(),
            )
            .add_systems(Update, demo_dry_fire.run_if(in_state(AppState::InGame)).run_if(demo_is_dry_fire));
    }
}

// ---------------------------------------------------------------------------------------------- data

/// Which AUDIO tab slider scales a sound. `Ambient` has none (the mockup has no ambience slider): MASTER only.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
pub enum Category {
    Weapons,
    Movement,
    Abilities,
    Hits,
    Interface,
    Music,
    Ambient,
}

fn one() -> f32 {
    1.0
}

fn default_ref_m() -> f32 {
    2.0
}

fn default_max_m() -> f32 {
    40.0
}

/// One sound id in `sounds.ron`.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct SoundSpec {
    /// Variations, relative to `game/assets/audio/`.
    pub files: Vec<String>,
    pub category: Category,
    #[serde(default = "one")]
    pub volume: f32,
    #[serde(default = "one")]
    pub pitch: f32,
    #[serde(default)]
    pub pitch_jitter: f32,
    #[serde(default)]
    pub spatial: bool,
    #[serde(default = "default_ref_m")]
    pub ref_distance_m: f32,
    #[serde(default = "default_max_m")]
    pub max_distance_m: f32,
    #[serde(default)]
    pub looped: bool,
    #[serde(default)]
    pub far: Option<FarSound>,
}

/// Past `beyond_m` the `sound` id plays instead (a gunshot's distant crack).
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct FarSound {
    pub sound: String,
    pub beyond_m: f32,
}

/// The sounds of one gun.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct WeaponSounds {
    pub shot: String,
    /// Worked `bolt_delay_s` after each shot (bolt guns).
    #[serde(default)]
    pub bolt: Option<String>,
    #[serde(default)]
    pub bolt_delay_s: f32,
    /// The bolt is also worked after a reload from empty (the round has to be chambered).
    #[serde(default)]
    pub bolt_after_empty_reload: bool,
}

/// Footstep sounds per surface, and how fast and loud steps come at a ground speed.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Footsteps {
    pub concrete: String,
    pub grass: String,
    pub gravel: String,
    pub wood: String,
    /// Slower than this on the ground makes no steps: walking and crouching are silent.
    pub silent_below_mps: f32,
    pub cadence_base_hz: f32,
    pub cadence_per_mps: f32,
    pub cadence_max_hz: f32,
    /// Starting to run: the first step comes after (1 - this) of a step.
    pub first_step_phase: f32,
    /// Step volume: `quiet_volume` just above the silent speed, rising to `loud_volume` at `loud_mps`.
    pub quiet_volume: f32,
    pub loud_volume: f32,
    pub loud_mps: f32,
    /// Your own steps are this much quieter than another player's right next to you.
    pub own_volume: f32,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Moves {
    pub jump_min_up_mps: f32,
    pub land_min_air_s: f32,
    pub mantle_volume: f32,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct UiSounds {
    pub hover_gap_s: f32,
    pub back_words: Vec<String>,
    pub confirm_words: Vec<String>,
    /// Settings ▸ AUDIO: once a volume slider has rested this long after a change, its sample plays.
    pub preview_rest_s: f32,
    /// The sample per volume slider, in the tab's order: master, weapons, movement, abilities, hits, interface,
    /// music.
    pub previews: [Option<String>; 7],
}

/// `game/assets/data/sounds.ron`.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct SoundData {
    pub sounds: BTreeMap<String, SoundSpec>,
    pub weapons: BTreeMap<String, WeaponSounds>,
    pub default_weapon: WeaponSounds,
    /// Another player's shots heard in one frame play at most this many times (spaced by the fire interval).
    pub max_heard_shots_per_frame: u32,
    pub footsteps: Footsteps,
    pub moves: Moves,
    pub ambience: BTreeMap<String, String>,
    pub shield_hit_pitch: [f32; 4],
    /// The shield tink of your own arc under the damage sound, this much quieter than the shooter hears it.
    pub own_shield_hit_volume: f32,
    pub ui: UiSounds,
    pub ear_gap_m: f32,
}

const EMBEDDED: &str = include_str!("../../../assets/data/sounds.ron");

impl SoundData {
    /// The copy compiled into the binary.
    pub fn embedded() -> &'static SoundData {
        static DATA: OnceLock<SoundData> = OnceLock::new();
        DATA.get_or_init(|| ron::from_str(EMBEDDED).expect("game/assets/data/sounds.ron is valid"))
    }

    /// From the data folder (so it can be tuned without a rebuild), else the built-in copy.
    pub fn load() -> SoundData {
        let path = crate::config::assets_root().join("data").join("sounds.ron");
        match std::fs::read_to_string(&path).map(|text| ron::from_str(&text)) {
            Ok(Ok(d)) => d,
            Ok(Err(e)) => {
                error!("{} is invalid ({e}); using the built-in copy", path.display());
                Self::embedded().clone()
            }
            Err(_) => Self::embedded().clone(),
        }
    }

    /// The sounds of a weapon id.
    pub fn weapon(&self, id: &str) -> &WeaponSounds {
        self.weapons.get(id).unwrap_or(&self.default_weapon)
    }

    /// Every sound id the data or the code refers to.
    pub fn references(&self) -> Vec<&str> {
        let f = &self.footsteps;
        let mut ids: Vec<&str> = cue::ALL.to_vec();
        ids.extend([f.concrete.as_str(), &f.grass, &f.gravel, &f.wood]);
        for w in self.weapons.values().chain([&self.default_weapon]) {
            ids.push(&w.shot);
            ids.extend(w.bolt.as_deref());
        }
        ids.extend(self.ambience.values().map(String::as_str));
        ids.extend(self.sounds.values().filter_map(|s| s.far.as_ref().map(|f| f.sound.as_str())));
        ids.extend(self.ui.previews.iter().flatten().map(String::as_str));
        ids
    }

    /// What is wrong with the data: ids referred to but not defined, sounds without files, bad ranges.
    pub fn problems(&self) -> Vec<String> {
        let mut out = Vec::new();
        for id in self.references() {
            if !self.sounds.contains_key(id) {
                out.push(format!("no sound \"{id}\""));
            }
        }
        for (id, s) in &self.sounds {
            if s.files.is_empty() {
                out.push(format!("\"{id}\" has no files"));
            }
            if s.spatial && s.max_distance_m <= s.ref_distance_m {
                out.push(format!("\"{id}\": max_distance_m must be past ref_distance_m"));
            }
            if let Some(far) = &s.far
                && self.sounds.get(&far.sound).is_some_and(|f| f.far.is_some())
            {
                out.push(format!("\"{id}\": its far sound \"{}\" has a far sound itself", far.sound));
            }
        }
        out
    }

    /// The sound id of footsteps on a surface.
    pub fn step(&self, s: Surface) -> &str {
        let f = &self.footsteps;
        match s {
            Surface::Concrete => &f.concrete,
            Surface::Grass => &f.grass,
            Surface::Gravel => &f.gravel,
            Surface::Wood => &f.wood,
        }
    }
}

/// The sound ids the code plays by name (the data maps each to files).
pub mod cue {
    pub const DRY_FIRE: &str = "weapons/dry_fire";
    pub const LOW_MAG: &str = "weapons/low_mag_click";
    pub const MAG_OUT: &str = "weapons/mag_out";
    pub const MAG_IN: &str = "weapons/mag_in";
    pub const FIRE_MODE: &str = "weapons/fire_mode";
    pub const MAG_CHECK: &str = "weapons/mag_check";
    pub const EQUIP: &str = "weapons/equip";
    pub const JUMP: &str = "movement/jump";
    pub const LAND: &str = "movement/land";
    pub const SLIDE: &str = "movement/slide";
    pub const JETPACK: &str = "movement/jetpack";
    pub const ZIPLINE: &str = "movement/zipline";
    pub const HIT_FLESH: &str = "combat/hit_flesh";
    pub const HIT_HEAD: &str = "combat/hit_head";
    pub const SHIELD_HIT: &str = "combat/shield_hit";
    pub const SHIELD_BREAK: &str = "combat/shield_break";
    pub const KILL: &str = "combat/kill";
    pub const DAMAGE_TAKEN: &str = "combat/damage_taken";
    pub const HEAL: &str = "items/heal";
    pub const UI_CLICK: &str = "ui/click";
    pub const UI_HOVER: &str = "ui/hover";
    pub const UI_CONFIRM: &str = "ui/confirm";
    pub const UI_BACK: &str = "ui/back";

    pub const ALL: [&str; 23] = [
        DRY_FIRE,
        LOW_MAG,
        MAG_OUT,
        MAG_IN,
        FIRE_MODE,
        MAG_CHECK,
        EQUIP,
        JUMP,
        LAND,
        SLIDE,
        JETPACK,
        ZIPLINE,
        HIT_FLESH,
        HIT_HEAD,
        SHIELD_HIT,
        SHIELD_BREAK,
        KILL,
        DAMAGE_TAKEN,
        HEAL,
        UI_CLICK,
        UI_HOVER,
        UI_CONFIRM,
        UI_BACK,
    ];
}

// ---------------------------------------------------------------------------------------------- maths

/// What footsteps sound like underfoot.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Surface {
    Concrete,
    Grass,
    Gravel,
    Wood,
}

/// The surface of a floor look: Ground is grass, Gravel gravel, Floor (indoor boards) wood, the rest concrete.
pub fn surface_of(look: Look) -> Surface {
    match look {
        Look::Ground => Surface::Grass,
        Look::Gravel => Surface::Gravel,
        Look::Floor => Surface::Wood,
        _ => Surface::Concrete,
    }
}

/// The look of the walkable brush under a player's feet (the highest one containing a point just below
/// them), if any. Invisible clips are skipped, so a player on one hears the floor's default.
pub fn look_under(world: &CollisionWorld, feet: Vec3) -> Option<Look> {
    const EPS: f32 = 0.02;
    let p = feet - Vec3::Y * 0.05;
    world
        .brushes
        .iter()
        .filter(|b| b.blocks_players() && b.look != Look::Invisible)
        .filter(|b| p.cmpge(b.min - EPS).all() && p.cmple(b.max + EPS).all())
        .filter(|b| b.planes.iter().all(|pl| pl.normal.dot(p) <= pl.dist + EPS))
        .max_by(|a, b| a.max.y.total_cmp(&b.max.y))
        .map(|b| b.look)
}

impl Footsteps {
    /// Steps per second at a horizontal ground speed: none below the silent speed (standing, walking,
    /// crouching), then faster with speed up to a cap.
    pub fn cadence_hz(&self, speed: f32) -> f32 {
        if speed < self.silent_below_mps {
            return 0.0;
        }
        (self.cadence_base_hz + self.cadence_per_mps * speed).min(self.cadence_max_hz)
    }

    /// A step's volume factor at a ground speed (above the silent speed): louder the faster you run.
    pub fn volume(&self, speed: f32) -> f32 {
        let span = (self.loud_mps - self.silent_below_mps).max(1e-3);
        let t = ((speed - self.silent_below_mps) / span).clamp(0.0, 1.0);
        self.quiet_volume + (self.loud_volume - self.quiet_volume) * t
    }
}

/// Advance a footstep clock (one step per whole phase) by `dt` at `hz` steps per second. True when a foot
/// lands. While no steps come the clock rests at `first`, so the first step comes `1 - first` steps in.
pub fn step_clock(phase: &mut f32, hz: f32, dt: f32, first: f32) -> bool {
    if hz <= 0.0 {
        *phase = first;
        return false;
    }
    *phase += hz * dt;
    if *phase >= 1.0 {
        *phase = phase.fract();
        return true;
    }
    false
}

/// The trigger and the gun after one simulation tick (or one look at another player's replicated state).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct TriggerTick {
    /// FIRE is held.
    pub held: bool,
    /// The gun fires while FIRE is held (an automatic), rather than once per press (semi, bolt).
    pub auto: bool,
    /// The gun is up, ready and cooled down, so it would fire now, but the magazine in it is empty.
    pub empty_ready: bool,
}

impl TriggerTick {
    pub fn of(w: &WeaponState) -> Self {
        TriggerTick {
            held: w.prev_buttons.held(Buttons::FIRE),
            auto: w.fire_mode == FireMode::Auto,
            empty_ready: w.mag() == 0 && w.is_ready() && w.cooldown == 0 && w.sprint_lock == 0,
        }
    }
}

/// The dry click: once per trigger pull, never once per tick while FIRE is held.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct DryFire {
    clicked: bool,
}

impl DryFire {
    /// One look at the trigger: true when this pull clicks. `tries_empty` is the gun trying to fire with
    /// nothing in it; the pull clicks the first time, and again only after FIRE is let go.
    pub fn step(&mut self, held: bool, tries_empty: bool) -> bool {
        let click = held && tries_empty && !self.clicked;
        self.clicked = held && (self.clicked || click);
        click
    }

    /// Your own gun after one tick: a press with an empty magazine (the simulation's `dry_fire`), or an
    /// automatic held on into an empty one (it ran dry mid-burst) once it would fire again.
    pub fn local(&mut self, ev: &WeaponEvents, t: TriggerTick) -> bool {
        self.step(t.held, ev.dry_fire || (t.auto && t.empty_ready))
    }

    /// Another player's gun, read from their state: the trigger held while it would fire but is empty.
    pub fn remote(&mut self, t: TriggerTick) -> bool {
        self.step(t.held, t.empty_ready)
    }
}

/// Which sound plays for `id` heard from `distance` metres: past the sound's `far.beyond_m`, its far variant.
pub fn by_distance<'a>(data: &'a SoundData, id: &'a str, distance: Option<f32>) -> &'a str {
    match (data.sounds.get(id).and_then(|s| s.far.as_ref()), distance) {
        (Some(far), Some(d)) if d > far.beyond_m && data.sounds.contains_key(&far.sound) => &far.sound,
        _ => id,
    }
}

/// The gain on a far variant that keeps the hand-over smooth: at `beyond_m` the distant crack is as loud as
/// the near shot there, so a heavy rifle stays louder far away than an SMG.
pub fn handover_gain(near: &SoundSpec, far: &SoundSpec, beyond_m: f32) -> f32 {
    let n = near.volume * attenuation(beyond_m, near.ref_distance_m, near.max_distance_m);
    let f = far.volume * attenuation(beyond_m, far.ref_distance_m, far.max_distance_m);
    if f > 0.0 { n / f } else { 1.0 }
}

/// How many of `new_shots` shots heard in one frame play (the rest would only stack up on the same instant).
pub fn heard_shots(new_shots: u32, cap: u32) -> u32 {
    // A counter that went backwards (a respawn) or jumped far (a missed update) plays nothing.
    if new_shots >= 64 { 0 } else { new_shots.min(cap) }
}

/// The shield tink's pitch for the tier (1..=4) of the arc that was hit.
pub fn shield_pitch(table: &[f32; 4], tier: u8) -> f32 {
    table[(tier.clamp(1, 4) - 1) as usize]
}

/// Distance fall-off: full volume up to `reference`, silent from `max`, quadratic between.
pub fn attenuation(d: f32, reference: f32, max: f32) -> f32 {
    if d <= reference {
        return 1.0;
    }
    if d >= max || max <= reference {
        return 0.0;
    }
    let t = 1.0 - (d - reference) / (max - reference);
    t * t
}

/// A 0..100 slider as a gain: (v / 100)², roughly even steps in loudness.
pub fn slider_gain(v: f32) -> f32 {
    let x = (v / 100.0).clamp(0.0, 1.0);
    x * x
}

/// The volume sliders in the AUDIO tab's order: master, weapons, movement, abilities, hits, interface, music.
pub fn sliders(a: &AudioSettings) -> [f32; 7] {
    [a.master, a.weapons, a.movement, a.abilities, a.hits, a.interface, a.music]
}

/// The category slider's gain.
pub fn category_gain(c: Category, a: &AudioSettings) -> f32 {
    match c {
        Category::Weapons => slider_gain(a.weapons),
        Category::Movement => slider_gain(a.movement),
        Category::Abilities => slider_gain(a.abilities),
        Category::Hits => slider_gain(a.hits),
        Category::Interface => slider_gain(a.interface),
        Category::Music => slider_gain(a.music),
        Category::Ambient => 1.0,
    }
}

/// MASTER as a gain, or nothing while the window is in the background and PLAY IN BACKGROUND is off.
pub fn master_gain(a: &AudioSettings, focused: bool) -> f32 {
    if focused || a.play_in_background { slider_gain(a.master) } else { 0.0 }
}

/// A variation index (`r` is a random number): never the last one again when there is a choice.
pub fn pick_variation(n: usize, last: Option<usize>, r: u64) -> usize {
    match (n, last) {
        (0 | 1, _) => 0,
        (n, Some(l)) if l < n => (l + 1 + (r % (n as u64 - 1)) as usize) % n,
        (n, _) => (r % n as u64) as usize,
    }
}

/// The interface sound of a button press, from its label and whether it is a primary button.
pub fn press_cue(label: &str, primary: bool, ui: &UiSounds) -> &'static str {
    let first = label.split_whitespace().next().unwrap_or("").to_ascii_uppercase();
    if ui.back_words.contains(&first) {
        cue::UI_BACK
    } else if primary || ui.confirm_words.contains(&first) {
        cue::UI_CONFIRM
    } else {
        cue::UI_CLICK
    }
}

/// What the shooter hears for a confirmed hit: a kill confirm, a headshot or flesh hit, the shield tink and
/// break. SHIELD-HIT SOUND off drops the tink, HEADSHOT SOUND off plays a head hit as a flesh hit.
pub fn hit_cues(h: &HitConfirm, shield_tink: bool, headshot: bool) -> Vec<&'static str> {
    let head = h.zone == Zone::Head && headshot;
    let mut out = Vec::new();
    match h.kind {
        HitKind::Kill => {
            out.push(cue::KILL);
            if head {
                out.push(cue::HIT_HEAD);
            }
        }
        HitKind::Shield => {
            if shield_tink {
                out.push(cue::SHIELD_HIT);
            }
        }
        HitKind::Health => out.push(if head { cue::HIT_HEAD } else { cue::HIT_FLESH }),
    }
    if h.shield_broke {
        out.push(cue::SHIELD_BREAK);
    }
    out
}

/// LOW-MAG CUE: on while the magazine would check ALMOST EMPTY (or the shot just emptied it). Tied to the mag
/// check's bands, so it tells no more than a mag check would.
pub fn low_mag(rounds: u16, capacity: u16) -> bool {
    matches!(MagEstimate::from_rounds(rounds, capacity), MagEstimate::AlmostEmpty | MagEstimate::Empty)
}

/// A jump: off the ground (or a slide) and going up.
pub fn jumped(prev: MoveMode, now: MoveMode, up_speed: f32, moves: &Moves) -> bool {
    matches!(prev, MoveMode::Ground | MoveMode::Slide) && now == MoveMode::Air && up_speed >= moves.jump_min_up_mps
}

/// A landing: back on the ground (or straight into a slide) after long enough in the air.
pub fn landed(prev: MoveMode, now: MoveMode, air_s: f32, moves: &Moves) -> bool {
    matches!(prev, MoveMode::Air | MoveMode::Jetpack)
        && matches!(now, MoveMode::Ground | MoveMode::Slide)
        && air_s >= moves.land_min_air_s
}

/// The weapon action without its timers.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
enum ActionKind {
    #[default]
    Ready,
    Equipping,
    Reloading(ReloadKind),
    MagChecking,
}

impl ActionKind {
    fn of(a: &WeaponAction) -> Self {
        match a {
            WeaponAction::Ready => Self::Ready,
            WeaponAction::Equipping { .. } => Self::Equipping,
            WeaponAction::Reloading { kind, .. } => Self::Reloading(*kind),
            WeaponAction::MagChecking { .. } => Self::MagChecking,
        }
    }
}

/// The sound of another player's weapon action changing: the magazine out when a reload starts, in when it
/// ends (and the bolt after an empty one, for guns that need it), the mag check.
fn action_cues(was: ActionKind, now: ActionKind, ws: &WeaponSounds) -> Vec<&str> {
    match (was, now) {
        (a, b) if a == b => vec![],
        (_, ActionKind::Reloading(_)) => vec![cue::MAG_OUT],
        (_, ActionKind::MagChecking) => vec![cue::MAG_CHECK],
        (ActionKind::Reloading(kind), ActionKind::Ready) => reload_done_cues(kind, ws),
        _ => vec![],
    }
}

/// A reload finishing: the magazine seated, then the bolt worked when the gun ran empty and needs it.
fn reload_done_cues(kind: ReloadKind, ws: &WeaponSounds) -> Vec<&str> {
    let mut out = vec![cue::MAG_IN];
    if kind == ReloadKind::Empty
        && ws.bolt_after_empty_reload
        && let Some(bolt) = &ws.bolt
    {
        out.push(bolt);
    }
    out
}

// ---------------------------------------------------------------------------------------------- playing

/// The data and the loaded files per sound id.
#[derive(Resource)]
pub struct SoundBank {
    pub data: SoundData,
    handles: HashMap<String, Vec<Handle<AudioSource>>>,
}

/// The mix this frame, from the AUDIO settings and the window focus.
#[derive(Resource, Debug, Clone)]
pub struct SoundMix {
    pub master: f32,
    category: HashMap<Category, f32>,
    /// Scripted runs: every sound is muted (see the module docs).
    pub muted: bool,
    /// Scripted runs with `VETF_SOUND=1`: heard although the test window has no focus.
    pub ignore_focus: bool,
    /// Log each sound at info level (scripted runs), else at debug.
    pub log: bool,
    pub shield_tink: bool,
    pub headshot: bool,
    pub low_mag_cue: bool,
}

impl Default for SoundMix {
    fn default() -> Self {
        Self {
            master: 1.0,
            category: HashMap::new(),
            muted: false,
            ignore_focus: false,
            log: false,
            shield_tink: true,
            headshot: true,
            low_mag_cue: false,
        }
    }
}

impl SoundMix {
    pub fn category(&self, c: Category) -> f32 {
        self.category.get(&c).copied().unwrap_or(1.0)
    }
}

/// Where the listener (the view camera) is, once there is one.
#[derive(Resource, Default)]
pub struct Ear {
    pub pos: Option<Vec3>,
}

/// Random numbers and the last variation per id.
#[derive(Resource)]
pub struct Voices {
    seed: u64,
    last: HashMap<String, usize>,
    warned: HashSet<String>,
}

impl Default for Voices {
    fn default() -> Self {
        Self { seed: 0x9E37_79B9_7F4A_7C15, last: HashMap::new(), warned: HashSet::new() }
    }
}

impl Voices {
    /// xorshift64*.
    fn next(&mut self) -> u64 {
        let mut x = self.seed;
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        self.seed = x;
        x.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }

    /// Uniform in -1..1.
    fn signed(&mut self) -> f32 {
        (self.next() >> 40) as f32 / (1u64 << 24) as f32 * 2.0 - 1.0
    }
}

/// A playing sound.
#[derive(Component, Debug)]
pub struct Voice {
    pub id: String,
    category: Category,
    /// The data's volume times the play's.
    gain: f32,
    /// Heard from its position: (full volume within, silent from), metres.
    range: Option<(f32, f32)>,
    /// Kept at this player's feet plus a height (loops on other players).
    follow: Option<(Entity, f32)>,
    /// The volume last given to the sink.
    applied: f32,
    looped: bool,
    age: f32,
}

/// A sound to play: the id and where.
#[derive(Debug, Clone, Copy)]
pub struct Play<'a> {
    pub id: &'a str,
    /// `None` plays it as your own (never spatial).
    pub at: Option<Vec3>,
    pub volume: f32,
    pub pitch: f32,
    pub follow: Option<(Entity, f32)>,
}

impl<'a> Play<'a> {
    pub fn new(id: &'a str) -> Self {
        Self { id, at: None, volume: 1.0, pitch: 1.0, follow: None }
    }

    pub fn at(self, at: Option<Vec3>) -> Self {
        Self { at, ..self }
    }

    pub fn volume(self, volume: f32) -> Self {
        Self { volume, ..self }
    }

    pub fn pitch(self, pitch: f32) -> Self {
        Self { pitch, ..self }
    }

    pub fn follow(self, follow: Option<(Entity, f32)>) -> Self {
        Self { follow, ..self }
    }
}

/// Plays sounds (see [`Sfx::play`]).
#[derive(SystemParam)]
pub struct Sfx<'w, 's> {
    commands: Commands<'w, 's>,
    bank: Res<'w, SoundBank>,
    mix: Res<'w, SoundMix>,
    ear: Res<'w, Ear>,
    voices: ResMut<'w, Voices>,
    server: Res<'w, AssetServer>,
}

impl<'w, 's> Sfx<'w, 's> {
    pub fn data(&self) -> &SoundData {
        &self.bank.data
    }

    pub fn mix(&self) -> &SoundMix {
        &self.mix
    }

    pub fn commands(&mut self) -> &mut Commands<'w, 's> {
        &mut self.commands
    }

    /// Stop a playing sound.
    pub fn stop(&mut self, voice: Option<Entity>) {
        if let Some(e) = voice {
            self.commands.entity(e).try_despawn();
        }
    }

    /// Play a sound: a random variation with the data's volume and pitch jitter. Heard from `at` when the sound
    /// is spatial (fading with distance, the far variant past its range); `None` when it is too far to hear,
    /// unknown, or its file did not load.
    pub fn play(&mut self, p: Play) -> Option<Entity> {
        let data = &self.bank.data;
        let Some(near) = data.sounds.get(p.id) else {
            if self.voices.warned.insert(p.id.to_string()) {
                warn!("no sound \"{}\" in sounds.ron", p.id);
            }
            return None;
        };
        let distance = match (near.spatial, p.at, self.ear.pos) {
            (true, Some(at), Some(ear)) => Some(ear.distance(at)),
            _ => None,
        };
        let id = by_distance(data, p.id, distance);
        let spec = data.sounds.get(id).unwrap_or(near);
        let handover = match &near.far {
            Some(far) if id != p.id => handover_gain(near, spec, far.beyond_m),
            _ => 1.0,
        };
        let distance = distance.filter(|_| spec.spatial);
        let range = distance.map(|_| (spec.ref_distance_m, spec.max_distance_m));
        let att = distance.map_or(1.0, |d| attenuation(d, spec.ref_distance_m, spec.max_distance_m));
        if att <= 0.0 {
            return None;
        }
        let handles = self.bank.handles.get(id).filter(|h| !h.is_empty())?;
        let last = self.voices.last.get(id).copied();
        let i = pick_variation(handles.len(), last, self.voices.next());
        let handle = handles[i].clone();
        if matches!(self.server.load_state(&handle), LoadState::Failed(_)) {
            if self.voices.warned.insert(format!("{id}#{i}")) {
                warn!("sound \"{id}\": file {} did not load", spec.files.get(i).map_or("?", String::as_str));
            }
            return None;
        }
        self.voices.last.insert(id.to_string(), i);
        let (category, looped) = (spec.category, spec.looped);
        let gain = spec.volume * p.volume * handover;
        let speed = (spec.pitch * p.pitch * (1.0 + spec.pitch_jitter * self.voices.signed())).max(0.05);
        let volume = gain * self.mix.category(category) * att;
        let file = spec.files.get(i).map_or("?", String::as_str);
        let msg = format!(
            "sound: {id} ({file}) vol {volume:.2} pitch {speed:.2}{}{}",
            distance.map_or(String::new(), |d| format!(" at {d:.1} m")),
            if self.mix.muted { " (muted)" } else { "" },
        );
        if self.mix.log {
            info!("{msg}");
        } else {
            debug!("{msg}");
        }
        let settings = PlaybackSettings {
            mode: if looped { PlaybackMode::Loop } else { PlaybackMode::Despawn },
            volume: Volume::Linear(volume),
            speed,
            muted: self.mix.muted,
            spatial: range.is_some(),
            ..PlaybackSettings::ONCE
        };
        let voice = Voice {
            id: id.to_string(),
            category,
            gain,
            range,
            follow: p.follow,
            applied: volume * self.mix.master,
            looped,
            age: 0.0,
        };
        let mut e = self.commands.spawn((
            AudioPlayer(handle),
            settings,
            Transform::from_translation(p.at.unwrap_or_default()),
            voice,
        ));
        if category != Category::Interface {
            e.insert(DespawnOnExit(AppState::InGame));
        }
        Some(e.id())
    }
}

/// The game's sounds (Bevy's audio resolves them under the asset folder).
fn load_sounds(mut bank: ResMut<SoundBank>, server: Res<AssetServer>) {
    let handles: HashMap<String, Vec<Handle<AudioSource>>> = bank
        .data
        .sounds
        .iter()
        .map(|(id, s)| (id.clone(), s.files.iter().map(|f| server.load(format!("audio/{f}"))).collect()))
        .collect();
    info!("sounds: {} ids, {} files", handles.len(), handles.values().map(Vec::len).sum::<usize>());
    bank.handles = handles;
}

/// `VETF_SOUND=1` (or anything but empty and `0`).
fn sound_env() -> bool {
    std::env::var("VETF_SOUND").is_ok_and(|v| !v.is_empty() && v != "0")
}

fn setup_mix(cli: Res<Cli>, mut mix: ResMut<SoundMix>) {
    let audible = sound_env();
    mix.muted = cli.automated() && !audible;
    mix.ignore_focus = cli.automated() && audible;
    mix.log = cli.automated();
    if mix.muted {
        info!("sounds are muted in scripted runs (VETF_SOUND=1 plays them)");
    }
}

/// The view camera is the listener: it gets the ears, and [`Ear`] follows it.
fn follow_listener(
    bank: Res<SoundBank>,
    cameras: Query<(Entity, &GlobalTransform, Has<SpatialListener>), With<ViewCamera>>,
    mut ear: ResMut<Ear>,
    mut commands: Commands,
) {
    let cam = cameras.iter().next();
    ear.pos = cam.map(|(_, t, _)| t.translation());
    if let Some((e, _, false)) = cam {
        commands.entity(e).insert(SpatialListener::new(bank.data.ear_gap_m));
    }
}

/// The AUDIO settings and the window focus into [`SoundMix`] and [`GlobalVolume`].
fn apply_mix(
    settings: Res<Settings>,
    windows: Query<&Window, With<PrimaryWindow>>,
    mut mix: ResMut<SoundMix>,
    mut global: ResMut<GlobalVolume>,
) {
    let a = &settings.audio;
    let focused = mix.ignore_focus || windows.iter().next().is_none_or(|w| w.focused);
    let master = master_gain(a, focused);
    if (global.volume.to_linear() - master).abs() > 1e-4 {
        global.volume = Volume::Linear(master);
    }
    let categories = [
        Category::Weapons,
        Category::Movement,
        Category::Abilities,
        Category::Hits,
        Category::Interface,
        Category::Music,
        Category::Ambient,
    ];
    let m = mix.bypass_change_detection();
    m.master = master;
    for c in categories {
        m.category.insert(c, category_gain(c, a));
    }
    m.shield_tink = a.shield_hit;
    m.headshot = a.headshot;
    m.low_mag_cue = a.low_mag_cue;
}

/// Keep every playing sound at the mix (sliders and the focus move it at once: Bevy applies [`GlobalVolume`]
/// only when a sound starts), at its distance, and at the player it follows; drop loops whose player left
/// and sounds that never started.
fn update_voices(
    time: Res<Time>,
    mix: Res<SoundMix>,
    ear: Res<Ear>,
    players: Query<&PlayerMove>,
    mut voices: Query<(Entity, &mut Voice, &mut Transform, Option<&mut AudioSink>, Option<&mut SpatialAudioSink>)>,
    mut warned: Local<bool>,
    mut commands: Commands,
) {
    let dt = time.delta_secs();
    for (e, mut v, mut t, sink, spatial) in &mut voices {
        v.age += dt;
        if let Some((player, height)) = v.follow {
            let Ok(mv) = players.get(player) else {
                commands.entity(e).try_despawn();
                continue;
            };
            t.translation = mv.0.pos + Vec3::Y * height;
        }
        if sink.is_none() && spatial.is_none() {
            // Still loading, or no audio device: give up on a one-shot that never started.
            if !v.looped && v.age > 5.0 {
                if !std::mem::replace(&mut *warned, true) {
                    warn!("sound \"{}\" never started playing (no audio device?)", v.id);
                }
                commands.entity(e).try_despawn();
            }
            continue;
        }
        let att = match (v.range, ear.pos) {
            (Some((reference, max)), Some(ear)) => attenuation(ear.distance(t.translation), reference, max),
            _ => 1.0,
        };
        let volume = v.gain * mix.category(v.category) * att * mix.master;
        if (volume - v.applied).abs() < 1e-3 {
            continue;
        }
        v.applied = volume;
        if let Some(mut s) = sink {
            s.set_volume(Volume::Linear(volume));
        } else if let Some(mut s) = spatial {
            s.set_volume(Volume::Linear(volume));
        }
    }
}

/// A sound that comes a moment after another: a bolt worked after the shot, the next of several shots heard
/// in one frame.
#[derive(Debug, Clone)]
struct Later {
    left_s: f32,
    id: String,
    at: Option<Vec3>,
    follow: Option<(Entity, f32)>,
}

#[derive(Resource, Default)]
struct Delayed(Vec<Later>);

impl Delayed {
    fn push(&mut self, left_s: f32, id: &str, at: Option<Vec3>, follow: Option<(Entity, f32)>) {
        self.0.push(Later { left_s, id: id.to_string(), at, follow });
    }
}

fn play_delayed(time: Res<Time>, mut delayed: ResMut<Delayed>, mut sfx: Sfx) {
    let dt = time.delta_secs();
    let mut due = Vec::new();
    delayed.0.retain_mut(|l| {
        l.left_s -= dt;
        if l.left_s <= 0.0 {
            due.push(l.clone());
            return false;
        }
        true
    });
    for l in due {
        // A followed player who left takes the sound with them (`update_voices`).
        sfx.play(Play::new(&l.id).at(l.at).follow(l.follow));
    }
}

// ---------------------------------------------------------------------------------------------- players

/// What we last heard of a player (their state a frame ago) and their running sounds.
#[derive(Component, Default)]
struct Heard {
    alive: bool,
    mode: MoveMode,
    air_s: f32,
    /// Footstep clock: a step on each whole phase.
    phase: f32,
    shot_seq: u32,
    action: ActionKind,
    /// The reload in progress (your own: from the tick events).
    reload: Option<ReloadKind>,
    fire_mode: Option<FireMode>,
    dry: DryFire,
    using: bool,
    items_left: u32,
    jet: Option<Entity>,
    zip: Option<Entity>,
    slide: Option<Entity>,
    heal: Option<Entity>,
}

impl Heard {
    /// Take the state as it is now, without sounds (first sight, respawn). The gun counts as not yet
    /// raised, so a fresh spawn's equip is heard.
    fn snapshot(&mut self, mv: &PlayerMove, w: &PlayerWeapon, items: Option<&PlayerItems>, first: f32) {
        self.alive = true;
        self.mode = mv.0.mode;
        self.air_s = 0.0;
        self.phase = first;
        self.shot_seq = w.0.shot_seq;
        self.action = ActionKind::Ready;
        self.reload = None;
        self.fire_mode = Some(w.0.fire_mode);
        self.dry = DryFire::default();
        self.using = items.is_some_and(|i| i.0.using.is_some());
        self.items_left = items_left(items);
    }

    fn loops(&mut self) -> [&mut Option<Entity>; 4] {
        [&mut self.jet, &mut self.zip, &mut self.slide, &mut self.heal]
    }
}

fn items_left(items: Option<&PlayerItems>) -> u32 {
    items.map_or(0, |i| i.0.counts.iter().map(|c| *c as u32).sum())
}

/// Every player's sounds: yours from the simulation's events, others' from their state as it changes; and
/// for everyone footsteps, the jetpack and zipline loops, and the gun being raised.
#[allow(clippy::type_complexity)]
fn player_sounds(
    mut sfx: Sfx,
    time: Res<Time>,
    data: Res<Data>,
    level: Option<Res<CurrentLevel>>,
    mut events: MessageReader<LocalPlayerEvents>,
    mut delayed: ResMut<Delayed>,
    mut players: Query<(
        Entity,
        &PlayerId,
        &PlayerMove,
        &PlayerWeapon,
        &PlayerLoadout,
        Option<&PlayerItems>,
        Option<&Vitals>,
        Has<Controlled>,
        Option<&mut Heard>,
    )>,
) {
    let dt = time.delta_secs();
    let local_events: Vec<LocalPlayerEvents> = events.read().copied().collect();
    let first = sfx.data().footsteps.first_step_phase;
    for (entity, id, mv, w, lo, items, vitals, local, heard) in &mut players {
        let Some(mut heard) = heard else {
            let mut h = Heard::default();
            h.snapshot(mv, w, items, first);
            sfx.commands().entity(entity).insert(h);
            continue;
        };
        let h = &mut *heard;
        let alive = vitals.is_none_or(|v| !v.health.dead);
        if !alive {
            if h.alive {
                for l in h.loops() {
                    let e = l.take();
                    sfx.stop(e);
                }
            }
            h.alive = false;
            continue;
        }
        if !h.alive {
            h.snapshot(mv, w, items, first);
        }
        let m = &mv.0;
        // Your own sounds play as yours; everyone else's from where they are.
        let feet = (!local).then_some(m.pos);
        let body = (!local).then_some(m.pos + Vec3::Y * 1.0);
        let follow = (!local).then_some((entity, 1.0));
        let spec = lo.0.weapon.spec(&data);
        let ws = sfx.data().weapon(&spec.id).clone();

        // Footsteps: from the speed over the ground, whatever keys made it.
        let speed = Vec2::new(m.vel.x, m.vel.z).length();
        let f = &sfx.data().footsteps;
        let hz = if m.mode == MoveMode::Ground { f.cadence_hz(speed) } else { 0.0 };
        let vol = f.volume(speed) * if local { f.own_volume } else { 1.0 };
        if step_clock(&mut h.phase, hz, dt, first) {
            let look = level.as_ref().and_then(|l| look_under(&l.world, m.pos));
            let id = sfx.data().step(look.map_or(Surface::Concrete, surface_of)).to_string();
            sfx.play(Play::new(&id).at(feet).volume(vol));
        }

        // One-shots: yours from the events, theirs from the state.
        if local {
            for ev in local_events.iter().filter(|e| e.player == id.0) {
                local_one_shots(&mut sfx, h, &ev.events, ev.trigger, w, lo, &ws, &mut delayed);
            }
        } else {
            let moves = sfx.data().moves.clone();
            if jumped(h.mode, m.mode, m.vel.y, &moves) {
                sfx.play(Play::new(cue::JUMP).at(body));
            }
            if landed(h.mode, m.mode, h.air_s, &moves) {
                sfx.play(Play::new(cue::LAND).at(feet));
            }
            if m.mode == MoveMode::Slide && h.mode != MoveMode::Slide {
                h.slide = sfx.play(Play::new(cue::SLIDE).at(feet).follow(Some((entity, 0.2))));
            }
            if m.mode == MoveMode::Mantle && h.mode != MoveMode::Mantle {
                sfx.play(Play::new(cue::JUMP).at(body).volume(moves.mantle_volume));
            }
            for id in action_cues(h.action, ActionKind::of(&w.0.action), &ws) {
                sfx.play(Play::new(id).at(body));
            }
            if h.fire_mode.is_some_and(|f| f != w.0.fire_mode) {
                sfx.play(Play::new(cue::FIRE_MODE).at(body));
            }
            // Shots since last frame: the first now, the rest spaced by the gun's fire interval.
            let n = heard_shots(w.0.shot_seq.wrapping_sub(h.shot_seq), sfx.data().max_heard_shots_per_frame);
            let tick_hz = data.net.tick_hz;
            let gap =
                vetf_sim::weapon::fire_interval_ticks(spec, tick_hz, w.0.ads >= ADS_AIMED) as f32 / tick_hz as f32;
            let eye = Some(m.eye_pos());
            for k in 0..n {
                shot(&mut sfx, &ws, eye, follow, k as f32 * gap, &mut delayed);
            }
            if DryFire::remote(&mut h.dry, TriggerTick::of(&w.0)) {
                sfx.play(Play::new(cue::DRY_FIRE).at(body));
            }
            let using = items.is_some_and(|i| i.0.using.is_some());
            let left = items_left(items);
            if using && !h.using {
                h.heal = sfx.play(Play::new(cue::HEAL).at(body).follow(follow));
            } else if !using && h.using && left == h.items_left {
                // Put away before it was used up: cancelled.
                let e = h.heal.take();
                sfx.stop(e);
            }
            h.using = using;
            h.items_left = left;
        }
        // The gun coming up (a fresh spawn), for everyone.
        let action = ActionKind::of(&w.0.action);
        if action == ActionKind::Equipping && h.action != ActionKind::Equipping {
            sfx.play(Play::new(cue::EQUIP).at(body));
        }

        // Loops while thrusting or riding; a slide stops when it ends.
        let jet_on = m.mode == MoveMode::Jetpack;
        let zip_on = m.mode == MoveMode::Zipline;
        for (on, id, slot) in [(jet_on, cue::JETPACK, &mut h.jet), (zip_on, cue::ZIPLINE, &mut h.zip)] {
            if on && slot.is_none() {
                *slot = sfx.play(Play::new(id).at(body).follow(follow));
            } else if !on && slot.is_some() {
                let e = slot.take();
                sfx.stop(e);
            }
        }
        if m.mode != MoveMode::Slide && h.slide.is_some() {
            let e = h.slide.take();
            sfx.stop(e);
        }

        if matches!(m.mode, MoveMode::Air | MoveMode::Jetpack) {
            h.air_s += dt;
        } else {
            h.air_s = 0.0;
        }
        h.mode = m.mode;
        h.shot_seq = w.0.shot_seq;
        h.action = action;
        h.fire_mode = Some(w.0.fire_mode);
    }
}

/// A gunshot of this weapon `after_s` from now, and its bolt being worked after it.
fn shot(
    sfx: &mut Sfx,
    ws: &WeaponSounds,
    at: Option<Vec3>,
    follow: Option<(Entity, f32)>,
    after_s: f32,
    delayed: &mut Delayed,
) {
    if after_s > 0.0 {
        delayed.push(after_s, &ws.shot, at, follow);
    } else {
        sfx.play(Play::new(&ws.shot).at(at));
    }
    if let Some(bolt) = &ws.bolt {
        delayed.push(after_s + ws.bolt_delay_s, bolt, at, follow);
    }
}

/// Your own sounds from one tick's simulation events and the trigger after it.
#[allow(clippy::too_many_arguments)]
fn local_one_shots(
    sfx: &mut Sfx,
    h: &mut Heard,
    ev: &PlayerEvents,
    trigger: TriggerTick,
    w: &PlayerWeapon,
    lo: &PlayerLoadout,
    ws: &WeaponSounds,
    delayed: &mut Delayed,
) {
    // In the order the tick does them: a reload ends, then the fire mode, a new reload or mag check, the shot.
    let wev = &ev.weapon;
    if wev.reload_finished {
        let kind = h.reload.take().unwrap_or(ReloadKind::Tactical);
        for id in reload_done_cues(kind, ws) {
            sfx.play(Play::new(id));
        }
    }
    if let Some(kind) = wev.reload_started {
        h.reload = Some(kind);
    }
    for (on, id) in [
        (wev.fire_mode_changed, cue::FIRE_MODE),
        (wev.reload_started.is_some(), cue::MAG_OUT),
        (wev.mag_check_started, cue::MAG_CHECK),
        (ev.movement.jumped, cue::JUMP),
        (ev.movement.landed, cue::LAND),
    ] {
        if on {
            sfx.play(Play::new(id));
        }
    }
    if wev.shot.is_some() {
        shot(sfx, ws, None, None, 0.0, delayed);
        if sfx.mix().low_mag_cue && low_mag(w.0.mag(), lo.0.weapon.mag_capacity) {
            sfx.play(Play::new(cue::LOW_MAG));
        }
    }
    if h.dry.local(wev, trigger) {
        sfx.play(Play::new(cue::DRY_FIRE));
    }
    if ev.movement.mantle_started {
        let v = sfx.data().moves.mantle_volume;
        sfx.play(Play::new(cue::JUMP).volume(v));
    }
    if ev.movement.slide_started {
        let e = h.slide.take();
        sfx.stop(e);
        h.slide = sfx.play(Play::new(cue::SLIDE));
    }
    if ev.items.started.is_some() {
        let e = h.heal.take();
        sfx.stop(e);
        h.heal = sfx.play(Play::new(cue::HEAL));
    }
    if ev.items.cancelled {
        let e = h.heal.take();
        sfx.stop(e);
    }
}

// ---------------------------------------------------------------------------------------------- hits

/// The host's word on a hit you landed or took (`client::receive_feedback` forwards them).
#[derive(Message, Debug, Clone, Copy)]
pub enum FeedbackSound {
    Hit(HitConfirm),
    Damage(DamageTaken),
}

/// Your hits: the kill confirm, head or flesh hit, and the shield tink pitched by the tier of the victim's
/// arc. Hits you take: the impact, and the tink of your own arc when the halo took it.
fn feedback_sounds(
    mut sfx: Sfx,
    mut heard: MessageReader<FeedbackSound>,
    players: Query<(&PlayerId, &PlayerLoadout, Has<Controlled>)>,
) {
    for f in heard.read() {
        let tier = |pick: &dyn Fn(u64, bool) -> bool, zone: Zone| {
            players.iter().find(|(p, _, me)| pick(p.0, *me)).map_or(1, |(_, l, _)| l.0.halo.tiers[zone])
        };
        match f {
            FeedbackSound::Hit(h) => {
                let (tink, head) = (sfx.mix().shield_tink, sfx.mix().headshot);
                for id in hit_cues(h, tink, head) {
                    let pitch = if id == cue::SHIELD_HIT {
                        shield_pitch(&sfx.data().shield_hit_pitch, tier(&|p, _| p == h.victim, h.zone))
                    } else {
                        1.0
                    };
                    sfx.play(Play::new(id).pitch(pitch));
                }
            }
            FeedbackSound::Damage(d) => {
                sfx.play(Play::new(cue::DAMAGE_TAKEN));
                if d.shield && sfx.mix().shield_tink {
                    let pitch = shield_pitch(&sfx.data().shield_hit_pitch, tier(&|_, me| me, d.zone));
                    let v = sfx.data().own_shield_hit_volume;
                    sfx.play(Play::new(cue::SHIELD_HIT).pitch(pitch).volume(v));
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------------------------- interface

/// Menu and hub-screen buttons: a tick on hover, a click (or confirm / back) on press; a hub screen opening
/// or closing without a button (Esc) clicks or goes back too.
#[allow(clippy::too_many_arguments)]
fn ui_sounds(
    mut sfx: Sfx,
    time: Res<Time>,
    buttons: Query<(Entity, &Interaction, Option<&Looks>, Has<Disabled>), (Changed<Interaction>, With<Button>)>,
    children: Query<&Children>,
    texts: Query<&Text>,
    screens: Res<Screens>,
    mut prev: Local<HashMap<Entity, Interaction>>,
    mut last_hover: Local<f32>,
    mut last_press: Local<f32>,
    mut prev_screens: Local<Option<Screens>>,
) {
    let now = time.elapsed_secs();
    let gap = sfx.data().ui.hover_gap_s;
    if prev.len() > 512 {
        prev.clear();
    }
    for (e, interaction, looks, disabled) in &buttons {
        let before = prev.insert(e, *interaction).unwrap_or(Interaction::None);
        if disabled {
            continue;
        }
        match interaction {
            Interaction::Hovered if before == Interaction::None && now - *last_hover >= gap => {
                *last_hover = now;
                sfx.play(Play::new(cue::UI_HOVER));
            }
            Interaction::Pressed => {
                let label = children.iter_descendants(e).find_map(|c| texts.get(c).ok()).map_or("", |t| t.0.as_str());
                let primary = looks.is_some_and(|l| *l == BTN_PRIMARY || *l == BTN_ALLY);
                let id = press_cue(label, primary, &sfx.data().ui);
                *last_press = now;
                sfx.play(Play::new(id));
            }
            Interaction::None => {
                prev.remove(&e);
            }
            _ => {}
        }
    }
    // Screens opened or closed with a key (Esc) rather than a button. The lobby closing is the match starting.
    let before = prev_screens.replace(screens.clone());
    if let Some(before) = before
        && before != *screens
        && now - *last_press > 0.2
    {
        let (was, is) = (before.iter().count(), screens.iter().count());
        let lobby_closed = before.contains(Screen::Lobby) && !screens.contains(Screen::Lobby);
        if is < was && !lobby_closed {
            sfx.play(Play::new(cue::UI_BACK));
        } else if is > was && !screens.contains(Screen::Lobby) {
            sfx.play(Play::new(cue::UI_CLICK));
        }
    }
}

/// Which volume slider changed between two looks at the settings (the first, if several did).
pub fn changed_slider(before: &[f32; 7], now: &[f32; 7]) -> Option<usize> {
    (0..7).find(|&i| (before[i] - now[i]).abs() > 1e-4)
}

/// Settings ▸ AUDIO: once a volume slider rests after a change, a sample of its category plays at the new
/// level (the hub spec's proposal), while a Settings screen is open.
fn preview_volume(
    mut sfx: Sfx,
    time: Res<Time>,
    settings: Res<Settings>,
    screens: Res<Screens>,
    mut last: Local<Option<[f32; 7]>>,
    mut pending: Local<Option<(usize, f32)>>,
) {
    let now = sliders(&settings.audio);
    let t = time.elapsed_secs();
    if let Some(before) = last.replace(now)
        && let Some(i) = changed_slider(&before, &now)
    {
        *pending = Some((i, t));
    }
    let Some((i, since)) = *pending else { return };
    if t - since < sfx.data().ui.preview_rest_s {
        return;
    }
    *pending = None;
    let open = screens.iter().any(|s| matches!(s, Screen::Settings(_)));
    if let (true, Some(id)) = (open, sfx.data().ui.previews[i].clone()) {
        sfx.play(Play::new(&id));
    }
}

// ---------------------------------------------------------------------------------------------- ambience

/// The map's ambience loop while in a match.
fn ambience(
    mut sfx: Sfx,
    state: Res<State<AppState>>,
    level: Option<Res<CurrentLevel>>,
    voices: Query<(), With<Voice>>,
    mut playing: Local<Option<(String, Entity)>>,
) {
    let want = match (state.get(), &level) {
        (AppState::InGame, Some(l)) => sfx.data().ambience.get(&l.name.to_ascii_lowercase()).cloned(),
        _ => None,
    };
    let current = playing.as_ref().filter(|(_, e)| voices.contains(*e)).map(|(id, _)| id.clone());
    if current == want {
        return;
    }
    if let Some((_, e)) = playing.take() {
        sfx.stop(Some(e));
    }
    if let Some(id) = want
        && let Some(e) = sfx.play(Play::new(&id))
    {
        *playing = Some((id, e));
    }
}

// ---------------------------------------------------------------------------------------------- demo

fn demo_is_dry_fire(cli: Res<Cli>) -> bool {
    cli.host.is_some() && cli.demo_ui.as_deref() == Some("dry-fire")
}

/// `--host ... --bot --demo-ui dry-fire`: a second into the match, and then at most every 5 s, empty the
/// magazine in the host's own gun once it has fired from it, so the bot's next trigger pulls click (once each)
/// until its reload tap swaps magazines. A test of the dry click and the reload sounds.
fn demo_dry_fire(
    time: Res<Time>,
    mut me: Query<(&mut PlayerWeapon, &PlayerLoadout), With<Controlled>>,
    mut entered: Local<Option<f32>>,
    mut last: Local<Option<f32>>,
) {
    let t = time.elapsed_secs();
    let since = t - *entered.get_or_insert(t);
    if since < 1.0 || last.is_some_and(|l| t - l < 5.0) {
        return;
    }
    for (mut w, lo) in &mut me {
        let rounds = w.0.mag();
        if w.0.is_ready() && rounds > 0 && rounds < lo.0.weapon.mag_capacity {
            let slot = w.0.loaded as usize;
            w.0.rounds[slot] = 0;
            *last = Some(t);
            info!("demo: emptied the magazine in the gun (slot {})", slot + 1);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use vetf_sim::GameData;
    use vetf_sim::data::AmmoChoice;
    use vetf_sim::input::InputFrame;
    use vetf_sim::movement::collision::{Brush, BrushKind};
    use vetf_sim::weapon::{WeaponEnv, WeaponLoadout};

    fn data() -> &'static SoundData {
        SoundData::embedded()
    }

    /// The ids the game plays and the H3 batch generates (`assets/audio/h3_test/<category>/<name>_<n>.ogg`).
    const IDS: [&str; 34] = [
        "weapons/mako_shot",
        "weapons/warden_shot",
        "weapons/skink_shot",
        "weapons/shot_distant",
        "weapons/dry_fire",
        "weapons/mag_out",
        "weapons/mag_in",
        "weapons/bolt_cycle",
        "weapons/fire_mode",
        "weapons/mag_check",
        "weapons/equip",
        "movement/step_concrete",
        "movement/step_grass",
        "movement/step_gravel",
        "movement/step_wood",
        "movement/jump",
        "movement/land",
        "movement/slide",
        "movement/jetpack",
        "movement/zipline",
        "combat/hit_flesh",
        "combat/hit_head",
        "combat/shield_hit",
        "combat/shield_break",
        "combat/kill",
        "combat/damage_taken",
        "items/heal",
        "ui/click",
        "ui/hover",
        "ui/confirm",
        "ui/back",
        "ambient/showhome_loop",
        "ambient/range_loop",
        // AUDIO > LOW-MAG CUE (it borrows the dry click's file)
        "weapons/low_mag_click",
    ];

    #[test]
    fn the_data_file_parses_and_every_id_and_file_exists() {
        let d = data();
        assert!(d.problems().is_empty(), "{:?}", d.problems());
        let audio = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../assets/audio");
        for id in IDS {
            assert!(d.sounds.contains_key(id), "sounds.ron has \"{id}\"");
        }
        let shared: HashSet<&str> = d.sounds.values().flat_map(|s| s.files.iter().map(String::as_str)).collect();
        for (id, s) in &d.sounds {
            assert!((1..=3).contains(&s.files.len()), "{id}: one to three variations, not {}", s.files.len());
            for f in &s.files {
                assert!(f.ends_with(".ogg"), "{id}: {f} is OGG Vorbis like the rest");
                assert!(audio.join(f).is_file(), "{id}: game/assets/audio/{f} exists");
                // `<id>.ogg` or `<id>_<n>.ogg`, so a real sound goes in under the id's own name (the low-mag
                // click borrows the dry fire's file).
                let stem = f.trim_end_matches(".ogg");
                let named = stem == id
                    || stem
                        .strip_prefix(id.as_str())
                        .and_then(|r| r.strip_prefix('_'))
                        .is_some_and(|n| n.parse::<u8>().is_ok());
                assert!(named || (id == cue::LOW_MAG && shared.contains(f.as_str())), "{id}: {f} is named after it");
            }
        }
        for gun in &GameData::embedded().weapons.weapons {
            assert!(d.weapons.contains_key(&gun.id), "{} has shot sounds", gun.id);
        }
        assert_eq!(d.weapon("vk50_warden").bolt.as_deref(), Some("weapons/bolt_cycle"));
        assert_eq!(d.weapon("nope").shot, "weapons/mako_shot", "a gun without a row uses the default");
        for map in ["showhome", "range"] {
            assert!(vetf_sim::maps::by_name(map).is_some(), "{map} is a map");
            assert!(d.ambience.contains_key(map), "{map} has ambience");
        }
        // Loops loop, own and hit sounds are not spatial, other players' gunshots are and have a far variant.
        for id in [cue::JETPACK, cue::ZIPLINE, "ambient/showhome_loop", "ambient/range_loop"] {
            assert!(d.sounds[id].looped, "{id} loops");
        }
        for id in [cue::HIT_FLESH, cue::KILL, cue::DAMAGE_TAKEN, cue::UI_CLICK, cue::LOW_MAG] {
            assert!(!d.sounds[id].spatial, "{id}");
        }
        for gun in d.weapons.values() {
            let s = &d.sounds[&gun.shot];
            assert!(s.spatial && s.far.as_ref().is_some_and(|f| f.sound == "weapons/shot_distant"), "{}", gun.shot);
        }
        assert!(d.sounds[cue::DRY_FIRE].spatial, "other players' dry clicks are heard nearby");
    }

    #[test]
    fn a_broken_data_file_reports_its_problems() {
        let mut d = data().clone();
        d.sounds.remove(cue::KILL);
        d.weapons.get_mut("ar7_mako").unwrap().shot = "weapons/laser".into();
        d.sounds.get_mut(cue::HEAL).unwrap().files.clear();
        d.sounds.get_mut("weapons/shot_distant").unwrap().far =
            Some(FarSound { sound: "weapons/mako_shot".into(), beyond_m: 10.0 });
        let p = d.problems();
        assert!(p.iter().any(|s| s.contains("combat/kill")), "{p:?}");
        assert!(p.iter().any(|s| s.contains("weapons/laser")), "{p:?}");
        assert!(p.iter().any(|s| s.contains("items/heal") && s.contains("no files")), "{p:?}");
        assert!(p.iter().any(|s| s.contains("has a far sound itself")), "far sounds never chain: {p:?}");
        assert!(ron::from_str::<SoundData>("(sounds: {})").is_err(), "a partial file falls back to the built-in");
    }

    /// Pull the trigger on every gun until it is empty and on: each pull of an empty gun clicks once, however
    /// long FIRE is held, and a gun with rounds never clicks.
    #[test]
    fn an_empty_gun_clicks_once_per_trigger_pull() {
        let d = GameData::embedded();
        let env = WeaponEnv {
            mode: MoveMode::Ground,
            sprinting: false,
            crouched: false,
            speed_frac: 0.0,
            broken_arms: false,
            hands_busy: false,
        };
        for gun in &d.weapons.weapons {
            let lo = WeaponLoadout::resolve(&d, &gun.id, &[AmmoChoice::STANDARD], &[]).unwrap();
            let mut ws = WeaponState::new(&d, &lo);
            ws.action = WeaponAction::Ready;
            let mut dry = DryFire::default();
            let mut tick = |ws: &mut WeaponState, fire: bool| {
                let b = if fire { Buttons::FIRE } else { 0 };
                let ev = ws.step(&d, &lo, &InputFrame { buttons: Buttons(b), ..Default::default() }, &env);
                let click = dry.local(&ev, TriggerTick::of(ws));
                (ev.shot.is_some(), click)
            };
            // Each pull: FIRE held for 2 s, then let go for half a second. Count shots and clicks per pull.
            let mut pulls = Vec::new();
            for _ in 0..(lo.mag_capacity as usize + 10) {
                let (mut shots, mut clicks) = (0, 0);
                for _ in 0..120 {
                    let (s, c) = tick(&mut ws, true);
                    shots += s as u32;
                    clicks += c as u32;
                }
                for _ in 0..30 {
                    let (s, c) = tick(&mut ws, false);
                    assert!(!s && !c, "{}: nothing with the trigger let go", gun.id);
                }
                pulls.push((shots, clicks));
                if pulls.iter().filter(|p| p.1 > 0).count() >= 3 {
                    break;
                }
            }
            let total: u32 = pulls.iter().map(|p| p.0).sum();
            assert_eq!(total, lo.mag_capacity as u32, "{}: the magazine empties ({pulls:?})", gun.id);
            let first_dry = pulls.iter().position(|p| p.1 > 0).unwrap();
            for (i, &(shots, clicks)) in pulls.iter().enumerate() {
                assert!(clicks <= 1, "{}: pull {i} clicked {clicks} times", gun.id);
                if i > first_dry {
                    assert_eq!((shots, clicks), (0, 1), "{}: an empty pull clicks once", gun.id);
                }
            }
            // An automatic that runs dry with FIRE held clicks on that same pull, once.
            if gun.fire_modes.first() == Some(&FireMode::Auto) {
                let mut ws = WeaponState::new(&d, &lo);
                ws.action = WeaponAction::Ready;
                let mut dry = DryFire::default();
                let (mut shots, mut clicks) = (0, 0);
                for _ in 0..(lo.mag_capacity as usize * 10 + 120) {
                    let b = InputFrame { buttons: Buttons(Buttons::FIRE), ..Default::default() };
                    let ev = ws.step(&d, &lo, &b, &env);
                    shots += ev.shot.is_some() as u16;
                    clicks += dry.local(&ev, TriggerTick::of(&ws)) as u16;
                }
                assert_eq!((shots, clicks), (lo.mag_capacity, 1), "{}: held through the last round", gun.id);
            }
        }
    }

    #[test]
    fn the_dry_fire_latch_and_other_players_triggers() {
        let mut dry = DryFire::default();
        // a semi-automatic pressed three times: three clicks; held: one
        let press = WeaponEvents { dry_fire: true, ..Default::default() };
        let held = TriggerTick { held: true, auto: false, empty_ready: true };
        let up = TriggerTick { held: false, auto: false, empty_ready: true };
        let mut clicks = 0;
        for _ in 0..3 {
            clicks += dry.local(&press, held) as u32;
            for _ in 0..10 {
                clicks += dry.local(&WeaponEvents::default(), held) as u32;
            }
            clicks += dry.local(&WeaponEvents::default(), up) as u32;
        }
        assert_eq!(clicks, 3);
        // a semi-automatic held on after its last shot does not click by itself: only a press tries to fire
        let mut dry = DryFire::default();
        assert!(!(0..60).any(|_| dry.local(&WeaponEvents::default(), held)));
        // another player's state, seen once a frame: one click per pull, not while the gun is busy
        let mut dry = DryFire::default();
        let busy = TriggerTick { held: true, auto: true, empty_ready: false };
        assert!(!dry.remote(busy), "reloading or cooling down");
        assert!(dry.remote(held));
        assert!(!dry.remote(held) && !dry.remote(held));
        assert!(!dry.remote(up));
        assert!(dry.remote(held), "a new pull");
    }

    #[test]
    fn footstep_surfaces_follow_the_floor_look() {
        assert_eq!(surface_of(Look::Ground), Surface::Grass);
        assert_eq!(surface_of(Look::Gravel), Surface::Gravel);
        assert_eq!(surface_of(Look::Floor), Surface::Wood);
        for l in [Look::Paving, Look::Asphalt, Look::Concrete, Look::Metal, Look::Roof] {
            assert_eq!(surface_of(l), Surface::Concrete, "{l:?}");
        }
        assert_eq!(data().step(Surface::Wood), "movement/step_wood");
        // A gravel patch on grass, a floor slab above, a ramp and an invisible clip over everything.
        let mut w = CollisionWorld::default();
        let cube = |a: Vec3, b: Vec3, look| Brush::cuboid(a, b, BrushKind::Solid).with_look(look);
        w.push(cube(Vec3::new(-10.0, -1.0, -10.0), Vec3::new(10.0, 0.0, 10.0), Look::Ground));
        w.push(cube(Vec3::new(2.0, -0.5, 2.0), Vec3::new(4.0, 0.0, 4.0), Look::Gravel));
        w.push(cube(Vec3::new(-4.0, 2.7, -4.0), Vec3::new(-2.0, 3.0, -2.0), Look::Floor));
        w.push(
            Brush::ramp(Vec3::new(5.0, 0.0, -4.0), Vec3::new(8.0, 1.5, -2.0), Vec3::X, BrushKind::Solid)
                .with_look(Look::Paving),
        );
        w.push(Brush::cuboid(Vec3::new(-20.0, 0.0, -20.0), Vec3::new(20.0, 5.0, 20.0), BrushKind::PlayerClip));
        assert_eq!(look_under(&w, Vec3::new(0.0, 0.0, 0.0)), Some(Look::Ground));
        assert_eq!(look_under(&w, Vec3::new(3.0, 0.002, 3.0)), Some(Look::Gravel), "the patch, not the ground");
        assert_eq!(look_under(&w, Vec3::new(-3.0, 3.0, -3.0)), Some(Look::Floor), "upstairs");
        assert_eq!(look_under(&w, Vec3::new(-3.0, 0.0, -3.0)), Some(Look::Ground), "under the slab");
        // halfway up the ramp (it rises toward +X from 0 to 1.5 m)
        assert_eq!(look_under(&w, Vec3::new(6.5, 0.75, -3.0)), Some(Look::Paving));
        assert_eq!(look_under(&w, Vec3::new(50.0, 0.0, 0.0)), None, "off the map");
    }

    /// Steps come from the speed over the ground: walking and crouching (also with the lightest halo) are
    /// silent, running at any weight, backwards or aiming is heard, and faster is louder and quicker.
    #[test]
    fn footsteps_follow_the_ground_speed() {
        let f = &data().footsteps;
        let g = GameData::embedded();
        let s = &g.movement.speed;
        let fx = |w| g.armor.effects(w).move_mult;
        use vetf_sim::data::WeightClass as W;
        let (lightest, heaviest) = (fx(W::None).max(fx(W::Light)), fx(W::Heavy).min(fx(W::Medium)));
        let slowest_gun = g.weapons.weapons.iter().map(|w| w.move_mult_held).fold(1.0, f32::min);
        for quiet in [s.walk * lightest, s.crouch * lightest, 0.0, 0.5] {
            assert_eq!(f.cadence_hz(quiet), 0.0, "{quiet} m/s is silent");
        }
        let slow_run = s.jog * heaviest * s.backpedal_mult * slowest_gun;
        assert!(f.cadence_hz(slow_run) > 0.0, "a heavy halo running backwards ({slow_run} m/s) is heard");
        let (jog, sprint) = (f.cadence_hz(s.jog), f.cadence_hz(s.sprint));
        assert!(jog < sprint, "{jog} {sprint}");
        assert!((jog - 2.64).abs() < 1e-4 && (sprint - 3.3).abs() < 1e-4, "{jog} {sprint}");
        assert_eq!(f.cadence_hz(40.0), f.cadence_max_hz);
        assert!(f.volume(s.jog) < f.volume(s.sprint), "sprinting is louder");
        assert_eq!(f.volume(f.silent_below_mps), f.quiet_volume);
        assert_eq!(f.volume(40.0), f.loud_volume);
        assert!(f.own_volume < 1.0, "your own steps sit under other players'");
        // two seconds of jogging at 60 fps is five steps, the first after (1 - first_step_phase) of a step
        let mut phase = 0.0;
        step_clock(&mut phase, 0.0, 0.016, f.first_step_phase);
        assert_eq!(phase, f.first_step_phase, "standing still rests the clock");
        let ticks: Vec<usize> =
            (0..120).filter(|_| step_clock(&mut phase, jog, 1.0 / 60.0, f.first_step_phase)).collect();
        assert_eq!(ticks.len(), 5, "{ticks:?}");
        assert_eq!(ticks[0], ((1.0 - f.first_step_phase) / jog * 60.0).ceil() as usize - 1);
    }

    #[test]
    fn far_shots_play_the_distant_crack() {
        let d = data();
        let beyond = d.sounds["weapons/mako_shot"].far.as_ref().unwrap().beyond_m;
        assert_eq!(by_distance(d, "weapons/mako_shot", None), "weapons/mako_shot", "your own shot");
        assert_eq!(by_distance(d, "weapons/mako_shot", Some(5.0)), "weapons/mako_shot");
        assert_eq!(by_distance(d, "weapons/mako_shot", Some(beyond)), "weapons/mako_shot");
        assert_eq!(by_distance(d, "weapons/mako_shot", Some(beyond + 1.0)), "weapons/shot_distant");
        assert_eq!(by_distance(d, "weapons/warden_shot", Some(300.0)), "weapons/shot_distant");
        assert_eq!(by_distance(d, cue::DRY_FIRE, Some(300.0)), cue::DRY_FIRE, "no far variant");
        // a near gunshot at its hand-over distance is still well audible, and the distant crack takes over at
        // the same loudness (no jump), the Warden's louder than the Skink's
        let far = &d.sounds["weapons/shot_distant"];
        let level =
            |s: &SoundSpec, gain: f32, m: f32| gain * s.volume * attenuation(m, s.ref_distance_m, s.max_distance_m);
        let mut at_100 = Vec::new();
        for gun in ["weapons/skink_shot", "weapons/mako_shot", "weapons/warden_shot"] {
            let near = &d.sounds[gun];
            let beyond = near.far.as_ref().unwrap().beyond_m;
            let g = handover_gain(near, far, beyond);
            assert!(level(near, 1.0, beyond) > 0.1, "{gun}");
            assert!((level(near, 1.0, beyond) - level(far, g, beyond)).abs() < 1e-4, "{gun}: a smooth hand-over");
            assert!(level(far, g, 200.0) < level(far, g, beyond) && level(far, g, far.max_distance_m) == 0.0);
            at_100.push(level(far, g, 100.0));
        }
        assert!(at_100.windows(2).all(|w| w[0] < w[1]), "SMG < rifle < bolt rifle far away: {at_100:?}");
        // several shots of another player in one frame: a few play, a counter reset plays none
        let cap = d.max_heard_shots_per_frame;
        assert_eq!(heard_shots(0, cap), 0);
        assert_eq!(heard_shots(1, cap), 1);
        assert_eq!(heard_shots(20, cap), cap);
        assert_eq!(heard_shots(0u32.wrapping_sub(5), cap), 0);
    }

    #[test]
    fn reloads_mag_checks_and_the_bolt() {
        let d = data();
        let (mako, warden) = (d.weapon("ar7_mako"), d.weapon("vk50_warden"));
        use ActionKind as A;
        let (tac, empty) = (A::Reloading(ReloadKind::Tactical), A::Reloading(ReloadKind::Empty));
        assert_eq!(action_cues(A::Ready, tac, mako), [cue::MAG_OUT]);
        assert_eq!(action_cues(tac, tac, mako), Vec::<&str>::new());
        assert_eq!(action_cues(tac, A::Ready, mako), [cue::MAG_IN]);
        assert_eq!(action_cues(empty, A::Ready, mako), [cue::MAG_IN], "the Mako has no bolt to work");
        assert_eq!(action_cues(empty, A::Ready, warden), [cue::MAG_IN, "weapons/bolt_cycle"]);
        assert_eq!(action_cues(tac, A::Ready, warden), [cue::MAG_IN], "a round is still chambered");
        assert_eq!(action_cues(A::Ready, A::MagChecking, mako), [cue::MAG_CHECK]);
        assert_eq!(action_cues(A::MagChecking, A::Ready, mako), Vec::<&str>::new());
        assert_eq!(action_cues(A::Equipping, A::Ready, mako), Vec::<&str>::new());
    }

    #[test]
    fn shield_tinks_rise_with_the_tier() {
        let t = &data().shield_hit_pitch;
        let p: Vec<f32> = (1..=4).map(|tier| shield_pitch(t, tier)).collect();
        assert_eq!(p[0], 1.0, "T1 at the file's own pitch");
        assert!(p.windows(2).all(|w| w[1] > w[0]), "{p:?}");
        assert_eq!(shield_pitch(t, 0), p[0]);
        assert_eq!(shield_pitch(t, 9), p[3]);
    }

    #[test]
    fn volume_maths() {
        assert_eq!(slider_gain(100.0), 1.0);
        assert_eq!(slider_gain(50.0), 0.25);
        assert_eq!(slider_gain(0.0), 0.0);
        assert_eq!(slider_gain(150.0), 1.0);
        let mut a = crate::settings::Settings::default().audio;
        a.master = 80.0;
        a.weapons = 50.0;
        a.interface = 0.0;
        assert!((master_gain(&a, true) - 0.64).abs() < 1e-6);
        assert_eq!(category_gain(Category::Weapons, &a), 0.25);
        assert_eq!(category_gain(Category::Interface, &a), 0.0);
        assert_eq!(category_gain(Category::Ambient, &a), 1.0, "no ambience slider: master only");
        // PLAY IN BACKGROUND
        a.play_in_background = false;
        assert_eq!(master_gain(&a, false), 0.0, "muted in the background");
        a.play_in_background = true;
        assert!((master_gain(&a, false) - 0.64).abs() < 1e-6);
        // distance
        assert_eq!(attenuation(1.0, 2.0, 40.0), 1.0);
        assert_eq!(attenuation(40.0, 2.0, 40.0), 0.0);
        assert!((attenuation(21.0, 2.0, 40.0) - 0.25).abs() < 1e-6, "half way out is a quarter");
        let fall: Vec<f32> = (0..50).map(|d| attenuation(d as f32, 2.0, 40.0)).collect();
        assert!(fall.windows(2).all(|w| w[1] <= w[0]));
        // the sliders in the tab's order, and which one moved
        let s = sliders(&a);
        assert_eq!(s, [80.0, 50.0, a.movement, a.abilities, a.hits, 0.0, a.music]);
        let mut b = s;
        assert_eq!(changed_slider(&s, &b), None);
        b[4] = 12.0;
        assert_eq!(changed_slider(&s, &b), Some(4));
        // each category slider's sample is a sound of that category (MUSIC has none yet), MASTER has one
        let d = data();
        let category = |i: usize| d.ui.previews[i].as_deref().map(|id| d.sounds[id].category);
        let want = [Category::Weapons, Category::Movement, Category::Abilities, Category::Hits, Category::Interface];
        for (i, c) in want.into_iter().enumerate() {
            assert_eq!(category(i + 1), Some(c), "slider {}", i + 1);
        }
        assert!(d.ui.previews[0].is_some() && d.ui.previews[6].is_none());
    }

    #[test]
    fn variations_never_repeat_back_to_back() {
        assert_eq!(pick_variation(1, Some(0), 7), 0);
        assert_eq!(pick_variation(0, None, 7), 0);
        for r in 0..50 {
            for last in 0..3 {
                let i = pick_variation(3, Some(last), r);
                assert!(i < 3 && i != last);
            }
            assert!(pick_variation(3, None, r) < 3);
        }
        let mut v = Voices::default();
        let xs: Vec<f32> = (0..1000).map(|_| v.signed()).collect();
        assert!(xs.iter().all(|x| (-1.0..1.0).contains(x)));
        assert!(xs.iter().any(|x| *x < -0.9) && xs.iter().any(|x| *x > 0.9));
    }

    #[test]
    fn button_presses_pick_click_confirm_or_back() {
        let ui = &data().ui;
        assert_eq!(press_cue("BACK", false, ui), cue::UI_BACK);
        assert_eq!(press_cue("Cancel", true, ui), cue::UI_BACK, "back wins over primary");
        assert_eq!(press_cue("READY", false, ui), cue::UI_CONFIRM);
        assert_eq!(press_cue("START MATCH", false, ui), cue::UI_CONFIRM);
        assert_eq!(press_cue("LOADOUT", true, ui), cue::UI_CONFIRM, "a primary button");
        assert_eq!(press_cue("LOADOUT", false, ui), cue::UI_CLICK);
        assert_eq!(press_cue("NORTH UP", false, ui), cue::UI_CLICK, "whole words only");
        assert_eq!(press_cue("", false, ui), cue::UI_CLICK);
    }

    #[test]
    fn hits_kills_and_their_settings() {
        let hit = |kind, zone, shield_broke| HitConfirm { victim: 1, zone, kind, shield_broke };
        assert_eq!(hit_cues(&hit(HitKind::Health, Zone::Torso, false), true, true), [cue::HIT_FLESH]);
        assert_eq!(hit_cues(&hit(HitKind::Health, Zone::Head, false), true, true), [cue::HIT_HEAD]);
        assert_eq!(hit_cues(&hit(HitKind::Health, Zone::Head, false), true, false), [cue::HIT_FLESH], "HEADSHOT off");
        assert_eq!(hit_cues(&hit(HitKind::Shield, Zone::Arms, false), true, true), [cue::SHIELD_HIT]);
        assert!(hit_cues(&hit(HitKind::Shield, Zone::Arms, false), false, true).is_empty(), "SHIELD-HIT off");
        assert_eq!(
            hit_cues(&hit(HitKind::Health, Zone::Legs, true), true, true),
            [cue::HIT_FLESH, cue::SHIELD_BREAK],
            "the arc broke and the rest went through"
        );
        assert_eq!(
            hit_cues(&hit(HitKind::Kill, Zone::Head, true), true, true),
            [cue::KILL, cue::HIT_HEAD, cue::SHIELD_BREAK]
        );
        assert_eq!(hit_cues(&hit(HitKind::Kill, Zone::Torso, false), true, true), [cue::KILL]);
    }

    #[test]
    fn the_low_mag_cue_follows_the_mag_check_bands() {
        // A 30-round magazine: the cue starts where a mag check would say ALMOST EMPTY.
        let on: Vec<u16> = (0..=30).filter(|r| low_mag(*r, 30)).collect();
        assert_eq!(on, [0, 1, 2, 3, 4]);
        for r in 0..=30 {
            let band = MagEstimate::from_rounds(r, 30);
            assert_eq!(low_mag(r, 30), matches!(band, MagEstimate::AlmostEmpty | MagEstimate::Empty));
        }
        assert!(!low_mag(5, 5), "a full magazine");
        assert!(low_mag(0, 5));
    }

    #[test]
    fn jumps_and_landings_from_the_movement_mode() {
        let m = &data().moves;
        assert!(jumped(MoveMode::Ground, MoveMode::Air, 5.0, m));
        assert!(jumped(MoveMode::Slide, MoveMode::Air, 5.0, m), "a slide jump");
        assert!(!jumped(MoveMode::Ground, MoveMode::Air, 0.0, m), "walking off a ledge");
        assert!(!jumped(MoveMode::Air, MoveMode::Jetpack, 5.0, m));
        assert!(landed(MoveMode::Air, MoveMode::Ground, 0.6, m));
        assert!(landed(MoveMode::Jetpack, MoveMode::Slide, 0.6, m));
        assert!(!landed(MoveMode::Air, MoveMode::Ground, 0.05, m), "a step down");
        assert!(!landed(MoveMode::Zipline, MoveMode::Ground, 2.0, m));
    }
}
