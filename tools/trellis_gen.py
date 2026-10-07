"""Image -> textured 3D model (GLB) with TRELLIS.2 through ComfyUI's bundled template.

  python tools/trellis_gen.py --image concept.png --out model.glb [--seed 42] [--dry]

Background is removed automatically (BiRefNet). Best input: one subject, full view, plain background.
"""
import argparse
import json
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
import comfy_gen as cg  # noqa: E402
import comfy_ui2api as u2a  # noqa: E402

TEMPLATE = (r"C:/Users/alexw/AppData/Roaming/StabilityMatrix/Packages/ComfyUI/venv/Lib/site-packages/"
            r"comfyui_workflow_templates_json/templates/3d_pixal3d_trellis2_image_to_model.json")
COMFY_ROOT = r"C:/Users/alexw/AppData/Roaming/StabilityMatrix/Packages/ComfyUI"


def build(image_name, seed, prefix, info, faces=80000, tex=2048):
    ui = json.load(open(TEMPLATE, encoding="utf-8"))
    api = u2a.convert(ui, info)
    # choose the TRELLIS.2 branch (template default is Pixal3D)
    for nid, n in api.items():
        if n["class_type"] == "PrimitiveBoolean":
            n["inputs"]["value"] = True
        if n["class_type"] == "LoadImage":
            n["inputs"]["image"] = image_name
        if n["class_type"] == "DecimateMesh":
            n["inputs"]["target_face_count"] = faces
        if n["class_type"] == "PrimitiveInt":  # texture atlas size
            n["inputs"]["value"] = tex
        if n["class_type"] == "KSampler":
            n["inputs"]["seed"] = seed + int(nid)
        if n["class_type"] == "Save3DAdvanced":  # needs a live 3D viewport; use the plain GLB saver
            api[nid] = {"class_type": "SaveGLB",
                        "inputs": {"mesh": n["inputs"]["model_3d"], "filename_prefix": prefix}}
    api = u2a.resolve_switches(api)
    save = [nid for nid, n in api.items() if n["class_type"] == "SaveGLB"]
    return u2a.prune(api, info, keep_outputs=save)


def run(image, out, seed=42, dry=False, faces=80000, tex=2048):
    info = u2a.object_info(cg.COMFY)
    prefix = "valetf_" + os.path.splitext(os.path.basename(out))[0]
    name = cg.upload_image(image) if not dry else "dry.png"
    api = build(name, seed, prefix, info, faces, tex)
    if dry:
        for nid, n in sorted(api.items(), key=lambda x: int(x[0])):
            print(nid, n["class_type"], json.dumps(n["inputs"])[:220])
        return
    t0 = time.time()
    try:
        res = cg._post("/prompt", {"prompt": api, "client_id": "valetf-trellis"})
    except urllib.error.HTTPError as e:
        print(e.read().decode()[:4000])
        raise
    pid = res["prompt_id"]
    while True:
        hist = json.loads(cg._get(f"/history/{pid}"))
        if pid in hist:
            st = hist[pid].get("status", {})
            if st.get("status_str") == "error":
                print(json.dumps(st)[:4000])
                raise RuntimeError("generation failed")
            if st.get("completed"):
                break
        if time.time() - t0 > 3600:
            raise TimeoutError
        time.sleep(3)
    # newest matching file in output/3d
    d = os.path.join(COMFY_ROOT, "output")
    cands = [os.path.join(d, f) for f in os.listdir(d) if f.startswith(prefix)]
    if not cands:
        print(json.dumps(hist[pid].get("outputs"))[:3000])
        raise FileNotFoundError("no 3D output found")
    src = max(cands, key=os.path.getmtime)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    shutil.copy(src, out)
    print(f"saved {out} from {src} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--faces", type=int, default=80000, help="triangle budget of the output mesh")
    ap.add_argument("--tex", type=int, default=2048, help="texture atlas size")
    a = ap.parse_args()
    run(a.image, a.out, a.seed, a.dry, a.faces, a.tex)
