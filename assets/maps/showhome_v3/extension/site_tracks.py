"""Light wheel-worn construction lanes using existing painted depth maps.

Pure path/mask functions can be checked without Blender. build() lazily loads
Blender helpers and creates thin visual finish meshes only; existing terrain or
parking roof supplies collision. Building, foundation, pit and ramp openings are
clipped out, so no finish face bridges a void or changes a playable route.
"""
import math

PATHS=[
    dict(name='west_receiving_lane',controls=[(323,745),(320.5,770),(322,792),(321,802)],width_m=5.8,wheel_strength=.56),
    dict(name='west_rear_haul_lane',controls=[(321,831),(323,842),(316.8,862),(315,883)],width_m=4.8,wheel_strength=.52),
    dict(name='east_delivery_lane',controls=[(466,762),(465,790),(465,817),(469,834)],width_m=5.6,wheel_strength=.58),
    dict(name='east_frame_supply_lane',controls=[(432,748),(435,775),(433,802)],width_m=4.6,wheel_strength=.50),
    dict(name='west_frame_turnout',controls=[(333,791),(335,800),(341,810),(346,814)],width_m=4.2,wheel_strength=.46),
    dict(name='material_worker_scuff',controls=[(329,750),(328,775),(330,786)],width_m=1.6,wheel_strength=.18),
]
WET_SPOTS=[(321.5,795,3.4),(465,807,3.0),(316,860,2.6)]

def nearest(x,y,controls):
    best=None;station=0
    for a,b in zip(controls,controls[1:]):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if length<1e-6:continue
        t=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/(length*length)))
        px,py=a[0]+dx*t,a[1]+dy*t;distance=math.hypot(x-px,y-py)
        lateral=((x-px)*-dy+(y-py)*dx)/length
        row=(distance,lateral,station+t*length)
        if best is None or distance<best[0]:best=row
        station+=length
    return best or (1e9,0,0)

def masks(x,y):
    broad=0;wheel=0
    for path in PATHS:
        distance,lateral,station=nearest(x,y,path['controls']);half=path['width_m']/2
        envelope=max(0,1-distance/half)
        broad=max(broad,envelope)
        if path['width_m']>2:
            pair=max(0,1-abs(abs(lateral)-.95)/.52)
            variation=.82+.18*math.sin(station*.37+len(path['name']))**2
            wheel=max(wheel,pair*envelope*path['wheel_strength']*variation)
        else:wheel=max(wheel,envelope*path['wheel_strength'])
    wet=max([max(0,1-math.hypot(x-cx,y-cy)/radius) for cx,cy,radius in WET_SPOTS])
    # R is dark worn dirt, B/A are the existing32mm track depth family. Heavy
    # wet dirt is confined to small localized spots, never an entire haul lane.
    return (.035+.27*wet*broad,.06*broad,wheel,.055*wet*broad)

def _clip(poly,axis,value,less):
    result=[]
    if not poly:return result
    for a,b in zip(poly,poly[1:]+poly[:1]):
        ina=a[axis]<=value+1e-7 if less else a[axis]>=value-1e-7
        inb=b[axis]<=value+1e-7 if less else b[axis]>=value-1e-7
        if ina:result.append(a)
        if ina!=inb:
            t=(value-a[axis])/(b[axis]-a[axis]);result.append(tuple(a[k]+(b[k]-a[k])*t for k in range(len(a))))
    return result

def subtract_rect(poly,rect):
    x0,y0,x1,y1=rect
    if max(p[0] for p in poly)<=x0 or min(p[0] for p in poly)>=x1 or max(p[1] for p in poly)<=y0 or min(p[1] for p in poly)>=y1:return [poly]
    middle=_clip(_clip(poly,0,x0,False),0,x1,True)
    parts=[_clip(poly,0,x0,True),_clip(poly,0,x1,False),_clip(middle,1,y0,True),_clip(middle,1,y1,False)]
    return [p for p in parts if len(p)>=3 and abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(p,p[1:]+p[:1])))>.0001]

def geometry(path,exclusions):
    sections=[];station=0;controls=path['controls'];half=path['width_m']/2
    offsets=sorted({-half,half,-.95,-.43,0,.43,.95} if half>.95 else {-half,0,half})
    for index,(a,b) in enumerate(zip(controls,controls[1:])):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy);count=max(1,math.ceil(length/1.2))
        for k in range(count+(1 if index==len(controls)-2 else 0)):
            t=k/count;px,py=a[0]+dx*t,a[1]+dy*t;s=station+t*length
            row=[]
            for offset in offsets:
                # Restrained irregular shoulders break the ruler-straight edge.
                if abs(abs(offset)-half)<1e-6:offset*=1+.035*math.sin(s*.59+index*1.7)
                x,y=px-dy/length*offset,py+dx/length*offset
                row.append((x,y,offset/6,s/6,*masks(x,y)))
            sections.append(row)
        station+=length
    polygons=[]
    for a,b in zip(sections,sections[1:]):
        for k in range(len(offsets)-1):
            parts=[[a[k],b[k],b[k+1],a[k+1]]]
            for rect in exclusions:parts=[q for p in parts for q in subtract_rect(p,rect)]
            polygons.extend(parts)
    return polygons

def build(root,exclusions):
    import common as C
    mat=C.material('TrackedEarth','soil','worksite_mud_tracks',(1,.99,.97),rough=.9)
    mat.name='M_GND_Ext_TrackedEarth';mat['repeat']=[6,6];mat['showhome_ground_tint']=[1,.99,.97]
    result=[]
    for path in PATHS:
        polygons=geometry(path,exclusions);verts=[];faces=[];attributes=[]
        for poly in polygons:
            n=len(verts);verts.extend((p[0],p[1],.014) for p in poly);attributes.extend(poly)
            faces.extend((n,n+k,n+k+1) for k in range(1,len(poly)-1))
        ob=C.mesh('EXT_TrackedEarth_'+path['name'],verts,faces,mat,root);ob['part']='terrain/tracked_paths';ob['ground_blend']='showhome_height_blend_v2';ob['thin_finish_over_existing_support']=True
        ca=ob.data.color_attributes.new(name='Col',type='FLOAT_COLOR',domain='CORNER')
        for face in ob.data.polygons:
            for li in face.loop_indices:
                p=attributes[ob.data.loops[li].vertex_index];ob.data.uv_layers[0].data[li].uv=p[2:4];ca.data[li].color=p[4:8]
        ob.data.color_attributes.active_color=ca
        result.append(dict(**path,polygons=len(polygons),triangles=len(faces),phys='soil',collision='existing terrain or roof deck',surface_z_m=.014,uv_repeat_m=6,height_range_m=.032,rgba_semantics='shared height-blend masks; localized wet dirt',base_tint=[1,.99,.97],openings_clipped=True))
    return result
