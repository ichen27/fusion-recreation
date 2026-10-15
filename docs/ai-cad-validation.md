# AI CAD workflow validation — 2026-10-15

Platform: Apple M4 Mac mini, macOS, arm64; Rust 1.85.1; Python 3.14.3. The Rust kernel, Python document host and browser renderer are original source; optional transport uses MCP Python SDK 2.3.0.

## Observed results

- 18 contract/HTTP integration tests passed against the actual release Rust executable. Covered exact two-turn geometry, fixed and preserved dimensions, atomic failed batches, malformed inputs, unsupported references, unrelated bodies, undo/redo across reopening, redo branching, checksum rejection, exact retries after later edits, injected failures before/after snapshot publication, and competing processes at one revision. HTTP checks cover viewer/store agreement and origin/host/path restrictions.
- Official MCP stdio client successfully initialized, discovered all four typed tools, inspected, created, previewed, widened, undid and received a structured constraint diagnostic. Preview did not increment the saved revision.
- Rust format and Clippy with warnings denied passed; Python Ruff lint/format passed; JavaScript syntax and Prettier passed. Existing 104 Python research tests also passed.
- Browser inspected at 1440×900: actual WebGL 2 solid rendered; corner and thickness inputs locked. Editing width 120→140 produced a preview volume 100,200 mm³, then saved revision 3; undo produced revision 4, width 120 and volume 85,800 mm³. Browser reported no JavaScript errors.
- Included fixtures record create volume 71,400 mm³ and widen volume 85,800 mm³. Saved demo document reopens with editable named parameters and history.

The browser screenshot is [included](../examples/ai-cad/viewer.png). It shows the initial two-turn result at revision 2; subsequent UI tests used the disposable working copy, not the distributed snapshot.

## Boundaries of this evidence

MCP transport was tested with the official SDK client, not a new signed-in Codex/Claude conversation. No provider credential, account configuration or paid inference was used by the test harness. Natural-language quality and subscription-client configuration remain to be evaluated in a fresh client session. The deterministic fixtures should not be described as recorded model outputs.

File/directory fsync failure injection is not physical power-loss certification. Geometry is limited to the supported exact planar feature subset; this evidence does not establish general CAD robustness or large-document performance. WebGL 2 rendering does not implement GPU geometry computation. CI repeats model/transport checks on Linux; browser verification here is manual, not an automated visual regression suite.
