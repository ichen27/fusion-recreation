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
    profileOnly: false,
    relationEdits: {},
  };
}
export function editable(draft, parameter) {
  return !(parameter in draft.model.fixed) && !draftRelation(draft, parameter);
}
export function draftRelation(draft, id) {
  return Object.hasOwn(draft.relationEdits ?? {}, id)
    ? draft.relationEdits[id]
    : (draft.model.relations?.[id] ?? null);
}
export function alignEdge(draft, index, orientation) {
  if (
    !["horizontal", "vertical"].includes(orientation) ||
    !draft.vertices[index] ||
    draft.vertices.length < 3
  )
    throw Error("Select an edge on a closed profile");
  const axis = orientation === "horizontal" ? "y" : "x";
  const source = draft.vertices[index][axis],
    target = draft.vertices[(index + 1) % draft.vertices.length][axis];
  if (source === target) return false;
  const rule = { offset_mm: "0", terms: { [source]: "1" } },
    current = draftRelation(draft, target);
  if (
    current &&
    current.offset_mm === "0" &&
    Object.keys(current.terms).length === 1 &&
    current.terms[source] === "1"
  )
    return false;
  if (target in draft.model.fixed)
    throw Error(`${target} is fixed; release its constraint before linking it`);
  if (current)
    throw Error(
      `${target} already has a relationship; clear it before assigning another`,
    );
  draft.relationEdits[target] = rule;
  return true;
}
export function clearSketchRelation(draft, id) {
  if (!draft.vertices.some((v) => v.x === id || v.y === id))
    throw Error("Select a sketch coordinate");
  if (!draftRelation(draft, id)) throw Error("Coordinate has no relationship");
  draft.relationEdits[id] = null;
}
function relationOperations(draft) {
  return Object.entries(draft.relationEdits ?? {}).flatMap(([id, rule]) => {
    if (rule) return [{ op: "set_relation", id, relation: rule }];
    return draft.model.relations?.[id] ? [{ op: "remove_relation", id }] : [];
  });
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
export function removeLastPoint(draft) {
  if (draft.featureId)
    throw Error("Existing sketches retain their vertex topology");
  if (!draft.vertices.length) throw Error("No point to remove");
  draft.vertices.pop();
  const refs = new Set(draft.vertices.flatMap((v) => [v.x, v.y]));
  for (const [id, rule] of Object.entries(draft.relationEdits)) {
    if (
      !refs.has(id) ||
      (rule && Object.keys(rule.terms).some((source) => !refs.has(source)))
    )
      delete draft.relationEdits[id];
  }
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
    const rules = relationOperations(draft);
    const changed = refs.filter(
      (ref) =>
        draft.values[ref] !== draft.model.parameters[ref] &&
        !draft.relationEdits[ref],
    );
    if (!changed.length && !rules.length)
      throw Error(
        "Move a point, change a coordinate or add an edge relationship first",
      );
    if (changed.some((ref) => !editable(draft, ref)))
      throw Error("Cannot edit a fixed or derived coordinate");
    return [
      ...rules.filter((o) => o.op === "remove_relation"),
      ...changed.map((id) => ({
        op: "set_parameter",
        id,
        mm: draft.values[id],
      })),
      ...rules.filter((o) => o.op === "set_relation"),
    ];
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
    ...(draft.profileOnly
      ? []
      : [{ op: "define_parameter", id: height, mm: draft.height }]),
    ...relationOperations(draft),
    {
      op: "add_feature",
      feature: {
        kind: draft.kind,
        id: profile,
        vertices: structuredClone(draft.vertices),
      },
    },
    ...(draft.profileOnly
      ? []
      : [
          {
            op: "add_feature",
            feature: { kind: "extrude", id: solid, profile, height },
          },
        ]),
  ];
}
export function sketchProposal(state, draft) {
  const operations = sketchOperations(draft);
  const changed = new Set(
    operations
      .filter((o) =>
        ["set_parameter", "set_relation", "remove_relation"].includes(o.op),
      )
      .map((o) => o.id),
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
