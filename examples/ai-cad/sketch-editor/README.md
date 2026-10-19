# Draw, extrude and edit in the browser

The browser can now create a solid without a CLI modeling command: place points in a sketch, preview the extrusion, then save. Existing convex polygon profiles can be edited by dragging points or entering exact coordinate values.

## Try it

Requires the normal Rust release build, Python 3.14, macOS/Linux and a WebGL 2 browser. From the repository root:

```sh
cargo +1.85.1 build --manifest-path crates/model-engine/Cargo.toml --release --locked
python3 tools/ai-cad/viewer.py --store work/drawing.cad.json
```

Open http://127.0.0.1:8765 and select **New sketch → solid**. Click around a convex outline or select **Start rectangle**. Dragging snaps to 1 mm; the coordinate fields accept integers or fractions such as `25/2`. Choose extrusion height, **Preview solid**, inspect the result and **Save edit**. Cancel/discard does not save. Undo/redo and the saved STL download use the existing document workflow.

Use **Edit sketch** on a profile to drag its existing vertices or change coordinate values. Fixed and derived coordinate parameters remain locked. Shared parameter references move together; derived coordinates refresh during the authoritative preview. To change a controlling parameter or relationship, use the dimension panel or existing CLI/MCP operations. A stale saved revision rejects preview/commit; close the editor, refresh, and replan explicitly.

New drawings support 3..16 points in one strictly convex loop. Existing profile topology is retained: no vertex insertion/removal in an existing feature yet. Crossings, concavity, repeated points and collinear corners reject without modifying the document. This is an interactive editor over the existing exact model, not a new general geometric constraint solver. SVG coordinates and the drag grid are interaction aids; Rust decides validity. No automatic geometric repair is performed.

## Actual browser artifacts

| File | Meaning |
|---|---|
| [browser-recording.json](browser-recording.json) | Four actual HTTP calls: create preview/commit and drag-edit preview/commit, including returned exact results |
| [create.cad.json](create.cad.json) | Native 100×60×6 mm rectangle drawn by four mouse point placements |
| [widen.cad.json](widen.cad.json) | Native document after dragging both right vertices to x=120 |
| [sketch.png](sketch.png) | Existing profile editor after the two drags |
| [solid.png](solid.png) | Saved 120×60×6 mm extrusion, volume 43200 mm³ |

Copy a `.cad.json` before opening it for edits. The example records human-style browser interactions, not new natural-language inference. Feature and parameter IDs remain stable during editing.

```sh
node --test tools/ai-cad/test_sketch.mjs
python3 tools/ai-cad/verify_sketch_recording.py
```

Four JavaScript integration tests generate the real typed commands and call the Rust executable: creation/editing, exact fractions, invalid geometry, fixed/derived/shared coordinates, preservation of relationships and limits/collisions. The recording replay checks exact outputs, preview isolation, reopened snapshots and undo. Existing 51 Python host/geometry/HTTP tests continue to pass. Browser checks include actual mouse placement/drag, field edits, save/reopen, and rejected crossing geometry with unchanged revision. This small workflow does not certify general usability or all pointer devices.
