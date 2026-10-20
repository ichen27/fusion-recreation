# Original CAD runtime — private development build

This bundle contains the built original Rust engine, editable Python host/viewer sources, browser assets and sample native documents. No Rust toolchain is needed to run it. It is a bounded development workbench, not a completed general CAD product. The project distribution license has not been selected; this archive is a development-validation build, without a new redistribution license grant. Existing third-party notices are included under `third-party/`.

Requires Python3.14+, macOS/Linux matching the archive's operating system and CPU architecture, and a WebGL2 browser. The manifest records the tested OS; compatibility with other OS releases is not established. Windows is unsupported because the host uses POSIX locking. The geometry runs on the host CPU; the browser GPU displays disposable meshes.

## Verify and run

Extract the archive, open a terminal in `original-cad/`, then run:

```sh
python3 cad.py doctor
python3 cad.py viewer --store ../my-part.cad.json
```

Open http://127.0.0.1:8765 and use **New sketch / solid** or **New solid stock**. An empty path starts a new document; an existing native file reopens it. Documents must live outside the bundle so replacing the runtime does not overwrite your work.

To try the modelling alpha, copy one of `samples/rectangular-plate.cad.json`, `samples/counterbored-mount.cad.json` or `samples/turned-spacer.cad.json` outside the bundle and pass its path to `viewer --store`. The rectangle keeps its width/depth relationships; the mount includes a named shoulder and rim. **New sketch / solid → Constrained rectangle** creates a new dimension-driven outline. **Named references** manages authored analytic surfaces and connected edge chains; these survive dimension edits and reject structural changes until explicitly rebound or removed.

To explore the included material example:

```sh
cp samples/materials.cad.json ../material-example.cad.json
python3 cad.py viewer --store ../material-example.cad.json
```

Select a part, edit dimensions or materials, preview and save. Undo retains native history. Drawing/section exports and STL downloads are available for supported geometry. Native files preserve editable intent; STL is a derived mesh. General curved operations, joints, freeform surfaces and manufacturing completeness remain open.

The doctor verifies file hashes, runs the actual engine, and exercises preview/save/reopen/undo, assigned mass and a section in a temporary document. It does not edit your documents. The optional MCP status is separate: core checks can pass while the current Python has missing or mismatched MCP packages. MCP startup requires the pinned environment; use the virtual-environment commands below. Hashes detect accidental file changes; they are not a signed trust guarantee. Each launch verifies the bundle and rejects mismatched platforms, missing files or changed contents. Keep edited source in a separate development checkout and rebuild the bundle.

The CLI accepts the same JSON commands as the full checkout:

```sh
printf '%s\n' '{"action":"inspect"}' | python3 cad.py command --store ../my-part.cad.json
```

## Optional MCP adapter

The viewer and command interface need no Python packages. MCP dependencies are optional and are not bundled:

```sh
python3 -m venv ../cad-mcp-env
../cad-mcp-env/bin/python -m pip install -r requirements.lock
../cad-mcp-env/bin/python cad.py mcp --store ../my-part.cad.json
```

Configure your agent client's stdio command with the absolute virtual-environment Python path and arguments `["/absolute/path/original-cad/cad.py", "mcp", "--store", "/absolute/path/my-part.cad.json"]`. Use the same document for viewer and MCP. Provider authentication stays in the agent client; no model subscription or embedded inference is included here.

Optional STEP export adapters are included as source but require the separate dependencies in `step-requirements.txt`; they are not installed by the runtime or included in its core smoke checks. They serve as interoperability adapters, not modeling fallbacks.

The host binds loopback only. For a remote computation host, forward the viewer port through your existing authenticated SSH connection (`ssh -L 8765:127.0.0.1:8765 user@host`) and launch MCP on that same host. This bundle does not configure remote access or install a background service.

## Provenance and updates

`manifest.json` records the exact source commit, whether it was dirty, build platform/compiler and every bundled file hash. A development-marked archive is not a release artifact. Editable implementation and full geometry tests are in the source repository linked there. `engine-Cargo.lock` and `third-party/index.json` record native dependencies and their copied notices; Python dependencies remain in `requirements.lock`.

To update, unpack a new verified bundle alongside the old one and point viewer/MCP commands to it while retaining external document files. Restart both clients. New material-bearing files require a material-aware engine; older engines reject them rather than silently discarding assignments. No automatic downgrade or document migration is performed.
