import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import {
  sweepProposal,
  sweepDraft,
  sweepCandidates,
} from "./web/sweep-model.mjs";
const binary = fileURLToPath(
  new URL(
    "../../crates/model-engine/target/release/model-engine",
    import.meta.url,
  ),
);
const model = () => ({
  parameters: { zero: "0", radius: "10", height: "12", inner: "3" },
  fixed: {},
  features: [
    {
      kind: "planar_profile",
      id: "section",
      vertices: [
        { id: "a", x: "zero", y: "zero" },
        { id: "b", x: "radius", y: "zero" },
        { id: "c", x: "radius", y: "height" },
        { id: "d", x: "zero", y: "height" },
      ],
    },
  ],
});
function run(model, proposal) {
  const r = spawnSync(binary, {
    input: JSON.stringify({
      schema_version: 1,
      model,
      operations: proposal.operations,
      preserve: proposal.preserve,
    }),
    encoding: "utf8",
  });
  assert.ok(r.stdout, r.stderr);
  return JSON.parse(r.stdout);
}
test("sweep creates parameter-backed vector, canonical units and stable profile replacement", () => {
  const state = { revision: 1, model: model() };
  const draft = sweepDraft(state);
  draft.values = ["7", "-3", "1/2 in"];
  const result = run(state.model, sweepProposal(state, draft)).result;
  assert.equal(result.bodies[0].volume_mm3, "1524");
  assert.equal(result.model.parameters["sweep1.z"], "127/10");
  const updated = { revision: 2, model: result.model };
  const edit = sweepDraft(updated, "sweep1");
  edit.values[2] = "-12";
  const changed = run(updated.model, sweepProposal(updated, edit)).result;
  assert.equal(changed.bodies[0].volume_mm3, "1440");
  assert.equal(changed.bodies[0].feature_id, "sweep1");
  const ring = { ...structuredClone(state.model.features[0]), id: "other" };
  ring.vertices[0].x = "inner";
  ring.vertices[3].x = "inner";
  updated.model.features.splice(1, 0, ring);
  edit.profile = "other";
  const replacement = sweepProposal(updated, edit);
  assert.ok(replacement.operations.some((o) => o.op === "replace_feature"));
  assert.equal(
    run(updated.model, replacement).result.bodies[0].volume_mm3,
    "1008",
  );
});
test("sweep filters forward profiles, preserves controls and rejects zero Z", () => {
  const source = { revision: 0, model: model() };
  const created = run(
    source.model,
    sweepProposal(source, sweepDraft(source)),
  ).result;
  const state = { revision: 1, model: created.model };
  state.model.features.push({
    ...structuredClone(state.model.features[0]),
    id: "later",
  });
  const draft = sweepDraft(state, "sweep1");
  assert.deepEqual(
    sweepCandidates(state, "sweep1").map((f) => f.id),
    ["section"],
  );
  draft.profile = "later";
  assert.throws(() => sweepProposal(state, draft), /earlier/);
  draft.profile = "section";
  assert.throws(() => sweepProposal(state, draft), /Change/);
  draft.values[2] = "0";
  assert.equal(
    run(state.model, sweepProposal(state, draft)).error.code,
    "sweep_direction",
  );
  state.model.fixed["sweep1.z"] = "10";
  assert.throws(() => sweepProposal(state, draft), /fixed or derived/);
});
test("sweep does not duplicate retained parameter namespaces or contradict shared coordinates", () => {
  const state = { revision: 0, model: model() };
  state.model.parameters["sweep1.retained"] = "3";
  assert.equal(sweepDraft(state).id, "sweep2");
  const draft = sweepDraft(state);
  draft.offset[1] = draft.offset[0];
  draft.values = ["1", "2", "3"];
  assert.throws(() => sweepProposal(state, draft), /Shared coordinate/);
});
