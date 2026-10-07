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
