# Edit an existing feature's structure

Starting with the two-hole L plate, the browser adds h3 at(10,10) with radius3, removes h1, then removes both remaining holes. Surviving IDs remain unchanged. Each edit previews and saves through Rust. The empty group is removed and the original extrusion becomes visible again. A separate explicit CLI cleanup removes nine unused hole parameters.

## Run and artifacts

Build the engine with [the setup instructions](../../../tools/ai-cad/README.md). Copy `base.cad.json` to a working path and run the viewer to repeat **Edit holes → place/remove → preview → save**. Run `python3 tools/ai-cad/verify_feature_edits.py` to reproduce and verify all stages.

- `base.cad.json`: two-hole L plate, revision3, exact volume `12000−125π` mm³.
- `add.cad.json`: new h3, revision4, volume `12000−170π`.
- `remove.cad.json`: h1 removed, h2/h3 unchanged, revision5, volume `12000−125π`.
- `clear.cad.json`: group removed, original extrusion restored, revision6, volume12000.
- `cleanup.json`, `cleanup.reply.json`, `cleanup.cad.json`: explicit removal of nine unused parameters, revision7.
- `browser-recording.json`: six actual browser requests and exact semantic replies. Disposable display meshes and approximate volume fields are omitted. No AI inference was run for this recording.
- `added-hole.png`: actual browser editor after adding h3.

The verifier compares every native snapshot, verifies preview immutability, reopens the final document, and undoes cleanup/group removal to recover h2/h3. Tests exercise profile replacement with dependent extrusion/holes, missing and forward references, same-ID/kind enforcement, explicit parameter cleanup, constraints, retry receipts, failure atomicity, undo/redo and actual typed MCP transport.

## Semantics and limits

`replace_feature` keeps the feature's ID, kind and timeline position; the caller supplies the full definition and retains surviving vertex/hole IDs. `remove_feature` never cascades: remove or repair dependents explicitly in the same batch. `remove_parameter` never silently deletes a fixed constraint or relation; release/remove them first, and leave no unresolved uses. The original saved state survives every rejected edit.

The browser retains unused parameters after deleting holes to avoid destroying shared references or design intent; CLI/MCP cleanup is explicit. New holes use fresh parameter IDs even when a removed hole's parameters still exist. Emptying a new unsaved group is a no-op and cannot be previewed; emptying an existing group previews removal. Feature reordering, general topology naming, arbitrary body booleans and full geometric constraints remain outside this milestone.
