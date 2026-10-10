# Reproducible local image → TRELLIS prop workflow

The current user authorization permits TRELLIS experiments for loose props. Structural maps, buildings, terrain, doors and exact gameplay collision continue to use the procedural kit. This instruction supersedes the older “characters only / procedural-only props” preference; the older experiment's cleanup findings remain useful.

**What was confirmed on 10 October 2026 (Brussels time).** ComfyUI 0.37.0 answers at `http://127.0.0.1:8188`. Qwen Image 2.1 nodes are registered, and all ten required Krea/Qwen/TRELLIS weight files are both listed by their loaders and present on disk. This is installation/graph availability, not a new successful generation test. The audit sent GET requests only and submitted zero GPU jobs. Never use port 8199. See [availability snapshot](ai_prop_workflow/audit/availability.json).

**The supplied blue toilet image has a confirmed different history.** Its PNG contains a Hunyuan3D 2.1 API prompt: checkpoint `hunyuan_3d_v2.1.safetensors`, seed 42, 30 steps, CFG 5, Euler/normal, octree 256, and background removal/crop to white at 1024² with padding 1.18. It is a preprocessing preview, not evidence of Qwen or TRELLIS image generation. Its input `PICK_d_portapotty.png` is byte-identical to `d_portapotty_s11.png`; that PNG names **Krea2 Turbo**, seed **11**, **8 steps**, CFG **1**, Euler/simple, **1024²**, no LoRA. The Qwen-named encoder/VAE in that Krea graph do not make it a Qwen Image generator.

The recovered originals are [source image](ai_prop_workflow/inputs/portapotty_source_krea_s11.png), [attached preprocessing image](ai_prop_workflow/inputs/portapotty_hunyuan_prep.png), [Krea API prompt](ai_prop_workflow/workflows/portapotty_krea_seed11.recovered.api.json) and [Hunyuan API prompt](ai_prop_workflow/workflows/portapotty_hunyuan_prep.recovered.api.json). Neither PNG includes an editor `workflow` field; their `prompt` API graphs were recovered without inventing UI graphs. Historical upload filenames inside those graphs must be replaced if queued; the provided wrappers upload fresh input names automatically.

**The portable bundle** is `F:/git/val etf/art/briefs/showhome_v3_handoff/ai_prop_workflow`. It contains copied inputs, recovered API prompts, actual Qwen editor workflows, the actual TRELLIS template, scripts, prompts and a hashed source manifest. No model weights or GLBs were copied. Original scripts and Kestrel GLBs were left untouched. Three documented changes affect copied helpers only: pin the endpoint to 8188, use the bundled TRELLIS template, and import the bundled Qwen helpers. [Source paths, hashes and changes](ai_prop_workflow/audit/source_manifest.json).

1. **Audit or dry-build first; these commands do not generate.** Run from the repository root:

   ```powershell
   $pack = 'F:/git/val etf/art/briefs/showhome_v3_handoff/ai_prop_workflow'
   $env:COMFY_URL = 'http://127.0.0.1:8188'
   python "$pack/scripts/offline_audit.py"
   python "$pack/scripts/trellis_gen.py" --image "$pack/inputs/portapotty_source_krea_s11.png" --out "$pack/runs/dry.glb" --seed 42 --faces 700000 --tex 4096 --dry
   ```

   The offline check verifies copied hashes, graph rebuilding and node links against the saved server snapshot. `--dry` reads live node definitions and prints the graph; it does not upload the image or post `/prompt`.

2. **After the TDM GPU tests finish, make or edit one clean input.** The style target is one isolated object, full silhouette with margin, a front three-quarter view, broad painted colour blocks, chunky readable geometry, softly bevelled edges and an even grey/white background. Keep the image free of small lettering, logos, cast-shadow clutter and multiple views. The [exact recovered portable-toilet prompt](ai_prop_workflow/prompts/krea_portapotty_seed11.txt) preserves the confirmed example.

   For Qwen text-to-image, open [the actual local Qwen 2.1 editor workflow](ai_prop_workflow/workflows/qwen21_text_to_image.ui.json) in ComfyUI, replace its sample prompt with the prop description/style, and fix seed 11, 1024², 25 steps, CFG 1, Euler/simple. That is a proposed Qwen rendition, not the origin of the supplied PNG. Its embedded subgraph UUIDs belong in the ComfyUI editor; do not feed this UI JSON directly into `/prompt` or the simple UI→API converter.

   For the already recovered, flat API **Qwen edit → TRELLIS** route, use the existing edit script copied from the scratchpad. `<image1>` is the canvas; state which geometry/camera/colours stay fixed and what finish changes. The following is a new edit experiment, with no LoRA:

   ```powershell
   python "$pack/scripts/qwen_edit.py" --image "$pack/inputs/portapotty_source_krea_s11.png" --prompt (Get-Content -Raw "$pack/prompts/qwen_clean_prop_edit.txt") --out "$pack/runs/prop_qwen21.png" --seed 11 --steps 25 --res 0
   ```

   `--res 0` retains the 1024² canvas size. It uses `qwen_image_2.1_int8_convrot.safetensors`, `qwen3vl_8b_int8_convrot.safetensors`, `qwen_image_2.1_vae_bf16.safetensors`, `QwenImage21Cache` and `TextEncodeQwenImage21`. The generated [Qwen edit API graph](ai_prop_workflow/workflows/qwen21_clean_prop_edit.api.json) was rebuilt and checked offline; inference was deliberately not run during this audit.

   To reproduce the historical Krea input instead:

   ```powershell
   python "$pack/scripts/comfy_gen.py" --prompt (Get-Content -Raw "$pack/prompts/krea_portapotty_seed11.txt") --out "$pack/runs/prop_krea.png" --w 1024 --h 1024 --seed 11 --steps 8
   ```

3. **Convert the selected image with the verified TRELLIS.2 branch.** Run one job at a time after GPU tests and any existing `gpu_busy` reservation have cleared. Background removal is already in this graph; do not combine the supplied Hunyuan prep graph with TRELLIS as though it were a text-to-image stage.

   ```powershell
   python "$pack/scripts/trellis_gen.py" --image "$pack/runs/prop_qwen21.png" --out "$pack/runs/prop_trellis_full.glb" --seed 42 --faces 700000 --tex 4096 --steps-mult 1.0
   ```

   The copied wrapper switches the template from its default Pixal3D branch to **TRELLIS.2**, resolves switches, prunes unused outputs, and replaces viewport-dependent `Save3DAdvanced` with `SaveGLB`. Full-quality settings match the recorded prop experiment: 1536 upsample, 700k face target, 4096 atlas, remesh resolution 768, UDF, 20 smoothing iterations. Default CLI settings are 80k faces / 2048 atlas if those flags are omitted. [Frozen full graph](ai_prop_workflow/workflows/trellis2_seed42_full.api.json).

   Base seed 42 becomes these actual sampler seeds because the script adds each node id:

   | Stage | Node | Seed | Steps |
   |---|---:|---:|---:|
   | Structure | 12 | 54 | 12 |
   | Shape | 18 | 60 | 20 |
   | Upsample | 3 | 45 | 12 |
   | Texture | 23 | 65 | 12 |

4. **Inspect and prepare an experimental prop before catalog integration.** The supplied [processing script](ai_prop_workflow/scripts/process_prop.py) measures topology/UVs, centres the mesh at ground level, makes budget variants and rebakes. It writes into the specified new run folder and does not edit the source GLB:

   ```powershell
   $env:BAKE_DEVICE = 'CPU'
   & 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b --factory-startup -P "$pack/scripts/process_prop.py" -- prop_trial "$pack/runs/prop_trellis_full.glb" "$pack/runs/review" 0 4500
   ```

   This is a review/bake stage, not automatic game-ready export. Check real-world scale, normals, UV coverage, material roughness/metalness and silhouette from several angles; author independent appropriate collision, `phys` assignments, LOD1, shared external textures and metadata before adding a reusable prop. Structural map work continues procedurally. The [existing local TRELLIS test report](../../../assets/props/_tests/trellis2/REPORT.md) recorded double-layer shells, normalised scale and UV-preserving decimation stalls; its exterior-cull → fresh UV → emission-basecolour rebake route is included here. Hard props may still need substantial cleanup, but the user's current loose-prop experiment is authorized.

Existing Kestrel TRELLIS samples remain in `F:/git/val etf/assets/characters/kestrel/trellis` (seeds 7, 42, 123 and 2024). Their presence demonstrates saved outputs; this audit neither identifies the unspecified attached GLB with a particular seed nor edits or copies it.
