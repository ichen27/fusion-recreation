import {
  intersectionCandidates,
  intersectionProposal,
} from "./intersection-model.mjs";
const $ = (id) => document.getElementById(id);
export function installIntersectionEditor({
  getState,
  onOpen,
  onClose,
  onPreview,
}) {
  const dialog = $("intersection-dialog");
  let state,
    pending = false;
  function controls() {
    for (const id of [
      "intersection-left",
      "intersection-right",
      "intersection-close",
      "intersection-preview",
    ])
      $(id).disabled = pending;
  }
  function close() {
    if (pending) return;
    dialog.close();
    onClose();
  }
  $("intersection-close").addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  $("intersection-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (pending) return;
    try {
      const proposal = intersectionProposal(
        state,
        $("intersection-left").value,
        $("intersection-right").value,
      );
      pending = true;
      controls();
      $("intersection-feedback").textContent =
        "Checking convexity and common volume…";
      await onPreview(proposal);
      pending = false;
      dialog.close();
      onClose();
    } catch (error) {
      pending = false;
      controls();
      $("intersection-feedback").textContent = error.message;
    }
  });
  return {
    open() {
      state = structuredClone(getState());
      const candidates = intersectionCandidates(state);
      for (const [i, id] of [
        "intersection-left",
        "intersection-right",
      ].entries()) {
        $(id).replaceChildren(
          ...candidates.map((body) => {
            const option = document.createElement("option");
            option.value = body.feature_id;
            option.textContent = body.feature_id;
            return option;
          }),
        );
        $(id).selectedIndex = i;
      }
      $("intersection-feedback").textContent =
        "Keep only the volume shared by both solids. Preview validates convexity; saving replaces both visible inputs with one result. Undo restores them.";
      controls();
      onOpen();
      dialog.showModal();
    },
  };
}
