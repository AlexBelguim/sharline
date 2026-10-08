// Player bodies (val_etf/src/render/friend_foe.rs): a StandardMaterial extension that adds a soft fresnel rim in
// the ally colour on a teammate's body (art/DIRECTION_LOG.md item 17). Everyone else's body has strength 0 and
// draws exactly as a plain StandardMaterial: no glow, no colour tell.
//
// The rim is emissive light on the body's own surface, so it is depth tested like the body: a wall in front of a
// teammate hides it (no silhouette through walls). Only the main pass is replaced; the prepass is
// StandardMaterial's.

#import bevy_pbr::{
    forward_io::{VertexOutput, FragmentOutput},
    pbr_fragment::pbr_input_from_standard_material,
    pbr_functions::{alpha_discard, apply_pbr_lighting, main_pass_post_lighting_processing},
}

struct Rim {
    // rgb: the ally colour (linear), a: strength at the edge (0 = no glow)
    color: vec4<f32>,
    // x: fresnel exponent, y: wash over the whole body (share of the edge's glow), zw: unused
    shape: vec4<f32>,
}

@group(#{MATERIAL_BIND_GROUP}) @binding(100) var<uniform> rim: Rim;

@fragment
fn fragment(in: VertexOutput, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    var pbr_input = pbr_input_from_standard_material(in, is_front);
    pbr_input.material.base_color = alpha_discard(pbr_input.material, pbr_input.material.base_color);

    if rim.color.a > 0.0 {
        // 1 where the surface turns away from the eye (the silhouette's edge), 0 facing it.
        let facing = saturate(dot(pbr_input.N, pbr_input.V));
        let edge = pow(1.0 - facing, rim.shape.x);
        let glow = rim.color.rgb * rim.color.a * (edge + rim.shape.y);
        pbr_input.material.emissive = vec4<f32>(pbr_input.material.emissive.rgb + glow, pbr_input.material.emissive.a);
    }

    var out: FragmentOutput;
    out.color = apply_pbr_lighting(pbr_input);
    out.color = main_pass_post_lighting_processing(pbr_input, out.color);
    return out;
}
