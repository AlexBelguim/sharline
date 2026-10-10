"""Kestrel bob: fixed scalp with overlapping solid locks and cosmetic tip bones.

Original procedural hairstyle following Kestrel v06. All locks are opaque mesh
volumes, not alpha cards. Movement is authored as a small optional bone rig;
the game has to drive those bones for secondary motion.
"""
import math
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
import character_v2 as cv
import blender_common as bc

def smooth(a,b,x):
    t=max(0.,min(1.,(x-a)/(b-a)));return t*t*(3-2*t)

def _material():
    mat=bc.material('M_KES_HairPaint',(1,1,1),rough=.73)
    p=bc._principled(mat);bc._set_input(p,['Specular IOR Level','Specular'],.22)
    nt=mat.node_tree
    ca=nt.nodes.new('ShaderNodeVertexColor');ca.layer_name='HairPaint'
    nt.links.new(ca.outputs['Color'],p.inputs['Base Color'])
    normal=nt.nodes.new('ShaderNodeTexImage')
    normal.image=bpy.data.images.load(str(Path(__file__).parent/'textures/hair_normal.png'),check_existing=True)
    normal.image.colorspace_settings.name='Non-Color'
    nm=nt.nodes.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.22
    nt.links.new(normal.outputs['Color'],nm.inputs['Color']);nt.links.new(nm.outputs['Normal'],p.inputs['Normal'])
    orm=nt.nodes.new('ShaderNodeTexImage')
    orm.image=bpy.data.images.load(str(Path(__file__).parent/'textures/hair_orm.png'),check_existing=True)
    orm.image.colorspace_settings.name='Non-Color'
    split=nt.nodes.new('ShaderNodeSeparateColor');split.mode='RGB'
    nt.links.new(orm.outputs['Color'],split.inputs['Color']);nt.links.new(split.outputs['Green'],p.inputs['Roughness'])
    return mat

def _paint(ob,colors,uv):
    attr=ob.data.color_attributes.new(name='HairPaint',type='FLOAT_COLOR',domain='POINT')
    for dst,c in zip(attr.data,colors):dst.color=(*c,1.)
    ob.data.color_attributes.active_color=attr
    for poly in ob.data.polygons:
        us=[uv[ob.data.loops[li].vertex_index][0]for li in poly.loop_indices]
        seam=max(us)-min(us)>.5
        for li in poly.loop_indices:
            vi=ob.data.loops[li].vertex_index;u,v=uv[vi]
            ob.data.uv_layers.active.data[li].uv=(u+1 if seam and u<.5 else u,v)

def _cap(base,mat):
    n=64;rows=14;v=[];f=[];c=[];uv=[]
    for k in range(rows):
        q=.016+(1-.016)*k/(rows-1)
        for j in range(n):
            a=-math.pi+math.tau*j/n
            end=1.568+.087*max(0,math.cos(a))+.055*max(0,math.sin(a))
            z=1.713+(end-1.713)*q
            radius=math.sqrt(max(.003,1-((z-1.588)/.126)**2))
            x=.085*radius*math.sin(a);y=.004-.110*radius*math.cos(a)
            v.append((x,y,z));uv.append((j/n,q))
            # The small exposed part uses the same blue-black midtone as the
            # lock roots; a black foundation would read as separate plates.
            top=np.array((.019,.026,.048));hem=np.array((.009,.013,.025))
            shade=smooth(.30,.90,q)
            c.append((top*(1-shade)+hem*shade)*(.96+.04*math.cos(a*3)))
    for k in range(rows-1):
        for j in range(n):
            a=k*n+j;b=k*n+(j+1)%n;f.append((a,b,b+n,a+n))
    f.append(tuple(reversed(range(n))))
    # A shallow inner return gives the cap a real edge; the strands cover its hem.
    start=len(v)
    for j in range(n):
        p=Vector(v[(rows-1)*n+j]);p.x*=.96;p.y=(p.y-.004)*.96+.004;p.z+=.003
        v.append(tuple(p));uv.append((j/n,1.));c.append(np.array((.006,.009,.018)))
    for j in range(n):
        a=(rows-1)*n+j;b=(rows-1)*n+(j+1)%n;f.append((a,start+j,start+(j+1)%n,b))
    ob=cv.mesh('KES_HairScalp',v,f,mat);_paint(ob,c,uv);cv.rigid(ob,base,'head')
    ob['hair_role']='fixed scalp foundation';ob['secondary_motion']='none'
    return ob

def _cosmetic_rig(base):
    arm=base['armature'];bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True);bpy.context.view_layer.objects.active=arm;bpy.ops.object.mode_set(mode='EDIT')
    chains={
      'front_r':((-.057,-.102,1.617),(-.084,-.071,1.538),(-.083,-.039,1.451)),
      'side_r':((-.089,-.036,1.620),(-.096,-.019,1.542),(-.088,.013,1.472)),
      'back':((0,.108,1.645),(0,.112,1.578),(0,.101,1.508)),
    }
    for group,(a,b,c)in chains.items():
        previous=arm.data.edit_bones['head']
        for k,(p,q)in enumerate(((a,b),(b,c)),1):
            name=f'hair_{group}_{k:02d}'
            bone=arm.data.edit_bones.get(name)or arm.data.edit_bones.new(name)
            bone.head=Vector(p)*base['scale'];bone.tail=Vector(q)*base['scale']
            bone.parent=previous;bone.use_connect=k==2;bone.use_deform=True;bone.align_roll(Vector((0,-1,0)))
            previous=bone
    bpy.ops.object.mode_set(mode='OBJECT')
    for name in [b.name for b in arm.data.bones if b.name.startswith('hair_')]:
        arm.data.bones[name]['role']='cosmetic secondary motion'
        arm.data.bones[name]['max_suggested_angle_deg']=7.
    arm['body_core_bones']=61
    arm['hair_motion']='optional damped tip rotation; scalp and roots remain fixed'
    return chains

def _samples(path,widths,depths):
    controls=[Vector(path[0])]+[Vector(p)for p in path]+[Vector(path[-1])]
    ws=[widths[0]]+list(widths)+[widths[-1]]
    ds=[depths[0]]+list(depths)+[depths[-1]]
    result=[];count=6
    for i in range(1,len(controls)-2):
        a,b,c,d=controls[i-1:i+3]
        for j in range(count):
            t=j/count
            p=.5*(2*b+(c-a)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t)
            def profile(values):
                a,b,c,d=values[i-1:i+3]
                return max(.0006,.5*(2*b+(c-a)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t))
            result.append((p,profile(ws),profile(ds)))
    result.append((Vector(path[-1]),widths[-1],depths[-1]))
    return result

def _scalp_projection(p):
    # Use a complete smooth ellipsoid, avoiding nearest-point jumps at the
    # trimmed cap's forehead/ear hem when broad locks wrap around it.
    center=Vector((0,.004,1.588));d=p-center
    radius=math.sqrt((d.x/.085)**2+(d.y/.110)**2+(d.z/.126)**2)
    if radius<1e-5:return p.copy(),Vector((0,0,1))
    q=center+d/radius
    normal=Vector((q.x/(.085**2),(q.y-.004)/(.110**2),(q.z-1.588)/(.126**2))).normalized()
    return q,normal

def _lock(base,mat,name,path,widths,depths,group):
    stations=_samples(path,widths,depths);centers=[];normals=[]
    for i,(query,width,depth)in enumerate(stations):
        t=i/(len(stations)-1)
        hit,no=_scalp_projection(query)
        # The first part of every solid lock sinks into the cap. End lengths
        # use authored coordinates so the asymmetry and pointed bob stay clear.
        seat=smooth(1.520,1.690,query.z)
        root_embed=.004*(1-smooth(0.,.14,t))
        center=query.lerp(hit+no*(depth*.15-root_embed),seat)
        radial=Vector((center.x,center.y-.004,max(0,center.z-1.588))).normalized()
        normal=radial.lerp(no,seat).normalized()
        normals.append(normal);centers.append(center)
    v=[];f=[];colors=[];uv=[];weights=[];sides=12
    # A broad continuous crest, narrow rounded bevels, and a shallow closed
    # underside. This reads as a carved hair mass instead of an inflated leaf.
    section=((1,0),(.95,.43),(.66,.87),(.24,1),(-.24,1),(-.66,.87),
             (-.95,.43),(-1,0),(-.87,-.40),(-.30,-.50),(.30,-.50),(.87,-.40))
    for i,(p,no,(_,width,depth))in enumerate(zip(centers,normals,stations)):
        t=i/(len(centers)-1)
        tangent=(centers[min(i+1,len(centers)-1)]-centers[max(0,i-1)]).normalized()
        cross=tangent.cross(no).normalized();no=cross.cross(tangent).normalized()
        # Broad soft ridge and shallow side bevels, as solid overlapping strands.
        for j,(sx,sy)in enumerate(section):
            pt=p+cross*sx*width*.5+no*sy*depth*.5
            # Wrap the broad root and crown faces onto the scalp rather than
            # leaving tangent slabs floating above it. The solid end lengths
            # remain free below the ear for the cosmetic bend chains.
            stick=smooth(1.530,1.680,pt.z)
            if stick:
                hit,nrm=_scalp_projection(pt)
                root_embed=.004*(1-smooth(0.,.14,t))
                fitted=hit+nrm*(.0007+depth*(.12+.50*sy)-root_embed)
                pt=pt.lerp(fitted,stick)
            v.append(tuple(pt*base['scale']));uv.append((j/sides,t))
            facet=max(0,sy)
            dark=np.array((.010,.014,.027));light=np.array((.034,.046,.080))
            # Restrained broad highlights run with the sweep; neighboring
            # layers remain close in value so the coiffure reads as one mass.
            flow=.88+.12*math.sin(t*4.0+sum(ord(c)for c in name)*.013)
            painted=.55*facet*flow
            color=dark*(1-painted)+light*painted
            dye=1-smooth(1.486,1.552,pt.z) if min(a[2]for a in path)<1.57 else 0.
            color=color*(1-dye)+np.array((.007,.149,.139))*(.73+.27*facet)*dye
            colors.append(color)
            if group:
                bend=smooth(.33,.66,t)*.86
                tip=smooth(.61,.92,t)
                weights.append({'head':1-bend,f'hair_{group}_01':bend*(1-tip),f'hair_{group}_02':bend*tip})
            else:weights.append({'head':1.})
    for i in range(len(centers)-1):
        for j in range(sides):
            a=i*sides+j;b=i*sides+(j+1)%sides;f.append((a,b,b+sides,a+sides))
    f.extend((tuple(reversed(range(sides))),tuple(range((len(centers)-1)*sides,len(centers)*sides))))
    ob=cv.mesh('KES_HairLock_'+name,v,f,mat);_paint(ob,colors,uv)
    cv._write_weights(ob,base,weights)
    ob['hair_role']='solid overlapping sculpted lock'
    ob['motion_group']=group or'fixed'
    ob['root_binding']='head; cosmetic bend fades in beyond the root'
    return ob

def build(base):
    mat=_material();cap=_cap(base,mat);_cosmetic_rig(base)
    bpy.context.view_layer.update()
    specs=[
      # Broad roots overlap beneath the offset (+X) part. Each layer shares
      # the crown's sweep, then separates only along the asymmetric bob hem.
      ('FrontRight',[(.036,-.022,1.711),(-.012,-.088,1.690),(-.055,-.110,1.645),(-.081,-.107,1.580),(-.091,-.078,1.515),(-.086,-.056,1.472),(-.068,-.047,1.447)],
       [.044,.064,.057,.047,.037,.020,.0009],[.007,.012,.012,.011,.010,.006,.0007],'front_r'),
      ('SideRight',[(.028,-.022,1.713),(-.020,-.036,1.712),(-.071,-.055,1.671),(-.096,-.059,1.595),(-.106,-.032,1.522),(-.085,-.018,1.463)],
       [.048,.073,.067,.052,.036,.0010],[.007,.012,.012,.011,.008,.0007],'side_r'),
      ('RearRight',[(.028,.014,1.711),(-.022,.028,1.709),(-.074,.039,1.667),(-.103,.038,1.593),(-.109,.033,1.529),(-.092,.037,1.477)],
       [.048,.074,.068,.053,.030,.0010],[.007,.012,.012,.010,.007,.0007],'side_r'),
      ('BackRight',[(.028,.050,1.702),(-.023,.072,1.689),(-.069,.105,1.624),(-.083,.100,1.556),(-.069,.083,1.487)],
       [.042,.071,.062,.044,.0010],[.006,.011,.011,.008,.0007],'back'),
      ('BackCentre',[(.034,.047,1.703),(.017,.102,1.676),(-.008,.120,1.617),(-.020,.117,1.555),(-.010,.094,1.499)],
       [.047,.076,.067,.047,.0010],[.006,.011,.011,.008,.0007],'back'),
      ('BackLeft',[(.035,.031,1.708),(.068,.066,1.682),(.083,.098,1.629),(.087,.096,1.576),(.064,.079,1.537)],
       [.047,.063,.055,.039,.0010],[.006,.011,.010,.007,.0007],'back'),
      ('TempleLeft',[(.030,-.071,1.699),(.046,-.078,1.687),(.073,-.065,1.659),(.089,-.029,1.638),(.086,.023,1.621)],
       [.042,.055,.049,.028,.0008],[.006,.009,.008,.005,.0006],None),
      ('CrownLeft',[(.035,-.021,1.713),(.063,-.003,1.694),(.084,.024,1.658),(.092,.040,1.624),(.086,.055,1.602)],
       [.048,.056,.045,.029,.0008],[.006,.010,.009,.006,.0006],None),
    ]
    parts=[cap]
    for name,path,widths,depths,group in specs:
        parts.append(_lock(base,mat,name,path,widths,depths,group))
    return parts
