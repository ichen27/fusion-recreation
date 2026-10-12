# Shared document experiment

Disposable research code, not the production app or a unified geometry kernel.
This probe gives the existing exact planar and analytic parallel-axis engines a common
document format, feature IDs, editing API, validation entry point and atomic save/reload.
It preserves rational coordinates as JSON strings and rejects implicit precision conversion.

Run dependency-free tests from this directory:
`python3 -m unittest -v`

Optional OCCT comparison (use the cylinder probe's comparison requirements):
`python compare_document.py`
This generates shared-demo.json and document-comparison.json in the working directory.

## Editing example

```python
from document import Document

original = (Document()
    .append("plate", "rectangle", bounds=[-5, -5, 5, 5], z=[0, 4])
    .append("drill", "cylinder", center=[0, 0], radius=1, z=[-1, 5])
    .append("part", "cut", left="plate", right="drill"))
edited = original.replace("drill", center=[0, 0], radius=2, z=[-1, 5])
edited.save("part.json")
restored = Document.load("part.json")
print(restored.evaluate()["part"].summary())
```

replace requires the full parameter set for the selected feature. References use named
features earlier in the list. A replacement replays and validates the whole list before
returning a new immutable document. The original remains usable after failure.
undo removes the last feature; previous immutable documents provide redo snapshots.
A document can contain both backends, but Booleans between backends are explicitly rejected.
Use rectangle and cylinder together for flat plates with circular holes.

## Limits

Feature IDs identify construction steps, not persistent face/edge topology.
Since 2026-10-12, validation also builds the shared analytic boundary and checks edge
ownership, face orientation, vertex links and shell Euler characteristics. Model.topology()
exposes that representation. It does not test general self-intersections or shell nesting.
No mixed-backend Boolean algorithm exists yet. Existing precision/tangency restrictions remain.
Every edit replays all features; the 128-feature and 1 MiB limits bound document size,
not geometry complexity or execution time. This is a trusted local research format,
not a hostile-file processing service. Atomic replacement prevents partial files but
does not implement multi-writer locking or certify power-loss durability.
There is no UI, general fillet tool or arbitrary-axis cylinder operation.
