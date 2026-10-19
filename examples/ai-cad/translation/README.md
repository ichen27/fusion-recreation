# Exact XYZ movement and downstream intersections

`translate` moves an earlier convex planar solid by signed parameter-backed XYZ offsets. It preserves dimensions, shape and volume, consumes the visible input and retains that input in editable history. Plane offsets and vertices are translated exactly, then the original boundary validator rechecks the result. Downstream planes use global coordinates; downstream intersections rebuild after a movement edit.

```json
{"op":"add_feature","feature":{"kind":"translate","id":"positioned","input":"stock","offset":["dx","dy","dz"]}}
```

Each offset references an existing parameter in mm and must be within ±1,000,000 mm. Fractions and negative values are supported. Fixed, derived and shared offset references retain normal parameter semantics. Computed boundary rationals are not restricted as new 128-bit user literals; existing boundary complexity limits still apply.

The browser offers **Move solid** on planar candidates and **Edit move** on the retained translation feature. Exact convexity is checked at preview. Blocks, convex sketch extrusions, cuts, intersections and earlier moves are supported. Circular, perforated and concave solids reject explicitly. This is translation, not rotation, assembly placement or a general transform system.

## Acceptance workflow

Create two 40×30×20 mm blocks. Move the second by (20,5,5) mm and intersect them: the common volume is 7500 mm³. Edit the retained move's X offset to 25: common volume becomes 5625 mm³. X=40 would leave only face contact, so preview rejects without saving. Undo restores the 7500 mm³ result.

```sh
python3 tools/ai-cad/verify_translation.py
# Optional after installing step-requirements.txt:
python3 tools/ai-cad/verify_translation_export.py
```

Use the [setup](../../../tools/ai-cad/README.md) and open a copy of a native checkpoint with `viewer.py --store`. The tests verify signed/fractional and million-mm offsets, translated face equations and vertices, invariant rational volume, compositional moves, world-space cuts, wide computed coefficients, stale/atomic history behavior and constrained browser offsets. MCP validation exercises typed preview and commit over the actual stdio transport.

## Artifacts

- `browser-recording.json`: twelve actual browser calls; display meshes and approximate volumes omitted. No inference run is claimed.
- `moved.cad.json`, `common.cad.json`, `edited.cad.json`, `undo.cad.json`: editable native history stages.
- `edited.stl`: actual browser download, verified closed topology, volume and world bounds (25,5,5) to (40,30,20) mm.
- `moved.step`, `common.step`, `edited.step`: reopened planar exports. `moved.step` contains only the translated body; the native moved stage retains both bodies.
- `step-comparison.json`: STEP vertex bounds and volume compared against independent positioned boxes and their Boolean intersection. Tolerance is 1e-8 mm for coordinates and 1e-6 mm³ for volume.
- `move-form.png`, `edited.png`, `contact-rejected.png`: actual browser authoring and failure evidence.

Generated boundary indices remain ephemeral. Body feature IDs and parameter references provide editable intent; translation does not introduce persistent face naming.
