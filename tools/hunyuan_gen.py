"""Image -> untextured 3D shape (GLB) with Hunyuan3D 2.1 through ComfyUI's bundled template.

  python tools/hunyuan_gen.py --image concept.png --out model.glb [--seed 42] [--dry]
  higher quality sampling: --steps 50

The template (3d_hunyuan3d-v2.1) makes SHAPE ONLY: DINOv2 image conditioning, 30 steps cfg 5, VAE decode on a
256^3 grid, surface-net mesher at 0.6. This wrapper adds what the template leaves out: BiRefNet background
removal and a recentre on white with ~15 % border (Hunyuan's own preprocessing: object on a clean white
background, longest side ~85 % of the frame).

Notes (ComfyUI 0.37, this install):
- octree_resolution > 256 decodes fine on the GPU, but ComfyUI's surface-net VoxelToMesh is a Python loop that
  gathers 8 int64 corners for every cell: ~11 GB of RAM at 384 and ~26 GB at 512. Do not go above 256 here.
  For 512, see assets/props/_tests/hunyuan21/scripts/hq_run.py (same ComfyUI code + marching cubes, own process).
- That surface net also joins every 2x2 block of active cells, so flat axis-aligned walls come out as stacked
  internal sheets (tens of thousands of non-manifold edges); Blender's collapse decimate then stalls or tears.
- --save-latent fails here: SaveLatent (safetensors temp file) cannot write into the symlinked output folder.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys
import time
import urllib.error

sys.path.insert(0, os.path.dirname(__file__))
import comfy_gen as cg  # noqa: E402
import comfy_ui2api as u2a  # noqa: E402

TEMPLATE = (r"C:/Users/alexw/AppData/Roaming/StabilityMatrix/Packages/ComfyUI/venv/Lib/site-packages/"
            r"comfyui_workflow_templates_json/templates/3d_hunyuan3d-v2.1.json")
COMFY_ROOT = r"C:/Users/alexw/AppData/Roaming/StabilityMatrix/Packages/ComfyUI"


def build(image_name, seed, prefix, info, steps=30, cfg=5.0, octree=256, num_chunks=8000, tokens=4096,
          mesher="surface net", threshold=0.6, remove_bg=True, pad=1.18, bg="#FFFFFF", save_latent=False):
    ui = json.load(open(TEMPLATE, encoding="utf-8"))
    api = u2a.convert(ui, info)
    load = next(nid for nid, n in api.items() if n["class_type"] == "LoadImage")
    for nid, n in api.items():
        ct, inp = n["class_type"], n["inputs"]
        if ct == "LoadImage":
            inp["image"] = image_name
        elif ct == "KSampler":  # template: 30 steps, cfg 5, euler / normal, seed randomised
            inp.update({"seed": seed, "steps": steps, "cfg": cfg})
        elif ct == "EmptyLatentHunyuan3Dv2":  # template: 4096 latent tokens
            inp["resolution"] = tokens
        elif ct == "VAEDecodeHunyuan3D":  # template: 8000 / 256
            inp.update({"num_chunks": num_chunks, "octree_resolution": octree})
        elif ct == "VoxelToMesh":  # template: surface net, 0.6
            inp.update({"algorithm": mesher, "threshold": threshold})
        elif ct == "SaveGLB":
            inp["filename_prefix"] = prefix
    clip_enc = next(nid for nid, n in api.items() if n["class_type"] == "CLIPVisionEncode")
    if remove_bg:
        api["900"] = {"class_type": "LoadBackgroundRemovalModel", "inputs": {"bg_removal_name": "birefnet.safetensors"}}
        api["901"] = {"class_type": "RemoveBackground", "inputs": {"bg_removal_model": ["900", 0], "image": [load, 0]}}
        api["902"] = {"class_type": "ImageCropToMask",
                      "inputs": {"images": [load, 0], "masks": ["901", 0], "width": 1024, "height": 1024,
                                 "pad_factor": pad, "grow_mask": 0, "background": bg}}
        api[clip_enc]["inputs"]["image"] = ["902", 0]
        api["903"] = {"class_type": "SaveImage", "inputs": {"images": ["902", 0], "filename_prefix": prefix + "_prep"}}
    if save_latent:
        ks = next(nid for nid, n in api.items() if n["class_type"] == "KSampler")
        api["904"] = {"class_type": "SaveLatent", "inputs": {"samples": [ks, 0], "filename_prefix": prefix + "_latent"}}
    return api


def _logs():
    try:
        return json.loads(cg._get("/internal/logs/raw")).get("entries", [])
    except Exception:  # noqa
        return []


def parse_timings(lines):
    """sampler / volume-decode / total seconds from ComfyUI's tqdm lines"""
    out = {}
    txt = "".join(e["m"] for e in lines)
    def secs(s):
        p = [int(x) for x in s.split(":")]
        return sum(v * 60 ** i for i, v in enumerate(reversed(p)))
    ks = re.findall(r"(\d+)/(\d+) \[(\d+:\d+(?::\d+)?)<", txt)
    vol = re.findall(r"Volume Decoding:\s+100%[^\[]*\[(\d+:\d+(?::\d+)?)<", txt)
    for a, b, t in ks:
        if a == b and int(b) <= 200:
            out["sampler_secs"] = secs(t)
    if vol:
        out["volume_decode_secs"] = secs(vol[-1])
    m = re.findall(r"Prompt executed in ([\d.]+) seconds", txt)
    if m:
        out["comfy_total_secs"] = float(m[-1])
    return out


def run(image, out, seed=42, dry=False, prep_out=None, latent_out=None, **kw):
    info = u2a.object_info(cg.COMFY)
    prefix = "valetf_hy_" + os.path.splitext(os.path.basename(out))[0]
    name = cg.upload_image(image) if not dry else "dry.png"
    api = build(name, seed, prefix, info, save_latent=latent_out is not None, **kw)
    if dry:
        for nid, n in sorted(api.items(), key=lambda x: int(x[0])):
            print(nid, n["class_type"], json.dumps(n["inputs"])[:220])
        return {}
    t_iso = datetime.datetime.now().isoformat()
    t0 = time.time()
    try:
        res = cg._post("/prompt", {"prompt": api, "client_id": "valetf-hunyuan"})
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
        time.sleep(2)
    wall = time.time() - t0
    time.sleep(1.0)
    new = [e for e in _logs() if e.get("t", "") >= t_iso]  # the log is a ring buffer: filter by time
    tm = parse_timings(new)
    tm["wall_secs"] = round(wall, 1)
    outs = hist[pid].get("outputs", {})
    d = os.path.join(COMFY_ROOT, "output")
    cands = [os.path.join(d, f) for f in os.listdir(d) if f.startswith(prefix) and f.endswith(".glb")]
    if not cands:
        print(json.dumps(outs)[:3000])
        raise FileNotFoundError("no GLB output found")
    src = max(cands, key=os.path.getmtime)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    shutil.copy(src, out)
    for node in outs.values():
        for im in node.get("images", []):
            if prep_out and im["filename"].startswith(prefix + "_prep"):
                shutil.copy(os.path.join(d, im["subfolder"], im["filename"]), prep_out)
        for lt in node.get("latents", []):
            if latent_out:
                shutil.copy(os.path.join(d, lt["subfolder"], lt["filename"]), latent_out)
    with open(os.path.splitext(out)[0] + "_comfy.log", "w", encoding="utf-8") as f:
        f.write("".join(e["t"] + " " + e["m"] for e in new))
    print(f"saved {out} from {src} ({wall:.0f}s) {json.dumps(tm)}")
    return tm


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--steps", type=int, default=30, help="template 30")
    ap.add_argument("--cfg", type=float, default=5.0, help="template 5")
    ap.add_argument("--octree", type=int, default=256, help="VAE decode grid (template 256; >256 needs a lot of RAM "
                                                            "in the surface-net mesher, see module doc)")
    ap.add_argument("--num-chunks", type=int, default=8000)
    ap.add_argument("--mesher", choices=["surface net", "basic"], default="surface net")
    ap.add_argument("--threshold", type=float, default=0.6)
    ap.add_argument("--no-bg-removal", action="store_true")
    ap.add_argument("--pad", type=float, default=1.18, help="crop margin (1/0.85 = Hunyuan's 15 %% border)")
    ap.add_argument("--prep-out", default=None, help="save the preprocessed conditioning image here")
    ap.add_argument("--save-latent", default=None, help="also save the sampled latent (.latent) here")
    a = ap.parse_args()
    run(a.image, a.out, a.seed, a.dry, a.prep_out, a.save_latent, steps=a.steps, cfg=a.cfg, octree=a.octree,
        num_chunks=a.num_chunks, mesher=a.mesher, threshold=a.threshold, remove_bg=not a.no_bg_removal, pad=a.pad)
