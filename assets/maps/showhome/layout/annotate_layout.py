"""Names every collision brush of the game's Showhome level and writes the art-facing layout data.

    python annotate_layout.py            # re-tag the existing showhome_level.json
    python annotate_layout.py --dump     # first re-run tools/level_dump (cargo) to refresh the JSON

Inputs
  showhome_level.json   exact dump of vetf_sim::maps::showhome() (tools/level_dump). GROUND TRUTH.
  design/maps/tdm/src/showhome_layout.py   (imported read-only) for ids, names, openings, markers.
Outputs (all in this folder)
  showhome_annotated.json   every brush with a tag (id / part / structure), the structure table, every
                            opening (checked clear in collision), spawns with ids, zipline, design markers.
  renders/plan_ground.png, renders/plan_upper.png, renders/section_A_y26.png, renders/section_D_x14.4.png
  LAYOUT.md                 the <!-- AUTO:... --> blocks are regenerated; the prose around them is hand-written.

The tagger mirrors a few constants of game/crates/vetf_sim/src/maps/showhome.rs (pods, stair, heights). If
that file changes, untagged brushes are listed (and the script exits 1), so drift cannot go unnoticed.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
RENDERS = os.path.join(HERE, "renders")
LEVEL_JSON = os.path.join(HERE, "showhome_level.json")
OUT_JSON = os.path.join(HERE, "showhome_annotated.json")
LAYOUT_MD = os.path.join(HERE, "LAYOUT.md")

sys.dont_write_bytecode = True  # never write __pycache__ into design/
sys.path.insert(0, os.path.join(ROOT, "design", "maps", "tdm", "src"))
import showhome_layout as SL  # noqa: E402

TOL = 2e-3
MAP_W, AXIS = 72.0, 36.0
UF, UF_CEIL, EAVES, RIDGE, CEIL_HARD, SLAB = 3.2, 6.0, 6.2, 11.2, 10.0, 0.25
# --- mirrored from showhome.rs (Pod, SHED, HUB, HOUSE, GARAGE, STAIR, RIDGE_Y)
HOUSE = (9.0, 22.0, 21.0, 32.0)
GARAGE = (9.0, 16.0, 21.0, 22.0)
STAIR = (13.8, 25.5, 15.0, 30.5)
RIDGE_Y = 27.0
PODS = {  # id: (rect, wall_top, roof_top, t)
    "W_GREENHOUSE": ((21.0, 32.0, 26.5, 36.0), 2.6, 2.8, 0.2),
    "W_STUDIO": ((20.0, 1.0, 26.0, 6.0), 2.6, 2.8, 0.2),
}
OFFICE = ((30.0, 1.0, 42.0, 8.0), 2.8, 3.0, 0.25)
CLOSED = {"W_SHED": ((17.0, 43.0, 21.0, 47.0), 2.6), "C_HUB": ((34.0, 39.0, 38.0, 44.0), 3.0)}

# Structure groups (art kit units). Key = structure id, value = id prefixes / ids that belong to it.
STRUCTURES_W = [
    ("SAGE_HOUSE", "Sage House (2 floors + garage, terrace on the garage roof, 45 deg gable)",
     ["W_GF_", "W_UF_", "W_TER_", "W_TERRACE", "W_STAIR", "W_ROOF_", "W_HOUSE"]),
    ("SAGE_HOUSE_PROPS", "Sage House furniture and terrace heat pump",
     ["W_ISLAND", "W_GARAGE_CAR", "W_WORKBENCH", "W_SHELF", "W_SOFA", "W_DRESSER", "W_HEATPUMP"]),
    ("SAGE_GREENHOUSE", "Sage Greenhouse (enterable, 3 doors, flat roof slab)", ["W_GREENHOUSE", "W_GH_"]),
    ("SAGE_STUDIO", "Sage Studio (enterable garden office, 2 doors + window)", ["W_STUDIO", "W_ST_"]),
    ("SAGE_SHED", "Sage Shed (closed solid)", ["W_SHED"]),
    ("SAGE_YARD", "Sage spawn yard walls + hot tub + outdoor kitchen",
     ["W_YARD_", "W_HOTTUB", "W_BBQ"]),
    ("SAGE_LAWN", "Sage front lawn: picket fences, lawn hedge, planters",
     ["W_FENCE_", "W_HEDGE_LAWN", "W_PLANTER_"]),
    ("SAGE_GARDEN", "Sage back garden: tank, arbour, veg beds", ["W_TANK", "W_ARBOUR", "W_BEDS_"]),
    ("SAGE_PYLON", "Sage Pylon (utility pole + service pad, zipline anchor)", ["W_PYLON_"]),
    ("SAGE_DRIVE", "Sage drive: low wall, bin store, parcel lockers", ["W_LOWWALL", "W_BINS", "W_LOCKERS"]),
    ("SAGE_STREET", "Sage-side street props: kerb delivery pod, armchair, crate",
     ["W_KERBPOD", "W_ARMCHAIR", "W_CRATE"]),
    ("SAGE_BOUNDARY", "West boundary hedge (+ player clip to the hard ceiling)", ["W_HEDGE"]),
]
STRUCTURES_C = [
    ("MOVER_TRUCK", "Mover: driverless removal truck (box = perch 3.2, cab 2.4)", ["C_MOVER_"]),
    ("STREET_CENTRE", "Centre-line props: charger island, tail crate", ["C_CHARGER", "C_CRATE_T"]),
    ("SALES_OFFICE", "Sales office (shutters W+E, 2 street windows, model table, flat roof perch 3.0)",
     ["C_OFFICE", "C_OF_", "C_MODEL"]),
    ("SHUTTLE_STOP", "Shuttle stop shelter against the office front", ["C_SHUTTLE"]),
    ("HUB", "Parcel hub kiosk in the turning circle (closed solid)", ["C_HUB"]),
    ("BOUNDARY_N", "North acoustic fence (+ player clip)", ["C_NWALL"]),
    ("BOUNDARY_S", "South boundary wall (+ player clip)", ["C_SWALL"]),
    ("MAP_CEILING", "Invisible hard ceiling at z 10 over the map", ["MAP_CEILING"]),
    ("GROUND", "Ground slab (flat z = 0 everywhere, top of a 1 m slab)", ["GROUND"]),
]


# ------------------------------------------------------------------------------------------ helpers
def mx(x):
    return MAP_W - x


def mrect(r):
    return (mx(r[2]), r[1], mx(r[0]), r[3])


def eq(a, b, tol=TOL):
    return abs(a - b) <= tol


def mid(s):
    return s.replace("W_", "E_", 1) if s.startswith("W_") else s


def box(b):
    (x0, y0, z0), (x1, y1, z1) = b["design"]["min"], b["design"]["max"]
    return x0, y0, z0, x1, y1, z1


def rect_eq(b, r, tol=TOL):
    x0, y0, _, x1, y1, _ = box(b)
    return eq(x0, r[0], tol) and eq(y0, r[1], tol) and eq(x1, r[2], tol) and eq(y1, r[3], tol)


def rect_in(b, r, tol=TOL):
    x0, y0, _, x1, y1, _ = box(b)
    return x0 >= r[0] - tol and y0 >= r[1] - tol and x1 <= r[2] + tol and y1 <= r[3] + tol


def grow(r, d):
    return (r[0] - d, r[1] - d, r[2] + d, r[3] + d)


def sides(rect_w):
    """West rect and its mirror (unless it sits on the axis)."""
    return [("W", rect_w), ("E", mrect(rect_w))]


# ------------------------------------------------------------------------------------------ wall defs
class WallDef:
    def __init__(self, wid, x0, y0, x1, y1, z0, z1, t, kind, floor, side):
        self.id, self.z0, self.z1, self.t, self.kind, self.floor, self.side = wid, z0, z1, t, kind, floor, side
        if abs(x0 - x1) < 1e-6:
            self.line, self.c, self.a0, self.a1 = "x", x0, min(y0, y1), max(y0, y1)
        else:
            self.line, self.c, self.a0, self.a1 = "y", y0, min(x0, x1), max(x0, x1)

    def footprint(self):
        h, a0, a1 = self.t / 2, self.a0 - self.t / 2, self.a1 + self.t / 2
        if self.line == "x":
            return (self.c - h, a0, self.c + h, a1)
        return (a0, self.c - h, a1, self.c + h)

    def along(self, b):
        """(a0, a1, thickness) of a brush measured along / across this wall's line."""
        x0, y0, _, x1, y1, _ = box(b)
        return (y0, y1, x1 - x0) if self.line == "x" else (x0, x1, y1 - y0)


def box_walls(prefix, r, z0, z1, t, side):
    x0, y0, x1, y1 = r
    return [WallDef(prefix + "_S", x0, y0, x1, y0, z0, z1, t, "pod", "GF", side),
            WallDef(prefix + "_N", x0, y1, x1, y1, z0, z1, t, "pod", "GF", side),
            WallDef(prefix + "_W", x0, y0, x0, y1, z0, z1, t, "pod", "GF", side),
            WallDef(prefix + "_E", x1, y0, x1, y1, z0, z1, t, "pod", "GF", side)]


def all_walls_and_openings():
    walls_w, opens_w = SL._west_walls_and_openings()
    walls = []
    for w in walls_w:
        walls.append(WallDef(w.id, w.x0, w.y0, w.x1, w.y1, w.z0, w.z1, w.t, w.kind, w.floor, "W"))
        m = SL.mirror_wall(w)
        walls.append(WallDef(m.id, m.x0, m.y0, m.x1, m.y1, m.z0, m.z1, m.t, m.kind, m.floor, "E"))
    for pid, short in (("W_GREENHOUSE", "W_GH_WALL"), ("W_STUDIO", "W_ST_WALL")):
        r, wt, _, t = PODS[pid]
        for wd in box_walls(short, r, 0.0, wt, t, "W"):
            walls.append(wd)
            # mirrored copy keeps the west suffix (E_GH_WALL_W is the mirror of W_GH_WALL_W, i.e. at x 51)
            if wd.line == "x":
                walls.append(WallDef(mid(wd.id), mx(wd.c), wd.a0, mx(wd.c), wd.a1, wd.z0, wd.z1, wd.t, wd.kind,
                                     wd.floor, "E"))
            else:
                walls.append(WallDef(mid(wd.id), mx(wd.a1), wd.c, mx(wd.a0), wd.c, wd.z0, wd.z1, wd.t, wd.kind,
                                     wd.floor, "E"))
    walls += box_walls("C_OF_WALL", OFFICE[0], 0.0, OFFICE[1], OFFICE[3], "C")
    opens = list(opens_w) + [SL.mirror_opening(o) for o in opens_w]
    return walls, opens


def opening_box(o, depth=0.6):
    """Design-frame box of an opening: its span along the wall, +-depth/2 across it, sill..head."""
    if o.wall == "x":
        return (o.c - depth / 2, o.a0, o.z0, o.c + depth / 2, o.a1, o.z1)
    return (o.a0, o.c - depth / 2, o.z0, o.a1, o.c + depth / 2, o.z1)


def boxes_overlap(a, b, shrink=0.01):
    return all(a[i] + shrink < b[i + 3] and b[i] + shrink < a[i + 3] for i in range(3))


# ------------------------------------------------------------------------------------------ tagging
def tag_brushes(level):
    brushes = level["brushes"]
    L = SL.build()
    elements = L["elements"]
    walls, opens = all_walls_and_openings()
    tags = [None] * len(brushes)

    def put(i, tid, part=None, **kw):
        if tags[i] is None:
            tags[i] = dict(id=tid, part=part, **kw)

    for i, b in enumerate(brushes):
        x0, y0, z0, x1, y1, z1 = box(b)
        look, kind, ramp = b["look"], b["kind"], b["shape"] == "ramp"

        # 1. ground slab pieces
        if eq(z0, -1.0) and eq(z1, 0.0):
            zone = None
            if look in ("TeamA", "TeamB"):
                for zid, zr in L["spawn_zones"].items():
                    if rect_eq(b, zr):
                        zone = zid
            elif look == "Floor":
                cands = [("SAGE_HOUSE", (9.0, 16.0, 21.0, 32.0))]
                cands += [(k.replace("W_", "SAGE_"), v[0]) for k, v in PODS.items()]
                cands += [("SALES_OFFICE", (OFFICE[0][0], OFFICE[0][1], AXIS, OFFICE[0][3]))]
                for name, r in cands:
                    for s, rr in sides(r):
                        if rect_in(b, rr):
                            zone = name if s == "W" or name == "SALES_OFFICE" else name.replace("SAGE_", "CLAY_")
            put(i, "GROUND", {"Ground": "ground", "Floor": "building_floor"}.get(look, "spawn_zone"), zone=zone)
            continue

        # 2. clips
        if kind == "PlayerClip":
            if ramp:
                half = "S" if b["design"]["ramp"]["rise_toward"] == "N" else "N"
                side = "W" if x1 <= AXIS else "E"
                put(i, f"{side}_ROOF_CLIP_{half}", "player_clip",
                    note="invisible, steeper than walkable: the gable cannot be stood on")
            elif eq(z0, CEIL_HARD):
                put(i, "MAP_CEILING", "player_clip", note="hard ceiling over the whole map")
            elif eq(y0, 47.0) and eq(y1, 48.0):
                put(i, "C_NWALL", "player_clip", note="above the fence up to the hard ceiling")
            elif eq(y0, 0.0) and eq(y1, 1.0):
                put(i, "C_SWALL", "player_clip", note="above the wall up to the hard ceiling")
            elif eq(z0, 3.0) and (eq(x1, 1.0) or eq(x0, 71.0)):
                put(i, "W_HEDGE" if x1 <= AXIS else "E_HEDGE", "player_clip",
                    note="above the hedge up to the hard ceiling")
            continue

        # 3. exact element matches (layout elements, incl. mirrored and centre ones)
        for e in elements:
            for side, r in ([("C", (e.x0, e.y0, e.x1, e.y1))] if e.side == "C" else sides((e.x0, e.y0, e.x1, e.y1))):
                if rect_eq(b, r) and eq(z0, e.z0) and eq(z1, e.z1):
                    eid = e.id if side != "E" else mid(e.id)
                    put(i, eid, "stair_ramp" if ramp else "solid", name=(e.name if side != "E" else SL._mname(e.name)),
                        kit=e.kit, el_kind=e.kind, note=e.note or None)
        if tags[i]:
            continue

        # 4. house slabs / roof
        for side, hr in sides(HOUSE):
            p = "W" if side == "W" else "E"
            if rect_in(b, hr) and eq(z0, UF - SLAB) and eq(z1, UF) and look == "Floor":
                put(i, f"{p}_UF_SLAB", "floor_slab", note="upper floor slab (stair hole cut out)")
            elif rect_eq(b, hr) and eq(z0, UF_CEIL) and eq(z1, EAVES):
                put(i, f"{p}_UF_CEILING", "ceiling_slab", note="UF ceiling / roof base at the eaves")
            elif ramp and look == "Roof" and rect_in(b, hr):
                half = "S" if b["design"]["ramp"]["rise_toward"] == "N" else "N"
                put(i, f"{p}_ROOF_{half}", "gable", note="45 deg gable half, ridge E-W at y 27 z 11.2; stops bullets")
        if tags[i]:
            continue

        # 5. pod roofs, closed buildings, office roof
        for pid, (r, wt, rt, t) in PODS.items():
            for side, rr in sides(r):
                if rect_eq(b, grow(rr, t / 2)) and eq(z0, wt) and eq(z1, rt):
                    put(i, pid if side == "W" else mid(pid), "roof_slab", note="flat roof slab (standable)")
        if rect_eq(b, grow(OFFICE[0], OFFICE[3] / 2)) and eq(z0, OFFICE[1]) and eq(z1, OFFICE[2]):
            put(i, "C_OFFICE", "roof_slab", note="J_OFFICE perch (flat, standable, z 3.0)")
        for cid, (r, h) in CLOSED.items():
            for side, rr in ([("C", r)] if cid.startswith("C_") else sides(r)):
                if rect_eq(b, rr):
                    nid = cid if side != "E" else mid(cid)
                    if eq(z0, 0.0) and eq(z1, h - 0.2):
                        put(i, nid, "body")
                    elif eq(z0, h - 0.2) and eq(z1, h):
                        put(i, nid, "roof_cap", note="flat top (standable by jetpack)")
        if tags[i]:
            continue

        # 6. walls (house walls, parapets, screens, pod walls, office walls)
        cands = []
        for w in walls:
            if not rect_in(b, w.footprint()):
                continue
            a0, a1, th = w.along(b)
            if not eq(th, w.t) or z0 < w.z0 - TOL or z1 > w.z1 + TOL:
                continue
            cands.append(w)
        for w in cands:
            a0, a1, _ = w.along(b)
            if eq(z0, w.z0) and eq(z1, w.z1):
                put(i, w.id, "pier", wall_kind=w.kind, floor=w.floor)
                break
            hit = None
            for o in opens:
                if o.wall != w.line or not eq(o.c, w.c):
                    continue
                oa0, oa1 = max(o.a0, w.a0 - w.t / 2), min(o.a1, w.a1 + w.t / 2)
                if not (eq(a0, oa0) and eq(a1, oa1)):
                    continue
                if eq(z0, w.z0) and eq(z1, max(o.z0, w.z0)):
                    hit = ("sill", o)
                elif eq(z1, w.z1) and eq(z0, min(o.z1, w.z1)):
                    hit = ("lintel", o)
            if hit:
                put(i, w.id, hit[0], opening=hit[1].id, wall_kind=w.kind, floor=w.floor)
                break
    return tags, L, walls, opens


STRUCT_ALL = None


def structure_of(tid):
    global STRUCT_ALL
    if STRUCT_ALL is None:
        STRUCT_ALL = []
        for sid, desc, pref in STRUCTURES_W:
            STRUCT_ALL.append((sid, desc, pref, "W"))
            STRUCT_ALL.append((sid.replace("SAGE_", "CLAY_"), desc.replace("Sage", "Clay").replace("West", "East")
                               .replace("west", "east"), [mid(p) for p in pref], "E"))
        for sid, desc, pref in STRUCTURES_C:
            STRUCT_ALL.append((sid, desc, pref, "C"))
    best = None
    for sid, desc, pref, side in STRUCT_ALL:
        for p in pref:
            if tid == p or (p.endswith("_") and tid.startswith(p)):
                if best is None or len(p) > best[2]:
                    best = (sid, desc, len(p), side)
    return best


# ------------------------------------------------------------------------------------------ assemble
def build(level):
    tags, L, walls, opens = tag_brushes(level)
    brushes = level["brushes"]
    untagged = [i for i, t in enumerate(tags) if t is None]
    out_brushes = []
    structs = {}
    for i, b in enumerate(brushes):
        t = tags[i] or dict(id="UNTAGGED", part=None)
        st = structure_of(t["id"]) if t["id"] != "UNTAGGED" else None
        sid = st[0] if st else "UNASSIGNED"
        t["structure"] = sid
        rec = dict(i=i, tag=t, kind=b["kind"], look=b["look"], shape=b["shape"],
                   min=b["design"]["min"], max=b["design"]["max"])
        if b["shape"] == "ramp":
            rr = b["design"]["ramp"]
            rec["ramp"] = dict(rise_toward=rr["rise_toward"], z_low=rr["z_low"], z_high=rr["z_high"],
                               slope_deg=rr["slope_deg"])
        out_brushes.append(rec)
        s = structs.setdefault(sid, dict(id=sid, desc=st[1] if st else "", side=st[3] if st else "?", brushes=[],
                                         ids=set()))
        s["brushes"].append(i)
        s["ids"].add(t["id"])

    # openings: verify each one is open in collision (no player/bullet-blocking brush inside it)
    solid_boxes = [(box(b), b) for b in brushes if b["kind"] != "BulletOnly"]
    out_open = []
    for o in opens:
        ob = opening_box(o, depth=0.2)
        blockers = [b["i"] for bb, b in solid_boxes if b["kind"] == "Solid" and boxes_overlap(ob, bb)]
        owner = None
        for w in walls:
            if w.line == o.wall and eq(w.c, o.c) and o.a0 < w.a1 and o.a1 > w.a0 and o.z0 < w.z1 and o.z1 > w.z0:
                owner = w.id
                break
        st = structure_of(owner) if owner else None
        out_open.append(dict(id=o.id, kind=o.kind, wall=owner, structure=st[0] if st else None, floor=o.floor,
                             line=f"{o.wall} = {o.c:g}", span=[round(o.a0, 4), round(o.a1, 4)],
                             sill=o.z0, head=o.z1, note=o.note or None,
                             clear_in_collision=not blockers, blockers=blockers))
    # structures with bounds
    out_structs = []
    for sid, s in structs.items():
        bx = [box(brushes[i]) for i in s["brushes"]]
        vis = [box(brushes[i]) for i in s["brushes"] if brushes[i]["look"] != "Invisible"]
        src = vis or bx
        mn = [round(min(b[k] for b in src), 4) for k in range(3)]
        mxx = [round(max(b[k + 3] for b in src), 4) for k in range(3)]
        out_structs.append(dict(id=sid, desc=s["desc"], side=s["side"], min=mn, max=mxx,
                                brush_count=len(s["brushes"]), element_ids=sorted(s["ids"]),
                                openings=[o["id"] for o in out_open if o["structure"] == sid],
                                brushes=s["brushes"]))
    order = {sid: k for k, (sid, *_r) in enumerate(STRUCT_ALL)}
    out_structs.sort(key=lambda s: order.get(s["id"], 999))

    # spawns: attach the layout ids
    spawns = []
    for s in level["spawns"]:
        p = s["design"]["pos"]
        sid = next((x["id"] for x in L["spawns"] if eq(x["x"], p[0]) and eq(x["y"], p[1])), None)
        zone = next((x["zone"] for x in L["spawns"] if eq(x["x"], p[0]) and eq(x["y"], p[1])), None)
        spawns.append(dict(id=sid, zone=zone, team=s["team"], pos=p, yaw_deg=s["design"]["yaw_deg"],
                           bevy_pos=s["bevy"]["pos"], bevy_yaw_rad=s["bevy"]["yaw_rad"]))

    zl = L["zipline"]
    markers = dict(
        source="design/maps/tdm/src/showhome_layout.py (design-only: NOT part of the game Level; the game "
               "has no pickups / callouts yet). Use them for set-dressing and naming, not for collision.",
        pickups=[dict(id=p[0], name=p[1], pos=[p[2], p[3], p[4]], respawn_s=p[5], note=p[6]) for p in L["pickups"]],
        perches=[dict(id=p[0], name=p[1], element=p[2], top_z=p[3], access=p[4]) for p in L["perches"]],
        callouts=L["callouts"],
        sightlines=[dict(id=s[0], name=s[1], a=list(s[2]), b=list(s[3]), note=s[4]) for s in L["sightlines"]],
        spawn_zones={k: list(v) for k, v in L["spawn_zones"].items()},
        zipline_design=dict(id=zl["id"], name=zl["name"], sag_m=zl["sag"], note=zl["note"]),
    )
    out = dict(
        schema="showhome_annotated/1",
        generated_by="assets/maps/showhome/layout/annotate_layout.py",
        level_source_fnv1a64=level["source_fnv1a64"],
        frames=level["frames"],
        map=level["map"],
        kill_plane=level["kill_plane"],
        bounds=level["bounds"],
        heights=dict(GF=0.0, UF=UF, UF_slab_bottom=UF - SLAB, UF_ceiling=UF_CEIL, eaves=EAVES, ridge=RIDGE,
                     hard_ceiling=CEIL_HARD, kill=level["kill_plane"]["design_z"]),
        structures=out_structs,
        openings=out_open,
        spawns=spawns,
        ziplines=level["ziplines"],
        design_markers=markers,
        untagged=untagged,
        brushes=out_brushes,
    )
    return out


# ------------------------------------------------------------------------------------------ plots
LOOK_RGB = {  # sRGB, close to game/crates/val_etf/src/render.rs look_color
    "Ground": (0.42, 0.47, 0.36), "Floor": (0.58, 0.52, 0.44), "Wall": (0.88, 0.83, 0.74),
    "Roof": (0.32, 0.30, 0.33), "Trim": (0.93, 0.91, 0.87), "Prop": (0.60, 0.49, 0.37),
    "Hedge": (0.24, 0.40, 0.22), "Fence": (0.82, 0.80, 0.74), "Glass": (0.60, 0.80, 0.92),
    "Vehicle": (0.80, 0.76, 0.66), "Metal": (0.36, 0.38, 0.42), "Concrete": (0.64, 0.64, 0.62),
    "Water": (0.22, 0.46, 0.56), "TeamA": (0.0, 0.62, 0.56), "TeamB": (0.93, 0.38, 0.32),
    "Accent": (0.95, 0.74, 0.22), "Target": (0.86, 0.86, 0.84), "Invisible": (1.0, 0.0, 1.0),
}


def plot_plans(ann, level):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Polygon, FancyArrow

    os.makedirs(RENDERS, exist_ok=True)
    B = ann["brushes"]
    labels = {s["id"]: s for s in ann["structures"]}

    def plan(fname, title, keep, label_level):
        fig, ax = plt.subplots(figsize=(19, 13.5), dpi=110)
        ax.set_facecolor((0.93, 0.93, 0.91))
        draw = [b for b in B if keep(b)]
        draw.sort(key=lambda b: (b["max"][2], b["look"] != "Invisible"))
        for b in draw:
            x0, y0, z0 = b["min"]
            x1, y1, z1 = b["max"]
            col = LOOK_RGB.get(b["look"], (0.5, 0.5, 0.5))
            if b["look"] == "Invisible":
                ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=(0.85, 0, 0.85), lw=0.6,
                                       ls="--", zorder=5))
                continue
            if b["tag"]["id"] == "GROUND":
                ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=col, ec="none", alpha=0.45, zorder=0))
                continue
            ec = (0.1, 0.1, 0.1)
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=col, ec=ec, lw=0.5, zorder=2 + z1 * 0.1))
            if b["shape"] == "ramp":
                r = b["ramp"]
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                d = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}[r["rise_toward"]]
                ln = 0.35 * ((y1 - y0) if d[1] else (x1 - x0))
                ax.add_patch(FancyArrow(cx - d[0] * ln, cy - d[1] * ln, 2 * d[0] * ln, 2 * d[1] * ln, width=0.12,
                                        head_width=0.6, length_includes_head=True, color=(0.6, 0.1, 0.1), zorder=9))
        # openings on this level
        for o in ann["openings"]:
            lvl = "U" if o["sill"] >= 3.0 else "G"
            if lvl != label_level:
                continue
            a0, a1 = o["span"]
            axis, c = o["line"].split(" = ")
            c = float(c)
            col = {"door": "#1f77b4", "door2": "#1f77b4", "roller": "#9467bd", "shutter": "#9467bd",
                   "window": "#2ca02c", "clerestory": "#bcbd22"}[o["kind"]]
            if axis == "x":
                ax.plot([c, c], [a0, a1], color=col, lw=4, solid_capstyle="butt", zorder=8)
            else:
                ax.plot([a0, a1], [c, c], color=col, lw=4, solid_capstyle="butt", zorder=8)
        # spawns (ground level only)
        if label_level == "G":
            for s in ann["spawns"]:
                x, y, _ = s["pos"]
                dx = math.cos(math.radians(s["yaw_deg"])) * 0.9
                dy = math.sin(math.radians(s["yaw_deg"])) * 0.9
                c = (0.0, 0.55, 0.5) if s["team"] == "A" else (0.9, 0.3, 0.25)
                ax.add_patch(FancyArrow(x, y, dx, dy, width=0.25, head_width=0.7, color=c, zorder=10))
        for z in ann["ziplines"]:
            a, bb = z["design"]["a"], z["design"]["b"]
            ax.plot([a[0], bb[0]], [a[1], bb[1]], color="k", lw=1.5, ls="-.", zorder=11)
            ax.text((a[0] + bb[0]) / 2, a[1] + 0.4, "zipline z 6.3 (sag 0.8)", ha="center", fontsize=8, zorder=12)
        for c in ann["design_markers"]["callouts"]:
            if c["level"] == label_level:
                ax.text(c["x"], c["y"], c["name"], fontsize=7.5, ha="center", va="center", zorder=13,
                        color=(0.05, 0.05, 0.3),
                        bbox=dict(boxstyle="round,pad=0.15", fc=(1, 1, 1, 0.65), ec="none"))
        ax.set_xlim(-2.5, 74.5)
        ax.set_ylim(-2.5, 50.5)
        ax.set_aspect("equal")
        ax.set_xticks(range(0, 73, 4))
        ax.set_yticks(range(0, 49, 4))
        ax.grid(True, color=(0.5, 0.5, 0.5), lw=0.3, alpha=0.6)
        ax.axvline(AXIS, color=(0.3, 0.3, 0.3), lw=0.8, ls=":")
        ax.set_xlabel("x (m, east)  — design frame; Bevy x = x")
        ax.set_ylabel("y (m, north) — Bevy z = -y")
        import textwrap
        ax.set_title(chr(10).join(textwrap.wrap(title, 150)), fontsize=11)
        fig.tight_layout()
        p = os.path.join(RENDERS, fname)
        fig.savefig(p)
        plt.close(fig)
        return p

    out = [plan("plan_ground.png",
                "Showhome collision plan, GROUND level (brushes starting below z 2.0). Colours = brush look; "
                "magenta dashed = player clip; blue = doors, green = windows, purple = roller/shutter gaps; "
                "arrows: spawns (teal A / coral B), ramp rise",
                lambda b: b["min"][2] < 2.0 and not (b["kind"] == "PlayerClip" and b["min"][2] >= 9.9), "G"),
           plan("plan_upper.png",
                "Showhome collision plan, UPPER level: brushes with 2.4 <= z0 < 6.0 (UF slabs + stair hole, terraces, "
                "UF walls, parapets, pod / office roofs, pylon pads) plus the Mover (perch top 3.2). Roofs above the "
                "UF ceiling (z 6.0) are left out. Openings: UF doors (blue), windows (green), clerestories (yellow)",
                lambda b: (2.4 <= b["min"][2] < 6.0 and b["kind"] != "PlayerClip")
                or b["tag"]["id"] in ("C_MOVER_BOX", "C_MOVER_CAB"), "U")]

    # sections
    def section(fname, axis, c, title):
        fig, ax = plt.subplots(figsize=(19, 5.2), dpi=110)
        for b in B:
            x0, y0, z0 = b["min"]
            x1, y1, z1 = b["max"]
            lo, hi, a0, a1 = (y0, y1, x0, x1) if axis == "y" else (x0, x1, y0, y1)
            if not (lo - 1e-6 <= c <= hi + 1e-6):
                continue
            col = LOOK_RGB.get(b["look"], (0.5, 0.5, 0.5))
            if b["shape"] == "ramp":
                r = b["ramp"]
                d = r["rise_toward"]
                # profile along the section axis
                along_rise = (axis == "y" and d in "EW") or (axis == "x" and d in "NS")
                if along_rise:
                    up_hi = d in "EN"
                    pts = [(a0, z0), (a1, z0), (a1, z1 if up_hi else z0), (a0, z0 if up_hi else z1)]
                else:
                    run_lo, run_hi = (y0, y1) if d in "NS" else (x0, x1)
                    f = (c - run_lo) / max(run_hi - run_lo, 1e-6)
                    if d in "SW":
                        f = 1 - f
                    zt = z0 + f * (z1 - z0)
                    pts = [(a0, z0), (a1, z0), (a1, zt), (a0, zt)]
                ax.add_patch(Polygon(pts, closed=True, fc=col if b["look"] != "Invisible" else "none",
                                     ec=(0.85, 0, 0.85) if b["look"] == "Invisible" else "k", lw=0.5,
                                     ls="--" if b["look"] == "Invisible" else "-", zorder=3))
                continue
            if b["look"] == "Invisible":
                ax.add_patch(Rectangle((a0, z0), a1 - a0, z1 - z0, fill=False, ec=(0.85, 0, 0.85), lw=0.6, ls="--",
                                       zorder=4))
            else:
                ax.add_patch(Rectangle((a0, z0), a1 - a0, z1 - z0, fc=col, ec="k", lw=0.4, zorder=2))
        ax.set_xlim(-2.5, (74.5 if axis == "y" else 50.5))
        ax.set_ylim(-1.2, 12.6)
        ax.set_aspect("equal")
        ax.set_xticks(range(0, 73 if axis == "y" else 49, 2))
        ax.set_yticks([0, 1, 2, 3.2, 4.2, 6.2, 8, 10, 11.2])
        ax.grid(True, lw=0.3, alpha=0.6)
        ax.axhline(1.6, color=(0.2, 0.4, 0.9), lw=0.6, ls=":")
        ax.text(-2.3, 1.7, "eye 1.6", fontsize=7, color=(0.2, 0.4, 0.9))
        ax.set_xlabel(("x (m, east)" if axis == "y" else "y (m, north)"))
        ax.set_ylabel("z (m, up)")
        ax.set_title(title, fontsize=11)
        fig.tight_layout()
        p = os.path.join(RENDERS, fname)
        fig.savefig(p)
        plt.close(fig)
        return p

    out.append(section("section_A_y26.png", "y", 26.0,
                       "Section A: E-W cut at y = 26 (both houses through the front doors, the Mover box). "
                       "Magenta dashed = player clips (roof clip, hedge clips, hard ceiling z 10)"))
    out.append(section("section_D_x14.4.png", "x", 14.4,
                       "Section D: N-S cut at x = 14.4 (Sage drive, bins, garage roller door, stair ramp, patio, tank, "
                       "shed)"))
    out.append(section("section_C_x36.png", "x", 36.0,
                       "Section C: N-S cut on the mirror axis x = 36 (office + roof perch, shuttle, Mover, cab, "
                       "charger, hub, north fence)"))
    return out


# ------------------------------------------------------------------------------------------ LAYOUT.md
def fmt_box(mn, mx_):
    return f"x {mn[0]:g}..{mx_[0]:g}, y {mn[1]:g}..{mx_[1]:g}, z {mn[2]:g}..{mx_[2]:g}"


def md_tables(ann, level):
    T = {}
    # structures
    rows = ["| Structure | Side | Bounds (design, visible brushes) | Brushes | Openings |",
            "|---|---|---|---|---|"]
    for s in ann["structures"]:
        if s["id"] in ("GROUND",):
            continue
        op = ", ".join(s["openings"]) if s["openings"] else "-"
        rows.append(f"| **{s['id']}**<br>{s['desc']} | {s['side']} | {fmt_box(s['min'], s['max'])} | "
                    f"{s['brush_count']} | {op} |")
    T["structures"] = "\n".join(rows)

    # openings (west + centre; east are mirrored)
    rows = ["| Opening | Kind | Wall | Line | Span along wall | Sill..head (z) | Clear in collision | Note |",
            "|---|---|---|---|---|---|---|---|"]
    for o in ann["openings"]:
        if o["id"].startswith("E_"):
            continue
        rows.append(f"| {o['id']} | {o['kind']} | {o['wall']} | {o['line']} | {o['span'][0]:g}..{o['span'][1]:g} | "
                    f"{o['sill']:g}..{o['head']:g} | {'yes' if o['clear_in_collision'] else 'NO ' + str(o['blockers'])} | "
                    f"{o['note'] or ''} |")
    T["openings"] = "\n".join(rows)

    # elements (single solid pieces) west + centre
    rows = ["| Id | Name | Kind (layout) | Look (game) | Box (design) | Kit hint |", "|---|---|---|---|---|---|"]
    seen = set()
    for b in ann["brushes"]:
        t = b["tag"]
        if t.get("part") not in ("solid", "stair_ramp") or t["id"].startswith("E_") or t["id"] in seen:
            continue
        seen.add(t["id"])
        rows.append(f"| {t['id']} | {t.get('name', '')} | {t.get('el_kind', '')} | {b['look']} | "
                    f"{fmt_box(b['min'], b['max'])} | {t.get('kit', '')} |")
    T["elements"] = "\n".join(rows)

    # walls west
    rows = ["| Wall | Kind | Floor | Pieces (pier / sill / lintel) | z | Thickness |", "|---|---|---|---|---|---|"]
    walls = {}
    for b in ann["brushes"]:
        t = b["tag"]
        if t.get("part") in ("pier", "sill", "lintel"):
            w = walls.setdefault(t["id"], dict(kind=t.get("wall_kind"), floor=t.get("floor"), p=[0, 0, 0],
                                               z=[9e9, -9e9], th=None))
            w["p"][("pier", "sill", "lintel").index(t["part"])] += 1
            w["z"] = [min(w["z"][0], b["min"][2]), max(w["z"][1], b["max"][2])]
            x0, y0, _ = b["min"]
            x1, y1, _ = b["max"]
            w["th"] = round(min(x1 - x0, y1 - y0), 3)
    for wid, w in walls.items():
        if wid.startswith("E_"):
            continue
        rows.append(f"| {wid} | {w['kind']} | {w['floor']} | {w['p'][0]} / {w['p'][1]} / {w['p'][2]} | "
                    f"{w['z'][0]:g}..{w['z'][1]:g} | {w['th']} |")
    T["walls"] = "\n".join(rows)

    # spawns
    rows = ["| Id | Team | Design pos (x, y, z) | Yaw (design deg) | Bevy pos | Bevy yaw (rad) |",
            "|---|---|---|---|---|---|"]
    for s in ann["spawns"]:
        rows.append(f"| {s['id']} | {s['team']} | {tuple(s['pos'])} | {s['yaw_deg']:g} | {tuple(s['bevy_pos'])} | "
                    f"{s['bevy_yaw_rad']:g} |")
    T["spawns"] = "\n".join(rows)

    # counts + fingerprint
    rows = ["| Kind / look | Count |", "|---|---|"]
    for k, v in level["brush_counts"].items():
        rows.append(f"| {k} | {v} |")
    rows.append(f"| **total** | **{level['brush_total']}** |")
    fp = ", ".join(f"`{k}` {v}" for k, v in level["source_fnv1a64"].items())
    T["counts"] = "\n".join(rows) + f"\n\nSource fingerprint (FNV-1a 64 of the sim files the dump was built from): {fp}."
    return T


def update_md(T):
    if not os.path.exists(LAYOUT_MD):
        print("LAYOUT.md missing: write the prose first, then re-run to fill the AUTO blocks")
        return
    s = open(LAYOUT_MD, encoding="utf-8").read()
    for k, v in T.items():
        # the block may be empty (fresh doc) or hold a previous table
        pat = re.compile(rf"(<!-- AUTO:{k} -->\n)(?:.*?\n)??(<!-- /AUTO:{k} -->)", re.S)
        if not pat.search(s):
            print(f"LAYOUT.md has no AUTO:{k} block")
            continue
        s = pat.sub(lambda m: m.group(1) + v + "\n" + m.group(2), s, count=1)
    open(LAYOUT_MD, "w", encoding="utf-8", newline="\n").write(s)


# ------------------------------------------------------------------------------------------ main
def fnv1a64(path):
    """Same fingerprint as tools/level_dump (FNV-1a 64 over the file bytes)."""
    h = 0xCBF29CE484222325
    with open(path, "rb") as f:
        for byte in f.read():
            h ^= byte
            h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", action="store_true", help="re-run tools/level_dump first (needs cargo on PATH)")
    ap.add_argument("--no-plots", action="store_true")
    a = ap.parse_args()
    if a.dump:
        env = dict(os.environ)
        env["PATH"] = os.path.join(os.path.expanduser("~"), ".cargo", "bin") + os.pathsep + env.get("PATH", "")
        subprocess.run(["cargo", "run", "--release", "--quiet", "--", "--out", HERE],
                       cwd=os.path.join(ROOT, "tools", "level_dump"), env=env, check=True)
    level = json.load(open(LEVEL_JSON, encoding="utf-8"))
    stale = [k for k, v in level["source_fnv1a64"].items()
             if fnv1a64(os.path.join(ROOT, "game", "crates", "vetf_sim", "src", k)) != v]
    if stale:
        print("WARNING: showhome_level.json is STALE (sim sources changed: " + ", ".join(stale) +
              "). Re-run with --dump.")
    ann = build(level)
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(ann, f, indent=1)
    print(f"wrote {OUT_JSON}: {len(ann['brushes'])} brushes, {len(ann['structures'])} structures, "
          f"{len(ann['openings'])} openings")
    blocked = [o["id"] for o in ann["openings"] if not o["clear_in_collision"]]
    print("openings blocked in collision:", blocked or "none")
    if not a.no_plots:
        for p in plot_plans(ann, level):
            print("wrote", p)
    update_md(md_tables(ann, level))
    if ann["untagged"]:
        print("UNTAGGED brushes (showhome.rs drifted from this tagger?):")
        for i in ann["untagged"]:
            b = level["brushes"][i]
            print("  ", i, b["kind"], b["look"], b["shape"], b["design"]["min"], b["design"]["max"])
        sys.exit(1)


if __name__ == "__main__":
    main()
