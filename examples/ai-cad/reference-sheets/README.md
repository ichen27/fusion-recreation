# Orthographic SVG reference sheets

Reference views generated from the original engine's validated line/quarter-circle topology. Native circles remain vector arcs. Each sheet carries its source revision, canonical-model SHA-256 and exact XYZ extents in millimeters.

## Open the deliverables

- [source.svg](source.svg): 100 × 60 × 6 mm plate with two circular through-holes.
- [edited.svg](edited.svg): same source after thickness changes to12 mm.
- [undo.svg](undo.svg): original geometry restored at revision3.
- [source.cad.json](source.cad.json), [edited.cad.json](edited.cad.json), [undo.cad.json](undo.cad.json): editable native projects/history; import into the viewer.
- [browser-download.svg](browser-download.svg): actual browser-button download, byte-identical to source.svg.
- [browser-sheet.png](browser-sheet.png): inspected browser rendering.
- [browser-export.json](browser-export.json), [browser-runtime.json](browser-runtime.json): actual HTTP export and unchanged native-file hashes.
- [mcp-recording.json](mcp-recording.json): eight actual stdio MCP create/draw/preview/edit/draw/stale/undo/draw requests.

SVGs open in a browser or vector editor without external resources or scripts. These are all-edge reference sheets: occluded edges and smooth surface seams remain visible. They do not include hidden-line removal, section views, tolerances or manufacturing annotations. Scale fits the sheet; use labeled dimensions, not page measurements. Re-export after model changes.

## Verify and reproduce

Build the native release engine using the [quickstart](../../../tools/ai-cad/README.md):

```sh
python tools/ai-cad/verify_drawings.py
python -m unittest discover -s tools/ai-cad -p test_drawings.py -v
python tools/ai-cad/drawings.py --store examples/ai-cad/reference-sheets/source.cad.json --revision 1 --body part --output reference.svg
# With MCP dependencies installed:
python tools/ai-cad/verify_drawings_mcp.py
```

Replay verifies exact SVG/native snapshots and browser bytes, including16 native quarter arcs forming the two holes' top/bottom rings. Independent tests verify box page coordinates, cylinder radii/arc direction on all three principal axes, large translation invariance, tiny whole-part normalization and explicit rejection of details that collapse at SVG display precision. HTTP tests reject stale, missing or repeated query fields. All reads leave the native file unchanged.

Projection coordinates use exact centering/scaling followed by12 significant digits for SVG display. Native geometry and labels retain exact rational values. Extent labels are bounded to80 characters and exports to4MiB. This initial drawing representation is a source-bound snapshot, not a persistent annotation or drawing-history model.
