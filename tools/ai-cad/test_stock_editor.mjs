import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { stockProposal } from "./web/stock-model.mjs";
const root = fileURLToPath(new URL("../../", import.meta.url));
function run(model, proposal) {
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
const empty = () => ({
  revision: 0,
  model: { parameters: {}, features: [], fixed: {} },
});
test("block and circular stock use distinct IDs and preserve the existing model", () => {
  let state = empty();
  let p = stockProposal(state, "block", {
    width: "40",
    depth: "30",
    height: "20",
  });
  assert.equal(p.expected_revision, 0);
  state = { revision: 1, ...run(state.model, p).result };
  assert.equal(state.bodies[0].volume_mm3, "24000");
  const before = structuredClone(state.model);
  p = stockProposal(state, "cylinder", {
    x: "70",
    y: "0",
    radius: "20",
    height: "10",
  });
  assert.deepEqual(p.preserve, Object.keys(state.model.parameters));
  const result = run(state.model, p).result;
  assert.deepEqual(
    result.model.features.map((f) => f.id),
    ["stock1", "stock2"],
  );
  assert.equal(result.bodies[1].volume_mm3, "4000*pi");
  assert.deepEqual(state.model, before);
});
test("invalid dimensions and reused namespaces never silently change prior stock", () => {
  const state = empty();
  assert.throws(() => stockProposal(state, "sphere", {}), /Choose/);
  const p = stockProposal(state, "block", {
    width: "-1",
    depth: "30",
    height: "20",
  });
  assert.equal(run(state.model, p).error.code, "dimension_range");
  state.model.parameters["stock1.reserved"] = "1";
  assert.equal(
    stockProposal(state, "block", {
      width: "1",
      depth: "2",
      height: "3",
    }).operations.at(-1).feature.id,
    "stock2",
  );
  state.model.relations = { "stock1.reserved": { offset_mm: "1", terms: {} } };
  assert.deepEqual(
    stockProposal(state, "cylinder", {
      x: "0",
      y: "0",
      radius: "1/2",
      height: "3",
    }).preserve,
    [],
  );
});
test("tapered stock carries exact radii and rejects equal radii", () => {
  const state = empty();
  const values = {
    x: "0",
    y: "0",
    bottom_radius: "10",
    top_radius: "5",
    height: "12",
  };
  const result = run(
    state.model,
    stockProposal(state, "conical_frustum", values),
  );
  assert.equal(result.result.bodies[0].volume_mm3, "700*pi");
  assert.equal(result.result.model.features[0].kind, "conical_frustum");
  assert.equal(
    run(
      state.model,
      stockProposal(state, "conical_frustum", { ...values, top_radius: "10" }),
    ).error.code,
    "invalid_taper",
  );
});
