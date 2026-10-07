# Shared detail-texture library (`art/textures/`)

Seamless 1024×1024 sRGB PNGs, meant to be **multiplied** over the flat palette colours through
`bc.material(..., tex=..., tex_mix=..., tex_scale=...)`. They add painted wear, weave and grain. The flat colour
still carries the look (see STYLE_GUIDE "Materials"). All of them are:

- neutral mid-light grey (luminance mean about 0.65–0.72 in sRGB) with low contrast (std 0.025–0.07), soft-clipped so
  no dark speck punches a hole in the base colour. `skin_soft` is the only one with a warm tint.
- evenly lit (light falloff and vignetting removed) and free of frames, objects or text.
- seamless in both directions (checked with 2×2 wrap tests in `_src/preview/*_wrap.png`).

## Files and recommended settings

`tex_mix` is the multiply amount (0 = flat colour, 1 = full multiply). `tex_scale` is the number of repeats per UV unit.
The values below assume the usual `bc.uv_all()` smart-UV, where each object's islands are packed into the 0–1 range,
on a typical part about 0.3–1 m across. For a much bigger or smaller object, use
**tex_scale ≈ √(object surface area in m²) × repeats/m**.

| File | What it is | Use it for | tex_mix | tex_scale | repeats/m |
|---|---|---|---|---|---|
| `worn_paint.png` | Big soft hand-painted brush strokes, a few faint hairline scratches | Painted hard surfaces: receivers, armor plates, jetpack shells, crates | **0.35** (0.25–0.45) | **1.5** | ~2.5 |
| `brushed_metal.png` | Fine horizontal brushing streaks, very uniform | Bare metal: barrels, bolts, rails, buckles (gunmetal, metal 0.85) | **0.30** (0.2–0.4) | **2.5** | ~4 |
| `polymer_stipple.png` | Fine pebbled stipple grip | Polymer furniture: grips, stocks, handguards, mag bodies | **0.40** (0.3–0.5) | **4** | ~8 |
| `fabric_ripstop.png` | Plain canvas weave with a subtle ripstop grid (8×8 grid squares per tile) | Jackets, pants, pouches, soft vest (tier 1), straps | **0.45** (0.35–0.55) | **3.5** | ~6 |
| `fabric_soft.png` | Fine jersey/stretch knit | Under-suits, base layers, sleeves, neck gaiters | **0.40** (0.3–0.55) | **4** | ~8 |
| `leather_soft.png` | Soft pebbled leather grain | Gloves, holsters, belts, boot uppers, padded straps | **0.35** (0.25–0.45) | **3** | ~6 |
| `carbon_weave.png` | Stylised 2×2 carbon twill (32 tows across) | Carbon parts: handguard panels, helmet shells, jetpack fins, plate covers | **0.45** (0.35–0.6) | **3** | ~5 |
| `skin_soft.png` | Very soft warm-neutral painterly mottling (no features or pores) | Skin (face, hands, neck) | **0.20** (0.15–0.3) | **1** | ~1.5 |
| `hair_strands.png` | Painted straight hair strands running **vertically (along V)** | Hair meshes or hair cards; strands follow the texture's V axis | **0.50** (0.35–0.6) | **1.5** | ~2 along the hair |

Example:

```python
import os, blender_common as bc
m = bc.material("M_Mako_Receiver", (0.55, 0.52, 0.46), rough=0.6,
                tex=os.path.join(bc.TEXTURES, "worn_paint.png"), tex_mix=0.35, tex_scale=1.5)
```

## Notes and tips

- **Darkening:** an average texel is about 0.40 in linear space, so the overlay darkens the base by about
  `0.6 × tex_mix` (≈ 21% at mix 0.35). If a palette value must read exactly, brighten the base colour by
  `1 / (1 − 0.6·tex_mix)`. Alternatively, keep the palette value and accept slightly deeper tones.
- **Very dark palette colours** (graphite 0.03, charcoal-cloth 0.035): a multiply barely shows on near-black. Use
  the top of the range (0.5–0.6). The faint result is fine for this style, because the flat colour should dominate there.
- **Hair:** lay the hair UVs out so that V runs root to tip. Smart-UV can rotate islands, which makes the strands
  run sideways (they then look like wood grain). Unwrap hair cards and hair shells by hand, or rotate their islands.
- **Directional textures:** `brushed_metal` streaks run along U (horizontal) and `hair_strands` along V.
- **Repetition:** `worn_paint` and `skin_soft` have large features, so do not push their tex_scale up on big
  surfaces, or the repeat becomes obvious. Rotate or offset UV islands between neighbouring parts.
- The ripstop grid and carbon twill periods divide 1024 exactly, so they also tile at mip levels.

## How they were made (reproducible, see `_src/`)

1. `_src/gen_textures.py`: raw generations with the local **Krea2 Turbo** model (ComfyUI). The final prompts and
   seeds are kept in that file. The raws are in `_src/raw/`. The prompts follow the style guide: they describe the
   surface, contain no "tile" or "tileable" wording, and say "flat even lighting, no borders, no objects, no text,
   neutral grey". Rejected first tries are also kept: `skin_soft_s1` (crisp camo-like blotches), `hair_strands_s1`
   (wavy, crossing locks) and `carbon_weave_s1..s4`.
2. `_src/process_textures.py`: makes each texture seamless and normalises it to grey, low contrast, mean about 0.66.
   `comfy_gen.py --tileable` (2×2 mirror quilt) was tried first. It showed obvious kaleidoscope symmetry on the
   painterly and directional sources, and it halves the feature size. So the raws are seamed instead with:
   - a **variance-preserving offset cross-fade**: fine detail is blended so it keeps its contrast, low frequencies
     are blended linearly, and the offset is phase-matched for weaves. Used for worn_paint, brushed_metal,
     polymer_stipple, fabric_ripstop, fabric_soft, leather_soft, skin_soft and hair_strands (whose vertical blend
     band is 48% so strands fade in and out rather than kinking).
   - a **minimum-error boundary cut** (image-quilting) mode, kept for regular weaves.
   - Other steps: low-frequency flattening (removes vignetting), soft clipping of outliers, a procedural ripstop grid
     for fabric_ripstop, and a slight blur and warm tint for skin.
3. `_src/make_carbon.py`: **carbon_weave is procedural.** It is an exact 2×2 twill with rounded, gap-lined tows. The
   fibre streaks inside the tows come from the AI-made `brushed_metal.png`. All four Krea2 carbon generations drifted
   or broke their pattern, which leaves visible faults on such a strictly regular weave.
4. `_src/test_render.py`: Blender check. It puts every texture on a palette colour at the values in the table above
   and writes `_src/preview/material_test_front.png` and `material_test_closeups.png`. `_src/preview/_contact_sheet.png`
   shows all nine textures.

To rebuild, run `python process_textures.py` (and `python make_carbon.py` after `brushed_metal.png`, then
`python process_textures.py carbon_weave`). This needs only the system Python with PIL and numpy.
