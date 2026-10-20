import {
  mirrorDraft,
  mirrorProposal,
  offsetEditable,
} from "./mirror-model.mjs";
const $ = (id) => document.getElementById(id);
export function installMirrorEditor({ getState, onOpen, onClose, onPreview }) {
  const dialog = $("mirror-dialog");
  let state,
    draft,
    pending = false;
  function controls() {
    for (const id of [
      "mirror-nx",
      "mirror-ny",
      "mirror-nz",
      "mirror-close",
      "mirror-keep",
      "mirror-preview",
    ])
      $(id).disabled = pending;
    $("mirror-offset").disabled = pending || !offsetEditable(state, draft);
  }
  function close() {
    if (pending) return;
    dialog.close();
    onClose();
  }
  $("mirror-close").addEventListener("click", close);
  dialog.addEventListener("cancel", (e) => {
    e.preventDefault();
    close();
  });
  $("mirror-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (pending) return;
    draft.normal = ["x", "y", "z"].map((axis) => $(`mirror-n${axis}`).value);
    draft.value = $("mirror-offset").value;
    draft.keep = $("mirror-keep").checked;
    try {
      const proposal = mirrorProposal(state, draft);
      pending = true;
      controls();
      $("mirror-feedback").textContent =
        "Reflecting the solid and checking downstream geometry…";
      await onPreview(proposal);
      pending = false;
      dialog.close();
      onClose();
    } catch (error) {
      pending = false;
      controls();
      $("mirror-feedback").textContent = error.message;
    }
  });
  return {
    open(input, featureId = null) {
      state = structuredClone(getState());
      draft = mirrorDraft(state, input, featureId);
      $("mirror-title").textContent = featureId
        ? `Edit ${featureId}`
        : `Mirror ${input}`;
      ["x", "y", "z"].forEach((axis, i) => {
        $(`mirror-n${axis}`).value = draft.normal[i];
      });
      $("mirror-offset").value = draft.value;
      $("mirror-keep").checked = draft.keep;
      $("mirror-feedback").textContent =
        "Reflect across nx × x + ny × y + nz × z = offset. Normal components are dimensionless ratios; offset follows their scale. Keep source creates a linked reflected part, with independently selectable geometry.";
      controls();
      onOpen();
      dialog.showModal();
    },
  };
}
