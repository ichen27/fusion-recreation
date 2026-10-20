# Exact planar separation

Two10×4×2 blocks with copy offset(13,8,2) have a3–4–5 gap: exact minimum distance5mm, with closest points(10,4,2) and(13,8,2). Moving the copy to(10,0,0) produces face contact; moving it to(5,0,0) produces positive material overlap. Zero separation in the latter case does not describe penetration depth.

| Artifact | Purpose |
|---|---|
| [source.cad.json](source.cad.json) | Editable separated blocks, revision1 |
| [contact.cad.json](contact.cad.json) | Face contact, revision2 |
| [overlap.cad.json](overlap.cad.json) | Positive overlap, revision3 |
| [undo.cad.json](undo.cad.json) | Undo returns to contact, revision4 |
| [mcp-recording.json](mcp-recording.json) | Twelve actual MCP calls: create, measure, preview/edit, stale rejection and undo |
| [browser-recording.json](browser-recording.json) | Six actual browser reads across three native files |
| [browser-source-runtime.json](browser-source-runtime.json), [browser-contact-runtime.json](browser-contact-runtime.json), [browser-overlap-runtime.json](browser-overlap-runtime.json) | Before/after native hashes for each browser inspection |
| [separated.png](separated.png), [contact.png](contact.png), [overlap.png](overlap.png) | Actual browser results |
| [independent-comparison.json](independent-comparison.json) | Fourteen independent solid distances and closest-point membership checks |
| `*.model.json` | Editable source models for each named reference case |

Copy a native file to a working path, start the [viewer](../../../tools/ai-cad/README.md), select **part**, choose **copy**, then **Measure separation**. Reads create no feature and preserve native bytes. Browser stages inspect the corresponding saved files; actual edits/history are recorded through MCP.

```sh
python -m unittest discover -s tools/ai-cad -p test_clearance.py
python tools/ai-cad/verify_clearance.py
python tools/ai-cad/verify_clearance_mcp.py
# Optional documented comparison environment:
python tools/ai-cad/verify_clearance_reference.py
```

Tests cover cavities, contacts at faces/edges/points, overlap, disconnected material, concave stock, lofts, fractional/irrational/tiny gaps and30 seeded box placements. Exact witness distance and membership are checked. Native segment tests cover interior skew minima, parallel/clamped minima and budget rejection. Independent OCCT shapes are built from source dimensions rather than native boundaries; OCCT never performs production modeling or distance queries.

Only supported planar material is admitted. The algorithm checks interior overlap before minimizing boundary distances; otherwise a contained body could incorrectly appear separated from its enclosing material. Closest points can be nonunique and are revision-scoped. No curved-distance, penetration-depth, motion or manufacturing-tolerance guarantee. The viewport does not yet draw the closest-point connector. No new model-inference run is claimed.
