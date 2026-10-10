# Local prop image batch

21 Qwen Image2.1 images, including12 bases,5 initial variants and4 refinements. No TRELLIS or3D jobs ran. `selection.json` lists the17 preferred inputs; original variants remain for comparison.

Vehicles include blue/clay hatchbacks, a rear view with the trunk open, ivory/sage vans, ivory/clay pickups, a semi tractor and a cement mixer. Household cabinets include a stationary kitchen cabinet and matching halfway-open drawer. Materials include a wheel-free pipe bundle, printed blocks and stacked boards; the compact excavator is a separate machine.

`manifest.json` records actual prompts, seeds, hashes, image dimensions and Comfy output names. `workflows/` contains the exact API graphs. `prompts/` contains plain text. All inference was local on port8188,1024square,25steps,CFG1,Euler/simple,without LoRAs.

Run `python assets/props/_concepts/local_batch_2026_10_10/generate_images.py` from the repo root to resume missing images; existing images and their provenance are preserved. It deliberately has no image-to-3D stage. These are input concepts, not game-ready models.
