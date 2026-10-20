import { planeCandidate } from "./plane-model.mjs";

export function intersectionCandidates(state, kind = "intersection") {
  if (kind === "intersection") return state.bodies.filter(planeCandidate);
  if (kind !== "coaxial_intersection")
    throw Error("Choose a supported intersection mode");
  return state.bodies.filter(
    (b) =>
      b.analytic &&
      !b.analytic.holes.length &&
      (b.analytic.revolution || b.analytic.outer_circle),
  );
}
export function intersectionProposal(
  state,
  left,
  right,
  kind = "intersection",
) {
  const candidates = new Set(
    intersectionCandidates(state, kind).map((b) => b.feature_id),
  );
  if (left === right || !candidates.has(left) || !candidates.has(right))
    throw Error("Select two distinct terminal solids for this mode");
  let id;
  for (let i = 1; i <= 33; i++) {
    const candidate = `${kind === "coaxial_intersection" ? "coaxial" : "intersection"}${i}`;
    if (!state.model.features.some((f) => f.id === candidate)) {
      id = candidate;
      break;
    }
  }
  if (!id) throw Error("No unused intersection IDs available");
  return {
    expected_revision: state.revision,
    operations: [{ op: "add_feature", feature: { kind, id, left, right } }],
    preserve: Object.keys(state.model.parameters).filter(
      (p) => !(p in (state.model.relations ?? {})),
    ),
  };
}
