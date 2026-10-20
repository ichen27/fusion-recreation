import test from "node:test";
import assert from "node:assert/strict";
import { pickBody, projectVertex } from "./web/picking.mjs";
import { packVertices, displayFrame, fittedZoom } from "./web/display-data.mjs";
const camera = { yaw: 0, pitch: 0, zoom: 1, aspect: 1 };
const triangle = (y) => [
  [-0.8, y, -0.8],
  [0.8, y, -0.8],
  [0, y, 0.8],
];
const packed = (points) =>
  new Float32Array(points.flatMap((p) => [...p, 0.3, 0.6, 0.5]));
const group = (id, first = 0) => ({ feature_id: id, first, count: 3 });
test("frontmost solid wins independent of body order, with stable coplanar ties", () => {
  const data = packed([...triangle(0), ...triangle(-1)]);
  const groups = [group("back"), group("front", 3)];
  assert.equal(pickBody(data, groups, camera, 0, 0), "front");
  assert.equal(pickBody(data, groups.toReversed(), camera, 0, 0), "front");
  assert.equal(
    pickBody(packed([...triangle(0), ...triangle(0)]), groups, camera, 0, 0),
    "back",
  );
  assert.equal(pickBody(data, groups, camera, 0.9, 0.9), null);
});
test("projection and picking agree across orbit, aspect, zoom and rebasing", () => {
  const points = [
    [1e6, 1e6, 0.001],
    [1e6 + 0.001, 1e6, 0.001],
    [1e6, 1e6, 0.002],
  ];
  const { center, extent } = displayFrame(points);
  const data = packVertices(
    points.flatMap((p) => [...p, 0.3, 0.6, 0.5]),
    [],
    center,
    extent,
  );
  for (const yaw of [-1, 0, 0.7])
    for (const pitch of [-0.8, 0, 0.9])
      for (const aspect of [0.4, 1, 2])
        for (const zoom of [0.5, 1]) {
          const c = { yaw, pitch, aspect, zoom: fittedZoom(zoom, aspect) };
          const projected = [0, 1, 2].map((i) =>
            projectVertex(Array.from(data.subarray(i * 6, i * 6 + 3)), c),
          );
          const x = projected.reduce((n, p) => n + p[0], 0) / 3,
            y = projected.reduce((n, p) => n + p[1], 0) / 3;
          assert.equal(pickBody(data, [group("tiny")], c, x, y), "tiny");
        }
});
test("missing triangles, collapsed faces, clipping and a hole stay unselected", () => {
  assert.equal(pickBody(packed(triangle(0)), [], camera, 0, 0), null);
  assert.equal(
    pickBody(
      packed([
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
      ]),
      [group("bad")],
      camera,
      0,
      0,
    ),
    null,
  );
  assert.equal(
    pickBody(packed(triangle(10)), [group("clipped")], camera, 0, 0),
    null,
  );
  assert.equal(
    pickBody(packed(triangle(0)), [group("outside")], camera, 2, 0),
    null,
  );
  assert.equal(
    pickBody(
      packed(triangle(0)),
      [group("invalid")],
      { ...camera, aspect: 0 },
      0,
      0,
    ),
    null,
  );
  // Four sides of a planar ring leave the center empty in the displayed surface.
  const outer = [
    [-0.8, -0.8],
    [0.8, -0.8],
    [0.8, 0.8],
    [-0.8, 0.8],
  ];
  const inner = outer.map((p) => p.map((x) => x / 4));
  const ring = [];
  for (let i = 0; i < 4; i++) {
    const j = (i + 1) % 4;
    for (const p of [
      outer[i],
      outer[j],
      inner[j],
      outer[i],
      inner[j],
      inner[i],
    ])
      ring.push([p[0], 0, p[1]]);
  }
  const data = packed(ring),
    groups = [{ feature_id: "ring", first: 0, count: ring.length }];
  assert.equal(pickBody(data, groups, camera, 0, 0), null);
  assert.equal(pickBody(data, groups, camera, 0.6, 0), "ring");
});

test("surface picking returns exact provenance of the visible triangle and retains body fallback", async () => {
  const { pickSurface } = await import("./web/picking.mjs");
  const data = packed([...triangle(0), ...triangle(-1)]);
  const groups = [
    { ...group("copy", 0), triangle_surfaces: ["feature/part/cap/top"] },
    {
      ...group("part", 3),
      triangle_surfaces: ["feature/part/hole/left/upper"],
    },
  ];
  assert.deepEqual(pickSurface(data, groups, camera, 0, 0), {
    feature_id: "part",
    surface_id: "feature/part/hole/left/upper",
  });
  assert.deepEqual(pickSurface(data, [groups[0]], camera, 0, 0), {
    feature_id: "copy",
    surface_id: "feature/part/cap/top",
  });
  assert.deepEqual(pickSurface(data, [group("legacy")], camera, 0, 0), {
    feature_id: "legacy",
    surface_id: null,
  });
  assert.equal(pickSurface(data, groups, camera, 0.99, 0.99), null);
  assert.equal(pickBody(data, groups, camera, 0, 0), "part");
});
