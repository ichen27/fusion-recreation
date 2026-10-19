import { rigidCandidate } from "./translate-model.mjs";
import { vectorOperations } from "./vector-parameters.mjs";
export { parameterEditable as pivotEditable } from "./vector-parameters.mjs";
export function rotationDraft(state, input, featureId = null) {
  const feature = featureId
    ? state.model.features.find(
        (f) => f.id === featureId && f.kind === "rotate_quarter",
      )
    : null;
  if (featureId && !feature) throw Error("Select a quarter-turn feature");
  if (
    !feature &&
    !state.bodies.some((b) => b.feature_id === input && rigidCandidate(b))
  )
    throw Error("Select a terminal solid");
  let id = featureId;
  if (!id)
    for (let i = 1; i <= 33; i++) {
      const name = `turn${i}`;
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
  if (!id) throw Error("No unused rotation IDs available");
  const pivot =
    feature?.pivot.slice() ?? ["x", "y", "z"].map((a) => `${id}.${a}`);
  return {
    id,
    featureId,
    input: feature?.input ?? input,
    pivot,
    values: feature
      ? pivot.map((p) => state.model.parameters[p])
      : ["0", "0", "0"],
    axis: feature?.axis ?? "z",
    turns: feature?.turns ?? 1,
  };
}
export function rotationProposal(state, draft) {
  if (!["x", "y", "z"].includes(draft.axis) || ![1, 2, 3].includes(draft.turns))
    throw Error("Select an axis and 90, 180 or 270 degrees");
  const operations = vectorOperations(
    state,
    draft.pivot,
    draft.values,
    !draft.featureId,
  );
  const feature = {
    kind: "rotate_quarter",
    id: draft.id,
    input: draft.input,
    axis: draft.axis,
    turns: draft.turns,
    pivot: draft.pivot.slice(),
  };
  if (!draft.featureId) operations.push({ op: "add_feature", feature });
  else {
    const previous = state.model.features.find((f) => f.id === draft.id);
    if (previous.axis !== feature.axis || previous.turns !== feature.turns)
      operations.push({ op: "replace_feature", id: draft.id, feature });
  }
  if (!operations.length) throw Error("Change the axis, angle or pivot first");
  return {
    expected_revision: state.revision,
    operations,
    preserve: Object.keys(state.model.parameters).filter(
      (id) =>
        !draft.pivot.includes(id) && !(id in (state.model.relations ?? {})),
    ),
  };
}
