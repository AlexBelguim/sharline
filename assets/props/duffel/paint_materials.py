"""Tint the existing shared Krea2 details into portable PBR albedo images."""
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent/'textures'
SPECS={
 'NavyCanvas':((.026,.064,.125),'fabric_ripstop'),
 'TealCanvas':((.009,.205,.185),'fabric_ripstop'),
 'GraphiteWebbing':((.022,.026,.034),'fabric_ripstop'),
 'BoneBinding':((.55,.52,.46),'fabric_soft'),
 'Hardware':((.105,.115,.120),'brushed_metal'),
}
def main():
 OUT.mkdir(exist_ok=True)
 for name,(palette,detail)in SPECS.items():
  a=np.asarray(Image.open(ROOT/'art/textures'/f'{detail}.png').convert('RGB'),dtype=np.float32)/255.
  lin=np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)
  gray=lin.mean(2);variation=(1-.32)+.32*gray
  variation/=variation.mean()
  color=np.array(palette)[None,None,:]*variation[:,:,None]
  s=np.where(color<=.0031308,color*12.92,1.055*np.maximum(color,0)**(1/2.4)-.055)
  Image.fromarray(np.uint8(np.clip(s,0,1)*255+.5)).save(OUT/f'duffel_{name}.png')
if __name__=='__main__':main()
