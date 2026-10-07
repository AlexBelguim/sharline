# Settings · Video tab

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/08c_settings_video.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/settings.html",
 "/home/user/sharline/design/ui/mockups/_src/common.css"
]

## purpose
Display mode, resolution, render scale, frame limit, V-sync, brightness, the performance overlay, and graphics quality, with a competitive-visibility rule.

## layout
Pane pattern (a). Two 754-wide column cards x340 and x1118, full height y112..976. Rows on a 64px pitch, 50 tall.

COLUMN A 'DISPLAY'
- h2 y131.
- Rows: Window mode y167; Resolution y231; Render scale y295; Frame limit y359; V-sync y423; Brightness y487.
- Sub-heading 'PERFORMANCE OVERLAY' at y563 (margin-top 12).
- Row Show y599.
- Controls at x591.

COLUMN B 'QUALITY'
- h2 y131, with a right micro tag at x1724 y138.
- Rows: Preset y167; Anti-aliasing y231; Shadows y295; Stylized outlines y359; Bloom y423; Particles y487; Contact shadows · SSR y551; Motion blur · vignette y615.
- Note at y689 (margin-top 10), 712x36.
- Controls at x1369.

## elements
DISPLAY
- 'WINDOW MODE': seg 'FULLSCREEN' (110w) | 'BORDERLESS' (selected, 110w) | 'WINDOWED' (99w).
- 'RESOLUTION': dropdown 240x36 '2560 × 1440 · 165 Hz' with chevron.
- 'RENDER SCALE', sub-label '3D only. UI always renders at native': slider 400 at 66% + field 70 '100 %'.
- 'FRAME LIMIT': seg '60' | '144' | '165' (selected) | '240' | 'OFF'.
- 'V-SYNC', sub-label 'Bevy PresentMode': seg 'OFF (AutoNoVsync)' (selected, 154w) | 'ON (AutoVsync)' (131w). Mixed case as written.
- 'BRIGHTNESS': slider at 50% + field '0'.
- Sub-heading 'PERFORMANCE OVERLAY'.
- 'SHOW': seg 'OFF' | 'FPS + FRAME TIME' (selected) | '+ NETWORK'.

QUALITY
- h2 'QUALITY'. Micro 'PRESET: HIGH · CUSTOM'.
- 'PRESET': seg 'LOW' | 'MEDIUM' | 'HIGH' (selected) | 'ULTRA'.
- 'ANTI-ALIASING': seg 'OFF' | 'FXAA' | 'SMAA' (selected) | 'TAA' | 'MSAA 4×'.
- 'SHADOWS': seg 'LOW' | 'MEDIUM' (selected) | 'HIGH'.
- 'STYLIZED OUTLINES', sub-label 'Ink edges on characters and props': switch ON (green #52E5A5).
- 'BLOOM', sub-label 'Halos, optics, jet cores': seg 'OFF' | 'LOW' (selected) | 'HIGH'.
- 'PARTICLES (BEVY_HANABI)': seg 'LOW' | 'HIGH' (selected).
- 'CONTACT SHADOWS · SSR': two switches, gap 12 (x1369 and x1427): ON, OFF.
- 'MOTION BLUR · VIGNETTE': two switches: OFF, OFF.
- Note: 'Competitive rule: settings may never hide halos, hex shards or enemy outlines. "Low" only drops their particle count, not their visibility.'

## data_bindings
SETTINGS: control, range/options, default
- Window mode: seg, default BORDERLESS.
  - Window.mode = WindowMode::Fullscreen(MonitorSelection::Current, VideoModeSelection::Current) / BorderlessFullscreen(MonitorSelection::Current) / Windowed.
- Resolution: dropdown of the current monitor's video modes from the Monitor component, as 'W × H · R Hz'.
  - Default: native.
  - In WINDOWED, the list sets the window size.
  - With no monitor data, show 'Native' alone and disable the dropdown.
  - Note: the game starts at 1600x900 windowed today (Cli width/height).
- Render scale: slider + field 50–125 %, step 5, default 100 % (66% fill matches a 50–125 range).
- Frame limit: seg 60 / 144 / <monitor refresh, if not already listed> / 240 / OFF.
  - Default: monitor refresh (165 in the mockup).
  - Unknown refresh: 60 / 144 / 240 / OFF, default OFF.
- V-sync: seg, default OFF. Sets Window.present_mode AutoNoVsync / AutoVsync (main.rs uses AutoNoVsync today).
- Brightness: slider + field −50…+50, step 1, default 0. Maps to the camera ColorGrading exposure, ±1 EV at the ends.
- Performance overlay: seg OFF / FPS + FRAME TIME / + NETWORK, default FPS + FRAME TIME (as drawn).
  - FPS and frame time come from FrameTimeDiagnosticsPlugin.
  - The network part is RTT and packet loss from lightyear.
- Preset: seg LOW/MEDIUM/HIGH/ULTRA, default HIGH. Picking one writes all quality values. Proposed table:
  - LOW: FXAA, shadows LOW, bloom OFF, particles LOW, contact OFF, SSR OFF
  - MEDIUM: SMAA, MEDIUM, LOW, LOW, ON, OFF
  - HIGH: SMAA, HIGH, LOW, HIGH, ON, OFF
  - ULTRA: TAA, HIGH, HIGH, HIGH, ON, ON
  - The micro reads 'PRESET: <NAME>', plus ' · CUSTOM' when any quality value differs from the preset. The mockup state (HIGH preset with MEDIUM shadows) is such a case.
- Anti-aliasing: seg, default SMAA. Maps to Bevy Msaa::Off/Sample4 and the Fxaa, Smaa and TemporalAntiAliasing components.
- Shadows: seg, default MEDIUM. Maps to the DirectionalLightShadowMap size 1024/2048/4096 and the cascade count. render.rs has one DirectionalLight with shadows on.
- Stylized outlines: switch, default ON.
- Bloom: seg, default LOW. Bloom component off / low intensity / high intensity.
- Particles: seg, default HIGH.
- Contact shadows: switch, default ON. SSR: switch, default OFF (ScreenSpaceReflections).
- Motion blur: switch, default OFF (MotionBlur). Vignette: switch, default OFF.

## interactions
- All controls apply instantly. Window mode and resolution apply on click; proposed: a 10 s 'Keep this display mode? KEEP / REVERT (9)' confirm for fullscreen and resolution changes.
- Changing any individual quality value keeps the preset highlighted and appends ' · CUSTOM' to the micro.
- Clicking a preset overwrites all quality values.

## adaptations
1. Several effects do not exist in the blockout renderer yet: render scale, outlines, bloom, particles, SSR, contact shadows, motion blur, vignette, and a frame limiter.
   - Bevy has no built-in frame limiter: use bevy_framepace if it supports 0.19, or a small sleep-based limiter.
   - Render scale needs a render-to-texture 3D camera.
   - Show rows the game cannot honour yet as disabled (opacity .35) at their default values, rather than hiding them, so the screen still mirrors the mockup.
   - The working ones today: window mode, resolution, V-sync, brightness (ColorGrading), AA, shadows, and the performance overlay.
2. Duplicate: the Gameplay tab's 'Show net graph' switch duplicates '+ NETWORK' here. Bind both to one setting (switch ON = '+ NETWORK').
3. Engine-jargon copy: 'Bevy PresentMode', '(AutoNoVsync)' and 'PARTICLES (BEVY_HANABI)' are dev-facing. Mirror them as drawn, but suggest the local session relabel them, e.g. sub-label 'Lower latency when off' and 'PARTICLES'. bevy_hanabi is not a dependency of the game today.
4. The competitive-rule note conflicts with the HUD tab's Enemy outline 'OFF' option; see the HUD tab.

## assets
Icon i-chev (resolution dropdown). No images.

