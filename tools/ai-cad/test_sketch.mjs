import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  draftSketch,
  addPoint,
  setCoordinate,
  sketchProposal,
  sketchOperations,
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
