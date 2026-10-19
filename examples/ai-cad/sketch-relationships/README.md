# Directed horizontal and vertical sketch links

The browser creates a100×60×6 mm rectangle with four exact axis links. Changing two independent coordinates grows it to120×70 while opposite coordinates follow. Clearing the right edge's vertical link then moving its upper X to100 makes a trapezoid. A deliberate circular Y dependency rejects without saving.

## Repeat

Follow [setup](../../../tools/ai-cad/README.md), start a viewer with a new document, choose **New sketch → solid → Start rectangle**, and expand **Edge relationships**. Apply horizontal to v1→v2 and v3→v4, vertical to v2→v3 and v4→v1. Preview and save. Edit v2 X and v3 Y to resize. Linked coordinates remain locked; preview rebuilds their values.

Run `python3 tools/ai-cad/verify_sketch_relationships.py` to replay the actual browser recording and verify native state, preview immutability, cycle rejection, reopen and undo. `node --test tools/ai-cad/test_sketch.mjs` also checks exact command behavior through Rust, fixed/derived conflicts, preserving unrelated parameters, direct editing after unlinking, and removal of draft links when a point disappears.

## Artifact index

- `browser-recording.json`: seven actual browser requests and semantic replies: three preview/save pairs and a failed cycle preview. Disposable display meshes and approximate volumes are omitted. No new AI inference session is claimed.
- `create.cad.json`: four linked edges, revision1, volume36000 mm³.
- `resize.cad.json`:120×70×6, revision2, volume50400 mm³.
- `unlink.cad.json`: right upper X100 after explicit unlink, revision3, volume46200 mm³. Copy native files before editing them.
- `rectangle.png`, `unlinked.png`: actual saved solids and parameter displays.
- `cycle-rejected.png`: actual diagnostic showing the dependency cycle while retaining the draft.

## Limits

Horizontal means end Y follows start Y; vertical means end X follows start X. Direction matters. Links use the existing exact affine parameter system; this is not a general geometric sketch solver and does not establish full constraint, degrees of freedom, redundant-constraint tolerance, arbitrary-angle or nonlinear relationships. Conflicting links must be cleared explicitly. Shared references already linked require no extra relation. Fixed targets remain fixed. Derived coordinates update at preview, not during draft dragging.
