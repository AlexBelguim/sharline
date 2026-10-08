//! A measuring tool for the parallax depth (nothing happens unless `VETF_STRAFE` is set): with `--camera`, the
//! fixed camera steps by `dx,dy,dz` metres `frames` times and one screenshot is saved per step, so swimming at
//! box edges and shimmer in motion can be measured frame to frame (`assets/fx/depth/strafe.sh`).
//!
//! `VETF_STRAFE=dx,dy,dz,frames[,hold_s[,start_s]]`, `VETF_STRAFE_OUT=<path prefix>` (`<prefix>_00.png`, ...).
//! Each step is held `hold_s` (default 0.5 s) and shot at the end of its hold; the first step is held
//! `start_s` longer (default 3 s) after the match view appears, while the map's textures finish loading.

use crate::config::Cli;
use crate::render::ViewCamera;
use bevy::prelude::*;
use bevy::render::view::screenshot::{Screenshot, save_to_disk};
use bevy::transform::TransformSystems;

pub(super) fn plugin(app: &mut App) {
    let plan = std::env::var("VETF_STRAFE").ok().and_then(|v| StrafePlan::parse(&v));
    let out = std::env::var("VETF_STRAFE_OUT").ok();
    if let (Some(plan), Some(out)) = (plan, out) {
        app.insert_resource(Strafe { plan, out, next_at: None, taken: 0 })
            .add_systems(PostUpdate, strafe.before(TransformSystems::Propagate));
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct StrafePlan {
    step: Vec3,
    frames: u32,
    hold: f32,
    start: f32,
}

impl StrafePlan {
    fn parse(v: &str) -> Option<Self> {
        let n: Vec<f32> = v.split(',').map(|s| s.trim().parse().ok()).collect::<Option<_>>()?;
        if n.len() < 4 || n[3] < 1.0 {
            return None;
        }
        Some(StrafePlan {
            step: Vec3::new(n[0], n[1], n[2]),
            frames: n[3] as u32,
            hold: n.get(4).copied().unwrap_or(0.5).max(0.1),
            start: n.get(5).copied().unwrap_or(3.0).max(0.0),
        })
    }
}

#[derive(Resource)]
struct Strafe {
    plan: StrafePlan,
    out: String,
    /// When the step on screen is shot (set on the first frame of the match view).
    next_at: Option<f32>,
    taken: u32,
}

impl Strafe {
    /// The step to show now, and whether to shoot it this frame (then the next step gets its full hold).
    fn tick(&mut self, now: f32) -> (u32, bool) {
        let next_at = *self.next_at.get_or_insert(now + self.plan.start + self.plan.hold);
        let step = self.taken.min(self.plan.frames - 1);
        let shoot = self.taken < self.plan.frames && now >= next_at;
        if shoot {
            self.taken += 1;
            self.next_at = Some(now + self.plan.hold);
        }
        (step, shoot)
    }
}

fn strafe(
    cli: Res<Cli>,
    time: Res<Time>,
    mut s: ResMut<Strafe>,
    mut cams: Query<&mut Transform, With<ViewCamera>>,
    mut commands: Commands,
) {
    let Some((at, target)) = cli.camera else { return };
    if cams.is_empty() {
        return;
    }
    let (i, shoot) = s.tick(time.elapsed_secs());
    let off = s.plan.step * i as f32;
    for mut tr in &mut cams {
        *tr = Transform::from_translation(at + off).looking_at(target + off, Vec3::Y);
    }
    if shoot {
        let path = format!("{}_{:02}.png", s.out, i);
        info!("strafe step {i}: saving {path}");
        commands.spawn(Screenshot::primary_window()).observe(save_to_disk(path));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strafe_holds_each_step_then_shoots_it() {
        assert_eq!(StrafePlan::parse("0.02,0,0"), None);
        assert_eq!(StrafePlan::parse("a,0,0,4"), None);
        let plan = StrafePlan::parse("0.02, 0, -0.02, 3, 0.5, 1").unwrap();
        assert_eq!(plan.step, Vec3::new(0.02, 0.0, -0.02));
        assert_eq!((plan.frames, plan.hold, plan.start), (3, 0.5, 1.0));
        let mut s = Strafe { plan, out: String::new(), next_at: None, taken: 0 };
        assert_eq!(s.tick(10.0), (0, false), "the match view appears");
        assert_eq!(s.tick(11.4), (0, false), "first step held start + hold");
        assert_eq!(s.tick(11.5), (0, true));
        assert_eq!(s.tick(11.6), (1, false), "then the camera moves on");
        // A slow frame shoots late; the next step still gets its whole hold.
        assert_eq!(s.tick(12.3), (1, true));
        assert_eq!(s.tick(12.7), (2, false));
        assert_eq!(s.tick(12.8), (2, true));
        assert_eq!(s.tick(20.0), (2, false), "all shot; the last step stays");
    }
}
