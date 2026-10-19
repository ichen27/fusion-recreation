# Editable mounting bracket

A **flat rectangular mounting plate**, 100 × 60 × 6 mm, with three 6 mm diameter through-holes. Widening to 120 mm moves the right hole from x=88 to 108 and the upper hole from x=50 to 60. The left hole stays at (12,12); the upper hole stays 12 mm below the top. Thickness, hole radius and margin are fixed. This is not a bent angle bracket, a strength calculation or a fabrication certification.

## Run from the repository root

Requires Rust 1.85.1, Python 3.14 and a WebGL 2 browser; macOS/Linux.

```sh
cargo +1.85.1 build --manifest-path crates/model-engine/Cargo.toml --release --locked
mkdir -p work
python3 tools/ai-cad/cad.py --store work/bracket.cad.json < examples/ai-cad/bracket/create.json
python3 tools/ai-cad/cad.py --store work/bracket.cad.json < examples/ai-cad/bracket/widen.json
python3 tools/ai-cad/viewer.py --store work/bracket.cad.json
```

Open http://127.0.0.1:8765. Edit Width, preview, save, undo/redo or download the saved STL. CLI/MCP creates features; the browser currently edits dimensions. The existing MCP tools now accept `through_holes`; restart clients to reload their schema. The typed MCP test covers the new feature; the earlier recorded natural-language conversation is a separate block/corner workflow.

```sh
python3 tools/ai-cad/exports.py --store work/bracket.cad.json --revision 2 --body bracket --format stl --output work/bracket.stl
python3 tools/ai-cad/verify_bracket_example.py
```

Exports refuse existing output files and stale revisions. Select a new output path to repeat. Exported geometry has no feature history; keep the `.cad.json` document for editing. STL does not standardize units: import these files as **millimeters**.

For optional STEP translation, create a separate Python environment and install the pinned comparison dependencies:

```sh
python3 -m venv .step-env
.step-env/bin/python -m pip install -r tools/ai-cad/step-requirements.txt
.step-env/bin/python tools/ai-cad/exports.py --store work/bracket.cad.json --revision 2 --body bracket --format step --output work/bracket.step
.step-env/bin/python tools/ai-cad/verify_step_export.py
```

OCCT translates the supplied analytic faces and reads the STEP back. It does not perform modeling booleans in the exporter. The separate verifier deliberately constructs an independent OCCT subtraction reference. STEP conversion has a 1e-7 mm sewing tolerance and requires hole clearances, radii and height above 1e-6 mm. Exact model validity does not guarantee export at all scales.

## Delivered artifacts

| File | Use |
|---|---|
| [create.json](create.json), [widen.json](widen.json) | Replayable typed commands |
| [create.cad.json](create.cad.json), [widen.cad.json](widen.cad.json) | Native editable snapshots, history and receipts; copy before editing |
| [create.reply.json](create.reply.json), [widen.reply.json](widen.reply.json) | Exact parameters, analytic circular holes and symbolic volume |
| [bracket.step](bracket.step) | Widened solid with analytic cylindrical surfaces, millimeters; open in a STEP-capable CAD tool |
| [bracket.stl](bracket.stl) | Widened triangulated solid; open in a mesh viewer/slicer using millimeters |
| [export-validation.json](export-validation.json) | Measured round-trip and independent-reference evidence |
| [viewer.png](viewer.png) | Verified browser view of widened bracket |

Widened volume is **43200 − 162π mm³**, approximately **42691.0619901185 mm³**. The 128-segment STL has 1560 triangles and volume 42691.2663525733 mm³. Its inscribed hole chords deviate radially by at most **0.000903544 mm**, excluding floating-point rounding; solid volume is slightly larger because the polygonal holes are smaller than the circles. The saved model and STEP retain circles.

[Geometry contract and limits](../../../docs/analytic-bracket-validation.md). These checked-in deliverables are versioned with source; regeneration supplements them.
