const $ = (id) => document.getElementById(id);
export function referenceProposal(state, id, feature, target, remove = false) {
  id = id.trim();
  if (!/^[A-Za-z0-9_.-]{1,64}$/.test(id))
    throw Error(
      "Use 1–64 letters, digits, dots, underscores or hyphens for the name.",
    );
  if (remove && !Object.hasOwn(state.model.references ?? {}, id))
    throw Error("Choose an existing saved reference to remove.");
  if (!remove && !state.bodies.some((body) => body.feature_id === feature))
    throw Error("Choose an existing terminal solid.");
  if (
    !remove &&
    (target.kind === "surface"
      ? !target.surface_id
      : !target.surfaces[0] ||
        !target.surfaces[1] ||
        target.surfaces[0] === target.surfaces[1])
  )
    throw Error(
      "Choose an authored surface, or two distinct adjacent surfaces for an edge chain.",
    );
  return {
    expected_revision: state.revision,
    operations: [
      remove
        ? { op: "remove_reference", id }
        : {
            op: "set_reference",
            id,
            feature_id: feature,
            target: structuredClone(target),
          },
    ],
    preserve: [],
  };
}
export function installReferenceEditor({
  getState,
  onOpen,
  onClose,
  onPreview,
  onSelect,
}) {
  const dialog = $("reference-dialog");
  let state,
    topology,
    pending = false;
  function choices(id, values) {
    $(id).replaceChildren(
      ...values.map(([value, text]) => {
        const node = document.createElement("option");
        node.value = value;
        node.textContent = text;
        return node;
      }),
    );
  }
  function controls() {
    for (const node of dialog.querySelectorAll("button,input,select"))
      node.disabled = pending;
    const existing = Object.hasOwn(
      state.model.references ?? {},
      $("reference-saved").value,
    );
    $("reference-remove").disabled = pending || !existing;
    $("reference-select").disabled =
      pending ||
      !existing ||
      state.model.references[$("reference-saved").value]?.target.kind !==
        "surface";
    $("reference-preview").disabled =
      pending || topology?.naming !== "authored_surfaces";
    $("reference-second-label").hidden =
      $("reference-kind").value !== "edge_chain";
  }
  function close() {
    if (!pending) {
      dialog.close();
      onClose();
    }
  }
  async function loadTarget(target) {
    pending = true;
    topology = null;
    controls();
    $("reference-feedback").textContent = "Inspecting the saved solid…";
    choices("reference-first", []);
    choices("reference-second", []);
    try {
      const response = await fetch("/api/topology", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_revision: state.revision,
          feature_id: $("reference-body").value,
        }),
      });
      const reply = await response.json();
      if (reply.error)
        throw Error(`${reply.error.code}: ${reply.error.message}`);
      topology = reply.result;
      if (topology.naming !== "authored_surfaces")
        throw Error(
          "This solid has generated face indices. Saved references currently require authored analytic surfaces.",
        );
      const surfaces = Object.keys(topology.surfaces).map((id) => [id, id]);
      choices("reference-first", surfaces);
      choices("reference-second", surfaces);
      if (target) {
        $("reference-kind").value = target.kind;
        $("reference-first").value = target.surface_id ?? target.surfaces[0];
        if (target.surfaces) $("reference-second").value = target.surfaces[1];
      }
      $("reference-feedback").textContent =
        "Dimension edits retain the name. Structural changes require explicitly removing or rebinding it. Edge chains must be connected intersections of two surfaces.";
    } catch (error) {
      $("reference-feedback").textContent = error.message;
    } finally {
      pending = false;
      controls();
    }
  }
  async function loadSaved() {
    const id = $("reference-saved").value;
    const saved = Object.hasOwn(state.model.references ?? {}, id)
      ? state.model.references[id]
      : null;
    $("reference-name").value = saved ? id : "";
    if (saved) $("reference-body").value = saved.feature_id;
    await loadTarget(saved?.target);
  }
  async function submit(remove) {
    if (pending) return;
    try {
      const target =
        $("reference-kind").value === "surface"
          ? { kind: "surface", surface_id: $("reference-first").value }
          : {
              kind: "edge_chain",
              surfaces: [
                $("reference-first").value,
                $("reference-second").value,
              ],
            };
      const proposal = referenceProposal(
        state,
        remove ? $("reference-saved").value : $("reference-name").value,
        $("reference-body").value,
        target,
        remove,
      );
      pending = true;
      controls();
      $("reference-feedback").textContent = "Validating the named reference…";
      await onPreview(proposal);
      pending = false;
      close();
    } catch (error) {
      pending = false;
      controls();
      $("reference-feedback").textContent = error.message;
    }
  }
  $("reference-body").addEventListener("change", () => loadTarget());
  $("reference-saved").addEventListener("change", loadSaved);
  $("reference-kind").addEventListener("change", controls);
  $("reference-close").addEventListener("click", close);
  $("reference-remove").addEventListener("click", () => submit(true));
  $("reference-select").addEventListener("click", async () => {
    const reference = state.resolved_references?.[$("reference-saved").value];
    if (!reference || reference.target.kind !== "surface" || pending) return;
    close();
    await onSelect(reference.feature_id, reference.target.surface_id);
  });
  $("reference-form").addEventListener("submit", (event) => {
    event.preventDefault();
    submit(false);
  });
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  return {
    open() {
      state = structuredClone(getState());
      choices("reference-saved", [
        ["", "New reference"],
        ...Object.keys(state.model.references ?? {}).map((id) => [id, id]),
      ]);
      choices(
        "reference-body",
        state.bodies.map((body) => [body.feature_id, body.feature_id]),
      );
      $("reference-kind").value = "surface";
      onOpen();
      dialog.showModal();
      loadSaved();
    },
  };
}
