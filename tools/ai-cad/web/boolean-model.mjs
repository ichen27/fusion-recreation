import { intersectionCandidates } from "./intersection-model.mjs";
export function booleanCandidates(state, kind = "boolean") {
  if (!["boolean", "coaxial_boolean"].includes(kind))
    throw Error("Choose a supported geometry mode");
  return intersectionCandidates(
    state,
    kind === "boolean" ? "intersection" : "coaxial_intersection",
  );
}
export function booleanProposal(
  state,
  left,
  right,
  operation,
  featureId = null,
  kind = "boolean",
) {
  if (!["union", "difference", "intersection"].includes(operation))
    throw Error("Choose a Boolean operation");
  let id = featureId;
  if (id) {
    const old = state.model.features.find(
      (f) => f.id === id && f.kind === kind,
    );
    if (!old || left !== old.left || right !== old.right)
      throw Error("Edit the operation while retaining its two inputs");
    if (operation === old.operation) throw Error("Change the operation first");
  } else {
    const candidates = new Set(
      booleanCandidates(state, kind).map((b) => b.feature_id),
    );
    if (left === right || !candidates.has(left) || !candidates.has(right))
      throw Error("Select two distinct terminal solids for this geometry mode");
    for (let i = 1; i <= 33; i++) {
      const name = `${kind === "boolean" ? "boolean" : "radial"}${i}`;
      if (!state.model.features.some((f) => f.id === name)) {
        id = name;
        break;
      }
    }
    if (!id) throw Error("No unused Boolean IDs available");
  }
  const feature = { kind, id, left, right, operation };
  return {
    expected_revision: state.revision,
    operations: [
      featureId
        ? { op: "replace_feature", id, feature }
        : { op: "add_feature", feature },
    ],
    preserve: Object.keys(state.model.parameters).filter(
      (p) => !(p in (state.model.relations ?? {})),
    ),
  };
}
