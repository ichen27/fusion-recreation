# Exact convex solid intersection

`intersection` keeps the common positive volume of two distinct earlier convex planar solids. Both input features remain editable in history; the visible result replaces both inputs. The original Rust kernel intersects their exact half-spaces and validates every intermediate boundary. There is no external modeling fallback.

The browser offers **Intersect two solids** when at least two unperforated planar candidates exist. Preview performs authoritative convexity/volume checks. Save is one undoable edit. The typed feature is also available through existing MCP preview/commit tools:

```json
{"op":"add_feature","feature":{"kind":"intersection","id":"common","left":"stock","right":"tool"}}
```

Inputs can be blocks, convex profile extrusions, previous plane/corner cuts or previous intersections. Circular, perforated and concave inputs reject. Identical geometry under two distinct feature IDs is valid. Disjoint inputs, or contact at only a face/edge/point, return `empty_solid`. Each solid can have only one consuming feature; subsequent operations reference the result. This is intersection only: union and difference are not implemented here.

## Browser acceptance workflow

Starting empty, create a 40×40×20 mm block. Draw a triangle with vertices (0,0), (60,0), (0,60) and extrude it 30 mm. Intersect the two solids: exact volume is 28000 mm³. Change the triangle's two 60 mm coordinates to 50: the common volume becomes 23000 mm³. Changing both to -60 would leave only touching geometry; preview rejects and preserves the saved result. Undo restores the larger intersection.

```sh
python3 tools/ai-cad/verify_intersection.py
# Optional, after installing step-requirements.txt:
python3 tools/ai-cad/verify_intersection_export.py
```

The tests also cover 25 seeded offset-box pairs in both operand orders, exact rational overlap volumes, identical/contained solids, 1e-12 mm³ positive overlap, contact, invalid/consumed references, upstream atomic rejection and chained intersections of oblique boundaries. MCP verification exercises the real typed transport. GPU display and STL remain approximate representations of exact native geometry.

## Artifacts

- `browser-recording.json`: ten actual browser preview/commit/undo calls, with display meshes/approximate volume omitted. No inference run is claimed.
- `inputs.cad.json`, `common.cad.json`, `edited.cad.json`, `undo.cad.json`: editable native history checkpoints. Open a copy with `viewer.py --store` after [setup](../../../tools/ai-cad/README.md).
- `edited.stl`: actual browser download; closed oriented topology, volume and containment audited.
- `common.step`, `edited.step`: validated planar STEP exports.
- `step-comparison.json`: reopened STEP comparison with an independently constructed OCCT box/triangular-prism Boolean, used only as an oracle. Observed differences are below 4e-12 mm³; CI tolerance is 1e-6 mm³.
- `choose-solids.png`, `preview.png`, `empty-rejected.png`: actual browser selection, preview and rejection.

The boundary kernel's existing vertex/edge/face and rational-complexity bounds still apply. Full nonconvex Booleans, disconnected results, curved intersections and persistent generated-face naming remain open.
