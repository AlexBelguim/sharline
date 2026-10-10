"""Corrected attached-home schematic, using the original concept and user sketch."""
from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def font(n):return ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',n)
def main():
    j=json.loads((HERE/'layout.json').read_text());im=Image.new('RGB',(1920,1200),'#ede9df');d=ImageDraw.Draw(im)
    d.text((24,16),'SHOWHOME V3 — FOUR HOMES / TWO ATTACHED BLOCKS',font=font(34),fill='#293632')
    d.text((24,63),'Original Showhome architecture · current-map spacing · larger separate gardens',font=font(23),fill='#54605b')
    refs=[('concept_worksite/worksite_aerial_v1_t2i_s12.png','WORKSITE EXTENSION REFERENCE',110,310),('concept_showhome/KEY_showhome_layout.png','SHOWHOME CORE REFERENCE',474,500)]
    for p,label,y,h in refs:
        ref=Image.open(ROOT/'art/briefs/showhome_v3_handoff'/p).convert('RGB');ref.thumbnail((860,h));im.paste(ref,(24,y));d.text((24,y+ref.height+8),label,font=font(22),fill='#34483b')
    ox,oy,sc=1010,1034,10
    def pt(x,y):return ox+(x-330)*sc,oy-(y-620)*sc
    def rect(r,color,label=None):
        x0,y0,x1,y1=r;d.rectangle((pt(x0,y1),pt(x1,y0)),fill=color,outline='#536052',width=2)
        if label:d.text(pt((x0+x1)/2,(y0+y1)/2),label,anchor='mm',font=font(17),fill='#26382e')
    rect([330,620,410,685],'#b8c99c')
    rect([330,690,410,718],'#d4b68b','WORKSITE · Phase 2\n2 attached + 1 detached / hedged gardens')
    rect([330,673,410,681],'#999ba0','CONTINUOUS CROSS-STREET')
    rect([330,671,410,673],'#d8d0bd');rect([330,681,410,685],'#d8d0bd')
    rect(j['central_street'],'#999ba0','CENTRAL\nDRIVE\n+ TRUCK')
    for x0,x1 in ((362,366),(374,378)):rect([x0,621,x1,664],'#d8d0bd')
    for h in j['houses']:
        x,y,_=h['centre'];west=x<370;x0,x1=(x-2.15,x+8.15) if west else (x-8.15,x+2.15)
        rect([x0,y-6.15,x1,y+6.15],'#90a879' if h['colour']=='sage' else '#c58b72',h['colour'].upper()+'\n'+('SOUTH' if h['id'].endswith('south') else 'NORTH'))
        if h.get('attached_garage',h['id'].endswith('south')):
            south=h['id'].endswith('south');rect([x-2 if west else x-8.15,y-12 if south else y+5.85,x+8.15 if west else x+2,y-5.85 if south else y+12],'#ddd3bc','GARAGE')
    for r in ([360.65,633.15,364.15,644.8],[375.85,633.15,379.35,644.8]):rect(r,'#a8c88c','FRONT\nLAWN')
    for x0,x1 in ((350.35,360.65),(379.35,389.65)):d.line((pt(x0,645),pt(x1,645)),fill='#3d4539',width=5)
    g=json.loads((HERE/'gardens.json').read_text());dims={'greenhouse':(4,5.6),'shed':(2.8,3.4),'hot_tub':(2.4,2.4),'pergola':(5,4),'raised_planter':(2.4,1.2)}
    colors={'greenhouse':'#b4d9ce','shed':'#9f8674','hot_tub':'#b6cfcb','pergola':'#c6b895','raised_planter':'#a7926f'}
    for row in g['props']:
        x,y,_=row['position'];w,h=dims[row['id']]
        if abs(row['yaw'])==90:w,h=h,w
        rect([x-w/2,y-h/2,x+w/2,y+h/2],colors[row['id']],{'greenhouse':'GH','raised_planter':'BED'}.get(row['id'],row['id'].upper()))
    for cx,lo,hi in ((339,332,350.35),(401,389.65,408)):
        for x0,x1 in ((lo,cx-1.05),(cx+1.05,hi)):d.line((pt(x0,645),pt(x1,645)),fill='#584a39',width=7)
        p=pt(cx,645);d.ellipse((p[0]-10,p[1]-10,p[0]+10,p[1]+10),fill='#efd26b',outline='#565641',width=2)
    for cx in (367.1,372.9):rect([cx-2.3,624.1,cx+2.3,629.7],'#dfd5bb','REAR\nGARAGE')
    for x in (347,393):rect([x-.6,646.8,x+.6,655.2],'#597248','FRAMED\nBUSHES')
    for a in ([330.35,621.85,331.65,671],[408.35,621.85,409.65,671],[330.35,620.55,409.65,621.85]):rect(a,'#5e754b')

    for a in ([331.65,669.7,350.35,671],[389.65,669.7,408.35,671],[346.35,632.25,350.35,633.45]):rect(a,'#5e754b')
    d.line((pt(389.65,632.85),pt(397.65,632.85)),fill='#584a39',width=7)
    rect([369,638.7,371,642.9],'#638eac','CAR')
    d.rectangle((pt(330,685),pt(410,620)),outline='#8457ac',width=4)
    d.text((24,1074),'Dark timber divider + open gate: separate private gardens',font=font(23),fill='#34483b')
    d.text((24,1120),'The house kit continues from v2; props / collision / foliage are prepared for later game integration.',font=font(22),fill='#34483b')
    d.text((1030,180),'N ↑  · World origin (330,620) · 80 × 65m',font=font(21),fill='#34483b')
    im.save(HERE/'step0_layout.png')
if __name__=='__main__':main()
