import { planeCandidate } from "./plane-model.mjs";
import { vectorOperations } from "./vector-parameters.mjs";
export { parameterEditable as stepEditable } from "./vector-parameters.mjs";
export function patternDraft(state, input, featureId = null) {
  const feature = featureId
    ? state.model.features.find(
        (f) => f.id === featureId && f.kind === "linear_pattern",
      )
    : null;
  if (featureId && !feature) throw Error("Select a linear material pattern");
  if (
    !feature &&
    !state.bodies.some((b) => b.feature_id === input && planeCandidate(b))
  )
    throw Error("Select terminal planar material");
  let id = featureId;
  if (!id)
    for (let i = 1; i <= 33; i++) {
      const candidate = `pattern${i}`;
      if (
        !state.model.features.some((f) => f.id === candidate) &&
        !Object.keys(state.model.parameters).some(
          (p) => p === candidate || p.startsWith(candidate + "."),
        )
      ) {
        id = candidate;
        break;
      }
    }
  if (!id) throw Error("No unused pattern IDs available");
  const step =
    feature?.step.slice() ?? ["x", "y", "z"].map((a) => `${id}.${a}`);
  return {
    id,
    featureId,
    input: feature?.input ?? input,
    count: feature?.count ?? 3,
    step,
    values: feature
      ? step.map((p) => state.model.parameters[p])
      : ["50", "0", "0"],
  };
}
export function patternProposal(state, draft) {
  if (!Number.isInteger(draft.count) || draft.count < 1 || draft.count > 16)
    throw Error(
      "Count must be an integer from 1 through 16, including the original",
    );
  const operations = vectorOperations(
    state,
    draft.step,
    draft.values,
    !draft.featureId,
  );
  const feature = {
    kind: "linear_pattern",
    id: draft.id,
    input: draft.input,
    count: draft.count,
    step: draft.step.slice(),
  };
  if (!draft.featureId) operations.push({ op: "add_feature", feature });
  else if (
    draft.count !==
    state.model.features.find((f) => f.id === draft.featureId).count
  )
    operations.push({ op: "replace_feature", id: draft.featureId, feature });
  if (!operations.length) throw Error("Change the count or spacing first");
  return {
    expected_revision: state.revision,
    operations,
    preserve: Object.keys(state.model.parameters).filter(
      (id) =>
        !draft.step.includes(id) && !(id in (state.model.relations ?? {})),
    ),
  };
}
