# Analytic bracket milestone — 2026-10-19

The integrated Rust model can now create a convex XY extrusion with 1..16 separate circular through-holes. The delivered example is a flat mounting plate, not a bent bracket. This milestone completes a bounded create/edit/save/reopen/export path; the long-term platform remains in progress.

## Precision and architecture

The authoritative geometry is a constructive analytic perforated prism: rational outer polygon, height, circle centers and radii. Exact squared-distance predicates reject tangency, breakout and overlapping holes. Volume retains rational coefficients of π. This is a new bounded representation, not a general curved B-rep, nonconvex Boolean engine or nonlinear sketch solver. The old planar closed-boundary schema remains unchanged for old features.

The `--mesh` path validates the exact model, samples 16..256 inscribed segments per circle, triangulates caps with earcutr, and builds walls. It checks noncollapsed triangles and opposite two-use edge incidence. These checks do not prove absence of every possible numerical self-intersection. Failure leaves the exact model valid and saved; the viewer reports a separate display error. CPU geometry and float GPU display remain separate. No GPU compute is added, and the browser's float32 display is not a metrology surface.

STL uses that mesh with 17-digit ASCII coordinates and an explicit millimeter convention. Its radial error report is the mathematical chord sagitta, excluding floating-point rounding. STEP uses OCCT solely to construct supplied faces/walls, sew and serialize them; it never substitutes OCCT Boolean modeling. The independent verification script uses OCCT subtraction as an oracle. STEP conversion uses a 1e-7 mm sewing tolerance and rejects hole radii, height and clearances at or below 1e-6 mm. These export constraints are deliberately stricter than exact model validity. Neither format retains parametric feature history.

## Evidence

- 46 model/HTTP integration test methods, including nine new hole/export methods and a new HTTP display/download test. New coverage includes both profile windings, diagonal edges, 24 seeded scaled/translated cases, exact sub-float clearances, tangency/overlap/breakout, invalid IDs/references, maximum 16-hole display at 256 segments, and old planar STL export.
- Independent STL reader verifies opposite directed edge incidence, Euler characteristic for through-hole genus, signed volume, cap exclusion of hole centers, and convergence over 16/32/64/128/256 segments. A separate diamond and 16-hole grid exercise cap triangulation beyond the example.
- Native document tests cover preview without writes, dependent center/margin edits, fixed dimensions, atomic failure, reopen, undo/redo, stale export revisions and unchanged document bytes.
- MCP stdio test discovers the typed hole schema and runs preview, commit and invalid-clearance diagnostics through the real adapter. The earlier live natural-language recording replays unchanged. This milestone does not claim a new authenticated natural-language conversation for the bracket.
- STEP readback checks one valid solid and volume. The independent verifier checks three cylindrical radii/centers, axes, points in each hole outside the solid, a material point inside, and agreement with a separately constructed subtraction reference. Additional corner-cut and diamond exports pass; sub-tolerance radius rejects without publication. Existing output files are protected.
- Browser checks: three visible holes; width 100→120 preview updates dependent centers; save/reload, undo/redo, rejected width 20 with unchanged revision, saved-revision STL download, and no console errors. Desktop parameter panels scroll independently of the viewport. The screenshot is the saved 120 mm bracket.
- Rust fmt/clippy/release, Python Ruff, JavaScript syntax/Prettier, all four replay verifiers and all 104 older research test executions pass locally. CI repeats the integrated checks, including the optional STEP verifier on Linux.

[Measured export report](../examples/ai-cad/bracket/export-validation.json): widened exact volume **43200 − 162π**, STEP volume 42691.06199011844 mm³, independent-reference error approximately **2.18e-11 mm³**. At 128 segments, STL volume is 42691.26635257332 mm³, 1560 triangles, radial chord error at most **0.000903544 mm**. The difference is disclosed approximation, not model error.

[Artifacts and portable quickstart](../examples/ai-cad/bracket/README.md) include both editable stages, commands/results, STEP/STL, screenshot and measured report. These are a small checked corpus, not certification for manufacturing or a proof of general CAD robustness.

## Remaining dependencies

The evaluator still rebuilds the full document/history and starts Rust subprocesses. Analytic display creates additional tessellation subprocesses; no performance improvement is claimed. Next work is measurement and incremental runtime scheduling, interactive sketches, broader exact/numerical geometry and stable topology references. Assemblies, drawings, manufacturing/analysis, packaging and collaboration remain later platform gates.
