const $ = (id) => document.getElementById(id);

export function massRequest(state, entries) {
  if (!entries.length || entries.length > 16)
    throw Error("Select between 1 and 16 parts.");
  const ids = new Set();
  const parts = entries.map(({ feature_id, density }) => {
    if (
      ids.has(feature_id) ||
      !state.bodies.some((b) => b.feature_id === feature_id)
    )
      throw Error("Select each saved solid once.");
    ids.add(feature_id);
    if (typeof density !== "string" || !density.trim())
      throw Error(`Enter a density for ${feature_id}.`);
    return { feature_id, density_kg_per_m3: density.trim() };
  });
  return { expected_revision: state.revision, parts };
}

export function installMassEditor({ getState, onOpen, onClose }) {
  const dialog = $("mass-dialog");
  let state,
    rows = [],
    pending = false;
  function controls() {
    for (const node of dialog.querySelectorAll("button,input"))
      node.disabled = pending;
    for (const row of rows)
      row.density.disabled = pending || !row.select.checked;
  }
  function clear() {
    $("mass-result").replaceChildren();
    controls();
  }
  function close() {
    if (pending) return;
    dialog.close();
    onClose();
  }
  $("mass-close").addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  $("mass-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (pending) return;
    const result = $("mass-result");
    try {
      const command = massRequest(
        state,
        rows
          .filter((r) => r.select.checked)
          .map((r) => ({ feature_id: r.id, density: r.density.value })),
      );
      pending = true;
      controls();
      result.textContent = "Calculating exact mass properties…";
      const reply = await (
        await fetch("/api/mass-set", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(command),
        })
      ).json();
      if (getState().revision !== state.revision)
        throw Error(
          "The saved model changed. Close and reopen this measurement.",
        );
      if (reply.error)
        throw Error(`${reply.error.code}: ${reply.error.message}`);
      const info = reply.result;
      result.replaceChildren();
      for (const text of [
        `Saved revision: ${info.revision}.`,
        `Combined mass: ${info.mass_kg} kg.`,
        `Center of mass mm: (${info.center_of_mass_mm.join(", ")}).`,
        "Each selected occurrence is counted separately, including any overlap.",
      ]) {
        const p = document.createElement("p");
        p.textContent = text;
        result.append(p);
      }
      const details = document.createElement("details"),
        title = document.createElement("summary"),
        tensor = document.createElement("pre");
      title.textContent = "Centroidal mass inertia · kg m² · global XYZ";
      tensor.textContent = info.centroidal_inertia_kg_m2
        .map((row) => row.join("  "))
        .join("\n");
      details.append(title, tensor);
      result.append(details);
    } catch (error) {
      result.textContent = error.message;
    } finally {
      pending = false;
      controls();
    }
  });
  return {
    open() {
      state = structuredClone(getState());
      rows = [];
      const list = $("mass-parts");
      list.replaceChildren();
      for (const body of state.bodies) {
        const field = document.createElement("fieldset"),
          label = document.createElement("label"),
          select = document.createElement("input"),
          densityLabel = document.createElement("label"),
          density = document.createElement("input");
        select.type = "checkbox";
        select.setAttribute("aria-label", `Include ${body.feature_id}`);
        label.append(select, document.createTextNode(body.feature_id));
        density.type = "text";
        density.required = true;
        density.maxLength = 80;
        density.setAttribute("aria-label", `Density for ${body.feature_id}`);
        densityLabel.append(
          document.createTextNode("Uniform density · kg/m³"),
          density,
        );
        select.addEventListener("change", clear);
        density.addEventListener("input", clear);
        field.append(label, densityLabel);
        list.append(field);
        rows.push({ id: body.feature_id, select, density });
      }
      clear();
      onOpen();
      dialog.showModal();
    },
  };
}
