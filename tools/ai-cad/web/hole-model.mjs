// Draft intent only: Rust owns containment, separation, constraints and topology.
import { editable } from "./sketch-model.mjs";
export { editable };
export function availableHoleInputs(model) {
  const consumed = new Set(
    model.features
      .filter((f) => f.kind === "through_holes")
      .map((f) => f.input),
  );
  return model.features.filter(
    (f) => ["extrude", "cylinder"].includes(f.kind) && !consumed.has(f.id),
  );
}
export function nextHolePrefix(model) {
  for (let i = 1; i <= 33; i++) {
    const prefix = `holes${i}`;
    if (
      !model.features.some(
        (f) => f.id === prefix || f.id.startsWith(prefix + "."),
      ) &&
      !Object.keys(model.parameters).some((id) => id.startsWith(prefix + "."))
    )
      return prefix;
  }
  throw Error("Model feature limit reached");
}
export function draftHoles(model, input, featureId = null) {
  const feature = featureId
    ? model.features.find(
        (f) => f.id === featureId && f.kind === "through_holes",
      )
    : null;
  if (featureId && !feature) throw Error("Select a through-hole group");
  input = feature?.input ?? input;
  const parent = model.features.find(
    (f) => f.id === input && ["extrude", "cylinder"].includes(f.kind),
  );
  if (!parent) throw Error("Select a profile extrusion or cylinder");
  if (!feature && !availableHoleInputs(model).some((f) => f.id === input))
    throw Error("This solid already has a hole group; edit that group");
  const profile =
    parent.kind === "cylinder"
      ? { kind: "circle", x: parent.x, y: parent.y, radius: parent.radius }
      : model.features.find((f) => f.id === parent.profile);
  if (
    !profile ||
    !["planar_profile", "polygon_profile", "circle"].includes(profile.kind)
  )
    throw Error("Select a polygon extrusion");
  return {
    model: structuredClone(model),
    input,
    featureId,
    profile: structuredClone(profile),
    prefix: featureId ?? nextHolePrefix(model),
    holes: structuredClone(feature?.holes ?? []),
    values: { ...model.parameters },
  };
}
export function addHole(draft, x, y, radius) {
  if (draft.holes.length >= 16) throw Error("At most 16 holes per group");
  let id;
  for (let i = 1; i <= 65; i++) {
    const candidate = `h${i}`;
    if (
      !draft.holes.some((h) => h.id === candidate) &&
      !["x", "y", "radius"].some(
        (k) => `${draft.prefix}.${candidate}.${k}` in draft.model.parameters,
      )
    ) {
      id = candidate;
      break;
    }
  }
  if (!id) throw Error("No unused hole IDs available");
  const refs = {
    id,
    x: `${draft.prefix}.${id}.x`,
    y: `${draft.prefix}.${id}.y`,
    radius: `${draft.prefix}.${id}.radius`,
  };
  if (["x", "y", "radius"].some((k) => refs[k] in draft.model.parameters))
    throw Error("Hole parameter IDs already exist; reopen the editor");
  draft.holes.push(refs);
  for (const [key, value] of Object.entries({ x, y, radius }))
    draft.values[refs[key]] = String(value);
}
export function setHoleValue(draft, index, axis, value) {
  if (!["x", "y", "radius"].includes(axis) || !draft.holes[index])
    throw Error("Unknown hole dimension");
  const ref = draft.holes[index][axis];
  if (!editable(draft, ref))
    throw Error(`${ref} is fixed or derived; edit its controlling parameter`);
  draft.values[ref] = String(value);
}
export function removeHole(draft, index) {
  if (!Number.isInteger(index) || !draft.holes[index])
    throw Error("Unknown hole");
  draft.holes.splice(index, 1);
}
export function holeProposal(state, draft) {
  if (!draft.holes.length && !draft.featureId)
    throw Error("Place at least one hole");
  const refs = [...new Set(draft.holes.flatMap((h) => [h.x, h.y, h.radius]))];
  const changed = refs.filter(
    (id) =>
      id in draft.model.parameters &&
      draft.values[id] !== draft.model.parameters[id],
  );
  if (changed.some((id) => !editable(draft, id)))
    throw Error("Cannot edit a fixed or derived dimension");
  const operations = refs
    .filter((id) => !(id in draft.model.parameters))
    .map((id) => ({ op: "define_parameter", id, mm: draft.values[id] }));
  operations.push(
    ...changed.map((id) => ({ op: "set_parameter", id, mm: draft.values[id] })),
  );
  const feature = {
    kind: "through_holes",
    id: draft.featureId ?? draft.prefix,
    input: draft.input,
    holes: structuredClone(draft.holes),
  };
  if (draft.featureId) {
    const original = draft.model.features.find((f) => f.id === draft.featureId);
    if (!draft.holes.length)
      operations.push({ op: "remove_feature", id: draft.featureId });
    else if (JSON.stringify(original.holes) !== JSON.stringify(draft.holes))
      operations.push({ op: "replace_feature", id: draft.featureId, feature });
  } else operations.push({ op: "add_feature", feature });
  if (!operations.length)
    throw Error("Move a hole, change a dimension or add/remove a hole first");
  return {
    expected_revision: state.revision,
    operations,
    preserve: Object.keys(state.model.parameters).filter(
      (id) => !changed.includes(id) && !(id in (state.model.relations ?? {})),
    ),
  };
}
