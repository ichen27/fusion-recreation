# Editable model and command contract v1

## Model ownership

The authoritative model has `parameters` (ID → exact mm value string), ordered `features`, and `fixed` (parameter ID → invariant value). It stores intent; evaluated boundary geometry is regenerated. Feature IDs and parameter IDs survive dimension edits. One earlier block may feed one corner cut; a cut must reference a block directly, and only the terminal cut is displayed. Unsupported references and branches fail explicitly.

Block dimensions reference parameters: `{ "kind":"block", "id":"stock", "width":"width", "depth":"depth", "height":"thickness" }`.

Corner cut: `{ "kind":"corner_cut", "id":"corner", "input":"stock", "size":"corner_size" }`. For width W, depth D and setback S, it keeps `x+y <= W+D-S`. It removes a triangular prism of volume `S²H/2`. S must be positive and smaller than both W and D. This semantic anchor deliberately avoids naming a transient face index.

### Polygon profiles and extrusion (2026-10-19)

A profile is a separate editable feature on the XY plane:

```json
{"kind":"polygon_profile","id":"outline","vertices":[
  {"id":"origin","x":"zero","y":"zero"},
  {"id":"right","x":"width","y":"zero"},
  {"id":"top","x":"zero","y":"depth"}
]}
```

Each x/y field references a named parameter, including zero or negative coordinates; it is not a literal number or expression. Vertex IDs must be unique within their profile. The implicit closing edge joins the last vertex to the first; do not repeat the first vertex. There must be 3..32 vertices forming one **strictly convex** loop. Either winding is accepted. The exact interior-side test checks every vertex against every edge, rejecting crossings (including stars), concavity, repeated points and collinear corners. Coordinate magnitudes must be at most 1000000 mm. No tolerance-based cleanup is performed.

`{"kind":"extrude","id":"plate","profile":"outline","height":"thickness"}` references an earlier profile and a positive height parameter. It creates a solid from z=0 to z=height. Multiple extrusions may reference one profile; they are independent bodies, not a union. A profile may exist without an extrusion. Corner cuts still accept only blocks, not extrusions.

Parameter edits regenerate profiles and dependent solids together. A failed regeneration leaves the saved document unchanged. The saved model retains its input winding and vertex IDs; extrusion may reverse an internal copy to orient its boundary. Feature/parameter/vertex IDs are stable semantic references, but generated boundary indices are not persistent topology names. There is no vertex insertion/removal operation yet; coordinate edits use the existing parameter operations.

Replies include `profiles` when at least one profile exists, containing `feature_id`, exact `area_mm2`, and `vertices` with `id` and `[x,y,z]` rational-string `position`. Empty `profiles` is omitted so existing recorded replies replay unchanged. The viewer renders unextruded outlines and terminal solids; profile measurements remain available after extrusion. Schema version remains 1 for this additive feature extension. Older binaries cannot open documents containing the new feature kinds; upgrade the engine and MCP adapter together and restart clients to reload tool schemas.

[Runnable example and saved stages](../examples/ai-cad/profile-extrusion/README.md).

Every block, extrusion and cut passes the custom kernel's closed-boundary, orientation, manifold and convexity checks. Fixed values are checked against exact rational values, independently of AI interpretation. A language model can still misunderstand intent; the tool descriptions, preview, preserved parameters and explicit constraints make that inspectable, not infallible.

## Commands

All fields shown below are mandatory; unknown fields are rejected.

| Action | Other fields | Behavior |
|---|---|---|
| `inspect` | none | Current model, geometry, revision, undo/redo availability |
| `preview` | `expected_revision`, `operations`, `preserve` | Evaluates without saving, changing history, or advancing revision |
| `commit` | `expected_revision`, `transaction_id`, `operations`, `preserve` | Validates and atomically publishes a complete edit |
| `undo`, `redo` | `expected_revision`, `transaction_id` | Reverses one edit and advances revision |

Operations are tagged with `op`: `define_parameter`/`set_parameter` take `id, mm`; `adjust_parameter` takes `id, delta_mm`; `add_feature` takes `feature`; `fix_parameter`/`release_parameter` take `id`. Fixing an already-fixed parameter keeps its existing invariant. Changing it requires an explicit release. `preserve` contains existing parameter IDs that must have equal exact values before/after the entire batch, even if a constraint is released.

A successful command returns `result`, including `schema_version:1`, `units:"mm"`, `revision`, `model`, `bodies`, `changed_parameters`, `can_undo`, `can_redo`. Each body carries `feature_id`, the shared boundary schema and exact `volume_mm3`. Preview returns `preview:true`; mutation returns `committed_revision` and `replayed`.

Retries are checked before revision preconditions: an identical transaction ID and canonical request hash acknowledges the original `committed_revision` and returns the **current** model/revision, with `replayed:true`. Reusing an ID for another request gives `transaction_conflict`. A new edit against stale state gives `revision_conflict`; inspect and replan, never blindly update the expected revision.

## Storage

A POSIX advisory lock serializes cooperating host processes using a permanent sibling `.lock` file. Locks release when the process exits. The host reads/checks the snapshot, validates current/history models through Rust, executes the command and writes a complete envelope to a same-directory temporary file. It fsyncs the file, atomically replaces the destination, then fsyncs its parent directory.

Failure before replace returns `save_failed`, leaving the prior snapshot intact. Failure after replace returns `commit_uncertain`: inspect and retry the **identical** transaction. An envelope SHA-256 detects accidental corruption; invalid files are rejected rather than overwritten. Editing snapshots outside the host is unsupported. The native C++ journal/locking code is not reused or implicitly certified by these tests.

Limits: 64 parameters, 32 features, 64 fixed constraints, 128 operations/request, 64 preserve IDs; 128-bit rational numerator/denominator inputs; geometry dimension `(0, 1000000]` mm; 256 KiB host command, 1 MiB Rust input, 16 MiB saved envelope; 64 undo/redo snapshots and 1024 receipts. Revision is bounded to JavaScript's exact integer range. No-op commits fail and do not advance revision. New commits after undo clear redo.

## Diagnostics and repair

Errors carry `code`, `entity`, `message`. Typical codes: `missing_parameter`, `duplicate_id`, `invalid_number`, `dimension_range`, `cut_range`, `invalid_profile`, `profile_limit`, `coordinate_range`, `unsupported_reference`, `constraint_conflict`, `preserve_conflict`, `revision_conflict`, `transaction_conflict`, `invalid_document`, `commit_uncertain`. No failed validation partially changes the model. Agents should repair the identified parameter/reference or ask for an intent decision; unsupported geometry must not be substituted silently.
