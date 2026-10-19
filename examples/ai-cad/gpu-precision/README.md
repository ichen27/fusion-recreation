# Tiny parts far from the origin

A cylinder centered at (1000000, 1000000) mm has radius 0.001 mm and height 0.001 mm. Previewing height 0.0011 mm preserves its exact volume of 11π/10000000000 mm³. Previously, direct float32 GPU upload collapsed all X and Y samples to 1000000 and the viewer displayed no solid. The rounded volume label also read zero.

The CPU now subtracts the display-bounds center and normalizes in float64 before packing float32 vertices. The GPU receives small local coordinates; camera angles and zoom remain uniforms. Native model coordinates, exported coordinates and exact geometry are unchanged. Small nonzero area/volume labels use scientific notation, with exact values in the tooltip.

## Reproduce

Build the engine using [setup](../../../tools/ai-cad/README.md), then:

```sh
python3 tools/ai-cad/cad.py --store work/tiny.cad.json < examples/ai-cad/gpu-precision/create.json
python3 tools/ai-cad/viewer.py --store work/tiny.cad.json
node --test tools/ai-cad/test_display.mjs
```

In the viewer, change Height to `11/10000` and preview. `preview.json` contains the equivalent typed command. Do not commit if reproducing the included unchanged revision-1 snapshot.

## Artifacts and evidence

- `create.json`, `preview.json`: portable typed commands.
- `create.cad.json`: editable revision-1 native document.
- `before.png`, `after.png`: actual browser previews at the same dimensions, before and after the fix.
- `browser-validation.json`: actual GPU buffer bounds and unique-coordinate counts, 60-frame orbit report with renderer identity, and explicit context loss/recovery result. The old buffer has one unique X and Y; the corrected buffer has 33 of each. Camera orbit uploads zero bytes; context restoration rebuilds one local-coordinate buffer.

Node tests compare the translated tiny cylinder with the same shape at the origin, verify line/triangle packing and colors, and cover measurement formatting. HTTP tests load the new module through the actual viewer route. The browser evidence exercises the active shader and actual buffer uploads, not just the pure helper.

## Limits

This removes loss during float32 upload for a compact model at a large offset. It does not recover detail already lost by float64 tessellation, solve mixed-scale assemblies, guarantee arbitrary geometric precision or change export tolerances. The scene still uses one set of bounds. Timing is a synthetic browser workload, not a claim about physical-display latency or production-scale CAD performance.
