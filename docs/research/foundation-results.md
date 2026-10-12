# Native foundation evidence

Date: 2026-10-12. Decision: **conditional go for a browser workflow prototype**, limited to implemented analytic operations. This is not full Fusion functionality or proof of general CAD robustness.

Run `python3 tools/verify_foundation.py`. It runs CTest and drives the actual runner through sketch, extrusion, hole, width edit, close/reopen and STEP export/import. Reports contain source commit, dirty-tree state, dependency hashes, tool versions, timings, memory definition and reference statuses. Failed assertions or scenarios produce a nonzero exit. Reports/models live under the ignored build directory; measured evidence is preserved beside this document.

## Verified behavior

- OCCT analytic volumes and invalid-input rejection.
- Actual planeGCS dimensions, degrees of freedom, conflicting/redundant IDs and residuals without modifying the input sketch.
- Dependency recomputation, stable feature IDs, one OCAF label transaction per grouped edit, monotonic undo/redo and independent-feature preservation.
- Unique top-support references survive width edits. Split, missing and mismatched provenance require explicit repair.
- Immutable snapshots, SHA-256 integrity, schema/engine checks, writer locks, file/directory fsync and atomic manifest replacement.
- A real child is killed between payload write and manifest publication; the old revision remains readable. Controlled pre-publication failure preserves the manifest.
- STEP preserves tested volumes and translated placement in millimeter/inch exports. Import reports lost feature history and assembly metadata.
- Duplicate transactions return their original reply after restart. Concurrent writers produce one commit and one revision conflict. Completed, cancelled and disconnected previews never publish.

## Bounds and open risks

- Arc solving and circular/mixed extrusion reject explicitly. This gate exercises line-loop extrusion and contained, body-centered through holes.
- Topology naming covers one highest horizontal planar support. Split/deletion tests inject changed provenance; they do not implement native split features or general topology repair.
- JSON owns feature parameters, history and command ledger. OCAF supplies in-memory label transactions; no full OCAF binary document is persisted. Caches are reconstructed; imported BREP is a versioned payload.
- POSIX/local-filesystem interrupt tests do not prove all hardware power-loss cases. Old revisions remain retained; garbage collection and bounded history policies are future work.
- Previews are disposable workers. Commits cannot be cancelled; use Undo. Lost commit replies can be retried with the same transaction ID. There is no network/authentication API yet.
- Limits: 64 MiB saved state, 4 MiB requests, bounded model size and numerical range. No production SLA or scalability claim.
- [Reference comparisons](freecad-comparison.md) remain incomplete. Neither FreeCAD nor Fusion is labeled passed.

No performance target was invented after measurement. Broader geometry, browser UI, manufacturing, electronics, simulation and collaboration remain subsequent waves.

Measured clean source: 4fdafef4fd3117d50b7d8b07fb0e1bdfc80a54ee.
[Machine-readable report](foundation-evidence.json): 11/11 CTest groups passed;
maximum fixture volume error 1.10e-11 mm³; collector elapsed 1.33 s.
Maximum waited-child RSS was 28,934,144 bytes, not aggregate memory.
Observed create/extrude/hole/edit command latencies were 45.2/2.8/8.7/10.6 ms;
creation includes process startup. These are one-run measurements.
[Independent review and regressions](foundation-review.md).
