import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  availableHoleInputs,
  draftHoles,
  addHole,
  removeHole,
  setHoleValue,
  holeProposal,
} from "./web/hole-model.mjs";
const root = fileURLToPath(new URL("../../", import.meta.url));
function model() {
  const m = JSON.parse(
    readFileSync(`${root}/examples/ai-cad/concave-profile/create.reply.json`),
  ).result.model;
  m.features.pop();
  return m;
}
function run(m, proposal) {
  const child = spawnSync(
    `${root}/crates/model-engine/target/release/model-engine`,
    {
      input: JSON.stringify({
        schema_version: 1,
        model: m,
        operations: proposal.operations,
        preserve: proposal.preserve,
      }),
      encoding: "utf8",
    },
  );
  assert.ok(child.stdout, child.stderr);
  return JSON.parse(child.stdout);
}
function create(m = model()) {
  const d = draftHoles(m, "plate");
  addHole(d, 10, 50, "3");
  addHole(d, 70, 10, "3");
  return {
    draft: d,
    result: run(m, holeProposal({ model: m, revision: 5 }, d)).result,
  };
}
test("place two holes in a concave plate, then edit with persistent feature and hole IDs", () => {
  const m = model(),
    { draft, result } = create(m);
  assert.equal(result.bodies[0].volume_mm3, "12000 - (90)*pi");
  assert.equal(
    holeProposal({ model: m, revision: 5 }, draft).expected_revision,
    5,
  );
  assert.equal(availableHoleInputs(result.model).length, 0);
  assert.throws(() => draftHoles(result.model, "plate"), /already has/);
  const edit = draftHoles(result.model, null, "holes1");
  setHoleValue(edit, 1, "x", "65");
  const changed = run(
    result.model,
    holeProposal({ model: result.model, revision: 6 }, edit),
  ).result;
  assert.deepEqual(changed.model.features, result.model.features);
  assert.equal(changed.bodies[0].analytic.holes[1].center[0], "65");
  assert.equal(result.model.parameters["holes1.h2.x"], "70");
});
test("Rust rejects breakout, overlap, bad radius and invalid numeric edits without changing draft source", () => {
  const { result } = create();
  const before = structuredClone(result.model);
  for (const [axis, value, code] of [
    ["x", "40", "hole_clearance"],
    ["radius", "10", "hole_clearance"],
    ["radius", "0", "dimension_range"],
    ["radius", "2.5", "invalid_number"],
  ]) {
    const d = draftHoles(result.model, null, "holes1");
    setHoleValue(d, 0, axis, value);
    assert.equal(
      run(result.model, holeProposal({ model: result.model, revision: 1 }, d))
        .error.code,
      code,
    );
  }
  const d = draftHoles(result.model, null, "holes1");
  setHoleValue(d, 1, "x", "10");
  setHoleValue(d, 1, "y", "50");
  assert.equal(
    run(result.model, holeProposal({ model: result.model, revision: 1 }, d))
      .error.code,
    "hole_overlap",
  );
  assert.deepEqual(result.model, before);
});
test("shared, fixed and derived parameter references keep their semantics", () => {
  const state = JSON.parse(
    readFileSync(`${root}/examples/ai-cad/concave-profile/create.reply.json`),
  ).result;
  const d = draftHoles(state.model, null, "mount");
  assert.throws(() => setHoleValue(d, 0, "x", "60"), /fixed or derived/);
  assert.throws(() => setHoleValue(d, 1, "radius", "4"), /fixed or derived/);
  const m = structuredClone(state.model);
  delete m.fixed.radius;
  const edit = draftHoles(m, null, "mount");
  setHoleValue(edit, 0, "radius", "7/2");
  assert.equal(edit.values[edit.holes[1].radius], "7/2");
  const p = holeProposal({ model: m, revision: 1 }, edit);
  assert.deepEqual(p.operations, [
    { op: "set_parameter", id: "radius", mm: "7/2" },
  ]);
  assert.ok(!p.preserve.includes("right_x"));
  assert.equal(run(m, p).result.bodies[0].volume_mm3, "12000 - (245/2)*pi");
});
test("draft limits, unsupported parents, duplicate groups and unchanged edits reject", () => {
  const m = model();
  assert.throws(() => draftHoles(m, "outline"), /profile extrusion/);
  const d = draftHoles(m, "plate");
  assert.throws(
    () => holeProposal({ model: m, revision: 0 }, d),
    /at least one/,
  );
  for (let i = 0; i < 16; i++) addHole(d, i, 10, 1);
  assert.throws(() => addHole(d, 17, 10, 1), /At most 16/);
  const { result } = create();
  const edit = draftHoles(result.model, null, "holes1");
  assert.throws(
    () => holeProposal({ model: result.model, revision: 1 }, edit),
    /Move a hole/,
  );
  assert.throws(() => setHoleValue(edit, 0, "diameter", "4"), /Unknown/);
});

test("topology edits add/remove holes, preserve surviving IDs and remove empty groups", () => {
  const { result } = create();
  const d = draftHoles(result.model, null, "holes1");
  addHole(d, 10, 10, 3);
  const p = holeProposal({ model: result.model, revision: 1 }, d);
  assert.equal(p.operations.at(-1).op, "replace_feature");
  const added = run(result.model, p).result;
  assert.equal(added.bodies[0].volume_mm3, "12000 - (135)*pi");
  assert.deepEqual(
    added.model.features.at(-1).holes.slice(0, 2),
    result.model.features.at(-1).holes,
  );
  const edit = draftHoles(added.model, null, "holes1");
  removeHole(edit, 0);
  const removed = run(
    added.model,
    holeProposal({ model: added.model, revision: 2 }, edit),
  ).result;
  assert.deepEqual(
    removed.model.features.at(-1).holes.map((h) => h.id),
    ["h2", "h3"],
  );
  const empty = draftHoles(removed.model, null, "holes1");
  removeHole(empty, 1);
  removeHole(empty, 0);
  const cleared = run(
    removed.model,
    holeProposal({ model: removed.model, revision: 3 }, empty),
  ).result;
  assert.equal(cleared.bodies[0].feature_id, "plate");
  assert.equal(cleared.bodies[0].volume_mm3, "12000");
  assert.deepEqual(cleared.model.parameters, removed.model.parameters);
  const collision = draftHoles(removed.model, null, "holes1");
  addHole(collision, 10, 50, 3);
  assert.equal(collision.holes.at(-1).id, "h4");
});

test("round stock exposes an exact circular outline and accepts typed hole editing", () => {
  const m = {
    parameters: { cx: "0", cy: "0", r: "40", h: "5" },
    fixed: {},
    features: [
      {
        kind: "cylinder",
        id: "round",
        x: "cx",
        y: "cy",
        radius: "r",
        height: "h",
      },
    ],
  };
  assert.equal(availableHoleInputs(m)[0].id, "round");
  const d = draftHoles(m, "round");
  assert.equal(d.profile.kind, "circle");
  addHole(d, 0, 0, 10);
  addHole(d, 30, 0, 3);
  const result = run(m, holeProposal({ model: m, revision: 0 }, d)).result;
  assert.equal(result.bodies[0].volume_mm3, "7455*pi");
  assert.equal(result.bodies[0].analytic.outer_circle.radius, "40");
  const edit = draftHoles(result.model, null, "holes1");
  setHoleValue(edit, 1, "x", "37");
  assert.equal(
    run(result.model, holeProposal({ model: result.model, revision: 1 }, edit))
      .error.code,
    "hole_clearance",
  );
});
