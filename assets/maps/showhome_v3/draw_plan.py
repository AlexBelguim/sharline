"""Step-0 sketch beside and over the concept; no generated image models."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
REF=ROOT/'art/briefs/showhome_v3_handoff/concept_showhome/KEY_showhome_layout.png'
def font(n):
    return ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',n)
def main():
    j=json.loads((HERE/'layout.json').read_text())
    im=Image.new('RGB',(1920,1080),'#e9e5da');d=ImageDraw.Draw(im)
    ref=Image.open(REF).convert('RGB').resize((960,540));im.paste(ref,(0,105))
    d.text((25,22),'SHOWHOME V3  /  PHASE 1',font=font(35),fill='#242b2a')
    d.text((25,72),'FOUR houses / two per side; world origin (330, 620)',font=font(23),fill='#485354')
    # Callouts are over the matching parts of the original aerial.
    labels=[((130,350),'SAGE / south-facing'),((640,380),'CLAY / south-facing'),((300,155),'REAR GARDENS + CARPORTS'),((400,430),'CENTRAL DRIVE + TRUCK'),((40,600),'OPEN THROUGH-STREET'),((475,110),'WORKSITE BEHIND PLOTS')]
    for (x,y),text in labels:
        b=d.textbbox((x,y),text,font=font(17));d.rounded_rectangle((b[0]-7,b[1]-5,b[2]+7,b[3]+5),5,fill='#f1eddb');d.text((x,y),text,font=font(17),fill='#273238')
    ox,oy,sc=1010,790,10
    def pt(x,y):return (ox+(x-330)*sc,oy-(y-620)*sc)
    def rect(a,color,label=None):
        x0,y0,x1,y1=a;d.rectangle((pt(x0,y1),pt(x1,y0)),fill=color,outline='#454d46',width=2)
        if label:
            p=pt((x0+x1)/2,(y0+y1)/2);d.text(p,label,font=font(16),fill='#26302e',anchor='mm')
    rect([330,620,410,680],'#b7c99c')
    rect([330,608,410,616],'#93979d','FRONT STREET — continues 40m each way')
    rect([330,616,410,620],'#d9d0b9')
    rect(j['central_street'],'#96989b','DRIVE')
    for x0,x1 in ((362,366),(374,378)):rect([x0,620,x1,680],'#d8ceb9')
    for h in j['houses']:
        x,y,_=h['centre'];rect([x-8.15,y-6.15,x+8.15,y+6.15],'#92a57c' if h['colour']=='sage' else '#c5876c',h['id'].upper().replace('_','\n'))
    for x in (339,401):
        rect([x-4,671,x+4,677],'#ded6c3','CARPORT')
        for y in (633,656):rect([x-2,y-3,x+2,y+3],'#c3dbd0','GH')
        for y in (643,666):rect([x-2,y-2,x+1,y+1],'#9c8170','SHED')
        rect([x-3,663,x+3,668],'#c9c29f','PERGOLA')
    rect([368.75,635,371.25,646],'#f7edda','TRUCK')
    for a in ([331,622,332,658],[331,662,332,678],[408,622,409,658],[408,662,409,678]):rect(a,'#65794f')
    d.rectangle((pt(330,680),pt(410,620)),outline='#784ead',width=5)
    for name,p in j['gates'].items():
        p=pt(*p);d.ellipse((p[0]-7,p[1]-7,p[0]+7,p[1]+7),fill='#f1dc73',outline='#393c32',width=2)
    d.text((1040,110),'N  ↑   worksite / back road / Shells',font=font(24),fill='#343c39')
    d.text((1010,932),'80 × 60 m  /  mirrored about world x370',font=font(23),fill='#343c39')
    d.text((25,700),'KEEP: painted house kit, real roof courses, deep panel seams',font=font(22),fill='#343c39')
    d.text((25,748),'CHANGE: two pairs, open outer gardens, open fences',font=font(22),fill='#343c39')
    d.text((25,796),'PREPARE: openable props, real wall thickness, phys + COL + FOL',font=font(22),fill='#343c39')
    d.text((25,875),'Purple: editable TDM clips    Yellow: extraction entrances',font=font(22),fill='#784ead')
    d.text((25,974),'Phase 2 reserved: site office west / material yard east / cranes north',font=font(23),fill='#343c39')
    im.save(HERE/'step0_layout.png')
if __name__=='__main__':main()
