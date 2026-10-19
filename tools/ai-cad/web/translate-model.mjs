import { planeCandidate } from "./plane-model.mjs";
export function translationDraft(state, input, featureId = null) {
  const feature = featureId
    ? state.model.features.find(
        (f) => f.id === featureId && f.kind === "translate",
      )
    : null;
  if (featureId && !feature) throw Error("Select a translation feature");
  if (
    !feature &&
    !state.bodies.some((b) => b.feature_id === input && planeCandidate(b))
  )
    throw Error("Select terminal convex planar stock");
  let id = featureId;
  if (!id)
    for (let i = 1; i <= 33; i++) {
      const name = `move${i}`;
      if (
        !state.model.features.some((f) => f.id === name) &&
        !Object.keys(state.model.parameters).some(
          (p) => p === name || p.startsWith(name + "."),
        )
      ) {
        id = name;
        break;
      }
    }
  if (!id) throw Error("No unused move IDs available");
  const offset =
    feature?.offset.slice() ?? ["x", "y", "z"].map((a) => `${id}.${a}`);
  return {
    id,
    featureId,
    input: feature?.input ?? input,
    offset,
    values: feature
      ? offset.map((p) => state.model.parameters[p])
      : ["0", "0", "0"],
  };
}
export function translationEditable(state, reference) {
  return (
    !(reference in state.model.fixed) &&
    !(reference in (state.model.relations ?? {}))
  );
}
export function translationProposal(state, draft) {
  const values = new Map();
  draft.offset.forEach((id, i) => {
    if (values.has(id) && values.get(id) !== draft.values[i])
      throw Error("Shared offset references must have one value");
    values.set(id, draft.values[i]);
  });
  const operations = [];
  for (const [id, mm] of values) {
    if (!draft.featureId) operations.push({ op: "define_parameter", id, mm });
    else if (mm !== state.model.parameters[id]) {
      if (!translationEditable(state, id))
        throw Error(
          "Offset is fixed or derived; edit its controlling parameter",
        );
      operations.push({ op: "set_parameter", id, mm });
    }
  }
  if (!draft.featureId)
    operations.push({
      op: "add_feature",
      feature: {
        kind: "translate",
        id: draft.id,
        input: draft.input,
        offset: draft.offset.slice(),
      },
    });
  if (!operations.length) throw Error("Change an offset first");
  return {
    expected_revision: state.revision,
    operations,
    preserve: Object.keys(state.model.parameters).filter(
      (id) => !values.has(id) && !(id in (state.model.relations ?? {})),
    ),
  };
}
