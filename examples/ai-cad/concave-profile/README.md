# Editable L-shaped mounting plate

The original Rust engine creates one simple concave outline with 20 mm legs, 80×60 mm overall extent, 5 mm thickness and two 6 mm diameter through-holes. Widening to 100 mm moves the right mounting hole from x=70 to x=90 while keeping its 10 mm edge margin. Exact volume changes from `12000 − 90π` to `14000 − 90π` mm³.

## Run

Build the Rust engine using [the setup instructions](../../../tools/ai-cad/README.md), then use a new document path:

```sh
python3 tools/ai-cad/cad.py --store work/l-plate.cad.json < examples/ai-cad/concave-profile/create.json
python3 tools/ai-cad/cad.py --store work/l-plate.cad.json < examples/ai-cad/concave-profile/widen.json
python3 tools/ai-cad/viewer.py --store work/l-plate.cad.json
python3 tools/ai-cad/verify_concave_example.py
```

## Artifact index

- `create.json`, `widen.json`: reproducible typed edit inputs.
- `*.reply.json`: exact engine results, including rational geometry and symbolic circular volume.
- `*.cad.json`: reopenable native documents with editable parameters, relationships and history. Copy before editing.
- `mount.step`: widened solid with planar/cylindrical surfaces; loses model history and constraints.
- `mount.stl`: widened solid in millimeters with 128 inscribed chords per circle; loses exact circles, history and constraints.
- `browser-recording.json`, `drawn.cad.json`, `edited.cad.json`: actual mouse-created concave outline and coordinate edits, with four captured preview/save calls; independently replayed by `verify_concave_example.py`. This separate no-hole UI case widens the vertical leg from 20 to 30 mm, volume 12000→14000 mm³.
- `sketch.png`, `drawn-solid.png`: actual browser sketch and edited solid.
- `export-validation.json`: measured export results and independent OCCT reference comparison.

Run `verify_concave_export.py` with the optional STEP dependencies to check saved artifacts, cylinder positions, empty notch/hole regions, material containment and volume. The oracle unions two boxes and subtracts cylinders only in verification. The exporter translates the Rust-supplied boundary without using solid Boolean operations. Both stages agree with the independent reference to within 4e−11 mm³ on the recorded machine; CI allows 1e−6 mm³ across platforms. STL maximum radial error is about 0.000904 mm; inscribed holes make its material volume about 0.113535 mm³ larger.

## Limits

This is a bounded straight-edge profile/prism family, not a general Boolean engine or fabrication certification. Profiles must form one simple loop; touching, collinear, repeated and crossing edges reject. Circles must have strictly positive clearance from finite boundary segments, including inward corners. Exact validation can accept gaps below the STEP adapter's 1e−6 mm threshold; export then refuses explicitly. Original convex profiles keep their original restrictions. New browser sketches permit inward corners.
