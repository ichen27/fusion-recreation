// Keep selection and editing visible; disclose new modeling actions on demand.
const editClasses = {
  straight_sweep: "edit-sweep",
  revolve: "edit-revolve",
  polygon_profile: "edit-sketch",
  planar_profile: "edit-sketch",
  through_holes: "edit-holes",
  blind_holes: "edit-holes",
  counterbore_holes: "edit-holes",
  countersink_holes: "edit-holes",
  linear_pattern: "edit-pattern",
  mirror_plane: "edit-mirror",
  planar_shell: "edit-shell",
  plane_cut: "edit-plane",
  translate: "edit-move",
  instance: "edit-instance",
  rotate_quarter: "edit-rotation",
  boolean: "edit-boolean",
  coaxial_boolean: "edit-boolean",
};
export function createFeatureActions() {
  let expanded = null;
  return (row, feature) => {
    const buttons = [...row.querySelectorAll(":scope > button")];
    const editClass = editClasses[feature.kind];
    const edit = editClass
      ? buttons.find((button) => button.classList.contains(editClass))
      : null;
    const secondary = buttons.filter(
      (button) => button !== edit && !button.classList.contains("select-body"),
    );
    if (!secondary.length) return;
    const details = document.createElement("details");
    details.className = "feature-actions";
    details.dataset.feature = feature.id;
    details.open = expanded === feature.id;
    const summary = document.createElement("summary");
    summary.textContent = "Modeling actions";
    summary.setAttribute("aria-label", `Modeling actions for ${feature.id}`);
    details.append(summary, ...secondary);
    details.addEventListener("toggle", () => {
      // Removed rows can still have queued toggle events after a model redraw.
      if (!details.isConnected) return;
      if (details.open) {
        expanded = feature.id;
        for (const other of document.querySelectorAll(".feature-actions[open]"))
          if (other !== details) other.open = false;
      } else if (expanded === feature.id) expanded = null;
    });
    row.append(details);
  };
}
