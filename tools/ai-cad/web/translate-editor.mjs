import {
  translationDraft,
  translationProposal,
  translationEditable,
} from "./translate-model.mjs";
const $ = (id) => document.getElementById(id);
const axes = ["x", "y", "z"];
export function installTranslateEditor({
  getState,
  onOpen,
  onClose,
  onPreview,
}) {
  const dialog = $("translate-dialog");
  let state,
    draft,
    pending = false;
  function controls() {
    $("translate-close").disabled = pending;
    $("translate-preview").disabled = pending;
    axes.forEach(
      (axis, i) =>
        ($("translate-" + axis).disabled =
          pending || !translationEditable(state, draft.offset[i])),
    );
  }
  function close() {
    if (pending) return;
    dialog.close();
    onClose();
  }
  $("translate-close").addEventListener("click", close);
  dialog.addEventListener("cancel", (e) => {
    e.preventDefault();
    close();
  });
  axes.forEach((axis, i) =>
    $("translate-" + axis).addEventListener("input", () => {
      const value = $("translate-" + axis).value;
      axes.forEach((other, j) => {
        if (draft.offset[j] === draft.offset[i])
          $("translate-" + other).value = value;
      });
    }),
  );
  $("translate-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (pending) return;
    draft.values = axes.map((axis) => $("translate-" + axis).value);
    try {
      const proposal = translationProposal(state, draft);
      pending = true;
      controls();
      $("translate-feedback").textContent =
        "Validating the moved solid and downstream features…";
      await onPreview(proposal);
      pending = false;
      dialog.close();
      onClose();
    } catch (error) {
      pending = false;
      controls();
      $("translate-feedback").textContent = error.message;
    }
  });
  return {
    open(input, featureId = null, kind = "translate") {
      state = structuredClone(getState());
      draft = translationDraft(state, input, featureId, kind);
      $("translate-title").textContent = featureId
        ? `Edit ${featureId}`
        : kind === "instance"
          ? `Linked copy of ${input}`
          : `Move ${input}`;
      axes.forEach(
        (axis, i) => ($("translate-" + axis).value = draft.values[i]),
      );
      $("translate-feedback").textContent =
        kind === "instance"
          ? "This copy stays linked to the source dimensions. Global offsets place it independently; the source remains available. Preview validates all dependent parts."
          : "Offsets use global X, Y and Z in millimeters. Dimensions and volume stay unchanged. Preview checks downstream cuts/intersections before saving.";
      controls();
      onOpen();
      dialog.showModal();
    },
  };
}
