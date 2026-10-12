# Fusion recreation operating guide

Repository: https://github.com/ichen27/fusion-recreation (private).
Canonical checkout: /Volumes/SamsungSSD1/code/fusion-recreation on the Mac mini.
Read /Volumes/SamsungSSD1/AGENTS.md and the registry before edits.

## Architecture and scope
The full app has an approved browser/OCCT architecture and a foundation plan awaiting review.
experiments/ contains disposable research source, not production application code.
Keep each probe isolated; document precision, supported geometry, failure modes and evidence.
Never silently route custom-kernel geometry operations through OCCT.
OCCT is used explicitly for reference comparisons and export adapters.
Vendor binaries, user design files, caches, environments and credentials stay outside Git.

## Setup and validation
Python 3.9+ runs the dependency-free modeling tests:
`python3 scripts/check.py`
Optional comparisons need each probe's comparison-requirements.txt; on the mini use
/Volumes/SamsungSSD1/tools/fusion-recreation/comparison-env/bin/python.
Run comparison scripts from their experiment directory. Do not install dependencies on the MacBook.
Tests run independently to avoid collisions between the prototype module names.

## GitHub workflow
Use focused feature branches. Inspect status, fetch origin and review upstream before edits.
Commit and push meaningful checkpoints and all intended source changes before handing back.
Verify local HEAD equals the remote branch SHA. Never imply local commits are backed up.
Open a PR with scope, validation and limitations; inspect the diff and current-revision CI.
Merge only when authorized, checks pass and any required reviews are satisfied.
Never push implementation directly to main or bypass checks.
Update Obsidian with durable decisions and links. No unattended autosave daemon is installed;
agents must push explicitly as part of their work.
