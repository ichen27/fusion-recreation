# Measured-edge viewport highlight

Measuring a saved native edge draws its location in purple, with endpoint markers. Lines use two vertices; quarter circles use33 sampled vertices. These samples are disposable display data and never determine the exact length. Solid surfaces occlude hidden portions; orbit to inspect them.

| Artifact | Purpose |
|---|---|
| [Source document](../edge-measurements/source.cad.json) | Editable synthetic tapered solid, shared with the exact-length examples |
| [arc.png](arc.png), [seam.png](seam.png) | Actual viewport arc and straight seam highlights |
| [browser-recording.json](browser-recording.json) | Nine actual browser requests and GPU/lifecycle instrumentation |
| [reselection-recording.json](reselection-recording.json), [reselection-runtime.json](reselection-runtime.json) | Same-body delayed-reply rejection and fresh recovery, unchanged native bytes |
| [browser-runtime.json](browser-runtime.json) | Unchanged native document hashes and worker counters |

The browser recording checks one792-byte arc upload, one48-byte line upload, no geometry uploads during orbit, restoration of body/edge buffers after forced context loss, and no stale highlight after a delayed reply arrives following selection clearing. Editing a dimension clears the display measurement before any preview/save. Selection, surface changes, model redraws and repeat inspection invalidate pending highlight requests, including reselection of the same body/revision. The exact measurement remains revision-bound in the host.

Run the viewer with a copy of the linked source, choose **taper → Inspect surfaces → Measure edge**. Edge1 is an arc and Edge9 is a conical patch seam. Choose another edge, clear selection or begin an edit to clear the old highlight. This is local visual inspection; it does not add shared edge selection or direct mouse edge picking.

```sh
node --test tools/ai-cad/test_edge_display.mjs
python tools/ai-cad/verify_edge_highlight.py
```

The verifier replays the actual HTTP reads and audits retained GPU instrumentation. It does not rerun a graphics browser in CI. Unit tests cover all six signed axes, exact endpoint retention, fractional/rebased coordinates and bounded sampling. Native source/history bytes remained unchanged. No new model-inference run is claimed.
