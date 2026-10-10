"""Keep generated painted region layout, reuse existing Krea2 surface detail.

Only intrinsic colour and geometry-normal information are retained. Source
metalness/roughness are replaced with calm cloth/lining/hardware responses.
"""
from pathlib import Path
import numpy as np
from PIL import Image,ImageFilter
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent/'textures'
SOURCE=Path(__file__).parent/'input/models/budget_tex'
def linear(a):return np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)
def srgb(a):return np.where(a<=.0031308,a*12.92,1.055*np.maximum(a,0)**(1/2.4)-.055)
def smooth(a,b,x):
 t=np.clip((x-a)/(b-a),0,1);return t*t*(3-2*t)
def main():
 OUT.mkdir(exist_ok=True);size=2048
 im=Image.open(SOURCE/'duffel_budget_basecolor.png').convert('RGB').filter(ImageFilter.GaussianBlur(.65))
 raw=np.asarray(im,dtype=np.float32)/255.;lin=linear(raw)
 # Preserve the good painted colour layout; compress large intensity swings
 # rather than turning every texel/triangle into one flat classified colour.
 v=raw.max(2);sat=(v-raw.min(2))/np.maximum(v,.001)
 canvas=smooth(.28,.52,sat)
 detail=Image.open(ROOT/'art/textures/fabric_ripstop.png').convert('L').resize((size,size)).filter(ImageFilter.GaussianBlur(1.5))
 gray=np.asarray(detail,dtype=np.float32)/255.;variation=gray-gray.mean()
 variation/=gray.std()+1e-6;variation=np.clip(variation,-2,2)*.022
 col=lin*(1+variation[:,:,None])
 # No source shine or metallic cloth; the region masks affect roughness only.
 light_neutral=(1-smooth(.15,.30,sat))*smooth(.34,.55,v)
 rough=.79-.34*light_neutral
 metal=.58*light_neutral*(1-smooth(.72,.92,v))
 ao=np.ones_like(v)
 Image.fromarray(np.uint8(np.clip(srgb(col),0,1)*255+.5)).save(OUT/'duffel_albedo.png')
 orm=np.stack((ao,rough,metal),2)
 Image.fromarray(np.uint8(np.clip(orm,0,1)*255+.5)).save(OUT/'duffel_orm.png')
 # Reuse the selected-to-active geometry normal bake, with subdued shared
 # fabric detail. This preserves broad folds after the 99.4% triangle reduction.
 n=np.asarray(Image.open(SOURCE/'duffel_budget_normal.png').convert('RGB'),dtype=np.float32)/255.*2-1
 d=np.asarray(Image.open(ROOT/'assets/characters/kestrel/v2/textures/jacket_normal.png').convert('RGB').resize((size,size)),dtype=np.float32)/255.*2-1
 n[:,:,:2]=n[:,:,:2]*.70+d[:,:,:2]*.20*canvas[:,:,None]
 n[:,:,2]=np.maximum(.20,n[:,:,2]);n/=np.linalg.norm(n,axis=2,keepdims=True)
 Image.fromarray(np.uint8(np.clip(n*.5+.5,0,1)*255+.5)).save(OUT/'duffel_normal.png')
if __name__=='__main__':main()
