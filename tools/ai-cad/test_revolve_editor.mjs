import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { revolveProposal, revolveCandidates } from "./web/revolve-model.mjs";
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
test("revolution creation retains source sketch, no new parameters and stable edit identity", () => {
  const state = { revision: 1, model: model() };
  const result = run(state.model, revolveProposal(state, "section")).result;
  assert.equal(result.bodies[0].volume_mm3, "1200*pi");
  assert.deepEqual(result.model.parameters, state.model.parameters);
  assert.equal(result.model.features[0].id, "section");
  assert.throws(
    () =>
      revolveProposal(
        { revision: 2, model: result.model },
        "section",
        "revolve1",
      ),
    /different profile/,
  );
  const ring = { ...structuredClone(state.model.features[0]), id: "ring" };
  ring.vertices[0].x = "inner";
  ring.vertices[3].x = "inner";
  result.model.features.splice(1, 0, ring);
  const proposal = revolveProposal(
    { revision: 2, model: result.model },
    "ring",
    "revolve1",
  );
  assert.equal(proposal.operations[0].op, "replace_feature");
  const edited = run(result.model, proposal).result;
  assert.equal(edited.bodies[0].feature_id, "revolve1");
  assert.equal(edited.bodies[0].volume_mm3, "1092*pi");
});
test("profile selection excludes forward references and invalid radius profiles reject natively", () => {
  const state = { revision: 1, model: model() };
  assert.throws(() => revolveProposal(state, "missing"), /earlier/);
  const saved = run(state.model, revolveProposal(state, "section")).result
    .model;
  saved.features.push({ ...structuredClone(saved.features[0]), id: "later" });
  assert.deepEqual(
    revolveCandidates({ model: saved }, "revolve1").map((f) => f.id),
    ["section"],
  );
  assert.throws(
    () => revolveProposal({ model: saved, revision: 2 }, "later", "revolve1"),
    /earlier/,
  );
  state.model.parameters.zero = "-1";
  const reply = run(state.model, revolveProposal(state, "section"));
  assert.equal(reply.error.code, "unsupported_revolution");
});
