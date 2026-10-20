# Combined mass of selected occurrences

A linked two-part model demonstrates read-only total mass, center of mass and centroidal inertia with independently supplied densities. The native model is evaluated once. Each selected occurrence contributes separately, including overlaps; this operation does not fuse solids or check interference.

## Artifacts

- [source.cad.json](source.cad.json): editable 10 × 4 × 2 mm block and linked copy offset by (20, 30, 40) mm. Import into the browser to try the workflow.
- [measurement.png](measurement.png): browser combined-mass dialog with different densities.
- [browser-recording.json](browser-recording.json): four actual HTTP reads: different densities, equal densities, zero rejection, and deselecting the copy.
- [mcp-recording.json](mcp-recording.json): seven actual typed stdio MCP calls, including reordered selection, doubled densities, duplicate rejection and stale revision.
- [browser-runtime.json](browser-runtime.json): native file hashes before/after and worker counts for browser validation, including the screenshot capture.

At densities 1000 and 2000 kg/m³, the combined mass is 3/12500 kg and its center is (55/3, 22, 83/3) mm. Equal densities put the center at (15, 17, 21) mm. The replay independently calculates each block's diagonal inertia and shifts it to the combined center with the parallel-axis theorem, checking all nine tensor entries exactly. Deselecting the copy restores the single block's result. Inputs and measurements leave native file bytes unchanged.

## Reproduce

Build the release engine using the [quickstart](../../../tools/ai-cad/README.md), then run:

```sh
python tools/ai-cad/verify_mass_set.py
python -m unittest discover -s tools/ai-cad -p test_mass_set.py -v
# With tools/ai-cad/requirements.lock installed:
python tools/ai-cad/verify_mass_set_mcp.py
```

Tests include 24 seeded exact density/placement combinations, mixed box/cylinder formulas, shared-coordinate and one-part identities, overlap semantics, translation invariance, 16 occurrences with a shared dimension edit, error recovery, cache separation and fresh/worker equality. Recorded browser calls replay in CI; the replay does not claim to launch a new browser session.

## Bounds and limits

Select 1..16 distinct terminal solids with positive rational densities in kg/m³. Native geometry and density validation guarantee positive mass. Rational outputs reduce exactly; curved outputs retain exact rational/pi expressions, capped at 65536 bytes per constructed expression. Complicated symbolic selections may exceed that limit before reaching 16 parts. Explicit errors preserve the document.

The result uses global XYZ axes; the tensor is about the combined center in kg m². Densities are scenario inputs, not persisted material assignments. Assembly hierarchy, joints, external references, overlap removal and principal axes are separate work.
