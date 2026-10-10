# Direction log — decisions from the user (these override concept BRIEFs)

1. **Weapons are modular.** Swappable stock, foregrip, optic, magazine. Mako upgrades: front shield, laser,
   flashlight, underbarrel grenade launcher. Warden upgrades: thermal optic, front bipod.
   Full spec: `art/WEAPON_MODULAR_SPEC.md`.
2. **Mako: `art/concepts/mako/v09.png` is THE master reference ("perfect").** It has no iron sights
   (ignore the small block behind the optic). Match v09:
   - a long, slightly squared free-float handguard with 3 rows of rounded slots, running nearly to the muzzle,
     with a full-length top rail;
   - **NO ammo counter** (user: "leave out the ammo count"). There is no "30" display and no glowing counter
     anywhere on the Mako. Its only emissive is the optic's reticle glint, which belongs to the optic;
   - a slotted birdcage-style flash hider (stylized), not an angular compensator;
   - graphite receiver;
   - **bone** angular collapsible stock, pistol grip and magazine (the mag has a long vertical window slot);
   - the default optic `optic_holo` is a **bone-coloured** box holo sight with an ice reticle glint.
   v04/v02 are secondary references for the straight side profile.
3. **Kestrel's face/eyepiece: use `art/concepts/kestrel/v06.png`.** Her LEFT eye stays visible:
   the eyepiece is a small **translucent teal hexagonal lens** (glowing teal rim, see-through tinted glass,
   the eye clearly visible behind it). It is held by a thin dark strap running around the head
   to a compact earpiece on her left ear. It is NOT an opaque visor and must not cover the brow or cheek.
   Also from v06: blue-black asymmetric bob with teal-dyed ends (long on her right side), tall charcoal collar
   with teal piping, bone chest plate with dark straps, and a calm, determined expression.
   Her chest plate is outfit styling only (no tier pips), see item 5.
4. **Varga is dropped.** The heavy breacher archetype read too bulky and male-coded. The second agent is now
   **SOLACE**, a field medic / healer support with a more typical, graceful female hero-shooter design.
   Her brief is `art/concepts/solace/BRIEF.md`; the old `art/concepts/varga/` folder is archived and must not be used.
5. **Armor becomes energy shields that any agent can wear.** It is not part of any character's design.
   A universal **shield core** module sits at the same socket on every agent. The tier (T1 white, T2 blue,
   T3 violet, T4 gold) shows in the colour of the hex-shard particles when the shield is hit or cracks.
   A recon skill (Kestrel's eyepiece scan) can read an enemy's tier from long range.
   Details are in `art/STYLE_GUIDE.md`, "Shields instead of armor plates".
6. **Shield = halo above the head** (supersedes the back-mounted shield core in item 5). The halo's colour,
   lit arcs (coverage zones), ring shape (core type) and orbiting power cells (drain / power level) encode
   the armor's stats. Full spec: `art/HALO_SHIELD_SPEC.md`. Characters need a `<P>_SOCKET_Halo` empty.
7. **The halo is dim when idle but never hides how heavy someone is.** As with gear in EFT, anyone can always
   read the **weight class** (Light / Medium / Heavy) from the halo's size, outer weight band and power-cell
   count, plus the dimmed tier colour. Coverage arcs, pips and shards flare up on hit. Exact stats only show
   up through a scan. See "Readability layers" in `art/HALO_SHIELD_SPEC.md`.
8. **No ammo counters on ANY weapon (genre rule).** Not knowing exactly how many rounds you have left, and
   checking or topping off magazines yourself, is part of the extraction-shooter feel. The Warden loses its
   receiver counter too, so neither gun has a glowing ammo display. Base guns may then have **no emissive at
   all**; only optics carry a small reticle/status glow. Magazine **window slots** (like on the Mako v09
   mag) stay. They are physical, approximate, and useful for a mag-check animation. Model a few visible
   cartridges behind the window so a mag check can show roughly how full it is.
9. **Per-arc armor tiers and ammo × tier** (decided with the game session; details in `game/DESIGN_DELTAS.md`).
   Every halo arc (head / torso / arms / legs) has its own tier, colour and shield pool. Weight class = sum of the
   arc tiers. Ammo is chosen per loadout as a type (Standard / AP / Shrapnel / RIP / Slug) and a tier (I–III), and
   halo penetration depends on weapon class × type × tier.
10. **Map themes chosen.** TDM map = **A "Showhome"**: near-future 3D-printed show homes in a half-built suburb,
    with a delivery truck in the street and a construction crane (`design/maps/tdm/concepts/_candidates/A_showhome_*`).
    Gun range / hub "The Yard" = **B: Nordic fjord** setting, with the HQ facility by a fjord, snowy mountains,
    cool light, and the long range running toward a tunnel in the cliff (`design/maps/range/concepts/themeB_*`).
11. **TRELLIS is for placeholders only. NEVER use TRELLIS (or any image-to-3D) for maps.** The current TRELLIS
    characters (Kestrel, Solace) are stand-ins. They don't look polished, so they get remade properly once the game
    works. Maps are built procedurally in Blender as a modular kit, textured with Krea2-made stylized textures, and must
    look like the concept art (Showhome = `design/maps/tdm/concepts/_candidates/A_showhome_*`).
12. **Optic rules.** 1x sights (red dot, holo, projector) are looked THROUGH in 3D, so they need a large clear
    aperture: front and rear windows about the same size, thin frames, no tunnel. Magnified optics (3x, 6/12x, thermal)
    switch to a scope view in code, so their lens size is cosmetic. 1x sights keep a slight ADS zoom (red dot 1.15,
    holo 1.25, projector about 1.2; values in `game/assets/data/attachments.ron`).
    **New high-end optic `optic_projector`** (Valorant-style): a low-profile housing whose flaps fold open on ADS and
    project a holographic reticle frame in mid-air, with no glass. Game side: flap animation on ADS, hologram above
    about 80% ADS, a data entry in attachments.ron.
13. **Warden follows `art/concepts/warden/concept_main.png` proportions.** The user found the first build bulky and
    stumpy: slim handguard over a separate lower, more exposed fluted barrel, smaller mag, slim skeleton stock.
14. **First launch asks for a player name** ("callsign"). It is saved to the profile and editable later. `--name` still
    overrides it for automated runs.
15. **Hosting always goes through a lobby, which is its OWN FULL SCREEN** (mockup `design/ui/mockups/png/06_lobby.png`, not a popup). Players join the lobby first; the host picks map and game mode (plus
    score and time limit) there and starts the match. Today: TDM on Showhome plus the gun range. More modes and maps
    plug into the same selectors later.
16. **Playtest round 1 (2026-10-08): run-and-gun feel.**
    - **Movement:**
      - Sprint is the default and holding Shift walks.
      - A slide starts from a normal run, not only from a full sprint.
    - **Aiming:**
      - Aiming never slows movement and works in every movement state (sprint, slide, air, jetpack, zipline).
      - Aimed shots are accurate in every state. Hip fire keeps its movement penalties.
      - Shooting while sprinting is allowed.
      - Aiming down sights is much faster.
    - **Guns:**
      - Recoil is much stronger, the AR's most of all. Recoil control is the skill check.
      - The AR's time to kill is lower.
      - The SMG is weak at range.
    - **Feel:**
      - A slight camera wobble while sprinting and shooting.
      - The gun sways a little.
      - Tracers are more visible.
      - Hit markers and shield cracks show on the player that was hit, not at the crosshair.
      - The default crosshair is a small cross.
      - An empty gun clicks when you pull the trigger.
    - **Modes:** a free-for-all deathmatch mode next to TDM.
    - **Keys:** Heal defaults to B, and fire mode moves to H.
17. **Playtest round 2 (2026-10-08): gunplay and a simpler loadout.**
    - **Recoil:**
      - Standing still, every gun has a fixed recoil pattern with no randomness, so it can be learned.
      - Moving adds random bloom on top of that pattern, Apex-style. Moving is never more accurate than standing still.
      - Aimed shots stay accurate while moving (item 16): aimed bloom is small, hip fire takes most of it.
    - **TDM and FFA loadout:**
      - There is no LOADOUT button on the start screen for now.
      - There is no agent pick, because these modes have no abilities. The jetpack stays.
      - Armor is ONE tier pick (T1-T4). A tier is a fixed combination of the existing per-arc tiers (no new armor):
        T1 = 1/1/1/1 (head/torso/arms/legs, Light), T2 = 2/2/2/2 (Medium), T3 = 3/3/1/1 (Medium), T4 = 4/4/3/2
        (Heavy, the best combination the loadout allows). There is only one halo, so no halo pick.
      - Everyone carries 6 magazines of the magazine type they pick, all loaded with the one ammo type they pick.
      - Point costs and the point total are reset so the choice is a trade-off: T4 armor plus the best ammo does
        not fit.
    - **Agents in TDM and FFA:** once the agent models are done, every player gets a random agent at the start of
      the match (there is no pick).
    - **Telling friend from foe:** in team modes, teammates get a soft glow. Enemies get NO glow and no colour tell.
      The way teammates are identified must carry over unchanged into the extraction mode (squad members glow,
      everyone else looks plain).
    - **Grass:** the lawn needs a new look. The hedges and the bullet holes are kept.
    - **Performance:** 270 fps (4K borderless, HIGH) should be higher. Look for what holds the frame rate back.
18. **Playtest round 3 (2026-10-08).**
    - **Warden:** hip fire gets a penalty even standing still. It is not random: the barrel drifts on a fixed sway that
      the crosshair shows.
    - **AR recoil:** a T shape. It climbs straight up first, then swings left and right across the top.
    - **Attachments:** stocks lower vertical recoil only; front grips lower horizontal recoil only.
    - **Loadout:**
      - A NO HALO armor option for 0 points.
      - The MAG attachment is the magazine pick (you always carry 6), with no separate magazine row.
      - Every pick shows its point cost at all times, and the total is always visible.
    - **Bullet marks:** none on lawns.
    - **Slide:** faster and longer.
    - **Clipping:** fix seeing into walls while sliding, and getting stuck in the zipline pylon at the end of a ride.
    - **Laser:** draws a visible beam, within 25 m.
    - **AR damage falloff is gentler:** no sudden extra hit around 45 m (proposal: 46 to 35 m, 42 at 60 m, 38 at 90 m).
    - **Bullet penetration:** glass, fences and thin bushes/hedges let bullets through, with a small damage loss. Walls,
      concrete and vehicles stay solid. Guns stay hitscan. Penetration depends on how much material the bullet
      crosses, so the corner of a thick bush can be shot through while its middle stops bullets. Bullet holes in
      glass and thin materials are see-through where possible.
    - **Physical materials:** every surface has a material id (glass, wood, sheet metal, foliage, concrete, ...). It
      is authored in Blender on the art materials and on convex `COL_` collision volumes, then exported as
      `collision.json`. The game builds collision from it and measures thickness itself. Spec:
      `art/briefs/MAP_MATERIALS_SPEC.md`. The remade map follows it.
      Bullets go through interior drywall with a big damage loss; house outer walls stop them. AP rounds lose less
      damage through materials.
    - **Loot containers** (for extraction): many kinds of container, each a reusable prop with type ids:
      backpacks, duffels, weapon and ammo boxes, metal crates, toolboxes, cabinets, PC cases, electrical boxes,
      safes, barrels, hidden stashes. **Lootable means slightly open** (a door ajar, a drawer out, a lid
      cracked); decor stays closed. Brief: `art/briefs/showhome_rebuild/03_LOOT_CONTAINERS.md`.
    - **Props** go into a reusable library shared by all maps. Free CC0/CC-BY models are allowed when they are
      restyled to our look. Fences are open and thin. Each boundary between surfaces gets one edge treatment.
    - **Build mode:** an in-game editor. The modelling agent builds the fixed kit and the main props as instances.
      The user moves, deletes and adds library props and sets every loot spot, spawn, extract and invisible wall,
      saved in `placements.ron`, which the agent never overwrites. Brief:
      `art/briefs/showhome_rebuild/02_BUILD_MODE.md`. It comes before the map rebuild.
    - **Death screen:** a death cam that turns to show where you were shot from (no replay of the fight), a LOADOUT
      button, a RESPAWN button with the countdown, and a recap of damage taken and given, per zone, for that life.
    - **Applying loadout changes:**
      - From the death screen there is no CONFIRM: the RESPAWN button applies the changes.
      - While alive, CONFIRM works, and Esc applies the changes too when they are within the points.
    - **Test bot for solo testing:** a host-side bot that stands still and aims at your head when it sees you. The
      host gets ADD BOT / REMOVE BOT in the lobby, plus `--bots N` on the command line.
    - **Variable scopes:**
      - The Warden's scope zooms smoothly from 6x to 12x with the scroll wheel.
      - A NEW, more expensive 1x-3x variable optic next to the fixed 3x, which stays.
      - The zoom is remembered per player and per optic.
      - Both reticles are a thin line cross.
    - **Recoil tune after testing:**
      - The Mako's T has a 15-round stem, about 70 % more total climb over a 30-round mag, and a 60 % wider bar.
      - The recoil reset is gradual: the pattern rewinds step by step after a pause, and a slow tap is always the
        first bullet.
    - **Air control:** you can steer sideways in the air. Strafe jumping is allowed up to 9 m/s, and past that you
      only turn.
    - **Mag check:**
      - Pressing the key tilts the gun so you see the magazine and shows the estimate popup.
      - The magazine window shows a coarse fill level that you cannot count.
    - **Bots** give up their seat automatically when a real player joins.
    - **Loadout screen:** shows the real gun model with its selected attachments, and you can drag to rotate it.
    - **The SMG (Skink) is removed for now.** Its data stays so it can come back.
    - **Death recap v2:**
      - It covers your own life only.
      - It shows kill icons (headshot or body) and "your last fight": the players you damaged in the last 5 s
        but did not kill, as silhouettes with your total damage and shield damage. It never shows their remaining
        health.
      - There are no per-body-part columns.
      - The Tab scoreboard shows assists and KDA.
    - **Kill streaks** (TDM/FFA):
      - Milestones appear in the kill feed.
      - A map-wide banner and stinger play at 5; a voice line follows later.
      - A golden ember aura shows from 5 (not the ally glow).
      - The streak count sits left of health.
      - At 3 you get full health and shield; at 5 your magazines refill. A grenade reward comes later.
    - **Smoke and molotovs:**
      - Throwables that use the painted card look of the hedges.
      - Bullets carve a see-through tunnel through smoke for a moment.
      - Smoke puts out molotov fire.
    - **Exact ammo option** (an exception to "no exact ammo counters"): in TDM, FFA and the range, a setting (off by
      default) shows a permanent exact ammo counter on the HUD (and in the mag-check popup). In TDM/FFA it is a host
      match setting.
    - **Assists:**
      - The kill feed shows "KILLER + HELPER".
      - The helper gets a small ASSIST popup with a sound; a voice line comes later.
      - Deaths by fall, fire or (later) bleeding still give assists.
    - **One player model for now: Solace** (from the user's AI-generated model, with the hip drone removed). Kestrel
      is parked. **Agents as separate characters are dropped for now.** Everyone uses the same model, and abilities can
      differ later as a loadout choice. Her robe and accents come in several colours (team or cosmetic variants).
      Krea2 and Qwen Image may be used for her textures and depth.
    - **Character system:** a test session after the current queue decides between a MODULAR system (base body plus
      clothing and hair parts, colour masks, an editor, cosmetics later sold as items) and WHOLE-BODY SKINS (AI models
      like Solace on one shared skeleton). The test: the Rain base in our style, rigged, one fitted outfit, two
      hairstyles and a helmet, next to Solace.
    - **Streak extras, free-for-all only:**
      - From a 5 streak, each kill adds +5 % movement speed, up to a cap.
      - The streaker is revealed to everyone through walls (a name marker with a bounty icon). This is a deliberate
        bounty exception to "no enemy tells".
      - After 10, the announcement repeats every 5 kills.
    - **Laser:** V turns it on and off. Your own dot stays visible while scoped. When the gun is lowered or busy
      (sprint, reload, heal, ...), the beam follows the barrel.
    - **Planned modes:**
      - Low-gravity snipers: Warden only, no armor, no loadout, one shot kills.
      - Grenade launcher only: no jetpack, faster movement.
