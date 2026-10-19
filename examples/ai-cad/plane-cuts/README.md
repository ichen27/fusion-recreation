# Repeated exact plane cuts

Start with a 60 mm cube. Keep `x + y + z ≤ 60`, then keep `−x ≤ −10` (x ≥ 10). The result is a tetrahedron with exact volume 62500/3 mm³. Editing the first plane to `x + y + z ≤ 54` rebuilds the second cut and yields 42592/3 mm³. An offset of 10 would leave only a point after the second cut and is rejected without changing the saved model.

The original Rust boundary kernel performs these cuts using rational arithmetic. OCCT is used only for explicit STEP boundary translation and independent verification.

## Run

Build using [setup](../../../tools/ai-cad/README.md), then use a new document:

```sh
python3 tools/ai-cad/cad.py --store work/planes.cad.json < examples/ai-cad/plane-cuts/create.json
python3 tools/ai-cad/cad.py --store work/planes.cad.json < examples/ai-cad/plane-cuts/resize.json
python3 tools/ai-cad/viewer.py --store work/planes.cad.json
python3 tools/ai-cad/verify_plane_example.py
```

For browser authoring, start with `stock.json`. Select **Cut with plane**, enter normal `(1,1,1)` and offset `60`, then preview/save. Select **Add next plane cut**, use normal `(-1,0,0)` and offset `-10`. **Edit plane** can change an earlier offset or its normal. The form explains the retained side; preview shows the result before saving. Camera orbit/zoom remains available.

Normal components are dimensionless rational literals. Offset references a length parameter, but it is **not perpendicular distance unless the normal has unit length**. Scaling the normal and offset by the same positive factor describes the same retained half-space. Changing their signs reverses the retained side.

## Artifact index

- `create.json`, `resize.json`, matching `.reply.json` and `.cad.json`: typed commands, exact output and editable native history.
- `stock.json`, `stock.cad.json`: browser starting cube.
- `browser-recording.json`: eight actual calls for two sequential cuts, upstream editing, rejected empty-solid preview and undo. Corresponding `browser-first/second/resize/undo.cad.json` files preserve the native stages. Reopen and redo are verified. No inference run is claimed.
- `plane-editor.png`, `browser-solid.png`, `rejected-cut.png`: actual editor, saved solid after camera zoom, and atomic-rejection feedback.
- `part.step`, `part.stl`: resized tetrahedron. STEP retains planes; STL has four triangles. Neither preserves feature history. STL coordinates use millimeters.
- `export-validation.json`: independent sequential half-space intersection volume, imported plane locations/normals, material/removed-region classification and STL closed-topology/volume checks. Recorded STEP volume differences are below 4.1e−10 mm³; CI permits 1e−6 across platforms.

## Limits

Convex planar solids only: blocks, strict convex profile extrusions, corner cuts and prior plane cuts. Circular/perforated stock and `planar_profile` extrusions are unsupported here. Each solid has at most one consuming feature; chain subsequent cuts through the previous result. No general union, nonconvex difference, curved intersection or persistent generated-face identity is claimed. Feature IDs and parameter references remain stable. Empty and lower-dimensional solids reject; unchanged/coplanar cuts are allowed. Existing document and exact-boundary size/bit limits still apply.
