"""Generate the Krea2 sky and convert it to the brief's Bevy cubemap layout.

Normal Python + numpy/Pillow. --generate runs the repository Comfy helper on
8188. No text-to-image LoRA, no use of port 8199. Conversion is deterministic.
"""
from pathlib import Path
import json
import math
import subprocess
import sys
import numpy as np
from PIL import Image,ImageFilter,ImageOps,ImageDraw

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
SEED=260084
PROMPT=('Full spherical equirectangular panorama of only a calm painted late afternoon sky, horizontal 2 to 1 panorama. '
        'Warm pale cream peach horizon gently fading to a soft muted blue zenith. A few broad soft cumulus clouds, '
        'simple hand-painted shapes and broad very subtle brush patches, cream sun-facing edges and lavender shadow undersides, '
        'stylized game concept painting, clean low contrast colour, balanced even sky, no photographic grain. '
        'No sun disc, no land, no buildings, no birds, no aircraft, no objects, no letters, no words. '
        'Lower hemisphere is plain blue grey ground haze. The left and right ends continue the same horizon.')


def generate():
    raw=HERE/'_src/krea_sky_raw.png'
    raw.parent.mkdir(parents=True,exist_ok=True)
    if not raw.exists():
        subprocess.run([sys.executable,str(ROOT/'tools/comfy_gen.py'),'--prompt',PROMPT,'--out',str(raw),
                        '--w','4096','--h','2048','--seed',str(SEED),'--steps','8'],check=True)
    return raw


def panorama(raw):
    source=Image.open(raw).convert('RGB')
    original=source.size
    a=np.asarray(source.resize((4096,2048),Image.Resampling.LANCZOS),np.float32)/255
    h,w=a.shape[:2]
    # Feather both ends into the same averaged edge; horizontal periodicity only.
    band=192
    seam=(a[:,:band]+a[:,-band:][:,::-1])*.5
    f=np.linspace(1,0,band,dtype=np.float32)[None,:,None]
    a[:,:band]=a[:,:band]*(1-f)+seam*f
    a[:,-band:]=a[:,-band:]*(1-f[:,::-1])+seam[:,::-1]*f[:,::-1]
    edge=(a[:,0]+a[:,-1])*.5
    a[:,0]=edge;a[:,-1]=edge
    # Smooth polar singularity; lower hemisphere is the exact fog colour.
    fog=np.array([.66,.76,.86],np.float32)
    horizon=h//2
    for row in range(horizon-64,horizon):
        t=(row-(horizon-64))/64
        t=t*t*(3-2*t)
        a[row]=a[row]*(1-t)+fog*t
    a[horizon:]=fog
    cap=a[0].mean(axis=0)
    for row in range(64):
        t=row/64;t=t*t*(3-2*t)
        a[row]=cap*(1-t)+a[row]*t
    out=Image.fromarray(np.uint8(np.clip(a,0,1)*255+.5),'RGB')
    out.save(HERE/'sky_equirect.png')
    return out,original


def sample(a,u,v):
    h,w=a.shape[:2]
    xx=(u*w-.5)%w; yy=np.clip(v*h-.5,0,h-1)
    x0=np.floor(xx).astype(np.int32);y0=np.floor(yy).astype(np.int32)
    fx=(xx-x0)[...,None];fy=(yy-y0)[...,None]
    x1=(x0+1)%w;y1=np.minimum(y0+1,h-1)
    return(a[y0,x0]*(1-fx)*(1-fy)+a[y0,x1]*fx*(1-fy)+a[y1,x0]*(1-fx)*fy+a[y1,x1]*fx*fy)


def cube(a,size):
    t=(np.arange(size,dtype=np.float32)+.5)/size*2-1
    u,v=np.meshgrid(t,t)
    one=np.ones_like(u)
    vectors=[(one,-v,-u),(-one,-v,u),(u,one,v),(u,-one,-v),(u,-v,one),(-u,-v,-one)]
    faces=[]
    for vec in vectors:
        x,y,z=vec
        length=np.sqrt(x*x+y*y+z*z)
        longitude=np.arctan2(x,-z)
        latitude=np.arcsin(y/length)
        colour=sample(a,.5+longitude/(2*np.pi),.5-latitude/np.pi)
        faces.append(Image.fromarray(np.uint8(np.clip(colour,0,1)*255+.5),'RGB'))
    return faces


def main():
    raw=generate() if '--generate' in sys.argv else HERE/'_src/krea_sky_raw.png'
    sky,original=panorama(raw)
    faces=cube(np.asarray(sky,np.float32)/255,1024)
    labels=['px','nx','py','ny','pz','nz']
    strip=Image.new('RGB',(1024,6144))
    for i,(name,face)in enumerate(zip(labels,faces)):
        face.save(HERE/f'sky_cube_{name}.png');strip.paste(face,(0,i*1024))
    strip.save(HERE/'sky_cube_strip.png')
    # Blur periodic panorama before cubemap sampling, so cube edges remain consistent.
    padded=Image.new('RGB',(sky.width*3,sky.height))
    for i in range(3):padded.paste(sky,(sky.width*i,0))
    blurred=padded.filter(ImageFilter.GaussianBlur(80)).crop((sky.width,0,sky.width*2,sky.height))
    irradiance=cube(np.asarray(blurred,np.float32)/255,256)
    small=Image.new('RGB',(256,1536))
    for i,face in enumerate(irradiance):small.paste(face,(0,i*256))
    small.save(HERE/'sky_cube_irradiance_strip.png')
    preview=Image.new('RGB',(1536,860),(239,234,221));draw=ImageDraw.Draw(preview)
    preview.paste(sky.resize((1024,512)),(0,24))
    concept=Image.open(ROOT/'design/maps/tdm/concepts/_candidates/A_showhome_ground_s12.png').convert('RGB').crop((420,0,1070,390))
    concept=ImageOps.contain(concept,(500,512));preview.paste(concept,(1034,24))
    draw.text((12,5),'Krea2 panorama / concept sky crop',fill=(50,50,50))
    for i,face in enumerate(faces):
        preview.paste(face.resize((250,250)),(i*256,588));draw.text((i*256+8,564),labels[i],fill=(50,50,50))
    preview.save(HERE/'sky_compare.png')
    notes=f'''# Showhome painted sky\n\nModel: krea2_turbo_fp8_scaled.safetensors via tools/comfy_gen.py.\nSeed: {SEED}; steps: 8; no LoRA for text-to-image; port 8188.\nNative source: {original[0]} x {original[1]}; final panorama: 4096 x 2048.\n\nPrompt:\n\n{PROMPT}\n\nProcessing: 192 px periodic end blend, softened zenith pole, lower hemisphere exact fog sRGB (.66,.76,.86). No sun disc.\n\nFace order: +X,-X,+Y,-Y,+Z,-Z; glTF/Bevy Y up. +X=east,-X=west,+Y=zenith,-Y=nadir,+Z=south,-Z=north. Each face uses cube sampling vectors documented in build_sky.py. Panorama centre U=.5 is north; longitude increases toward east.\n\nSkybox strip: 1024 x 6144 RGB PNG; reinterpret as a six-layer cube, not a 2D stretched texture. Irradiance strip: 256 x 1536, panorama-blurred before cube sampling. Suggested Skybox brightness 700 cd/m2 initially; calibrate to the game exposure.\n'''
    (HERE/'PROMPT.md').write_text(notes,encoding='utf8')
    (HERE/'validation.json').write_text(json.dumps(dict(native_size=original,panorama=[4096,2048],faces=[1024,1024],
        strip=[1024,6144],irradiance_strip=[256,1536],face_order=labels,horizontal_edge_error=0,
        lower_hemisphere_srgb=[.66,.76,.86],seed=SEED),indent=2)+'\n',encoding='utf8')
    print('SKY COMPLETE',HERE)


if __name__=='__main__':main()
