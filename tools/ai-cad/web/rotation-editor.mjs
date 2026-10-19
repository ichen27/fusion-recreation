import {
  rotationDraft,
  rotationProposal,
  pivotEditable,
} from "./rotation-model.mjs";
const $ = (id) => document.getElementById(id),
  axes = ["x", "y", "z"];
export function installRotationEditor({
  getState,
  onOpen,
  onClose,
  onPreview,
}) {
  const dialog = $("rotation-dialog");
  let state,
    draft,
    pending = false;
  function controls() {
    for (const id of [
      "rotation-axis",
      "rotation-turns",
      "rotation-close",
      "rotation-preview",
    ])
      $(id).disabled = pending;
    axes.forEach(
      (axis, i) =>
        ($("rotation-" + axis).disabled =
          pending || !pivotEditable(state, draft.pivot[i])),
    );
  }
  function close() {
    if (pending) return;
    dialog.close();
    onClose();
  }
  $("rotation-close").addEventListener("click", close);
  dialog.addEventListener("cancel", (e) => {
    e.preventDefault();
    close();
  });
  axes.forEach((axis, i) =>
    $("rotation-" + axis).addEventListener("input", () => {
      const value = $("rotation-" + axis).value;
      axes.forEach((other, j) => {
        if (draft.pivot[j] === draft.pivot[i])
          $("rotation-" + other).value = value;
      });
    }),
  );
  $("rotation-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (pending) return;
    draft.axis = $("rotation-axis").value;
    draft.turns = Number($("rotation-turns").value);
    draft.values = axes.map((axis) => $("rotation-" + axis).value);
    try {
      const proposal = rotationProposal(state, draft);
      pending = true;
      controls();
      $("rotation-feedback").textContent =
        "Checking the rotated solid and downstream features…";
      await onPreview(proposal);
      pending = false;
      dialog.close();
      onClose();
    } catch (error) {
      pending = false;
      controls();
      $("rotation-feedback").textContent = error.message;
    }
  });
  return {
    open(input, featureId = null) {
      state = structuredClone(getState());
      draft = rotationDraft(state, input, featureId);
      $("rotation-title").textContent = featureId
        ? `Edit ${featureId}`
        : `Quarter-turn ${input}`;
      $("rotation-axis").value = draft.axis;
      $("rotation-turns").value = String(draft.turns);
      axes.forEach(
        (axis, i) => ($("rotation-" + axis).value = draft.values[i]),
      );
      $("rotation-feedback").textContent =
        "Positive rotations follow the right-hand rule about the selected global axis through the pivot. Dimensions and volume remain exact.";
      controls();
      onOpen();
      dialog.showModal();
    },
  };
}
