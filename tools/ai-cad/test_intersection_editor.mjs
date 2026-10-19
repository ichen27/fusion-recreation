import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import {
  intersectionCandidates,
  intersectionProposal,
} from "./web/intersection-model.mjs";
const root = fileURLToPath(new URL("../../", import.meta.url));
function run(model, proposal = { operations: [], preserve: [] }) {
  const p = spawnSync(
    `${root}/crates/model-engine/target/release/model-engine`,
    {
      input: JSON.stringify({ schema_version: 1, model, ...proposal }),
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
test("browser intersection consumes two inputs and preserves dimensions", () => {
  const state = { revision: 7, ...run(model).result };
  assert.equal(intersectionCandidates(state).length, 2);
  const proposal = intersectionProposal(state, "large", "small");
  assert.equal(proposal.expected_revision, 7);
  assert.deepEqual(proposal.preserve, ["a", "b"]);
  const { expected_revision, ...request } = proposal;
  const reply = run(model, request);
  assert.ok(reply.result, reply);
  assert.equal(reply.result.bodies.length, 1);
  assert.equal(reply.result.bodies[0].volume_mm3, "8000");
  assert.equal(reply.result.bodies[0].feature_id, "intersection1");
  assert.throws(
    () => intersectionProposal({ ...state, ...reply.result }, "large", "small"),
    /terminal/,
  );
});
test("selection rejects same/missing inputs and avoids feature ID collisions", () => {
  const state = { revision: 1, ...run(model).result };
  assert.throws(
    () => intersectionProposal(state, "small", "small"),
    /distinct/,
  );
  assert.throws(
    () => intersectionProposal(state, "small", "missing"),
    /terminal/,
  );
  state.model.features.push({
    kind: "block",
    id: "intersection1",
    width: "a",
    depth: "a",
    height: "a",
  });
  assert.equal(
    intersectionProposal(state, "small", "large").operations[0].feature.id,
    "intersection2",
  );
});

test("consumed sketch stock no longer offers a new hole group", async () => {
  const { availableHoleInputs } = await import("./web/hole-model.mjs");
  const features = [
    { kind: "extrude", id: "a" },
    { kind: "extrude", id: "b" },
  ];
  assert.equal(availableHoleInputs({ features }).length, 2);
  assert.deepEqual(
    availableHoleInputs({
      features: [...features, { kind: "intersection", left: "a", right: "b" }],
    }),
    [],
  );
  assert.deepEqual(
    availableHoleInputs({
      features: [...features, { kind: "plane_cut", input: "a" }],
    }).map((f) => f.id),
    ["b"],
  );
});
