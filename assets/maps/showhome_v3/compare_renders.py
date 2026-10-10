"""Non-destructive comparison/contact boards from Blender exports and supplied concepts."""
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw,ImageFont
import json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];R=HERE/'renders';REF=ROOT/'art/briefs/showhome_v3_handoff'
def font(n):return ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',n)
def fit(p,w,h):
    image=Image.open(p).convert('RGB');image.thumbnail((w,h));out=Image.new('RGB',(w,h),'#2d3438');out.paste(image,((w-image.width)//2,(h-image.height)//2));return out
def main():
    views=[('aerial.png','concept_showhome/KEY_showhome_layout.png','AERIAL · core architecture / enlarged four-home layout'),('street.png','concept_showhome/A_showhome_ground_s12.png','STREET · 1.6m eye'),('garden.png','concept_showhome/A_showhome_aerial_s11.png','GARDEN · volumes show where game foliage grows'),('interior.png','refs_ingame/good_garage_workbench_cabinets.png','INTERIOR · real furniture / openable library')]
    board=Image.new('RGB',(1920,4*650),'#ede9df');d=ImageDraw.Draw(board)
    for i,(a,b,label) in enumerate(views):
        y=i*650;d.text((20,y+10),label,font=font(25),fill='#303c36');board.paste(fit(REF/b,940,580),(10,y+50));board.paste(fit(R/a,940,580),(970,y+50))
    board.save(R/'phase1_compare.png')
    cat=json.loads((ROOT/'assets/props/catalog.json').read_text())['props'];poses=[]
    for r in cat:
        states=('closed','ajar','open') if r['category']=='containers' else ('default',)
        for s in states:
            p=R/'library'/(r['id']+'_'+s+'.png')
            if p.exists():poses.append((r['id']+' / '+s,p))
    cols=6;tw=300;th=338;sheet=Image.new('RGB',(cols*tw,((len(poses)+cols-1)//cols)*th),'#ede9df');d=ImageDraw.Draw(sheet)
    for i,(name,p) in enumerate(poses):
        x=i%cols*tw;y=i//cols*th;sheet.paste(fit(p,tw,300),(x,y));d.text((x+8,y+305),name,font=font(15),fill='#354039')
    sheet.save(R/'prop_contact_sheet.png')
    # Dedicated painted-reference close crop, not the worksite expansion image.
    terrace=R/'houses_terrace.png'
    if terrace.exists():
        im=Image.new('RGB',(1920,650),'#ede9df');im.paste(fit(terrace,1260,600),(0,40));im.paste(fit(REF/'style/painted_cladding_ref.png',630,600),(1280,40));ImageDraw.Draw(im).text((15,5),'ACTUAL TERRACE / PAINTED CLADDING REFERENCE',font=font(25),fill='#354039');im.save(R/'terrace_painted_compare.png')
    print('Comparison and prop contact boards written')
if __name__=='__main__':main()
