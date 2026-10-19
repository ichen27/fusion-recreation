import { planeDraft, planeProposal, offsetEditable } from "./plane-model.mjs";
const $ = (id) => document.getElementById(id);
export function installPlaneEditor({ getState, onOpen, onClose, onPreview }) {
  const dialog = $("plane-dialog");
  let state,
    draft,
    pending = false;
  function controls() {
    for (const id of [
      "plane-nx",
      "plane-ny",
      "plane-nz",
      "plane-close",
      "plane-preview",
    ])
      $(id).disabled = pending;
    $("plane-offset").disabled = pending || !offsetEditable(state, draft);
  }
  function close() {
    if (pending) return;
    dialog.close();
    onClose();
  }
  $("plane-close").addEventListener("click", close);
  dialog.addEventListener("cancel", (e) => {
    e.preventDefault();
    close();
  });
  $("plane-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (pending) return;
    draft.normal = ["x", "y", "z"].map((axis) => $(`plane-n${axis}`).value);
    draft.value = $("plane-offset").value;
    try {
      const proposal = planeProposal(state, draft);
      pending = true;
      controls();
      $("plane-feedback").textContent = "Validating the remaining solid…";
      await onPreview(proposal);
      pending = false;
      dialog.close();
      onClose();
    } catch (error) {
      pending = false;
      controls();
      $("plane-feedback").textContent = error.message;
    }
  });
  return {
    open(input, featureId = null) {
      state = structuredClone(getState());
      draft = planeDraft(state, input, featureId);
      $("plane-title").textContent = featureId
        ? `Edit ${featureId}`
        : `Cut ${input} with a plane`;
      ["x", "y", "z"].forEach((axis, i) => {
        $(`plane-n${axis}`).value = draft.normal[i];
      });
      $("plane-offset").value = draft.value;
      $("plane-feedback").textContent =
        "Keep the side where nx × x + ny × y + nz × z ≤ offset. Normal components are dimensionless ratios. Offset is in mm for those ratios, not necessarily perpendicular distance.";
      controls();
      onOpen();
      dialog.showModal();
    },
  };
}
