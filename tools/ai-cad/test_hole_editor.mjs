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
  setHoleDepth,
  setIndividualHoleDepth,
  setCounterboreRadius,
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
  assert.throws(() => draftHoles(result.model, "plate"), /consumed/);
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
    ["radius", "2.5.1", "invalid_number"],
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

test("blind depth survives creation, resizing, fixed rules and group removal", () => {
  const m = model(),
    d = draftHoles(m, "plate");
  d.kind = "blind_holes";
  addHole(d, 10, 50, "3");
  setHoleDepth(d, "2");
  const first = run(m, holeProposal({ model: m, revision: 0 }, d)).result;
  assert.equal(first.bodies[0].volume_mm3, "12000 - (18)*pi");
  assert.equal(first.bodies[0].analytic.hole_depth, "2");
  assert.equal(availableHoleInputs(first.model).length, 0);
  let edit = draftHoles(first.model, null, "holes1");
  assert.equal(edit.kind, "blind_holes");
  setHoleDepth(edit, "3");
  const changed = run(
    first.model,
    holeProposal({ model: first.model, revision: 1 }, edit),
  ).result;
  assert.equal(changed.bodies[0].volume_mm3, "12000 - (27)*pi");
  setHoleDepth(edit, "5");
  assert.equal(
    run(first.model, holeProposal({ model: first.model, revision: 1 }, edit))
      .error.code,
    "hole_depth",
  );
  const fixed = structuredClone(first.model);
  fixed.fixed[edit.depth] = "2";
  edit = draftHoles(fixed, null, "holes1");
  assert.throws(() => setHoleDepth(edit, "3"), /fixed or derived/);
  removeHole(edit, 0);
  const proposal = holeProposal({ model: fixed, revision: 1 }, edit);
  assert.deepEqual(proposal.operations, [
    { op: "remove_feature", id: "holes1" },
  ]);
  assert.equal(run(fixed, proposal).result.bodies[0].volume_mm3, "12000");
});

test("depth references can be shared without duplicate edits or shadowing old values", () => {
  const { result } = create();
  let m = structuredClone(result.model),
    f = m.features.at(-1);
  m.parameters["holes1.depth"] = "70";
  f.holes[1].x = "holes1.depth";
  assert.equal(draftHoles(m, null, f.id).values["holes1.depth"], "70");
  m = structuredClone(result.model);
  f = m.features.at(-1);
  f.kind = "blind_holes";
  f.depth = f.holes[0].radius;
  let d = draftHoles(m, null, f.id);
  setHoleDepth(d, "2");
  const proposal = holeProposal({ model: m, revision: 2 }, d);
  assert.equal(proposal.operations.length, 1);
  assert.ok(run(m, proposal).result);
  m.relations = {
    [f.depth]: { offset_mm: "0", terms: { [f.holes[1].radius]: "1" } },
  };
  d = draftHoles(m, null, f.id);
  assert.throws(() => setHoleDepth(d, "2"), /fixed or derived/);
});

test("counterbore editor retains through radii and shares validated recess dimensions", () => {
  const m = model(),
    d = draftHoles(m, "plate");
  d.kind = "counterbore_holes";
  addHole(d, 10, 50, "3");
  addHole(d, 70, 10, "2");
  setCounterboreRadius(d, "5");
  setHoleDepth(d, "2");
  const created = run(m, holeProposal({ model: m, revision: 1 }, d)).result;
  assert.equal(created.bodies[0].volume_mm3, "12000 - (139)*pi");
  const edit = draftHoles(created.model, null, "holes1");
  assert.equal(edit.boreRadius, "holes1.bore_radius");
  setCounterboreRadius(edit, "6");
  const changed = run(
    created.model,
    holeProposal({ model: created.model, revision: 2 }, edit),
  ).result;
  assert.equal(changed.bodies[0].volume_mm3, "12000 - (183)*pi");
  assert.deepEqual(changed.model.features, created.model.features);
  setCounterboreRadius(edit, "3");
  assert.equal(
    run(
      created.model,
      holeProposal({ model: created.model, revision: 2 }, edit),
    ).error.code,
    "counterbore_radius",
  );
  const fixed = structuredClone(created.model);
  fixed.fixed[edit.boreRadius] = "5";
  assert.throws(
    () => setCounterboreRadius(draftHoles(fixed, null, "holes1"), "6"),
    /fixed or derived/,
  );
});
test("countersink editor uses a conical rim and preserves its parameter link on edit", () => {
  const m = model(),
    d = draftHoles(m, "plate");
  d.kind = "countersink_holes";
  addHole(d, 10, 50, "3");
  addHole(d, 70, 10, "2");
  setCounterboreRadius(d, "5");
  setHoleDepth(d, "2");
  const created = run(m, holeProposal({ model: m, revision: 1 }, d)).result;
  assert.equal(created.bodies[0].volume_mm3, "12000 - (293/3)*pi");
  assert.equal(created.model.features.at(-1).rim_radius, d.boreRadius);
  assert.equal(created.model.features.at(-1).bore_radius, undefined);
  const edit = draftHoles(created.model, null, "holes1");
  setCounterboreRadius(edit, "6");
  const changed = run(
    created.model,
    holeProposal({ model: created.model, revision: 2 }, edit),
  ).result;
  assert.equal(changed.bodies[0].volume_mm3, "12000 - (347/3)*pi");
  assert.deepEqual(changed.model.features, created.model.features);
  setCounterboreRadius(edit, "3");
  assert.equal(
    run(
      created.model,
      holeProposal({ model: created.model, revision: 2 }, edit),
    ).error.code,
    "countersink_radius",
  );
});

test("individual blind depths create, edit, reconnect and remove without changing other holes", () => {
  const m = model(),
    d = draftHoles(m, "plate");
  d.kind = "blind_holes";
  addHole(d, 10, 50, "3");
  addHole(d, 70, 10, "3");
  setIndividualHoleDepth(d, 1, "4");
  const first = run(m, holeProposal({ model: m, revision: 0 }, d)).result;
  assert.equal(first.bodies[0].volume_mm3, "12000 - (54)*pi");
  assert.equal(
    first.model.features.at(-1).depth_overrides.h2,
    "holes1.h2.depth",
  );
  let edit = draftHoles(first.model, null, "holes1");
  setIndividualHoleDepth(edit, 1, "3");
  const resized = run(
    first.model,
    holeProposal({ model: first.model, revision: 1 }, edit),
  ).result;
  assert.equal(resized.bodies[0].volume_mm3, "12000 - (45)*pi");
  assert.deepEqual(resized.model.features, first.model.features);
  setIndividualHoleDepth(edit, 1, "");
  const reset = run(
    first.model,
    holeProposal({ model: first.model, revision: 1 }, edit),
  ).result;
  assert.equal(reset.bodies[0].volume_mm3, "12000 - (36)*pi");
  assert.equal(reset.model.features.at(-1).depth_overrides, undefined);
  assert.equal(reset.model.parameters["holes1.h2.depth"], "4");
  edit = draftHoles(reset.model, null, "holes1");
  setIndividualHoleDepth(edit, 1, "3");
  assert.equal(edit.depthOverrides.h2, "holes1.h2.depth2");
  removeHole(edit, 1);
  const removed = run(
    reset.model,
    holeProposal({ model: reset.model, revision: 2 }, edit),
  ).result;
  assert.equal(removed.bodies[0].volume_mm3, "12000 - (18)*pi");
  assert.equal(removed.model.features.at(-1).depth_overrides, undefined);
  const fixed = structuredClone(first.model);
  fixed.fixed["holes1.h2.depth"] = "4";
  edit = draftHoles(fixed, null, "holes1");
  assert.throws(() => setIndividualHoleDepth(edit, 1, "3"), /fixed or derived/);
  setIndividualHoleDepth(edit, 1, "");
  assert.equal(
    run(fixed, holeProposal({ model: fixed, revision: 1 }, edit)).result
      .bodies[0].volume_mm3,
    "12000 - (36)*pi",
  );
});

test("hole fields retain unit text until native conversion", () => {
  const { result } = create();
  const draft = draftHoles(result.model, null, "holes1");
  setHoleValue(draft, 0, "radius", ".25 cm");
  const proposal = holeProposal({ model: result.model, revision: 1 }, draft);
  assert.ok(proposal.operations.some((op) => op.mm === ".25 cm"));
  const changed = run(result.model, proposal).result;
  assert.equal(changed.model.parameters["holes1.h1.radius"], "5/2");
});
