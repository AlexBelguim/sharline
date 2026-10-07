"""Generate the theme concept images for the TDM map (local Krea2 via ComfyUI).

Usage:  python gen_concepts.py [shot_id ...] [--seeds 11 12]
Writes candidates to ../concepts/_candidates/<shot>_s<seed>.png. The picked ones are copied
by hand to ../concepts/<shot>.png after review.
"""
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import comfy_gen  # noqa: E402

OUT = os.path.join(HERE, "..", "concepts", "_candidates")

STYLE = (" Stylized 3D game environment concept art in the style of a modern hero shooter: clean planar "
         "hard-surface shapes, generous bevels, chunky readable silhouettes, painted slightly flat materials, "
         "soft colour gradients, minimal grime, grounded near-future design, not cyberpunk, no neon. "
         "No people, no text, no letters, no logos.")

SHOTS = {
    # --- Theme A: SHOWHOME (recommended) ---------------------------------------------------------
    "A_showhome_aerial": (
        "High aerial three-quarter view of a compact multiplayer arena map set on one short suburban street "
        "in the 2060s. Two matching modern two-storey prefab show homes face each other across the street: "
        "the left house has sage-green facade panels, the right house has terracotta clay-coloured facade "
        "panels, both with rounded 3D-printed concrete corners, steep dark solar-tile gable roofs and a flat "
        "roof terrace over the attached garage. In the exact middle of the street a white boxy driverless "
        "removal truck has stopped, with moving crates and a sofa spilled on the asphalt. Small front yards "
        "with low white picket fences, back gardens with a rounded hydroponic greenhouse pod and a small shed, "
        "open carports at one end of the street, two slim utility pylons with a cable line strung across the "
        "street. The block is enclosed by tall clipped hedges; beyond them empty graded construction lots and "
        "a distant tower crane. Warm late-afternoon sun, long soft shadows." + STYLE),
    "A_showhome_ground": (
        "Eye-level view standing in the middle of a near-future suburban street in the 2060s. In the centre of "
        "the street a white boxy driverless removal truck with closed side skirts, its rear doors open, moving "
        "crates and an armchair spilled around it. On the left a modern two-storey prefab show home with "
        "sage-green facade panels, on the right a matching house with terracotta clay facade panels, both with "
        "large open upper-floor window frames looking onto the street, steep dark solar-tile roofs, low white "
        "picket fences and small front lawns. A slim utility pylon with a small service platform and a cable "
        "line crossing above the street. Clean pastel suburb that was left behind suddenly, a few dry leaves on "
        "the asphalt. Warm late-afternoon sunlight." + STYLE),
    # --- Theme B: FACADE (training mock street) --------------------------------------------------
    "B_facade_aerial": (
        "High aerial three-quarter view of a compact multiplayer arena map: a tactical training mock street "
        "built inside an enormous open-roofed steel hangar. Two simple two-storey training houses made of "
        "plywood, grey foam panels and scaffolding face each other across a painted concrete street; in the "
        "middle of the street a stripped armoured van and two stacked shipping containers serve as cover. "
        "Safety-yellow painted floor lanes, cardboard target silhouettes, sandbag walls, an overhead gantry "
        "crane with a cable running across the street, steel catwalks along the hangar walls. Bright daylight "
        "from roof skylights mixed with warm work lights." + STYLE),
    "B_facade_ground": (
        "Eye-level view inside a tactical training mock street built in a huge steel hangar: plywood and grey "
        "foam training house facades with empty window openings on both sides of a painted concrete street, a "
        "stripped armoured van with stacked shipping containers in the middle as cover, safety-yellow floor "
        "lanes, cardboard target silhouettes, sandbags, an overhead gantry crane and steel trusses, light "
        "beams from roof skylights in dusty air." + STYLE),
    # --- Theme C: SALTWAY (frontier waystation) --------------------------------------------------
    "C_saltway_aerial": (
        "High aerial three-quarter view of a compact multiplayer arena map: a small frontier waystation on "
        "bright white salt flats in the 2060s. Two homestead habitats built from stacked shipping containers "
        "with a rounded dome room face each other across a dusty freight road; in the middle of the road a "
        "stalled autonomous road-train tractor unit with a detached cargo pod serves as cover. Water condenser "
        "towers, a solar canopy carport, small fenced gardens with shade sails, a wind turbine mast with a "
        "cable line strung across the road, low adobe-style walls around each yard. Distant mesas, golden "
        "dusk light, long shadows." + STYLE),
    "C_saltway_ground": (
        "Eye-level view standing on a dusty freight road at a frontier waystation on white salt flats in the "
        "2060s: a stalled autonomous road-train tractor unit and a detached cargo pod in the centre of the road "
        "as cover, homestead habitats made of stacked shipping containers and a dome on both sides with "
        "upper-floor windows overlooking the road, water condenser towers, shade sails, low adobe walls, a "
        "cable line overhead between two masts, golden dusk light, warm dusty air." + STYLE),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shots", nargs="*")
    ap.add_argument("--seeds", nargs="*", type=int, default=[11, 12])
    a = ap.parse_args()
    shots = a.shots or list(SHOTS)
    os.makedirs(OUT, exist_ok=True)
    for seed in a.seeds:
        for s in shots:
            out = os.path.abspath(os.path.join(OUT, f"{s}_s{seed}.png"))
            if os.path.exists(out):
                print("skip", out)
                continue
            try:
                comfy_gen.generate(SHOTS[s], out, 1536, 864, seed)
            except Exception as e:  # keep going; one failure must not stop the batch
                print("FAILED", s, seed, e)
            sys.stdout.flush()


if __name__ == "__main__":
    main()
