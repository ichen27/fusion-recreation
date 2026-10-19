# Viewport fit across orientations and window shapes

The previous fit used only the longest world-axis extent and did not account for narrow viewports. A valid angled tetrahedron at zoom 1 projected to x = −1.223 in a narrow window, beyond the visible clip boundary at −1.

The display now uses a containing sphere with a 15% radius margin and scales zoom by the smaller viewport dimension. Fit view restores zoom 1 while retaining the current orientation. Orbit, fit and window resize update uniforms and reuse the existing vertex buffer. User zoom can intentionally move outside the fitted bounds.

## Evidence and artifacts

- [Editable input and commands](../plane-cuts/README.md): use `resize.cad.json` or replay the create/resize commands. No document change is needed to reproduce camera behavior.
- `before.png`, `after.png`: actual wide-window views at default zoom.
- `before-narrow.png`, `narrow.png`: actual narrow-window comparison; the old model is clipped horizontally, the new model fits.
- `browser-validation.json`: actual GPU buffer positions and active camera uniforms projected with the shader's transform. Narrow X range changes from [−1.223, 0.167] to [−0.703, 0.096]. Fit after zooming and viewport resize each cause zero vertex-buffer uploads.
- `inspect-view.js`: read-only browser-console probe used to collect projected bounds. Optional `window.__uploads` is supplied by the test harness's bufferData counter.

Run `node --test tools/ai-cad/test_display.mjs`. Tests cover 180 angle/aspect combinations, large point arrays, small offset geometry and measurement formatting. Display bounds are accumulated with iteration rather than argument spreading, avoiding JavaScript call-argument limits for large arrays.

The test used the source before this fix from a separate checkout and the current viewer against the same native model. Fit applies to model geometry; it does not add panning, orthographic view presets, selection or a guarantee that overlays never overlap a deliberately zoomed model. Native geometry and exported coordinates are unchanged.
