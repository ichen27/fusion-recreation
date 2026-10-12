# Archived and ongoing geometry research

These probes are source-controlled research artifacts. They remain disposable experiments;
saving them here does not promote them to production code.

- 2026-10-11-rational-kernel: exact convex cells.
- 2026-10-11-boundary-kernel: merged planar boundaries and repeated Booleans.
- 2026-10-11-cylinder-kernel: separate analytic parallel-axis cylinders and circular holes.
- 2026-10-11-shared-document: common editing, validation dispatch and JSON persistence.

The first three originated under /Volumes/SamsungSSD1/tools/fusion-recreation/experiments.
Those copies remain unchanged as historical evidence. Future source work belongs here.
Their original README paths, evidence-manifest.json files and recorded result files describe
the original runs. original-snapshot.json records hashes before portability and whitespace edits.
The repository versions use relative helper imports and a portable render-cache location.
New tests run from this checkout; do not treat historical hashes as current-source hashes.

Run all dependency-free suites with `python3 scripts/check.py` from the repository root.
Optional OCCT comparisons run separately; CI does not claim to run OCCT or STEP checks.
Do not commit dependency installations, vendor artifacts or user designs.
