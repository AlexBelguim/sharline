"""Shared Showhome look development: the brief's frame, light and distance fog."""
import math
import os
import bpy
from mathutils import Vector


def linear(c):
    return tuple(v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in c)


def sun_direction(azimuth=188, elevation=54):
    """Direction toward the sun. Compass azimuth: north=0, east=90, south=180."""
    a, e = math.radians(azimuth), math.radians(elevation)
    return Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))


def setup(quick=False, sky=None, fog=True):
    sc = bpy.context.scene
    world = bpy.data.worlds.new('_ShowhomeLateAfternoon')
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputWorld')
    bg = nt.nodes.new('ShaderNodeBackground')
    bg.inputs['Strength'].default_value = .65
    if sky and os.path.exists(sky):
        tex = nt.nodes.new('ShaderNodeTexEnvironment')
        tex.image = bpy.data.images.load(sky, check_existing=True)
        nt.links.new(tex.outputs['Color'], bg.inputs['Color'])
    else:
        tc = nt.nodes.new('ShaderNodeTexCoord')
        sep = nt.nodes.new('ShaderNodeSeparateXYZ')
        nt.links.new(tc.outputs['Normal'], sep.inputs[0])
        ramp = nt.nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].position = 0
        ramp.color_ramp.elements[0].color = (*linear((.83,.80,.75)),1)
        ramp.color_ramp.elements[1].position = .8
        ramp.color_ramp.elements[1].color = (*linear((.48,.65,.80)),1)
        nt.links.new(sep.outputs['Z'], ramp.inputs[0])
        nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
    nt.links.new(bg.outputs[0], out.inputs[0])
    sc.world = world
    light = bpy.data.lights.new('_ShowhomeSun','SUN')
    light.energy = 2.5
    light.color = (1,.84,.66)
    light.angle = math.radians(2)
    sun = bpy.data.objects.new('_ShowhomeSun',light)
    sc.collection.objects.link(sun)
    sun.rotation_euler = (-sun_direction()).to_track_quat('-Z','Y').to_euler()
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 12 if quick else 32
    sc.cycles.use_denoising = True
    sc.cycles.device = 'CPU'
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'OPTIX'
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type != 'CPU'
        if any(d.use for d in prefs.devices):
            sc.cycles.device = 'GPU'
    except Exception:
        pass
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Medium Low Contrast'
    sc.render.image_settings.file_format = 'PNG'
    sc.render.film_transparent = False
    cam = bpy.data.objects.new('_ShowhomeCamera',bpy.data.cameras.new('_ShowhomeCamera'))
    sc.collection.objects.link(cam)
    cam.data.clip_start, cam.data.clip_end = .03, 2500
    sc.camera = cam
    if fog:
        world.mist_settings.start = 80
        world.mist_settings.depth = 340
        world.mist_settings.falloff = 'LINEAR'
        sc.view_layers[0].use_pass_mist = True
        sc.view_layers[0].use_pass_z = True
        # Blender 5.2 owns compositing through a node group, rather than Scene.node_tree.
        group = bpy.data.node_groups.new('_ShowhomeDistanceFog','CompositorNodeTree')
        group.interface.new_socket(name='Image', in_out='OUTPUT',socket_type='NodeSocketColor')
        n = group.nodes
        layers = n.new('CompositorNodeRLayers')
        geometry = n.new('ShaderNodeMath')
        geometry.operation = 'LESS_THAN'
        geometry.inputs[1].default_value = 5000
        group.links.new(layers.outputs['Depth'], geometry.inputs[0])
        amount = n.new('ShaderNodeMath')
        amount.operation = 'MULTIPLY'
        group.links.new(layers.outputs['Mist'], amount.inputs[0])
        group.links.new(geometry.outputs[0], amount.inputs[1])
        mix = n.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MIX'
        mix.inputs[7].default_value = (*linear((.66,.76,.86)),1)
        group.links.new(amount.outputs[0],mix.inputs[0])
        group.links.new(layers.outputs['Image'],mix.inputs[6])
        output = n.new('NodeGroupOutput')
        group.links.new(mix.outputs[2],output.inputs['Image'])
        if hasattr(sc,'compositing_node_group'):
            sc.compositing_node_group = group
        else:
            sc.use_nodes = True
            sc.node_tree.nodes.clear()
            wrapper = sc.node_tree.nodes.new('CompositorNodeGroup')
            wrapper.node_tree = group
            final = sc.node_tree.nodes.new('CompositorNodeComposite')
            sc.node_tree.links.new(wrapper.outputs['Image'],final.inputs['Image'])
    return cam, sun


def render(cam, path, location, target, lens=24, resolution=(1280,720), ortho=None):
    cam.location = location
    cam.rotation_euler = (Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.type = 'ORTHO' if ortho else 'PERSP'
    if ortho:
        cam.data.ortho_scale = ortho
    cam.data.lens = lens
    sc = bpy.context.scene
    sc.render.resolution_x,sc.render.resolution_y = resolution
    sc.render.resolution_percentage = 100
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
