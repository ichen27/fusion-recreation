export function parameterEditable(state, reference) {
  return (
    !(reference in state.model.fixed) &&
    !(reference in (state.model.relations ?? {}))
  );
}
export function vectorOperations(state, references, coordinates, create) {
  const values = new Map();
  references.forEach((id, i) => {
    if (values.has(id) && values.get(id) !== coordinates[i])
      throw Error("Shared coordinate references must have one value");
    values.set(id, coordinates[i]);
  });
  const operations = [];
  for (const [id, mm] of values) {
    if (create) operations.push({ op: "define_parameter", id, mm });
    else if (mm !== state.model.parameters[id]) {
      if (!parameterEditable(state, id))
        throw Error(
          "Coordinate is fixed or derived; edit its controlling parameter",
        );
      operations.push({ op: "set_parameter", id, mm });
    }
  }
  return operations;
}
