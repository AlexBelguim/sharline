"""Continuous intrinsic face paint in the same native frame as the CC0 topology."""
from pathlib import Path
import numpy as np
from PIL import Image,ImageFilter
OUT=Path(__file__).resolve().parent/'textures'
ROOT=Path(__file__).resolve().parents[4]

def smooth(a,b,x):
 t=np.clip((x-a)/(b-a),0,1);return t*t*(3-2*t)

def main():
 size=2048
 u,v=np.meshgrid(np.linspace(0,1,size,dtype=np.float32),np.linspace(1,0,size,dtype=np.float32))
 x=(np.mod(u,.5)*2-.5)*.28;z=1.295+v*(1.613162-1.295)
 ax=np.abs(x);front=u<.5
 base=np.array((.62,.42,.33))*np.array((.84,.62,.48))
 rgb=np.tile(base,(size,size,1))
 cheek=np.exp(-((ax-.058)/.039)**2-((z-1.413)/.025)**2)*front
 rgb*=1+cheek[:,:,None]*np.array((.025,-.08,-.08))
 lids=np.exp(-((ax-.047)/.029)**2-((z-1.481)/.013)**2)*front
 rgb*=1+lids[:,:,None]*np.array((-.12,-.23,-.24))
 width=.041;fade=np.maximum(0,1-(x/width)**2)
 center=1.377+.0022*fade
 upper=(.012+.004*np.exp(-((ax-.011)/.008)**2))*fade**.7
 lower=.018*fade**.65
 mask=smooth(center-lower,center-lower+.0025,z)*(1-smooth(center+upper-.0020,center+upper,z))*front*(ax<width)
 dark=np.array((.62,.42,.33))*np.array((.36,.14,.105))
 light=np.array((.62,.42,.33))*np.array((.43,.18,.13))
 blend=smooth(center-.0015,center+.0015,z)
 lip=light[None,None,:]*(1-blend[:,:,None])+dark[None,None,:]*blend[:,:,None]
 rgb=rgb*(1-mask[:,:,None])+lip*mask[:,:,None]
 # Broad Krea2 painted mottling only; all seams and facial borders remain exact.
 source=Image.open(ROOT/'art/textures/skin_soft.png').convert('L').resize((size,size)).filter(ImageFilter.GaussianBlur(24))
 detail=np.asarray(source,dtype=np.float32)/255.;detail-=detail.mean();detail/=detail.std()+1e-8
 rgb*=1+np.clip(detail,-2,2)[:,:,None]*.012
 srgb=np.where(rgb<=.0031308,rgb*12.92,1.055*rgb**(1/2.4)-.055)
 OUT.mkdir(exist_ok=True)
 Image.fromarray(np.uint8(np.clip(srgb,0,1)*255+.5)).save(OUT/'face_paint.png')
 # Projected painted iris remains circular while the sphere sits inside the lid.
 size=1024
 u,v=np.meshgrid(np.linspace(-.025,.025,size,dtype=np.float32),np.linspace(.025,-.025,size,dtype=np.float32))
 radius=np.sqrt(u*u+v*v);angle=np.arctan2(v,u)
 sclera=np.array((.55,.48,.40));brown=np.array((.105,.045,.018));black=np.array((.002,.003,.004))
 eye=np.tile(sclera,(size,size,1))
 irismask=1-smooth(.0064,.0068,radius)
 variation=1+.08*np.cos(angle*39)+.055*np.cos(angle*71+radius*800)
 iris=brown[None,None,:]*variation[:,:,None]
 limb=smooth(.0058,.0064,radius)*(1-smooth(.0065,.0068,radius))
 iris*=1-limb[:,:,None]*.65
 eye=eye*(1-irismask[:,:,None])+iris*irismask[:,:,None]
 pupil=1-smooth(.0025,.0028,radius)
 eye=eye*(1-pupil[:,:,None])+black[None,None,:]*pupil[:,:,None]
 eye=np.where(eye<=.0031308,eye*12.92,1.055*eye**(1/2.4)-.055)
 Image.fromarray(np.uint8(np.clip(eye,0,1)*255+.5)).save(OUT/'eye_paint.png')

if __name__=='__main__':main()
