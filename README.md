# Fusion recreation

An original AI-native CAD / 3D modeling engine under development. The first editable Rust workflow now exposes typed commands, constraints, preview/commit, undo, persistence, MCP tools for Codex/Claude Code, and a minimal WebGL viewer. The earlier C++/OCCT foundation remains a separate track. This is not a complete CAD system.

The current workflow supports interactive convex/simple-concave profile extrusion, circular stock, through and flat-bottom blind holes, linked part copies, exact translations and quarter turns of planar and analytic solids, repeated arbitrary-plane cuts, and bounded planar union/difference/intersection. Boolean results can contain cavities, through-holes and disconnected pieces. Exact affine relationships, native history and atomic previews are shared by the browser and typed AI tools. [Runnable examples](examples/ai-cad/README.md) include editable native stages, STEP/STL exports, actual browser recordings and independent geometry checks. Geometry remains bounded; general curved Boolean operations, arbitrary rotations, assemblies and drawings are still ahead.

The [platform delivery plan](docs/platform-delivery-plan.md) tracks the full long-term scope and acceptance gates. [Exact parameter relationships](examples/ai-cad/relationships/README.md) now preserve declared design relationships across edits.

Start with the [AI CAD quickstart](tools/ai-cad/README.md), [command contract](docs/ai-cad-contract.md), and [working demo artifacts](examples/ai-cad/README.md).

- [Approved full-product specification](docs/superpowers/specs/2026-10-11-fusion-recreation-design.md)
- [Initial static research findings](docs/research/2026-10-11-fusion-findings.md)
- [Partial command declaration inventory](docs/research/fusion-command-inventory.csv)

The reference is installed Autodesk Fusion 2705.1.15. Raw vendor binaries and resources remain outside this repository in `/Volumes/SamsungSSD1/tools/rea/work/fusion-2705.1.15/`.

Development and engineering computation run on the Mac mini SSD. Read `/Volumes/SamsungSSD1/AGENTS.md` and the project registry. The architecture was approved on 2026-10-11. The six-task foundation plan has been implemented and reviewed; native CI verifies integration. No product-parity claim is made.

- [Foundation implementation plan](docs/superpowers/plans/2026-10-11-fusion-foundation.md)

- [Custom-kernel feasibility results](docs/research/2026-10-11-custom-kernel-experiment.md): disposable planar-solid probe completed; OCCT remains the app baseline.

- [Merged-boundary experiment](docs/research/2026-10-11-kernel-boundary-experiment.md): internal seams removed for tested planar solids; repeated-cut, cavity and boundary comparisons recorded.

- [Analytic-cylinder experiment](docs/research/2026-10-11-kernel-cylinder-experiment.md): separate parallel-axis curve prototype, 34 OCCT comparisons and a verified STEP demonstration.

## Source and GitHub
Private repository: https://github.com/ichen27/fusion-recreation.
All original prototype source is now preserved in [experiments/](experiments/README.md).
Future source changes are committed on feature branches, pushed at meaningful checkpoints,
checked by GitHub Actions, and reviewed through PRs. See [AGENTS.md](AGENTS.md).
GitHub reflects pushed commits; local edits are not a live autosave.

- [Shared-document experiment](docs/research/2026-10-11-shared-document-experiment.md):
  common editing, validation dispatch and atomic JSON persistence for both research engines.
- Run dependency-free checks: `python3 scripts/check.py`.

- [Shared boundary topology](docs/research/2026-10-12-shared-topology-experiment.md): common analytic face/edge/vertex representation and validation; 54 OCCT comparisons.

- [Custom Rust boundary clipping](experiments/2026-10-15-rust-boundary/README.md):
  original exact plane clipping directly on shared convex planar boundaries, with
  48 OCCT reference comparisons. This continues the custom-engine research;
  the C++ application below still uses OCCT. Source, JSON fixtures, measured
  results and PNG/SVG illustrations are included.

## Native foundation
On 2026-10-12 Ivan authorized autonomous execution of the foundation plan.
The native foundation uses C++20, pinned OCCT/OCAF and planeGCS. Experimental Python probes remain separate.

On the mini, add /Volumes/SamsungSSD1/tools/fusion-recreation/build-env/bin to PATH.
Build tools in that isolated environment are CMake 4.1.2 and Ninja 1.13.0.
With Python 3.12+ and those build tools:
```sh
python3 tools/bootstrap.py --root /Volumes/SamsungSSD1/tools/fusion-recreation/native-deps
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 6
ctest --test-dir build --output-on-failure
```
For other hosts set CAD_DEPS to the dependency root. All downloads must match deps/lock.json.
The initial modeling contract accepts finite coordinates within +/-1e6 mm and positive
dimensions above 1e-7 mm; unsupported scales return diagnostics before native modeling.

The native sketch adapter uses the pinned, unmodified planeGCS sources as a shared
library. Lines and circles support coincidence, horizontal/vertical, distance,
radius and fixed-point constraints. Point references use `entity:start`,
`entity:end`, or `entity:center`. Arc solving currently returns
`UnsupportedEntity`; no polygon approximation is substituted. Boundary extraction
supports one connected line loop; circles are returned separately. Tests report
solver residuals, remaining degrees of freedom, conflicting and redundant IDs.

Run the measured fixture: python3 tools/verify_foundation.py.
Start the local process service: build/cad-runner --store /SSD/path/to/document --document document.
See [protocol](docs/native-protocol.md), [results](docs/research/foundation-results.md),
and [reference status](docs/research/freecad-comparison.md).
Native CTest and independent Python research checks run in GitHub Actions.

### Editable mounting bracket

[Create, resize, reopen and export a flat bracket with analytic round holes](examples/ai-cad/bracket/README.md). Includes native documents, STEP, STL, browser evidence and independent export validation. This is a bounded milestone within the [full platform plan](docs/platform-delivery-plan.md).
