import { linearProposal } from "./linear-model.mjs";
const $ = (id) => document.getElementById(id);
const term = () => ({ parameter: "", coefficient: "1" });
const equation = () => ({ terms: [term(), term()], offset: "0" });
export function installLinearEditor({ getState, onOpen, onClose, onPreview }) {
  const dialog = $("linear-dialog");
  let state,
    draft,
    pending = false;
  const button = (text, label, action) => {
    const node = document.createElement("button");
    node.type = "button";
    node.textContent = text;
    node.setAttribute("aria-label", label);
    node.addEventListener("click", action);
    return node;
  };
  function controls() {
    for (const node of dialog.querySelectorAll("input,select,button"))
      node.disabled = pending || node.dataset.atLimit === "true";
  }
  function close() {
    if (pending) return;
    dialog.close();
    onClose();
  }
  function renderRows() {
    $("linear-equations").replaceChildren(
      ...draft.equations.map((row, index) => {
        const field = document.createElement("fieldset");
        const legend = document.createElement("legend");
        legend.textContent = `Equation ${index + 1}`;
        field.append(legend);
        for (const [j, value] of row.terms.entries()) {
          const line = document.createElement("div");
          line.className = "linear-term";
          const coefficient = document.createElement("input");
          coefficient.value = value.coefficient;
          coefficient.required = true;
          coefficient.setAttribute(
            "aria-label",
            `Equation ${index + 1} term ${j + 1} coefficient`,
          );
          coefficient.addEventListener(
            "input",
            () => (value.coefficient = coefficient.value),
          );
          const parameter = document.createElement("select");
          parameter.setAttribute(
            "aria-label",
            `Equation ${index + 1} term ${j + 1} dimension`,
          );
          const choices = [
            ["", "Choose dimension"],
            ...Object.keys(state.model.parameters)
              .sort()
              .map((id) => [id, id]),
          ];
          for (const [id, name] of choices) {
            const option = document.createElement("option");
            option.value = id;
            option.textContent = name;
            parameter.append(option);
          }
          parameter.value = value.parameter;
          parameter.addEventListener(
            "change",
            () => (value.parameter = parameter.value),
          );
          const remove = button(
            "×",
            `Remove equation ${index + 1} term ${j + 1}`,
            () => {
              row.terms.splice(j, 1);
              renderRows();
            },
          );
          remove.dataset.atLimit = String(row.terms.length === 1);
          line.append(coefficient, parameter, remove);
          field.append(line);
        }
        const add = button(
          "+ Term",
          `Add term to equation ${index + 1}`,
          () => {
            row.terms.push(term());
            renderRows();
          },
        );
        add.dataset.atLimit = String(row.terms.length >= 8);
        field.append(add);
        const label = document.createElement("label");
        label.className = "linear-rhs";
        label.textContent = "Sum of terms equals (mm)";
        const rhs = document.createElement("input");
        rhs.value = row.offset;
        rhs.required = true;
        rhs.setAttribute("aria-label", `Equation ${index + 1} right side mm`);
        rhs.addEventListener("input", () => (row.offset = rhs.value));
        label.append(rhs);
        field.append(label);
        const remove = button(
          "Remove equation",
          `Remove equation ${index + 1}`,
          () => {
            draft.equations.splice(index, 1);
            renderRows();
          },
        );
        remove.dataset.atLimit = String(draft.equations.length === 1);
        field.append(remove);
        return field;
      }),
    );
    $("linear-add-equation").dataset.atLimit = String(
      draft.equations.length >= 32,
    );
    controls();
  }
  $("linear-add-equation").addEventListener("click", () => {
    draft.equations.push(equation());
    renderRows();
  });
  $("linear-close").addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  $("linear-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (pending) return;
    try {
      const proposal = linearProposal(state, draft);
      pending = true;
      controls();
      $("linear-feedback").textContent =
        "Solving exact relationships and checking the resulting parts…";
      await onPreview(proposal);
      pending = false;
      close();
    } catch (error) {
      pending = false;
      controls();
      $("linear-feedback").textContent = error.message;
    }
  });
  return {
    open() {
      state = structuredClone(getState());
      draft = { targets: [], equations: [equation()] };
      $("linear-targets").replaceChildren(
        ...Object.keys(state.model.parameters)
          .sort()
          .map((id) => {
            const label = document.createElement("label");
            const input = document.createElement("input");
            input.type = "checkbox";
            input.value = id;
            input.setAttribute("aria-label", `Solve for ${id}`);
            input.addEventListener("change", () => {
              draft.targets = input.checked
                ? [...draft.targets, id]
                : draft.targets.filter((p) => p !== id);
            });
            label.append(
              input,
              document.createTextNode(
                `${id} (${state.model.parameters[id]} mm)`,
              ),
            );
            return label;
          }),
      );
      $("linear-feedback").textContent =
        "Choose target dimensions and enter the equations that should determine them.";
      renderRows();
      onOpen();
      dialog.showModal();
    },
  };
}
