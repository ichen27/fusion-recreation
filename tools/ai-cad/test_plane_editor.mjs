import test from "node:test";
import { readFileSync } from "node:fs";
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

test("browser-created simple sketches feed plane cuts; concavity rejects in Rust", async () => {
  const { draftSketch, addPoint, sketchProposal } = await import(
    "./web/sketch-model.mjs"
  );
  const { planeCandidate } = await import("./web/plane-model.mjs");
  const empty = { parameters: {}, fixed: {}, features: [] };
  const draft = draftSketch(empty, "sketch1");
  for (const [x, y] of [
    [0, 0],
    [40, 0],
    [40, 30],
    [0, 30],
  ])
    addPoint(draft, x, y);
  draft.height = "20";
  let state = {
    revision: 1,
    ...run(empty, sketchProposal({ model: empty, revision: 0 }, draft)).result,
  };
  assert.equal(state.model.features[0].kind, "planar_profile");
  const id = state.bodies[0].feature_id;
  assert.ok(planeCandidate(state.bodies[0]));
  const p = planeDraft(state, id);
  p.normal = ["1", "0", "1"];
  p.value = "40";
  const result = run(state.model, planeProposal(state, p));
  assert.equal(result.result.bodies[0].volume_mm3, "18000");
  assert.ok(planeCandidate(result.result.bodies[0]));
  state.model.parameters["sketch1.v3.x"] = "10";
  state.model.parameters["sketch1.v3.y"] = "5";
  assert.equal(
    run(state.model, planeProposal(state, p)).error.code,
    "unsupported_reference",
  );
  assert.equal(
    planeCandidate({ analytic: { kind: "cylinder", holes: [] } }),
    false,
  );
  assert.equal(
    planeCandidate({ analytic: { kind: "polygon_prism", holes: [{}] } }),
    false,
  );
});

test("browser plane opens a cavity and updates its offset atomically", () => {
  const model = JSON.parse(
    readFileSync(
      `${root}/examples/ai-cad/planar-booleans/cavity.model.json`,
      "utf8",
    ),
  );
  let state = { revision: 1, ...run(model).result };
  let draft = planeDraft(state, "result");
  draft.value = "5";
  state = {
    revision: 2,
    ...run(state.model, planeProposal(state, draft)).result,
  };
  assert.equal(state.bodies[0].volume_mm3, "392");
  assert.equal(state.bodies[0].components.length, 1);
  assert.equal(
    state.bodies[0].boundary.faces.filter((f) => f.loops.length === 2).length,
    1,
  );
  draft = planeDraft(state, null, "plane1");
  draft.value = "4";
  assert.equal(
    run(state.model, planeProposal(state, draft)).result.bodies[0].volume_mm3,
    "328",
  );
  draft.value = "0";
  assert.equal(
    run(state.model, planeProposal(state, draft)).error.code,
    "empty_solid",
  );
});
