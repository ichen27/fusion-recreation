import test from "node:test";
import assert from "node:assert/strict";
import { edgeVertices } from "./web/edge-display.mjs";
import { packVertices } from "./web/display-data.mjs";
const points = (rows) =>
  Array.from({ length: rows.length / 6 }, (_, i) =>
    rows.slice(6 * i, 6 * i + 3),
  );
test("line endpoints and display rebasing preserve the measured world locations", () => {
  const measurement = {
    endpoints_mm: [
      ["1000000", "-2/3", "0"],
      ["1000000001/1000", "1/3", "4"],
    ],
    curve: { kind: "line" },
  };
  const before = structuredClone(measurement),
    rows = edgeVertices(measurement);
  assert.deepEqual(points(rows), [
    [1e6, -2 / 3, 0],
    [1e6 + 0.001, 1 / 3, 4],
  ]);
  const rebased = packVertices([], rows, [1e6, 0, 2], 4);
  assert.ok(Math.abs(rebased[6] - 0.00025) < 1e-10);
  assert.deepEqual(measurement, before);
});
test("positive quarter arcs follow every signed axis and keep exact supplied endpoints", () => {
  const center = [3, -7, 11],
    radius = 5;
  for (let axisIndex = 0; axisIndex < 3; axisIndex++)
    for (const sign of [-1, 1]) {
      const axis = [0, 0, 0];
      axis[axisIndex] = sign;
      const radialIndex = (axisIndex + 1) % 3,
        tangentIndex = (axisIndex + 2) % 3;
      const a = [...center],
        b = [...center];
      a[radialIndex] += radius;
      b[tangentIndex] += sign * radius;
      const measurement = {
        endpoints_mm: [a, b].map((p) => p.map(String)),
        curve: {
          kind: "quarter_circle",
          center: center.map(String),
          radius: "5",
          axis,
        },
      };
      const sampled = points(edgeVertices(measurement));
      assert.equal(sampled.length, 33);
      assert.deepEqual(sampled[0], a);
      assert.deepEqual(sampled.at(-1), b);
      for (const p of sampled) {
        assert.equal(p[axisIndex], center[axisIndex]);
        assert.ok(
          Math.abs(Math.hypot(...p.map((v, i) => v - center[i])) - radius) <
            1e-12,
        );
        assert.ok(p[radialIndex] >= center[radialIndex] - 1e-12);
        assert.ok(sign * (p[tangentIndex] - center[tangentIndex]) >= -1e-12);
      }
      // Display approximation changes sample count, never endpoint/native length data.
      assert.equal(points(edgeVertices(measurement, 1)).length, 2);
      assert.deepEqual(points(edgeVertices(measurement, 256)).at(-1), b);
    }
});
test("display refuses nonfinite coordinates, unsupported curves and unbounded sampling", () => {
  const line = {
    endpoints_mm: [
      ["0", "0", "0"],
      ["1", "0", "0"],
    ],
    curve: { kind: "line" },
  };
  for (const n of [0, -1, 1.5, 257, Infinity])
    assert.throws(() => edgeVertices(line, n));
  assert.throws(() => edgeVertices({ ...line, curve: { kind: "spline" } }));
  assert.throws(() =>
    edgeVertices({
      ...line,
      endpoints_mm: [
        ["1/0", "0", "0"],
        ["1", "0", "0"],
      ],
    }),
  );
});
