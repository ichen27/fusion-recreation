# Browser sketch to a sloped solid

**Historical recording:** the concavity rejection below describes the original capture. Simple concave stock is now supported by [exact decomposition](../concave-operations/README.md). The original recording and screenshot remain unchanged; replay explicitly checks the formerly rejected preview now succeeds with exact volume 295000/27 mm³ and still does not save.

A browser-created rectangle now works with the original exact plane-cut engine. `planar_profile` continues to store a simple polygon and its extrusion continues to use its existing analytic prism representation. When a plane cut consumes that extrusion, the engine verifies strict convexity using exact rational edge-side tests and constructs the planar boundary it needs. It does not convert circles or concave outlines into approximate convex solids.

The recorded browser workflow creates a 100×60 mm rectangle, extrudes it 20 mm, then keeps `x + z ≤ 100`. Its exact volume is 108000 mm³. Moving the upper-right sketch point from (100,60) to (80,60) rebuilds the downstream cut and gives 104000 mm³. Moving that point to (10,5) would make the outline concave, so preview rejects and the saved part stays unchanged. Undo restores the rectangular cut.

## Use and validate

Build with [setup](../../../tools/ai-cad/README.md), launch an empty workspace, choose **New sketch → solid**, **Start rectangle**, height 20, then preview/save. **Cut with plane** on the extrusion opens the plane editor. Use normal (1,0,1), offset 100. The sketch coordinates remain editable, with downstream cuts revalidated on every edit.

```sh
python3 tools/ai-cad/verify_sketch_plane.py
# Optional independent STEP comparison (requires step-requirements.txt):
python3 tools/ai-cad/verify_sketch_plane_export.py
```

Exact regression cases compare clockwise/counterclockwise rectangles and rational pentagons against the existing strict-convex representation. Tests cover upstream concavity rejection and explicit removal of the dependent cut before a valid concave edit. Circular/perforated inputs remain unsupported. The browser offers unperforated polygonal candidates; exact convexity is checked on preview.

## Artifacts

- `browser-recording.json`: eight actual browser calls; display meshes and approximate volumes omitted. No inference run is claimed.
- `sketch.cad.json`, `cut.cad.json`, `edited.cad.json`, `undo.cad.json`: complete editable native history.
- `edited.stl`: actual browser download; closed oriented topology, exact planar volume and half-space containment verified.
- `cut.step`, `edited.step`: usable planar STEP exports, independently reopened and checked for validity/volume.
- `step-comparison.json`: comparison with a separate OCCT box/half-space construction used only as a verification oracle. Error tolerance is 1e-6 mm³; observed errors are recorded.
- `cut-preview.png`, `edited.png`, `rejected-concavity.png`: actual browser evidence.

This closes an integration gap for convex sketch stock. It does not implement general nonconvex Booleans, arbitrary curved intersections or persistent naming of generated faces.
