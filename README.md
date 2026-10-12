# Fusion recreation

Full-product recreation research and approved design. No recreation application code has been implemented yet.

- [Approved full-product specification](docs/superpowers/specs/2026-10-11-fusion-recreation-design.md)
- [Initial static research findings](docs/research/2026-10-11-fusion-findings.md)
- [Partial command declaration inventory](docs/research/fusion-command-inventory.csv)

The reference is installed Autodesk Fusion 2705.1.15. Raw vendor binaries and resources remain outside this repository in `/Volumes/SamsungSSD1/tools/rea/work/fusion-2705.1.15/`.

Development and engineering computation run on the Mac mini SSD. Read `/Volumes/SamsungSSD1/AGENTS.md` and the project registry. The architecture was approved on 2026-10-11. The foundation plan awaits review before implementation. No product-parity claim is made.

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

## Native foundation (in development)
On 2026-10-12 Ivan authorized autonomous execution of the foundation plan.
The native foundation uses C++20, pinned OCCT/OCAF and planeGCS. Experimental Python probes remain separate.

On the mini, add /Volumes/SamsungSSD1/tools/fusion-recreation/build-env/bin to PATH.
Build tools in that isolated environment are CMake 4.1.2 and Ninja 1.13.0.
With Python 3.12+ and those build tools:
```sh
python3 tools/bootstrap.py --root /Volumes/SamsungSSD1/tools/fusion-recreation/native-deps
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build -j 6
ctest --test-dir build --output-on-failure
```
For other hosts set CAD_DEPS to the dependency root. All downloads must match deps/lock.json.
The initial modeling contract accepts finite coordinates within +/-1e6 mm and positive
dimensions above 1e-7 mm; unsupported scales return diagnostics before native modeling.
