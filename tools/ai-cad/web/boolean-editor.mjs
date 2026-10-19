import { booleanCandidates, booleanProposal } from "./boolean-model.mjs";
const $ = (id) => document.getElementById(id);
export function installBooleanEditor({ getState, onOpen, onClose, onPreview }) {
  const dialog = $("boolean-dialog");
  let state,
    feature,
    pending = false;
  function controls() {
    for (const id of ["boolean-close", "boolean-preview", "boolean-operation"])
      $(id).disabled = pending;
    for (const id of ["boolean-left", "boolean-right"])
      $(id).disabled = pending || !!feature;
  }
  function close() {
    if (pending) return;
    dialog.close();
    onClose();
  }
  $("boolean-close").addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  $("boolean-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (pending) return;
    try {
      const proposal = booleanProposal(
        state,
        $("boolean-left").value,
        $("boolean-right").value,
        $("boolean-operation").value,
        feature?.id,
      );
      pending = true;
      controls();
      $("boolean-feedback").textContent =
        "Checking exact volume, face holes and solid components…";
      await onPreview(proposal);
      pending = false;
      dialog.close();
      onClose();
    } catch (error) {
      pending = false;
      controls();
      $("boolean-feedback").textContent = error.message;
    }
  });
  return {
    open(featureId = null) {
      state = structuredClone(getState());
      feature = featureId
        ? state.model.features.find(
            (f) => f.id === featureId && f.kind === "boolean",
          )
        : null;
      const candidates = feature
        ? [feature.left, feature.right]
        : booleanCandidates(state).map((b) => b.feature_id);
      for (const [i, id] of ["boolean-left", "boolean-right"].entries()) {
        $(id).replaceChildren(
          ...candidates.map((name) => {
            const option = document.createElement("option");
            option.value = name;
            option.textContent = name;
            return option;
          }),
        );
        $(id).selectedIndex = i;
      }
      $("boolean-operation").value = feature?.operation ?? "union";
      $("boolean-feedback").textContent =
        "Union joins volumes; difference removes the second solid from the first; intersection keeps shared volume. Saving consumes both inputs. Undo restores them.";
      controls();
      onOpen();
      dialog.showModal();
    },
  };
}
