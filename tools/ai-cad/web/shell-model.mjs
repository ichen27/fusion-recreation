import { planeCandidate } from "./plane-model.mjs";
export function shellDraft(state, input, featureId = null) {
  const feature = featureId
    ? state.model.features.find(
        (f) => f.id === featureId && f.kind === "planar_shell",
      )
    : null;
  if (featureId && !feature) throw Error("Select a planar shell");
  if (
    !feature &&
    !state.bodies.some((b) => b.feature_id === input && planeCandidate(b))
  )
    throw Error(
      "Select terminal planar stock; the engine checks convexity and exact offsets",
    );
  let id = featureId;
  if (!id)
    for (let i = 1; i <= 33; i++) {
      const candidate = `shell${i}`;
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
  if (!id) throw Error("No unused shell IDs available");
  return {
    featureId,
    id,
    input: feature?.input ?? input,
    thickness: feature?.thickness ?? `${id}.thickness`,
    value: feature ? state.model.parameters[feature.thickness] : "2",
    open: feature ? !!feature.opening_normal : true,
    normal: feature?.opening_normal?.slice() ?? ["0", "0", "1"],
  };
}
export function thicknessEditable(state, draft) {
  return (
    !(draft.thickness in state.model.fixed) &&
    !(draft.thickness in (state.model.relations ?? {}))
  );
}
export function shellProposal(state, draft) {
  const operations = [];
  if (!draft.featureId)
    operations.push({
      op: "define_parameter",
      id: draft.thickness,
      mm: draft.value,
    });
  else if (draft.value !== state.model.parameters[draft.thickness]) {
    if (!thicknessEditable(state, draft))
      throw Error(
        "Thickness is fixed or derived; edit its controlling parameter",
      );
    operations.push({
      op: "set_parameter",
      id: draft.thickness,
      mm: draft.value,
    });
  }
  const feature = {
    kind: "planar_shell",
    id: draft.id,
    input: draft.input,
    thickness: draft.thickness,
    ...(draft.open ? { opening_normal: draft.normal.slice() } : {}),
  };
  if (!draft.featureId) operations.push({ op: "add_feature", feature });
  else if (
    JSON.stringify(feature.opening_normal ?? null) !==
    JSON.stringify(
      state.model.features.find((f) => f.id === draft.featureId)
        .opening_normal ?? null,
    )
  )
    operations.push({ op: "replace_feature", id: draft.featureId, feature });
  if (!operations.length) throw Error("Change the thickness or opening first");
  return {
    expected_revision: state.revision,
    operations,
    preserve: Object.keys(state.model.parameters).filter(
      (id) => id !== draft.thickness && !(id in (state.model.relations ?? {})),
    ),
  };
}
