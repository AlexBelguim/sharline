//! Which schedules run on Bevy's single-threaded executor.
//!
//! The frame is CPU-bound below 4K: the render world (prepare, then the render graph) is the long pole, the main
//! world runs beside it. Their schedules are many tiny systems, mostly chained, and on a many-core CPU the
//! multi-threaded executor's hand-offs between worker threads cost more than the systems themselves. Measured on
//! Showhome at 1080p (perf probe, `VETF_PERF=1`): the render world's `Core3d`, `RenderGraph` and `Render`
//! schedules plus the main world's `First` .. `Last` on the single-threaded executor took the frame from about
//! 4.6 ms to 3.8 ms; the extract schedule stayed faster multi-threaded. Systems that fan out internally
//! (`par_iter`, Bevy's visibility and transform passes) still use the task pools.
//!
//! The executors only change how systems are dispatched, not their order: the same ordering constraints and
//! the same sync points apply. `VETF_EXECUTOR=multi` puts Bevy's default back (to compare).

use bevy::core_pipeline::Core3d;
use bevy::ecs::intern::Interned;
use bevy::ecs::schedule::{ScheduleLabel, SingleThreadedExecutor};
use bevy::prelude::*;
use bevy::render::renderer::RenderGraph;
use bevy::render::{Render, RenderApp};

pub struct ExecutorPlugin;

/// The executor setup `VETF_EXECUTOR` asks for: single-threaded where it measured faster (the default), or
/// Bevy's multi-threaded executor everywhere (`multi`).
pub fn single_threaded(env: Option<&str>) -> bool {
    !env.is_some_and(|v| v.trim().eq_ignore_ascii_case("multi"))
}

/// The main world's per-frame schedules that run single-threaded.
fn main_schedules() -> [Interned<dyn ScheduleLabel>; 5] {
    [First.intern(), PreUpdate.intern(), Update.intern(), PostUpdate.intern(), Last.intern()]
}

impl Plugin for ExecutorPlugin {
    fn build(&self, app: &mut App) {
        if !single_threaded(std::env::var("VETF_EXECUTOR").ok().as_deref()) {
            info!("executor: Bevy's multi-threaded executor everywhere (VETF_EXECUTOR=multi)");
            return;
        }
        let single = |s: &mut Schedule| {
            s.set_executor(SingleThreadedExecutor::new());
        };
        for label in main_schedules() {
            app.edit_schedule(label, single);
        }
        if let Some(render_app) = app.get_sub_app_mut(RenderApp) {
            render_app.edit_schedule(Core3d, single).edit_schedule(RenderGraph, single).edit_schedule(Render, single);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn single_threaded_unless_asked_for_multi() {
        assert!(single_threaded(None));
        assert!(single_threaded(Some("single")));
        assert!(!single_threaded(Some(" Multi ")));
        assert_eq!(main_schedules().len(), 5);
    }
}
