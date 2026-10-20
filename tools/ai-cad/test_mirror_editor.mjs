import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import {
  mirrorDraft,
  mirrorProposal,
  offsetEditable,
} from "./web/mirror-model.mjs";
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
test("mirror keeps linked source, edits its plane, then consumes source", () => {
  let state = initial(),
    draft = mirrorDraft(state, "stock");
  draft.value = "50";
  state = {
    revision: 2,
    ...run(state.model, mirrorProposal(state, draft)).result,
  };
  assert.equal(state.bodies.length, 2);
  assert.equal(state.bodies[0].volume_mm3, "24000");
  draft = mirrorDraft(state, null, "mirror1");
  assert.throws(() => mirrorProposal(state, draft), /Change/);
  draft.normal = ["1", "2", "3"];
  draft.keep = false;
  const edit = mirrorProposal(state, draft);
  assert.equal(edit.operations[0].op, "replace_feature");
  state = { revision: 3, ...run(state.model, edit).result };
  assert.equal(state.bodies.length, 1);
  assert.equal(state.bodies[0].volume_mm3, "24000");
  assert.throws(() => mirrorDraft(state, "stock"), /terminal/);
});
test("fixed/derived offsets, implicit retention default and safe draft IDs", () => {
  let state = initial();
  state.model.parameters["mirror1.reserved"] = "1";
  const draft = mirrorDraft(state, "stock");
  assert.equal(draft.id, "mirror2");
  state = {
    revision: 2,
    ...run(state.model, mirrorProposal(state, draft)).result,
  };
  delete state.model.features.at(-1).keep_original;
  const edit = mirrorDraft(state, null, "mirror2");
  assert.equal(edit.keep, false);
  state.model.fixed[edit.offset] = "0";
  assert.equal(offsetEditable(state, edit), false);
  edit.value = "1";
  assert.throws(() => mirrorProposal(state, edit), /fixed or derived/);
  edit.value = "0";
  edit.keep = true;
  assert.ok(mirrorProposal(state, edit));
  delete state.model.fixed[edit.offset];
  state.model.relations = {
    [edit.offset]: { offset_mm: "0", terms: { w: "1" } },
  };
  assert.equal(offsetEditable(state, edit), false);
});
