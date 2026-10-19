// Exact half-space intent. Rust owns geometry, parameter parsing and validation.
export function planeDraft(state, input, featureId = null) {
  const feature = featureId
    ? state.model.features.find(
        (f) => f.id === featureId && f.kind === "plane_cut",
      )
    : null;
  if (featureId && !feature) throw Error("Select a plane cut");
  if (
    !feature &&
    !state.bodies.some((b) => b.feature_id === input && b.boundary)
  )
    throw Error("Select a terminal convex planar solid");
  let prefix = featureId;
  if (!prefix)
    for (let i = 1; i <= 33; i++) {
      const name = `plane${i}`;
      if (
        !state.model.features.some((f) => f.id === name) &&
        !Object.keys(state.model.parameters).some(
          (p) => p === name || p.startsWith(name + "."),
        )
      ) {
        prefix = name;
        break;
      }
    }
  if (!prefix) throw Error("No unused plane IDs available");
  return {
    featureId,
    input: feature?.input ?? input,
    id: prefix,
    normal: feature?.normal.slice() ?? ["0", "0", "1"],
    offset: feature?.offset ?? `${prefix}.offset`,
    value: feature ? state.model.parameters[feature.offset] : "",
  };
}
export function offsetEditable(state, draft) {
  return (
    !(draft.offset in state.model.fixed) &&
    !(draft.offset in (state.model.relations ?? {}))
  );
}
export function planeProposal(state, draft) {
  const operations = [];
  if (!draft.featureId)
    operations.push({
      op: "define_parameter",
      id: draft.offset,
      mm: draft.value,
    });
  else if (draft.value !== state.model.parameters[draft.offset]) {
    if (!offsetEditable(state, draft))
      throw Error("Offset is fixed or derived; edit its controlling parameter");
    operations.push({ op: "set_parameter", id: draft.offset, mm: draft.value });
  }
  const feature = {
    kind: "plane_cut",
    id: draft.id,
    input: draft.input,
    normal: draft.normal.slice(),
    offset: draft.offset,
  };
  if (!draft.featureId) operations.push({ op: "add_feature", feature });
  else if (
    JSON.stringify(feature.normal) !==
    JSON.stringify(
      state.model.features.find((f) => f.id === draft.featureId).normal,
    )
  )
    operations.push({ op: "replace_feature", id: draft.featureId, feature });
  if (!operations.length) throw Error("Change the normal or offset first");
  return {
    expected_revision: state.revision,
    operations,
    preserve: Object.keys(state.model.parameters).filter(
      (id) => id !== draft.offset && !(id in (state.model.relations ?? {})),
    ),
  };
}
