import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import {
  patternDraft,
  patternProposal,
  stepEditable,
} from "./web/pattern-model.mjs";
const binary = fileURLToPath(
  new URL(
    "../../crates/model-engine/target/release/model-engine",
    import.meta.url,
  ),
);
function run(model, proposal = { operations: [], preserve: [] }) {
  const result = spawnSync(binary, {
    input: JSON.stringify({
      schema_version: 1,
      model,
      operations: proposal.operations,
      preserve: proposal.preserve,
    }),
    encoding: "utf8",
  });
  assert.ok(result.stdout, result.stderr);
  return JSON.parse(result.stdout);
}
function initial() {
  return {
    revision: 1,
    ...run({
      parameters: { w: "40", d: "30", h: "20" },
      fixed: {},
      features: [
        { kind: "block", id: "stock", width: "w", depth: "d", height: "h" },
      ],
    }).result,
  };
}
test("create, edit count/spacing, merge overlapping copies and keep source", () => {
  let state = initial(),
    draft = patternDraft(state, "stock");
  state = {
    revision: 2,
    ...run(state.model, patternProposal(state, draft)).result,
  };
  assert.equal(state.bodies[0].volume_mm3, "72000");
  assert.equal(state.bodies[0].components.length, 3);
  assert.throws(() => patternDraft(state, "stock"), /terminal/);
  draft = patternDraft(state, null, "pattern1");
  assert.throws(() => patternProposal(state, draft), /Change/);
  draft.count = 2;
  draft.values = ["20", "0", "0"];
  const edit = patternProposal(state, draft);
  assert.equal(edit.operations.at(-1).op, "replace_feature");
  const result = run(state.model, edit).result;
  assert.equal(result.bodies[0].volume_mm3, "36000");
  assert.equal(result.bodies[0].components.length, 1);
  assert.equal(result.model.features[0].id, "stock");
});
test("constrained spacing, count boundaries and collision-free draft identity", () => {
  let state = initial();
  state.model.parameters["pattern1.reserved"] = "1";
  const draft = patternDraft(state, "stock");
  assert.equal(draft.id, "pattern2");
  state = {
    revision: 2,
    ...run(state.model, patternProposal(state, draft)).result,
  };
  const edit = patternDraft(state, null, "pattern2");
  state.model.fixed[edit.step[0]] = "50";
  assert.equal(stepEditable(state, edit.step[0]), false);
  edit.values[0] = "60";
  assert.throws(() => patternProposal(state, edit), /fixed or derived/);
  edit.values[0] = "50";
  edit.count = 4;
  assert.ok(patternProposal(state, edit));
  for (const count of [0, 17, 2.5, NaN]) {
    edit.count = count;
    assert.throws(() => patternProposal(state, edit), /Count/);
  }
  delete state.model.fixed[edit.step[0]];
  state.model.relations = {
    [edit.step[0]]: { offset_mm: "10", terms: { w: "1" } },
  };
  assert.equal(stepEditable(state, edit.step[0]), false);
});
