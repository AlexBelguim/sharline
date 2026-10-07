"""Generate images (textures / concept art) with the local Krea2 Turbo model via ComfyUI.

Usage:
  python tools/comfy_gen.py --prompt "..." --out path/to/file.png [--w 1024 --h 1024 --seed 1 --steps 8]
  python tools/comfy_gen.py --prompt "..." --out tex.png --tileable      # seamless texture (circular padding)

Requires ComfyUI running at http://127.0.0.1:8188 (COMFY_URL env var overrides).
Only stdlib is used so any Python 3 works.
"""
import argparse
import json
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request
import uuid

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")


def build_graph(prompt, w, h, seed, steps, prefix):
    return {
        "10": {"class_type": "UNETLoader",
               "inputs": {"unet_name": "krea2_turbo_fp8_scaled.safetensors", "weight_dtype": "default"}},
        "11": {"class_type": "CLIPLoader",
               "inputs": {"clip_name": "qwen3vl_4b_fp8_scaled.safetensors", "type": "krea2", "device": "default"}},
        "12": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["11", 0]}},
        "13": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "3": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": steps, "cfg": 1.0, "sampler_name": "euler",
                         "scheduler": "simple", "denoise": 1.0, "model": ["10", 0],
                         "positive": ["6", 0], "negative": ["13", 0], "latent_image": ["5", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["12", 0]}},
        "29": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["8", 0]}},
    }


def build_ref_graph(prompt, refs, w, h, seed, steps, prefix, ref_boost=4.0, grounding_px=768):
    """Krea2 identity edit (LoRA krea2_identity_edit_v1_2): refs = 1 or 2 uploaded image names.
    One ref: the image to edit / the character to keep. Two refs: scene first, subject second."""
    g = {
        "10": {"class_type": "UNETLoader",
               "inputs": {"unet_name": "krea2_turbo_fp8_scaled.safetensors", "weight_dtype": "default"}},
        "71": {"class_type": "LoraLoaderModelOnly",
               "inputs": {"model": ["10", 0], "lora_name": "krea2_identity_edit_v1_2.safetensors",
                          "strength_model": 1.0}},
        "11": {"class_type": "CLIPLoader",
               "inputs": {"clip_name": "qwen3vl_4b_fp8_scaled.safetensors", "type": "krea2", "device": "default"}},
        "12": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "72": {"class_type": "LoadImage", "inputs": {"image": refs[0]}},
        "73": {"class_type": "VAEEncode", "inputs": {"pixels": ["72", 0], "vae": ["12", 0]}},
        "82": {"class_type": "EmptySD3LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "79": {"class_type": "Krea2EditModelPatch",
               "inputs": {"model": ["71", 0], "source_latent": ["73", 0], "ref_boost": ref_boost,
                          "ref_boost_a": 1.0, "fit_mode": "fit", "vae": ["12", 0], "source_image": ["72", 0],
                          "target_latent": ["82", 0]}},
        "84": {"class_type": "Krea2EditGroundedEncode",
               "inputs": {"clip": ["11", 0], "prompt": prompt, "image": ["72", 0],
                          "grounding_px": grounding_px, "system_prompt": ""}},
        "85": {"class_type": "Krea2EditGroundedEncode",
               "inputs": {"clip": ["11", 0], "prompt": "", "image": ["72", 0],
                          "grounding_px": grounding_px, "system_prompt": ""}},
        "53": {"class_type": "KSampler",
               "inputs": {"seed": seed, "steps": steps, "cfg": 1.0, "sampler_name": "euler",
                          "scheduler": "simple", "denoise": 1.0, "model": ["79", 0],
                          "positive": ["84", 0], "negative": ["85", 0], "latent_image": ["82", 0]}},
        "54": {"class_type": "VAEDecode", "inputs": {"samples": ["53", 0], "vae": ["12", 0]}},
        "29": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["54", 0]}},
    }
    if len(refs) > 1:
        g["90"] = {"class_type": "LoadImage", "inputs": {"image": refs[1]}}
        g["92"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["90", 0], "vae": ["12", 0]}}
        g["79"]["inputs"].update({"source_latent_b": ["92", 0], "source_image_b": ["90", 0]})
        for k in ("84", "85"):
            g[k]["inputs"]["image_b"] = ["90", 0]
    return g


def upload_image(path):
    """Upload a local image to ComfyUI's input folder; returns the name to use in LoadImage."""
    boundary = "----valetf" + uuid.uuid4().hex
    name = "valetf_" + uuid.uuid4().hex[:8] + "_" + os.path.basename(path)
    with open(path, "rb") as f:
        data = f.read()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
            f"Content-Type: image/png\r\n\r\n").encode() + data + \
           (f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue"
            f"\r\n--{boundary}--\r\n").encode()
    req = urllib.request.Request(COMFY + "/upload/image", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.loads(r.read())
    return (res.get("subfolder") + "/" if res.get("subfolder") else "") + res["name"]


def _post(path, payload):
    req = urllib.request.Request(COMFY + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _get(path):
    with urllib.request.urlopen(COMFY + path, timeout=60) as r:
        return r.read()


def make_tileable(path):
    """Mirror-quilt the image (2x2: original, h-flip, v-flip, both) so it wraps with no seams.
    Mirror symmetry is hard to spot on noisy surface textures (metal wear, fabric, carbon)."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        print("PIL not available; skipping tileable post-process", file=sys.stderr)
        return
    img = Image.open(path).convert("RGB")
    w, h = img.size
    out = Image.new("RGB", (w * 2, h * 2))
    out.paste(img, (0, 0))
    out.paste(ImageOps.mirror(img), (w, 0))
    out.paste(ImageOps.flip(img), (0, h))
    out.paste(ImageOps.flip(ImageOps.mirror(img)), (w, h))
    out.resize((w, h), Image.LANCZOS).save(path)


def generate(prompt, out, w=1024, h=1024, seed=1, steps=8, tileable=False, refs=None, ref_boost=4.0,
             grounding_px=768):
    client = str(uuid.uuid4())
    prefix = "valetf_" + uuid.uuid4().hex[:8]
    if refs:
        names = [upload_image(r) for r in refs]
        graph = build_ref_graph(prompt, names, w, h, seed, max(steps, 10), prefix, ref_boost, grounding_px)
    else:
        graph = build_graph(prompt, w, h, seed, steps, prefix)
    res = _post("/prompt", {"prompt": graph, "client_id": client})
    pid = res["prompt_id"]
    t0 = time.time()
    while True:
        hist = json.loads(_get(f"/history/{pid}"))
        if pid in hist:
            entry = hist[pid]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(json.dumps(status)[:2000])
            imgs = [im for node in entry.get("outputs", {}).values() for im in node.get("images", [])]
            if imgs:
                im = imgs[0]
                q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im["subfolder"],
                                            "type": im["type"]})
                data = _get("/view?" + q)
                os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
                with open(out, "wb") as f:
                    f.write(data)
                if tileable:
                    make_tileable(out)
                print(f"saved {out} ({time.time() - t0:.1f}s)")
                return out
        if time.time() - t0 > 900:
            raise TimeoutError("ComfyUI generation timed out")
        time.sleep(1.5)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--w", type=int, default=1024)
    ap.add_argument("--h", type=int, default=1024)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--steps", type=int, default=8)
    ap.add_argument("--tileable", action="store_true")
    ap.add_argument("--ref", action="append", default=[],
                    help="reference image (Krea2 identity edit). Give once to edit/keep a character, twice for "
                         "scene + subject. Prompt = plain-English instruction, e.g. 'Show this exact character "
                         "from the side, full body, A-pose, plain grey background'.")
    ap.add_argument("--ref-boost", type=float, default=4.0, help="likeness dial: 1 = loose, 4 = strong, >10 over-copies")
    ap.add_argument("--grounding-px", type=int, default=768, help="384-768; lower it if outputs come out doubled/split")
    a = ap.parse_args()
    generate(a.prompt, a.out, a.w, a.h, a.seed, a.steps, a.tileable, a.ref, a.ref_boost, a.grounding_px)
