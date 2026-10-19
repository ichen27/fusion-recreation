import test from "node:test";
import assert from "node:assert/strict";
import { packVertices, formatMeasurement } from "./web/display-data.mjs";

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
