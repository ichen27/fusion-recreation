# Fusion recreation operating guide

Repository: https://github.com/ichen27/fusion-recreation (public).
Canonical checkout: /Volumes/SamsungSSD1/code/fusion-recreation on the Mac mini.
Read /Volumes/SamsungSSD1/AGENTS.md and the registry before edits.

## Architecture and scope
Current objective (2026-10-15): an original AI-native CAD/3D modeling engine.
For Rust model, subscription-client MCP, document host or viewer work, read
tools/ai-cad/README.md and docs/ai-cad-contract.md; validation is listed there.
For modelling alpha work, read docs/modelling-alpha.md and retain the three-part
acceptance corpus in examples/ai-cad/modelling-alpha. Test on synthetic documents;
the registered personal model is not a test fixture.
crates/model-engine currently depends on the exact boundary research crate.
Preserve the earlier browser/OCCT architecture and headless C++ foundation as a separate track.
include/cad and src contain original native application code; see docs/native-protocol.md.
experiments/ contains disposable research source, not production application code.
Keep each probe isolated; document precision, supported geometry, failure modes and evidence.
Never silently route custom-kernel geometry operations through OCCT.
The native application explicitly uses OCCT/OCAF and a pinned planeGCS adapter.
Separate custom-kernel experiments use OCCT only for comparisons/export adapters.
Vendor binaries, user design files, caches, environments and credentials stay outside Git.

## Setup and validation
Python 3.9+ runs the dependency-free modeling tests:
`python3 scripts/check.py`
Optional comparisons need each probe's comparison-requirements.txt; on the mini use
/Volumes/SamsungSSD1/tools/fusion-recreation/comparison-env/bin/python.
Run comparison scripts from their experiment directory. Do not install dependencies on the MacBook.
Tests run independently to avoid collisions between the prototype module names.

Native setup: add /Volumes/SamsungSSD1/tools/fusion-recreation/build-env/bin to PATH.
Run tools/bootstrap.py with the SSD native-deps root, then CMake configure/build and
ctest --test-dir build --output-on-failure. Run python3 tools/verify_foundation.py
for the real runner fixture. Dependencies are pinned in deps/lock.json.
Use semantic references, explicit diagnostics and monotonic revisions. Never silently
replace unsupported CAD geometry with a mesh. See foundation-results.md for limits.

## GitHub workflow
Use focused feature branches. Inspect status, fetch origin and review upstream before edits.
Commit and push meaningful checkpoints and all intended source changes before handing back.
Verify local HEAD equals the remote branch SHA. Never imply local commits are backed up.
Open a PR with scope, validation and limitations; inspect the diff and current-revision CI.
Merge only when authorized, checks pass and any required reviews are satisfied.
Never push implementation directly to main or bypass checks.
Update Obsidian with durable decisions and links. No unattended autosave daemon is installed;
agents must push explicitly as part of their work.
