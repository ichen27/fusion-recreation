import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import {
  shellDraft,
  shellProposal,
  thicknessEditable,
} from "./web/shell-model.mjs";
const binary = fileURLToPath(
  new URL(
    "../../crates/model-engine/target/release/model-engine",
    import.meta.url,
  ),
);
function run(model, proposal = { operations: [], preserve: [] }) {
  const reply = spawnSync(binary, {
    input: JSON.stringify({
      schema_version: 1,
      model,
      operations: proposal.operations,
      preserve: proposal.preserve,
    }),
    encoding: "utf8",
  });
  assert.ok(reply.stdout, reply.stderr);
  return JSON.parse(reply.stdout);
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
test("hollow, thicken, close and reopen retain editable source", () => {
  let state = initial(),
    draft = shellDraft(state, "stock");
  state = {
    revision: 2,
    ...run(state.model, shellProposal(state, draft)).result,
  };
  assert.equal(state.bodies[0].volume_mm3, "7152");
  assert.throws(() => shellDraft(state, "stock"), /terminal/);
  draft = shellDraft(state, null, "shell1");
  assert.throws(() => shellProposal(state, draft), /Change/);
  draft.open = false;
  const proposal = shellProposal(state, draft);
  assert.equal(proposal.operations[0].op, "replace_feature");
  state = { revision: 3, ...run(state.model, proposal).result };
  assert.equal(state.bodies[0].volume_mm3, "9024");
  assert.equal(state.model.features[0].id, "stock");
  draft = shellDraft(state, null, "shell1");
  draft.value = "3";
  assert.equal(
    run(state.model, shellProposal(state, draft)).result.bodies[0].volume_mm3,
    "12576",
  );
  draft.value = "20";
  assert.equal(
    run(state.model, shellProposal(state, draft)).error.code,
    "shell_thickness",
  );
  draft.value = "2";
  draft.open = true;
  draft.normal = ["0", "0", "-1"];
  assert.equal(
    run(state.model, shellProposal(state, draft)).result.bodies[0].volume_mm3,
    "7152",
  );
});
test("fixed and derived walls reject direct edits; opening remains editable", () => {
  let state = initial();
  state = {
    revision: 2,
    ...run(state.model, shellProposal(state, shellDraft(state, "stock")))
      .result,
  };
  state.model.fixed["shell1.thickness"] = "2";
  let draft = shellDraft(state, null, "shell1");
  assert.equal(thicknessEditable(state, draft), false);
  draft.value = "3";
  assert.throws(() => shellProposal(state, draft), /fixed or derived/);
  draft.value = "2";
  draft.open = false;
  assert.equal(
    run(state.model, shellProposal(state, draft)).result.bodies[0].volume_mm3,
    "9024",
  );
  delete state.model.fixed["shell1.thickness"];
  state.model.relations = {
    "shell1.thickness": { offset_mm: "0", terms: { h: "1/10" } },
  };
  assert.equal(thicknessEditable(state, draft), false);
});
test("drafts avoid parameter collisions, retain revision and do not mutate state", () => {
  const state = initial();
  state.model.parameters["shell1.other"] = "1";
  const before = structuredClone(state),
    draft = shellDraft(state, "stock");
  assert.equal(draft.id, "shell2");
  const proposal = shellProposal(state, draft);
  assert.equal(proposal.expected_revision, 1);
  assert.deepEqual(proposal.preserve.slice().sort(), [
    "d",
    "h",
    "shell1.other",
    "w",
  ]);
  assert.deepEqual(state, before);
  assert.throws(() => shellDraft(state, null, "missing"), /Select/);
});
