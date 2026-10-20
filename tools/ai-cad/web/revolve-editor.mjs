import { revolveCandidates, revolveProposal } from "./revolve-model.mjs";
const $ = (id) => document.getElementById(id);
export function installRevolveEditor({ getState, onOpen, onClose, onPreview }) {
  const dialog = $("revolve-dialog");
  let state,
    featureId = null,
    pending = false;
  function controls() {
    for (const id of ["revolve-profile", "revolve-close", "revolve-preview"])
      $(id).disabled = pending;
  }
  function close() {
    if (pending) return;
    dialog.close();
    onClose();
  }
  $("revolve-close").addEventListener("click", close);
  dialog.addEventListener("cancel", (e) => {
    e.preventDefault();
    close();
  });
  $("revolve-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (pending) return;
    try {
      const proposal = revolveProposal(
        state,
        $("revolve-profile").value,
        featureId,
      );
      pending = true;
      controls();
      $("revolve-feedback").textContent =
        "Checking the radial profile and full revolution…";
      await onPreview(proposal);
      pending = false;
      dialog.close();
      onClose();
    } catch (error) {
      pending = false;
      controls();
      $("revolve-feedback").textContent = error.message;
    }
  });
  return {
    open(id = null) {
      state = structuredClone(getState());
      featureId = id;
      $("revolve-title").textContent = id ? `Edit ${id}` : "Revolve profile";
      $("revolve-profile").replaceChildren(
        ...revolveCandidates(state, id).map((f) => {
          const o = document.createElement("option");
          o.value = f.id;
          o.textContent = f.id;
          return o;
        }),
      );
      if (id)
        $("revolve-profile").value = state.model.features.find(
          (f) => f.id === id,
        ).profile;
      $("revolve-feedback").textContent =
        "A full 360° turn around Z. Sketch X is radius; sketch Y is height along Z. Edit the source sketch to change dimensions.";
      controls();
      onOpen();
      dialog.showModal();
    },
  };
}
