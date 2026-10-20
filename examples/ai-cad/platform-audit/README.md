# Current-stack local integration audit

[verification.json](verification.json) records137 existing CI verification commands
run sequentially on macOS ARM64 against source `5a449785c59c3351f2080ab4d4c6390473f2d738`.
136 passed initially. The generic MCP negotiation test rejected five newly added
public tools because its exact expected tool list was stale.

The test retains exact tool-set equality. Expected tools were added on their
introducing branches and merged forward through PR71–78 without force-pushing or
rewriting shared history. The full negotiation/edit scenario was rerun successfully
on all eight affected branches. Their original and repaired commit IDs are recorded.
The effective result is137 passing verification commands after this correction;
this is not a claim that the first run passed unchanged.

The commands cover actual stdio MCP, recorded browser/native workflows, independent
geometry/moment comparisons and STEP export/readback. Additional local checks:

- 307 document-host Python tests and85 browser-logic tests.
- 28 Rust model tests, Rust formatting and Clippy.
- 104 Python geometry research tests across five suites.
- 11 tests for the separate C++ foundation, plus its create/edit/reopen/STEP scenario.
- Python formatting/lint and changed browser-source formatting.
- [Packaged runtime](../runtime-bundle/README.md): clean-source build, isolated
  doctor/CLI/HTTP,46 assets and4 actual MCP reads, including inventory.

The audit is local evidence, not a replacement for required GitHub checks or a
cross-platform certification. Hosted jobs refuse to start because of the account's
billing/spending-limit error. PR58–78 remain unmerged. No check was bypassed.
The retained runtime manifest identifies its source independently of this report.
Later report/artifact commits do not imply an unrecorded rerun of every command.

No personal working CAD document was used. Temporary documents and browser servers
were isolated and closed. Full platform capabilities—general curved geometry,
nonlinear sketch solving, reusable assemblies/joints, manufacturing annotations,
CAM/CAE and product distribution—remain incomplete.
