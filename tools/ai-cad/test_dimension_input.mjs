import test from "node:test";
import assert from "node:assert/strict";
import { dimensionNumber } from "./web/dimension-input.mjs";
import { stockProposal } from "./web/stock-model.mjs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
test("draft coordinates interpret length units and reject invalid drawing inputs", () => {
  for (const [input, expected] of [
    ["1/2 in", 12.7],
    ["2.54 cm", 25.4],
    [".001m", 1],
    ["-1/12 ft", -25.4],
    ["+1.", 1],
    ["-.125", -0.125],
    ["1/-2", -0.5],
    [" 1 IN ", 25.4],
  ]) {
    assert.ok(Math.abs(dimensionNumber(input) - expected) < 1e-12, input);
  }
  for (const text of [
    "",
    "NaN",
    "1/0",
    "1e3",
    "1 yd",
    "1.2.3",
    "1 1/2 in",
    "1 + 2",
    null,
  ])
    assert.ok(Number.isNaN(dimensionNumber(text)), String(text));
});
test("browser proposals retain exact text and native canonicalization owns geometry", () => {
  const state = {
    revision: 0,
    model: { parameters: {}, features: [], fixed: {} },
  };
  const proposal = stockProposal(state, "block", {
    width: "1/2 in",
    depth: "2.54 cm",
    height: ".01m",
  });
  assert.deepEqual(
    proposal.operations.slice(0, 3).map((p) => p.mm),
    ["1/2 in", "2.54 cm", ".01m"],
  );
  const binary = fileURLToPath(
    new URL(
      "../../crates/model-engine/target/release/model-engine",
      import.meta.url,
    ),
  );
  const reply = spawnSync(binary, {
    input: JSON.stringify({
      schema_version: 1,
      model: state.model,
      operations: proposal.operations,
      preserve: [],
    }),
    encoding: "utf8",
  });
  assert.equal(reply.status, 0, reply.stderr);
  const result = JSON.parse(reply.stdout).result;
  assert.deepEqual(Object.values(result.model.parameters), [
    "127/5",
    "10",
    "127/10",
  ]);
  assert.equal(result.bodies[0].volume_mm3, "16129/5");
});
