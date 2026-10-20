import { loftCandidates, loftProposal } from "./web/loft-model.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  draftSketch,
  addPoint,
  removeLastPoint,
  setCoordinate,
  sketchProposal,
  sketchOperations,
  alignEdge,
  clearSketchRelation,
} from "./web/sketch-model.mjs";
const root = fileURLToPath(new URL("../../", import.meta.url));
const empty = { parameters: {}, features: [], fixed: {} };
function evaluate(model, operations, preserve = []) {
  const child = spawnSync(
    `${root}/crates/model-engine/target/release/model-engine`,
    {
      input: JSON.stringify({ schema_version: 1, model, operations, preserve }),
      encoding: "utf8",
    },
  );
  assert.ok(child.stdout, child.stderr);
  return JSON.parse(child.stdout);
}
function rectangle(model = empty) {
  const draft = draftSketch(model, "test");
  for (const [x, y] of [
    [0, 0],
    [100, 0],
    [100, 60],
    [0, 60],
  ])
    addPoint(draft, x, y);
  return draft;
}
test("draw→typed operations→real Rust extrusion, then edit same profile IDs", () => {
  const draft = rectangle();
  const proposal = sketchProposal({ revision: 0, model: empty }, draft);
  const created = evaluate(
    empty,
    proposal.operations,
    proposal.preserve,
  ).result;
  assert.equal(created.bodies[0].volume_mm3, "36000");
  const edit = draftSketch(created.model, "unused", "test.profile");
  setCoordinate(edit, 1, "x", "120");
  setCoordinate(edit, 2, "x", "120");
  const changed = sketchProposal({ revision: 1, model: created.model }, edit);
  const result = evaluate(
    created.model,
    changed.operations,
    changed.preserve,
  ).result;
  assert.equal(result.bodies[0].volume_mm3, "43200");
  assert.deepEqual(result.model.features, created.model.features);
});
test("fraction coordinates remain exact; crossing and degenerate drawings fail in Rust", () => {
  const draft = rectangle();
  setCoordinate(draft, 1, "x", "201/2");
  setCoordinate(draft, 2, "x", "201/2");
  assert.equal(
    evaluate(empty, sketchOperations(draft)).result.bodies[0].volume_mm3,
    "36180",
  );
  setCoordinate(draft, 2, "x", "-10");
  assert.equal(
    evaluate(empty, sketchOperations(draft)).error.code,
    "invalid_profile",
  );
  const bad = rectangle();
  setCoordinate(bad, 1, "x", "0");
  assert.equal(
    evaluate(empty, sketchOperations(bad)).error.code,
    "invalid_profile",
  );
});
test("fixed/derived coordinates stay locked, shared refs move together, preserve excludes dependencies", () => {
  const doc = JSON.parse(
    readFileSync(`${root}/examples/ai-cad/relationships/widen.reply.json`),
  ).result;
  const feature = doc.model.features.find((f) => f.kind === "polygon_profile");
  const draft = draftSketch(doc.model, "unused", feature.id);
  const tip = feature.vertices.findIndex((v) => v.x === "tip_x");
  assert.throws(() => setCoordinate(draft, tip, "x", "90"), /fixed or derived/);
  const right = feature.vertices.findIndex((v) => v.x === "width");
  setCoordinate(draft, right, "x", "140");
  assert.ok(
    draft.vertices
      .filter((v) => v.x === "width")
      .every((v) => draft.values[v.x] === "140"),
  );
  const proposal = sketchProposal(doc, draft);
  assert.ok(!proposal.preserve.includes("tip_x"));
  assert.ok(!proposal.preserve.includes("width"));
  assert.equal(
    evaluate(doc.model, proposal.operations, proposal.preserve).result.model
      .parameters.tip_x,
    "70",
  );
  assert.equal(doc.model.parameters.width, "120");
});
test("limits and collisions reject before ambiguous commands are emitted", () => {
  const draft = draftSketch(empty, "test");
  assert.throws(() => sketchOperations(draft), /three points/);
  for (let i = 0; i < 16; i++) addPoint(draft, i, i * i);
  assert.throws(() => addPoint(draft, 17, 17), /16 points/);
  const existing = evaluate(empty, sketchOperations(rectangle())).result.model;
  assert.throws(
    () => addPoint(draftSketch(existing, "test"), 1, 2),
    /already exist/,
  );
  const edit = draftSketch(existing, "unused", "test.profile");
  assert.throws(() => addPoint(edit, 2, 2), /retain their vertex topology/);
  assert.throws(() => sketchOperations(edit), /Move a point/);
});

test("new concave outlines extrude while existing convex profiles keep their kind", () => {
  const draft = draftSketch(empty, "ell");
  for (const [x, y] of [
    [0, 0],
    [80, 0],
    [80, 20],
    [20, 20],
    [20, 60],
    [0, 60],
  ])
    addPoint(draft, x, y);
  draft.height = "5";
  const result = evaluate(empty, sketchOperations(draft)).result;
  assert.equal(result.model.features[0].kind, "planar_profile");
  assert.equal(result.bodies[0].volume_mm3, "12000");
  const old = rectangle();
  old.kind = "polygon_profile";
  const model = evaluate(empty, sketchOperations(old)).result.model;
  const edit = draftSketch(model, "unused", "test.profile");
  assert.equal(edit.kind, "polygon_profile");
  setCoordinate(edit, 2, "x", "40");
  const changed = evaluate(model, sketchOperations(edit));
  assert.equal(changed.result.model.features[0].kind, "polygon_profile");
});

test("axis links make an editable rectangle retain horizontal/vertical edges", () => {
  const d = rectangle();
  for (const [i, o] of [
    [0, "horizontal"],
    [1, "vertical"],
    [2, "horizontal"],
    [3, "vertical"],
  ])
    alignEdge(d, i, o);
  const created = evaluate(empty, sketchOperations(d)).result;
  const edit = draftSketch(created.model, "unused", "test.profile");
  assert.throws(() => setCoordinate(edit, 2, "x", "120"), /fixed or derived/);
  setCoordinate(edit, 1, "x", "120");
  setCoordinate(edit, 2, "y", "70");
  const proposal = sketchProposal({ model: created.model, revision: 1 }, edit);
  const changed = evaluate(
    created.model,
    proposal.operations,
    proposal.preserve,
  ).result;
  assert.equal(changed.model.parameters["test.v3.x"], "120");
  assert.equal(changed.model.parameters["test.v4.y"], "70");
  assert.equal(changed.bodies[0].volume_mm3, "50400");
  assert.deepEqual(changed.model.features, created.model.features);
});
test("linking existing coordinates removes the driven value from preserve; clearing restores direct editing", () => {
  const m = evaluate(empty, sketchOperations(rectangle())).result.model;
  const d = draftSketch(m, "unused", "test.profile");
  setCoordinate(d, 1, "x", "120");
  alignEdge(d, 1, "vertical");
  const p = sketchProposal({ model: m, revision: 1 }, d);
  assert.ok(!p.preserve.includes("test.v3.x"));
  const changed = evaluate(m, p.operations, p.preserve).result;
  assert.equal(changed.bodies[0].volume_mm3, "43200");
  const clear = draftSketch(changed.model, "unused", "test.profile");
  clearSketchRelation(clear, "test.v3.x");
  setCoordinate(clear, 2, "x", "100");
  const q = sketchProposal({ model: changed.model, revision: 2 }, clear);
  assert.equal(q.operations[0].op, "remove_relation");
  const freed = evaluate(changed.model, q.operations, q.preserve).result;
  assert.equal(freed.model.parameters["test.v3.x"], "100");
  assert.equal(freed.model.relations, undefined);
});
test("axis links reject conflicts and let Rust report cycles without mutating source", () => {
  const d = rectangle();
  alignEdge(d, 0, "horizontal");
  assert.equal(alignEdge(d, 0, "horizontal"), false);
  for (const i of [1, 2, 3]) alignEdge(d, i, "horizontal");
  assert.equal(
    evaluate(empty, sketchOperations(d)).error.code,
    "relation_cycle",
  );
  const m = evaluate(empty, sketchOperations(rectangle())).result.model;
  m.fixed["test.v2.y"] = "0";
  assert.throws(
    () => alignEdge(draftSketch(m, "unused", "test.profile"), 0, "horizontal"),
    /fixed/,
  );
  const linked = evaluate(empty, [
    ...sketchOperations(rectangle()),
    {
      op: "set_relation",
      id: "test.v2.y",
      relation: { offset_mm: "0", terms: { "test.v4.x": "1" } },
    },
  ]).result.model;
  assert.throws(
    () =>
      alignEdge(draftSketch(linked, "unused", "test.profile"), 0, "horizontal"),
    /already has/,
  );
  assert.equal(m.parameters["test.v2.y"], "0");
});

test("removing a draft point removes only links involving its vanished coordinates", () => {
  const d = rectangle();
  for (const [i, o] of [
    [0, "horizontal"],
    [1, "vertical"],
    [2, "horizontal"],
    [3, "vertical"],
  ])
    alignEdge(d, i, o);
  removeLastPoint(d);
  assert.deepEqual(Object.keys(d.relationEdits).sort(), [
    "test.v2.y",
    "test.v3.x",
  ]);
  assert.equal(
    evaluate(empty, sketchOperations(d)).result.bodies[0].volume_mm3,
    "18000",
  );
});

test("standalone sketches feed a named planar loft and upstream edits rebuild it", () => {
  let m = structuredClone(empty);
  for (const [prefix, points] of [
    [
      "bottom",
      [
        [0, 0],
        [40, 0],
        [40, 20],
        [0, 20],
      ],
    ],
    [
      "top",
      [
        [5, 5],
        [35, 5],
        [35, 15],
        [5, 15],
      ],
    ],
  ]) {
    const draft = draftSketch(m, prefix);
    draft.profileOnly = true;
    for (const [x, y] of points) addPoint(draft, x, y);
    const result = evaluate(m, sketchOperations(draft)).result;
    assert.equal(result.bodies.length, 0);
    assert.equal(result.model.parameters[`${prefix}.height`], undefined);
    m = result.model;
  }
  const state = { model: m, revision: 2 };
  assert.equal(loftCandidates(state).length, 2);
  const proposal = loftProposal(state, "bottom.profile", "top.profile", "12");
  const result = evaluate(m, proposal.operations, proposal.preserve).result;
  assert.equal(result.bodies[0].volume_mm3, "6400");
  const draft = draftSketch(result.model, "unused", "top.profile");
  setCoordinate(draft, 0, "x", "8");
  setCoordinate(draft, 3, "x", "8");
  const changed = evaluate(result.model, sketchOperations(draft)).result;
  assert.equal(changed.bodies[0].volume_mm3, "6160");
  assert.deepEqual(changed.model.features, result.model.features);
  assert.throws(
    () => loftProposal(state, "missing", "top.profile", "12"),
    /polygon profiles/,
  );
  assert.equal(
    loftProposal(
      { ...state, model: result.model },
      "bottom.profile",
      "top.profile",
      "12",
    ).operations[1].feature.id,
    "loft2",
  );
});

test("rectangle dimensions control all corners and remain editable after reopening", async () => {
  const { startRectangle, sketchDrivers } = await import(
    "./web/sketch-model.mjs"
  );
  const model = { parameters: {}, features: [], fixed: {} };
  const draft = draftSketch(model, "sketch1");
  startRectangle(draft, "100", "60");
  assert.deepEqual(sketchDrivers(draft), ["sketch1.width", "sketch1.depth"]);
  draft.values["sketch1.width"] = "120";
  const ops = sketchOperations(draft);
  assert.equal(ops.filter((o) => o.op === "set_relation").length, 8);
  assert.equal(ops.find((o) => o.id === "sketch1.width").mm, "120");
  const actual = evaluate(model, ops).result;
  assert.equal(actual.bodies[0].volume_mm3, "43200");
  assert.equal(actual.model.parameters["sketch1.v3.x"], "120");
  const source = { parameters: {}, features: [], fixed: {}, relations: {} };
  for (const op of ops) {
    if (op.op === "define_parameter") source.parameters[op.id] = op.mm;
    if (op.op === "set_relation") source.relations[op.id] = op.relation;
    if (op.op === "add_feature") source.features.push(op.feature);
  }
  const reopened = draftSketch(source, "sketch2", "sketch1.profile");
  reopened.values["sketch1.width"] = "140";
  assert.deepEqual(sketchOperations(reopened), [
    { op: "set_parameter", id: "sketch1.width", mm: "140" },
  ]);
});
