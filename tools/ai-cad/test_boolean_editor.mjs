import test from "node:test";
import { readFileSync } from "node:fs";
import {
  translationDraft,
  translationProposal,
} from "./web/translate-model.mjs";
import { rotationDraft, rotationProposal } from "./web/rotation-model.mjs";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { booleanCandidates, booleanProposal } from "./web/boolean-model.mjs";
import { availableHoleInputs } from "./web/hole-model.mjs";
const root = fileURLToPath(new URL("../../", import.meta.url));
function run(model, proposal = { operations: [], preserve: [] }) {
  const { expected_revision, ...request } = proposal;
  const p = spawnSync(
    `${root}/crates/model-engine/target/release/model-engine`,
    {
      input: JSON.stringify({ schema_version: 1, model, ...request }),
      encoding: "utf8",
    },
  );
  assert.ok(p.stdout, p.stderr);
  return JSON.parse(p.stdout);
}
const model = {
  parameters: { a: "20", b: "30" },
  fixed: {},
  features: [
    { kind: "block", id: "small", width: "a", depth: "a", height: "a" },
    { kind: "block", id: "large", width: "b", depth: "b", height: "b" },
  ],
};
test("Boolean browser proposals consume solids, preserve parameters and edit in place", () => {
  const state = { revision: 4, ...run(model).result };
  assert.equal(booleanCandidates(state).length, 2);
  const proposal = booleanProposal(state, "large", "small", "union");
  assert.equal(proposal.expected_revision, 4);
  assert.deepEqual(proposal.preserve, ["a", "b"]);
  const result = run(model, proposal).result;
  assert.equal(result.bodies.length, 1);
  assert.equal(result.bodies[0].volume_mm3, "27000");
  const saved = { revision: 5, ...result };
  const edit = booleanProposal(
    saved,
    "large",
    "small",
    "difference",
    "boolean1",
  );
  assert.equal(edit.operations[0].op, "replace_feature");
  const cut = run(result.model, edit).result;
  assert.equal(cut.bodies[0].volume_mm3, "19000");
  assert.equal(cut.model.features.at(-1).id, "boolean1");
  assert.throws(
    () => booleanProposal(saved, "large", "small", "union", "boolean1"),
    /Change/,
  );
  assert.throws(
    () => booleanProposal(saved, "small", "large", "difference", "boolean1"),
    /retaining/,
  );
});
test("Boolean controls reject missing/consumed inputs and invalid operations", () => {
  const state = { revision: 0, ...run(model).result };
  assert.throws(
    () => booleanProposal(state, "large", "large", "union"),
    /distinct/,
  );
  assert.throws(
    () => booleanProposal(state, "large", "missing", "union"),
    /terminal/,
  );
  assert.throws(
    () => booleanProposal(state, "large", "small", "xor"),
    /operation/,
  );
  state.model.features.push({ id: "boolean1" });
  assert.equal(
    booleanProposal(state, "large", "small", "union").operations[0].feature.id,
    "boolean2",
  );
  assert.deepEqual(
    availableHoleInputs({
      features: [
        { kind: "extrude", id: "a" },
        { kind: "extrude", id: "b" },
        { kind: "boolean", left: "a", right: "b" },
      ],
    }),
    [],
  );
});

test("browser moves and rotates a holed Boolean while retaining further Boolean capability", () => {
  const source = JSON.parse(
    readFileSync(
      `${root}/examples/ai-cad/planar-booleans/through.model.json`,
      "utf8",
    ),
  );
  let state = { revision: 2, ...run(source).result };
  const move = translationDraft(state, "result");
  move.values = ["10", "-5", "3"];
  state = {
    revision: 3,
    ...run(state.model, translationProposal(state, move)).result,
  };
  assert.equal(state.bodies[0].feature_id, "move1");
  const turn = rotationDraft(state, "move1");
  turn.axis = "x";
  state = {
    revision: 4,
    ...run(state.model, rotationProposal(state, turn)).result,
  };
  assert.equal(state.bodies[0].volume_mm3, "640");
  assert.equal(state.bodies[0].components.length, 1);
  assert.equal(
    state.bodies[0].boundary.faces.filter((f) => f.loops.length === 2).length,
    2,
  );
  assert.equal(booleanCandidates(state)[0].feature_id, "turn1");
});
