// Profile correspondence and exact geometry are validated by the native engine.
export function loftCandidates(state) {
  return state.model.features.filter((f) =>
    ["polygon_profile", "planar_profile"].includes(f.kind),
  );
}
export function loftProposal(state, bottom, top, height) {
  const candidates = new Set(loftCandidates(state).map((f) => f.id));
  if (!candidates.has(bottom) || !candidates.has(top))
    throw Error("Select two polygon profiles");
  let id;
  for (let i = 1; i <= 33; i++) {
    const name = `loft${i}`;
    if (
      !state.model.features.some((f) => f.id === name) &&
      !(`${name}.height` in state.model.parameters)
    ) {
      id = name;
      break;
    }
  }
  if (!id) throw Error("No unused loft IDs available");
  return {
    expected_revision: state.revision,
    operations: [
      { op: "define_parameter", id: `${id}.height`, mm: height },
      {
        op: "add_feature",
        feature: {
          kind: "planar_loft",
          id,
          bottom,
          top,
          height: `${id}.height`,
        },
      },
    ],
    preserve: Object.keys(state.model.parameters).filter(
      (id) => !(id in (state.model.relations ?? {})),
    ),
  };
}
