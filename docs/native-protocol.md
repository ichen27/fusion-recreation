# Native runner protocol v1

Start `build/cad-runner --store /SSD/path/to/document --document document`. Existing stores must match the document ID. Internal geometry uses millimeters and radians.

Each JSON line has `protocolVersion:1` and `kind`. Replies include `ok`; errors include code, message and entityIds. Request limit: 4 MiB.

- snapshot: committed revision, feature parameters and body metrics.
- commit: command with documentId, unsigned expectedRevision, transactionId, operation and parameters. Repeat the exact command after a lost reply; changed payload with the same ID conflicts.
- preview: command plus jobId. Receives accepted then previewResult, carrying base revision and proposedRevision. Never commits.
- cancel: active preview jobId. Terminates and reaps its worker.
- exportStep: local output path; exports terminal solid features.
- shutdown: closes supervisor. Preview is terminated; accepted commit finishes. On restart, snapshot/retry resolves its state.

One worker per supervisor; another compute request returns Busy. Multiple supervisors sharing a store serialize commits with a file lock. Reads use one atomically published immutable payload.

Operations:
- CreateSketch / EditSketch: `{featureId, sketch}`.
- Extrude: `{featureId, profileId, depth}`.
- Hole: `{featureId, baseFeatureId, radius, centerMode:0, support:{featureId,role:"top",evolutionIds:["extrude/top"]}}`.
- Undo / Redo: empty parameters. Both create new monotonic revisions.

Sketch fields: entities, constraints. Lines: type="line", id, a=[x,y], b=[x,y], construction. Circles: type="circle", id, center, radius, construction. Constraints: id, kind, entityIds, value. Kind values: 0 coincidence, 1 horizontal, 2 vertical, 3 distance, 4 radius, 5 fixed point. Point selectors use `line:start`, `line:end`, `circle:center`. Fixed point preserves its input position. Distance takes one line ID or two point selectors.

See tools/native_client.py for a constrained rectangle and tools/verify_foundation.py for a full sequence. The explicit --allow-test-faults switch enables testStopWorker for preview cancellation tests only; disabled by default.
