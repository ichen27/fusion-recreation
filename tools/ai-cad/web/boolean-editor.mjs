import { booleanCandidates, booleanProposal } from "./boolean-model.mjs";
const $ = (id) => document.getElementById(id);
export function installBooleanEditor({ getState, onOpen, onClose, onPreview }) {
  const dialog = $("boolean-dialog");
  let state,
    feature,
    pending = false;
  function controls() {
    for (const id of ["boolean-close", "boolean-preview", "boolean-operation"])
      $(id).disabled = pending;
    for (const id of ["boolean-kind", "boolean-left", "boolean-right"])
      $(id).disabled = pending || !!feature;
  }
  function close() {
    if (pending) return;
    dialog.close();
    onClose();
  }
  $("boolean-close").addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  $("boolean-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (pending) return;
    try {
      const proposal = booleanProposal(
        state,
        $("boolean-left").value,
        $("boolean-right").value,
        $("boolean-operation").value,
        feature?.id,
        $("boolean-kind").value,
      );
      pending = true;
      controls();
      $("boolean-feedback").textContent =
        "Checking exact volume, face holes and solid components…";
      await onPreview(proposal);
      pending = false;
      dialog.close();
      onClose();
    } catch (error) {
      pending = false;
      controls();
      $("boolean-feedback").textContent = error.message;
    }
  });
  function populate() {
    const candidates = feature
      ? [feature.left, feature.right]
      : booleanCandidates(state, $("boolean-kind").value).map(
          (b) => b.feature_id,
        );
    for (const [i, id] of ["boolean-left", "boolean-right"].entries()) {
      $(id).replaceChildren(
        ...candidates.map((name) => {
          const o = document.createElement("option");
          o.value = name;
          o.textContent = name;
          return o;
        }),
      );
      $(id).selectedIndex = i;
    }
    $("boolean-feedback").textContent =
      $("boolean-kind").value === "coaxial_boolean"
        ? "Join, cut or keep common material on exactly one shared coordinate-axis line. Stepped radial sections are supported. Disconnected sections, enclosed contour holes and multiple axis contacts reject. Saving consumes both inputs; undo restores them."
        : "Union joins volumes; difference removes the second solid from the first; intersection keeps shared volume. Saving consumes both inputs. Undo restores them.";
  }
  $("boolean-kind").addEventListener("change", populate);
  return {
    open(featureId = null) {
      state = structuredClone(getState());
      feature = featureId
        ? state.model.features.find(
            (f) =>
              f.id === featureId &&
              ["boolean", "coaxial_boolean"].includes(f.kind),
          )
        : null;
      $("boolean-kind").value =
        feature?.kind ??
        (booleanCandidates(state).length >= 2 ? "boolean" : "coaxial_boolean");
      populate();
      $("boolean-operation").value = feature?.operation ?? "union";
      controls();
      onOpen();
      dialog.showModal();
    },
  };
}
