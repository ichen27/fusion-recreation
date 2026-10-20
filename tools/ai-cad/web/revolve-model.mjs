// Profile coordinates remain editable; the native engine validates radius/Z geometry.
export function revolveCandidates(state, featureId = null) {
  const index = featureId
    ? state.model.features.findIndex(
        (f) => f.id === featureId && f.kind === "revolve",
      )
    : state.model.features.length;
  if (index < 0) throw Error("Select a revolution feature");
  return state.model.features
    .slice(0, index)
    .filter((f) => ["planar_profile", "polygon_profile"].includes(f.kind));
}
export function revolveProposal(state, profile, featureId = null) {
  if (!revolveCandidates(state, featureId).some((f) => f.id === profile))
    throw Error("Select an earlier polygon profile");
  let id = featureId;
  if (!id)
    for (let i = 1; i <= 33; i++) {
      const name = `revolve${i}`;
      if (!state.model.features.some((f) => f.id === name)) {
        id = name;
        break;
      }
    }
  if (!id) throw Error("No unused revolution IDs available");
  if (
    featureId &&
    state.model.features.find((f) => f.id === id).profile === profile
  )
    throw Error(
      "Choose a different profile, or edit the existing sketch dimensions",
    );
  const feature = { kind: "revolve", id, profile };
  return {
    expected_revision: state.revision,
    operations: [
      featureId
        ? { op: "replace_feature", id, feature }
        : { op: "add_feature", feature },
    ],
    preserve: Object.keys(state.model.parameters).filter(
      (id) => !(id in (state.model.relations ?? {})),
    ),
  };
}
