import test from "node:test";
import assert from "node:assert/strict";
import { materialProposal } from "./web/material-editor.mjs";
import { massRequest } from "./web/mass-editor.mjs";
const state = {
  revision: 7,
  model: {
    features: [
      { id: "part", kind: "block" },
      { id: "outline", kind: "planar_profile" },
      { id: "__proto__", kind: "instance" },
    ],
    materials: { part: { name: "Existing", density_kg_per_m3: "1000" } },
  },
  bodies: [{ feature_id: "part" }],
};
test("saved override and clear use ordinary preview transactions", () => {
  const snapshot = structuredClone(state);
  assert.deepEqual(materialProposal(state, "part", " Test ", " 2000/2 "), {
    expected_revision: 7,
    operations: [
      {
        op: "set_material",
        feature_id: "part",
        material: { name: "Test", density_kg_per_m3: "2000/2" },
      },
    ],
    preserve: [],
  });
  assert.deepEqual(materialProposal(state, "part", "", "", true).operations, [
    { op: "clear_material", feature_id: "part" },
  ]);
  assert.deepEqual(state, snapshot);
});
test("sketches, missing overrides and prototype-shaped IDs do not fabricate materials", () => {
  assert.throws(
    () => materialProposal(state, "outline", "Name", "1000"),
    /solid feature/,
  );
  assert.throws(
    () => materialProposal(state, "__proto__", "", "", true),
    /no direct/,
  );
  assert.throws(() => materialProposal(state, "part", " ", "1000"), /name/);
});
test("assigned mass sends IDs without replacing absent materials with invented densities", () => {
  assert.deepEqual(massRequest(state, [{ feature_id: "part" }], true), {
    expected_revision: 7,
    feature_ids: ["part"],
  });
  assert.throws(
    () =>
      massRequest(
        state,
        [{ feature_id: "part" }, { feature_id: "part" }],
        true,
      ),
    /once/,
  );
  assert.throws(() => massRequest(state, [{ feature_id: "part" }]), /density/);
});
