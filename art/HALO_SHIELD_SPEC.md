# Halo shield system: armor as a readable halo

Armor is **equipment any agent can wear**. It projects an energy shield, which shows as a stylized tech
**halo floating above the head**. The halo's look encodes the armor's stats, so players can read it at a glance.
Shots against the shield throw hex-shard particles in the tier colour, and breaking it plays a crack burst.

## What the halo encodes
| Armor property | Visual | Readable from |
|---|---|---|
| **Tier / level** (T1–T4) | Halo **colour** (emissive), plus 1–4 small tier pips on the front of the ring | Far: colour. Mid: pips |
| **Coverage** (Head, Torso, Arms, Legs) | The ring is split into **4 arc segments**, one per zone. A covered zone's arc is lit; an uncovered one is dark, ghosted glass | Mid range |
| **Core type** (what kind of shield) | The **shape of the ring** (4 silhouettes, below) | Mid and far |
| **Power level** (drain on food/energy, like heavy armor in EFT) | **1–3 orbiting power cells** circling the halo. More cells means heavier drain and a stronger shield | Mid range |
| **Status effect** of the core | Particle trail / pulse colour on the cells, plus the hit-particle behaviour (engine VFX) | Close range, and on hit |

Arc order, seen from above with the agent facing −Y: **front = Head**, **left = Arms** (+X), **back = Torso**,
**right = Legs** (−X). Each arc carries a tiny raised glyph for its zone.

Tier colours (linear RGB, emissive): T1 white (0.85, 0.88, 0.92) · T2 blue (0.10, 0.45, 1.0) ·
T3 violet (0.55, 0.15, 1.0) · T4 gold (1.0, 0.62, 0.08). Unlit arc: dark smoked glass (0.02, 0.02, 0.025), alpha ≈ 0.5.

### Core types (proposal, all names are placeholders)
| Core | Ring silhouette | Fantasy | Example status effect |
|---|---|---|---|
| **Bulwark** | Thick **hexagonal** faceted ring | Highest capacity, slow regen | Reduced flinch while the shield is up |
| **Mender** | **Twin** thin concentric rings | Low capacity, regenerates out of combat | Slow passive shield regen |
| **Volt** | **Notched / crown** ring with short upward teeth | Medium capacity, punishes melee range | When it breaks, a shock pulse slows nearby enemies |
| **Phase** | Smooth **round** ring with a gap opposite the front | Light, low drain | Resistance to slow and bleed status |

## Readability layers (user decision)
Like gear in EFT, players must always be able to judge **how heavy an enemy is** before deciding to
engage. The fine details reveal themselves on hit or scan.

| State | What anyone can read |
|---|---|
| **Idle (always, any range)**: low glow, never invisible | **Weight class** (Light / Medium / Heavy) from the halo's **size, band thickness and number of power cells**, plus the **tier colour** at reduced brightness and the **core silhouette** |
| **Taking damage** | Full flare: lit/dark coverage arcs are clear, tier pips glow, and hex shards in the tier colour fly off. Remaining shield is visible as cracks |
| **Scanned** (Kestrel's eyepiece) | Everything, including exact core, status effect, power draw and remaining capacity (as a UI overlay) |

**Weight class** comes from total protection (tier × number of covered zones) and the power level:
- **Light**: halo scale 0.85, thin ring only, 1 power cell.
- **Medium**: scale 1.0, ring plus a medium outer **weight band**, 2 cells.
- **Heavy**: scale 1.2, ring plus a heavy, thick, armored-looking outer weight band, 3 cells, slower and heavier orbit.
A heavy halo must read as clearly bigger and chunkier than a light one in silhouette alone, even at 50 m and
with no colour. Your own halo also appears in the HUD.

## Model kit to build (`assets/shields/`, prefix `HALO`)
- `HALO_<Core>_Arc_<Zone>`: 4 core silhouettes × 4 arcs = 16 meshes. Each arc is a separate object, origin at
  the halo centre, ring radius ≈ 0.16 m (fits over any head), ring band about 0.012–0.03 m depending on core type.
- `HALO_<Core>_Band_Medium` / `HALO_<Core>_Band_Heavy`: 4 cores × 2 = 8 outer weight-band meshes that fit
  around each core's ring shape. Heavy must look clearly armored and thick.
- `HALO_TierPip`: one small diamond pip mesh; the engine shows 1–4 of them at fixed front positions
  (the positions are stored as empties `HALO_PIP_1..4`).
- `HALO_PowerCell`: a small capsule/crystal cell with a short orbit-trail fin. The engine orbits 1–3 of them.
- `HALO_Shard_A/B/C`: low-poly hex glass shards for hit and break particle meshes.
- Sprites (PNG, transparent): `hex_hit_flash.png`, `crack_overlay.png`, `shard_sprite.png`. White/greyscale,
  tinted by tier colour in-engine.
- **Pickup / loot items** `HALO_Core_<Core>`: the physical core device found in raids (hand-sized puck or
  canister, about 0.08–0.12 m). It echoes its ring silhouette and has a coloured glass window.
- Characters get a `<P>_SOCKET_Halo` empty about **0.22 m above the top of the head**, centred over the skull.
  The halo attaches there. It is not parented to head-bone rotation, so it stays level.
- `assets/shields/armor_catalog.example.json`: a data schema plus a few example armors
  (id, core, tier, coverage[], capacity, regen, power_cells, food_drain_mult, energy_drain_mult,
  move_speed_mult, status_effect).
- Showcase renders:
  - all 4 cores in T1–T4 colours;
  - a **Light / Medium / Heavy weight-class lineup**, also as a **pure black silhouette** to prove it reads without colour;
  - a coverage example (Head + Torso lit, Arms + Legs dark);
  - the halo on a character, in idle (dim) and hit (flared) states.
