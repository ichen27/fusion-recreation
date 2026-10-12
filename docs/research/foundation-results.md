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

Latest measured clean source: 5f779e3fa6dae2ff9e260846c2b371fa5993fff5.
[Machine-readable report](foundation-evidence.json): 11/11 native CTest groups and
the runner fixture passed, with maximum volume error 1.10e-11 mm³.
The collector took 1.73 s; maximum waited-child RSS was
28,934,144 bytes, not aggregate memory. Per-command one-run
latencies are in the report; process startup is included in the first request.
[Independent review and regressions](foundation-review.md).

A post-publication failure test confirms that the new revision can be visible even when final durability fails. This returns CommitUncertain, requiring reopen or transaction retry; it never claims the write rolled back. Pre-publication I/O failure is exercised with a real failing file-open against a directory.

## Additional runtime checks

A separate Debug build with UndefinedBehaviorSanitizer and
-fno-sanitize-recover=all passed 11/11 CTest groups (3.26 s). The application and
planeGCS were instrumented; the prebuilt OCCT libraries were not.

AddressSanitizer is **unverified on this host**. Apple clang 17's ASAN runtime
on this macOS 27.0.1 mini hung before main. A sampled stack showed reentrant ASAN
initialization waiting in StaticSpinMutex through malloc and dyld cache enumeration.
A standalone int main(){return 0;} built with -fsanitize=address also timed out
after five seconds. The CAD test run was stopped and its child processes cleaned
up. This is an observed tooling limitation, not a passing ASAN result.
