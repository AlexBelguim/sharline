"""Independent integrated capsule checks for the three placed cabin stair stacks.

Uses the reusable stair's authored <=60mm route and all fixed/placed COLL data.
Interactive office door leaves are tested open, as in the stair asset's own QA.
No Blender, game source, source placements or assets are modified.
"""
import json,math,sys,hashlib
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]

def read(path):return json.loads(Path(path).read_text())
def norm(v):return float(np.linalg.norm(v))

def triangles(row):
    vs=np.array(row['vertices']);out=[]
    for nx,ny,nz,d in row['planes']:
        n=np.array([nx,ny,nz]);pts=vs[np.abs(vs@n-d)<3e-5]
        if len(pts)<3:continue
        centre=pts.mean(0);u=pts[0]-centre;u/=norm(u);v=np.cross(n,u)
        pts=sorted(pts,key=lambda p:math.atan2((p-centre)@v,(p-centre)@u))
        out.extend((pts[0],pts[i],pts[i+1]) for i in range(1,len(pts)-1))
    return out

def point_tri(p,a,b,c):
    ab=b-a;ac=c-a;ap=p-a;d1=ab@ap;d2=ac@ap
    if d1<=0 and d2<=0:return norm(p-a)
    bp=p-b;d3=ab@bp;d4=ac@bp
    if d3>=0 and d4<=d3:return norm(p-b)
    vc=d1*d4-d3*d2
    if vc<=0 and d1>=0 and d3<=0:return norm(p-(a+ab*(d1/(d1-d3))))
    cp=p-c;d5=ab@cp;d6=ac@cp
    if d6>=0 and d5<=d6:return norm(p-c)
    vb=d5*d2-d1*d6
    if vb<=0 and d2>=0 and d6<=0:return norm(p-(a+ac*(d2/(d2-d6))))
    va=d3*d6-d5*d4
    if va<=0 and d4-d3>=0 and d5-d6>=0:return norm(p-(b+(c-b)*((d4-d3)/((d4-d3)+(d5-d6)))))
    den=1/(va+vb+vc);return norm(p-(a+ab*(vb*den)+ac*(vc*den)))

def seg_seg(p1,q1,p2,q2):
    d1=q1-p1;d2=q2-p2;r=p1-p2;a=d1@d1;e=d2@d2;f=d2@r
    clamp=lambda x:max(0,min(1,x))
    if a<1e-12:s=0;t=clamp(f/e) if e else 0
    else:
        c=d1@r
        if e<1e-12:t=0;s=clamp(-c/a)
        else:
            b=d1@d2;den=a*e-b*b;s=clamp((b*f-c*e)/den) if den>1e-12 else 0;t=(b*s+f)/e
            if t<0:t=0;s=clamp(-c/a)
            elif t>1:t=1;s=clamp((b-c)/a)
    return norm((p1+d1*s)-(p2+d2*t))

def capsule_distance(row,foot):
    a=np.array(foot)+[0,0,.32];b=np.array(foot)+[0,0,1.48]
    enter=0.;leave=1.;direction=b-a
    for nx,ny,nz,d in row['planes']:
        n=np.array([nx,ny,nz]);den=n@direction;dist=d-n@a
        if abs(den)<1e-9:
            if dist<0:enter=2;break
        elif den>0:leave=min(leave,dist/den)
        else:enter=max(enter,dist/den)
    if enter<=leave and enter<=1 and leave>=0:return 0.
    if '_tris' not in row:row['_tris']=triangles(row)
    result=1e6
    for p,q,s in row['_tris']:
        result=min(result,point_tri(a,p,q,s),point_tri(b,p,q,s),seg_seg(a,b,p,q),seg_seg(a,b,q,s),seg_seg(a,b,s,p))
    return result

def transformed(source,placement):
    angle=math.radians(placement['yaw_deg']);c,s=math.cos(angle),math.sin(angle)
    rotation=np.array([[c,-s,0],[s,c,0],[0,0,1]]);scale=placement['scale'];offset=np.array(placement['position'])
    vertices=np.array(source['vertices'])@rotation.T*scale+offset
    planes=np.array(source['planes']);normals=planes[:,:3]@rotation.T
    result=dict(source);result.update(name=placement['id']+'::'+source['name'],vertices=vertices.tolist(),
        planes=np.c_[normals,planes[:,3]*scale+normals@offset].tolist(),aabb=dict(min=vertices.min(0).tolist(),max=vertices.max(0).tolist()))
    return result

def main():
    fixed=read(HERE/'collision.json')['volumes'];placements=read(HERE/'placements.generated.json')['instances']
    catalog={p['id']:p for p in read(ROOT/'assets/props/catalog.json')['props']};cache={};rows=list(fixed)
    for placement in placements:
        pid=placement['prop_id']
        if pid not in cache:cache[pid]=read(ROOT/'assets'/catalog[pid]['collision'])['volumes']
        for source in cache[pid]:
            if pid=='site_office' and (source.get('parent') or '').startswith('OPEN_'):continue
            rows.append(transformed(source,placement))
    lows=np.array([r['aabb']['min'] for r in rows]);highs=np.array([r['aabb']['max'] for r in rows]);fail=[];stacks=[]
    local=read(ROOT/'assets/props/worksite/site_office_stairs/stairs_route.json')['supported_path']
    for stair in (p for p in placements if p['prop_id']=='site_office_stairs'):
        angle=math.radians(stair['yaw_deg']);c,s=math.cos(angle),math.sin(angle);offset=np.array(stair['position']);supported=[]
        uppers=[p for p in placements if p['prop_id']=='site_office' and abs(p['position'][2]-offset[2]-2.8)<.001]
        upper=min(uppers,key=lambda p:math.dist(p['position'][:2],offset[:2]));delta=np.array(upper['position'])-offset
        upper_dx=delta[0]*c+delta[1]*s
        for n,(x,y,want,foot) in enumerate(local):
            # The northeast reference stack has an upperoffice shifted1.2m
            # west. Redirect only the flat landing/door portion of the route;
            # flight, turning pocket and their validated support lift stay put.
            if abs(upper_dx)>.001 and want>=2.8:
                if -3.0001<=x<=.0001 and -2.0401<=y<=-1.8199:x=-3+(x+3)*(upper_dx+3)/3
                elif abs(x)<.0001 and y>=-2.0401:x=upper_dx
            p=offset+np.array([x*c-y*s,x*s+y*c,foot]);p[2]=max(p[2],.008) if want==0 else p[2]
            mask=np.all(highs>=p+[-.32,-.32,0],axis=1)&np.all(lows<=p+[.32,.32,1.8],axis=1)
            for index in np.flatnonzero(mask):
                row=rows[index];gap=capsule_distance(row,p)-.32
                if gap<-.00006:fail.append(dict(stair=stair['id'],sample=n,position=p.tolist(),volume=row['name'],gap_m=gap))
            supported.append(p.tolist())
        stacks.append(dict(instance=stair['id'],samples=len(supported),upper_office_id=upper['id'],upper_office_local_x_offset_m=upper_dx,upper_office_reached=supported[-1][2]>=2.9,doors_tested_open=True,supported_path=supported))
    result=dict(passed=not fail,failures=fail[:40],checked_stacks=len(stacks),capsule_radius_m=.32,capsule_height_m=1.8,
        route_samples=sum(s['samples'] for s in stacks),fixed_and_instance_volumes=len(rows),stacks=stacks,
        inputs_sha256={n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in ('collision.json','placements.generated.json')})
    (HERE/'cabin_routes_QA.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('stacks','inputs_sha256')},indent=2));sys.exit(bool(fail))

if __name__=='__main__':main()
