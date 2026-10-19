# Exact quarter-turn rotations

Rotate convex planar parts by 90°, 180° or 270° about a global X/Y/Z axis through an exact parameter-backed pivot. The input remains in editable history and is consumed by the rotated result. Signed coordinate permutations preserve exact dimensions and volume; the original boundary validator checks the transformed result. This does not introduce arbitrary-angle approximation, curved transforms or assembly instances.

```json
{"kind":"rotate_quarter","id":"turn1","input":"stock","axis":"z","turns":1,"pivot":["px","py","pz"]}
```

Pivot coordinates are parameter references in mm, each within ±1,000,000 mm. Positive angles use the right-hand rule. Fixed, derived and shared references retain their existing semantics. Blocks, convex profile extrusions, plane cuts, intersections, translations and previous quarter turns are supported. Circular, perforated and concave inputs reject explicitly. Downstream planes stay in global coordinates.

## Verified workflow

Create two 40×20×10 mm blocks. Rotate the second 90° about Z through (20,10,0), then intersect: common volume is 4000 mm³. Change the retained rotation to 180°: common volume becomes 8000 mm³. Moving the pivot to X=100 leaves disjoint parts and rejects without saving. Undo restores the 90° intersection.

```sh
python3 tools/ai-cad/verify_rotation.py
# Optional with step-requirements.txt installed:
python3 tools/ai-cad/verify_rotation_export.py
```

Tests independently check all three axes and angles with fractional pivots, signed volume, transformed face equations, inverse rotations, constrained browser edits and atomic downstream failure. Typed MCP preview and commit run through the actual stdio transport. See [setup](../../../tools/ai-cad/README.md) to open a copy of a native checkpoint using `viewer.py --store`.

## Included artifacts

- `browser-recording.json`: twelve actual browser requests, excluding only display meshes/approximate volumes; no inference run is claimed.
- `turned.cad.json`, `common.cad.json`, `edited.cad.json`, `undo.cad.json`: editable native checkpoints with history.
- `edited.stl`: actual browser download; closed topology, 8000 mm³ volume and world bounds (0,0,0) to (40,20,10) verified.
- `turned.step`, `common.step`, `edited.step`: reopened solid exports. The first exports only the rotated body, while its native checkpoint retains both parts.
- `step-comparison.json`: independent positioned-box/Boolean oracle, volume agreement within 1e-6 mm³ and vertex bounds within 1e-8 mm. All three recorded volume differences are zero at displayed precision.
- `rotation-form.png`, `edited.png`, `disjoint-rejected.png`: actual browser evidence; form/error screenshots were refreshed after dialog styling was unified.

Body IDs retain intent. Generated boundary indices remain ephemeral; rotation does not add persistent face naming.

Subsequent support: [analytic rigid placement](../analytic-placement/README.md) now admits circular stock and through/blind-hole groups. Earlier curved-placement exclusions describe the original checkpoint.
