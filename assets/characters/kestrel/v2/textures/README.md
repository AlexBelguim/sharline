Kestrel garment and gear maps: 1024 px RGB PNG.
Albedo is sRGB; OpenGL tangent normals and ORM are linear Non-Color.
ORM channels: R ambient occlusion, G roughness, B metalness (zero).
Sources: existing Krea2 art/textures/fabric_ripstop, fabric_soft, leather_soft and worn_paint. No generated noise or new texture model art.
Broad painted marks are intrinsic dye/coating variation with a preserved STYLE_GUIDE mean palette, without baked directional lighting.
Matte ripstop/webbing, satin navy underlayer, soft leather and bone polymer have separate roughness responses; micro relief stays subtle.
Bake with ../make_surface_maps.py. Standard maps embed in the GLB.
This baker deliberately leaves all hair_* and rain_face* maps untouched.
