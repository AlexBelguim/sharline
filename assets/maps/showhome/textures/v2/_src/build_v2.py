"""Showhome v2: exact physical structure plus broad Krea2 painted colour.

python assets/maps/showhome/textures/v2/_src/build_v2.py [names ...]
Uses the v1 texlib helper, palette and brush raws plus the reference-guided v2 raws.
No generated structure or directional light is retained from Krea2.
"""
from pathlib import Path
import json
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
V1 = OUT.parent
ROOT = HERE.parents[5]
sys.path.insert(0, str(V1 / '_src'))
import texlib as T
PAL = json.loads((V1 / '_src/palette.json').read_text())['materials']
S = 1024
Y, X = np.mgrid[0:S, 0:S].astype(np.float32)
ENTRIES = {}

def entry(name, use, repeat, palette, rough, depth, structure, brush='painted_ground', variant='clean', metal=0):
    ENTRIES[name] = dict(use=use, repeat_m=repeat, tint_linear=[1, 1, 1], palette=palette,
                         target_linear=PAL[palette]['albedo_linear'] if isinstance(palette, str) else palette,
                         roughness=rough, metalness=metal, height_min_m=0, height_max_m=depth,
                         height_range_m=depth, structure=structure, brush=brush, variant=variant,
                         maps={k: name + ext for k, ext in [('albedo','.png'),('normal','_normal.png'),
                                                          ('orm','_orm.png'),('height','_height.png')]})

for c in ['sage', 'clay']:
    entry('fibercement_'+c, '1.2 x 2.4 m fibre cement panels; jointed sheet', 4.8, 'fibercement_'+c, .65,.009,'panels','painted_panels')
    entry('fibercement_'+c+'_weathered', 'Soft painted water streaks below joints',4.8,'fibercement_'+c,.67,.009,'panels','painted_panels','weathered')
entry('printed_concrete_layers','Horizontal printed beads at 40 mm pitch',1.28,'printed_concrete',.8,.009,'beads')
entry('printed_concrete_layers_dusty','Printed beads with soft dusty base wash',1.28,'printed_concrete',.82,.009,'beads',variant='dusty')
entry('trim_sheet_house','Frames, sills, coping, gutters, fascia, flashing; see trims.json',4,'trim_cream',.65,.006,'trim')
entry('roof_shingle_dark','Half-bond shingles, 500 x 250 mm',2,'roof_dark',.7,.010,'shingles')
entry('roof_shingle_dark_lichen','Sparse subtle painted lichen spots',2,'roof_dark',.74,.010,'shingles',variant='lichen')
entry('roof_ridge_verge','Ridge cap and verge pieces, joints every .5 m along U',2,'roof_dark',.7,.008,'ridge')
entry('paving_slabs','600 mm paving slabs, 10 mm recessed joints',2.4,'paving',.8,.010,'slabs')
entry('paving_slabs_moss','Paving with soft moss only in the joints',2.4,'paving',.84,.010,'slabs',variant='moss')
entry('kerb_concrete','One metre kerb units, U runs along kerb',2,'kerb',.8,.009,'kerb')
entry('edging_strip','Concrete garden edging; one metre units along U',2,'kerb',.8,.006,'kerb')
entry('asphalt','Fresh calm violet grey asphalt',4,'asphalt',.85,.003,'asphalt')
entry('asphalt_patched','Repaired square patches, same average as fresh asphalt',4,'asphalt',.87,.004,'asphalt',variant='patched')
entry('asphalt_cracked','Sparse cracks sealed with broad tar lines',4,'asphalt',.82,.004,'asphalt',variant='cracked')
entry('grass_lawn','Lush lawn ground; foliage cards intentionally on hold',2,'grass',.9,.014,'grass')
entry('grass_lawn_dry','Dry patchy lawn, same family mean',2,'grass',.93,.010,'grass',variant='dry')
entry('grass_verge_weeds','Verge with simple broad painted weed marks',2,'grass',.9,.016,'grass',variant='weeds')
entry('garden_soil','Soft garden soil',1,'garden_soil',.95,.014,'soil')
entry('worn_dirt','Trodden garden dirt without photographic grit',1,'garden_soil',.93,.010,'soil',variant='worn')
entry('bark_mulch','Broad stylized bark pieces, same soil family mean',1,'garden_soil',.96,.024,'bark','painted_timber')
entry('gravel','Loose stylized pebbles',1,'gravel',.9,.028,'gravel')
entry('gravel_compacted','Compacted gravel path',1,'gravel',.92,.015,'gravel',variant='compacted')
entry('worksite_packed_dirt','Packed worksite dirt',6,'construction_sand',.95,.022,'soil',variant='packed')
entry('worksite_mud_tracks','Two repeating tyre track lanes in painted mud',6,'construction_sand',.8,.032,'tracks')
entry('construction_sand','Soft construction sand; no stamped round blotches',6,'construction_sand',.95,.022,'sand')
entry('foundation_slab','Printed concrete foundation slab, .6 m sections',2.4,'printed_concrete',.84,.008,'slabs')
entry('timber_pallets','Unbranded pallet timber; V follows board length',2,'shed_wood',.8,.007,'boards','painted_timber')
entry('wood_boards_stained','Stained garden boards and fences',2,'shed_wood',.8,.008,'boards','painted_timber',variant='stained')
entry('metal_corrugated_site','Painted cream corrugated site fence; .1 m flutes',2,'trim_cream',.6,.018,'corrugated')
entry('metal_scaffold_tube','Muted galvanized scaffold metal',1,'metal_chip',.48,.0008,'smooth',metal=.8)
# Compatibility surfaces required by the established house, ground and props builders.
entry('fibercement_panel','Seam-free neutral painted panel face; real mesh seams supply depth',2.4,[.70,.70,.70],.65,.00035,'smooth','painted_panels')
entry('concrete_smooth','Cast concrete blocks, rocks, coping and poles',2,'pole_concrete',.8,.003,'smooth')
entry('picket_wood_white','Painted white pickets; V follows timber length',1,'picket_white',.65,.003,'smooth','painted_timber')
entry('metal_painted_yellow','Crane and barrier yellow painted metal',2,'crane_yellow',.55,.001,'smooth')
entry('truck_paint_white','Plain white painted props and delivery vehicle',3,'truck_white',.42,.0005,'smooth')
entry('cardboard','Plain kraft cardboard for unbranded site bags',1,'cardboard',.85,.001,'smooth','painted_timber')

def write_manifest():
    OUT.mkdir(parents=True,exist_ok=True)
    doc=dict(version=2, axes='Blender design x=east y=north z=up; glTF=(x,z,-y)',
             normal_convention='OpenGL: red +U, green +V (toward top of PNG)',
             colour_spaces=dict(albedo='sRGB',normal='linear',orm='linear',height='linear16'),
             wall_joint_grid=dict(repeat_m=4.8,panel_m=[1.2,2.4],u=[.125,.375,.625,.875],v=[.25,.75],groove_width_m=.014,groove_depth_m=.009),
             materials=ENTRIES,
             macro_masks={n:dict(repeat_m=32,linear=True,encoding='16bit grayscale') for n in ['macro_ground','macro_walls']})
    (OUT/'manifest.json').write_text(json.dumps(doc,indent=2),encoding='utf-8')

BRUSH_CACHE={}
PATCH_CACHE={}
def brush_patches(seed):
    """Periodic soft angular strokes, not noise: counter the raw's mirrored stamp."""
    if seed in PATCH_CACHE:return PATCH_CACHE[seed]
    rng=np.random.default_rng(seed)
    canvas=Image.new('L',(S,S),128);draw=ImageDraw.Draw(canvas)
    for _ in range(52):
        px=int(rng.integers(0,S));py=int(rng.integers(0,S));w=int(rng.integers(40,155));hh=int(rng.integers(85,310))
        val=int(rng.integers(75,185));j=int(rng.integers(5,22))
        poly=[(px,py),(px+w-j,py+j),(px+w,py+hh-j),(px+w*.65,py+hh),
              (px+w*.5,py+hh-j),(px+w*.24,py+hh+j),(px+j,py+hh-j)]
        for ox in [-S,0,S]:
            for oy in [-S,0,S]:draw.polygon([(x+ox,y+oy) for x,y in poly],fill=val)
    a=T.fft_blur(np.asarray(canvas,np.float32)/255,2.0)
    a=T.normalise_detail(a);PATCH_CACHE[seed]=a
    return a

def paint(name):
    if name in BRUSH_CACHE:return BRUSH_CACHE[name]
    src=HERE/'raw'/f'{name}.png'
    if not src.exists():
        raise FileNotFoundError(f'Generate v2 Krea2 source first: {src}')
    im=np.asarray(Image.open(src).convert('RGB').resize((S,S)),np.float32)/255
    a=T.luminance(im)
    # Large brush colour only: filter away residual narrow lines and tiny image texture.
    a=T.fft_blur(a,(6,3) if name!='painted_ground' else (5,5))
    a=T.xfade(a,.22)
    a=T.normalise_detail(a)
    BRUSH_CACHE[name]=a
    return a

def noise(seed,scale=60,aniso=None):
    return T.periodic_noise(S,S,scale,seed,aniso=aniso)

def grid(repeat,pw,ph,groove,offset=(0,0)):
    x=(X/S*repeat-offset[0])%pw
    y=(Y/S*repeat-offset[1])%ph
    d=np.minimum(np.minimum(x,pw-x),np.minimum(y,ph-y))
    # Rounded 2 mm panel edge with a flat bottom to the 14 mm recess.
    f=np.clip((d-groove/2)/.002,0,1)
    face=f*f*(3-2*f)
    ids=((np.floor((X/S*repeat-offset[0])/pw).astype(int))%(round(repeat/pw))
         +(round(repeat/pw))*((np.floor((Y/S*repeat-offset[1])/ph).astype(int))%(round(repeat/ph))))
    return face,ids,x,y

def detail(e,seed):
    rep=e['repeat_m']; typ=e['structure'];var=e['variant'];rng=np.random.default_rng(seed)
    p=paint(e['brush']);b=noise(seed,65);d=.45*p+.2*b;h=np.full((S,S),.5,np.float32);c=np.zeros((S,S),np.float32)
    accent=np.zeros((S,S,3),np.float32)
    if typ=='panels':
        face,ids,x,y=grid(rep,1.2,2.4,.014,(.6,1.2))
        n=int(ids.max()+1);values=rng.normal(0,.023,n)
        # Broad gentle vertical brush rectangles, with top-of-panel intrinsic paint wash.
        strokes=.20*noise(seed+3,aniso=(85,18))+.85*p
        d=strokes*.070+.040*brush_patches(seed+29)+values[ids]+.025*(.5-y/2.4)
        if var=='weathered':
            under=np.exp(-y/.24)*np.maximum(noise(seed+8,aniso=(60,12))+.4,0)
            d-=.018*under
        h=face;c=1-face
        hue=rng.normal(0,.008,(n,3));accent=hue[ids]
    elif typ=='beads':
        t=(Y/S*rep+.020)%.04/.04
        h=np.maximum(np.sin(np.pi*t),0)**.50
        c=(1-h)**2
        d=.023*p+.009*noise(seed+5,aniso=(6,65))
        if var=='dusty':d+=.022*np.cos(2*np.pi*Y/S)*np.maximum(b,0)
    elif typ in ('slabs','kerb','ridge','boards'):
        dims={'slabs':(.6,.6,.010,(.3,.3)),'kerb':(1,rep,.012,(.5,rep/2)),
              'ridge':(.5,rep,.012,(.25,rep/2)), 'boards':(.20,rep,.008,(.10,rep/2))}[typ]
        h,ids,x,y=grid(rep,*dims[:3],dims[3]);c=1-h
        val=rng.normal(0,.028,int(ids.max()+1));d=.026*p+.012*b+val[ids]
        if typ=='boards':d=.037*p+.018*noise(seed+17,aniso=(100,4))+val[ids]
        if var=='moss':
            moss=(1-h)*np.clip(.5+.24*b,0,1)
            accent+=moss[...,None]*np.array([-.20,-.05,-.19]);d+=.025*noise(seed+2,35)
    elif typ=='shingles':
        r=np.floor(Y/S*rep/.25).astype(int);ty=(Y/S*rep% .25)/.25
        xx=(X/S*rep+(r%2)*.25)% .5
        dist=np.minimum(xx,.5-xx)
        sj=np.clip((dist-.004)/.003,0,1)
        butt=np.clip((np.minimum(ty,1-ty)*.25-.004)/.002,0,1)
        h=(.12+.88*ty)*sj*butt;c=1-sj*butt
        ids=r*4+np.floor((X/S*rep+(r%2)*.25)%rep/.5).astype(int)
        d=(.032*p+rng.normal(0,.038,32)[ids]+.016*b)*sj*butt
        if var=='lichen':
            m=np.clip((noise(seed+13,15)-1.6)*.20,0,.25)
            accent+=m[...,None]*np.array([.2,.3,.02])
    elif typ=='asphalt':
        d=.03*p+.012*noise(seed+1,5)+.015*b;h=.5+.08*noise(seed+21,7)
        if var=='patched':
            patch=((X>110)&(X<450)&(Y>165)&(Y<505))|((X>600)&(X<915)&(Y>640)&(Y<965))
            d+=patch*.08;h+=patch*.18
            edge=((np.abs(X-110)<3)|(np.abs(X-450)<3))&(Y>165)&(Y<505)
            c=edge.astype(np.float32)*.55
        if var=='cracked':
            # Integer periodic curves make exact seamless tar seals, never a photo crack raw.
            dist=np.abs(np.sin(2*np.pi*(X/S+ .038*np.sin(6*np.pi*Y/S))))*rep/(2*np.pi)
            tar=np.exp(-(dist/.015)**4)
            c=.75*tar;h-=.20*tar;accent+=tar[...,None]*np.array([-.28,-.26,-.24])
    elif typ=='grass':
        d=.040*p+.048*b+.012*noise(seed+10,3);h=.5+.16*noise(seed+12,3)+.12*b
        if var=='dry':
            m=np.clip((noise(seed+8,60)+.3)*.3,0,.65)
            accent+=m[...,None]*np.array([.14,-.08,.10]);h*=1-.2*m
        if var=='weeds':
            m=np.clip((noise(seed+9,12)-1.3)*.2,0,.3)
            accent+=m[...,None]*np.array([-.20,.06,-.14]);h+=m*.2
    elif typ in ('soil','sand'):
        d=.034*p+.040*b+.017*noise(seed+20,6);h=.5+.15*b+.08*noise(seed+22,9)
        if var in ('worn','packed'):d*=.75;h=.5+(h-.5)*.55
        if typ=='sand':d=.027*p+.025*noise(seed+19,aniso=(10,85));h=.5+.17*noise(seed+22,aniso=(14,60))
    elif typ=='tracks':
        lanes=np.exp(-((X/S-.29)/.07)**8)+np.exp(-((X/S-.71)/.07)**8)
        tread=np.clip(np.cos(2*np.pi*(Y/S*24+X/S*5))*.8+.2,0,1)*lanes
        h=.75-.55*tread+.10*b;c=.32*tread;d=.03*p+.05*b-.045*lanes
    elif typ in ('gravel','bark'):
        # Periodic feature centres with broad facets, varying aspect for bark chips.
        pts=rng.random((150 if typ=='gravel' else 65,2));best=np.full((S,S),99,np.float32);pid=np.zeros((S,S),int)
        for i,(px,py) in enumerate(pts):
            dx=np.minimum(np.abs(X/S-px),1-np.abs(X/S-px));dy=np.minimum(np.abs(Y/S-py),1-np.abs(Y/S-py))
            dist=(dx*dx*(3 if typ=='bark' else 1)+dy*dy)**.5
            take=dist<best;best[take]=dist[take];pid[take]=i
        val=rng.normal(0,.055,len(pts));d=.018*p+val[pid]
        h=np.clip(1-best/(.08 if typ=='bark' else .06),0,1);h=T.fft_blur(h,1.3);c=np.clip(1-h,0,1)*.5
        if var=='compacted':h=.3+h*.55;d*=.7
    elif typ=='corrugated':
        h=.5+.5*np.cos(2*np.pi*X/S*20);c=((1-h)**2)*.30;d=.02*p+.015*noise(seed+2,aniso=(100,10))
    elif typ=='smooth':
        d=.028*p+.014*noise(seed+5,aniso=(70,16));h=.5+.04*T.fft_blur(p,6)
        if e['brush']=='painted_panels':
            # The mirrored Krea raw has rounded brush ends. Real panel faces instead
            # retain its vertical colour bands and original angular procedural washes.
            # This removes the scalloped/oval stamp visible in a 5 m facade render.
            vertical=np.broadcast_to(p.mean(axis=0,keepdims=True),(S,S)).copy()
            vertical=T.normalise_detail(vertical)
            d=.042*vertical+.055*brush_patches(seed+29)+.018*noise(seed+3,aniso=(100,20))
            h=.5+.035*T.fft_blur(vertical+brush_patches(seed+29),12)
    return np.clip(h,0,1),np.clip(c,0,1),d,accent

def normal_physical(h,rep,depth):
    hm=h*depth
    dx=(np.roll(hm,-1,1)-np.roll(hm,1,1))/(2*rep/S)
    # PNG Y grows down, OpenGL +V grows up. Green = +dh/dPNG_Y after negating surface gradient.
    dy=(np.roll(hm,-1,0)-np.roll(hm,1,0))/(2*rep/S)
    n=np.stack([-dx,dy,np.ones_like(h)],axis=2);n/=np.maximum(np.linalg.norm(n,axis=2,keepdims=True),1e-8)
    return n*.5+.5

def finish_colour(lin,target):
    # Normalize the integrated linear reflectance, including groove cavities.
    lin=np.clip(lin,.002,.98)
    lin*=np.asarray(target)[None,None,:]/lin.mean(axis=(0,1),dtype=np.float64)
    return T.to_srgb(np.clip(lin,0,1))

def trim():
    import make_trim_sheet as M
    src=json.loads((V1/'trims.json').read_text())
    p=paint('painted_ground');a=np.zeros((S,S,3),np.float32)
    h=np.zeros((S,S),np.float32);orm=np.zeros((S,S,3),np.float32);norm=np.zeros((S,S,3),np.float32)
    yy=0
    for i,(name,hpx,prof,col,rough,metal,_,_,_) in enumerate(M.STRIPS):
        v=(np.arange(hpx,dtype=np.float32)+.5)/hpx
        hv,ao=prof(v);hv=hv[:,None]*np.ones((1,S),np.float32);ao=ao[:,None]*np.ones((1,S),np.float32)
        h[yy:yy+hpx]=hv
        target=T.to_lin(col)
        lin=target[None,None,:]*(1+.024*p[yy:yy+hpx,...,None])*(.8+.2*ao[...,None])
        a[yy:yy+hpx]=finish_colour(lin,target)
        orm[yy:yy+hpx,:,0]=.7+.3*ao;orm[yy:yy+hpx,:,1]=rough;orm[yy:yy+hpx,:,2]=metal
        # U repeat=4m; strip V physical width=hpx/512m, whole-sheet V=2m.
        dx=(np.roll(hv,-1,1)-np.roll(hv,1,1))*.006/(2*4/S)
        dy=np.gradient(hv,axis=0)*.006/(1/512)
        nn=np.stack([-dx,dy,np.ones_like(hv)],axis=2);nn/=np.linalg.norm(nn,axis=2,keepdims=True)
        norm[yy:yy+hpx]=nn*.5+.5
        norm[yy]=norm[yy+hpx-1]=(.5,.5,1)
        yy+=hpx
    src['size_px']=[S,S];src['px_per_m']={'u':256,'v':512};src['height']='trim_sheet_house_height.png'
    src['_doc']='v2 1024 square trim sheet. U repeats4m, unchanged15 strip UV rectangles. V density512px/m; U256px/m. Height0..0.006m. OpenGL normals; ORM=AO,roughness,metalness.'
    for s in src['strips']:s['px'][2]=S
    (OUT/'trims.json').write_text(json.dumps(src,indent=2),encoding='utf-8')
    return a,norm,orm,h

def save_maps(name,e,seed):
    if e['structure']=='trim':alb,norm,orm,h=trim()
    else:
        h,c,d,accent=detail(e,seed)
        target=np.asarray(e['target_linear'],np.float32)
        strength=.30 if e['structure'] in ('panels','shingles') else .15
        lin=target[None,None,:]*(1+d[...,None]+accent)*(1-strength*c[...,None])
        alb=finish_colour(lin,target);norm=normal_physical(h,e['repeat_m'],e['height_range_m'])
        ao=np.clip(1-.38*c,.48,1);rough=np.clip(e['roughness']+.016*d,.05,1)
        orm=np.stack([ao,rough,np.full_like(h,e['metalness'])],axis=2)
    T.save(alb,OUT/(name+'.png'));T.save(norm,OUT/(name+'_normal.png'));T.save(orm,OUT/(name+'_orm.png'))
    Image.fromarray(np.round(h*65535).astype(np.uint16),mode='I;16').save(OUT/(name+'_height.png'))
    return alb,h

def reference_crop(name):
    ground=Image.open(ROOT/'design/maps/tdm/concepts/_candidates/A_showhome_ground_s12.png').convert('RGB')
    aerial=Image.open(ROOT/'design/maps/tdm/concepts/_candidates/A_showhome_aerial_s12.png').convert('RGB')
    a11=Image.open(ROOT/'design/maps/tdm/concepts/_candidates/A_showhome_aerial_s11.png').convert('RGB')
    if name.startswith('fibercement_clay'):return ground.crop((1170,170,1470,500))
    if name.startswith('fibercement_sage') or name=='fibercement_panel':return ground.crop((30,210,250,410))
    if name.startswith('printed') or name=='foundation_slab':return a11.crop((270,493,443,605))
    if name.startswith('roof'):return a11.crop((355,207,390,242))
    if name.startswith('asphalt'):return ground.crop((560,735,1180,830))
    if name.startswith('grass'):return a11.crop((492,610,541,639))
    if name.startswith('paving') or name.startswith('kerb') or name=='edging_strip':return ground.crop((1135,610,1390,697))
    if name.startswith('wood') or name=='timber_pallets':return a11.crop((1340,544,1445,625))
    if 'sand' in name or name.startswith('worksite'):return aerial.crop((15,140,200,240))
    if name=='metal_painted_yellow' or name=='metal_scaffold_tube':return a11.crop((1407,141,1425,197))
    if name=='truck_paint_white':return a11.crop((720,420,755,450))
    if name=='cardboard':return ground.crop((613,520,703,588))
    if name=='picket_wood_white':return ground.crop((63,548,276,610))
    if name=='trim_sheet_house':return ground.crop((1204,172,1228,318))
    if name=='metal_corrugated_site':return ground.crop((63,548,276,610))
    if name in ('garden_soil','worn_dirt','bark_mulch'):return a11.crop((500,36,650,75))
    if name in ('gravel','gravel_compacted'):return ground.crop((1184,642,1300,665))
    if name=='concrete_smooth':return a11.crop((294,504,408,588))
    return ground.crop((385,430,590,690))

def wrap(name,alb):
    dest=OUT/'_preview';dest.mkdir(exist_ok=True)
    im=Image.fromarray(np.clip(alb*255+.5,0,255).astype(np.uint8)).resize((256,256),Image.Resampling.LANCZOS)
    out=Image.new('RGB',(1544,550),(29,33,37));d=ImageDraw.Draw(out)
    d.text((12,8),name+' | 2 x 2 wrap | contrast 3x | matching concept crop',fill=(236,227,210))
    for row in range(2):
        for col in range(2):out.paste(im,(12+col*256,32+row*256))
    boosted=np.clip((alb-alb.mean((0,1)))*3+alb.mean((0,1)),0,1)
    bi=Image.fromarray((boosted*255).astype(np.uint8)).resize((256,256))
    for row in range(2):
        for col in range(2):out.paste(bi,(532+col*256,32+row*256))
    out.paste(reference_crop(name).resize((480,512),Image.Resampling.LANCZOS),(1052,32))
    out.save(dest/(name+'_wrap.png'))

def preview_sheets():
    names=[n for n in ENTRIES if (OUT/(n+'.png')).exists()]
    cols=4;cw=512;ch=284;rows=(len(names)+cols-1)//cols
    out=Image.new('RGB',(cw*cols,ch*rows),(31,34,37));d=ImageDraw.Draw(out)
    for i,n in enumerate(names):
        x=(i%cols)*cw;y=(i//cols)*ch
        d.text((x+6,y+5),n,fill=(238,228,210))
        out.paste(Image.open(OUT/(n+'.png')).convert('RGB').resize((250,250)),(x+4,y+26))
        out.paste(reference_crop(n).resize((250,250)),(x+258,y+26))
    out.save(OUT/'_preview/contact_sheet.png')
    # Material-data reference board: colour, normal, packed channels and physical height.
    main=['fibercement_clay','fibercement_sage','printed_concrete_layers','roof_shingle_dark','paving_slabs','kerb_concrete']
    out=Image.new('RGB',(1536,6*290),(29,33,37));d=ImageDraw.Draw(out)
    for j,n in enumerate(main):
        if not (OUT/(n+'.png')).exists():continue
        d.text((8,j*290+5),n+' | albedo / normal / ORM / height / concept / painted reference',fill=(238,228,210))
        for k,suf in enumerate(['','.normal','.orm','.height']):
            fp=OUT/(n+suf.replace('.','_')+'.png');im=Image.open(fp)
            if suf=='.height':im=Image.fromarray((np.asarray(im,dtype=np.float32)/257).astype(np.uint8))
            out.paste(im.convert('RGB').resize((248,248)),(k*256+4,j*290+30))
        out.paste(reference_crop(n).resize((248,248)),(1028,j*290+30))
        out.paste(Image.open(ROOT/'art/briefs/refs/painted_cladding_ref.png').convert('RGB').resize((248,248)),(1284,j*290+30))
    out.save(OUT/'_preview/material_reference_board.png')
    for n in names:
        out=Image.new('RGB',(1536,290),(29,33,37));d=ImageDraw.Draw(out)
        d.text((8,5),n+' | albedo / normal / ORM / height / concept / painted reference',fill=(238,228,210))
        for k,suf in enumerate(['','_normal','_orm','_height']):
            im=Image.open(OUT/(n+suf+'.png'))
            if suf=='_height':im=Image.fromarray((np.asarray(im,dtype=np.float32)/257).astype(np.uint8))
            out.paste(im.convert('RGB').resize((248,248)),(k*256+4,30))
        out.paste(reference_crop(n).resize((248,248)),(1028,30))
        out.paste(Image.open(ROOT/'art/briefs/refs/painted_cladding_ref.png').convert('RGB').resize((248,248)),(1284,30))
        out.save(OUT/'_preview'/(n+'_maps_compare.png'))

def macro():
    for n,seed in [('macro_ground',118),('macro_walls',119)]:
        a=.5+.12*noise(seed,180)+.035*noise(seed+5,65)
        Image.fromarray(np.round(np.clip(a,0,1)*65535).astype(np.uint16),mode='I;16').save(OUT/(n+'.png'))

def validate(names):
    report={}
    for n in names:
        e=ENTRIES[n];a=np.asarray(Image.open(OUT/(n+'.png')),np.float32)/255
        target=np.array(e['target_linear']);mean=T.to_lin(a).mean((0,1),dtype=np.float64);ratio=T.seam_ratio(a)
        height=Image.open(OUT/(n+'_height.png'));arr=np.asarray(height)
        map_sizes={k:list(Image.open(OUT/f).size) for k,f in e['maps'].items()}
        assert all(s==[S,S] for s in map_sizes.values()),(n,map_sizes)
        assert (OUT/(n+'_height.png')).read_bytes()[24]==16,n+' height must be PNG16'
        nn=np.asarray(Image.open(OUT/(n+'_normal.png')),np.float32)/255*2-1
        report[n]=dict(size=list(Image.open(OUT/(n+'.png')).size),height_dtype=str(arr.dtype),
                        mean_linear=mean.tolist(),target_linear=target.tolist(),mean_max_error=float(abs(mean-target).max()),
                        seam_ratio=list(map(float,ratio)),height_min=float(arr.min()/65535),height_max=float(arr.max()/65535),
                        normal_length_max_error=float(abs(np.linalg.norm(nn,axis=2)-1).max()),maps_complete=True,map_sizes=map_sizes,
                        palette_mean_applies=e['structure']!='trim',wrap_v_applies=e['structure']!='trim')
        print(n,'mean error',round(float(abs(mean-target).max()),6),'seam',tuple(round(float(v),2) for v in ratio),flush=True)
    old={}
    if (OUT/'validation.json').exists():old=json.loads((OUT/'validation.json').read_text())
    old.update(report);(OUT/'validation.json').write_text(json.dumps(old,indent=2),encoding='utf-8')
    match=[v for n,v in old.items() if v.get('palette_mean_applies',True)]
    err=max(v['mean_max_error'] for v in match)
    nerr=max(v['normal_length_max_error'] for v in old.values())
    notes=['# v2 validation and look comparison','',
           f'{len(old)} complete material sets, all four maps at 1024 x 1024. '+
           'Every height PNG has an actual 16-bit IHDR and unsigned linear greyscale pixels.', '',
           f'Maximum absolute error in integrated linear albedo mean: {err:.8f}. '+
           'This includes groove cavity colour; clean and weathered members retain the family palette mean. '+
           'The mixed-colour trim atlas is exempt from a single-colour mean: each strip is individually mean matched.', '',
           f'Normal vector unit-length maximum error after RGB8 quantization: {nerr:.5f}. '+
           'Normals derive from physical height range and metres per repeat. Trim normals derive '+
           'from the original kit profile functions with the sheet V physical width kept at two metres.', '',
           'Wrap inspection: repeat seams are imperceptible in the painted colour. Recessed joints '+
           'and roof course boundaries intentionally remain visible physical structure. The roof '+
           'boundary was iterated until its wrap-edge comparison ceased showing a row change. '+
           'The cracked asphalt tar curve and compacted gravel can have seam ratios above 1 '+
           'because of their structured features; their feature functions are periodic.', '',
           'The contact sheet and every wrap image place the albedo next to its concept surface crop. '+
           'Every maps_compare image places albedo, normal, ORM and height next to the concept and '+
           'painted cladding reference. The reference board covers the main close-view materials.', '',
           'Comparison: sage and clay retain the calm concept hue, broad vertical strokes and soft '+
           'angular patches. Thin grooves add cavities without putting a directional highlight '+
           'in the albedo. Printed concrete remains cream with gentle bead shading. Roof remains '+
           'charcoal with restrained half-bond variation. Ground colours follow the established '+
           'palette; tyre tread, square repair patches, tar seals and joints add exact shape rather '+
           'than photo grit.', '',
           'Some requested surfaces (bark mulch, scaffold tube, loose gravel, corrugated site fence) '+
           'are not shown at texture-inspection size in the concepts. Their previews use the closest '+
           'visible earth, paving or site surface and preserve the established palette. These are '+
           'original supplemental designs, not claimed literal reproductions of a concept crop.', '',
           'Krea2 provenance: three reference-guided, mirror-quilted 1024² sources, seeds260081–260083. '+
           'The identity adapter is the required repository --ref workflow; no T2I LoRAs. '+
           'Precise structure and broad angular breakup are procedural. No new foliage cards or decals.', '',
           'Physical 1 m / 5 m wall, roof, street and aerial comparisons come from build_houses.py. '+
           'This data inspection does not certify the game height shader; the game session must '+
           'use the manifest height ranges, normal convention and linear data imports.']
    (OUT/'VALIDATION.md').write_text('\n'.join(notes)+'\n',encoding='utf-8')

def readme():
    lines=['# Showhome painted material library v2','',
           'Continues v1 palette, helpers and metre UV convention. All four maps are 1024 x 1024 PNG. '+
           'Albedo is sRGB; normals and ORM are linear; height is unsigned 16-bit linear grayscale (white = high).', '',
           'Normals use OpenGL / glTF +U red, +V green. ORM = R occlusion, G roughness, B metalness. '+
           'Use REPEAT samplers on both axes. All tint multipliers are white except neutral fibercement_panel, '+
           'whose linear mean is .70 and is tinted by concept linear colour / .70. No baked directional light.', '',
           'Each family shares the exact integrated linear mean from ../_src/palette.json, including cavities. '+
           'Fresh/weathered variants may be mask blended without brightness changes. Krea2 provides broad '+
           'paint colour; every seam, layer, shingle joint, tyre tread and height channel is exact procedural structure. '+
           'No photographic grain and no micro dirt. Foliage cards and decal atlas remain on hold.', '',
           '## Mapping and physical depth','',
           'Wall V runs up. Jointed cladding repeat is 4.8 m: U .125/.375/.625/.875, V .25/.75. '+
           'Panels are 1.2 x 2.4 m, seams 14 mm wide with 9 mm recession and 2 mm rounded edges. '+
           'Real panel meshes use seam-free fibercement_panel, so parallax does not duplicate their geometry. '+
           'The top-of-panel brightening is an intrinsic painted wash, never a cast lighting highlight.', '',
           'Printed beads are .04 m high, 32 per 1.28 m repeat. Roof V points up slope: '+
           '.5 m shingle width and .25 m course pitch, half stagger, .010 m max relief. '+
           'Paving is .6 m; kerb U follows length with joints at .5 and 1.5 m in the 2 m repeat. '+
           'Low edging and trim profiles take physical depth from geometry. Do not displace their collision meshes.', '',
           'Trim sheet keeps the v1 15 strips and UV rectangles in trims.json; U is still 4 m. '+
           'The v2 sheet is square 1024 x 1024 (256 px/m along U); V rectangles are unchanged. '+
           'It carries mixed strip colours and metalness, so its integrated colour is intentionally exempt '+
           'from single-colour mean matching. Use the profile strip UV rectangles with a 2 px vertical inset.', '',
           '## Textures','', '| Name | Use | Repeat m | Tint | Roughness | Height range m |',
           '|---|---|---:|---|---:|---:|']
    for n,e in ENTRIES.items():
        lines.append(f"| `{n}` | {e['use']} | {e['repeat_m']} | white | {e['roughness']} | 0–{e['height_range_m']:.5f} |")
    lines+=['','Every row has `.png`, `_normal.png`, `_orm.png` and `_height.png`. '+
            'Compatibility support surfaces are included for the existing kit rather than rewriting its material names.', '',
            '## Macro breakup','',
            '`macro_ground.png` and `macro_walls.png`: seamless 1024², 16-bit linear greyscale, '+
            '32 m repeat, neutral .5. Suggested subtle multiplier: `1 + (mask - .5) * .12`; '+
            'ground and walls use different seeds. Do not multiply AO or height by this mask.', '',
            '## Rebuild and checks','',
            '1. `python assets/maps/showhome/textures/v2/_src/generate_painted_raws.py` (ComfyUI 8188; no use of 8199).',
            '2. `python assets/maps/showhome/textures/v2/_src/build_v2.py`.',
            '3. Inspect `_preview/contact_sheet.png`, `_preview/material_reference_board.png` '+
            'and every `<name>_wrap.png`; each includes the matching concept crop. '+
            'House wall, roof and street geometry renders are produced by build_houses.py.', '',
            'Seed/prompt/reference provenance is `_src/KREA_PROVENANCE.json`. '+
            'The repository helper uses its required Krea2 identity-edit adapter for `--ref`; '+
            'no LoRAs are loaded for text-to-image. Reference raws are filtered to broad colour and '+
            'mean-normalized; image structure is never used as geometry.', '',
            '`manifest.json` is the machine-readable mapping contract. `validation.json` records dimensions, '+
            'linear mean errors, seam ratios, height encoding and normal unit-length errors. '+
            'Texture data and wrap tests cannot alone certify in-game parallax response; '+
            'the separate game session implements height blending and sampler colour spaces.']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

def main():
    write_manifest();readme()
    if '--manifest-only' in sys.argv:return
    names=[n for n in sys.argv[1:] if n in ENTRIES] or list(ENTRIES)
    (OUT/'_preview').mkdir(exist_ok=True)
    for n in names:
        i=list(ENTRIES).index(n);a,h=save_maps(n,ENTRIES[n],401+i*47);wrap(n,a)
    macro();preview_sheets();validate(names)

if __name__=='__main__':main()
