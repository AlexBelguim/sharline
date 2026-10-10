"""Calm painted PBR maps using the supplied rebake layout and shared Krea2 cloth.

No triangle-level colour classification: source UV colour layout remains an atlas.
Run with the workspace Python; build_armchair.py invokes this automatically.
"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).parent/'textures'
SOURCE=Path(__file__).parent/'input/budget_tex'

def linear(a):return np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)
def srgb(a):return np.where(a<=.0031308,a*12.92,1.055*np.maximum(a,0)**(1/2.4)-.055)
def save(name,a):Image.fromarray(np.uint8(np.clip(a,0,1)*255+.5)).save(OUT/name)

def normalized_blur(a,mask,radius):
    """Do not bleed the atlas's unused black gutters into valid islands."""
    weight=np.asarray(Image.fromarray(np.uint8(mask*255)).filter(ImageFilter.GaussianBlur(radius)),dtype=np.float32)/255
    if a.ndim==2:a=a[:,:,None]
    channels=[]
    for c in range(a.shape[2]):
        channel=np.asarray(Image.fromarray(np.uint8(np.clip(a[:,:,c]*mask,0,1)*255+.5)).filter(ImageFilter.GaussianBlur(radius)),dtype=np.float32)/255
        channels.append(channel/np.maximum(weight,.001))
    return np.stack(channels,2)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    raw=np.asarray(Image.open(SOURCE/'b_armchair_budget_basecolor.png').convert('RGB'),dtype=np.float32)/255
    size=raw.shape[0];valid=(raw.max(2)>.015).astype(np.float32)
    # Quiet broad source paint layout, with its channel/seam locations retained.
    # Source dark intensity is remapped to the warm showhome terracotta palette.
    clean=normalized_blur(raw,valid,2.0)
    lum=clean@np.array([.2126,.7152,.0722],np.float32)
    median=float(np.median(lum[valid>.5]))
    broad=np.clip((np.maximum(lum,.012)/median)**.24,.72,1.14)
    cloth=np.asarray(Image.open(ROOT/'art/textures/fabric_soft.png').convert('L').resize((size,size)),dtype=np.float32)/255
    # Subtle existing Krea2 weave. Low contrast leaves flat palette dominant.
    detail=(cloth-cloth.mean())/(cloth.std()+1e-6)
    detail=np.clip(detail,-2.2,2.2)*.012
    base=np.array([.38,.135,.075],np.float32)
    albedo=base[None,None,:]*broad[:,:,None]*(1+detail[:,:,None])
    save('armchair_albedo.png',srgb(albedo))
    # Standard packed linear occlusion/roughness/metallic; upholstery is matte.
    orm=np.ones_like(raw);orm[:,:,1]=.76+np.clip(detail,-.016,.016);orm[:,:,2]=0
    save('armchair_orm.png',orm)
    normal=np.asarray(Image.open(SOURCE/'b_armchair_budget_normal.png').convert('RGB'),dtype=np.float32)/255
    normal=normalized_blur(normal,valid,2.2)*2-1
    normal[:,:,:2]*=.20
    # Fabric weave derives from the shared raster, avoiding generated node-only detail.
    gx=(np.roll(cloth,-1,1)-np.roll(cloth,1,1))*.30
    gy=(np.roll(cloth,-1,0)-np.roll(cloth,1,0))*.30
    normal[:,:,0]-=gx;normal[:,:,1]-=gy
    normal[:,:,2]=np.maximum(normal[:,:,2],.55)
    normal/=np.maximum(np.linalg.norm(normal,axis=2,keepdims=True),1e-6)
    save('armchair_normal.png',normal*.5+.5)
    wood=np.asarray(Image.open(ROOT/'art/textures/worn_paint.png').convert('L'),dtype=np.float32)/255
    grain=np.clip((wood-wood.mean())/(wood.std()+1e-6),-2,2)*.025
    save('timber_albedo.png',srgb(np.array([.050,.027,.016])[None,None,:]*(1+grain[:,:,None])))
    torm=np.ones((*wood.shape,3),np.float32);torm[:,:,1]=.62;torm[:,:,2]=0
    save('timber_orm.png',torm)

if __name__=='__main__':main()
