"""Qwen Image 2.1 image edit through ComfyUI (official template graph, flattened to API form). No LoRAs.

  python qwen_edit.py --image in.png [--image ref2.png] --prompt "..." --out out.png [--seed 1 --steps 30 --res 0]

image_1 is the edit target (output size follows it when --res 0); refer to images as <image1>, <image2>...
Graph (from user/default/workflows/Qwen 2.1/01 Qwen 2.1 image edit (official template).json):
UNETLoader qwen_image_2.1_int8_convrot -> QwenImage21Cache(auto) -> KSampler(euler/simple, cfg 1)
CLIPLoader qwen3vl_8b_int8_convrot (type qwen_image) -> TextEncodeQwenImage21(images, vae) -> pos/neg/latent
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import uuid

sys.path.insert(0, os.path.dirname(__file__))
import comfy_gen as cg  # noqa: E402


def graph(names, prompt, seed, steps, res, prefix, w=None, h=None):
    g = {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": "qwen_image_2.1_int8_convrot.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "QwenImage21Cache", "inputs": {"model": ["1", 0], "device": "auto", "dtype": "default"}},
        "3": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": "qwen3vl_8b_int8_convrot.safetensors", "type": "qwen_image",
                         "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_2.1_vae_bf16.safetensors"}},
        "6": {"class_type": "TextEncodeQwenImage21",
              "inputs": {"clip": ["3", 0], "prompt": prompt, "negative_prompt": "", "resolution": res,
                         "vae": ["4", 0]}},
        "7": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": steps, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
                         "denoise": 1.0, "model": ["2", 0], "positive": ["6", 0], "negative": ["6", 1],
                         "latent_image": ["6", 2]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["4", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["8", 0]}},
    }
    for i, n in enumerate(names, 1):
        g[f"5{i}"] = {"class_type": "LoadImage", "inputs": {"image": n}}
        g["6"]["inputs"][f"images.image_{i}"] = [f"5{i}", 0]
    if w and h:
        g["10"] = {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}
        g["7"]["inputs"]["latent_image"] = ["10", 0]
    return g


def run(images, prompt, out, seed=1, steps=30, res=0, w=None, h=None):
    names = [cg.upload_image(p) for p in images]
    prefix = "valetf_qwen_" + uuid.uuid4().hex[:8]
    g = graph(names, prompt, seed, steps, res, prefix, w, h)
    t0 = time.time()
    try:
        pid = cg._post("/prompt", {"prompt": g, "client_id": "valetf-qwen"})["prompt_id"]
    except Exception as e:  # noqa
        body = getattr(e, "read", lambda: b"")().decode(errors="replace")
        raise RuntimeError(f"{e} {body[:3000]}")
    while True:
        hist = json.loads(cg._get(f"/history/{pid}"))
        if pid in hist:
            st = hist[pid].get("status", {})
            if st.get("status_str") == "error":
                raise RuntimeError(json.dumps(st)[:3000])
            imgs = [im for node in hist[pid].get("outputs", {}).values() for im in node.get("images", [])]
            if imgs:
                im = imgs[0]
                q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im["subfolder"],
                                            "type": im["type"]})
                os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
                open(out, "wb").write(cg._get("/view?" + q))
                dt = time.time() - t0
                print(f"saved {out} ({dt:.1f}s)", flush=True)
                return dt
        if time.time() - t0 > 1200:
            raise TimeoutError
        time.sleep(1.5)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", action="append", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--res", type=int, default=0)
    ap.add_argument("--w", type=int, default=None)
    ap.add_argument("--h", type=int, default=None)
    a = ap.parse_args()
    run(a.image, a.prompt, a.out, a.seed, a.steps, a.res, a.w, a.h)
