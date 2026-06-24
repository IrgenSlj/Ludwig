# Units standard

Every design declares real-world units up front; geometry is built to scale, never
"about right". Guessing scale is catastrophic for print/manufacture, not cosmetic.

- Default working unit for product-viz: **centimetres (cm)**.
- State the overall bounding size in the brief (e.g. "≈ 30 cm tall").
- 1 Blender unit = 1 metre unless the scene sets otherwise; scale meshes so a 30 cm
  object spans ~0.30 units, so lighting/camera distances read realistically.
- For manufacture/3D-print outputs, model in mm and keep wall thickness explicit.
