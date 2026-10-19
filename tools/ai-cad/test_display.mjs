import test from "node:test";
import assert from "node:assert/strict";
import {
  packVertices,
  formatMeasurement,
  displayFrame,
  fittedZoom,
} from "./web/display-data.mjs";

test("tiny offset cylinder retains shape before float32 upload", () => {
  const radius = 0.001,
    height = 0.0011,
    extent = radius * 2 * 0.85;
  const colors = [0.2, 0.5, 0.7];
  const vertices = (offset) =>
    Array.from({ length: 64 }, (_, i) => {
      const angle = (i * 2 * Math.PI) / 64;
      return [
        offset + radius * Math.cos(angle),
        offset + radius * Math.sin(angle),
        (i % 2) * height,
        ...colors,
      ];
    }).flat();
  const origin = packVertices(vertices(0), [], [0, 0, height / 2], extent);
  const far = vertices(1000000);
  const old = new Float32Array(far);
  assert.equal(new Set(old.filter((_, i) => i % 6 === 0)).size, 1);
  const local = packVertices(far, [], [1000000, 1000000, height / 2], extent);
  assert.ok(new Set(local.filter((_, i) => i % 6 === 0)).size > 30);
  origin.forEach((value, i) =>
    assert.ok(Math.abs(value - local[i]) < 1e-7, `element ${i}`),
  );
});

test("triangle and line offsets/colors survive CPU rebasing", () => {
  const a = [101, 202, 303, 0.2, 0.4, 0.8],
    b = [99, 198, 297, 0.1, 0.3, 0.7];
  const packed = packVertices(a, b, [100, 200, 300], 2);
  assert.deepEqual(
    [...packed],
    [
      ...new Float32Array([
        0.5,
        1,
        1.5,
        ...a.slice(3),
        -0.5,
        -1,
        -1.5,
        ...b.slice(3),
      ]),
    ],
  );
  assert.equal(packVertices([], [], [0, 0, 0], 1).length, 0);
  assert.throws(() => packVertices(a, [], [0, 0, 0], 0), /extent/);
  assert.throws(() => packVertices([1], [], [0, 0, 0], 1), /interleaved/);
});

test("nonzero small measurements never display as rounded zero", () => {
  assert.equal(formatMeasurement((11 / 1e10) * Math.PI, "en-US"), "3.456E-9");
  assert.equal(formatMeasurement(1e-6, "en-US"), "1E-6");
  assert.equal(formatMeasurement(-1e-6, "en-US"), "-1E-6");
  assert.equal(formatMeasurement(0, "en-US"), "0");
  assert.equal(formatMeasurement(0.001, "en-US"), "0.001");
  assert.equal(formatMeasurement(1234.56789, "en-US"), "1,234.568");
});

test("fit contains oblique solids at every sampled angle and aspect", () => {
  const points = [
    [10, 0, 0],
    [54, 0, 0],
    [10, 44, 0],
    [10, 0, 44],
  ];
  const { center, extent } = displayFrame(points);
  for (const yaw of [-3, -1, -0.65, 0, 1, 3])
    for (const pitch of [-3, -1, 0, 0.65, 1, 3])
      for (const aspect of [0.2, 0.5, 1, 2, 5]) {
        for (const point of points) {
          const p = point.map((v, i) => (v - center[i]) / extent);
          const x = Math.cos(yaw) * p[0] - Math.sin(yaw) * p[1];
          const y = Math.sin(yaw) * p[0] + Math.cos(yaw) * p[1];
          const screenY = -Math.sin(pitch) * y + Math.cos(pitch) * p[2];
          const scale = fittedZoom(1, aspect);
          assert.ok(Math.abs((x * scale) / aspect) <= 1 / 1.15 + 1e-12);
          assert.ok(Math.abs(screenY * scale) <= 1 / 1.15 + 1e-12);
        }
      }
  assert.equal(fittedZoom(2, 0.5), 1);
  assert.deepEqual(displayFrame([]), { center: [0, 0, 0], extent: 1 });
});

test("frame handles large point arrays and preserves tiny offset extents", () => {
  const points = Array.from({ length: 200000 }, (_, i) => [
    i % 100,
    i % 70,
    i % 30,
  ]);
  const frame = displayFrame(points);
  assert.deepEqual(frame.center, [49.5, 34.5, 14.5]);
  assert.ok(frame.extent > 0);
  const tiny = displayFrame([
    [1e6, 1e6, 0],
    [1e6 + 0.001, 1e6 + 0.001, 0.001],
  ]);
  assert.ok(tiny.extent > 0.0009 && tiny.extent < 0.0011);
  assert.throws(() => displayFrame([[Infinity, 0, 0]]), /finite/);
});
