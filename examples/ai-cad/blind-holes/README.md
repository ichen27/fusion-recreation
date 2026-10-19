# Flat-bottom blind holes

A radius-40 mm disk, 5 mm thick, receives a radius-10 center pocket and two radius-3 mounting pockets at x=±30 mm. All start at the top face. Increasing depth from 2 to 4 mm changes the remaining floor from 3 to 1 mm and the exact volume from 7764π to 7528π mm³. Depth 5 is rejected because a blind hole must leave material beneath it.

## Run

Build with [setup](../../../tools/ai-cad/README.md), then use a new document:

```sh
python3 tools/ai-cad/cad.py --store work/blind.cad.json < examples/ai-cad/blind-holes/create.json
python3 tools/ai-cad/cad.py --store work/blind.cad.json < examples/ai-cad/blind-holes/deeper.json
python3 tools/ai-cad/viewer.py --store work/blind.cad.json
python3 tools/ai-cad/verify_blind_example.py
```

For browser authoring, start with [plain circular stock](../round-flange/stock.json), select **Add holes**, choose **Blind · flat bottom**, set depth, and place circles. Preview checks the complete model. Existing hole groups retain their kind; remove/recreate explicitly to change from through to blind. Shared, fixed and derived depth parameters retain their semantics.

## Artifact index

- `create.json`, `deeper.json`: typed exact commands; corresponding `.reply.json` and `.cad.json` files contain results and editable native stages.
- `part.step`: deeper part with cylindrical walls and planar pocket floors. Native history/relationships are not retained in STEP.
- `part.stl`: deeper part, millimeters, 128 chords per circle; maximum radial error ≈0.0120473 mm, volume ≈9.49655 mm³ below exact material volume.
- `export-validation.json`: independent STEP surface/floor/volume and STL topology measurements.
- `browser-recording.json`: six actual calls across two browser sessions: create preview/save, deeper preview/save, rejected full-depth preview, and undo. Disposable display meshes/approximate volume fields are omitted. No AI inference run is claimed.
- `browser-create.cad.json`, `browser-deeper.cad.json`, `browser-undo.cad.json`: corresponding editable stages, verified by replay and reopen.
- `placement.png`, `browser-solid.png`, `rejected-depth.png`: actual editor, saved part and invalid-depth feedback.

`verify_blind_example.py` replays native and browser cases and verifies redo. With optional STEP dependencies, `verify_blind_export.py` compares rectangular and round stock against independent box/cylinder-minus-cylinder solids, verifies cylinder locations/radii, counts pocket floor planes, and checks material below each floor and empty space above it. Recorded volume differences are below 8e−10 mm³; CI permits 1e−6 across platforms. Solid Booleans occur only in this verification oracle. The export adapter translates the supplied faces and walls.

## Limits

One group of 1–16 separate cylindrical holes per stock, one depth per group, flat bottoms and the existing +Z stock orientation. No drill tips, counterbores, overlapping pockets, arbitrary axes or mixed-depth groups. Native depth and remaining floor are exact positive rationals. Float tessellation can refuse collapsed depth/floor; STEP requires both above 1e−6 mm. Neither failure changes the exact native document. These models are not fabrication certification.
