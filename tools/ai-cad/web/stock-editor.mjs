import { stockProposal } from "./stock-model.mjs";
const $ = (id) => document.getElementById(id);
export function installStockEditor({ getState, onOpen, onClose, onPreview }) {
  const dialog = $("stock-dialog"),
    fields = [
      "width",
      "depth",
      "height",
      "x",
      "y",
      "radius",
      "bottom_radius",
      "top_radius",
    ];
  let state,
    pending = false;
  function controls() {
    const kind = $("stock-kind").value;
    for (const field of fields) {
      const active =
        field === "height" ||
        (kind === "conical_frustum"
          ? ["x", "y", "bottom_radius", "top_radius"].includes(field)
          : kind === "cylinder"
            ? ["x", "y", "radius"].includes(field)
            : ["width", "depth"].includes(field));
      $(`stock-${field}-row`).hidden = !active;
      $(`stock-${field}`).disabled = pending || !active;
    }
    for (const id of ["stock-kind", "stock-preview", "stock-close"])
      $(id).disabled = pending;
  }
  function close() {
    if (pending) return;
    dialog.close();
    onClose();
  }
  $("stock-close").addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  $("stock-kind").addEventListener("change", controls);
  $("stock-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (pending) return;
    try {
      const values = Object.fromEntries(
        fields.map((field) => [field, $(`stock-${field}`).value]),
      );
      const proposal = stockProposal(state, $("stock-kind").value, values);
      pending = true;
      controls();
      $("stock-feedback").textContent = "Checking stock dimensions…";
      await onPreview(proposal);
      pending = false;
      dialog.close();
      onClose();
    } catch (error) {
      pending = false;
      controls();
      $("stock-feedback").textContent = error.message;
    }
  });
  return {
    open() {
      state = structuredClone(getState());
      $("stock-kind").value = "block";
      for (const [field, value] of Object.entries({
        width: "60",
        depth: "40",
        height: "10",
        x: "0",
        y: "0",
        radius: "20",
        bottom_radius: "20",
        top_radius: "10",
      }))
        $(`stock-${field}`).value = value;
      $("stock-feedback").textContent =
        "Dimensions are in millimeters. Use integers or fractions. A block starts at the origin; circular stock uses the specified XY center. All extend upward from z=0. Tapered stock requires two positive, differing radii.";
      controls();
      onOpen();
      dialog.showModal();
    },
  };
}
