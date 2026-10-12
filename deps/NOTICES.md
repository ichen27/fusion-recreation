# Pinned dependency provenance and notices

See lock.json for official source URLs, exact archive SHA-256 hashes and source directories.
Sources and builds live outside Git under CAD_DEPS; bootstrap.py verifies every archive before extraction.

- OCCT 8.0.1: Open Cascade, LGPL-2.1 with OCCT exception. Actual license and exception copied in licenses/occt/.
- planeGCS from FreeCAD 1.1.4: source headers state GNU Library GPL version 2 or later; FreeCAD's LICENSE and applicable source headers are preserved in the downloaded tree. The Boost adjacency wrapper is LGPL-2.1-or-later. Standalone integration does not modify solver algorithms.
- Eigen 3.4.0: MPL-2.0 core with file-specific alternative/additional notices; shipped COPYING files included.
- Boost 1.88.0: Boost Software License 1.0.
- nlohmann/json 3.12.0: MIT.

The application links native dependency libraries dynamically where applicable. Dependency source
and license notices remain available at the pinned locations. This inventory covers the selected
foundation dependencies, not a claim about unselected future engines.

Build tools: CMake 4.1.2 and Ninja 1.13.0 installed in an isolated SSD Python environment.
Compiler used for the first build: Apple clang 17.0.0 (clang-1700.6.3.2), arm64-apple-darwin27.0.0.
