export function linearProposal(state, draft) {
  const parameters = state.model.parameters;
  const targets = [...draft.targets];
  if (!targets.length || targets.length > 16)
    throw Error("Choose 1–16 dimensions to solve for.");
  if (
    new Set(targets).size !== targets.length ||
    targets.some((id) => !Object.hasOwn(parameters, id))
  )
    throw Error("Choose distinct existing target dimensions.");
  if (!draft.equations.length || draft.equations.length > 32)
    throw Error("Add 1–32 equations.");
  const equations = draft.equations.map((row, index) => {
    if (!row.terms.length || row.terms.length > 8)
      throw Error(`Equation ${index + 1} needs 1–8 terms.`);
    const terms = Object.create(null);
    for (const term of row.terms) {
      if (!Object.hasOwn(parameters, term.parameter))
        throw Error(
          `Choose a dimension for every term in equation ${index + 1}.`,
        );
      if (Object.hasOwn(terms, term.parameter))
        throw Error(
          `Combine repeated ${term.parameter} terms in equation ${index + 1}.`,
        );
      if (!term.coefficient.trim())
        throw Error(`Enter every coefficient in equation ${index + 1}.`);
      terms[term.parameter] = term.coefficient.trim();
    }
    if (!row.offset.trim())
      throw Error(`Enter the right side of equation ${index + 1}.`);
    return { id: `equation${index + 1}`, terms, offset_mm: row.offset.trim() };
  });
  return {
    expected_revision: state.revision,
    operations: [{ op: "constrain_linear", targets, equations }],
    preserve: Object.keys(parameters).filter(
      (id) =>
        !targets.includes(id) &&
        !Object.hasOwn(state.model.relations ?? {}, id),
    ),
  };
}
