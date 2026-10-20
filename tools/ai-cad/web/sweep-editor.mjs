import {
  sweepCandidates,
  sweepDraft,
  sweepProposal,
  sweepEditable,
} from "./sweep-model.mjs";
const $ = (id) => document.getElementById(id);
const axes = ["x", "y", "z"];
export function installSweepEditor({ getState, onOpen, onClose, onPreview }) {
  const dialog = $("sweep-dialog");
  let state,
    draft,
    pending = false;
  function controls() {
    $("sweep-close").disabled = pending;
    $("sweep-profile").disabled = pending;
    $("sweep-preview").disabled = pending;
    axes.forEach(
      (axis, i) =>
        ($("sweep-" + axis).disabled =
          pending || !sweepEditable(state, draft.offset[i])),
    );
  }
  function close() {
    if (pending) return;
    dialog.close();
    onClose();
  }
  $("sweep-close").addEventListener("click", close);
  dialog.addEventListener("cancel", (e) => {
    e.preventDefault();
    close();
  });
  axes.forEach((axis, i) =>
    $("sweep-" + axis).addEventListener("input", () => {
      const value = $("sweep-" + axis).value;
      axes.forEach((other, j) => {
        if (draft.offset[j] === draft.offset[i])
          $("sweep-" + other).value = value;
      });
    }),
  );
  $("sweep-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (pending) return;
    draft.profile = $("sweep-profile").value;
    draft.values = axes.map((axis) => $("sweep-" + axis).value);
    try {
      const proposal = sweepProposal(state, draft);
      pending = true;
      controls();
      $("sweep-feedback").textContent =
        "Validating the swept profile and downstream features…";
      await onPreview(proposal);
      pending = false;
      dialog.close();
      onClose();
    } catch (error) {
      pending = false;
      controls();
      $("sweep-feedback").textContent = error.message;
    }
  });
  return {
    open(featureId = null) {
      state = structuredClone(getState());
      draft = sweepDraft(state, featureId);
      $("sweep-title").textContent = featureId
        ? `Edit ${featureId}`
        : "Straight profile sweep";
      $("sweep-profile").replaceChildren(
        ...sweepCandidates(state, featureId).map((f) => {
          const option = document.createElement("option");
          option.value = f.id;
          option.textContent = f.id;
          return option;
        }),
      );
      $("sweep-profile").value = draft.profile;
      axes.forEach((axis, i) => ($("sweep-" + axis).value = draft.values[i]));
      $("sweep-feedback").textContent =
        "Translate an XY sketch along a straight XYZ displacement. Z must be nonzero. Cross-section orientation stays fixed; edit the source sketch to reshape it.";
      controls();
      onOpen();
      dialog.showModal();
    },
  };
}
