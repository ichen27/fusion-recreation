import { planeCandidate } from "./plane-model.mjs";
export function booleanCandidates(state) {
  return state.bodies.filter(planeCandidate);
}
export function booleanProposal(
  state,
  left,
  right,
  operation,
  featureId = null,
) {
  if (!["union", "difference", "intersection"].includes(operation))
    throw Error("Choose a Boolean operation");
  let id = featureId;
  if (id) {
    const old = state.model.features.find(
      (f) => f.id === id && f.kind === "boolean",
    );
    if (!old || left !== old.left || right !== old.right)
      throw Error("Edit the operation while retaining its two inputs");
    if (operation === old.operation) throw Error("Change the operation first");
  } else {
    const candidates = new Set(
      booleanCandidates(state).map((b) => b.feature_id),
    );
    if (left === right || !candidates.has(left) || !candidates.has(right))
      throw Error("Select two distinct terminal planar solids");
    for (let i = 1; i <= 33; i++) {
      if (!state.model.features.some((f) => f.id === `boolean${i}`)) {
        id = `boolean${i}`;
        break;
      }
    }
    if (!id) throw Error("No unused Boolean IDs available");
  }
  const feature = { kind: "boolean", id, left, right, operation };
  return {
    expected_revision: state.revision,
    operations: [
      featureId
        ? { op: "replace_feature", id, feature }
        : { op: "add_feature", feature },
    ],
    preserve: Object.keys(state.model.parameters),
  };
}
