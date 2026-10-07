# Settings · Audio tab

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/08d_settings_audio.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/settings.html",
 "/home/user/sharline/design/ui/mockups/_src/common.css"
]

## purpose
Per-category volume mix, output device, mix profile, and gameplay audio cues: shield-hit tink per tier, headshot sound, an approximate low-mag cue (no exact counts), and play in background.

## layout
Pane pattern (a). Two 754-wide column cards, rows on a 64px pitch.

COLUMN A 'VOLUME' (x340)
- h2 y131.
- Rows at y167, 231, 295, 359, 423, 487, 551.
- Each control is a .meter: slider 340x4 at x591, gap 10, number field 64x36 at x941. The space right of x1005 stays empty.

COLUMN B 'OUTPUT & CUES' (x1118)
- h2 y131.
- Rows: Output device y167; Mix y231; Shield-hit sound y295; Headshot sound y359; Low-mag cue y423; Play in background y487.
- Note at y561 (margin-top 10).
- Controls at x1369.

## elements
VOLUME (slider fill % = value)
- 'MASTER' 80
- 'WEAPONS' 90
- 'FOOTSTEPS & MOVEMENT', sub-label 'Jetpack, slide, zipline': 100
- 'ABILITIES & HALOS' 85
- 'HIT AND KILL SOUNDS' 70
- 'INTERFACE' 60
- 'MUSIC', sub-label 'Menus and match end only': 40

OUTPUT & CUES
- 'OUTPUT DEVICE': dropdown 300x36 'System default' with chevron. Mixed case as written.
- 'MIX': seg 'HEADPHONES' (selected, 113w) | 'SPEAKERS' (95w) | 'NIGHT (compressed)' (163w, mixed case as written).
- 'SHIELD-HIT SOUND', sub-label 'Glassy "tink" per tier, pitch rises T1 → T4': switch ON.
- 'HEADSHOT SOUND': switch ON.
- 'LOW-MAG CUE', sub-label 'Lighter trigger click in roughly the last 15 % (open question)' (wraps to 2 lines): seg 'OFF' (selected) | 'ON'.
- 'PLAY IN BACKGROUND': switch OFF.
- Note: 'No voice chat in the prototype. Friends use Discord or similar. Text chat is in the lobby and in match.'

## data_bindings
SETTINGS: control, range, default
- Volumes: slider + integer field 0–100, step 1. Defaults: Master 80, Weapons 90, Footsteps & movement 100, Abilities & halos 85, Hit and kill sounds 70, Interface 60, Music 40.
  - Effective volume = master × category / 10000.
  - Master maps to Bevy GlobalVolume. Each category scales PlaybackSettings.volume for sounds tagged with that category.
- Output device: dropdown, default 'System default'.
- Mix: seg, default HEADPHONES.
- Shield-hit sound: switch, default ON. Headshot sound: switch, default ON.
- Low-mag cue: seg, default OFF.
  - When ON, the trigger click changes in roughly the last 15% of the magazine.
  - Approximate by design. It must never reveal an exact count; keep it consistent with the mag-check estimate bands in vetf_sim.
- Play in background: switch, default OFF. When the window is unfocused, mute GlobalVolume.

## interactions
- Sliders and fields as in the shell.
- Proposed: releasing a volume slider plays a short sample from that category (Weapons: a Mako shot; Interface: a click) once sounds exist.
- Switches toggle on click.

## adaptations
1. The game has no audio yet: no AudioPlayer anywhere in game/crates. Keep every row enabled and saved so the values are ready, and apply them when sound lands. Master can apply right away via GlobalVolume.
2. Output device: Bevy's audio (rodio) plays on the system default device only. Show the dropdown with the single item 'System default', disabled (opacity .35), until device selection is built.
3. Mix (headphones/speakers/night) needs a compressor or limiter on the output. Disable the row until that exists, default HEADPHONES.
4. Low-mag cue is marked '(open question)' in the copy. Keep it OFF by default and flag it to the local session as a design decision: the no-exact-ammo rule allows an approximate cue.
5. Glyph: '→' in 'T1 → T4' is missing from Barlow; use a symbol span or write 'T1 to T4'.
6. The tier pitch steps (T1 to T4) follow the halo tiers; the per-arc halo tiers mean one hit plays the tink of the struck arc's tier.

## assets
Icon i-chev (output device dropdown). No images.

