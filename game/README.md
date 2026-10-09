# SHARD/LINE: game code (`game/`)

Rust 1.91+ + Bevy 0.19 + lightyear 0.30, as chosen in `design/systems` (network diagram). It is a host-and-join
listen server: whoever hosts runs the server and plays in the same process, and friends join through Iroh or direct UDP.

![main menu](screenshots/main_menu.png)

## Build and run

```sh
cd game
cargo run --release -p val_etf          # main menu
cargo test --workspace                  # gameplay math, design-data sync, netcode serialization
```

Linux needs the usual Bevy packages: `libasound2-dev libudev-dev libxkbcommon-dev libwayland-dev`.

### Main menu
After mockups 04 / 04b (`design/ui/mockups`). The left nav has **PLAY** (with **HOST GAME** and **JOIN GAME**),
**GUN RANGE**, **SETTINGS** and **QUIT**; the PLAY flyout opens to its right. There is no **LOADOUT** entry for now
(user direction 2026-10-08): the loadout is picked in the lobby (**LOADOUT**) and from the ESC menu.

- **PLAY > HOST GAME:** lobby name, **MODE** (team deathmatch or free-for-all), who can join, max players
  (team deathmatch: even, 2-10; free-for-all: 2-8), port (default **UDP 47820**, or `--port`) and password
  (shown, not available yet). **CREATE LOBBY** opens the lobby on Showhome, where the host can still switch the
  mode under MATCH SETTINGS. A busy port is reported in the panel.
- **Free-for-all:** everyone against everyone, first to 25 kills (`ffa` in `rules.ron`). No teams and no SWITCH
  TEAM; every other player is an enemy (enemy colour on bodies and in the kill feed). You spawn on either side, at
  a point far from living enemies (with a little randomness). The HUD shows your kills against the leader's; the
  scoreboard is one list sorted by kills. The most kills wins (tie: fewer deaths, then whoever got there first).
- **GUN RANGE** hosts the range the same way, so friends can join it.
- **PLAY > JOIN GAME:** paste an `SL1-...` internet invite or a direct `ip:port` address.
  Legacy short LAN codes are also accepted. **PASTE** and Ctrl+V use the system clipboard.
  **RECENT** lists the last three games joined. **ON YOUR NETWORK** discovery is not built yet.
  Connection problems show under the field.
- **First launch:** with no saved profile, **CHOOSE YOUR CALLSIGN** opens over the menu: type a name (Enter or
  CONFIRM) or take the generated **USE AGENT-nnnn**. Esc does not skip it. Until then you show as `UNKNOWN`;
  the OS user name is never used.
- **Player card:** your name (**EDIT NAME**: 3-16 letters, digits, spaces, `-`, `_`, `.`), the loadout as HOST GAME's
  mode takes it (its armor tier, its one ammo type and magazine count) and its points against that mode's total
  (**OVER BUDGET** means the host will give you the default loadout).
- **Keys:** ↑↓ select (moving onto HOST GAME / JOIN GAME opens it), Enter confirm (or → into the flyout),
  Tab / Shift+Tab or ↑↓ inside a flyout, ←→ on a toggle, stepper or the tabs, Esc back to the nav.
- **Saved per user** (in `~/.config/shardline`, `%APPDATA%\shardline` or `~/Library/Application Support/shardline`;
  `VETF_CONFIG_DIR` overrides): the name (`profile.ron`), the recent games (`recent.ron`, with the mode each was
  joined in) and the loadout presets (`loadouts.ron`).

### Loadout
Opens from the lobby's **LOADOUT** and the ESC menu's **LOADOUT**; presets **A / B / C**, **+ SAVE AS**, **CONFIRM**.
- **Team deathmatch and free-for-all** (user direction 2026-10-08, `deathmatch_loadout` in `rules.ron`): the gun,
  its attachments and its **MAGAZINE** type (everyone carries six of it), then **one ARMOR tier** (T1 1/1/1/1 Light,
  T2 2/2/2/2 Medium, T3 3/3/1/1 Medium, T4 4/4/3/2 Heavy, as head / torso / arms / legs), then **one AMMO type** for
  all six magazines, then the points used against the total. Points: total 8; armor 1 / 2 / 3 / 5; ammo once,
  Standard 0, AP and RIP I / II / III 1 / 2 / 4; magazine standard 0, extended 1, drum 2. T4 armor and a tier III
  round never fit together. Every card shows its points, red when picking it would go over. No agent pick (these
  modes have no abilities; everyone keeps the jetpack): the host deals everyone a random agent when the match
  starts, kept for the match. No halo pick: everyone wears the one halo (Mender). The host shapes whatever a client
  sends the same way and refuses what is over the points. In the lobby a confirmed loadout is worn at once; in a
  match it applies at the next spawn.
- **Applying:** CONFIRM, or Esc / BACK when the picks are within the points. Over the points the first Esc shows
  a notice and a second Esc discards the edits. Opened from the death screen there is no CONFIRM: valid edits go
  to the host as they are made, and **RESPAWN** (with its timer) takes CONFIRM's place; over the points it reads
  OVER THE POINTS and stays blocked until the picks are fixed.
- **Keys:** Q / E switch column, the arrows move, Enter picks; BACK and CONFIRM close the focus order. 1 / 2 / 3
  load a preset, R resets the slot (or the ammo / magazine row) under the focus.
- **Gun range:** the full screen: agent, halo core, a tier per arc and up to six magazines, each with its own ammo
  (no budget).
- Presets saved by older builds load as they were; team deathmatch and free-for-all open them as their nearest
  picks (an armor tier, slot 1's ammo in six magazines).

### Hosting and joining

**Internet play (default):** choose HOST GAME with WHO CAN JOIN set to **Join code**.
The host runs the match; Iroh connects friends directly where possible and uses public relays when
necessary. Nobody needs Tailscale, a Steam account, or manual port forwarding.

1. Host a match or the gun range. Allow up to 30 seconds for the internet invite to become ready.
2. Hold Tab or press Esc to see the invite status, then press **F6** to copy the invite.
3. Send that invite to friends. They paste it in JOIN GAME and select JOIN LOBBY.
4. Invites start with `SL1-` and are valid only while that hosting session is running.
   Restarting hosting creates a new identity/invite. Recent entries for old sessions will no longer connect.

System clipboard support is enabled, including Ctrl+V and the PASTE button.
The public Iroh discovery and relay services need internet access and are rate-limited, with no uptime
guarantee. A relayed connection can have higher latency. If the host leaves, the match ends.

**Direct IP / LAN:** select Direct IP or LAN only when hosting to avoid starting Iroh.
Friends can still enter `ip:port` or the old short address code. The default is UDP 47820.
Internet direct-IP connections still require a publicly reachable port or a VPN.
The LAN discovery list is not implemented, and LAN only is not a firewall/access-control boundary.

**Transport:** Iroh runs on a separate worker and carries unreliable QUIC datagrams. Loopback sockets
adapt these to Lightyear's existing netcode transport, one socket per remote peer. Bounded fragmentation
preserves packet boundaries without adding reliable-stream head-of-line blocking. Leaving stops the
worker and releases its sockets. Gameplay authority, prediction and replication remain in Lightyear.
This adapter can also carry a future headless server's packets; headless hosting and persistent
extraction inventories are not implemented by this change.

Optional environment variables (set before launching):
- `VETF_IROH_RELAY_ONLY=1`: disable direct IP transport to test relay fallback.
- `VETF_IROH_RELAY_URL=https://relay.example.com`: use your own Iroh-compatible relay.
  Endpoint-ID discovery still uses the public Iroh discovery service.

Validation:
```sh
cargo test --workspace
# Opt-in public-infrastructure smoke test; normal tests do not need public relays:
cargo test -p val_etf public_invite_roundtrip_and_shutdown -- --ignored --nocapture
# Run the same test with VETF_IROH_RELAY_ONLY=1 to check the relay path.
```

A real friend on a different network should still confirm gameplay and latency before a release.

### Controls

Every key below is the default and can be rebound in SETTINGS > KEYBINDS; look speed, FOV, the crosshair, HUD
and video options are in SETTINGS too (changes apply at once and are saved to `settings.ron` in the config
folder).

| Key | Action |
|---|---|
| WASD, mouse | Move, look. Moving forward sprints (AUTO-SPRINT, on by default in SETTINGS > GAMEPLAY) |
| Shift (hold) | Walk (silent). Scoped with the Warden, it also holds your breath |
| Alt (hold) | Sprint, when AUTO-SPRINT is off |
| Space | Jump. Press again in the air for the jetpack (hold); hold while moving into a ledge to mantle |
| Ctrl / C | Crouch. While running or sprinting forward: slide |
| F | Grab zipline |
| LMB | Fire. Works on the run: the gun comes up from the sprint and you keep your speed |
| RMB | Aim (ADS). Never slows you, and aimed shots are accurate in every movement state (sprint, slide, air, jetpack, zipline) |
| H | Fire mode |
| R | Tap: reload the next magazine in slot order. Hold: magazine radial; release over a slot (or press 1-6) to load it. Magazines keep their slots |
| B | Heal ring: click an item; a region item opens a second ring to pick the region. Right click steps back |
| T | Mag check. Gives an estimate only; there is no ammo counter anywhere (genre rule) |
| 4 / 5 | Throw a smoke grenade / a molotov (each life carries some, shown bottom right). Smoke hides what is behind it and puts out fire; a shot through it leaves a short see-through tunnel |
| Tab (hold) | Scoreboard: kills, deaths and ping per player |
| F6 | Copy the host's invite to the system clipboard |
| Esc | Match menu: resume, loadout, settings, key reference, leave (or stop hosting) |
| Space / Enter (dead) | Death screen: RESPAWN once the timer is out. L opens LOADOUT; Esc the match menu |

### Command line (automation and testing)
`val_etf [--host showhome|range [--live] [--mode tdm|ffa]] [--join CODE|IP[:PORT]] [--name NAME] [--port PORT] [--width W --height H]
[--screenshot PATH --screenshot-after S] [--exit-after S] [--bot] [--yaw DEG] [--bots N]
[--weapon ID] [--ammo AMMO | --mags std,ap2,..] [--armor PRESET] [--attach A,B]
[--demo-ui reload|heal|heal-region|hud|menu-join|menu-join-ip|menu-host]`

- `--name` overrides the name saved from the main menu, for this run only (not saved; no first-launch prompt).
  `--host`, `--join`, `--bot`, `--screenshot` and `--demo-ui` runs never show the prompt either.
- `--demo-ui first-run|first-run-invalid|first-run-valid` opens the first-launch callsign prompt (empty, too
  short, valid) for screenshots.
- `--host showhome` opens the lobby, like CREATE LOBBY; add `--live` to start the match at once. `--mode ffa`
  hosts a free-for-all instead of team deathmatch (and preselects HOST GAME's MODE).
  `--demo-ui lobby-ready|lobby-switch|lobby-start` presses READY, SWITCH TEAM then READY, or READY then START MATCH
  a few seconds in, to test the lobby over the network; `lobby-ffa` (host) switches the lobby to free-for-all,
  readies and starts it.
- `--demo-ui settings-gameplay|settings-mouse|settings-keybinds|settings-video|settings-audio|settings-hud` opens
  that Settings tab from the main menu. `--demo-ui esc|esc-stop|esc-restart` opens the ESC menu or one of its
  confirms over a hosted match. `ads` holds aim down sights (`sprint` / `sprint-ads` hold sprint, and aim, for a
  `--bot`), `inspect` / `inspect-left` hold the gun across the view with its right / left side to the camera (to
  check attachments), `hud-fx` shows the damage flash and `overlay` keeps the performance overlay in a scripted run.
- `--demo-ui hit-fx` keeps hit markers (each kind in turn) and halo cracks going on the nearest other player, for
  screenshots of the hit feedback (with a `--bot` joining, or as the joiner).
- `--port` sets HOST GAME's port (and so `--host`'s).
- `VETF_ASSETS` points the game at another asset folder. Without it the game finds `game/assets` from wherever the
  exe was built (`target/debug`, `target/release`, `target/<triple>/release`) or an `assets` folder next to a
  copied exe.
- `--bot` drives the local player.
- `--bots N` (when hosting) adds N test bots once the game is up, like pressing ADD BOT N times in the lobby: for
  solo testing. A bot is a player the host runs itself (no client): it takes a seat (in team deathmatch on the
  team with fewer players), plays the default loadout, stands where it spawns and shoots at your head when it
  sees you. Its numbers are in `assets/data/bots.ron`.
- `--yaw` makes the bot hold a heading and shoot, which is useful for testing hits over the network.
- `--mags` lists magazines in slot order (up to six); `--ammo` loads every default magazine with one ammo.
- `--demo-ui reload|heal|heal-region` opens a ring menu for screenshots (the heal ones also hurt the host's player).
- `--demo-ui menu-join|menu-join-ip|menu-host` opens the main menu's JOIN GAME (code or direct IP tab) or HOST
  GAME flyout with its field focused, for screenshots. `--demo-ui loadout|loadout-ammo|loadout-attach` opens the
  Loadout screen (over the lobby or match with `--host` / `--join`). `--demo-ui loadout-set:TIER,AMMO[,MAG][,GUN]`
  (e.g. `loadout-set:3,ap3,mag_45`) also clicks that gun, magazine type, armor tier and ammo on the deathmatch
  layout; `loadout-pick:...` then confirms, readies in the lobby and (the host) starts the match: a host and a
  `--bot` joiner both pick and play.
- `--demo-ui impacts|impacts-sheet[:x,y,z]|impacts-live|impacts-idle` (in a match, best with `--camera`): bullet
  marks for screenshots. `impacts` fires once through a 9x5 grid over the view (the real shot path), `impacts-sheet`
  lays every surface kind (rows) in every variant (columns) on the face under the view centre (or toward x,y,z),
  `impacts-live` fires 12 shots a second at random points over the view (debris included) and `impacts-idle` fires
  none; those two log the marks, the debris and the frame rate every 2 s.
- **Screenshot and demo runs** (`--screenshot` or `--demo-ui`) ignore the desktop's display scale: the window
  renders at scale factor 1, so `--width 1920 --height 1080` gives exactly a 1920x1080 image, also on a HiDPI
  screen (a normal run follows Windows scaling, so 1600x900 at 200 % is a 3200x1800 window). They never grab or
  hide the mouse cursor, and the mouse does not turn the view or fire in the match, so a test run cannot
  capture your mouse. `--bot` runs do not grab the cursor either. Always pass `--exit-after` in automated runs.

For example, a local two-process test:

```sh
val_etf --host range --name HOST &
val_etf --join 127.0.0.1:47820 --name JOINER --bot --yaw 90
```

## Layout

| Crate | What |
|---|---|
| `crates/vetf_sim` | Engine-free gameplay: data loading, damage/halo/health pipeline, weapons (fire rate, reloads, mag checks, spread, bloom, recoil), the character controller and brush collision, hitboxes and lag compensation, and the Showhome and Range levels. No Bevy, so it is fast to test and runs identically on host and clients. |
| `crates/vetf_net` | The lightyear protocol: replicated components, `PlayerInput`, messages (`Hello`, `ShotClaim`, `HitConfirm`, `DamageTaken`, `KillFeed`, `ShotFx`), channels, and join codes. |
| `crates/val_etf` | The game binary: menu, hosting and joining, the host authority (`server.rs`), the local player (`client.rs`), the shared predicted simulation (`shared.rs`), blockout rendering and the HUD. |
| `assets/fonts` | Barlow and Barlow Condensed (SIL OFL, see `OFL.txt`), the mockups' fonts, compiled into the binary. |
| `assets/models/weapons` | The Mako and Warden, their stocks and magazines, and the optics and tactical attachments: copies of the Blender exports in the repository's `assets/weapons/` (Git LFS). `assets/data/weapon_models.ron` maps each gun and attachment id to its file and socket, and holds the first-person hip poses (`weapon_models.rs`). The Skink (hidden for now) has no model yet and keeps placeholder boxes. |
| `assets/data/*.ron` | **Every gameplay number.** They are loaded at start-up, so you can tune without rebuilding; the build also has a copy compiled in. `cargo test` fails if they drift from `design/systems/data/*.json`, except for the deliberate changes in [DESIGN_DELTAS.md](DESIGN_DELTAS.md). |

### Netcode model
The design is a listen server ticking at 60 Hz.

- **Inputs:** clients send inputs every tick, each packet repeating the last 10.
- **Prediction:** each client predicts its own movement and weapon, rolls back on mismatch, and interpolates
  other players about 100 ms behind.
- **Shots:**
  - The shooter's client raycasts against what it sees and sends a `ShotClaim`: shot number, ray, the tick it was
    viewing, zone and point.
  - The host has simulated the same shot from the same inputs. Ammo, fire rate and spread seed are
    host-authoritative.
  - The host checks the claim: muzzle position, aim cone, rewinding the victim by at most 200 ms, an inflated
    zone hitbox, and line of sight through the level. Then it applies halo and zone damage.
- **Replication:** the host sends snapshots at 30 Hz.

## Status: what works, what's next

**Works (tested):**
- Host and join over UDP, verified with two processes.
- Prediction and interpolation.
- Shot claims with lag compensation; hits, kills, kill feed and respawn.
- Death screen: a death cam that turns to your killer (no replay), the killer's gun, distance and a rough read
  of their health and halo, the life's damage taken and dealt per player and zone, LOADOUT and RESPAWN.
- TDM score, timer and match end; free-for-all (`--mode ffa`) kills, timer and match end.
- Per-arc halo shields and per-zone HP with spill.
- Two guns: AR-7 Mako and VK-50 Warden. The SK-9 Skink SMG (the only gun that loads RIP) is out for now: it stays
  in `weapons.ron` with `hidden: true` (see DESIGN_DELTAS 30).
- Ammo class × type × tier: one type for every magazine in team deathmatch and free-for-all, picked per magazine
  (up to six ordered magazines) in the gun range.
- Rulesets: team deathmatch has no bleeding or broken-limb penalties; the range runs the full rules.
- Healing items with a heal ring: whole-body items (the only kind in team deathmatch) and region items.
- Smoke grenades and molotovs (DESIGN_DELTAS 32): a deterministic, host-run throw with bounces; smoke clouds
  that hide players from bots and markers and put out fire; burning areas that hurt through halo and health.
- The full movement set: sprint, slide, jump, jetpack with design max-rise values, mantle, zipline, step-up and
  ramps.
- Recoil pattern and recovery; ADS behaviour.
- Mag check estimates.
- Both maps as blockouts.

**Not done yet:**
- UPnP and the LAN beacon (JOIN GAME's ON YOUR NETWORK tab, HOST GAME's LAN ONLY).
- Lobby passwords, and lobby names and player counts for other players (RECENT shows `—` for ping and players).
- Range targets and aim-lab modes. `maps::range_targets()` exists, but nothing spawns from it yet.
- Character abilities (Kestrel scan, Solace heal) and energy drain.
- Warden sway and hold-breath, the bipod, aim punch, and Bulwark flinch reduction.
- Network visibility: exact enemy halo values only after a scan. Today all vitals replicate to everyone.
- Real art: glTF characters, weapons and halos. Everything is blockout boxes for now.
- Security: netcode uses a fixed private key, so this is a prototype for friends only.

**Known limits:**
- Leg spraying is only faster than shooting the torso with RIP in the SMG, against bare legs (by design).
- Some "not standable" roofs are flat in the blockout.
- On a CPU software renderer running two copies of the game (this cloud container), the frame rate gets so low
  that lightyear can drop inputs (more than 64 ticks out). It is fine on real GPUs.
