# Shared document and GitHub preservation — 2026-10-11

The two geometry prototypes now share an experimental document, editing API, validation entry
point and save/reload format. This is the first integration layer; the geometry algorithms and
boundary representations remain separate. The full Fusion recreation is not implemented.

## Behavior demonstrated
- Store exact planar solids and analytic parallel-axis curved solids in one document.
- Create named construction features, cut/union/intersect within a backend, and edit parameters.
- Rebuild dependent features after editing an earlier dimension.
- Preserve exact rational coordinates through JSON without floating-point conversion.
- Keep the previous document unchanged when a rebuild fails.
- Validate before atomic file replacement; preserve the previous file when replacement fails.
- Reject mixed-backend operations, forward references, duplicate IDs, unsupported schemas,
  nonfinite values and malformed parameter sets.
- Remove the final feature with undo. IDs belong to features, not persistent face topology.

## Verification
20 new dependency-free test methods passed. The full runner passed 85 test executions
(30 boundary, 21 cylinder, 14 baseline, 20 document; the 14 baseline methods are also included
in the boundary suite). These are executions, not 85 independent tests.

24 model states across original, edited and reloaded documents were compared with independently
constructed OCCT shapes. All reference shapes passed OCCT validation. Maximum volume difference:
2.2737367544323206e-13 mm³. Maximum area difference: 7.105427357601002e-15 mm².
These checks concern editing/replay, volume and area; they do not prove complete surface equivalence.

The comparison's sample document contains a counterbored plate and a separate slotted planar
block. Changing drill radius and block width rebuilds the downstream cuts; save/reload retains
the edited feature graph. See experiments/2026-10-11-shared-document/shared-demo.json.

## GitHub correction
Inspection found no remote configured and all three previous probes outside Git. Created
the private repository https://github.com/ichen27/fusion-recreation under the verified ichen27
account, pushed the existing documentation history, and brought original source, tests and
research evidence into experiments/. External historical tool copies remain intact.
Original hashes are recorded in experiments/original-snapshot.json; portability edits and
trailing whitespace normalization explain differences in the tracked copies.

Added a project AGENTS.md, ignore rules, a portable test runner and GitHub Actions for Python
3.9 and 3.14. Modeling requires only the standard library. Optional OCCT comparisons remain
separate from CI. Agents are instructed to push meaningful progress and verify remote SHAs
before handoff; no background autosave or recurring automation is installed.

The branch-protection API returned HTTP 403: GitHub requires a plan upgrade or a public
repository for that feature. Repository privacy was preserved. CI checks are available,
but branch protection is not enforced.

## Remaining work
- A shared geometric boundary representation and full curved-shell topology validation.
- Cross-backend Booleans, arbitrary-axis curves and fillets.
- Persistent face/edge identities, incremental rebuilds and a production document service.
- UI and the remaining CAD/CAM/CAE/ECAD product.

The prototype remains disposable research. The recommended product foundation remains OCCT.
