// Draft intent only. Rust remains the sole geometry/constraint authority.
export function draftSketch(model, prefix, featureId = null) {
  const feature = featureId
    ? model.features.find(
        (f) =>
          f.id === featureId &&
          ["polygon_profile", "planar_profile"].includes(f.kind),
      )
    : null;
  if (featureId && !feature) throw Error("Select a polygon profile");
  return {
    model: structuredClone(model),
    prefix,
    featureId,
    kind: feature?.kind ?? "planar_profile",
    vertices: feature ? structuredClone(feature.vertices) : [],
    values: { ...model.parameters },
    height: "6",
  };
}
export function editable(draft, parameter) {
  return (
    !(parameter in draft.model.fixed) &&
    !(parameter in (draft.model.relations ?? {}))
  );
}
export function addPoint(draft, x, y) {
  if (draft.featureId)
    throw Error(
      "Existing sketches retain their vertex topology; edit coordinates instead",
    );
  if (draft.vertices.length >= 16)
    throw Error("The drawing editor supports at most 16 points");
  const id = `v${draft.vertices.length + 1}`,
    xr = `${draft.prefix}.${id}.x`,
    yr = `${draft.prefix}.${id}.y`;
  if (xr in draft.model.parameters || yr in draft.model.parameters)
    throw Error("Sketch parameter IDs already exist; reopen the editor");
  draft.vertices.push({ id, x: xr, y: yr });
  draft.values[xr] = String(x);
  draft.values[yr] = String(y);
}
export function setCoordinate(draft, index, axis, value) {
  if (!["x", "y"].includes(axis) || !draft.vertices[index])
    throw Error("Unknown sketch coordinate");
  const ref = draft.vertices[index][axis];
  if (!editable(draft, ref))
    throw Error(`${ref} is fixed or derived; edit its controlling parameter`);
  draft.values[ref] = String(value);
}
export function sketchOperations(draft) {
  if (draft.vertices.length < 3)
    throw Error("Add at least three points around a simple outline");
  const refs = [...new Set(draft.vertices.flatMap((v) => [v.x, v.y]))];
  if (draft.featureId) {
    const changed = refs.filter(
      (ref) => draft.values[ref] !== draft.model.parameters[ref],
    );
    if (!changed.length)
      throw Error("Move a point or change a coordinate first");
    if (changed.some((ref) => !editable(draft, ref)))
      throw Error("Cannot edit a fixed or derived coordinate");
    return changed.map((id) => ({
      op: "set_parameter",
      id,
      mm: draft.values[id],
    }));
  }
  const profile = `${draft.prefix}.profile`,
    solid = `${draft.prefix}.solid`,
    height = `${draft.prefix}.height`;
  if (
    draft.model.features.some((f) => f.id === profile || f.id === solid) ||
    height in draft.model.parameters
  )
    throw Error("Sketch IDs already exist; reopen the editor");
  return [
    ...refs.map((id) => ({ op: "define_parameter", id, mm: draft.values[id] })),
    { op: "define_parameter", id: height, mm: draft.height },
    {
      op: "add_feature",
      feature: {
        kind: draft.kind,
        id: profile,
        vertices: structuredClone(draft.vertices),
      },
    },
    {
      op: "add_feature",
      feature: { kind: "extrude", id: solid, profile, height },
    },
  ];
}
export function sketchProposal(state, draft) {
  const operations = sketchOperations(draft);
  const changed = new Set(
    operations.filter((o) => o.op === "set_parameter").map((o) => o.id),
  );
  return {
    expected_revision: state.revision,
    operations,
    preserve: Object.keys(state.model.parameters).filter(
      (id) => !changed.has(id) && !(id in (state.model.relations ?? {})),
    ),
  };
}

export function nextSketchPrefix(model) {
  for (let i = 1; i <= 33; i++) {
    const prefix = `sketch${i}`;
    if (
      !model.features.some((f) => f.id.startsWith(prefix + ".")) &&
      !Object.keys(model.parameters).some((id) => id.startsWith(prefix + "."))
    )
      return prefix;
  }
  throw Error("Model feature limit reached");
}
