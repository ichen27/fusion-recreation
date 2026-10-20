import test from "node:test";
import assert from "node:assert/strict";
import { referenceProposal } from "./web/reference-editor.mjs";
const state = {
  revision: 4,
  bodies: [{ feature_id: "part" }],
  model: { references: { seat: {} } },
};
test("reference edits preserve saved revision and source state", () => {
  const target = { kind: "edge_chain", surfaces: ["a", "b"] };
  const result = referenceProposal(state, " rim ", "part", target);
  assert.equal(result.expected_revision, 4);
  assert.deepEqual(result.operations, [
    { op: "set_reference", id: "rim", feature_id: "part", target },
  ]);
  result.operations[0].target.surfaces[0] = "changed";
  assert.deepEqual(target.surfaces, ["a", "b"]);
  assert.deepEqual(
    referenceProposal(state, "seat", "", null, true).operations,
    [{ op: "remove_reference", id: "seat" }],
  );
});
test("missing, prototype-shaped, ambiguous and invalid inputs are not silently accepted", () => {
  assert.throws(
    () => referenceProposal(state, "__proto__", "", null, true),
    /existing saved/,
  );
  assert.throws(() => referenceProposal(state, "bad name", "part", {}), /1–64/);
  assert.throws(
    () => referenceProposal(state, "seat", "missing", {}),
    /terminal/,
  );
  assert.throws(
    () =>
      referenceProposal(state, "seat", "part", {
        kind: "edge_chain",
        surfaces: ["a", "a"],
      }),
    /distinct/,
  );
});
