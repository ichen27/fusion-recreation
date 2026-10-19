import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import {
  planeDraft,
  planeProposal,
  offsetEditable,
} from "./web/plane-model.mjs";
const root = fileURLToPath(new URL("../../", import.meta.url));
function run(model, proposal = { operations: [], preserve: [] }) {
  const p = spawnSync(
    `${root}/crates/model-engine/target/release/model-engine`,
    {
      input: JSON.stringify({
        schema_version: 1,
        model,
        operations: proposal.operations,
        preserve: proposal.preserve,
      }),
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
      parameters: { size: "60" },
      fixed: {},
      features: [
        {
          kind: "block",
          id: "stock",
          width: "size",
          depth: "size",
          height: "size",
        },
      ],
    }).result,
  };
}
test("browser creates sequential planes and edits an upstream plane", () => {
  let state = initial(),
    d = planeDraft(state, "stock");
  d.normal = ["1", "1", "1"];
  d.value = "60";
  const proposal = planeProposal(state, d);
  assert.equal(proposal.expected_revision, 1);
  state = { revision: 2, ...run(state.model, proposal).result };
  assert.equal(state.bodies[0].volume_mm3, "36000");
  assert.throws(() => planeDraft(state, "stock"), /terminal/);
  d = planeDraft(state, "plane1");
  d.normal = ["-1", "0", "0"];
  d.value = "-10";
  state = { revision: 3, ...run(state.model, planeProposal(state, d)).result };
  assert.equal(state.bodies[0].volume_mm3, "62500/3");
  d = planeDraft(state, null, "plane1");
  d.value = "54";
  assert.equal(
    run(state.model, planeProposal(state, d)).result.bodies[0].volume_mm3,
    "42592/3",
  );
  d.value = "10";
  assert.equal(
    run(state.model, planeProposal(state, d)).error.code,
    "empty_solid",
  );
});
test("normal replacement, unchanged draft and constrained offset semantics", () => {
  let state = initial(),
    d = planeDraft(state, "stock");
  d.normal = ["1", "1", "1"];
  d.value = "60";
  state = { revision: 2, ...run(state.model, planeProposal(state, d)).result };
  d = planeDraft(state, null, "plane1");
  assert.throws(() => planeProposal(state, d), /Change/);
  d.normal = ["1", "0", "0"];
  assert.equal(planeProposal(state, d).operations[0].op, "replace_feature");
  assert.equal(
    run(state.model, planeProposal(state, d)).result.bodies[0].volume_mm3,
    "216000",
  );
  state.model.fixed[d.offset] = "60";
  d = planeDraft(state, null, "plane1");
  assert.equal(offsetEditable(state, d), false);
  d.value = "20";
  assert.throws(() => planeProposal(state, d), /fixed or derived/);
  delete state.model.fixed[d.offset];
  state.model.relations = {
    [d.offset]: { offset_mm: "0", terms: { size: "1" } },
  };
  assert.equal(offsetEditable(state, d), false);
});
