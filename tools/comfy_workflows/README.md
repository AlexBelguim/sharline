# The exact ComfyUI workflows behind the prop and Solace tests

`tools/export_prop_workflows.py` regenerates these files. It uses the same functions the test scripts used, with the
seeds of the picked results. For each workflow:
- `*.api.json` is the graph exactly as it was POSTed to ComfyUI;
- `*.ui.json` opens in the ComfyUI editor. Drag it onto the canvas, or open it from the workflow list under
  **SHARD-LINE**, where copies are already saved.

The input images are already in ComfyUI's input folder as `valetf_wf_*.png`, so every workflow opens ready to queue.
I loaded all four in ComfyUI and compared them with the API graphs:
- **01 to 03** give back identical graphs.
- **04** is the bundled TRELLIS.2 template, so it keeps its previews and notes. Every setting matches what was sent.
  The only differences: its switches pick TRELLIS.2 at run time, and it saves with `Save3DAdvanced`, because the
  script swaps that for a plain `SaveGLB` when it runs headless.

No workflow loads a style LoRA. The only LoRA in this set is the identity-edit LoRA in 02.

## The porta-potty, start to finish

| Step | File | Model | Settings |
|---|---|---|---|
| 1. Base image | `01_krea2_t2i__portapotty` | Krea2 Turbo fp8 (`krea2_turbo_fp8_scaled`), text encoder `qwen3vl_4b_fp8_scaled` (type krea2), VAE `qwen_image_vae` | 1024 × 1024, **seed 11**, 8 steps, CFG 1, euler / simple, denoise 1, negative = zeroed conditioning. The prompt is in the file (and in `assets/props/_tests/trellis2/inputs/_prompts.json`). I made seeds 11 and 23 and picked 11. |
| 2. Image to 3D | `04_trellis2_full__portapotty` | TRELLIS.2 int8 (`trellis_2_int8_convrot`), DINOv3 vision, BiRefNet background removal, shape and texture VAEs | The template's full quality: **base seed 42**, so the stage seeds are structure 54 (12 steps, CFG 1), shape 60 (20 steps, CFG 7.5), upsample 45 (12 steps, CFG 7.5, **1536**), texture 65 (12 steps, CFG 7.5, simple); remesh 768, UDF, no QEF, 20 smoothing passes; decimate to **700 000** faces; **4096** texture atlas. It took 178 s on the RTX 5080. |
| 3. Game budget (Blender, not ComfyUI) | `assets/props/_tests/trellis2/scripts/process_prop.py` | Blender 5.2, headless | Stand it on the ground with its front to −Y. Make a 90k proxy and delete faces that can never be seen (48 ray directions). Collapse to **4500** triangles. Smart UV (66°, margin 0.004). Rebake base colour (through emission), normal, roughness and metallic from the full mesh at **2048** (Cycles, selected-to-active). Output: `models/d_portapotty_budget_rebake.glb`. |

The step-3 command:

```bash
blender -b --factory-startup --python "assets/props/_tests/trellis2/scripts/process_prop.py" -- d_portapotty "assets/props/_tests/trellis2/models/d_portapotty_full.glb" "assets/props/_tests/trellis2" 0 4500
```

The duffel and the ammo can went through the same three steps, each with its own prompt and seed 11.

## Base images and their edits (the Solace test)

| File | What it did | Settings |
|---|---|---|
| `02_krea2_identity_edit__solace_no_drone` | Removed the drone from the Solace concept. This made `PICK_front.png`. | Krea2 Turbo + the identity-edit LoRA `krea2_identity_edit_v1_2` (strength 1). `Krea2EditModelPatch`: ref_boost 4, fit. `Krea2EditGroundedEncode`: grounding 768 px. Output 1024 × 1536, **seed 1**, 10 steps, CFG 1, euler / simple. I made seeds 1–3 and picked 1. |
| `03_qwen21_edit__solace_three_quarter` | Turned the drone-free front view to a three-quarter view. This made `PICK_front34.png`. | Qwen Image 2.1 int8 (`qwen_image_2.1_int8_convrot`) + `QwenImage21Cache` (auto); text encoder `qwen3vl_8b_int8_convrot` (type qwen_image); VAE `qwen_image_2.1_vae_bf16`. `TextEncodeQwenImage21`, resolution 0 (output follows the input size), empty negative, **seed 2**, 30 steps, CFG 1, euler / simple, no LoRA. You call the input image `<image1>` in the prompt. |

The same Qwen graph also made the drone-removal candidates (seeds 1–3) and the flat-light test. Only the prompt and
the seed changed; all the prompts are in `assets/characters/_tests/solace_trellis/inputs/_prompts.json`.

How I write edit prompts:
- Say exactly what to change.
- Then list what must stay the same: face, hair, outfit, colours, pose, framing, art style and background.
- For Qwen, name the images `<image1>`, `<image2>`.
- For Krea2, say "this exact character".

Which one to use:
- **Krea2 identity edit** keeps a character's identity best for a change in place.
- **Qwen 2.1** is better at moving the camera.
- For the step-1 base images, plain Krea2 text-to-image with the shared style suffix gave the cleanest results. The
  area concept art used no edits at all: reference edits copied Showhome's own content into the other areas.

## Running them from the command line

Each one is the matching script:

```bash
python tools/comfy_gen.py --prompt "<prompt>" --out out.png --w 1024 --h 1024 --seed 11 --steps 8
```

```bash
python tools/comfy_gen.py --ref source.png --prompt "<edit>" --out out.png --w 1024 --h 1536 --seed 1 --steps 10
```

```bash
python "assets/characters/_tests/solace_trellis/scripts/qwen_edit.py" --image source.png --prompt "<edit>" --out out.png --seed 2 --steps 30 --res 0
```

```bash
python tools/trellis_gen.py --image input.png --out model.glb --seed 42 --faces 700000 --tex 4096
```

Without `--faces` and `--tex`, `trellis_gen.py` falls back to 80 000 faces and a 2048 atlas.
