"""Gravel haul-road geometry and fence placements, in design-world metres."""
import math,sys
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import common as C
CONTROL=[(447,681),(447,847)]
WIDTH=6.0
RAMP_EXCAVATION=[443.85,847,450.15,873]
TOP_APRON_RECTS=[]

def _samples(controls):
    points=[]
    for i in range(len(controls)-1):
        p0=Vector(controls[max(0,i-1)]);p1=Vector(controls[i]);p2=Vector(controls[i+1]);p3=Vector(controls[min(len(controls)-1,i+2)])
        n=max(2,math.ceil((p2-p1).length/1.2))
        for k in range(n):
            t=k/n;q=.5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t);points.append(q)
    points.append(Vector(controls[-1]));return points
POINTS=_samples(CONTROL)
SPUR=[]
PATHS=[POINTS]

def distance(x,y):
    q=Vector((x,y));best=1e8
    for a,b in [(a,b) for path in PATHS for a,b in zip(path,path[1:])]:
        d=b-a;t=max(0,min(1,(q-a).dot(d)/max(d.length_squared,1e-8)));best=min(best,(q-(a+d*t)).length)
    return best

def road(root):
    # The existing painted gravel set is warm. This calibrated multiplier
    # neutralizes its mean albedo while retaining the original pebble pattern.
    tint=(.58,.76,.98)
    mat=C.material('HaulRoad','gravel','gravel',tint,rough=.92);mat.name='M_GND_Ext_HaulGravel';mat['repeat']=[1,1];mat['showhome_ground_tint']=list(tint)
    def clip(poly,axis,value,keep_less):
        if not poly:return []
        result=[]
        for a,b in zip(poly,poly[1:]+poly[:1]):
            ina=a[axis]<=value+1e-7 if keep_less else a[axis]>=value-1e-7
            inb=b[axis]<=value+1e-7 if keep_less else b[axis]>=value-1e-7
            if ina:result.append(a)
            if ina!=inb:
                t=(value-a[axis])/(b[axis]-a[axis]);result.append(tuple(a[k]+(b[k]-a[k])*t for k in range(3)))
        return result
    def outside_excavation(poly):
        x0,y0,x1,y1=RAMP_EXCAVATION
        middle=clip(clip(poly,0,x0,False),0,x1,True)
        return [clip(poly,0,x0,True),clip(poly,0,x1,False),clip(middle,1,y0,True),clip(middle,1,y1,False)]
    polygons=[]
    total_length=0
    for path_index,path in enumerate(PATHS):
        edges=[];length=0
        for i,p in enumerate(path):
            tangent=(path[min(i+1,len(path)-1)]-path[max(i-1,0)]).normalized();side=Vector((-tangent.y,tangent.x))
            if i:length+=(p-path[i-1]).length
            edge=[]
            for lateral in (-WIDTH/2,WIDTH/2):
                q=p+side*lateral;edge.append(q)
            edges.append(edge)
        for i,(a,b) in enumerate(zip(edges,edges[1:])):
            quad=[(a[0].x,a[0].y,.014),(b[0].x,b[0].y,.014),(b[1].x,b[1].y,.014),(a[1].x,a[1].y,.014)]
            polygons.extend(p for p in outside_excavation(quad) if len(p)>=3)
        total_length+=length
    for x0,y0,x1,y1 in TOP_APRON_RECTS:polygons.append([(x0,y0,.014),(x1,y0,.014),(x1,y1,.014),(x0,y1,.014)])
    # Keep the existing whole-road convex support prisms. Only the visual
    # surface gains lateral samples for the two wheel bands in COLOR_0.
    for index,poly in enumerate(polygons):
        for k in range(1,len(poly)-1):
            top=[poly[0],poly[k],poly[k+1]]
            area=(Vector(top[1])-Vector(top[0])).cross(Vector(top[2])-Vector(top[0])).length
            longest=max((Vector(top[(k+1)%3])-Vector(top[k])).length for k in range(3))
            if area/max(longest,.001)<.01:continue
            vs=top+[(x,y,-.04) for x,y,z in top]
            C.col_mesh('EXT_HaulRoad_'+str(index)+'_'+str(k),vs,[(0,1,2),(3,5,4),(0,3,4,1),(1,4,5,2),(2,5,3,0)],'gravel',parent=root)
    refined=[]
    for poly in polygons:
        remainder=poly
        for xcut in (445.53,446.05,446.57,447,447.43,447.95,448.47):
            one=clip(remainder,0,xcut,True);remainder=clip(remainder,0,xcut,False)
            if len(one)>=3:refined.append(one)
        if len(remainder)>=3:refined.append(remainder)
    verts=[];faces=[]
    for poly in refined:
        n=len(verts);verts.extend(poly)
        for k in range(1,len(poly)-1):
            a,b,c=map(Vector,(poly[0],poly[k],poly[k+1]))
            if (b-a).cross(c-a).length>.0001:faces.append((n,n+k,n+k+1))
    ob=C.mesh('EXT_GravelHaulRoad',verts,faces,mat,root);ob['part']='terrain/access_road';ob['ground_blend']='showhome_height_blend_v2';ob['ramp_excavation_trimmed']=True
    color=ob.data.color_attributes.new(name='Col',type='FLOAT_COLOR',domain='CORNER')
    for face in ob.data.polygons:
        for li in face.loop_indices:
            ix=ob.data.loops[li].vertex_index;x,y,z=verts[ix];ob.data.uv_layers[0].data[li].uv=(x,y)
            rut=max(0,1-abs(abs(x-447)-.95)/.52)
            color.data[li].color=(.04,0,.42*rut,.025*rut)
    ob.data.color_attributes.active_color=color
    return dict(polyline=[list(p) for p in CONTROL],alignment='straight_perpendicular_to_public_street',junction_start_y_m=681,public_street_overlap=False,ramp_spur=SPUR,width_m=WIDTH,length_m=total_length,surface='gravel',finish='compacted grey pebbles with paired wheel wear',tint=list(tint),height_range_source='gravel_height.png',height_range_m=.028,tyre_depth_source='worksite_mud_tracks_height.png',tyre_depth_range_m=.032,tyre_repeat_m=6,iron_panels='site_mesh_panel',ramp_excavation_trimmed=True,local_top_entry_apron=TOP_APRON_RECTS,ground_retained_under_road=True)

def iron_fence_positions():
    rows=[]
    for side_sign in (-1,1):
        last=None
        for i,(a,b) in enumerate(zip(POINTS,POINTS[1:])):
            p=(a+b)/2;tangent=(b-a).normalized();side=Vector((-tangent.y,tangent.x));q=p+side*(WIDTH/2+.45)*side_sign
            # Keep the perimeter entry, courtyard crossing and ramp forecourt open.
            if p.y<738 or 811<p.y<833 or p.y>844:continue
            if last is not None and (q-last).length<2.6:continue
            rows.append((q.x,q.y,math.degrees(math.atan2(tangent.y,tangent.x))));last=q
    return rows
