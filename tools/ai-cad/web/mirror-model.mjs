import { planeCandidate } from "./plane-model.mjs";
export function mirrorDraft(state, input, featureId = null) {
  const feature = featureId
    ? state.model.features.find(
        (f) => f.id === featureId && f.kind === "mirror_plane",
      )
    : null;
  if (featureId && !feature) throw Error("Select a mirrored solid");
  if (
    !feature &&
    !state.bodies.some((b) => b.feature_id === input && planeCandidate(b))
  )
    throw Error(
      "Select terminal unperforated planar stock or a previous planar Boolean/cut result",
    );
  let prefix = featureId;
  if (!prefix)
    for (let i = 1; i <= 33; i++) {
      const name = `mirror${i}`;
      if (
        !state.model.features.some((f) => f.id === name) &&
        !Object.keys(state.model.parameters).some(
          (p) => p === name || p.startsWith(name + "."),
        )
      ) {
        prefix = name;
        break;
      }
    }
  if (!prefix) throw Error("No unused mirror IDs available");
  return {
    featureId,
    input: feature?.input ?? input,
    id: prefix,
    normal: feature?.normal.slice() ?? ["1", "0", "0"],
    offset: feature?.offset ?? `${prefix}.offset`,
    value: feature ? state.model.parameters[feature.offset] : "0",
    keep: feature ? (feature.keep_original ?? false) : true,
  };
}
export function offsetEditable(state, draft) {
  return (
    !(draft.offset in state.model.fixed) &&
    !(draft.offset in (state.model.relations ?? {}))
  );
}
export function mirrorProposal(state, draft) {
  const operations = [];
  if (!draft.featureId)
    operations.push({
      op: "define_parameter",
      id: draft.offset,
      mm: draft.value,
    });
  else if (draft.value !== state.model.parameters[draft.offset]) {
    if (!offsetEditable(state, draft))
      throw Error("Offset is fixed or derived; edit its controlling parameter");
    operations.push({ op: "set_parameter", id: draft.offset, mm: draft.value });
  }
  const feature = {
    kind: "mirror_plane",
    id: draft.id,
    input: draft.input,
    normal: draft.normal.slice(),
    offset: draft.offset,
    keep_original: draft.keep,
  };
  if (!draft.featureId) operations.push({ op: "add_feature", feature });
  else if (
    feature.keep_original !==
      (state.model.features.find((f) => f.id === draft.featureId)
        .keep_original ?? false) ||
    JSON.stringify(feature.normal) !==
      JSON.stringify(
        state.model.features.find((f) => f.id === draft.featureId).normal,
      )
  )
    operations.push({ op: "replace_feature", id: draft.featureId, feature });
  if (!operations.length)
    throw Error("Change the plane or source retention first");
  return {
    expected_revision: state.revision,
    operations,
    preserve: Object.keys(state.model.parameters).filter(
      (id) => id !== draft.offset && !(id in (state.model.relations ?? {})),
    ),
  };
}
