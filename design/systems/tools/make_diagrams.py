"""Draws the exact diagrams for GDD_SLICE.md (matplotlib, no image model).

Run:  python "F:/git/val etf/design/systems/tools/make_diagrams.py"
Out:  design/systems/diagrams/*.png
"""
import json
import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Ellipse, Polygon

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "diagrams")
DATA = os.path.join(ROOT, "data")
os.makedirs(OUT, exist_ok=True)

INK = "#1d2330"
MUTED = "#5b6474"
TEAL = "#00a596"
TEAL_BG = "#e3f6f3"
CORAL = "#e8584a"
CORAL_BG = "#fde9e6"
ICE = "#3d8fd6"
ICE_BG = "#e6f1fb"
GOLD = "#d08a00"
GOLD_BG = "#fff3d6"
GREY_BG = "#f2f3f6"
VIOLET = "#7a3fd6"
VIOLET_BG = "#efe7fc"
RED = "#c62828"

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "text.color": INK,
                     "axes.edgecolor": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK})


def canvas(w=16, h=10, xmax=160, ymax=100):
    fig = plt.figure(figsize=(w, h), dpi=110)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, ymax)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    return fig, ax


def box(ax, x, y, w, h, title=None, lines=(), fc=GREY_BG, ec=INK, lw=1.6, title_size=13, size=10.5,
        title_color=INK, pad=1.6, line_gap=2.9, align="left", rounding=1.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={rounding}",
                                fc=fc, ec=ec, lw=lw, zorder=2))
    ty = y + h - pad
    if title:
        tx = x + w / 2 if align == "center" else x + pad
        ax.text(tx, ty, title, fontsize=title_size, fontweight="bold", va="top",
                ha="center" if align == "center" else "left", color=title_color, zorder=3)
        ty -= line_gap + 0.9
    for ln in lines:
        tx = x + w / 2 if align == "center" else x + pad
        ax.text(tx, ty, ln, fontsize=size, va="top", ha="center" if align == "center" else "left",
                color=INK, zorder=3)
        ty -= line_gap


def arrow(ax, p0, p1, label=None, color=INK, lw=1.8, rad=0.0, style="-|>", ls="-", label_pos=0.5,
          label_off=(0, 0), size=10, label_fc="white", ms=16, zorder=4, label_color=None):
    a = FancyArrowPatch(p0, p1, arrowstyle=style, mutation_scale=ms, color=color, lw=lw,
                        connectionstyle=f"arc3,rad={rad}", linestyle=ls, zorder=zorder)
    ax.add_patch(a)
    if label:
        # approximate the label point on the arc
        mx = p0[0] + (p1[0] - p0[0]) * label_pos
        my = p0[1] + (p1[1] - p0[1]) * label_pos
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        # arc3 control point offset
        mx += -dy * rad * 0.5 * (1 - abs(2 * label_pos - 1)) * 2 * 0.5
        my += dx * rad * 0.5 * (1 - abs(2 * label_pos - 1)) * 2 * 0.5
        ax.text(mx + label_off[0], my + label_off[1], label, fontsize=size, ha="center", va="center",
                color=label_color or color, zorder=5,
                bbox=dict(boxstyle="round,pad=0.25", fc=label_fc, ec="none", alpha=0.95))
    return a


def badge(ax, x, y, n, color=INK, r=1.55, size=10):
    ax.add_patch(Ellipse((x, y), r * 2, r * 2, fc=color, ec="white", lw=1.2, zorder=6))
    ax.text(x, y - 0.05, str(n), color="white", fontsize=size, fontweight="bold", ha="center", va="center", zorder=7)


# ============================================================================ 1. network
def net_architecture():
    fig, ax = canvas(17, 10.6, 170, 106)
    ax.text(3, 102.5, "Network architecture: listen server (host = server + player in one process)",
            fontsize=17, fontweight="bold", va="top")
    ax.text(3, 98.0, "Rust + Bevy 0.19 + lightyear 0.30 (HostClient mode, UDP + netcode.io)."
            "  Fixed simulation tick 60 Hz on every machine.",
            fontsize=11.5, color=MUTED, va="top")

    # host PC
    ax.add_patch(FancyBboxPatch((3, 30), 66, 63, boxstyle="round,pad=0,rounding_size=2", fc="#fafbfc", ec=TEAL, lw=2.4))
    ax.text(5, 91, "HOST PC   val_etf.exe  ->  Host game", fontsize=14, fontweight="bold", color=TEAL, va="top")
    ax.text(5, 87.2, "one Bevy App, one World; the host never talks to itself over a socket", fontsize=10.5, color=MUTED, va="top")
    box(ax, 6, 52, 60, 32, "SERVER ROLE (authoritative)", [
        "FixedUpdate 60 Hz: movement, weapons, abilities, halo, damage",
        "Validates every client input + shot claim (trust but verify)",
        "Lag-comp history: hitbox poses for the last 0.5 s (30 ticks)",
        "   rewinds a victim at most 200 ms when checking a claim",
        "Match rules: TDM score, timer, respawn, spawn protection",
        "Replicates state to clients at 30 Hz (configurable 20/30/60)",
        "Network visibility: exact enemy halo values only after a scan",
    ], fc=TEAL_BG, ec=TEAL)
    box(ax, 6, 31.5, 36, 18, "LOCAL PLAYER (HostClient)", [
        "input -> same tick, 0 ms latency",
        "render, HUD, audio, menus",
        "no prediction or rollback needed",
    ], fc="white", ec=TEAL)
    box(ax, 44, 31.5, 22, 18, "PORT HELPERS", [
        "UPnP (igd-next):",
        "  map UDP 47820, lease 2 h",
        "LAN beacon UDP 47821",
        "join code shown in lobby",
    ], fc="white", ec=TEAL, size=10)
    arrow(ax, (24, 49.5), (24, 52), color=TEAL, style="<|-|>", lw=2)
    ax.text(25.5, 50.7, "in-process", fontsize=9.5, color=TEAL, va="center")

    # router + internet
    box(ax, 75, 62, 22, 14, "HOME ROUTER / NAT", ["UDP 47820 -> host LAN IP", "(UPnP or manual forward)"],
        fc=GOLD_BG, ec=GOLD, size=10, title_size=12)
    ax.add_patch(Ellipse((86, 45), 26, 15, fc=GREY_BG, ec=MUTED, lw=1.6, ls="--"))
    ax.text(86, 47, "INTERNET", fontsize=13, fontweight="bold", ha="center", color=MUTED)
    ax.text(86, 43, "public IPv4 of the host", fontsize=10, ha="center", color=MUTED)
    arrow(ax, (69, 69), (75, 69), color=GOLD, style="<|-|>", lw=2.2)
    arrow(ax, (86, 62), (86, 52.5), color=GOLD, style="<|-|>", lw=2.2)

    # clients
    for i, y in enumerate((68, 48, 28)):
        box(ax, 118, y, 49, 17.5, f"FRIEND CLIENT {i + 1}" if i < 2 else "FRIEND CLIENT N (max 9 remote)", [
            "own player: PREDICTED (rollback <= 20 ticks)",
            "other players: INTERPOLATED (~100 ms behind)",
            "sends inputs every tick + last 10 (packet loss)",
            "sends shot claims {tick, ray, hit zone}",
        ], fc=ICE_BG, ec=ICE, size=10, title_size=12)
        arrow(ax, (99, 45 + (i - 1) * 3), (118, y + 9), color=ICE, style="<|-|>", lw=1.8, rad=0.0)

    # traffic legend
    box(ax, 104, 87, 63, 13.5, None, [], fc="white", ec="#c9ced8", lw=1.0)
    ax.text(106, 98.6, "Traffic per remote client (10 players, worst case)", fontsize=11, fontweight="bold", va="top")
    ax.text(106, 95.0, "client -> host: inputs 60 Hz, ~4-6 KB/s", fontsize=9.8, va="top")
    ax.text(106, 92.0, "host -> client: snapshots 30 Hz + events, ~15-20 KB/s", fontsize=9.8, va="top")
    ax.text(106, 89.0, "host upload for 9 clients: ~1.5 Mbit/s", fontsize=9.8, va="top")

    # fallback lane
    ax.add_patch(FancyBboxPatch((3, 3), 164, 23, boxstyle="round,pad=0,rounding_size=2", fc="#fbfbfd", ec="#c9ced8", lw=1.2))
    ax.text(5, 24.2, "How a friend reaches the host (pick the first that works; the join code always holds the address to dial)",
            fontsize=12.5, fontweight="bold", va="top")
    cols = [
        ("A  LAN", "same network: LAN list via beacon,", "no setup at all", TEAL_BG, TEAL),
        ("B  UPnP / port forward", "router opens UDP 47820 for the host;", "fails on CGNAT / double NAT", GOLD_BG, GOLD),
        ("C  VPN mesh", "Tailscale / ZeroTier / Radmin VPN:", "join code uses the 100.x VPN IP", VIOLET_BG, VIOLET),
        ("D  Steam relay (later)", "steamworks + Steam Datagram Relay,", "app id 480 only for tests", ICE_BG, ICE),
    ]
    for i, (t, l1, l2, fc, ec) in enumerate(cols):
        box(ax, 5 + i * 40.5, 5, 38.5, 14.5, t, [l1, l2], fc=fc, ec=ec, size=10, title_size=12)
    fig.savefig(os.path.join(OUT, "net_architecture.png"), dpi=110)
    plt.close(fig)


# ============================================================================ 2. damage flow
def diamond(ax, cx, cy, w, h, text, fc=GOLD_BG, ec=GOLD, size=10.5):
    ax.add_patch(Polygon([(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)],
                         closed=True, fc=fc, ec=ec, lw=1.8, zorder=2))
    ax.text(cx, cy, text, fontsize=size, ha="center", va="center", zorder=3, fontweight="bold")


def damage_flow():
    fig, ax = canvas(17, 12.5, 170, 125)
    ax.text(3, 122.5, "Damage pipeline: bullet -> validation -> zone -> halo -> zone HP -> result", fontsize=17,
            fontweight="bold", va="top")
    ax.text(3, 118.2, "All steps after the claim run on the HOST only, in FixedUpdate. Numbers are the slice defaults "
            "(GDD_SLICE.md sections 2-3).", fontsize=11.5, color=MUTED, va="top")

    # column 1: client + validation
    box(ax, 4, 96, 50, 17, "1  CLIENT fires at tick T", [
        "predicted locally: muzzle flash, tracer, sound",
        "local ray hits a hitbox -> 'pending' hit marker",
        "sends FireClaim{T, origin, dir, seq, hit?}",
    ], fc=ICE_BG, ec=ICE, size=10.3)
    box(ax, 4, 70, 50, 21, "2  HOST validates the shot", [
        "weapon equipped, not sprinting / mantling",
        "fire interval >= 5 ticks (Mako) / 75 (Warden)",
        "round in chamber (host owns ammo count)",
        "fail -> shot ignored, client resynced",
    ], fc=TEAL_BG, ec=TEAL, size=10.3)
    box(ax, 4, 40, 50, 25, "3  Lag-compensated hit check", [
        "view tick = T - client interpolation delay",
        "rewind victim hitboxes (cap 200 ms back)",
        "claimed point inside zone hitbox",
        "   inflated by 0.15 m + 0.03 s x victim speed",
        "LOS ray shooter eye -> point: no static world",
        "fail -> no damage (counted as a miss)",
    ], fc=TEAL_BG, ec=TEAL, size=10.3)
    box(ax, 4, 14, 50, 21, "4  Raw damage", [
        "raw = base x falloff(range) x zone mult",
        "Mako 37 (25 m) -> 31 (50 m) -> 27 (80 m+)",
        "Warden 160 (60 m) -> 150 (120 m) -> 140",
        "zone mult  head 1.3 (Warden 2.0) | torso 1.0",
        "                arms 0.8 | legs 0.85",
    ], fc="white", ec=INK, size=10.3)
    arrow(ax, (29, 96), (29, 91), lw=2)
    arrow(ax, (29, 70), (29, 65), lw=2)
    arrow(ax, (29, 40), (29, 35), lw=2)

    # column 2: halo
    diamond(ax, 86, 90, 36, 17, "zone covered by\nthe halo AND\nshield > 0 ?")
    ax.plot([54, 59, 59], [24, 24, 90], color=INK, lw=2, zorder=4, solid_joinstyle="round")
    arrow(ax, (58.95, 90), (68, 90), lw=2)
    box(ax, 63, 52, 46, 26, "5a  HALO absorbs", [
        "pierce = raw x p   (Mako p = 0, Warden p = 0.30)",
        "-> pierce goes straight to zone HP",
        "rest = raw - pierce -> shield takes min(shield, rest)",
        "overflow (rest - absorbed) -> zone HP",
        "regen waits: delay per core (2.5-5 s)",
        "shield hits throw tier-colour hex shards",
    ], fc=VIOLET_BG, ec=VIOLET, size=10.2)
    box(ax, 63, 28, 46, 19, "5b  shield reaches 0 = BREAK", [
        "crack burst VFX + sound (everyone)",
        "regen delay after break 5-8 s",
        "Volt core: shock pulse r 4 m, slow 30% 1.5 s",
    ], fc=VIOLET_BG, ec=VIOLET, size=10.2)
    arrow(ax, (86, 81.5), (86, 78), lw=2, label="yes", label_off=(3.2, 0), color=VIOLET)
    arrow(ax, (86, 52), (86, 47), lw=1.8, ls="--", color=VIOLET, label="if empty", label_off=(5, 0))
    box(ax, 113, 82, 24, 16, "5c  NOT covered", ["all raw damage", "-> zone HP", "(no shards)"], fc="white", ec=INK,
        size=10.2)
    arrow(ax, (104, 90), (113, 90), lw=2, label="no", label_off=(0, 2.4))

    # column 3: HP
    diamond(ax, 147, 63, 32, 15, "zone HP\n<= 0 ?", fc=CORAL_BG, ec=CORAL)
    arrow(ax, (109, 65), (131, 63), lw=2, label="HP damage", label_off=(0, 2.6))
    arrow(ax, (125, 82), (140, 69), lw=2, rad=0.15)
    box(ax, 140, 82, 27, 30, "ZONE HP", [
        "Head      45",
        "Torso   120",
        "Arms     70",
        "Legs      85",
        "",
        "no passive HP regen",
        "(items, Solace heal)",
    ], fc=CORAL_BG, ec=CORAL, size=10.5)
    box(ax, 113, 31, 26, 20, "WOUNDED", [
        "tagging: -25% speed", "  for 0.4 s (HP hits)", "aim punch 0.6 deg", "  (shield hits 0.2)"],
        fc="white", ec=CORAL, size=10)
    arrow(ax, (140, 58), (132, 51), lw=2, label="no", label_off=(-2.5, 1.6), color=CORAL)
    box(ax, 141, 28, 26, 23, "which zone?", [
        "HEAD / TORSO -> DEATH",
        "ARMS -> broken:",
        "  sway x2, ADS x1.3",
        "  recoil x1.25",
        "LEGS -> broken: no",
        "  sprint/jet/slide, x0.7",
    ], fc=CORAL_BG, ec=CORAL, size=9.8)
    arrow(ax, (154, 55.5), (154, 51), lw=2, label="yes", label_off=(3, 0), color=CORAL)
    box(ax, 113, 4, 54, 19, "6  Spill + results", [
        "hits on a broken limb -> torso x0.6 (arms) / x0.7 (legs)",
        "HitConfirmed -> shooter (marker: shield / HP / head / kill)",
        "DamageTaken -> victim (direction, zone); kill feed to all",
        "death -> respawn timer 4 s, score +1 to killer's team",
    ], fc="white", ec=INK, size=10)
    arrow(ax, (154, 28), (150, 23), lw=1.8, ls="--")

    box(ax, 63, 4, 46, 19, "Worked example (Warden torso, 30 m)", [
        "target: Volt Line T3 (torso+arms, shield 100)",
        "raw 160 -> pierce 48 to torso; rest 112",
        "shield absorbs 100 -> BREAK; overflow 12",
        "torso 120 - 48 - 12 = 60 HP left, alive",
    ], fc=GOLD_BG, ec=GOLD, size=10)
    fig.savefig(os.path.join(OUT, "damage_flow.png"), dpi=110)
    plt.close(fig)


# ============================================================================ 3. movement FSM
def movement_fsm():
    fig, ax = canvas(17, 11.5, 170, 115)
    ax.text(3, 112.5, "Movement state machine (character controller, FixedUpdate 60 Hz)", fontsize=17,
            fontweight="bold", va="top")
    ax.text(3, 108.3, "Speeds shown for no / Light halo; Medium x0.95, Heavy x0.88. Numbered arrows = transitions in the table.",
            fontsize=11.5, color=MUTED, va="top")

    box(ax, 4, 38, 30, 30, "GROUND", [
        "walk     2.6 m/s (silent)",
        "jog      4.8 m/s (default)",
        "sprint   7.0 m/s (no fire)",
        "crouch   2.4 m/s",
        "accel 40, decel 36 m/s2",
        "step 0.35 m, slope <= 46 deg",
    ], fc=TEAL_BG, ec=TEAL, size=10.2)
    box(ax, 6, 4, 26, 20, "SLIDE", ["entry >= 5.5 m/s, +2.0 boost", "friction 4.5 m/s2 (flat)",
                                    "downhill > 8 deg: speeds up", "cap 13 m/s, eye 0.85 m"],
        fc=TEAL_BG, ec=TEAL, size=10)
    box(ax, 70, 42, 26, 20, "AIR", ["gravity 19 m/s2", "jump 1.0 m (6.16 m/s)", "air accel 14, wish 1.2 m/s"],
        fc=ICE_BG, ec=ICE, size=10)
    box(ax, 70, 4, 26, 20, "JETPACK", ["thrust 32 m/s2 (net +13)", "climb cap 6.0 m/s", "fuel 1.6 s, rise <= 5.65 m",
                                       "regen after 1.0 s, 3.2 s full"], fc=ICE_BG, ec=ICE, size=10)
    box(ax, 40, 70, 22, 16, "MANTLE", ["ledge 0.6-2.2 m", "0.35 s / 0.55 s", "weapon lowered"],
        fc=GOLD_BG, ec=GOLD, size=10)
    box(ax, 68, 78, 34, 19, "ZIPLINE", ["attach: interact within 1.2 m", "11 m/s (8-13 by slope)",
                                        "fire + ADS ok, spread +2.0 deg", "detach: 0.7 x vel + 5 m/s up"],
        fc=GOLD_BG, ec=GOLD, size=10)
    box(ax, 40, 3, 22, 9, "DEAD", ["from any state"], fc=CORAL_BG, ec=CORAL, size=10, title_size=12)

    def tr(n, p0, p1, rad=0.0, color=INK):
        arrow(ax, p0, p1, color=color, rad=rad, lw=1.9)
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        badge(ax, mx + 0.5 * rad * dy, my - 0.5 * rad * dx, n, color=color)

    tr(1, (34, 58), (70, 58))                         # ground -> air
    tr(2, (70, 47), (34, 47))                         # air -> ground
    tr(3, (13, 38), (13, 24))                         # ground -> slide
    tr(4, (24, 24), (24, 38))                         # slide -> ground
    tr(5, (32, 15), (72, 42))                         # slide -> air
    tr(6, (78, 42), (78, 24), color=ICE)              # air -> jet
    tr(7, (89, 24), (89, 42), color=ICE)              # jet -> air
    tr(8, (73, 62), (60, 70), color=GOLD)             # air -> mantle
    tr(9, (40, 76), (28, 68), color=GOLD)             # mantle -> ground
    tr(10, (9, 68), (68, 91), rad=-0.3, color=GOLD)   # ground -> zipline (arc over mantle)
    tr(11, (79, 62), (79, 78), color=GOLD)            # air -> zipline
    tr(12, (92, 78), (92, 62), color=GOLD)            # zipline -> air

    rows = [
        ("1", "GROUND -> AIR", "jump (coyote 0.10 s, jump buffer 0.10 s) or walk off a ledge"),
        ("2", "AIR -> GROUND", "ground probe finds slope <= 46 deg (crouch held at >= 5.5 m/s: -> SLIDE)"),
        ("3", "GROUND -> SLIDE", "crouch pressed at >= 5.5 m/s; speed boost at most once per 2.0 s"),
        ("4", "SLIDE -> GROUND", "speed < 3.6 m/s (-> crouch) or crouch released (-> jog)"),
        ("5", "SLIDE -> AIR", "jump keeps 90% of horizontal speed; or slide off a ledge"),
        ("6", "AIR -> JETPACK", "jump pressed again in the air and held; fuel >= 10%; legs not broken"),
        ("7", "JETPACK -> AIR", "jump released, fuel empty, or thrust faded at the ceiling band"),
        ("8", "AIR / JETPACK -> MANTLE", "ledge 0.6-2.2 m above feet ahead, moving forward, jump held"),
        ("9", "MANTLE -> GROUND", "after 0.35 s (<= 1.2 m) or 0.55 s; Medium x1.10, Heavy x1.25"),
        ("10", "GROUND -> ZIPLINE", "interact within 1.2 m of a line; snap 0.15 s"),
        ("11", "AIR / JETPACK -> ZIPLINE", "interact within 1.2 m in mid-air"),
        ("12", "ZIPLINE -> AIR", "jump (detach boost), crouch (drop), end of line, or legs broken"),
    ]
    x0, y0 = 107, 99
    ax.text(x0, y0, "Transitions", fontsize=13, fontweight="bold", va="top")
    for i, (n, name, cond) in enumerate(rows):
        y = y0 - 6.0 - i * 6.6
        badge(ax, x0 + 1.6, y, n, color=INK, r=1.45, size=9)
        ax.text(x0 + 4.2, y + 1.15, name, fontsize=10, fontweight="bold", va="center")
        ax.text(x0 + 4.2, y - 1.5, cond, fontsize=9, va="center", color=INK)
    for k, t in enumerate(("Kestrel Jet Burst is an impulse, not a state:",
                           "+11 m/s horizontal (+2.5 m/s up in air),",
                           "usable in GROUND, SLIDE, AIR, JETPACK.")):
        ax.text(107, 14 - k * 3.0, t, fontsize=10, color=MUTED, va="top")
    fig.savefig(os.path.join(OUT, "movement_state_machine.png"), dpi=110)
    plt.close(fig)


# ============================================================================ 4. recoil pattern
def recoil_chart():
    with open(os.path.join(DATA, "mako_recoil_pattern.json")) as f:
        pat = json.load(f)
    kicks = [(k["pitch"], k["yaw"]) for k in pat["kicks"]]
    pts = [(0.0, 0.0)]
    for p, y in kicks:
        pts.append((pts[-1][0] + y, pts[-1][1] + p))
    fig, axs = plt.subplots(1, 2, figsize=(15, 8.6), dpi=110, gridspec_kw=dict(width_ratios=[1.25, 1]))
    fig.patch.set_facecolor("white")
    ax = axs[0]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ax.plot(xs, ys, "-", color="#9aa3b2", lw=1.2, zorder=1)
    cols = [TEAL if i < 9 else (GOLD if i < 20 else CORAL) for i in range(len(pts))]
    ax.scatter(xs, ys, s=46, c=cols, zorder=2, edgecolors="white", linewidths=0.8)
    for i in (0, 2, 4, 8, 11, 15, 19, 23, 29):
        ax.annotate(str(i + 1), (xs[i], ys[i]), textcoords="offset points", xytext=(9, -3), fontsize=10,
                    fontweight="bold")
    ax.set_xlim(-1.6, 1.9)
    ax.set_ylim(-0.4, 5.6)
    ax.set_aspect("equal")
    ax.grid(True, color="#e3e6ec")
    ax.set_xlabel("yaw (deg, + = right)")
    ax.set_ylabel("pitch (deg, + = up)")
    ax.set_title("Cumulative view kick, shots 1-30 (hip, no ADS x0.85)", fontsize=12, fontweight="bold", loc="left")
    for k, (t, c) in enumerate((("1-9: climb 4.2 deg", TEAL), ("10-20: right, then left", GOLD),
                                ("21-30: slow S-sway", CORAL))):
        ax.text(0.25, 1.6 - k * 0.32, t, fontsize=10, color=c, fontweight="bold", va="top")
    ax2 = ax.secondary_yaxis("right", functions=(lambda d: 20 * 100 * (math.pi / 180) * d,
                                                   lambda c: c / (20 * 100 * (math.pi / 180))))
    ax2.set_ylabel("offset at 20 m (cm)")

    # right: per-shot pitch kick + spread bloom
    ax = axs[1]
    shots = list(range(1, len(kicks) + 1))
    ax.bar(shots, [k[0] for k in kicks], color=[cols[i] for i in range(len(kicks))], label="pitch kick after shot n")
    ax.plot(shots, [k[1] for k in kicks], "o-", color=INK, ms=3.5, lw=1.2, label="yaw kick after shot n")
    ax.axhline(0, color=INK, lw=0.8)
    ax.set_xlabel("shot n")
    ax.set_ylabel("kick (deg)")
    ax.grid(True, axis="y", color="#e3e6ec")
    ax.legend(loc="upper right", fontsize=9.5)
    ax.set_title("Kick applied after shot n (data/mako_recoil_pattern.json)", fontsize=12, fontweight="bold", loc="left")
    for k, t in enumerate(("pattern restarts after 0.30 s without firing",
                           "60% of un-compensated climb recovers at 15 deg/s",
                           "45 / 60 round mags loop kicks 21-29")):
        ax.text(0.36, 0.80 - k * 0.045, t, transform=ax.transAxes, fontsize=9.6, va="top")
    fig.suptitle("AR-7 Mako recoil: learnable view-kick pattern at 720 RPM", fontsize=15, fontweight="bold", x=0.01,
                 ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(os.path.join(OUT, "mako_recoil_pattern.png"), dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    net_architecture()
    damage_flow()
    movement_fsm()
    recoil_chart()
    print("ok", sorted(os.listdir(OUT)))
