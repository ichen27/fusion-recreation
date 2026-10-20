import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { linearProposal } from "./web/linear-model.mjs";
const root = fileURLToPath(new URL("../../", import.meta.url));
const compiled = JSON.parse(
  readFileSync(
    `${root}/examples/ai-cad/linear-constraints/mcp-created.cad.json`,
    "utf8",
  ),
).state.model;
function source() {
  const model = structuredClone(compiled);
  delete model.relations.left;
  delete model.relations.right;
  return { revision: 1, model };
}
function run(state, draft) {
  const { expected_revision, ...proposal } = linearProposal(state, draft);
  assert.equal(expected_revision, state.revision);
  return JSON.parse(
    spawnSync(`${root}/crates/model-engine/target/release/model-engine`, {
      input: JSON.stringify({
        schema_version: 1,
        model: state.model,
        ...proposal,
      }),
      encoding: "utf8",
    }).stdout,
  );
}
function row(terms, offset = "0") {
  return {
    terms: Object.entries(terms).map(([parameter, coefficient]) => ({
      parameter,
      coefficient,
    })),
    offset,
  };
}
const draft = {
  targets: ["left", "right"],
  equations: [
    row({ left: "1", right: "1", gap: "1", span: "-1" }),
    row({ left: "1", right: "-2" }),
  ],
};
test("browser authors coupled dimensions without preserving solved or downstream parameters", () => {
  const state = source();
  const proposal = linearProposal(state, draft);
  assert.ok(
    !proposal.preserve.includes("left") &&
      !proposal.preserve.includes("right") &&
      !proposal.preserve.includes("offset"),
  );
  assert.ok(
    proposal.preserve.includes("span") && proposal.preserve.includes("gap"),
  );
  const reply = run(state, draft);
  assert.deepEqual(reply.result.model, compiled);
  const replacement = {
    targets: ["left", "right"],
    equations: [draft.equations[0], row({ left: "1", right: "-1" })],
  };
  const result = run({ revision: 2, model: compiled }, replacement).result;
  assert.equal(result.model.parameters.left, "45");
  assert.equal(result.model.parameters.right, "45");
  assert.equal(result.model.parameters.offset, "55");
});
test("native rank and fixed constraints remain authoritative and local validation catches incomplete rows", () => {
  const state = source();
  assert.equal(
    run(state, { ...draft, equations: [draft.equations[0]] }).error.code,
    "linear_underdetermined",
  );
  state.model.fixed.left = "60";
  assert.equal(
    run(state, { targets: ["left"], equations: [row({ left: "1" }, "20")] })
      .error.code,
    "constraint_conflict",
  );
  assert.throws(
    () => linearProposal(state, { ...draft, targets: [] }),
    /Choose 1/,
  );
  assert.throws(
    () => linearProposal(state, { ...draft, targets: ["missing"] }),
    /existing/,
  );
  assert.throws(
    () => linearProposal(state, { ...draft, equations: [row({ "": "1" })] }),
    /Choose a dimension/,
  );
  assert.throws(
    () =>
      linearProposal(state, {
        ...draft,
        equations: [
          {
            terms: [
              { parameter: "span", coefficient: "1" },
              { parameter: "span", coefficient: "2" },
            ],
            offset: "0",
          },
        ],
      }),
    /repeated/,
  );
});
test("prototype-shaped parameter names are preserved as own equation terms", () => {
  const state = {
    revision: 0,
    model: {
      parameters: JSON.parse(
        '{"__proto__":"0","constructor":"0","toString":"1"}',
      ),
      features: [],
      fixed: {},
    },
  };
  const draft = {
    targets: ["__proto__", "constructor"],
    equations: [
      row(JSON.parse('{"__proto__":"1","toString":"-2"}')),
      row({ constructor: "1" }, "3"),
    ],
  };
  const proposal = linearProposal(state, draft);
  assert.ok(
    Object.hasOwn(proposal.operations[0].equations[0].terms, "__proto__"),
  );
  assert.deepEqual(proposal.preserve, ["toString"]);
  const reply = run(state, draft);
  assert.equal(reply.result.model.parameters.__proto__, "2");
  assert.equal(reply.result.model.parameters.constructor, "3");
  assert.throws(
    () => linearProposal(source(), { targets: ["constructor"], equations: [] }),
    /existing/,
  );
});
