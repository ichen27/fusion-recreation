# Exact edge measurements

The original engine measures native lines and quarter circles without using mesh chords. A conical frustum with radii10/7 and height4 has four sloping patch seams of exact length5mm. Its bottom quarter-circle arcs have length5*pi mm and chord sqrt(200)mm. Raising the height to5 changes the seams to sqrt(34)mm.

| Artifact | Use |
|---|---|
| [source.cad.json](source.cad.json) | Editable synthetic original document, revision1 |
| [taller.cad.json](taller.cad.json) | Revision2, including prior native history |
| [mcp-recording.json](mcp-recording.json) | Twelve actual typed MCP calls, invalid/stale indices and current measurements |
| [browser-recording.json](browser-recording.json) | Actual browser selection, topology and exact arc/seam reads |
| [browser-runtime.json](browser-runtime.json) | Before/after native hashes and worker counters |
| [arc.png](arc.png), [seam.png](seam.png) | Browser results for arc and seam |
| [reference-comparison.json](reference-comparison.json) | 196 edge lengths in7 models, compared with OCCT integration of translated native supports |

Copy `source.cad.json` to a working file, then start the viewer using the [quickstart](../../../tools/ai-cad/README.md). Select **taper → Inspect surfaces → Measure edge**. Edge1 is a bottom arc; Edge9 is a smooth patch seam. The UI counts from1; the API counts from0. Refresh references after edits. The dropdown does not yet highlight an edge in the viewport.

Reproduce from the repository root:

```sh
python -m unittest discover -s tools/ai-cad -p test_edge_measurements.py
python tools/ai-cad/verify_edge_measurements.py
python tools/ai-cad/verify_edge_measurements_mcp.py
# Optional documented comparison environment:
python tools/ai-cad/verify_edge_measurements_reference.py
```

Tests include independently known3–4–5 triangle sides/conical generators, exact fractional/irrational/tiny lengths, all-axis quarter turns, translation, stale/invalid references and same-revision document replacement. The OCCT comparison checks integration of supplied native supports; it is not an independent reconstruction of topology. Actual MCP calls are deterministic test clients, not a new model-inference recording. No arbitrary entity-distance, angle or persistent-edge naming claim. No native modeling operation is delegated to OCCT.
