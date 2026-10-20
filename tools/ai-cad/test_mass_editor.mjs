import assert from "node:assert/strict";
import test from "node:test";
import { massRequest } from "./web/mass-editor.mjs";
const state = {
  revision: 7,
  bodies: [{ feature_id: "left" }, { feature_id: "right" }],
};
test("mass selection keeps per-occurrence density and saved revision", () => {
  assert.deepEqual(
    massRequest(state, [
      { feature_id: "left", density: " 1000 " },
      { feature_id: "right", density: "3/7" },
    ]),
    {
      expected_revision: 7,
      parts: [
        { feature_id: "left", density_kg_per_m3: "1000" },
        { feature_id: "right", density_kg_per_m3: "3/7" },
      ],
    },
  );
});
test("invalid, repeated, empty or oversized selections reject before submitting", () => {
  for (const entries of [
    [],
    Array(17).fill({ feature_id: "left", density: "1" }),
    [
      { feature_id: "left", density: "1" },
      { feature_id: "left", density: "2" },
    ],
    [{ feature_id: "missing", density: "1" }],
    [{ feature_id: "left", density: " " }],
  ])
    assert.throws(() => massRequest(state, entries));
  // Native input validation decides whether the supplied number is physically valid.
  assert.equal(
    massRequest(state, [{ feature_id: "left", density: "-1" }]).parts[0]
      .density_kg_per_m3,
    "-1",
  );
});
