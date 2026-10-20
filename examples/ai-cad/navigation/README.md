# Orthographic viewport navigation

The viewer provides isometric, front, back, left, right, top and bottom views. Drag to orbit; Shift-drag or middle-drag pans. Wheel zoom keeps the cursor's projected point in place. With the canvas focused, arrow keys orbit, Shift+arrows pan, +/− zoom and F fits. Fit resets pan/zoom while retaining orientation; choosing a named view resets all three. Orbit stays upright. This is display navigation; camera state is not stored in the native model.

Front looks from −Y with +X right/+Z up; top looks from +Z with +X right/+Y up. Right looks from +X. Rendering and CPU picking now use consistent depth in a right-handed frame. The former depth direction would expose the opposite face for those standard-view labels. The default isometric orientation changes accordingly. Native geometry, exact measurements and surface IDs do not change.

## Evidence and artifacts

- `source.cad.json`: editable mixed-unit-created stock, 12.7 × 25.4 × 10 mm; open with the viewer's `--store` argument.
- `browser-recording.json`: seven actual saved-surface selections. Top/front/right/bottom/back/left return normals +Z/−Y/+X/−Z/+Y/−X; clicking after a middle-button pan still selects the top face.
- `browser-audit.json`: retained camera uniforms and selection counts for middle-drag panning, keyboard orbit/pan/zoom, fit, synthetic cursor-centered wheel input, synthetic Shift-drag and WebGL context recovery. Camera actions before context loss perform zero geometry uploads; restoration uploads the geometry once and retains camera state. The browser driver did not deliver wheel events or propagate its held Shift key into pointer events, so those two handler paths are explicitly tested with synthetic events. Middle drag, keyboard controls and surface clicks used native browser input commands.
- `gpu-projection.json`: 63 WebGL transform-feedback configurations × four points compared to CPU picking projection. Renderer/vendor identify the actual browser backend; this is shader agreement, not a hardware throughput benchmark. Maximum error must be below 2e−6 in clip coordinates; no GL errors are accepted.
- `browser-runtime.json`: retained worker counts and equal before/after native hashes. Selection context is stored separately; the design file is unchanged.
- `isometric.png`, `top.png`, `narrow.png`: actual, visually inspected browser screenshots at 1280×900 or 600×900.

From the repository root after the [documented setup](../../../tools/ai-cad/README.md):

```sh
node --test tools/ai-cad/test_camera.mjs tools/ai-cad/test_picking.mjs
python3 tools/ai-cad/verify_navigation.py
# Open the running local viewer with agent-browser, then:
agent-browser eval --stdin < tools/ai-cad/verify_camera_gpu.js
```

The Python replay validates selections and retained observations; it does not launch a new browser. Pure camera tests independently assert named axes/outside faces, translated picking, anchor invariance at zoom limits, fitting and orbit bounds. GPU agreement was measured in the retained run. Camera changes only update uniforms; exact CPU geometry remains authoritative. Perspective, stored views, multi-touch navigation and assembly-scale performance remain future work.
