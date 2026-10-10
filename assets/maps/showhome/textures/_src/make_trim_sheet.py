"""Procedural house TRIM SHEET for Showhome: trim_sheet_house.png (2048 x 1024 albedo), trim_sheet_house_normal.png
(OpenGL / glTF tangent space), trim_sheet_house_orm.png (R = occlusion, G = roughness, B = metallic; the glTF /
Bevy metallic-roughness packing) and trims.json (the UV rectangle of every strip).

Every strip runs the full width and tiles along U, so a frame, gutter or sill of any length just scrolls along U.
Texel density 512 px/m: the sheet's U repeat is 4.0 m, a strip of h px covers a profile h/512 m wide.
Colours come from the concept palette (palette.json, see sample_palette.py).

Usage: python make_trim_sheet.py
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw

import texlib as T

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)
PREV = os.path.join(HERE, "preview")
W, H = 2048, 1024
PX_PER_M = 512
PAL = json.load(open(os.path.join(HERE, "palette.json")))["materials"]


def c(mat):
    return np.array(PAL[mat]["albedo_srgb"], np.float32) / 255.0


def rgb(*v):
    return np.array(v, np.float32) / 255.0


def ramp(v, a, b):
    """0 at v <= a, 1 at v >= b (smoothstep)."""
    t = np.clip((v - a) / max(b - a, 1e-6), 0, 1)
    return t * t * (3 - 2 * t)


def bump(v, centre, width):
    return np.exp(-0.5 * ((v - centre) / width) ** 2)


# ------------------------------------------------------------------------------------------------ profiles
# Each profile takes v (0 at the strip's top row .. 1 at its bottom row) and returns (height 0..1, ao 0..1).
def p_frame(v):
    """Window / door frame face: chamfered edges and two shallow grooves."""
    h = ramp(v, 0.0, 0.10) * (1 - ramp(v, 0.90, 1.0))
    g = 0.35 * bump(v, 0.32, 0.018) + 0.35 * bump(v, 0.68, 0.018)
    return np.clip(h - g, 0, 1), 1 - 0.55 * g - 0.25 * (1 - h)


def p_surround(v):
    """Deep window surround / reveal band: rounded outer edge, flat face, small step to the inner return."""
    h = 0.85 * ramp(v, 0.0, 0.12) + 0.15 * (1 - ramp(v, 0.80, 0.84))
    step = bump(v, 0.82, 0.012)
    return h, 1 - 0.35 * step - 0.2 * (1 - ramp(v, 0.0, 0.06))


def p_architrave(v):
    """Door architrave: a raised outer band, a step down, a flat inner band, chamfered end."""
    h = 0.7 + 0.3 * (1 - ramp(v, 0.28, 0.36))
    h = h * ramp(v, 0.0, 0.06) * (1 - ramp(v, 0.94, 1.0))
    step = bump(v, 0.36, 0.015)
    return h, 1 - 0.35 * step - 0.2 * (1 - ramp(v, 0.0, 0.05)) - 0.2 * ramp(v, 0.95, 1.0)


def p_sill(v):
    """Window sill seen from above/front: sloped top, rounded nose, drip groove underneath (bottom quarter)."""
    h = 0.6 + 0.4 * ramp(v, 0.0, 0.62)
    h = h * (1 - 0.6 * ramp(v, 0.66, 0.74))
    drip = bump(v, 0.86, 0.02)
    return np.clip(h - 0.3 * drip, 0, 1), 1 - 0.6 * drip - 0.2 * ramp(v, 0.7, 0.78)


def p_round(v):
    """Rounded top (parapet coping, rail cap, gasket): a convex half-cylinder across v."""
    x = 2 * v - 1
    h = np.sqrt(np.clip(1 - x * x, 0, 1)) ** 0.7
    return h, 0.85 + 0.15 * h


def p_gutter(v):
    """Half-round gutter seen from outside: rolled bead at the top, round belly."""
    bead = bump(v, 0.09, 0.04)
    x = (v - 0.18) / 0.82
    belly = np.where(v > 0.18, np.sin(np.pi * np.clip(x, 0, 1)) ** 0.6, 0)
    h = np.maximum(0.8 * bead, belly)
    return h, 1 - 0.35 * bump(v, 0.17, 0.02) - 0.2 * ramp(v, 0.85, 1.0)


def p_fascia(v):
    """Fascia board: flat with a small drip lip along its bottom edge."""
    h = 0.85 * ramp(v, 0.0, 0.05) + 0.15 * ramp(v, 0.84, 0.88)
    h = h * (1 - ramp(v, 0.96, 1.0))
    return h, 1 - 0.3 * bump(v, 0.86, 0.015)


def p_louvre(v, n=6, border=0.07):
    """Vent grille: n sloped louvres between two border bands; each louvre throws a dark gap below it."""
    inner = (v - border) / (1 - 2 * border)
    t = (inner * n) % 1.0
    louv = np.where((inner > 0) & (inner < 1), 0.25 + 0.75 * (1 - t), 1.0)
    gap = np.where((inner > 0) & (inner < 1), ramp(t, 0.80, 0.9) * (1 - ramp(t, 0.97, 1.0)), 0)
    h = np.clip(louv - 0.6 * gap, 0, 1)
    return h, 1 - 0.75 * gap


def p_slats(v, n=2):
    """Garage-door slats: n boards with V-grooves between them."""
    t = (v * n) % 1.0
    groove = bump(t, 0.0, 0.035) + bump(t, 1.0, 0.035)
    return np.clip(1 - 0.8 * groove, 0, 1), 1 - 0.6 * groove


def p_lip(v):
    """Thin frame with a raised lighter lip on top (solar module frame / flashing)."""
    h = 0.7 + 0.3 * (1 - ramp(v, 0.25, 0.35))
    return h, 1 - 0.25 * bump(v, 0.33, 0.03)


def p_flat(v):
    return np.ones_like(v), np.ones_like(v)


# name, height px, profile, base colour, roughness, metallic, U-detail (kind, amount), edge-lift, use
STRIPS = [
    ("window_frame_dark", 64, p_frame, c("frame_dark"), 0.45, 0.0, ("paint", 0.012), 0.10,
     "Dark aluminium window frames and mullions (the slim dark frames of the concept's big windows)."),
    ("window_frame_cream", 64, p_frame, c("trim_cream"), 0.55, 0.0, ("paint", 0.018), 0.05,
     "Cream window / glazing frames (the light frames inside the big window surrounds)."),
    ("window_surround_cream", 128, p_surround, c("trim_cream"), 0.70, 0.0, ("concrete", 0.022), 0.05,
     "Deep cream window surrounds / reveals around the big picture windows (about 25 cm deep)."),
    ("door_frame_cream", 64, p_architrave, c("trim_cream"), 0.60, 0.0, ("paint", 0.018), 0.05,
     "Door frames / architraves and the door canopy edge."),
    ("sill_cream", 64, p_sill, c("trim_cream"), 0.70, 0.0, ("concrete", 0.022), 0.05,
     "Window sills and ledges (top + rounded nose + drip groove)."),
    ("coping_cream", 96, p_round, c("printed_concrete"), 0.75, 0.0, ("concrete", 0.024), 0.05,
     "Rounded coping on the printed-concrete parapets / roof-terrace walls and chimney caps."),
    ("gutter_dark", 64, p_gutter, rgb(64, 64, 70), 0.40, 0.0, ("paint", 0.012), 0.12,
     "Half-round gutters (outside face) and, mapped around a cylinder, downpipes."),
    ("fascia_dark", 96, p_fascia, rgb(70, 66, 70), 0.55, 0.0, ("paint", 0.012), 0.08,
     "Roof fascia / barge boards along the eaves and gable edges."),
    ("railing_cap_steel", 32, p_round, rgb(176, 178, 182), 0.30, 1.0, ("brushed", 0.035), 0.0,
     "Brushed stainless handrail cap and glass-railing clamps on the roof terraces (metallic)."),
    ("vent_louvre", 128, p_louvre, rgb(120, 122, 128), 0.50, 0.0, ("paint", 0.018), 0.10,
     "Wall vents / AC grille: horizontal louvres; frame it with window_frame_dark."),
    ("garage_door_slats", 128, p_slats, c("shed_wood"), 0.65, 0.0, ("wood", 0.050), 0.04,
     "Garage door / carport store: dark wood-look horizontal slats (2 boards per strip height)."),
    ("solar_frame", 32, p_lip, rgb(62, 64, 72), 0.35, 0.6, ("brushed", 0.025), 0.18,
     "Solar module frame edges (anodised aluminium) and roof-window frames."),
    ("flashing_dark", 32, p_lip, rgb(88, 90, 96), 0.50, 0.3, ("paint", 0.020), 0.10,
     "Lead-grey flashing around the chimney and roof edges, ridge capping."),
    ("seal_rubber", 16, p_round, rgb(30, 30, 33), 0.80, 0.0, ("paint", 0.010), 0.0,
     "Rubber gaskets / glazing seals (thin dark line between frame and glass)."),
    ("plain_dark", 16, p_flat, c("frame_dark"), 0.50, 0.0, ("paint", 0.010), 0.0,
     "Flat frame_dark colour for tiny parts (hinges, handles' backplates, bolts)."),
]


def u_detail(kind, amount, h, seed):
    """Painterly variation along U (periodic in U over 2048 px), shape (h, W)."""
    rng_seed = 1000 + seed
    if kind == "brushed":
        n = T.periodic_noise(max(h, 8), W, None, rng_seed, aniso=(0.8, 60))[:h]
    elif kind == "wood":
        n = 0.6 * T.periodic_noise(max(h, 8), W, None, rng_seed, aniso=(0.8, 30))[:h] + \
            0.25 * T.periodic_noise(max(h, 8), W, None, rng_seed + 2, aniso=(0.6, 6))[:h] + \
            0.4 * T.periodic_noise(max(h, 8), W, None, rng_seed + 1, aniso=(5, 160))[:h]
    elif kind == "concrete":
        n = 0.6 * T.periodic_noise(max(h, 8), W, None, rng_seed, aniso=(2.0, 3.0))[:h] + \
            0.6 * T.periodic_noise(max(h, 8), W, None, rng_seed + 1, aniso=(20, 120))[:h]
    else:  # paint: soft long brush strokes along U plus a little grain
        n = 0.7 * T.periodic_noise(max(h, 8), W, None, rng_seed, aniso=(14, 160))[:h] + \
            0.35 * T.periodic_noise(max(h, 8), W, None, rng_seed + 1, aniso=(1.0, 2.0))[:h]
    n = n - n.mean()
    return amount * n / max(n.std(), 1e-6)


def build():
    alb = np.zeros((H, W, 3), np.float32)
    height = np.zeros((H, W), np.float32)
    orm = np.zeros((H, W, 3), np.float32)
    meta = []
    y = 0
    for i, (name, hpx, prof, col, rough, metal, (kind, amt), lift, use) in enumerate(STRIPS):
        v = (np.arange(hpx, dtype=np.float32) + 0.5) / hpx
        hv, ao = prof(v)
        hv = np.asarray(hv, np.float32)[:, None] * np.ones((1, W), np.float32)
        ao = np.asarray(ao, np.float32)[:, None] * np.ones((1, W), np.float32)
        det = u_detail(kind, amt, hpx, i)
        # convex edges catch a little painted highlight ("edge lift"), cavities darken (ao)
        slope = np.abs(np.gradient(hv, axis=0)) * hpx / 8.0
        edge = np.clip(slope, 0, 1) * (hv > 0.5)
        lum = (1.0 + det / max(float(col @ T.LUMA), 0.05) + lift * edge) * ao
        a = col[None, None, :] * lum[..., None]
        if kind == "brushed":
            a = a * (1 + 0.5 * det[..., None])
        alb[y:y + hpx] = a
        height[y:y + hpx] = hv * (hpx / 64.0) ** 0.5           # taller strips get a deeper relief
        orm[y:y + hpx, :, 0] = 0.6 + 0.4 * ao
        orm[y:y + hpx, :, 1] = np.clip(rough + 0.05 * det / max(amt, 1e-6) * 0.5, 0.05, 1)
        orm[y:y + hpx, :, 2] = metal
        meta.append({
            "name": name, "use": use,
            "px": [0, y, W, y + hpx],
            "uv_gltf": [0.0, round(y / H, 6), 1.0, round((y + hpx) / H, 6)],
            "uv_blender": [0.0, round(1 - (y + hpx) / H, 6), 1.0, round(1 - y / H, 6)],
            "profile_width_m": round(hpx / PX_PER_M, 4),
            "u_repeat_m": W / PX_PER_M,
            "roughness": rough, "metallic": metal,
            "albedo_srgb": [int(round(x * 255)) for x in col],
        })
        y += hpx
    assert y == H, y
    nrm = T.normal_from_height(height, 6.0)
    # strips are independent: flatten the normal across strip borders so one strip never leans into the next
    yb = 0
    for s in STRIPS:
        nrm[yb] = nrm[yb + s[1] - 1] = (0.5, 0.5, 1.0)
        yb += s[1]
    return np.clip(alb, 0, 1), nrm, orm, meta


def main():
    alb, nrm, orm, meta = build()
    T.save(alb, os.path.join(OUT, "trim_sheet_house.png"))
    T.save(nrm, os.path.join(OUT, "trim_sheet_house_normal.png"))
    T.save(orm, os.path.join(OUT, "trim_sheet_house_orm.png"))
    doc = {
        "_doc": "Showhome house trim sheet. Every strip spans the full width and tiles along U; map a part's long "
                "axis to U and its profile across the strip's V range. Texel density 512 px/m -> U repeat 4.0 m; "
                "'profile_width_m' is the real width a strip is drawn for (scale V to fit other widths). "
                "uv_gltf: (u0, v0, u1, v1) with v down from the image top (glTF / Bevy). uv_blender: v up from the "
                "bottom (Blender UV editor; the glTF exporter flips it). Inset UVs by about 2 px (0.002 in V) from "
                "a strip's edges so mips do not bleed the neighbouring strip in. Textures: albedo "
                "trim_sheet_house.png (sRGB), normal trim_sheet_house_normal.png (linear, OpenGL/glTF +Y), "
                "trim_sheet_house_orm.png (linear: R occlusion, G roughness, B metallic).",
        "texture": "trim_sheet_house.png", "normal": "trim_sheet_house_normal.png", "orm": "trim_sheet_house_orm.png",
        "size_px": [W, H], "px_per_m": PX_PER_M, "u_repeat_m": W / PX_PER_M,
        "strips": meta,
    }
    with open(os.path.join(OUT, "trims.json"), "w") as f:
        json.dump(doc, f, indent=1)
    # labelled preview
    os.makedirs(PREV, exist_ok=True)
    im = Image.open(os.path.join(OUT, "trim_sheet_house.png")).convert("RGB")
    lab = Image.new("RGB", (W + 420, H), (24, 26, 30))
    lab.paste(im, (0, 0))
    d = ImageDraw.Draw(lab)
    for m in meta:
        y0, y1 = m["px"][1], m["px"][3]
        d.line([(W, y0), (W + 420, y0)], fill=(90, 90, 90))
        d.text((W + 8, y0 + 2), f"{m['name']}  {y1 - y0}px  {m['profile_width_m'] * 100:.1f}cm", fill=(235, 235, 235))
    lab.save(os.path.join(PREV, "trim_sheet_labelled.png"))
    for m in meta:
        print(f"{m['name']:22s} px y {m['px'][1]:4d}-{m['px'][3]:4d}  uv_gltf v {m['uv_gltf'][1]:.4f}-{m['uv_gltf'][3]:.4f}")


if __name__ == "__main__":
    main()
