import { vectorOperations, parameterEditable } from "./vector-parameters.mjs";
export { parameterEditable as sweepEditable };
export function sweepCandidates(state, featureId = null) {
  const end = featureId
    ? state.model.features.findIndex(
        (f) => f.id === featureId && f.kind === "straight_sweep",
      )
    : state.model.features.length;
  if (end < 0) throw Error("Select a straight sweep feature");
  return state.model.features
    .slice(0, end)
    .filter((f) => ["polygon_profile", "planar_profile"].includes(f.kind));
}
export function sweepDraft(state, featureId = null) {
  const candidates = sweepCandidates(state, featureId);
  if (!candidates.length) throw Error("Create a polygon sketch first");
  const feature = featureId
    ? state.model.features.find((f) => f.id === featureId)
    : null;
  let id = featureId;
  if (!id)
    for (let i = 1; i <= 33; i++) {
      const name = `sweep${i}`;
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
  if (!id) throw Error("No unused sweep IDs available");
  const offset =
    feature?.offset.slice() ?? ["x", "y", "z"].map((a) => `${id}.${a}`);
  return {
    id,
    featureId,
    profile: feature?.profile ?? candidates[0].id,
    offset,
    values: feature
      ? offset.map((p) => state.model.parameters[p])
      : ["0", "0", "10"],
  };
}
export function sweepProposal(state, draft) {
  if (
    !sweepCandidates(state, draft.featureId).some((f) => f.id === draft.profile)
  )
    throw Error("Select an earlier polygon profile");
  const operations = vectorOperations(
    state,
    draft.offset,
    draft.values,
    !draft.featureId,
  );
  const feature = {
    kind: "straight_sweep",
    id: draft.id,
    profile: draft.profile,
    offset: draft.offset.slice(),
  };
  if (!draft.featureId) operations.push({ op: "add_feature", feature });
  else if (
    state.model.features.find((f) => f.id === draft.featureId).profile !==
    draft.profile
  )
    operations.push({ op: "replace_feature", id: draft.featureId, feature });
  if (!operations.length)
    throw Error("Change the displacement or profile first");
  return {
    expected_revision: state.revision,
    operations,
    preserve: Object.keys(state.model.parameters).filter(
      (p) => !draft.offset.includes(p) && !(p in (state.model.relations ?? {})),
    ),
  };
}
