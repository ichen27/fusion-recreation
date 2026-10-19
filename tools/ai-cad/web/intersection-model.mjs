import { planeCandidate } from "./plane-model.mjs";

export function intersectionCandidates(state) {
  return state.bodies.filter(planeCandidate);
}
export function intersectionProposal(state, left, right) {
  const candidates = new Set(
    intersectionCandidates(state).map((b) => b.feature_id),
  );
  if (left === right || !candidates.has(left) || !candidates.has(right))
    throw Error("Select two distinct terminal planar solids");
  let id;
  for (let i = 1; i <= 33; i++) {
    const candidate = `intersection${i}`;
    if (!state.model.features.some((f) => f.id === candidate)) {
      id = candidate;
      break;
    }
  }
  if (!id) throw Error("No unused intersection IDs available");
  return {
    expected_revision: state.revision,
    operations: [
      { op: "add_feature", feature: { kind: "intersection", id, left, right } },
    ],
    preserve: Object.keys(state.model.parameters),
  };
}
