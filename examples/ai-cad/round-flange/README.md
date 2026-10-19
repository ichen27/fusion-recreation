# Exact round flange

Circular stock of radius 40 and thickness 5 mm has a radius 10 center bore and two radius 3 mounting holes, each with a 10 mm center-to-edge margin. Growing stock radius to 50 moves the mounts from x=±30 to±40. Exact volume changes from 7410π to 11910π mm³.

## Run

Build using [setup](../../../tools/ai-cad/README.md), then use a new document:

```sh
python3 tools/ai-cad/cad.py --store work/flange.cad.json < examples/ai-cad/round-flange/create.json
python3 tools/ai-cad/cad.py --store work/flange.cad.json < examples/ai-cad/round-flange/grow.json
python3 tools/ai-cad/viewer.py --store work/flange.cad.json
python3 tools/ai-cad/verify_round_example.py
```

For interactive hole placement, use `stock.json` instead of create/grow, then **Add through-holes**. The stock is created through typed CLI/MCP; the viewer supports its dimension and hole edits.

## Artifact index

- `create.json`, `grow.json`: typed flange/relationship commands.
- `create.reply.json`, `grow.reply.json`: exact semantic results.
- `create.cad.json`, `grow.cad.json`: editable model/history stages.
- `flange.step`: grown flange with exact planar/cylindrical surfaces, without native history/relationships.
- `flange.stl`: grown flange, millimeters, 128 chords per circle. Maximum radial error≈0.0150591 mm and volume≈15.0244 mm³ below the exact material volume.
- `export-validation.json`: independent STEP surface/location/containment/volume and STL topology measurements.
- `stock.json`, `stock.cad.json`: separate browser starting stock, radius 40.
- `browser-recording.json`, `browser-create.cad.json`, `browser-edit.cad.json`: actual three-hole placement and bore-radius 10→12 edit; exact volumes 7410π→7190π. Disposable display meshes/approximate volume fields are omitted from the four captured replies. No AI inference run is claimed.
- `placement.png`, `browser-solid.png`: actual browser top view and saved solid.

`verify_round_example.py` replays both command and browser cases, verifies native snapshots/reopen and undo. With optional STEP dependencies, `verify_round_export.py` compares imported cylinders and empty/material regions against an independent cylinder-minus-three-cylinders oracle. Recorded volume differences are below 1.3e−9 mm³; CI permits 1e−6 across platforms. Oracle solid Booleans run only in verification; export translates the supplied boundary. Offset stock without holes and rejected sub-tolerance clearances are also checked.

## Limits

Axial stock and full-depth +Z holes only, 1..16 separate circles, no tangency/breakout. The exact model uses rational radii/centers and symbolic π volume. Display/STL inscribe circles; holes must fit safely inside the sampled outer boundary, so extremely narrow native gaps can refuse a given mesh resolution. STEP requires radius/height/clearances above 1e−6 mm and can refuse geometry below adapter precision. These are separate representation limits, not changes to the native model. General curved intersections, arbitrary-axis features, fillets and fabrication certification are not provided.

Round-stock tessellation tries the original angular samples and, only if validation fails, at most two deterministic phase offsets. This addresses collinear triangulation bridge triangles for aligned circles. Circle radii, centers, segment count and maximum chord-error bound stay unchanged; every candidate must pass containment, noncollapsed-triangle and opposite-edge-incidence checks. All six hole orders at 16/64/128 segments are covered for the radius 12 bore regression. Native geometry is never changed by this display retry.
