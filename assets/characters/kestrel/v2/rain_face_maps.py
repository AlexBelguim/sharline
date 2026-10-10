"""Intrinsic PBR colour atlases in Rain's native facial coordinate frame."""
from pathlib import Path
import numpy as np
from PIL import Image
OUT=Path(__file__).parent/'textures'

def smooth(a,b,x):
    t=np.clip((x-a)/(b-a),0,1);return t*t*(3-2*t)

def save(rgb,name):
    srgb=np.where(rgb<=.0031308,rgb*12.92,1.055*np.maximum(rgb,0)**(1/2.4)-.055)
    OUT.mkdir(exist_ok=True)
    Image.fromarray(np.uint8(np.clip(srgb,0,1)*255+.5)).save(OUT/name)

def main():
    size=2048
    u,v=np.meshgrid(np.linspace(0,1,size,dtype=np.float32),np.linspace(1,0,size,dtype=np.float32))
    x=(np.mod(u,.5)*2-.5)*.30;z=1.275+v*(1.623896122-1.275)
    ax=np.abs(x);front=u<.5
    skin=np.array((.62,.42,.33))*np.array((.78,.62,.52))
    rgb=np.tile(skin,(size,size,1))
    cheek=np.exp(-((ax-.062)/.030)**2-((z-1.421)/.024)**2)*front
    rgb*=1+cheek[:,:,None]*np.array((.035,-.085,-.075))
    orbit=np.exp(-((ax-.052)/.026)**2-((z-1.493)/.012)**2)*front
    rgb*=1+orbit[:,:,None]*np.array((-.14,-.21,-.22))
    # Source lip rim landmarks (Rain), independent of the old CC0 mesh.
    width=.038;fade=np.maximum(0,1-(x/width)**2)
    center=1.3855-.0025*fade
    up=(.0085+.0025*np.exp(-((ax-.012)/.007)**2))*fade**.65
    down=.0115*fade**.7
    mask=smooth(center-down,center-down+.0017,z)*(1-smooth(center+up-.0015,center+up,z))*front*(ax<width)
    blend=smooth(center-.001,center+.001,z)
    upper=np.array((.235,.095,.069));lower=np.array((.31,.135,.103))
    lip=lower*(1-blend[:,:,None])+upper*blend[:,:,None]
    rgb=rgb*(1-mask[:,:,None])+lip*mask[:,:,None]
    save(rgb,'rain_face_basecolor.png')
    size=1024
    x,z=np.meshgrid(np.linspace(-.04,.04,size,dtype=np.float32),np.linspace(.04,-.04,size,dtype=np.float32))
    r=np.sqrt(x*x+z*z);a=np.arctan2(z,x)
    rgb=np.tile(np.array((.57,.53,.47)),(size,size,1))
    mask=1-smooth(.0140,.0146,r)
    iris=np.array((.12,.052,.023))*(1+.075*np.cos(a[:,:,None]*43)+.045*np.cos(a[:,:,None]*73+r[:,:,None]*500))
    iris*=1-.63*smooth(.0120,.0140,r)[:,:,None]
    rgb=rgb*(1-mask[:,:,None])+iris*mask[:,:,None]
    pupil=1-smooth(.0053,.0057,r)
    rgb=rgb*(1-pupil[:,:,None])+np.array((.0025,.003,.004))*pupil[:,:,None]
    save(rgb,'rain_face_eye.png')

if __name__=='__main__':main()
