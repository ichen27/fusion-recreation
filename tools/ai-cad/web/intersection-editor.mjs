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
      "intersection-kind",
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
        $("intersection-kind").value,
      );
      pending = true;
      controls();
      $("intersection-feedback").textContent =
        "Checking the selected geometry and common volume…";
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
  function populate() {
    const kind = $("intersection-kind").value;
    const candidates = intersectionCandidates(state, kind);
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
      kind === "coaxial_intersection"
        ? "Keep shared volume of cylinders, frusta or simple radial-profile revolutions on exactly the same axis. Stepped and undercut sections are supported when the result has one connected radial contour. Cavities, separate regions and offset/crossing axes reject. Saving consumes both inputs; undo restores them."
        : "Keep only the volume shared by two convex planar solids. Saving consumes both inputs; undo restores them.";
  }
  $("intersection-kind").addEventListener("change", populate);
  return {
    open() {
      state = structuredClone(getState());
      $("intersection-kind").value =
        intersectionCandidates(state).length >= 2
          ? "intersection"
          : "coaxial_intersection";
      populate();
      controls();
      onOpen();
      dialog.showModal();
    },
  };
}
