# Custom engine: first Rust boundary operation

Date: 2026-10-15. Status: bounded research implementation, not an application-engine replacement.

Ivan asked to continue the custom-engine work after discussing Rust. This milestone
continues the October 12 shared boundary representation in a separate Rust probe.
The existing OCCT-backed C++ application is unchanged.

## Result

Rust now clips a closed convex planar boundary by an arbitrary rational plane.
It classifies exact signed distances, intersects crossing edges, trims face loops,
and follows the exposed oriented edge rim to build a closing planar face. It
validates both input and output incidence and convexity. Operations use big integer
fractions throughout; there is no call into an existing CAD engine or Python modeler.

The older Python cell engine already performed restricted convex clipping. The
new milestone is direct operation on the shared representation in Rust, including
conforming subdivisions and coplanar face patches. A lossless Python bridge exposes
returned vertices/edges/faces to the earlier independent topology validator.

## Measured evidence

- 14 end-to-end test methods passed, including 40 deterministic transformed-solid
  cases with exact complementary volume conservation, reference volume checks,
  idempotence and plane-rescaling invariance.
- Exact tests retain a 1e-30-thick solid and correctly clip a small solid translated
  by 1e30. These are arithmetic/geometry tests, not OCCT comparisons or performance claims.
- 48 independent OCCT comparisons passed: complementary half-space cuts and repeated
  cuts on cubes, triangular prisms and rationally transformed/reflected solids.
- Compared validity, shell counts, volume, area and 5,698 bidirectional surface samples.
  Maximum observed volume error: 1.78e-15 mm³; area error: 7.11e-15 mm²;
  sampled surface distance: 1.61e-15 mm.
- Rust unit tests, format check and Clippy with warnings denied passed. The existing
  Python regression runner passed 104 test executions.

[Machine-readable comparison evidence](../../experiments/2026-10-15-rust-boundary/occt-comparison.json)
records source hashes, input-fixture digest, binary hash, base commit and environment.
Finite samples do not prove global equivalence. Linux CI runs its own comparisons;
uploaded CI evidence records that environment separately.

![Actual computed boundary cut](../../experiments/2026-10-15-rust-boundary/boundary-clipping.png)

## Scope and next step

Supported input is one exact convex planar shell (or empty), with bounded sizes
and rational bit lengths. Nonconvex bodies, face holes, curved faces and malformed
boundaries reject explicitly. This is not a unified curved/planar Boolean engine,
and topology indices are not persistent CAD face names. Arbitrary imported B-reps,
general Boolean operations, fillets and application integration remain future work.

Next: compose plane clips into convex solid–solid intersection directly on shared
boundaries, retaining exact checks and independent references. Broader custom-kernel
work must keep OCCT strictly as a reference/export adapter.

[Source, portable quickstart, fixtures, protocol and artifacts](../../experiments/2026-10-15-rust-boundary/README.md).
