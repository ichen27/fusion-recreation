import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import {
  translationDraft,
  translationProposal,
  translationEditable,
} from "./web/translate-model.mjs";
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
      parameters: { size: "10" },
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
test("browser move creates exact offsets and edits its existing feature", () => {
  let state = initial(),
    d = translationDraft(state, "stock");
  d.values = ["1/3", "-2", "5"];
  const proposal = translationProposal(state, d);
  assert.equal(proposal.expected_revision, 1);
  assert.deepEqual(proposal.preserve, ["size"]);
  state = { revision: 2, ...run(state.model, proposal).result };
  assert.equal(state.bodies[0].volume_mm3, "1000");
  assert.equal(state.bodies[0].feature_id, "move1");
  assert.equal(
    Math.min(...state.bodies[0].boundary.vertices.map((p) => Number(p[2]))),
    5,
  );
  assert.throws(() => translationDraft(state, "stock"), /terminal/);
  d = translationDraft(state, null, "move1");
  assert.throws(() => translationProposal(state, d), /Change/);
  d.values[2] = "9";
  assert.equal(translationProposal(state, d).operations[0].op, "set_parameter");
  assert.equal(
    run(state.model, translationProposal(state, d)).result.bodies[0].volume_mm3,
    "1000",
  );
  d.values[2] = "1000001";
  assert.equal(
    run(state.model, translationProposal(state, d)).error.code,
    "translation_range",
  );
});
test("fixed/derived/shared offsets remain explicit and collide safely", () => {
  let state = initial(),
    d = translationDraft(state, "stock");
  state.model.parameters["move1.x"] = "2";
  assert.equal(translationDraft(state, "stock").id, "move2");
  delete state.model.parameters["move1.x"];
  state = {
    revision: 2,
    ...run(state.model, translationProposal(state, d)).result,
  };
  state.model.fixed["move1.x"] = "0";
  d = translationDraft(state, null, "move1");
  d.values[0] = "1";
  assert.equal(translationEditable(state, "move1.x"), false);
  assert.throws(() => translationProposal(state, d), /fixed or derived/);
  delete state.model.fixed["move1.x"];
  state.model.relations = {
    "move1.x": { offset_mm: "0", terms: { size: "1" } },
  };
  assert.equal(translationEditable(state, "move1.x"), false);
  delete state.model.relations;
  d.offset = ["move1.x", "move1.x", "move1.z"];
  d.values = ["2", "3", "0"];
  assert.throws(() => translationProposal(state, d), /Shared/);
  d.values = ["2", "2", "0"];
  assert.deepEqual(translationProposal(state, d).operations, [
    { op: "set_parameter", id: "move1.x", mm: "2" },
  ]);
});

test("linked copies retain source, propagate dimensions and edit placement independently", () => {
  let state = initial();
  const draft = translationDraft(state, "stock", null, "instance");
  draft.values = ["20", "0", "0"];
  let proposal = translationProposal(state, draft);
  assert.equal(proposal.operations.at(-1).feature.source, "stock");
  assert.equal(proposal.operations.at(-1).feature.kind, "instance");
  state = { revision: 2, ...run(state.model, proposal).result };
  assert.deepEqual(
    state.bodies.map((b) => b.feature_id),
    ["instance1", "stock"],
  );
  assert.equal(
    translationDraft(state, "stock", null, "instance").id,
    "instance2",
  );
  const edit = translationDraft(state, null, "instance1", "instance");
  edit.values[0] = "30";
  proposal = translationProposal(state, edit);
  assert.deepEqual(proposal.operations, [
    { op: "set_parameter", id: "instance1.x", mm: "30" },
  ]);
  const moved = run(state.model, proposal).result;
  assert.deepEqual(
    moved.bodies.find((b) => b.feature_id === "stock"),
    state.bodies.find((b) => b.feature_id === "stock"),
  );
  const changed = run(state.model, {
    operations: [{ op: "set_parameter", id: "size", mm: "12" }],
    preserve: [],
  }).result;
  assert.deepEqual(
    changed.bodies.map((b) => b.volume_mm3),
    ["1728", "1728"],
  );
  assert.throws(() => translationDraft(state, null, "instance1"), /matching/);
});
