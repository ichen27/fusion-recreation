import test from "node:test";
import assert from "node:assert/strict";
import {
  presetCamera,
  fitCamera,
  orbitCamera,
  panCamera,
  zoomCamera,
  displayCamera,
  projector,
} from "./web/camera.mjs";
import { pickSurface } from "./web/picking.mjs";
const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-12, `${a} != ${b}`);
const pack = (points) =>
  new Float32Array(points.flatMap((p) => [...p, 0, 0, 0]));
test("named views have conventional screen directions and visible outside faces", () => {
  const cases = [
    ["front", [1, 0, 0], [0, 0, 1], [0, -1, 0]],
    ["back", [-1, 0, 0], [0, 0, 1], [0, 1, 0]],
    ["right", [0, 1, 0], [0, 0, 1], [1, 0, 0]],
    ["left", [0, -1, 0], [0, 0, 1], [-1, 0, 0]],
    ["top", [1, 0, 0], [0, 1, 0], [0, 0, 1]],
    ["bottom", [1, 0, 0], [0, -1, 0], [0, 0, -1]],
  ];
  for (const [name, right, up, toward] of cases) {
    const camera = displayCamera(presetCamera(name), 1),
      project = projector(camera);
    near(project(...right)[0], 1);
    near(project(...up)[1], 1);
    near(project(...toward)[2], -0.2);
    const triangles = [-1, 1].flatMap((sign) =>
      [
        [-0.5, -0.5],
        [0.5, -0.5],
        [0, 0.5],
      ].map(([x, y]) =>
        toward.map((v, i) => v * sign * 0.5 + right[i] * x + up[i] * y),
      ),
    );
    const groups = [
      {
        feature_id: "far",
        first: 0,
        count: 3,
        triangle_surfaces: ["far-face"],
      },
      {
        feature_id: "near",
        first: 3,
        count: 3,
        triangle_surfaces: ["outside-face"],
      },
    ];
    assert.deepEqual(
      pickSurface(pack(triangles), groups, camera, 0, 0),
      { feature_id: "near", surface_id: "outside-face" },
      name,
    );
  }
});
test("panning tracks CSS pixels across aspect and preserves surface hit", () => {
  const original = presetCamera("front"),
    panned = panCamera(original, 90, -40, 900, 800);
  assert.deepEqual(panned.pan, [0.2, 0.1]);
  assert.deepEqual(original.pan, [0, 0]);
  const camera = displayCamera(panned, 900 / 800);
  const data = pack([
    [-0.05, 0, -0.05],
    [0.05, 0, -0.05],
    [0, 0, 0.05],
  ]);
  const groups = [
    { feature_id: "part", first: 0, count: 3, triangle_surfaces: ["face"] },
  ];
  assert.equal(pickSurface(data, groups, camera, 0, 0), null);
  assert.equal(pickSurface(data, groups, camera, 0.2, 0.1).surface_id, "face");
  assert.equal(
    pickSurface(data, groups, { ...camera, pan: [NaN, 0] }, 0.2, 0.1),
    null,
  );
});
test("cursor-centered zoom preserves projected point at zoom limits", () => {
  for (const aspect of [0.3, 1, 2])
    for (const delta of [-100000, 100000, -120, 120]) {
      const camera = { ...presetCamera("isometric"), pan: [0.2, -0.3] },
        point = [0.1, 0.2, -0.1];
      const before = projector(displayCamera(camera, aspect))(...point);
      const changed = zoomCamera(camera, delta, before.slice(0, 2));
      const after = projector(displayCamera(changed, aspect))(...point);
      near(before[0], after[0]);
      near(before[1], after[1]);
      assert.ok(changed.zoom >= 0.3 && changed.zoom <= 4);
    }
});
test("fit recenters without changing orientation; orbit remains upright", () => {
  const camera = { ...presetCamera("right"), zoom: 3, pan: [1, -2] };
  assert.deepEqual(fitCamera(camera), presetCamera("right"));
  const rotated = orbitCamera(camera, 100000, 100000);
  assert.ok(rotated.yaw >= -Math.PI && rotated.yaw <= Math.PI);
  near(rotated.pitch, Math.PI / 2);
  near(orbitCamera(rotated, 0, -100000).pitch, -Math.PI / 2);
  assert.throws(() => presetCamera("invalid"), /Unknown/);
});
