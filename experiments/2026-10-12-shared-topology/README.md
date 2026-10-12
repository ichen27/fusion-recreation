# Shared analytic boundary topology — research experiment

Both earlier geometry engines now adapt into the same immutable vertices, analytic edges,
oriented edge uses, face loops, plane/cylinder surfaces and connected shells.

Run from this directory:
- `python3 -m unittest -v`: dependency-free positive and damaged-boundary tests.
- `python compare_topology.py`: optional OCCT comparison of the common geometry.
- `python render_topology.py`: optional VTK/OCCT/Matplotlib visualization.

For optional tools, use the existing comparison environment or the cylinder experiment's
comparison-requirements.txt. Run the whole repository with `python3 scripts/check.py`.

## Representation and precision

Planar coordinates and subdivisions remain exact Fractions; the adapter uses zero tolerance.
Curved boundaries retain circle arcs and cylindrical walls. Full circles and long arcs split
into patches spanning at most 90 degrees, avoiding a periodic edge being used twice by one face.
These are modeling patches, not triangles. Extra coplanar/co-cylindrical seams can remain.

The curved adapter uses 8 * max(1e-9, coordinate_scale * 1e-12) mm for shared-vertex matching,
derived from the existing curve engine's numerical policy. Multiple matching vertices reject
as ambiguous. Every edge is subdivided at incident vertices before common edge ownership is
assembled; circle identity also checks center, radius and midpoint, not just endpoints.
Cap holes are assigned to containing outer loops using an analytic horizontal-ray test.

## Validation

The same validator checks:
- finite coordinates and supported dimensions;
- curve endpoints against vertices and supporting surfaces;
- closed face loops and face orientation;
- exactly two opposite uses per edge;
- connected cyclic face links around each vertex;
- connected shells and orientable Euler characteristics, counting face holes correctly.

The shared document's Model.topology() exposes this representation; document validation,
parameter rebuild and save/reload now run the checker in addition to existing backend checks.

## What this does not prove

This is an adapter and incidence-validation experiment, not a general Boolean kernel.
No face-face intersection test, shell nesting/material classification, exhaustive geometric
self-intersection check, persistent topology naming, arbitrary-axis cylinder support, or
general imported-B-rep validation is implemented. The low-level dataclasses are for trusted
internally generated models, not a public parser for arbitrary objects.
Positive examples and finite surface samples do not certify all possible geometry.
Planar and curved Boolean operations still run in separate original engines; cross-backend
operations remain rejected.

The optional OCCT adapter builds planar wires directly. A 3D wire alone lacks cylinder
p-curves, so cylindrical export verifies a rectangular angle/z domain and uses OCCT's bounded
surface constructor. Sewing may rebuild edge subdivisions. Consequently the OCCT comparison
checks surface geometry, shell count, area and volume, not one-to-one exported edge IDs.

## Evidence

19 new test methods cover the existing planar and curved corpora plus damaged edges/faces,
wrong surfaces, nonfinite values, exact 1e-30 thickness, through/blind holes, cavities and
point-touching shells. Full runner: 104 executions, including 14 duplicated baseline methods.
54 OCCT comparisons passed with 16,045 bidirectional surface samples; detailed measurements
are in topology-comparison.json. The image includes a deliberately removed top face, rejected
by the actual checker.
