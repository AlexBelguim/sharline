//! Performance probe for measuring changes: off unless `VETF_PERF=1` (then nothing of it runs or is added).
//!
//! In a match (`--host showhome --live`, best with a fixed `--camera`), after `VETF_PERF_WARMUP` seconds (default
//! 8) it records `VETF_PERF_WINDOW` seconds (default 8) of:
//!
//! - frame time (`Time<Real>`): mean, p50, p90, p99;
//! - the main world's schedules per frame (a schedule before `First` to one after `Last`);
//! - the render world's prepare (extract commands .. bind groups) and render (graph, submit, present) time;
//! - GPU time for the whole frame and per pass, from Bevy's `RenderDiagnosticsPlugin` timestamps (a `gpu_frame`
//!   span around the render graph); `VETF_PERF_GPU=0` leaves the GPU timing out;
//! - entity, mesh and triangle counts once at the window's start.
//!
//! Then one `PERF` log line, and a JSON line appended to `VETF_PERF_OUT` if set. `VETF_PERF_TAG` names the run,
//! `VETF_PERF_EXIT=1` quits after the window, `VETF_PERF_BORDERLESS=1` makes a scripted run borderless fullscreen
//! on its monitor (scripted runs otherwise keep the windowed size from the command line).

use crate::AppState;
use crate::showhome_kit::ShowhomeKitMesh;
use bevy::app::MainScheduleOrder;
use bevy::diagnostic::DiagnosticsStore;
use bevy::ecs::schedule::ScheduleLabel;
use bevy::prelude::*;
use bevy::render::diagnostic::{
    DiagnosticsRecorder, RecordDiagnostics, RenderDiagnosticsPlugin, begin_diagnostics_frame, resolve_encoder,
};
use bevy::render::render_resource::CommandEncoderDescriptor;
use bevy::render::renderer::{PendingCommandBuffers, RenderDevice, RenderGraph, RenderGraphSystems};
use bevy::render::{Render, RenderApp, RenderSystems};
use bevy::window::{MonitorSelection, PrimaryWindow, WindowMode};
use std::collections::BTreeMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;

/// The GPU span around the whole render graph (the passes' spans nest under it on the render thread).
const FRAME_SPAN: &str = "gpu_frame";

pub fn enabled() -> bool {
    std::env::var_os("VETF_PERF").is_some_and(|v| v != "0")
}

fn env_f32(name: &str, default: f32) -> f32 {
    std::env::var(name).ok().and_then(|v| v.trim().parse().ok()).unwrap_or(default)
}

#[derive(ScheduleLabel, Debug, Clone, PartialEq, Eq, Hash)]
struct PerfBegin;
#[derive(ScheduleLabel, Debug, Clone, PartialEq, Eq, Hash)]
struct PerfEnd;

/// What the render world measured, shared with the main world.
#[derive(Resource, Clone, Default)]
struct Shared {
    /// (prepare ms, render ms) per frame while recording.
    render: Arc<Mutex<Vec<(f64, f64)>>>,
    recording: Arc<AtomicBool>,
}

#[derive(Resource, Default)]
struct PerfWindow {
    in_game_at: Option<f32>,
    started: bool,
    done: bool,
    frames_ms: Vec<f64>,
    main_ms: Vec<f64>,
    main_begin: Option<Instant>,
    /// Render diagnostics: (time of the last measurement taken, sum, count), and every frame's GPU total.
    passes: BTreeMap<String, (Option<Instant>, f64, u32)>,
    gpu_ms: Vec<f64>,
    counts: String,
}

pub struct PerfProbePlugin;

impl Plugin for PerfProbePlugin {
    fn build(&self, app: &mut App) {
        if !enabled() {
            return;
        }
        let gpu = std::env::var("VETF_PERF_GPU").map_or(true, |v| v != "0");
        if gpu {
            app.add_plugins(RenderDiagnosticsPlugin);
        }
        let shared = Shared::default();
        app.insert_resource(shared.clone()).init_resource::<PerfWindow>();
        app.init_schedule(PerfBegin).init_schedule(PerfEnd);
        {
            let mut order = app.world_mut().resource_mut::<MainScheduleOrder>();
            order.insert_before(First, PerfBegin);
            order.insert_after(Last, PerfEnd);
        }
        app.add_systems(PerfBegin, |mut w: ResMut<PerfWindow>| w.main_begin = Some(Instant::now()))
            .add_systems(PerfEnd, (main_end, measure, take_counts).chain())
            .add_systems(PostUpdate, borderless);
        if let Some(render_app) = app.get_sub_app_mut(RenderApp) {
            render_app
                .insert_resource(shared)
                .init_resource::<RenderClock>()
                .add_systems(Render, render_begin.in_set(RenderSystems::ExtractCommands))
                .add_systems(
                    Render,
                    before_render.after(RenderSystems::PrepareBindGroups).before(RenderSystems::Render),
                )
                .add_systems(Render, after_render.after(RenderSystems::Render).before(RenderSystems::Cleanup));
            if gpu {
                // Exclusive systems run on the thread that runs the schedule, so the span opens and closes on one
                // thread (the recorder keeps a span stack per thread).
                render_app
                    .add_systems(
                        RenderGraph,
                        gpu_frame_begin.in_set(RenderGraphSystems::Begin).after(begin_diagnostics_frame),
                    )
                    .add_systems(RenderGraph, gpu_frame_end.after(RenderGraphSystems::Render).before(resolve_encoder));
            }
        }
    }
}

// ---------------------------------------------------------------------------------------------- main world

fn main_end(mut w: ResMut<PerfWindow>) {
    if let Some(t0) = w.main_begin.take()
        && w.started
        && !w.done
    {
        let ms = t0.elapsed().as_secs_f64() * 1000.0;
        w.main_ms.push(ms);
    }
}

fn pct(v: &[f64], p: f64) -> f64 {
    if v.is_empty() {
        return f64::NAN;
    }
    let mut s = v.to_vec();
    s.sort_by(f64::total_cmp);
    s[((s.len() as f64 - 1.0) * p).round() as usize]
}

fn mean(v: &[f64]) -> f64 {
    if v.is_empty() { f64::NAN } else { v.iter().sum::<f64>() / v.len() as f64 }
}

fn stat(v: &[f64]) -> String {
    format!(
        "{{\"n\":{},\"mean\":{:.4},\"p50\":{:.4},\"p90\":{:.4},\"p99\":{:.4},\"max\":{:.4}}}",
        v.len(),
        mean(v),
        pct(v, 0.5),
        pct(v, 0.9),
        pct(v, 0.99),
        pct(v, 1.0)
    )
}

/// A render diagnostic's path without the frame span, so a pass reads the same whichever thread drew it.
fn pass_name(path: &str) -> String {
    let path = path.trim_start_matches("render/");
    match path.strip_prefix(FRAME_SPAN).and_then(|rest| rest.strip_prefix('/')) {
        Some(inner) if inner.contains('/') => inner.to_string(),
        _ => path.to_string(),
    }
}

fn measure(
    windows: Query<&Window>,
    time: Res<Time<Real>>,
    state: Res<State<AppState>>,
    shared: Res<Shared>,
    store: Option<Res<DiagnosticsStore>>,
    mut w: ResMut<PerfWindow>,
    mut exit: MessageWriter<AppExit>,
) {
    let now = time.elapsed_secs();
    if *state.get() != AppState::InGame || w.done {
        return;
    }
    let since = *w.in_game_at.get_or_insert(now);
    let (warmup, len) = (env_f32("VETF_PERF_WARMUP", 8.0), env_f32("VETF_PERF_WINDOW", 8.0));
    if !w.started {
        if now - since >= warmup {
            w.started = true;
            shared.recording.store(true, Ordering::Relaxed);
            info!("PERF window start ({:.1} s after the match began)", now - since);
        }
        return;
    }
    w.frames_ms.push(time.delta_secs_f64() * 1000.0);
    if let Some(store) = store {
        let total = format!("render/{FRAME_SPAN}/elapsed_gpu");
        for d in store.iter() {
            let path = d.path().as_str();
            let Some(m) = d.measurement().filter(|_| path.starts_with("render/")) else { continue };
            let entry = w.passes.entry(pass_name(path)).or_insert((None, 0.0, 0));
            if entry.0 == Some(m.time) {
                continue; // no new frame's data yet
            }
            *entry = (Some(m.time), entry.1 + m.value, entry.2 + 1);
            if path == total {
                w.gpu_ms.push(m.value);
            }
        }
    }
    if now - since < warmup + len {
        return;
    }
    w.done = true;
    shared.recording.store(false, Ordering::Relaxed);
    let render = std::mem::take(&mut *shared.render.lock().unwrap());
    let (prepare, system): (Vec<f64>, Vec<f64>) = render.into_iter().unzip();
    let total: Vec<f64> = prepare.iter().zip(&system).map(|(a, b)| a + b).collect();
    let tag = std::env::var("VETF_PERF_TAG").unwrap_or_else(|_| "run".into());
    let frames = &w.frames_ms;
    let fps = 1000.0 / mean(frames);
    let passes: Vec<String> = w
        .passes
        .iter()
        .filter(|(_, (_, _, n))| *n > 0)
        .map(|(k, (_, sum, n))| {
            let v = sum / *n as f64;
            if k.ends_with("elapsed_gpu") || k.ends_with("elapsed_cpu") {
                format!("\"{k}\":{v:.4}")
            } else {
                format!("\"{k}\":{v:.0}")
            }
        })
        .collect();
    let window = windows.iter().next().map(|w| (w.physical_width(), w.physical_height(), w.present_mode));
    let json = format!(
        "{{\"tag\":\"{tag}\",\"window\":\"{window:?}\",\"fps\":{fps:.1},\"frame_ms\":{},\"main_ms\":{},\"gpu_ms\":{},\
         \"render_prepare_ms\":{},\"render_system_ms\":{},\"render_total_ms\":{},\"counts\":{},\"passes\":{{{}}}}}",
        stat(frames),
        stat(&w.main_ms),
        stat(&w.gpu_ms),
        stat(&prepare),
        stat(&system),
        stat(&total),
        if w.counts.is_empty() { "{}" } else { &w.counts },
        passes.join(",")
    );
    info!(
        "PERF {tag}: {fps:.1} fps, frame {:.3} ms (p50 {:.3} p99 {:.3}), main {:.3} ms, gpu {:.3} ms, render prep \
         {:.3} ms, render_system {:.3} ms",
        mean(frames),
        pct(frames, 0.5),
        pct(frames, 0.99),
        mean(&w.main_ms),
        mean(&w.gpu_ms),
        mean(&prepare),
        mean(&system)
    );
    match std::env::var("VETF_PERF_OUT") {
        Ok(path) => {
            use std::io::Write;
            if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(&path) {
                let _ = writeln!(f, "{json}");
            }
        }
        Err(_) => info!("PERF json {json}"),
    }
    if std::env::var_os("VETF_PERF_EXIT").is_some() {
        exit.write(AppExit::Success);
    }
}

/// The counts, once, at the window's start (an exclusive system: it reads the whole world).
fn take_counts(world: &mut World) {
    let w = world.resource::<PerfWindow>();
    if !w.started || !w.counts.is_empty() {
        return;
    }
    let c = counts(world);
    world.resource_mut::<PerfWindow>().counts = c;
}

fn triangles(meshes: &Assets<Mesh>, mesh: &Mesh3d) -> u64 {
    // A mesh kept only in the render world has no data here (`try_`: it would panic).
    meshes.get(&mesh.0).and_then(|m| m.try_indices().ok()).map_or(0, |i| i.len() as u64 / 3)
}

/// Entity, mesh (all, visible) and triangle counts, and the Showhome kit's meshes per part.
fn counts(world: &mut World) -> String {
    let mut out = vec![format!("\"entities\":{}", world.entities().count_spawned())];
    let mut kit = BTreeMap::<String, (u32, u64)>::new();
    let (mut all, mut visible, mut tris_visible) = (0u32, 0u32, 0u64);
    let mut q = world.query::<(&Mesh3d, &ViewVisibility, Option<&ShowhomeKitMesh>)>();
    let meshes = world.resource::<Assets<Mesh>>();
    for (mesh, vis, part) in q.iter(world) {
        let tris = triangles(meshes, mesh);
        all += 1;
        if vis.get() {
            visible += 1;
            tris_visible += tris;
        }
        if let Some(part) = part {
            let e = kit.entry(format!("{:?}", part.0)).or_default();
            *e = (e.0 + 1, e.1 + tris);
        }
    }
    out.push(format!("\"meshes\":{all},\"visible_meshes\":{visible},\"tris_visible\":{tris_visible}"));
    let kit: Vec<String> = kit.iter().map(|(k, (n, t))| format!("\"{k}\":[{n},{t}]")).collect();
    out.push(format!("\"kit\":{{{}}}", kit.join(",")));
    format!("{{{}}}", out.join(","))
}

/// `VETF_PERF_BORDERLESS=1`: borderless fullscreen on the window's monitor, once it is shown.
fn borderless(mut windows: Query<&mut Window, With<PrimaryWindow>>, mut done: Local<Option<bool>>) {
    let want = *done.get_or_insert_with(|| std::env::var_os("VETF_PERF_BORDERLESS").is_some());
    let Ok(mut window) = windows.single_mut() else { return };
    if want && window.visible {
        window.mode = WindowMode::BorderlessFullscreen(MonitorSelection::Current);
        *done = Some(false);
    }
}

// ---------------------------------------------------------------------------------------------- render world

#[derive(Resource, Default)]
struct RenderClock {
    begin: Option<Instant>,
    before_render: Option<Instant>,
}

fn render_begin(mut c: ResMut<RenderClock>) {
    c.begin = Some(Instant::now());
}

fn before_render(mut c: ResMut<RenderClock>) {
    c.before_render = Some(Instant::now());
}

fn after_render(mut c: ResMut<RenderClock>, shared: Res<Shared>) {
    let now = Instant::now();
    let (Some(b), Some(r)) = (c.begin.take(), c.before_render.take()) else { return };
    if shared.recording.load(Ordering::Relaxed) {
        shared.render.lock().unwrap().push(((r - b).as_secs_f64() * 1000.0, (now - r).as_secs_f64() * 1000.0));
    }
}

fn gpu_frame_begin(world: &mut World) {
    let Some(recorder) = world.get_resource::<DiagnosticsRecorder>() else { return };
    let mut encoder = world
        .resource::<RenderDevice>()
        .create_command_encoder(&CommandEncoderDescriptor { label: Some("perf_probe_frame_begin") });
    recorder.begin_time_span(&mut encoder, FRAME_SPAN.into());
    world.resource_mut::<PendingCommandBuffers>().push([encoder.finish()]);
}

fn gpu_frame_end(world: &mut World) {
    let Some(recorder) = world.get_resource::<DiagnosticsRecorder>() else { return };
    let mut encoder = world
        .resource::<RenderDevice>()
        .create_command_encoder(&CommandEncoderDescriptor { label: Some("perf_probe_frame_end") });
    recorder.end_time_span(&mut encoder);
    world.resource_mut::<PendingCommandBuffers>().push([encoder.finish()]);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pass_names_drop_the_frame_span() {
        assert_eq!(pass_name("render/gpu_frame/main_opaque_pass_3d/elapsed_gpu"), "main_opaque_pass_3d/elapsed_gpu");
        assert_eq!(pass_name("render/bloom/elapsed_gpu"), "bloom/elapsed_gpu");
        assert_eq!(pass_name("render/gpu_frame/elapsed_gpu"), "gpu_frame/elapsed_gpu");
        assert_eq!(pct(&[3.0, 1.0, 2.0], 0.5), 2.0);
        assert!(pct(&[], 0.5).is_nan());
    }
}
