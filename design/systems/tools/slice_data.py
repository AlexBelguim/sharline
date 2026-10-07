"""Single source of truth for the numbers in GDD_SLICE.md.

Run:  python "F:/git/val etf/design/systems/tools/slice_data.py"
Writes JSON data files to design/systems/data/ and prints markdown tables (TTK etc.)
that are pasted into GDD_SLICE.md. Change numbers HERE, re-run, re-paste.
"""
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)

TICK_HZ = 60

# ----------------------------------------------------------------------------- movement (no / Light halo)
MOVEMENT = dict(
    capsule=dict(radius=0.32, height_stand=1.80, height_crouch=1.25, height_slide=1.00),
    eye_height=dict(stand=1.60, crouch=1.10, slide=0.85, transition_s=0.15),
    speed=dict(walk=2.6, jog=4.8, sprint=7.0, crouch=2.4, backpedal_mult=0.85, sprint_max_angle_deg=45),
    ground=dict(accel=40.0, decel=36.0, counter_strafe_extra_decel=20.0, step_height=0.35, max_slope_deg=46,
                ground_snap=0.25),
    air=dict(gravity=19.0, jump_height=1.0, jump_v0=6.16, coyote_s=0.10, jump_buffer_s=0.10, air_accel=14.0,
             air_wish_speed=1.2, terminal_speed=40.0, max_horizontal_speed=12.0, max_horizontal_speed_boosted=16.0),
    fall_damage=dict(free_drop_m=7.0, legs_hp_per_m=12.0),
    slide=dict(min_entry_speed=5.5, boost=2.0, boost_cooldown_s=2.0, friction=4.5, end_speed=3.6,
               downhill_min_deg=8.0, max_speed=13.0, jump_keep_frac=0.90, steer_deg_per_s=90.0),
    mantle=dict(min_ledge=0.6, max_ledge=2.2, low_max=1.2, time_low_s=0.35, time_high_s=0.55, probe_forward=0.6,
                min_ledge_depth=0.4, min_headroom=1.25),
    jetpack=dict(fuel_s=1.6, kick_up_mps=3.0, kick_cost_s=0.12, min_fuel_frac=0.10, thrust=32.0, climb_cap=6.0,
                 air_accel=18.0, horizontal_cap=7.0, regen_delay_s=1.0, regen_full_s=3.2,
                 fade_band_m={"Light": [4.0, 5.0], "Medium": [3.6, 4.6], "Heavy": [3.0, 4.0]},
                 max_rise_m={"Light": 5.65, "Medium": 5.25, "Heavy": 4.65},
                 fire_spread_add_deg=3.0, ads_allowed=False),
    zipline=dict(attach_radius=1.2, snap_s=0.15, speed_flat=11.0, speed_min=8.0, speed_max=13.0, accel_s=0.3,
                 detach_keep_frac=0.7, detach_up=5.0, end_hop_up=3.0, reattach_block_s=0.5),
    noise_radius_m=dict(walk=0, crouch=0, jog=18, sprint=28, slide=24, land=22, jet_start=45, jet_loop=40,
                        zipline=30, mantle=12, reload=8, mag_check=5, heavy_mult=1.2, kestrel_mult=0.75),
)

# ----------------------------------------------------------------------------- health
ZONE_HP = {"head": 45, "torso": 120, "arms": 70, "legs": 85}
ZONE_MULT_DEFAULT = {"head": 1.30, "torso": 1.00, "arms": 0.80, "legs": 0.85}
SPILL_TO_TORSO = {"arms": 0.60, "legs": 0.70}   # damage past a broken limb flows to torso at this factor

# ----------------------------------------------------------------------------- halo
TIER_COLORS = {1: "white", 2: "blue", 3: "violet", 4: "gold"}
# capacity[core][tier-1]
CAPACITY = {
    "Bulwark": [65, 100, 130, 165],
    "Volt":    [50, 75, 100, 125],
    "Mender":  [40, 60, 80, 100],
    "Phase":   [35, 55, 70, 90],
}
REGEN = {  # delay after damage (s), delay after break (s), rate (shield/s)
    "Bulwark": (5.0, 8.0, 10.0),
    "Volt":    (4.0, 7.0, 15.0),
    "Mender":  (2.5, 5.0, 20.0),
    "Phase":   (3.5, 6.0, 15.0),
}
WEIGHT_BANDS = [("Light", 1, 4), ("Medium", 5, 8), ("Heavy", 9, 16)]   # protection score = tier x zones
WEIGHT_EFFECTS = {
    # move speed mult, accel mult, jet fuel mult, slide boost m/s, mantle time mult, energy drain per min, power cells
    "None":   dict(move=1.00, accel=1.00, fuel=1.00, slide_boost=2.0, mantle=1.00, energy_per_min=0.0, cells=0),
    "Light":  dict(move=1.00, accel=1.00, fuel=1.00, slide_boost=2.0, mantle=1.00, energy_per_min=2.0, cells=1),
    "Medium": dict(move=0.95, accel=0.95, fuel=0.90, slide_boost=1.7, mantle=1.10, energy_per_min=4.0, cells=2),
    "Heavy":  dict(move=0.88, accel=0.85, fuel=0.75, slide_boost=1.3, mantle=1.25, energy_per_min=8.0, cells=3),
}


def weight_class(tier, zones):
    if tier == 0 or zones == 0:
        return "None"
    s = tier * zones
    for name, lo, hi in WEIGHT_BANDS:
        if lo <= s <= hi:
            return name
    return "Heavy"


ARMORS = [
    # id, name, core, tier, coverage
    ("arm_none", "No halo", None, 0, []),
    ("arm_phase_runner", "Phase Runner", "Phase", 1, ["torso"]),
    ("arm_phase_ghost", "Phase Ghost", "Phase", 4, ["head"]),
    ("arm_mender_scout", "Mender Scout", "Mender", 2, ["head", "torso"]),
    ("arm_volt_line", "Volt Line", "Volt", 3, ["torso", "arms"]),
    ("arm_bulwark_assault", "Bulwark Assault", "Bulwark", 3, ["head", "torso", "arms"]),
    ("arm_bulwark_jugg", "Bulwark Juggernaut", "Bulwark", 4, ["head", "torso", "arms", "legs"]),
]
STATUS = {
    "Bulwark": "flinch (aim punch) taken -50% while shield > 0",
    "Mender": "fast out-of-combat regen (see regen table)",
    "Volt": "on break: shock pulse r=4 m, enemies slowed 30% for 1.5 s",
    "Phase": "immune to slow effects (Volt pulse, tagging slow)",
}


def armor_record(aid, name, core, tier, cov):
    wc = weight_class(tier, len(cov))
    rec = dict(id=aid, name=name, core=core, tier=tier, coverage=cov, weight_class=wc,
               power_cells=WEIGHT_EFFECTS[wc]["cells"],
               move_speed_mult=WEIGHT_EFFECTS[wc]["move"],
               energy_drain_per_min=WEIGHT_EFFECTS[wc]["energy_per_min"],
               gear_cost=tier * len(cov))
    if core:
        d, bd, r = REGEN[core]
        rec.update(capacity=CAPACITY[core][tier - 1], regen_delay_s=d, regen_delay_after_break_s=bd,
                   regen_per_s=r, status_effect=STATUS[core])
    else:
        rec.update(capacity=0)
    return rec


# ----------------------------------------------------------------------------- weapons
MAKO = dict(
    id="ar7_mako", name="AR-7 Mako", cls="assault_rifle", ballistics="hitscan",
    damage=37, falloff=[[0, 37], [25, 37], [50, 31], [80, 27]], min_damage=27, max_range_m=300,
    zone_mult=ZONE_MULT_DEFAULT, shield_pierce=0.0,
    rpm=720, fire_modes=["auto", "semi"], mag_default="mag_30",
    reload_tactical_s=2.10, reload_empty_s=2.65, reload_fast_drop_s=1.60, mag_check_s=1.00,
    equip_s=0.70, holster_s=0.40, ads_s=0.22, sprint_to_fire_s=0.20,
    move_mult_held=1.00, move_mult_ads=0.60,
    spread_deg=dict(ads_still=0.08, hip_still=0.70, crouch_mult=0.85,
                    move_full_ads=1.40, move_full_hip=2.60, move_threshold_frac=0.30,
                    air=4.0, slide=1.8, zipline=2.0, jetpack=3.0,
                    bloom_per_shot_ads=0.05, bloom_max_ads=0.80, bloom_per_shot_hip=0.12, bloom_max_hip=1.60,
                    bloom_decay_delay_s=0.08, bloom_decay_deg_per_s=3.0),
    recoil=dict(pattern="mako_recoil_pattern.json", ads_mult=0.85, hip_mult=1.00, crouch_mult=0.90,
                reset_after_s=0.30, recover_frac=0.60, recover_delay_s=0.10, recover_deg_per_s=15.0,
                view_punch_visual_deg=0.15),
)
WARDEN = dict(
    id="vk50_warden", name="VK-50 Warden", cls="bolt_sniper", ballistics="hitscan",
    damage=160, falloff=[[0, 160], [60, 160], [120, 150], [150, 140]], min_damage=140, max_range_m=500,
    zone_mult={"head": 2.00, "torso": 1.00, "arms": 0.80, "legs": 0.85}, shield_pierce=0.30,
    rpm=48, bolt_cycle_s=1.25, fire_modes=["bolt"], mag_default="mag_5",
    reload_tactical_s=2.80, reload_empty_s=3.40, reload_fast_drop_s=2.30, mag_check_s=1.20,
    equip_s=1.00, holster_s=0.55, ads_s=0.38, sprint_to_fire_s=0.32,
    move_mult_held=0.93, move_mult_ads=0.45,
    spread_deg=dict(ads_still=0.0, ads_unsettled=3.0, hip_still=6.0, crouch_mult=0.85,
                    move_full_ads=3.0, move_full_hip=8.0, move_threshold_frac=0.20,
                    air=8.0, slide=6.0, zipline=6.0, jetpack=10.0),
    sway=dict(idle_amp_deg=0.12, period_s=3.0, hold_breath_s=4.0, exhausted_mult=2.0, exhausted_s=2.0),
    recoil=dict(kick_pitch_deg=3.5, kick_yaw_rand_deg=0.4, recover_frac=0.70, recover_s=0.35),
    scope=dict(zoom_levels=[6.0, 12.0], glint_min_range_m=25, glint_cone_deg=15),
)

# per-shot view kick applied AFTER shot n (pitch up +, yaw right +), degrees.
MAKO_PATTERN = [
    (0.55, 0.00), (0.60, 0.02), (0.62, -0.03), (0.58, 0.04), (0.52, 0.08), (0.45, 0.12), (0.38, 0.15),
    (0.30, 0.18), (0.22, 0.20), (0.15, 0.22), (0.10, 0.18), (0.08, 0.10), (0.06, -0.05), (0.05, -0.18),
    (0.05, -0.25), (0.04, -0.28), (0.04, -0.28), (0.04, -0.25), (0.03, -0.20), (0.03, -0.12), (0.03, 0.00),
    (0.03, 0.10), (0.03, 0.18), (0.03, 0.22), (0.03, 0.22), (0.03, 0.18), (0.03, 0.10), (0.02, 0.00),
    (0.02, -0.10),
]
MAKO_PATTERN_LOOP_FROM = 20   # extended mags: after kick index 28 continue from index 20 (0-based)

# attachment modifiers: multiplicative unless noted. keys: ads_time, recoil_v, recoil_h, hip_spread, sway,
# move, reload, sprint_to_fire, zoom (absolute), other
ATTACHMENTS = [
    # optics
    dict(id="optic_reddot", cat="optic", fits=["ar7_mako", "vk50_warden"], zoom=1.15, ads_time=0.95, move=1.00),
    dict(id="optic_holo", cat="optic", fits=["ar7_mako", "vk50_warden"], zoom=1.25, ads_time=1.00, default_for=["ar7_mako"]),
    dict(id="optic_3x", cat="optic", fits=["ar7_mako", "vk50_warden"], zoom=3.0, ads_time=1.15, sway=1.10, ads_move=0.95,
         other="scope glint >= 40 m"),
    dict(id="optic_sniper", cat="optic", fits=["vk50_warden"], zoom=[6.0, 12.0], ads_time=1.00, default_for=["vk50_warden"],
         other="scope glint >= 25 m; scroll toggles 6x/12x"),
    dict(id="optic_thermal", cat="optic", fits=["vk50_warden"], zoom=4.0, ads_time=1.20, sway=1.10, move=0.99,
         other="white-hot view: bodies bright, world desaturated; no glint"),
    # stocks
    dict(id="mako_stock_standard", cat="stock", fits=["ar7_mako"], default_for=["ar7_mako"]),
    dict(id="mako_stock_precision", cat="stock", fits=["ar7_mako"], ads_time=1.10, recoil_v=0.90, recoil_h=0.90, sway=0.80, move=0.98),
    dict(id="mako_stock_light", cat="stock", fits=["ar7_mako"], ads_time=0.88, recoil_v=1.12, recoil_h=1.12, sway=1.15,
         sprint_to_fire=0.85),
    dict(id="warden_stock_standard", cat="stock", fits=["vk50_warden"], default_for=["vk50_warden"]),
    dict(id="warden_stock_folding", cat="stock", fits=["vk50_warden"], ads_time=0.90, sway=1.25, move=1.03, recoil_v=1.10),
    # magazines
    dict(id="mag_30", cat="mag", fits=["ar7_mako"], capacity=30, default_for=["ar7_mako"]),
    dict(id="mag_45", cat="mag", fits=["ar7_mako"], capacity=45, reload=1.12, ads_time=1.05, move=0.99),
    dict(id="mag_drum60", cat="mag", fits=["ar7_mako"], capacity=60, reload=1.35, ads_time=1.12, move=0.97),
    dict(id="mag_5", cat="mag", fits=["vk50_warden"], capacity=5, default_for=["vk50_warden"]),
    dict(id="mag_8", cat="mag", fits=["vk50_warden"], capacity=8, reload=1.15, ads_time=1.06),
    # under
    dict(id="grip_vertical", cat="under", fits=["ar7_mako"], recoil_v=0.88, ads_time=1.03),
    dict(id="grip_angled", cat="under", fits=["ar7_mako"], ads_time=0.92, recoil_h=0.94),
    dict(id="grip_stub", cat="under", fits=["ar7_mako"], hip_spread=0.88, sprint_to_fire=0.90, recoil_h=0.95),
    dict(id="ugl_launcher", cat="under", fits=["ar7_mako"], ads_time=1.15, sway=1.10, move=0.97,
         other="40 mm grenade, see UGL table"),
    dict(id="bipod", cat="under", fits=["vk50_warden"], ads_time=1.06, move=0.99,
         other="deployed: sway -80%, recoil -40%, look clamp yaw +-35 / pitch +-20 deg, deploy 0.40 s"),
    # side
    dict(id="laser", cat="side", fits=["ar7_mako", "vk50_warden"], hip_spread=0.80, ads_time=1.02,
         other="visible red dot always; beam visible <= 25 m; toggle"),
    dict(id="flashlight", cat="side", fits=["ar7_mako", "vk50_warden"], ads_time=1.02,
         other="cone 30 deg, 25 m; glare on enemies <= 15 m inside 12 deg; toggle"),
    # shield
    dict(id="shield_front", cat="shield", fits=["ar7_mako"], ads_time=1.20, move=0.96, sway=1.15, recoil_h=0.95,
         other="0.32 x 0.26 m plate, 250 HP, blocks bullets only, no repair in a life"),
]


# ----------------------------------------------------------------------------- damage model
def falloff(w, r):
    pts = w["falloff"]
    if r <= pts[0][0]:
        return pts[0][1]
    for (r0, d0), (r1, d1) in zip(pts, pts[1:]):
        if r0 <= r <= r1:
            return d0 + (d1 - d0) * (r - r0) / (r1 - r0)
    return w["min_damage"]


class Target:
    def __init__(self, armor):
        self.hp = dict(ZONE_HP)
        self.cap = armor.get("capacity", 0)
        self.shield = self.cap
        self.cov = set(armor.get("coverage", []))
        self.dead = False

    def hit(self, w, zone, r=10.0):
        raw = falloff(w, r) * w["zone_mult"][zone]
        direct = 0.0
        if zone in self.cov and self.shield > 0:
            pierce = raw * w["shield_pierce"]
            to_shield = raw - pierce
            absorbed = min(self.shield, to_shield)
            self.shield -= absorbed
            direct = pierce + (to_shield - absorbed)
        else:
            direct = raw
        self.apply(zone, direct)

    def apply(self, zone, dmg):
        if self.hp[zone] <= 0 and zone in SPILL_TO_TORSO:
            self.apply("torso", dmg * SPILL_TO_TORSO[zone])
            return
        before = self.hp[zone]
        self.hp[zone] = before - dmg
        if self.hp[zone] <= 0:
            if zone in ("head", "torso"):
                self.dead = True
            else:
                over = -self.hp[zone]
                self.hp[zone] = 0
                if over > 0:
                    self.apply("torso", over * SPILL_TO_TORSO[zone])


def shots_to_kill(w, armor, zone, r=10.0):
    t = Target(armor)
    for n in range(1, 200):
        t.hit(w, zone, r)
        if t.dead:
            return n
    return None


def ttk(w, n):
    if n is None:
        return None
    if "bolt_cycle_s" in w:
        return (n - 1) * w["bolt_cycle_s"]
    return (n - 1) * 60.0 / w["rpm"]


def main():
    armors = [armor_record(*a) for a in ARMORS]
    with open(os.path.join(DATA, "armors.slice.json"), "w") as f:
        json.dump(dict(zone_hp=ZONE_HP, weight_effects=WEIGHT_EFFECTS, capacity=CAPACITY,
                       regen={k: dict(delay_s=v[0], delay_after_break_s=v[1], rate_per_s=v[2]) for k, v in REGEN.items()},
                       weight_bands=WEIGHT_BANDS, presets=armors), f, indent=2)
    with open(os.path.join(DATA, "movement.slice.json"), "w") as f:
        json.dump(dict(units="metres, seconds, m/s, m/s2, degrees", tick_hz=TICK_HZ,
                       weight_effects=WEIGHT_EFFECTS, movement=MOVEMENT), f, indent=2)
    with open(os.path.join(DATA, "weapons.slice.json"), "w") as f:
        json.dump(dict(tick_hz=TICK_HZ, weapons=[MAKO, WARDEN], spill_to_torso=SPILL_TO_TORSO), f, indent=2)
    with open(os.path.join(DATA, "attachments_stats.slice.json"), "w") as f:
        json.dump(dict(note="multipliers on the base weapon stat; 1.0 = no change; missing key = 1.0",
                       attachments=ATTACHMENTS), f, indent=2)
    with open(os.path.join(DATA, "mako_recoil_pattern.json"), "w") as f:
        json.dump(dict(units="degrees of view kick applied after shot n (pitch up +, yaw right +)",
                       loop_from_index=MAKO_PATTERN_LOOP_FROM,
                       kicks=[dict(after_shot=i + 1, pitch=p, yaw=y) for i, (p, y) in enumerate(MAKO_PATTERN)]), f, indent=2)

    # cumulative pattern stats
    cp = cy = 0.0
    for i, (p, y) in enumerate(MAKO_PATTERN):
        cp += p
        cy += y
        if i + 1 in (3, 9, 12, 16, 20, 24, 29):
            print(f"after shot {i+1}: pitch {cp:.2f}, yaw {cy:+.2f}")

    print("\n### Armor presets")
    print("| id | core | tier | coverage | score | weight | capacity | regen delay / break / rate |")
    for a in armors:
        if a["core"]:
            print(f"| {a['id']} | {a['core']} | T{a['tier']} | {', '.join(a['coverage'])} | {a['gear_cost']} | "
                  f"{a['weight_class']} | {a['capacity']} | {a['regen_delay_s']} s / {a['regen_delay_after_break_s']} s / {a['regen_per_s']}/s |")
        else:
            print(f"| {a['id']} | - | - | - | 0 | None | 0 | - |")

    print("\n### Shots / TTK at 10 m")
    hdr = "| Target armor | Mako torso | Mako head | Mako legs only | Warden torso | Warden head |"
    print(hdr)
    for a in armors:
        row = [a["name"]]
        for w, z in ((MAKO, "torso"), (MAKO, "head"), (MAKO, "legs"), (WARDEN, "torso"), (WARDEN, "head")):
            n = shots_to_kill(w, a, z)
            row.append(f"{n} ({ttk(w, n):.2f} s)")
        print("| " + " | ".join(row) + " |")

    print("\n### Mako head one-tap range check")
    for r in (10, 25, 30, 34, 35, 40, 50, 80):
        d = falloff(MAKO, r)
        print(r, round(d, 2), round(d * 1.3, 2), "one-tap" if d * 1.3 >= ZONE_HP["head"] else "no")

    print("\n### Mako torso shots at range (unarmored / Volt Line)")
    for r in (10, 25, 40, 50, 80):
        print(r, shots_to_kill(MAKO, armors[0], "torso", r), shots_to_kill(MAKO, armors[4], "torso", r))

    # Warden one body shot then Mako follow-up
    print("\n### Warden torso hit, remaining state")
    for a in armors:
        t = Target(a)
        t.hit(WARDEN, "torso", 30)
        print(a["name"], "torso", round(t.hp["torso"], 1), "shield", round(t.shield, 1), "dead", t.dead)


if __name__ == "__main__":
    main()
