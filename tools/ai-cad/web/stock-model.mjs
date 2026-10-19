// Browser authoring produces the same typed feature/parameter operations as MCP.
export function stockProposal(state, kind, values) {
  const fields =
    kind === "block"
      ? ["width", "depth", "height"]
      : kind === "cylinder"
        ? ["x", "y", "radius", "height"]
        : null;
  if (!fields) throw Error("Choose block or circular stock");
  let id;
  for (let i = 1; i <= 33; i++) {
    const candidate = `stock${i}`;
    if (
      !state.model.features.some(
        (f) => f.id === candidate || f.id.startsWith(candidate + "."),
      ) &&
      !Object.keys(state.model.parameters).some(
        (p) => p === candidate || p.startsWith(candidate + "."),
      )
    ) {
      id = candidate;
      break;
    }
  }
  if (!id) throw Error("No unused stock IDs available");
  const feature = { kind, id },
    operations = [];
  for (const field of fields) {
    feature[field] = `${id}.${field}`;
    operations.push({
      op: "define_parameter",
      id: feature[field],
      mm: values[field],
    });
  }
  operations.push({ op: "add_feature", feature });
  return {
    expected_revision: state.revision,
    operations,
    preserve: Object.keys(state.model.parameters).filter(
      (id) => !(id in (state.model.relations ?? {})),
    ),
  };
}
