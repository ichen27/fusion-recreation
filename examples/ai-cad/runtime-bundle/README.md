# Portable runtime validation

A private development bundle runs the original engine and workbench without a Rust installation on the destination. It contains the built engine, editable host/browser sources, pinned optional MCP requirements, native samples and third-party notices. This is an internal validation artifact; project distribution licensing and a public product release remain unresolved.

## Downloadable artifact

- [original-cad-darwin-arm64.tar.gz](original-cad-darwin-arm64.tar.gz): macOS ARM64 runtime archive. Extract it and follow its README. Python3.14+ and a WebGL2 browser are required.
- [manifest.json](manifest.json): source commit, tested OS/compiler, exact file hashes and native dependency provenance. The bundle's copy is authoritative for its contents.
- [build.json](build.json): archive SHA-256, size and source state.
- [verification.json](verification.json): actual isolated doctor, CLI,45 HTTP asset checks, preview/save, platform/tamper rejection and3 typed MCP calls.
- [browser.png](browser.png), [browser-audit.json](browser-audit.json): actual packaged WebGL2 viewer, loaded from the extracted bundle; native sample unchanged.

The retained build is tested on the declared Mac mini platform only. The builder supports the macOS/Linux host layout; the new Linux packaging CI check remains unexecuted while GitHub account billing blocks jobs. Windows is unsupported. No signed distribution, installer service, auto-update or embedded model inference is claimed.

## Run

```sh
tar -xzf original-cad-darwin-arm64.tar.gz
cd original-cad
python3 cad.py doctor
python3 cad.py viewer --store ../my-part.cad.json
```

Open http://127.0.0.1:8765. Save documents outside the bundle. For a sample, copy `samples/materials.cad.json` outside the bundle and pass that path instead. The [bundled instructions](../../../tools/ai-cad/runtime-bundle.md) describe optional MCP installation, remote loopback forwarding, source provenance and updates.

## Rebuild and validate

From a clean source checkout with Rust1.85.1 and Python3.14, choose a new output path:

```sh
python tools/ai-cad/package_runtime.py --output work/runtime.tar.gz
python tools/ai-cad/verify_runtime_bundle.py work/runtime.tar.gz --mcp-python /absolute/path/to/pinned-mcp-environment/bin/python
python -m unittest discover -s tools/ai-cad -p 'test_runtime_launcher.py'
```

The builder compiles with the locked Cargo dependencies and remaps development paths before collecting explicitly selected runtime sources. It includes dependency license files and Rust notices. It refuses dirty source unless `--development` is explicit; such scratch builds are marked and are not retained as release artifacts. Archive timestamps and ownership are normalized. Manifest hashes are integrity checks, not signatures or a claim of bitwise reproducibility across different compilers/operating systems.

The verifier extracts into a new directory containing spaces. Core checks use Python `-S`, remove Python package paths and remove Cargo/Rust environment paths. It verifies exact document preview/save/reopen/undo, assigned mass, sections, CLI and real HTTP assets/preview/save. The optional adapter uses its separate pinned environment and an actual stdio MCP session. A changed asset and wrong-platform manifest must be rejected before startup. No personal working document is used.
