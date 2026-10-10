# Showhome painted sky

Model: krea2_turbo_fp8_scaled.safetensors via tools/comfy_gen.py.
Seed: 260084; steps: 8; no LoRA for text-to-image; port 8188.
Native source: 4096 x 2048; final panorama: 4096 x 2048.

Prompt:

Full spherical equirectangular panorama of only a calm painted late afternoon sky, horizontal 2 to 1 panorama. Warm pale cream peach horizon gently fading to a soft muted blue zenith. A few broad soft cumulus clouds, simple hand-painted shapes and broad very subtle brush patches, cream sun-facing edges and lavender shadow undersides, stylized game concept painting, clean low contrast colour, balanced even sky, no photographic grain. No sun disc, no land, no buildings, no birds, no aircraft, no objects, no letters, no words. Lower hemisphere is plain blue grey ground haze. The left and right ends continue the same horizon.

Processing: 192 px periodic end blend, softened zenith pole, lower hemisphere exact fog sRGB (.66,.76,.86). No sun disc.

Face order: +X,-X,+Y,-Y,+Z,-Z; glTF/Bevy Y up. +X=east,-X=west,+Y=zenith,-Y=nadir,+Z=south,-Z=north. Each face uses cube sampling vectors documented in build_sky.py. Panorama centre U=.5 is north; longitude increases toward east.

Skybox strip: 1024 x 6144 RGB PNG; reinterpret as a six-layer cube, not a 2D stretched texture. Irradiance strip: 256 x 1536, panorama-blurred before cube sampling. Suggested Skybox brightness 700 cd/m2 initially; calibrate to the game exposure.
