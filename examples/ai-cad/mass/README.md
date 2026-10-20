# Uniform-density mass measurements

The original engine converts its exact volume and centroidal volume inertia into mass properties using an explicitly supplied uniform density. This is a read-only scenario; no material is assigned or persisted.

## Retained artifacts

- [source.cad.json](source.cad.json): editable 10 × 4 × 2 mm box, revision 1; import it in the viewer.
- [measurement.png](measurement.png): browser measurement with density 1000 kg/m³.
- [browser-recording.json](browser-recording.json): five actual HTTP reads: geometry only, densities 1000 and 2000, zero rejection, then blank density restoring geometry only.
- [mcp-recording.json](mcp-recording.json): nine actual stdio MCP reads, including fractional density, invalid numbers, nonpositive density and a stale revision.
- [browser-runtime.json](browser-runtime.json): native file hashes before/after the session and worker reuse counts.

The box volume is 80 mm³. At the illustrative density 1000 kg/m³ its mass is exactly 1/12500 kg. For each diagonal axis, independent verification uses M(a²+b²)/12 with lengths converted to meters. Doubling density doubles mass and inertia without changing any geometric result. Density entry clears the old browser result. Native file bytes remain unchanged.

## Reproduce

Build the release engine following the [quickstart](../../../tools/ai-cad/README.md), then run:

```sh
python tools/ai-cad/verify_mass.py
python -m unittest discover -s tools/ai-cad -p test_mass.py -v
# With tools/ai-cad/requirements.lock installed:
python tools/ai-cad/verify_mass_mcp.py
```

The replay checks retained browser/MCP replies against current execution, independent box formulas and read-only file hashes. Tests additionally cover exact cylinder formulas, perforated solids, revolutions, cavities, disconnected material, placements, cache separation and invalid input. Browser recording was obtained through actual input/click actions; it is replay evidence rather than a new headless browser run in CI.

Density is a positive integer/fraction in kg/m³, not a decimal/unit expression. Rational outputs reduce exactly; curved outputs preserve rational functions of pi. The uniform-density center of mass equals the volume centroid. Mixed-material assembly mass, saved material assignments, material catalogs and principal inertia axes are not implemented by this feature.
