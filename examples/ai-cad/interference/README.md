# Exact planar part interference

The original engine checks positive shared material volume between two saved planar bodies. A10×4×2 block and its linked copy shifted5mm alongX overlap by40mm³. Shifting the copy10mm gives zero common volume, but the blocks still touch at a face. The browser and MCP explicitly avoid equating zero volume with clearance.

| Artifact | Purpose |
|---|---|
| [source.cad.json](source.cad.json) | Editable overlap case, revision1 |
| [contact.cad.json](contact.cad.json) | Copy shifted to face contact, revision2 |
| [undo.cad.json](undo.cad.json) | Undo restores overlap at revision3 |
| [curved.cad.json](curved.cad.json) | Added tapered stock demonstrates explicit unsupported interference |
| [mcp-recording.json](mcp-recording.json) | Eleven actual typed MCP creation/read/preview/edit/stale/undo/rejection calls |
| [browser-recording.json](browser-recording.json) | Four actual browser reads across overlap/contact native files |
| [browser-runtime.json](browser-runtime.json), [browser-contact-runtime.json](browser-contact-runtime.json) | Unchanged native hashes for both browser inspections |
| [overlap.png](overlap.png), [contact.png](contact.png) | Actual browser results |
| [independent-comparison.json](independent-comparison.json) | Twelve source-built OCCT solid-intersection comparisons |
| `*.model.json` | Editable model inputs for every independent comparison, named by case |

Copy either native file to a working path and start the [documented viewer](../../../tools/ai-cad/README.md). Select **part**, choose **copy**, then **Check volume overlap**. No part is consumed and no native transaction is saved by inspection. The two browser stages use the corresponding saved files; the edit/undo workflow is recorded through actual MCP.

```sh
python -m unittest discover -s tools/ai-cad -p test_interference.py
python tools/ai-cad/verify_interference.py
python tools/ai-cad/verify_interference_mcp.py
# Optional documented comparison environment:
python tools/ai-cad/verify_interference_reference.py
```

Independent source-built references include overlap, face/edge/point contact, a probe inside a cavity, cavity wall penetration, disconnected pieces, concave stock, overlapping bounding boxes with disjoint material, and placed lofts. Exact unit tests also cover25 seeded fractional offsets, identical geometry, tiny positive overlap, stale references, unsupported curves and content-cache replacement. OCCT is used only for verification; native overlap uses the original rational half-space kernel.

Supported: unperforated polygon extrusions, planar lofts, cuts/Booleans, cavities/disconnected material and their supported placements/instances. Curved/perforated analytic stock rejects, even when visually separated. No contact geometry, minimum distance, clearance, motion or assembly-joint result is provided. Coincident display faces can visually interfere; the answer uses exact material geometry rather than rendered pixels. No new model-inference run is claimed.
