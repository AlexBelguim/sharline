"""Make a labeled 1:1 reference / actual model plate for art review."""
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw, ImageFont

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
W=2048;H=2392
canvas=Image.new('RGB',(W,H),(222,219,213))
draw=ImageDraw.Draw(canvas)
font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',28)
small=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',22)
def place(path,box,label,crop=None):
    x,y,w,h=box
    im=Image.open(path).convert('RGB')
    if crop:im=im.crop(crop)
    im=ImageOps.contain(im,(w,h-50),Image.Resampling.LANCZOS)
    canvas.paste(im,(x+(w-im.width)//2,y+(h-50-im.height)//2))
    draw.text((x+24,y+h-42),label,fill=(30,32,38),font=font)
place(ROOT/'art/concepts/kestrel/v06.png',(0,0,1024,1074),'v06 master: face, hair, translucent LEFT lens')
place(OUT/'renders/face_three_quarter.png',(1024,0,1024,1074),'Actual authored 3D: current face / hair / lens',(40,145,960,1000))
place(ROOT/'art/concepts/kestrel/ref_sheet/front_apose.png',(0,1074,1024,1280),'A-pose reference: silhouette / light outfit')
place(OUT/'renders/kestrel_three_quarter.png',(1024,1074,1024,1280),'Actual authored 3D: cropped jacket / cargo cloth',(85,85,915,1035))
draw.text((24,2359),'Direction log applies: no tier pips or heavy armor; low twin jets; shared UE5 rig.',fill=(50,51,55),font=small)
canvas.save(OUT/'renders/reference_model_comparison.png')
print(OUT/'renders/reference_model_comparison.png')
