"""Write the exact ComfyUI graphs behind the prop and Solace tests as files you can open in ComfyUI.

  python tools/export_prop_workflows.py

Builds every graph with the same functions the test scripts used (comfy_gen, qwen_edit, trellis_gen), with the
settings and seeds of the picked results, and writes tools/comfy_workflows/<name>.api.json (what was POSTed) and
<name>.ui.json (drag into ComfyUI). The input images are copied into ComfyUI's input folder as valetf_wf_*.png so
the editor workflows open ready to queue. Needs ComfyUI running; queues nothing.
"""
import copy
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "assets/characters/_tests/solace_trellis/scripts"))
import comfy_api2ui as a2u  # noqa: E402
import comfy_gen as cg  # noqa: E402
import comfy_ui2api as u2a  # noqa: E402
import qwen_edit as qe  # noqa: E402
import trellis_gen as tg  # noqa: E402

OUT = os.path.join(HERE, "comfy_workflows")
COMFY_INPUT = os.path.join(tg.COMFY_ROOT, "input")
PROPS = os.path.join(REPO, "assets/props/_tests/trellis2/inputs")
SOL = os.path.join(REPO, "assets/characters/_tests/solace_trellis/inputs")

INPUTS = {  # name in ComfyUI's input folder -> the real file the test used
    "valetf_wf_portapotty.png": os.path.join(PROPS, "PICK_d_portapotty.png"),
    "valetf_wf_solace_source.png": os.path.join(SOL, "00_source_concept_main.png"),
    "valetf_wf_solace_front.png": os.path.join(SOL, "PICK_front.png"),
}


def save(name, api, ui):
    os.makedirs(OUT, exist_ok=True)
    for ext, data in (("api", api), ("ui", ui)):
        with open(os.path.join(OUT, f"{name}.{ext}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=1)
    print("wrote", name)


def main():
    for name, src in INPUTS.items():
        shutil.copyfile(src, os.path.join(COMFY_INPUT, name))
    info = a2u.object_info()
    props = json.load(open(os.path.join(PROPS, "_prompts.json"), encoding="utf-8"))
    sol = json.load(open(os.path.join(SOL, "_prompts.json"), encoding="utf-8"))

    # 1. Krea2 Turbo text-to-image: the porta-potty input (seed 11 was picked).
    api = cg.build_graph(props["d_portapotty_s11"]["prompt"], 1024, 1024, 11, 8, "valetf_wf_krea2_t2i")
    save("01_krea2_t2i__portapotty", api, a2u.convert(api, info))

    # 2. Krea2 identity edit (comfy_gen --ref): Solace without the drone (seed 1 was picked = PICK_front.png).
    #    generate() raises the steps to at least 10 for edits; ref_boost 4.0, grounding 768 are its defaults.
    api = cg.build_ref_graph(sol["c_krea_s1.png"]["prompt"], ["valetf_wf_solace_source.png"], 1024, 1536, 1, 10,
                             "valetf_wf_krea2_edit")
    save("02_krea2_identity_edit__solace_no_drone", api, a2u.convert(api, info))

    # 3. Qwen Image 2.1 edit: Solace three-quarter view from the front pick (seed 2 was picked = PICK_front34.png).
    api = qe.graph(["valetf_wf_solace_front.png"], sol["v34_qwen_s2.png"]["prompt"], 2, 30, 0, "valetf_wf_qwen_edit")
    save("03_qwen21_edit__solace_three_quarter", api, a2u.convert(api, info))

    # 4. TRELLIS.2, full quality, seed 42: the porta-potty model. API = what trellis_gen sent; UI = the bundled
    #    template with the same switches and values, so it keeps its layout, previews and notes.
    info_u2a = u2a.object_info(cg.COMFY)
    api = tg.build("valetf_wf_portapotty.png", 42, "valetf_wf_trellis2_portapotty", info_u2a, faces=700000, tex=4096)
    ui = copy.deepcopy(json.load(open(tg.TEMPLATE, encoding="utf-8")))
    for n in ui["nodes"]:
        t, w = n["type"], n.get("widgets_values")
        if t == "PrimitiveBoolean":
            w[0] = True  # TRELLIS.2 branch (the template defaults to Pixal3D)
        elif t == "LoadImage":
            w[0] = "valetf_wf_portapotty.png"
        elif t == "KSampler":
            w[0], w[1] = 42 + n["id"], "fixed"  # trellis_gen: seed + node id -> 54 / 60 / 45 / 65
        elif t == "DecimateMesh":
            w[0] = 700000
        elif t == "PrimitiveInt" and w and w[0] in (2048, 4096):
            w[0] = 4096  # texture atlas
        elif t == "Save3DAdvanced":
            w[0] = "3d/valetf_wf_trellis2_portapotty"
    save("04_trellis2_full__portapotty", api, ui)


if __name__ == "__main__":
    main()
