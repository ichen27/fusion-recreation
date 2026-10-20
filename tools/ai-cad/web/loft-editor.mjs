import { loftCandidates, loftProposal } from "./loft-model.mjs";
const $ = (id) => document.getElementById(id);
export function installLoftEditor({ getState, onOpen, onClose, onPreview }) {
  const dialog = $("loft-dialog");
  let state,
    pending = false;
  function controls() {
    for (const id of [
      "loft-bottom",
      "loft-top",
      "loft-height",
      "loft-close",
      "loft-preview",
    ])
      $(id).disabled = pending;
  }
  function close() {
    if (pending) return;
    dialog.close();
    onClose();
  }
  $("loft-close").addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  $("loft-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (pending) return;
    try {
      const proposal = loftProposal(
        state,
        $("loft-bottom").value,
        $("loft-top").value,
        $("loft-height").value,
      );
      pending = true;
      controls();
      $("loft-feedback").textContent =
        "Checking matching vertices, planar sides and convexity…";
      await onPreview(proposal);
      pending = false;
      dialog.close();
      onClose();
    } catch (error) {
      pending = false;
      controls();
      $("loft-feedback").textContent = error.message;
    }
  });
  return {
    open() {
      state = structuredClone(getState());
      const candidates = loftCandidates(state);
      for (const [i, id] of ["loft-bottom", "loft-top"].entries()) {
        $(id).replaceChildren(
          ...candidates.map((body) => {
            const option = document.createElement("option");
            option.value = body.id;
            option.textContent = body.id;
            return option;
          }),
        );
        $(id).selectedIndex = Math.min(i, candidates.length - 1);
      }
      $("loft-height").value = "12";
      $("loft-feedback").textContent =
        "Join the bottom sketch at z=0 to the top sketch at the chosen height. Matching vertex IDs connect the sections. Both profiles must be convex and every side planar; twisted or curved sides reject. Existing solids are retained.";
      controls();
      onOpen();
      dialog.showModal();
    },
  };
}
