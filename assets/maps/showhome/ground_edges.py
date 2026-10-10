"""Geometry and deterministic RGBA border masks for the existing ground partition.

The caller supplies its accumulator and world-metre UV helpers. No map layout is
changed: raised kerbs are emitted into an explicit collision-step handoff.
"""
import json
import math
from pathlib import Path
import numpy as np

GRASS = {'lawn','lawn_ns','lawn_ew','verge','grass'}
HARD = {'road','lane','pave','pave_A','conc'}
EARTH = {'sand','earth','soil','mulch'}
BOUNDARIES = {}
CACHE = {}
RUNS = []


def reset():
    BOUNDARIES.clear(); CACHE.clear(); RUNS.clear()


def register_partition(xs, ys, grid, zones):
    """Collect actual partition edges (priority-resolved), not hidden zone outlines."""
    groups = {}
    nx,ny = grid.shape
    for axis in (0,1):
        size = nx if axis == 0 else ny
        along = ny if axis == 0 else nx
        for i in range(1,size):
            for j in range(along):
                aa = int(grid[i-1,j] if axis==0 else grid[j,i-1])
                bb = int(grid[i,j] if axis==0 else grid[j,i])
                if aa < 0 or bb < 0:
                    continue
                a,b = zones[aa][0],zones[bb][0]
                if a == b or 'none' in (a,b):
                    continue
                if a in GRASS and b in GRASS:
                    continue
                c = float(xs[i] if axis==0 else ys[i])
                lo = float(ys[j] if axis==0 else xs[j])
                hi = float(ys[j+1] if axis==0 else xs[j+1])
                for first,second in ((a,b),(b,a)):
                    key = (first,second,axis,round(c,4))
                    groups.setdefault(key,[]).append((lo,hi))
    added = []
    for (first,second,axis,c), intervals in groups.items():
        spans = []
        for lo,hi in sorted(intervals):
            if spans and abs(spans[-1][1]-lo)<1e-4:
                spans[-1] = (spans[-1][0],hi)
            else:
                spans.append((lo,hi))
        for lo,hi in spans:
            row = (axis,c,lo,hi,second)
            BOUNDARIES.setdefault(first,[]).append(row)
            added.append((first,*row))
    return added


def distance(kind,x,y,predicate):
    best = 1e4
    for axis,c,lo,hi,other in BOUNDARIES.get(kind,[]):
        if not predicate(other):
            continue
        along,across = (y,x) if axis==0 else (x,y)
        da = max(lo-along,0,along-hi)
        best = min(best,math.hypot(across-c,da))
    return best


def fade(d,width):
    t = max(0,min(1,1-d/width))
    return t*t*(3-2*t)


def mask(kind,x,y):
    key = (kind,round(x,4),round(y,4))
    if key in CACHE:
        return CACHE[key]
    r=g=b=a=0.
    # Smooth large-scale masks; actual v2 height introduces the ragged tuft/pebble boundary.
    if kind in GRASS:
        d=distance(kind,x,y,lambda o:o not in GRASS)
        r=.94*fade(d,.68)
        for cx,cy in ((27.4,26),(18,41.8),(2.9,12),(2.9,36),(23,14.1)):
            r=max(r,.86*math.exp(-(((x-cx)/.9)**2+((y-cy)/.9)**2)))
        # Trampled tyre approach by the parked truck: no terrain displacement.
        tyre=math.exp(-(((x-29.65)/.68)**2+((y-23.2)/2.9)**2))
        a=.96*tyre
    elif kind in HARD:
        g=.96*fade(distance(kind,x,y,lambda o:o=='gravel'),.48)
        b=.82*fade(distance(kind,x,y,lambda o:o in GRASS),.32)
        a=.94*fade(distance(kind,x,y,lambda o:o in ('sand','earth')),.95)
        # Mud washed from the verge onto the truck approach, separated broad wheel paths.
        if 27.65<x<35.0 and 20<y<26.5:
            streak=math.exp(-((y-22.1)/.3)**2)+math.exp(-((y-24.25)/.34)**2)
            a=max(a,.62*min(1,streak)*max(0,1-(x-29.5)/5.7))
    elif kind=='gravel':
        r=.85*fade(distance(kind,x,y,lambda o:o in GRASS),.32)
        b=.35*fade(distance(kind,x,y,lambda o:o in GRASS),.25)
    elif kind in EARTH:
        r=.65*fade(distance(kind,x,y,lambda o:o in HARD),.6)
        if kind=='soil':
            b=.26*fade(distance(kind,x,y,lambda o:o in GRASS),.3)
    # Broad directional-neutral modulation; leaves endpoints at zero and stays low contrast.
    variation=.94+.06*math.sin(x*2.1+y*.77)*math.sin(y*1.8-x*.61)
    out=tuple(round(max(0,min(1,v*variation)),6)for v in(r,g,b,a))
    CACHE[key]=out
    return out


def _record(points,height,width,boxes,label):
    if height<=.0200001:
        return
    index=len(RUNS)+1
    in_map=any(0<=p[0]<=72 and 0<=p[1]<=48 for p in points)
    RUNS.append(dict(id=f'GSTEP_W_{index:04d}',kind=label,polyline=[[round(v,5)for v in p]for p in points],
                     width_m=width,height_m=height,top_z_m=height,collision_required=in_map,
                     boxes=boxes,frame='design Z-up metres'))


def stone(acc,quad,height,material,uv,label='kerb',record=True):
    """Closed 1-course stone prism, 12 mm bevel and 3 mm end joints, no subdivision."""
    q=np.asarray(quad,float)
    centre=q.mean(axis=0)
    outer=q.copy()
    bevel=min(.014,height*.25)
    inner=[]
    for p in q:
        d=centre-p
        # Separate bevel across the stone's narrow dimension from its long edges.
        shift=np.clip(d,-bevel,bevel)
        inner.append(p+shift)
    inner=np.asarray(inner)
    corners=[(p[0],p[1],height)for p in inner]
    cols=[(0,0,0,0)]*len(q)
    acc.poly(corners,material,[uv(*p)for p in inner],cols,want=(0,0,1))
    for k in range(len(q)):
        j=(k+1)%len(q)
        a,b=outer[k],outer[j]
        c,d=inner[j],inner[k]
        top=[(a[0],a[1],height-bevel),(b[0],b[1],height-bevel),(c[0],c[1],height),(d[0],d[1],height)]
        acc.poly(top,material,[uv(p[0],p[1])for p in top],[(0,0,0,0)]*4,want=(0,0,1))
        wall=[(a[0],a[1],.003),(b[0],b[1],.003),(b[0],b[1],height-bevel),(a[0],a[1],height-bevel)]
        normal=((a[0]+b[0])/2-centre[0],(a[1]+b[1])/2-centre[1],0)
        acc.poly(wall,material,[(i*.2,p[2]/2)for i,p in enumerate(wall)],[(0,0,0,0)]*4,want=normal)
    if record and height>.0200001:
        mn=[float(outer[:,0].min()),float(outer[:,1].min()),0]
        mx=[float(outer[:,0].max()),float(outer[:,1].max()),height]
        width=min(math.hypot(*(outer[(k+1)%len(q)]-outer[k]))for k in range(len(q)))
        _record([centre.tolist()],height,width,[dict(min=mn,max=mx)],label)
        RUNS[-1]['footprint']=[[round(float(v),5)for v in p]for p in outer]


def straight_stones(acc,kind,x0,y0,x1,y1,material):
    axis=1 if y1-y0>x1-x0 else 0
    lo,hi=(y0,y1)if axis==1 else(x0,x1)
    length=hi-lo
    n=max(1,int(math.ceil(length-1e-6)))
    for i in range(n):
        start=lo+i
        end=min(hi,start+1)
        if end-start<.009:
            continue
        h=.11 if kind.startswith('kerb') else .028
        mid=(start+end)/2
        # Front gate crossing and delivery pod bay get genuinely dropped stones.
        if kind.startswith('kerb') and axis==1 and abs(x0-30)<.3 and (25.05<=mid<=27.05 or 30.0<=mid<=34.5):
            h=.016
        a,b=start+.003,end-.003
        quad=[(x0,a),(x1,a),(x1,b),(x0,b)]if axis==1 else[(a,y0),(b,y0),(b,y1),(a,y1)]
        uv=(lambda x,y,st=start:((y-st+.5)/2,(x-x0)/2))if axis==1 else(lambda x,y,st=start:((x-st+.5)/2,(y-y0)/2))
        stone(acc,quad,h,material,uv,'kerb'if kind.startswith('kerb')else'concrete edging')


def curved_stones(acc,inner,outer,material):
    u=0.
    for i in range(len(inner)-1):
        a,b,c,d=np.array(inner[i]),np.array(inner[i+1]),np.array(outer[i+1]),np.array(outer[i])
        length=np.linalg.norm(c-d)
        n=max(1,int(math.ceil(length)))
        for k in range(n):
            t0=(k+.003/max(length,.01))/n;t1=(k+1-.003/max(length,.01))/n
            quad=[a+(b-a)*t0,a+(b-a)*t1,d+(c-d)*t1,d+(c-d)*t0]
            def uv(x,y):return(x/2,y/2)
            stone(acc,quad,.11,material,uv,'curved kerb')
        u+=length


def edging_lines(acc,rows,material,steel_material=None):
    """Add 5 cm restraint strips at every paving/lawn or gravel/lawn boundary."""
    done=set()
    for kind,axis,c,lo,hi,other in rows:
        if kind not in GRASS or other not in HARD|{'gravel'}:
            continue
        key=(axis,c,lo,hi)
        if key in done:
            continue
        done.add(key)
        # Keep thin steel edging flush to the gravel relief; concrete edging stands 28 mm.
        h=.018 if other=='gravel'else.028
        if axis==0:quad=[(c-.025,lo),(c+.025,lo),(c+.025,hi),(c-.025,hi)]
        else:quad=[(lo,c-.025),(hi,c-.025),(hi,c+.025),(lo,c+.025)]
        stone(acc,quad,h,steel_material if other=='gravel' and steel_material else material,lambda x,y:(x/2,y/2),
              'steel gravel restraint'if other=='gravel'else'concrete paving restraint')


def write_steps(path):
    rows=[]
    for run in RUNS:
        rows.append(run)
        mirrored=json.loads(json.dumps(run))
        mirrored['id']=run['id'].replace('_W_','_E_')
        mirrored['polyline']=[[72-p[0],p[1]]for p in run['polyline']]
        if 'footprint' in run:
            mirrored['footprint']=[[72-p[0],p[1]]for p in reversed(run['footprint'])]
        mirrored['boxes']=[dict(min=[72-b['max'][0],b['min'][1],b['min'][2]],
                                max=[72-b['min'][0],b['max'][1],b['max'][2]])for b in run['boxes']]
        rows.append(mirrored)
    doc=dict(version=2,doc='Every raised kerb/edging unit (>20mm) emitted by ground_edges. Flat art stays <=20mm. '+
                          'Apply boxes for straight units; curved units also carry precise render footprint polygons. '+
                          'Outside-play rows are render-only skirt information.',
             frame='design: metres X east,Y north,Z up; Bevy=(x,z,-y)',
             max_step_m=.12,runs=rows)
    Path(path).write_text(json.dumps(doc,indent=1)+'\n',encoding='utf8')
    return doc
