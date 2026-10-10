# Supplied Kestrel OBJ — technical assessment

Input: `D:/downloads/base.obj`, 52,645,092 bytes. The original was read only.
The user reports that it came from a paid online AI service; the provider and
commercial-use terms have not been identified.

## Verdict

Useful as a **high-resolution Kestrel form/sculpt source**. The dressed
silhouette, collar, jacket folds, cargo trousers, boots and asymmetric hair
follow the concept substantially more closely than the current procedural
wardrobe. This is already a dressed character, not a bare anatomy template.

It is not a drop-in game mesh or a modular wardrobe base. The audit found:

- 249,976 vertices and **500,000 triangles**, all triangulated.
- One mesh, one connected component, zero boundary/nonmanifold edges.
- UVs and supplied normals on every face corner.
- No rig, skin weights, animation, material library or texture files provided.
- Raw vertical extent 1.898092 OBJ units. The inspection copy is normalized to
  1.70 m, soles at zero, Blender Z up and front -Y.

Watertightness helps source-surface baking but does not establish animation
topology. Hair, eyewear, costume and equipment are joined into the connected
surface. Their boundaries need reconstruction/separation for skins and motion.
Eyes/lens and hand/face deformation need particular inspection and cleanup.

## Production path

Preserve this as the source of shapes. Build a clean low-resolution target with
deliberate loops at face, fingers, shoulders, elbows, hips and knees; keep the
costume/hair/gear separated in the authoring master. Bake retained fine surface
detail into normal/AO maps. Bind to the existing character/skin rig and validate
actual deformation, rather than relying on a triangle reduction alone.

The supplied mesh is roughly ten times the preferred full-character triangle
budget, before animation/skin work. Aim for the project's 30–50k preferred target
and stay below the 70k hard limit for the complete dressed character.

`inspection.blend` is an editable, normalized clay inspection copy.
`inspection.json` records the measured structure. Renders are in `renders/`.
No current Kestrel export or game asset has been replaced by this assessment.
