# AI-native CAD platform delivery plan

Scope confirmed 2026-10-19: pursue the full long-term platform. A bracket workflow and a first usable release are acceptance milestones within this scope. This plan records scope, dependencies, evidence and unresolved decisions; it is not a promise of a completion date or a claim of feature parity.

## Established direction

- Original geometry/modeling engine, with current custom development in Rust. No silent OCCT modeling fallback. Earlier C++/OCCT work stays available as a separate reference/integration track.
- AI and human actions share typed modeling operations, one authoritative editable document, exact diagnostics, previews and reversible commits.
- Single-user browser workflow first; computation/storage on the Mac mini SSD. Client GPU rendering and exact CPU geometry remain distinct. Measure before choosing GPU compute workloads.
- Deliver coherent feature branches through tests, reviewed PRs and verified CI. Retain runnable examples, native editable documents and usable exports. Keep repositories private until release visibility and licensing are explicitly settled.

## Capability ledger and acceptance gates

| Gate | Status | Acceptance evidence | Major unresolved work |
|---|---|---|---|
| Original planar geometry | Bounded implementation | Exact convex clipping, profile extrusion, orientation/manifold tests and independent comparisons | General nonconvex Boolean operations, multiple shells/cavities and tolerance policy beyond rational planes |
| Editable model and AI loop | Bounded implementation | Recorded create/edit conversation; typed MCP; atomic save/reopen, preview and undo | Broader intent tests, semantic selections, ambiguity handling and repair benchmarks |
| Parameter relationships | Bounded implementation | Center follows width; dependent chains rebuild exactly; cycles/conflicts reject atomically; same results through CLI/MCP/browser | General geometric constraint solving and nonlinear expressions |
| Useful part workflow | Bounded flat-bracket implementation | Three analytic through-holes; margin/center relationships; preview/save/reopen/undo; STL topology and STEP surface/location/volume checks | Bent brackets, arbitrary hole axes/depths, general curved topology and wider intent corpus |
| Sketch and feature modeling | Planned | Interactive constrained sketches and edit-stable extrude/revolve/sweep/loft/hole/chamfer/fillet/shell/draft/pattern workflows | Solver choice, over/underconstraint diagnostics, selection provenance and robust curved intersections |
| Geometry breadth and interchange | Planned | Analytic and spline surfaces, repeated nonconvex operations, valid native/STEP/STL round trips with explicit losses | Curved numerical policy, trimming/healing, NURBS and imported-boundary validation |
| Runtime and hardware | Basic split and initial host-latency baseline implemented | Versioned jobs, cancellation, incremental rebuilds, memory budgets and latency/frame-time measurements on declared workloads/devices | Large-document scheduling, caches, worker concurrency, GPU uploads/device recovery and justified compute acceleration |
| Assemblies and engineering documentation | Planned | Component transforms, joints/configurations, linked drawings, tolerances and parts lists survive model edits | Assembly references, configuration semantics, materials, sheet metal and associative drawings |
| Broader design workflows | Planned | Explicitly scoped surfaces/freeform, meshes, rendering and animation examples | Representations, conversion semantics and cross-workflow editability |
| Manufacturing and analysis | Long-term scope | Separate verified CAM, additive/nesting, CAE and electronics workflows | Domain solvers, toolpaths/posts, machine/process models, numerical accuracy and independent validation |
| Product delivery and collaboration | Planned | Reproducible installation/update, stable document migrations, recoverability, API/add-ins, versioning and collaboration tests | Packaging/deployment, licensing/business model, access controls and concurrent editing semantics |

“Implemented” applies only to the tested capabilities stated in each row. Earlier standalone experiments are references until integrated and revalidated. A screenshot or one accepted AI prompt is not an acceptance gate by itself.

## Immediate implementation sequence

1. Exact affine parameter relationships, shared validation and dependency diagnostics. Preserve existing document/replay behavior.
2. Define analytic round-hole geometry and its precision policy; integrate a bounded round-hole part path without substituting polygons as authoritative circles.
3. Add usable export with measured approximation where applicable and independent re-import checks. Supporting export adapters must be explicit about geometry/history losses.
4. Complete the bracket create/edit/save/reopen/export acceptance run through the shared AI and human workflow. Specify the bracket geometry and required edits in its fixture, not just its visual appearance.
5. Measure cold/warm operation cost, peak memory and browser frame/upload behavior on a representative corpus. Use results to guide incremental evaluation and scheduling.
6. Expand sketches, general solids and curved operations, each with accepted/rejected case corpora and edit-stability tests.

These steps may overlap when dependencies allow. A failed geometry or performance gate triggers a documented diagnosis and revised implementation, not a substituted success claim.

## Decision handling

Routine internal implementation choices can proceed within this scope. Record choices and tradeoffs alongside relevant code. Product-changing decisions still need concrete alternatives: supported manufacturing domains, public release/license, paid infrastructure, distribution beyond the existing host, and incompatible data/precision policies. Do not repeatedly reopen established browser/mini/custom-engine preferences.

Progress reporting identifies the completed gate, evidence, remaining limits, source revision and next dependency. The full platform remains in progress until its agreed acceptance gates are met; completing an individual PR does not complete this plan.

## Latest evidence

[Parameter relationship validation](parameter-relationship-validation.md) records the current dependency behavior, integration checks and measured full-history latency. Broader runtime and GPU measurements remain pending.

[Analytic bracket validation](analytic-bracket-validation.md) records the integrated hole, display and export milestone. Next: measured runtime/frame/upload behavior, then broader sketch interaction and geometry. The full platform remains in progress.

## Runtime checkpoint

[Measured bounded reuse and rendering](../examples/ai-cad/runtime/README.md) removes repeated host validation/tessellation and camera-time mesh uploads without changing exact geometry. Content/executable invalidation, memory limits and context recovery are covered. Feature-level incremental evaluation, asynchronous cancellation and large-model scheduling remain pending. Continue directly into interactive sketch creation after this checkpoint; a merged PR is not a stop condition.
