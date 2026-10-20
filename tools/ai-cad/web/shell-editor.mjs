import {
  shellDraft,
  shellProposal,
  thicknessEditable,
} from "./shell-model.mjs";
const $ = (id) => document.getElementById(id);
export function installShellEditor({ getState, onOpen, onClose, onPreview }) {
  const dialog = $("shell-dialog");
  let state,
    draft,
    pending = false;
  function controls() {
    for (const id of ["shell-open", "shell-close", "shell-preview"])
      $(id).disabled = pending;
    $("shell-thickness").disabled = pending || !thicknessEditable(state, draft);
    for (const axis of "xyz")
      $(`shell-n${axis}`).disabled = pending || !$("shell-open").checked;
  }
  function close() {
    if (pending) return;
    dialog.close();
    onClose();
  }
  $("shell-close").addEventListener("click", close);
  $("shell-open").addEventListener("change", controls);
  dialog.addEventListener("cancel", (e) => {
    e.preventDefault();
    close();
  });
  $("shell-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (pending) return;
    draft.value = $("shell-thickness").value;
    draft.open = $("shell-open").checked;
    draft.normal = ["x", "y", "z"].map((axis) => $(`shell-n${axis}`).value);
    try {
      const proposal = shellProposal(state, draft);
      pending = true;
      controls();
      $("shell-feedback").textContent =
        "Checking wall thickness and the hollow solid…";
      await onPreview(proposal);
      pending = false;
      dialog.close();
      onClose();
    } catch (error) {
      pending = false;
      controls();
      $("shell-feedback").textContent = error.message;
    }
  });
  return {
    open(input, featureId = null) {
      state = structuredClone(getState());
      draft = shellDraft(state, input, featureId);
      $("shell-title").textContent = featureId
        ? `Edit ${featureId}`
        : `Hollow ${input}`;
      $("shell-thickness").value = draft.value;
      $("shell-open").checked = draft.open;
      ["x", "y", "z"].forEach((axis, i) => {
        $(`shell-n${axis}`).value = draft.normal[i];
      });
      $("shell-feedback").textContent =
        "Walls extend inward. Source dimensions remain unchanged. The engine checks convexity, exact offsets and remaining interior.";
      controls();
      onOpen();
      dialog.showModal();
    },
  };
}
