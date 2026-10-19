import { vectorOperations } from "./vector-parameters.mjs";
export { parameterEditable as translationEditable } from "./vector-parameters.mjs";
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
    throw Error(
      "Select terminal unperforated planar stock or a previous planar Boolean result",
    );
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
export function translationProposal(state, draft) {
  const operations = vectorOperations(
    state,
    draft.offset,
    draft.values,
    !draft.featureId,
  );
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
      (id) =>
        !draft.offset.includes(id) && !(id in (state.model.relations ?? {})),
    ),
  };
}
