const $ = (id) => document.getElementById(id);
export function materialProposal(state, feature, name, density, clear = false) {
  const source = state.model.features.find((f) => f.id === feature);
  if (!source || ["polygon_profile", "planar_profile"].includes(source.kind))
    throw Error("Choose an existing solid feature.");
  let operation;
  if (clear) {
    if (!Object.hasOwn(state.model.materials ?? {}, feature))
      throw Error("This feature has no direct material override to clear.");
    operation = { op: "clear_material", feature_id: feature };
  } else {
    if (
      typeof name !== "string" ||
      !name.trim() ||
      typeof density !== "string" ||
      !density.trim()
    )
      throw Error("Enter a material name and a positive rational density.");
    operation = {
      op: "set_material",
      feature_id: feature,
      material: { name: name.trim(), density_kg_per_m3: density.trim() },
    };
  }
  return {
    expected_revision: state.revision,
    operations: [operation],
    preserve: [],
  };
}
export function installMaterialEditor({
  getState,
  onOpen,
  onClose,
  onPreview,
}) {
  const dialog = $("material-dialog");
  let state,
    pending = false;
  function controls() {
    for (const node of dialog.querySelectorAll("button,input,select"))
      node.disabled = pending;
    $("material-clear").disabled =
      pending ||
      !Object.hasOwn(state.model.materials ?? {}, $("material-target").value);
  }
  function loadTarget() {
    const feature = $("material-target").value;
    const direct = Object.hasOwn(state.model.materials ?? {}, feature)
      ? state.model.materials[feature]
      : null;
    const resolved = Object.hasOwn(state.resolved_materials ?? {}, feature)
      ? state.resolved_materials[feature]
      : null;
    const material = direct ?? resolved?.material;
    $("material-name").value = material?.name ?? "";
    $("material-density").value = material?.density_kg_per_m3 ?? "";
    $("material-feedback").textContent = direct
      ? "Editing this feature's saved override."
      : resolved?.status === "conflict"
        ? "Inputs have different or missing materials. A new override assigns one uniform material to the whole solid."
        : "A new override applies to this feature and descendants that inherit from it.";
    controls();
  }
  function close() {
    if (pending) return;
    dialog.close();
    onClose();
  }
  async function submit(clear) {
    if (pending) return;
    try {
      const proposal = materialProposal(
        state,
        $("material-target").value,
        $("material-name").value,
        $("material-density").value,
        clear,
      );
      pending = true;
      controls();
      $("material-feedback").textContent =
        "Checking the material assignment and model…";
      await onPreview(proposal);
      pending = false;
      dialog.close();
      onClose();
    } catch (error) {
      pending = false;
      controls();
      $("material-feedback").textContent = error.message;
    }
  }
  $("material-target").addEventListener("change", loadTarget);
  $("material-close").addEventListener("click", close);
  $("material-clear").addEventListener("click", () => submit(true));
  $("material-form").addEventListener("submit", (event) => {
    event.preventDefault();
    submit(false);
  });
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  return {
    open(feature) {
      state = structuredClone(getState());
      const select = $("material-target");
      select.replaceChildren();
      for (const f of state.model.features.filter(
        (f) => !["polygon_profile", "planar_profile"].includes(f.kind),
      )) {
        const option = document.createElement("option");
        option.value = f.id;
        option.textContent = `${f.id}${state.bodies.some((b) => b.feature_id === f.id) ? "" : " · retained source"}`;
        select.append(option);
      }
      select.value = feature;
      loadTarget();
      onOpen();
      dialog.showModal();
    },
  };
}
