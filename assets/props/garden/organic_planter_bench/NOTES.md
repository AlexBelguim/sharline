Original reusable organic planter with integrated curved dark timber benches.
Metres/Z-up/front -Y. Base-bounding-box-centre pivot at Z=0; exact bounds and
local foliage volumes are in metadata.json. Place at courtyard grade; yaw 0
puts the long axis along X, with the longest seat on the front/south side.

The original kidney outline is procedural and is not traced third-party mesh
geometry. References inform the sweeping shape, cream print and dark timber
style only. Wall is 220 mm concrete plus 9 mm actual printed bead relief at
40 mm pitch. Coping has a real 17-18 mm chamfer. Convex wall segments follow
the maximum bead envelope; the small print grooves are visual surface detail.
The soil inset is 120 mm below coping and has exact convex decomposition.

Two curving timber seat runs have actual separated slats, 45 mm thickness,
508 mm seat depth and 450 mm top height. Their printed concrete bases are
integrated into the outside wall at 405 mm top height. Exact convex segment
collision preserves the hollow planter and open space around the benches.

Existing painted v2 printed-concrete, concrete, dark wood and soil materials,
UVs, height metadata and external shared images; no new image or leaf cards.
foliage.json supplies conservative local GREENFOL proxy volumes for the
existing game leaf system. They are not baked into the asset GLBs or source
Blender scene. foliage_preview.png shows only coarse runtime volume proxies.

Rebuild: Blender -b --factory-startup -P
assets/maps/showhome_v3/extension/build_organic_planter.py -- --render
LOD1 retains the original curve and seat slats, with smooth wall courses.
