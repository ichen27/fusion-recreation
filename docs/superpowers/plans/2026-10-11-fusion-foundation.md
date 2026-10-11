# Fusion recreation foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a runnable, headless CAD foundation that proves Gate 0 before committing to broad interface development.

**Architecture:** A C++ library combines OCCT/OCAF with a planeGCS adapter and a product feature graph. A local command runner exercises transactions and recovery without requiring a browser. The full product remains the approved target; this plan resolves its first architectural dependency.

**Tech Stack:** C++20, CMake/CTest, OCCT, planeGCS and its declared dependencies; Python 3 standard library for external process tests. Freeze exact upstream commits, archives, checksums, compiler and build-tool versions in Task 1; do not depend on floating branches.

**Spec:** ../specs/2026-10-11-fusion-recreation-design.md (approved 2026-10-11)

## Global Constraints

- Development and engineering computation run on the Mac mini SSD.
- Full application coverage remains the target.
- A mesh triangle index or face number is never a durable selection.
- Repeating a transaction must not create another feature.
- Stale revisions return a conflict.
- Preview jobs are cancellable and never commit themselves.
- Migration failures preserve the original file.
- For simple analytic millimeter fixtures, start with volume tolerance max(1e-6 mm³, 1e-8 relative).
- Original executable bytes and copied vendor resources remain private in the SSD research area; they are not implementation assets.
- Project: /Volumes/SamsungSSD1/code/fusion-recreation. Dependency downloads/build caches: /Volumes/SamsungSSD1/tools/fusion-recreation. Reuse verified installed tools before provisioning tools there.
- No browser or production deployment is part of this foundation gate.

## Review Focus

1. Nonfinite, negative or zero dimensions must fail before entering native modeling (Task 1).
2. Constraint conflicts and degeneracy must preserve the last usable sketch (Task 2).
3. Split/deleted topology must fail explicitly when references become ambiguous (Task 3).
4. Interrupted saves and incompatible schemas must preserve the last committed document (Task 4).
5. Duplicate, reordered and cancelled commands must not duplicate or lose mutations (Task 5).

## File map and shared conventions

Paths below are relative to the project. Public headers live under include/cad; implementation files under src. Geometry uses millimeters and radians internally; input units remain explicit. IDs are opaque persisted strings. Public functions return Result<T>, defined in include/cad/result.hpp as a tagged value or Diagnostic{code,message,entityIds}; no silent fallback value.

- cmake/Dependencies.cmake, deps/lock.json, deps/NOTICES.md: reproducible third-party acquisition and actual license notices.
- include/cad/types.hpp: Id=std::string, Revision=uint64_t, Units{Millimeter,Inch}, Point2{x,y}, Profile{vertices}, Circle{center,radius}, Dimensions{width,height,depth}; values use double.
- include/cad/kernel.hpp, src/kernel.cpp: OCCT shape construction and physical checks.
- include/cad/sketch.hpp, src/sketch.cpp: planeGCS translation and solver diagnostics.
- include/cad/document.hpp, src/document.cpp: OCAF attributes, feature DAG, recomputation and undo.
- include/cad/selection.hpp, src/selection.cpp: topology provenance and ambiguity.
- include/cad/storage.hpp, src/storage.cpp: document serialization and crash-safe revisions.
- include/cad/exchange.hpp, src/exchange.cpp: STEP exchange.
- include/cad/commands.hpp, src/commands.cpp: revision and transaction semantics.
- src/runner.cpp: JSON-lines command-runner process; process transport is a testable service precursor.
- tests/*_test.cpp: compiled assertion tests registered in CTest; failed assertions must remain enabled in every build.
- tests/recovery_test.py, tests/runner_test.py: subprocess and disk-failure tests.
- tools/verify_foundation.py: one-command evidence collection, not a second test framework.

Build convention after Task 1: cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug; cmake --build build; ctest --test-dir build --output-on-failure. Set temporary/cache directories to SSD paths. Build directories are ignored.

## Task 1: Reproducible kernel and analytic solid

**Files:** Create CMakeLists.txt, .gitignore, cmake/Dependencies.cmake, deps/lock.json, deps/NOTICES.md, include/cad/result.hpp, include/cad/types.hpp, include/cad/kernel.hpp, src/kernel.cpp; Test tests/kernel_test.cpp.
**Consumes:** Pinned official OCCT headers/libraries.
**Produces:** opaque Shape wrapping TopoDS_Shape; Result<Shape> extrude(const Profile&, double depth); Result<Shape> cutCylinder(const Shape&, const Circle&, double depth); bool isValid(const Shape&); double volume(const Shape&).

- [ ] Record verified tool locations on mini, upstream OCCT release/commit and dependency checksums. Configure the smallest modeling/OCAF/STEP build; keep GUI dependencies optional. Record planeGCS source commit and dependency/license inventory for Task 2. Add an explicit fetch/build command to README.md and a checksum-verified lock; source extraction must reject checksum mismatch.
- [ ] Write kernel_test with assertions: volume(extrude(rectangle(40,20),10)) approximately 8000; cylindrical cut removes 90*pi; both shapes valid. rectangle is a test helper that constructs Profile vertices (0,0),(w,0),(w,h),(0,h). Add open, self-intersecting, zero-length, negative-depth, infinity and NaN cases; assert Diagnostic codes InvalidProfile or InvalidDimension.
- [ ] Run configure/build and ctest --test-dir build -R kernel --output-on-failure. Expect a missing implementation/link failure before implementation; distinguish environment failure from test failure.
- [ ] Implement the declared interfaces in src/kernel.cpp using OCCT extrusion, cylinder and Boolean APIs. Close only explicitly closed profiles: add Profile.closed:bool to types.hpp, default false; tests set true for the rectangle. Do not silently close arbitrary open input. Validate native shape results.
- [ ] Run the same test command; expect all kernel assertions PASS. Exercise the checksum mismatch fixture and record the rejected dependency.
- [ ] Commit only Task 1 files and README.md: feat: establish reproducible analytic solid kernel.

## Task 2: Dimensioned sketches with constraint diagnostics

**Files:** Create include/cad/sketch.hpp, src/sketch.cpp; Test tests/sketch_test.cpp. Modify CMakeLists.txt, cmake/Dependencies.cmake as required by the pinned solver.
**Consumes:** Result<T>, Id, Point2, Profile, Circle.
**Produces:** Sketch{entities,constraints} with stable IDs; SketchSolution{profile,circles,degreesOfFreedom,conflictingIds,redundantIds}; Result<SketchSolution> solve(const Sketch&). Entity is variant<Line{Id,a,b,construction},Arc{Id,center,radius,startAngle,endAngle,construction},CircleEntity{Id,center,radius,construction}>. Constraint{Id,kind,entityIds,value}; initial kinds Coincident,Horizontal,Vertical,Distance,Radius,FixedPoint. Unsupported kinds fail explicitly.

- [ ] Write sketch_test: a fixed-origin 40x20 rectangle solves with zero degrees of freedom and correct dimensions; removing width dimension increases DOF; a radius-3 circle solves; conflicting 40 and 50 width constraints return conflict IDs and leave the input Sketch unchanged. Duplicate dimensions return redundant IDs; a zero-length edge is rejected.
- [ ] Build and run ctest --test-dir build -R sketch --output-on-failure; expect missing solve implementation failure.
- [ ] Implement solve(const Sketch&) in src/sketch.cpp through planeGCS. Solve on copied working parameters; publish only a successful solution. Construction entities do not create profile boundaries. Return residual diagnostics and classify underconstrained sketches without inventing missing dimensions.
- [ ] Run sketch and kernel tests; expect PASS. Save measured residuals and solver version in test output.
- [ ] Commit Task 2 files: feat: solve dimensioned sketches with recoverable conflicts.

## Task 3: Feature history and durable references

**Files:** Create include/cad/document.hpp, src/document.cpp, include/cad/selection.hpp, src/selection.cpp; Test tests/document_test.cpp, tests/selection_test.cpp. Modify CMakeLists.txt.
**Consumes:** solve, extrude, cutCylinder and their Task 1–2 types.
**Produces:** Document{Id,Units,Revision,features}; Feature{Id,kind,inputIds,parameters,status}; FeatureKind{Sketch,Extrude,Hole}; Selection{featureId,semanticRole,evolutionIds}; Result<Id> resolve(const Document&, const Selection&); Result<Document> recompute(const Document&, const std::vector<Id>& changed); DocumentSession with begin(), Result<void> commit(), abort(), Result<void> undo(), Result<void> redo(), const Document& current() const. Parameters is a typed variant of Sketch, ExtrudeParams{profileId,depth}, HoleParams{baseFeatureId,support,radius,centerMode}; centerMode initially BodyCenter only.

- [ ] Write tests building a rectangle sketch, extrusion and centered hole: width 40 -> 50 yields 10000-90*pi mm³. Assert hole remains centered, all surviving IDs persist and independent feature output is unchanged. Undo once restores every affected descendant; redo restores the new result. Cyclic inputs fail with DependencyCycle.
- [ ] Write selection_test: preserve the original extrusion top-face reference through width edit; delete or split that support and assert BrokenReference or AmbiguousReference rather than a replacement face index. First failing feature must identify its ID.
- [ ] Run build plus ctest --test-dir build -R 'document|selection' --output-on-failure; expect missing implementations.
- [ ] Implement dependency-ordered recomputation in src/document.cpp and provenance/evolution resolution in src/selection.cpp. Store OCAF attributes for persisted feature/selection IDs. Tie all descendant changes to one OCAF transaction; maintain app-log ownership explicitly in comments and tests.
- [ ] Run kernel, sketch, document and selection tests; expect PASS. Record unsupported split/deletion repair cases rather than weakening selection assertions.
- [ ] Commit Task 3 files: feat: add transactional history and topology diagnostics.

## Task 4: Atomic persistence and STEP interoperability

**Files:** Create include/cad/storage.hpp, src/storage.cpp, include/cad/exchange.hpp, src/exchange.cpp; Test tests/storage_test.cpp, tests/exchange_test.cpp, tests/recovery_test.py. Modify CMakeLists.txt.
**Consumes:** Document and Shape.
**Produces:** Result<void> save(const Document&, const std::filesystem::path&); Result<Document> load(const std::filesystem::path&); Result<void> exportStep(const Document&, const std::filesystem::path&); ImportResult{document,losses}; Result<ImportResult> importStep(const std::filesystem::path&). Add FeatureKind::ImportedBody and ImportedBodyParams{payloadId} to the typed feature representation; imported geometry has no manufactured feature history.

- [ ] Write storage_test asserting save/reopen preserves IDs, dimensions, units and volume. Unsupported future schema and truncated payload return explicit errors and do not mutate originals. Write exchange_test asserting STEP geometry, occurrence placement and mm/inch conversion agree; loss report explicitly names feature history.
- [ ] Write recovery_test.py that kills a save subprocess after writing a new payload but before manifest publication; reopening must yield the entire old revision. Add a controlled disk-write failure and assert no partial revision becomes current.
- [ ] Run relevant CTest tests; expect missing storage/exchange implementation failures.
- [ ] Implement immutable revision payload directories and same-filesystem atomic publication of a manifest pointer in src/storage.cpp, including flush/fsync ordering. Verify payload checksum and schema on load; caches include revision and engine version. Implement STEP translation in src/exchange.cpp with explicit unit handling. Test-only fault injection uses an explicit runner flag disabled by default.
- [ ] Run ctest --test-dir build -R 'storage|exchange|recovery' --output-on-failure; expect PASS, including real child termination. Confirm originals' checksums unchanged after failures.
- [ ] Commit Task 4 files: feat: persist recoverable revisions and exchange STEP geometry.

## Task 5: Command transactions and cancellable worker

**Files:** Create include/cad/commands.hpp, src/commands.cpp, src/runner.cpp; Test tests/commands_test.cpp, tests/runner_test.py. Modify CMakeLists.txt, deps/lock.json, deps/NOTICES.md for a pinned JSON library if needed.
**Consumes:** DocumentSession, save/load, modeling functions.
**Produces:** Command{documentId,expectedRevision,transactionId,operation,parameters}; Operation{CreateSketch,Extrude,Hole,EditSketch,Undo,Redo}; parameters typed by operation using earlier types plus target feature IDs. Reply{committedRevision,affectedFeatureIds,diagnostics}; Result<Reply> apply(const Command&). Runner accepts protocolVersion=1 JSON lines, validates before conversion and exposes commit, preview, cancel, snapshot and shutdown message kinds. Preview/cancel use a jobId; snapshot returns document ID and committed revision. Errors return stable codes with no committed mutation.

- [ ] Write commands_test: duplicate same transaction/payload returns the original result; reused ID/different payload is TransactionConflict; stale revision is RevisionConflict. Commit increments revision once; undo/redo also produce new monotonic revisions.
- [ ] Write runner_test.py: two conflicting writers yield one commit and one conflict; preview then disconnect produces zero commits; cancel a child kernel worker and reload last committed state; malformed JSON, unsupported protocol and invalid numeric fields return errors without crashing the supervisor.
- [ ] Run ctest --test-dir build -R 'commands|runner' --output-on-failure; expect absent apply/runner failures.
- [ ] Implement apply in src/commands.cpp with one serialized writer and a persisted transaction-result ledger published with the document revision. In src/runner.cpp supervise one native worker initially, with process termination fallback for cancellation; previews use disposable copies. Add replies' revision-tagged mesh display changes only in the later browser-service plan.
- [ ] Run commands/runner tests and whole CTest suite; expect PASS. Restart the runner between duplicate transactions to verify durable idempotency.
- [ ] Commit Task 5 files: feat: supervise idempotent CAD commands and previews.

## Task 6: Foundation evidence and architecture decision

**Files:** Create tools/verify_foundation.py, tests/foundation_test.py, docs/research/foundation-results.md, docs/research/freecad-comparison.md; Modify README.md.
**Consumes:** Built cad-runner executable and all CTest tests.
**Produces:** A repeatable Gate 0 report containing exact versions, test results, measurements, runtime and peak memory; documented go/no-go decision. No performance target invented after measurements.

- [ ] Write foundation_test.py asserting the evidence collector reports nonzero exit on any failing test, includes source commit and tool/dependency versions, and cannot label a skipped reference check passed.
- [ ] Run python3 -m unittest discover -s tests -p foundation_test.py; expect the missing collector failure.
- [ ] Implement verify_foundation.py to run CTest and the rectangle/hole edit-save-reopen-STEP scenario, collecting analytic errors and command latencies. Inspect installed FreeCAD availability and run the same analytic workflow in an isolated SSD test directory if available; otherwise explicitly record the comparison as unperformed and its setup requirement.
- [ ] Construct only fresh, dedicated Fusion reference documents for behavioral comparison if the available UI/API can do so without touching unrelated designs. Record build and exact inputs; otherwise retain an unobserved reference-comparison status.
- [ ] Run the collector and its test; expect PASS for the collector test. The actual gate passes only if required foundation assertions pass and unresolved solver/topology/persistence risks have explicit decisions. A missing comparison is incomplete evidence, not a passing comparison.
- [ ] Commit tests, collector and results: test: record foundation viability and alternatives.

## Subsequent implementation plans

Gate 0 does not authorize claiming completion of any later wave. Keep all scope rows in the approved spec:

| Next plan | Working deliverable and dependencies |
|---|---|
| Browser workflow / Wave 1 | Mini command API, rendered selectable viewport, operational tree/timeline, rectangle/circle editing, undo/save and STEP/STL; requires Gate 0 |
| General authoring / Wave 2 | Expanded sketch/solid features, expressions, direct edits and repair corpus |
| Geometry and assemblies / Wave 3 | Separate surface/freeform, mesh, sheet-metal and assembly/configuration plans on stable references |
| Derived output / Wave 4 | Associative drawings/PMI/BOM, rendering and animation plans tied to document revisions |
| Engineering / Wave 5 | Separate CAM/nesting/additive, ECAD and CAE plans with domain-specific acceptance tests |
| Integration / Wave 6 | Collaboration, scripting/extensions, translators, generative/advanced assistance and cross-workspace coverage closure |

Each subsequent plan needs detailed interfaces and acceptance fixtures when its dependencies are measured. Do not preselect CAM, CAE or electronics engines without evaluating them.

## Self-review and coverage

Reviewed against all sections of the approved specification. Tasks 1–6 cover Gate 0, analytic fixtures, solver conflicts, dependency recomputation, topology ambiguity, undo/redo, persistence, STEP, cancellation and transactions. The five review-focus failures each have an owning test.

Explicit deferred requirements: browser/UI workflow and display-mesh response schema, STL tessellation and watertightness, full assembly occurrences, arbitrary sketch geometry and 3D constraints, migrations beyond initial schema rejection, domain engineering jobs, collaboration/permissions and all subsequent breadth. They remain assigned to the wave plans above; this foundation is not full spec implementation. Persistent unit conversion and feature-history loss reporting are tested now.

Profile closure, imported-body parameters and monotonic undo revisions are specified to remove otherwise ambiguous implementation choices. Test helpers build fixtures rather than duplicate algorithms. Dependencies are frozen by verified source artifacts at execution, not guessed from website documentation versions. The architecture can be rejected on measured failures before browser implementation.

