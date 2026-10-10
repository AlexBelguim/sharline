"""Generate the new v2 broad painted colour sources through the repository Krea2 helper.

Run with normal Python; needs the existing ComfyUI service on port 8188.
The reference-edit workflow uses its required identity adapter; no text-to-image LoRAs are used.
"""
from pathlib import Path
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
REF = ROOT / 'art/briefs/refs/painted_cladding_ref.png'
PROMPTS = {
    'painted_panels': (260081, 'Use the reference only for its soft hand-painted brush style. Make a uniform flat close-up of terracotta fibre cement colour, with broad gentle vertical brush strokes and large slightly angular painted patches. Calm low contrast soft mottling, no grooves, no joints, no shadows, no directional light, no dirt, no grain, no photographic detail, no objects, no borders. The whole image is one matte painted surface.'),
    'painted_ground': (260082, 'Use the reference brush language for a uniform flat close-up of muted warm grey beige painted concrete colour. Broad soft hand-painted patches with simple angular edges, subtle low contrast painterly colour variation, evenly lit, no slabs, no seams, no grooves, no shadows, no perspective, no objects, no dirt, no grain, no photographic detail, no borders. The whole image is one matte painted surface.'),
    'painted_timber': (260083, 'Use the reference brush language for a uniform flat close-up of muted warm brown timber colour. Broad soft vertical hand-painted strokes and gentle angular painted patches. Very low contrast, evenly lit, no boards, no seams, no knots, no grooves, no shadows, no perspective, no objects, no dirt, no grain, no photographic detail, no borders. The whole image is one matte painted surface.'),
}

def main():
    raw = HERE / 'raw'
    raw.mkdir(parents=True, exist_ok=True)
    records = []
    for name, (seed, prompt) in PROMPTS.items():
        out = raw / f'{name}.png'
        if not out.exists():
            subprocess.run([sys.executable, str(ROOT / 'tools/comfy_gen.py'), '--prompt', prompt,
                            '--out', str(out), '--seed', str(seed), '--w', '1024', '--h', '1024',
                            '--steps', '10', '--ref', str(REF), '--ref-boost', '1.2', '--tileable'], check=True)
        records.append(dict(name=name, seed=seed, prompt=prompt, reference=str(REF.relative_to(ROOT)),
                            workflow='Krea2 reference edit via tools/comfy_gen.py; --tileable mirror quilt',
                            model='krea2_turbo_fp8_scaled.safetensors', reference_adapter='krea2_identity_edit_v1_2',
                            loras_for_text_to_image=[], output=f'raw/{name}.png'))
    (HERE / 'KREA_PROVENANCE.json').write_text(json.dumps(records, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
