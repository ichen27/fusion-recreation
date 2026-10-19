# Select a solid without uploading geometry again

Click a visible surface or use **Select solid** in the feature list. The selected body is highlighted and its stable feature ID and exact native volume appear in the side panel. Empty-background clicks and **Clear selection** clear it. Dragging orbits without changing selection. The feature-list buttons support keyboard access.

Picking runs on the CPU against the retained float32 display triangles, using the viewport's current projection and frontmost depth. Highlighting uses a shader uniform for each body's retained draw ranges. It does not rebuild, tessellate, save or re-upload the model. Selection persists while the same terminal feature exists; undoing a feature that was selected clears it. Graphics-context recovery rebuilds the buffer once and restores the highlight.

This is body selection on an approximate display mesh, not exact face/edge picking, snapping or persistent generated-topology naming. Near coincident/edge pixels may be ambiguous; coplanar ties follow stable draw order. Native modeling continues to use exact feature references.

## Reproduce

Build and launch the [two-part editable fixture](../browser-stock/final.cad.json) with the [viewer setup](../../../tools/ai-cad/README.md). Click the planar part and circular part, clear selection, then orbit with a part selected. `inspect-picking.js` can be evaluated in the browser to measure the current display and a synthetic 65,536-triangle workload. It reads the actual retained GPU buffer; its timing loop measures CPU picking only. Evaluate `instrument-selection.js` once after loading, then call `window.__recordSelection("action description")` after each interaction to capture selection/upload rows; performance is hardware-dependent, not a CI threshold.

Run `node --test tools/ai-cad/test_picking.mjs` for frontmost-depth, coplanar tie, background/hole, degenerate/clipped triangle and 54 orbit/aspect/zoom combinations on tiny offset geometry.

## Artifacts and measurements

- `before.png`, `plane-selected.png`, `round-selected.png`, `restored.png`: actual browser selection and graphics-context recovery.
- `measurements.json`: actual Apple M4 browser results. The 520-triangle/two-body scene measured 0.1 ms median and 0.3 ms p95 CPU picking; the synthetic 65,536-triangle/32-body workload measured 2.7 ms median and 3.3 ms p95.
- `inspect-picking.js`, `instrument-selection.js`: editable browser measurement and upload/selection instrumentation sources.
- [Native input](../browser-stock/final.cad.json): retains the exact model, parameters and history used for the run.

Actual selection, clear, list selection and orbit generated zero buffer uploads. Restoring a lost context generated one upload and retained the selected ID. The working native file remained byte-identical through these interactions. A subsequent explicit Undo removed the selected hole feature, cleared selection and uploaded the changed model once; Redo restored that model. No new inference run is claimed.
