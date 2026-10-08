// Foliage cards for Showhome (val_etf/src/foliage.rs): the leaf-cluster shell of the hedges. (The lawn grass is
// grass.wgsl.)
//
// A StandardMaterial extension. The vertex stage (main pass and prepass, so depth and motion vectors match)
// sways the cards in the wind, on the view's clock (globals.time: nothing is updated per frame on the CPU). The
// fragment stage is the standard PBR one plus a light wrap past the terminator and sun-through-leaves
// translucency, dimmed where the hedge stands in another object's shadow. The prepass fragment is
// StandardMaterial's (alpha mask from the base colour texture).
//
// Vertex data (see foliage.rs): POSITION, NORMAL (bent outward from the hedge's rounded volume), TANGENT,
// UV_0 (atlas), COLOR rgb = AO and tint, a = sway weight

#import bevy_pbr::{
    mesh_functions,
    mesh_view_bindings::view,
    view_transformations::position_world_to_clip,
}

#ifdef PREPASS_PIPELINE
#import bevy_pbr::prepass_io::{Vertex, VertexOutput}
#import bevy_render::globals::Globals
// The prepass view bind group carries the globals at binding 1 (bevy_pbr prepass/mod.rs); no bevy_pbr module
// declares them there.
@group(0) @binding(1) var<uniform> globals: Globals;
#else
#import bevy_pbr::{
    mesh_view_bindings::globals,
    forward_io::{Vertex, VertexOutput, FragmentOutput},
    pbr_fragment::pbr_input_from_standard_material,
    pbr_functions::{alpha_discard, apply_pbr_lighting, main_pass_post_lighting_processing},
    mesh_view_bindings::lights,
    mesh_view_types::DIRECTIONAL_LIGHT_FLAGS_SHADOWS_ENABLED_BIT,
    shadows::fetch_directional_shadow,
}
#endif

struct Foliage {
    // xyz: the direction the wind blows toward (world, horizontal, unit); w: unused (0)
    wind_dir: vec4<f32>,
    // x: sway amplitude (m), y: angular frequency (rad/s), z: wave number along the wind (rad/m), w: gust lean
    wind: vec4<f32>,
    // x: wrap, y: translucency, z: shadow probe distance toward the sun (0 = none), w: translucency exponent
    light: vec4<f32>,
}

@group(#{MATERIAL_BIND_GROUP}) @binding(100) var<uniform> foliage: Foliage;

const PI: f32 = 3.141592653589793;

// Wind displacement of a point (world) with a sway weight (0 = rooted, 1 = free tip) at time t.
fn wind_offset(p: vec3<f32>, weight: f32, t: f32) -> vec3<f32> {
    let dir = foliage.wind_dir.xyz;
    let side = vec3<f32>(-dir.z, 0.0, dir.x);
    let along = dot(p.xz, dir.xz);
    let w = foliage.wind.y;
    // A wave travelling downwind, broken up with a little per-place phase.
    let phase = along * foliage.wind.z + sin(p.x * 1.7 + p.z * 2.3) * 0.8;
    let gust = 0.65 + 0.35 * sin(t * 0.31 - along * 0.09);
    let push = sin(w * t - phase) * 0.75 + sin(w * 2.37 * t - phase * 1.9) * 0.25;
    let flutter = sin(w * 1.41 * t + phase * 2.7);
    let amount = dir * (push * gust + foliage.wind.w * gust) + side * flutter * 0.35;
    return amount * foliage.wind.x * weight;
}

struct Placed {
    world: vec3<f32>,
    previous: vec3<f32>,
    color: vec4<f32>,
}

// Where a vertex goes this frame and the last: swayed by the corner's weight.
fn place(local: vec3<f32>, world_from_local: mat4x4<f32>, color: vec4<f32>) -> Placed {
    var out: Placed;
    let base = mesh_functions::mesh_position_local_to_world(world_from_local, vec4<f32>(local, 1.0)).xyz;
    let weight = color.a;
    // This frame and the last (for motion vectors).
    out.world = base + wind_offset(base, weight, globals.time);
    out.previous = base + wind_offset(base, weight, globals.time - globals.delta_time);
    out.color = vec4<f32>(color.rgb, 1.0);
    return out;
}

@vertex
fn vertex(vertex: Vertex) -> VertexOutput {
    var out: VertexOutput;
    let world_from_local = mesh_functions::get_world_from_local(vertex.instance_index);

#ifdef VERTEX_COLORS
    let color_in = vertex.color;
#else
    let color_in = vec4<f32>(1.0);
#endif
    let placed = place(vertex.position, world_from_local, color_in);
    out.world_position = vec4<f32>(placed.world, 1.0);
    out.position = position_world_to_clip(placed.world);

#ifdef PREPASS_PIPELINE
#ifdef UNCLIPPED_DEPTH_ORTHO_EMULATION
    out.unclipped_depth = out.position.z;
    out.position.z = min(out.position.z, 1.0);
#endif
#ifdef MOTION_VECTOR_PREPASS
    out.previous_world_position = vec4<f32>(placed.previous, 1.0);
#endif
#ifdef NORMAL_PREPASS_OR_DEFERRED_PREPASS
#ifdef VERTEX_NORMALS
    out.world_normal = mesh_functions::mesh_normal_local_to_world(vertex.normal, vertex.instance_index);
#endif
#ifdef VERTEX_TANGENTS
    out.world_tangent = mesh_functions::mesh_tangent_local_to_world(
        world_from_local, vertex.tangent, vertex.instance_index);
#endif
#endif
#else   // PREPASS_PIPELINE
#ifdef VERTEX_NORMALS
    out.world_normal = mesh_functions::mesh_normal_local_to_world(vertex.normal, vertex.instance_index);
#endif
#ifdef VERTEX_TANGENTS
    out.world_tangent = mesh_functions::mesh_tangent_local_to_world(
        world_from_local, vertex.tangent, vertex.instance_index);
#endif
#endif  // PREPASS_PIPELINE

#ifdef VERTEX_UVS_A
    out.uv = vertex.uv;
#endif
#ifdef VERTEX_UVS_B
    out.uv_b = vertex.uv_b;
#endif
#ifdef VERTEX_COLORS
    out.color = placed.color;
#endif
#ifdef VERTEX_OUTPUT_INSTANCE_INDEX
    out.instance_index = vertex.instance_index;
#endif
#ifdef VISIBILITY_RANGE_DITHER
    out.visibility_range_dither = mesh_functions::get_visibility_range_dither_level(
        vertex.instance_index, world_from_local[3]);
#endif
    return out;
}

#ifndef PREPASS_PIPELINE
@fragment
fn fragment(in: VertexOutput, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    var pbr_input = pbr_input_from_standard_material(in, is_front);
    pbr_input.material.base_color = alpha_discard(pbr_input.material, pbr_input.material.base_color);

    let surface = pbr_input.world_position;
    let has_sun = lights.n_directional_lights > 0u;
    var L = vec3<f32>(0.0, 1.0, 0.0);
    if has_sun {
        L = lights.directional_lights[0].direction_to_light;
    }
    // Cards are lit as if they stood `probe` metres further toward the sun: out of the hedge, so its core and
    // the other cards never shadow a hedge card (no acne; the bent normals and the AO do the self-shading).
    // Houses and walls still shadow them. Only the sun's shadow depends on the position here (no point lights
    // on the map).
    let probe = foliage.light.z;
    if probe > 0.0 {
        pbr_input.world_position = vec4<f32>(surface.xyz + L * probe, 1.0);
    }

    var out: FragmentOutput;
    out.color = apply_pbr_lighting(pbr_input);

    let wrap = foliage.light.x;
    let translucency = foliage.light.y;
    if has_sun && (wrap > 0.0 || translucency > 0.0) {
        let sun_color = lights.directional_lights[0].color.rgb;
        let sun_flags = lights.directional_lights[0].flags;
        let N = pbr_input.N;
        let ndl = dot(N, L);
        // Light that a wrapped diffuse adds past plain Lambert (soft, volumetric terminator).
        let wrapped = max((ndl + wrap) / (1.0 + wrap), 0.0) - max(ndl, 0.0);
        // Looking toward the sun through the leaves.
        let back = pow(saturate(dot(-pbr_input.V, L)), foliage.light.w) * saturate(0.35 - ndl);
        var lit = 1.0;
        if (sun_flags & DIRECTIONAL_LIGHT_FLAGS_SHADOWS_ENABLED_BIT) != 0u {
            let view_z = dot(vec4<f32>(
                view.view_from_world[0].z,
                view.view_from_world[1].z,
                view.view_from_world[2].z,
                view.view_from_world[3].z
            ), pbr_input.world_position);
            lit = fetch_directional_shadow(0u, pbr_input.world_position, L, view_z, pbr_input.frag_coord.xy);
        }
        let diffuse = pbr_input.material.base_color.rgb * pbr_input.diffuse_occlusion / PI;
        let extra = diffuse * sun_color * (wrapped + back * translucency) * lit * view.exposure;
        out.color = vec4<f32>(out.color.rgb + extra, out.color.a);
    }

    pbr_input.world_position = surface;
    out.color = main_pass_post_lighting_processing(pbr_input, out.color);
    return out;
}
#endif
