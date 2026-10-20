// Draft intent only: Rust owns containment, separation, constraints and topology.
import { editable } from "./sketch-model.mjs";
export { editable };
export function availableHoleInputs(model) {
  const consumed = new Set(
    model.features.flatMap((f) =>
      ["intersection", "boolean", "coaxial_intersection"].includes(f.kind)
        ? [f.left, f.right]
        : f.input
          ? [f.input]
          : [],
    ),
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
        (f) =>
          f.id === featureId &&
          [
            "through_holes",
            "blind_holes",
            "counterbore_holes",
            "countersink_holes",
          ].includes(f.kind),
      )
    : null;
  if (featureId && !feature) throw Error("Select a hole group");
  input = feature?.input ?? input;
  const parent = model.features.find(
    (f) => f.id === input && ["extrude", "cylinder"].includes(f.kind),
  );
  if (!parent) throw Error("Select a profile extrusion or cylinder");
  if (!feature && !availableHoleInputs(model).some((f) => f.id === input))
    throw Error(
      "This solid is consumed by another feature; select a terminal stock",
    );
  const profile =
    parent.kind === "cylinder"
      ? { kind: "circle", x: parent.x, y: parent.y, radius: parent.radius }
      : model.features.find((f) => f.id === parent.profile);
  if (
    !profile ||
    !["planar_profile", "polygon_profile", "circle"].includes(profile.kind)
  )
    throw Error("Select a polygon extrusion");
  const prefix = featureId ?? nextHolePrefix(model);
  const depth = feature?.depth ?? `${prefix}.depth`;
  const boreRadius =
    feature?.bore_radius ?? feature?.rim_radius ?? `${prefix}.bore_radius`;
  return {
    model: structuredClone(model),
    input,
    featureId,
    kind: feature?.kind ?? "through_holes",
    depth,
    boreRadius,
    depthOverrides: structuredClone(feature?.depth_overrides ?? {}),
    profile: structuredClone(profile),
    prefix,
    holes: structuredClone(feature?.holes ?? []),
    values: {
      ...model.parameters,
      ...(depth in model.parameters ? {} : { [depth]: "2" }),
      ...(boreRadius in model.parameters ? {} : { [boreRadius]: "5" }),
    },
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
  delete draft.depthOverrides[draft.holes[index].id];
  draft.holes.splice(index, 1);
}
export function holeProposal(state, draft) {
  if (!draft.holes.length && !draft.featureId)
    throw Error("Place at least one hole");
  const refs = [...new Set(draft.holes.flatMap((h) => [h.x, h.y, h.radius]))];
  if (
    ["blind_holes", "counterbore_holes", "countersink_holes"].includes(
      draft.kind,
    ) &&
    draft.holes.length &&
    !refs.includes(draft.depth)
  )
    refs.push(draft.depth);
  if (
    ["counterbore_holes", "countersink_holes"].includes(draft.kind) &&
    draft.holes.length &&
    !refs.includes(draft.boreRadius)
  )
    refs.push(draft.boreRadius);
  if (draft.kind === "blind_holes" && draft.holes.length)
    for (const ref of Object.values(draft.depthOverrides))
      if (!refs.includes(ref)) refs.push(ref);
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
    kind: draft.kind,
    ...(["blind_holes", "counterbore_holes", "countersink_holes"].includes(
      draft.kind,
    )
      ? { depth: draft.depth }
      : {}),
    ...(draft.kind === "counterbore_holes"
      ? { bore_radius: draft.boreRadius }
      : draft.kind === "countersink_holes"
        ? { rim_radius: draft.boreRadius }
        : {}),
    ...(draft.kind === "blind_holes" && Object.keys(draft.depthOverrides).length
      ? { depth_overrides: { ...draft.depthOverrides } }
      : {}),
    id: draft.featureId ?? draft.prefix,
    input: draft.input,
    holes: structuredClone(draft.holes),
  };
  if (draft.featureId) {
    const original = draft.model.features.find((f) => f.id === draft.featureId);
    if (!draft.holes.length)
      operations.push({ op: "remove_feature", id: draft.featureId });
    else if (
      JSON.stringify(original.holes) !== JSON.stringify(draft.holes) ||
      JSON.stringify(original.depth_overrides ?? {}) !==
        JSON.stringify(feature.depth_overrides ?? {})
    )
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

export function setHoleDepth(draft, value) {
  if (!editable(draft, draft.depth))
    throw Error("Depth is fixed or derived; edit its controlling parameter");
  draft.values[draft.depth] = String(value);
}

export function setCounterboreRadius(draft, value) {
  if (!editable(draft, draft.boreRadius))
    throw Error(
      "Recess rim radius is fixed or derived; edit its controlling parameter",
    );
  draft.values[draft.boreRadius] = String(value);
}

// An empty field reconnects the hole to the group default without deleting parameters.
export function setIndividualHoleDepth(draft, index, value) {
  const hole = draft.holes[index];
  if (draft.kind !== "blind_holes" || !hole) throw Error("Select a blind hole");
  if (!String(value).trim()) {
    delete draft.depthOverrides[hole.id];
    return;
  }
  let ref = draft.depthOverrides[hole.id];
  if (ref && !editable(draft, ref))
    throw Error("Depth is fixed or derived; edit its controlling parameter");
  if (!ref) {
    const base = `${draft.prefix}.${hole.id}.depth`;
    ref = base;
    let suffix = 2;
    while (ref in draft.values) ref = `${base}${suffix++}`;
    draft.depthOverrides[hole.id] = ref;
  }
  draft.values[ref] = String(value);
}
