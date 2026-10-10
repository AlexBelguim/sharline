"""Bake Kestrel's painted cloth / gear finish into portable PBR maps.

Existing Krea2 material art supplies all detail. Broad worn-paint marks are
reinterpreted as intrinsic dye / coating variation, never directional light.
Hair and face maps belong to their own bakers and are deliberately untouched.
"""
from pathlib import Path
import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent / 'textures'
ROOT = Path(__file__).resolve().parents[4]
SIZE = 1024

# Linear base palette; roughness separates matte ripstop, satin navy technical
# cloth, woven webbing, soft leather and the lightly polished bone coating.
# source, tint, roughness, micro relief, brush colour, brush roughness
SURFACES = {
    'jacket': ('fabric_ripstop', (.035,.037,.045), .72, .040, .125, .025),
    'jacketLight': ('fabric_ripstop', (.045,.047,.056), .71, .040, .110, .025),
    'suit': ('fabric_soft', (.017,.023,.055), .60, .025, .095, .022),
    'pants': ('fabric_ripstop', (.028,.030,.036), .77, .045, .115, .025),
    'pantsLight': ('fabric_ripstop', (.038,.040,.049), .75, .045, .100, .025),
    'web': ('fabric_ripstop', (.018,.020,.027), .80, .045, .065, .020),
    'webLight': ('fabric_ripstop', (.027,.030,.038), .78, .045, .065, .020),
    'graph': ('leather_soft', (.025,.027,.034), .51, .030, .085, .040),
    'bone': ('worn_paint', (.55,.52,.46), .54, .012, .075, .045),
    'boneLight': ('worn_paint', (.66,.62,.53), .52, .012, .065, .040),
    'boneShade': ('worn_paint', (.36,.33,.28), .58, .012, .075, .045),
}


def srgb(x):
    return np.where(x <= .0031308, x*12.92,
                    1.055*np.maximum(x,0)**(1/2.4)-.055)


def blur(field, radius):
    """Seamless float blur: preserve weak painted marks without quantization."""
    fy = np.fft.fftfreq(field.shape[0])[:,None]
    fx = np.fft.rfftfreq(field.shape[1])[None,:]
    kernel = np.exp(-2*np.pi**2*radius**2*(fx*fx+fy*fy))
    return np.fft.irfft2(np.fft.rfft2(field)*kernel,
                        s=field.shape).astype(np.float32)


def centered(field):
    field = field-field.mean()
    return np.clip(field/(field.std()+1e-8), -2.0, 2.0)


def source_fields(source):
    im = Image.open(ROOT/'art/textures'/f'{source}.png').convert('RGB')
    if im.size != (SIZE,SIZE):
        im = im.resize((SIZE,SIZE), Image.Resampling.LANCZOS)
    rgb = np.asarray(im,dtype=np.float32)/255.
    gray = rgb.mean(2)
    # No raw source grain enters the albedo. Its softened grain only supplies
    # tiny relief and a nearly invisible close-range material variation.
    body = centered(blur(gray,24))
    grain = centered(blur(gray,1.8)-blur(gray,12))
    return body, grain


def save_rgb(path, field):
    Image.fromarray(np.uint8(np.clip(field,0,1)*255+.5)).save(path)


def main():
    OUT.mkdir(exist_ok=True)
    fields = {source: source_fields(source) for source in
              {desc[0] for desc in SURFACES.values()}}
    # Preserve the broad brush boundaries rather than reproducing paint grain.
    paint = np.asarray(Image.open(ROOT/'art/textures/worn_paint.png')
                       .convert('L').resize((SIZE,SIZE)),dtype=np.float32)/255.
    brush = centered(blur(paint,7))
    brush_soft = centered(blur(paint,38))
    brush = centered(.78*brush+.22*brush_soft)
    for name,(source,tint,rough,relief,colour,rough_breakup) in SURFACES.items():
        body, grain = fields[source]
        polymer = source == 'worn_paint'
        # Measured broad dye variation carries the finish at full-body range.
        # Ripstop and leather remain primary material sources; the existing
        # painted source adds a small brush rhythm shared across the costume.
        variation = np.clip(colour*brush+.025*body+.003*grain,-.26,.26)
        albedo = np.array(tint,dtype=np.float32)[None,None,:]*(1+variation[:,:,None])
        # A little cool/warm pigment variation enriches graphite without
        # changing the average STYLE_GUIDE base colour or implying a key light.
        chroma = .008 if polymer else .022
        hue = np.stack((-brush*chroma, -brush*chroma*.15, brush*chroma),2)
        albedo *= 1+hue
        albedo *= np.array(tint)[None,None,:]/albedo.mean(axis=(0,1),keepdims=True)
        save_rgb(OUT/f'{name}.png', srgb(albedo))

        height = grain*relief
        if polymer:
            height += brush*.025
        # OpenGL: positive green points along +UV V. Image rows grow downward.
        dhx = (np.roll(height,-1,1)-np.roll(height,1,1))*.5
        dhy = (np.roll(height,1,0)-np.roll(height,-1,0))*.5
        normal = np.stack((-dhx,-dhy,np.ones_like(height)),2)
        normal /= np.linalg.norm(normal,axis=2,keepdims=True)
        save_rgb(OUT/f'{name}_normal.png',normal*.5+.5)

        orm = np.ones((SIZE,SIZE,3),dtype=np.float32)
        # Only tiny material pores contribute AO; broad paint carries no shadow.
        orm[:,:,0] = 1-np.maximum(0,-grain)*(.002 if polymer else .004)
        orm[:,:,1] = np.clip(rough-brush*rough_breakup+grain*.004, .42, .86)
        orm[:,:,2] = 0
        save_rgb(OUT/f'{name}_orm.png',orm)
        print(f'{name}: {source}, linear tint {tint}, roughness {rough:.2f}')
    (OUT/'README.md').write_text(
        'Kestrel garment and gear maps: 1024 px RGB PNG.\n'
        'Albedo is sRGB; OpenGL tangent normals and ORM are linear Non-Color.\n'
        'ORM channels: R ambient occlusion, G roughness, B metalness (zero).\n'
        'Sources: existing Krea2 art/textures/fabric_ripstop, fabric_soft, '
        'leather_soft and worn_paint. No generated noise or new texture model art.\n'
        'Broad painted marks are intrinsic dye/coating variation with a '
        'preserved STYLE_GUIDE mean palette, without baked directional lighting.\n'
        'Matte ripstop/webbing, satin navy underlayer, soft leather and bone '
        'polymer have separate roughness responses; micro relief stays subtle.\n'
        'Bake with ../make_surface_maps.py. Standard maps embed in the GLB.\n'
        'This baker deliberately leaves all hair_* and rain_face* maps untouched.\n')


if __name__ == '__main__':
    main()
