"""Every backdrop view is paired with the matching concept (or nearest intended view)."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
OUT=HERE/'renders'
C=ROOT/'design/maps/tdm/concepts/_candidates'
try:FONT=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',21)
except OSError:FONT=ImageFont.load_default()


def main():
    comparisons=[]
    for path in sorted(OUT.glob('*.png')):
        name=path.stem
        if name.endswith('_compare')or name=='contact_sheet':continue
        aerial='aerial'in name or 'jetpack'in name
        concept=C/('A_showhome_aerial_s12.png'if aerial else'A_showhome_ground_s12.png')
        reference=Image.open(concept).convert('RGB')
        raw=Image.open(path).convert('RGB')
        pair=Image.new('RGB',(1680,514),(239,234,221));d=ImageDraw.Draw(pair)
        pair.paste(ImageOps.contain(reference,(824,464)),(8,42))
        pair.paste(ImageOps.contain(raw,(824,464)),(848,42))
        d.text((10,10),'Concept: '+concept.name,fill=(50,50,50),font=FONT)
        d.text((850,10),'Exported scene: '+name.replace('_',' '),fill=(50,50,50),font=FONT)
        dest=OUT/(name+'_compare.png');pair.save(dest);comparisons.append(dest)
    sheet=Image.new('RGB',(1680,276*((len(comparisons)+1)//2)),(239,234,221))
    for i,path in enumerate(comparisons):
        sheet.paste(ImageOps.contain(Image.open(path),(840,276)),((i%2)*840,(i//2)*276))
    sheet.save(OUT/'contact_sheet.png')
    print('BACKDROP COMPARISONS',len(comparisons))


if __name__=='__main__':main()
