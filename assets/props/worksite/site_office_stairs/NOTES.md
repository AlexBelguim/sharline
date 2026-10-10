Original reusable external metal stair/landing attachment, authored for Showhome v3.

Mounting: place lower site_office and this attachment at exactly the same XYZ and yaw.
Place the upper site_office at local (0,0,2.8). Blender metres/Z-up/front -Y;
glTF converts to (x,z,-y). Deliberate pivot exception: attachment origin matches
the lower office ground-centre, not this asymmetric stair's base-bbox centre.

Flight: centre X -3.65, grade entry Y -7.00/Z 0, top Y -2.20/Z 2.80;
16 rises of 175 mm, 300 mm going, 15 elevated treads plus final landing.
The entry going is at grade. 1.20 m clear between 50 mm steel rails;
handrail is 1.05 m over the pitch line. Real 8 mm treads, riser plates,
downturned lips, paired structural stringers and yellow painted nosings.
Closed 80 mm inclined-prism collision smooths the flight without a jetpack.

Main landing X -4.40..0.60 / Y -2.70..-1.25 / top Z 2.80. Stair notch
X -4.30..-3.05 / Y -2.70..-2.20 leaves the final steps exposed. A west
turn pocket extends rearward to Y -0.98 beside the office, providing 1.22 m
clear turning depth. Main front strip has 1.292 m clear to the office skin.
Landing is 8 mm sheet_metal, with separate heavy beams, joists, columns,
braces and feet. Slim guardrails are metal_heavy; no railing closes the
stair mouth or the front doorway. The existing office floor is 100 mm
above its base: landing 2.80 m to upper finished floor 2.90 m is a normal
100 mm threshold step, checked in the capsule route.

QA: <=60 mm route samples, vertical support plus actual capsule-to-convex
face distance, radius 0.32 m / total height 1.8 m. The existing interactive
office leaf must be opened to enter; its original OPEN_DOOR hierarchy and
source GLB are preserved. See QA.json and stairs_route.json for measured
clearance, support lift, triangles and shared images.

Only existing painted v2 metal textures are used. UVs, repeat distances,
height_range_m and physics extras are retained; images are shared external
maps/showhome_v3/textures files. No new images, third-party meshes or game
code. GLB, LOD1, editable Blender source, collision and metadata included.

Rebuild: Blender -b --factory-startup -P
assets/maps/showhome_v3/extension/build_office_stairs.py -- --render
Renders are Cycles CPU: standalone.png, stack_alignment.png, stack_front.png.
Stacked-office context imports the two original GLBs without changing doors.
