## Problem

Your team's design system defines a categorical color palette for data visualizations. Before the next release, you must verify that every color pair in the palette remains distinguishable for users with color vision deficiencies (CVD). A previous accessibility audit flagged that some palettes passed informal "avoid red/green" checks but failed under rigorous simulation.

## Goal

Audit the palette defined in `/root/palette.json` for CVD safety. Simulate how each color appears under protanopia, deuteranopia, and tritanopia, then measure whether all color pairs remain distinguishable under every vision type.

## Inputs

- `/root/palette.json` — a JSON object with a `colors` array of hex color strings (e.g., `["#e64545", "#3b82f6", ...]`).

## Expected output

Write the audit results to `/root/audit_report.json` with this schema:

```json
{
  "palette_safe": [FILL: true or false],
  "min_delta_e": [FILL: number, the smallest pairwise deltaE_OK found across all vision types],
  "worst_pair": {
    "index_a": [FILL: integer],
    "index_b": [FILL: integer],
    "vision_type": [FILL: "normal", "protan", "deutan", or "tritan"]
  },
  "per_pair_results": [
    {
      "index_a": [FILL: integer],
      "index_b": [FILL: integer],
      "normal_delta_e": [FILL: number],
      "protan_delta_e": [FILL: number],
      "deutan_delta_e": [FILL: number],
      "tritan_delta_e": [FILL: number],
      "min_delta_e": [FILL: number],
      "pair_safe": [FILL: true or false]
    }
  ]
}
```

A pair is safe if its minimum deltaE_OK across all four vision types (normal, protan, deutan, tritan) is at least 0.09. The palette is safe only if every pair is safe.

## Constraints

- Simulation must use linearized RGB (sRGB piecewise decode), not gamma-encoded values.
- Use the standard published LMS transformation matrices for CVD simulation, not approximations or daltonization matrices that operate on encoded RGB.
- Distinguishability must be measured with deltaE in the OKLab perceptual color space, not Euclidean RGB distance.
- All three deficiency types must be checked — a palette that passes deuteranopia but fails protanopia is unsafe.
