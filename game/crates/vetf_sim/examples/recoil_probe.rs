//! Recoil probe: every gun fires a full magazine (default parts) at a wall 10 m and 25 m away, standing still,
//! walking and sprinting, from the hip and aimed. Nobody pulls down: the view climbs by every kick and recovers the
//! way the client's view recoil does (`recoil::ViewRecoil`). Prints where every round lands as CSV on stdout:
//! x right and y up on the wall (metres from the first aim point), and dx / dy, the round's offset from where the
//! view pointed (the random bloom alone, the fixed pattern taken out).
//!
//! With `trace`, it prints the view instead: every gun's pitch and yaw (degrees) every tick while it empties a
//! magazine standing still, from the hip and aimed, and a second after (the kick shape over time).
//!
//! `cargo run -p vetf_sim --example recoil_probe > impacts.csv`
//! `cargo run -p vetf_sim --example recoil_probe -- trace > trace.csv`

use vetf_sim::GameData;
use vetf_sim::data::{AmmoChoice, FireMode, WeaponSpec};
use vetf_sim::input::{Buttons, InputFrame, view_dir};
use vetf_sim::movement::MoveMode;
use vetf_sim::recoil::ViewRecoil;
use vetf_sim::weapon::{WeaponAction, WeaponEnv, WeaponLoadout, WeaponState, shot_direction, shot_seed};

/// Shooters (spread seeds) per spray: standing still they all land on the same points.
const PLAYERS: u64 = 3;

/// One magazine from `env`, aimed in first if `aimed`; FIRE held (pressed every other tick for guns that fire once
/// per pull) until the magazine is empty, then `tail` more ticks. Calls `out(tick, yaw, pitch, shot)` every tick with
/// the view the tick fired from (radians), the view recoil applied as the client does.
#[allow(clippy::too_many_arguments)]
fn spray(
    d: &GameData,
    gun: &WeaponSpec,
    l: &WeaponLoadout,
    env: &WeaponEnv,
    aimed: bool,
    tail: u32,
    mut out: impl FnMut(u32, f32, f32, Option<vetf_sim::weapon::Shot>),
) {
    let dt = d.tick_dt();
    let ads = if aimed { Buttons::ADS } else { 0 };
    let mut s = WeaponState::new(d, l);
    s.action = WeaponAction::Ready;
    for _ in 0..30 {
        s.step(d, l, &InputFrame { buttons: Buttons(ads), ..Default::default() }, env);
    }
    let mut recoil = ViewRecoil::default();
    let (mut yaw, mut pitch) = (0.0_f32, 0.0_f32);
    let mut left = None;
    for t in 0..4000 {
        if s.mag() == 0 {
            left.get_or_insert(tail);
        }
        if let Some(n) = &mut left {
            if *n == 0 {
                break;
            }
            *n -= 1;
        }
        let firing = left.is_none() && (s.fire_mode == FireMode::Auto || t % 2 == 0);
        let fire = if firing { Buttons::FIRE } else { 0 };
        let input = InputFrame { yaw, pitch, buttons: Buttons(fire | ads), ..Default::default() };
        let shot = s.step(d, l, &input, env).shot;
        out(t, yaw, pitch, shot);
        if let Some(shot) = shot {
            recoil.on_shot(gun, pitch.to_degrees(), shot.kick_pitch);
            pitch += shot.kick_pitch.to_radians();
            yaw -= shot.kick_yaw.to_radians();
        }
        pitch -= recoil.tick(gun, pitch.to_degrees(), dt).to_radians();
    }
}

fn main() {
    let d = GameData::embedded();
    let speed = &d.movement.speed;
    let env = |speed_frac: f32, sprinting: bool| WeaponEnv {
        mode: MoveMode::Ground,
        sprinting,
        crouched: false,
        speed_frac,
        broken_arms: false,
        hands_busy: false,
    };
    if std::env::args().nth(1).as_deref() == Some("trace") {
        println!("gun,aim,tick,pitch_deg,yaw_deg,shot");
        for gun in &d.weapons.weapons {
            let l = WeaponLoadout::resolve(&d, &gun.id, &[AmmoChoice::STANDARD], &[]).expect("a gun");
            for aimed in [false, true] {
                let aim = if aimed { "ads" } else { "hip" };
                spray(&d, gun, &l, &env(0.0, false), aimed, 60, |t, yaw, pitch, shot| {
                    let (p, y) = (pitch.to_degrees(), -yaw.to_degrees());
                    println!("{},{aim},{t},{p:.4},{y:.4},{}", gun.id, u8::from(shot.is_some()));
                });
            }
        }
        return;
    }
    let states = [
        ("standing", 0.0, false),
        ("walking", speed.walk / speed.jog, false),
        ("sprinting", speed.sprint / speed.jog, true),
    ];
    println!("gun,range_m,state,aim,player,shot,x,y,dx,dy,spread_deg");
    for gun in &d.weapons.weapons {
        let l = WeaponLoadout::resolve(&d, &gun.id, &[AmmoChoice::STANDARD], &[]).expect("a gun");
        for range in [10.0_f32, 25.0] {
            for (state, speed_frac, sprinting) in states {
                for aimed in [false, true] {
                    for player in 0..PLAYERS {
                        let mut n = 0;
                        spray(&d, gun, &l, &env(speed_frac, sprinting), aimed, 0, |_, yaw, pitch, shot| {
                            let Some(shot) = shot else { return };
                            let dir = shot_direction(yaw, pitch, shot.spread_deg, shot_seed(player, shot.seq));
                            let view = view_dir(yaw, pitch);
                            let (hit, aim) = (dir * (range / -dir.z), view * (range / -view.z));
                            n += 1;
                            println!(
                                "{},{range},{state},{},{player},{n},{:.4},{:.4},{:.4},{:.4},{:.4}",
                                gun.id,
                                if aimed { "ads" } else { "hip" },
                                hit.x,
                                hit.y,
                                hit.x - aim.x,
                                hit.y - aim.y,
                                shot.spread_deg
                            );
                        });
                    }
                }
            }
        }
    }
}
