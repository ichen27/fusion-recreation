import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import {
  rotationDraft,
  rotationProposal,
  pivotEditable,
} from "./web/rotation-model.mjs";
const root = fileURLToPath(new URL("../../", import.meta.url));
function run(model, proposal = { operations: [], preserve: [] }) {
  const { operations, preserve } = proposal;
  const p = spawnSync(
    `${root}/crates/model-engine/target/release/model-engine`,
    {
      input: JSON.stringify({ schema_version: 1, model, operations, preserve }),
      encoding: "utf8",
    },
  );
  assert.ok(p.stdout, p.stderr);
  return JSON.parse(p.stdout);
}
function initial() {
  return {
    revision: 1,
    ...run({
      parameters: { w: "40", d: "20", h: "10" },
      fixed: {},
      features: [
        { kind: "block", id: "stock", width: "w", depth: "d", height: "h" },
      ],
    }).result,
  };
}
test("browser quarter-turn preserves dimensions and edits axis/angle in place", () => {
  let state = initial(),
    draft = rotationDraft(state, "stock");
  draft.values = ["20", "10", "0"];
  const proposal = rotationProposal(state, draft);
  assert.deepEqual(proposal.preserve, ["d", "h", "w"]);
  state = { revision: 2, ...run(state.model, proposal).result };
  assert.equal(state.bodies[0].volume_mm3, "8000");
  assert.equal(
    Math.min(...state.bodies[0].boundary.vertices.map((p) => Number(p[0]))),
    10,
  );
  assert.equal(
    Math.min(...state.bodies[0].boundary.vertices.map((p) => Number(p[1]))),
    -10,
  );
  draft = rotationDraft(state, null, "turn1");
  assert.throws(() => rotationProposal(state, draft), /Change/);
  draft.turns = 2;
  assert.equal(
    rotationProposal(state, draft).operations[0].op,
    "replace_feature",
  );
  assert.equal(
    run(state.model, rotationProposal(state, draft)).result.bodies[0]
      .volume_mm3,
    "8000",
  );
  draft.axis = "y";
  assert.ok(run(state.model, rotationProposal(state, draft)).result);
  draft.turns = 0;
  assert.throws(() => rotationProposal(state, draft), /90/);
  assert.throws(() => rotationDraft(state, "stock"), /terminal/);
});
test("fixed, derived and shared pivots retain coordinate rules", () => {
  let state = initial(),
    draft = rotationDraft(state, "stock");
  state = {
    revision: 2,
    ...run(state.model, rotationProposal(state, draft)).result,
  };
  state.model.fixed["turn1.x"] = "0";
  draft = rotationDraft(state, null, "turn1");
  draft.values[0] = "5";
  assert.equal(pivotEditable(state, "turn1.x"), false);
  assert.throws(() => rotationProposal(state, draft), /fixed or derived/);
  delete state.model.fixed["turn1.x"];
  state.model.relations = {
    "turn1.x": { offset_mm: "0", terms: { w: "1/2" } },
  };
  assert.equal(pivotEditable(state, "turn1.x"), false);
  delete state.model.relations;
  draft.pivot = ["turn1.x", "turn1.x", "turn1.z"];
  draft.values = ["1", "2", "0"];
  assert.throws(() => rotationProposal(state, draft), /Shared/);
});
