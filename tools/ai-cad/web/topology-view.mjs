function label(reference) {
  if (reference.startsWith("evaluated/face/"))
    return `Face ${Number(reference.split("/").at(-1)) + 1}`;
  const role = reference.split("/").slice(2);
  if (role[0] === "cap") return `${role[1] === "top" ? "Top" : "Bottom"} cap`;
  if (role[0] === "outer")
    return role[1] === "frustum"
      ? "Conical wall"
      : role[1] === "cylinder"
        ? "Outer cylinder"
        : `Side ${role[2]} / ${role[3]}`;
  const names = {
    upper: "upper recess wall",
    lower: "lower through wall",
    wall: "wall",
    floor: "floor",
    shoulder: "shoulder",
    taper: "conical recess",
  };
  return `Hole ${role[1]} · ${names[role[2]] ?? role[2]}`;
}
export function renderTopology(container, info, onSelect, onMeasureEdge) {
  container.replaceChildren();
  const summary = document.createElement("p");
  summary.textContent = `${Object.keys(info.surfaces).length} surfaces · ${info.shells.length} closed shell${info.shells.length === 1 ? "" : "s"} · ${info.components.length} material component${info.components.length === 1 ? "" : "s"}.`;
  container.append(summary);
  const note = document.createElement("p");
  note.textContent =
    info.naming === "authored_surfaces"
      ? "Surface names follow feature, hole and profile IDs. Refresh references after edits."
      : "These face references apply to this saved revision. Refresh after edits.";
  container.append(note);
  if (onMeasureEdge) {
    const section = document.createElement("section"),
      select = document.createElement("select"),
      button = document.createElement("button"),
      output = document.createElement("p"),
      hint = document.createElement("p");
    select.id = "measurement-edge";
    select.setAttribute("aria-label", "Edge to measure");
    for (const [index, edge] of info.edges.entries()) {
      const option = document.createElement("option");
      option.value = index;
      option.textContent = `Edge ${index + 1} · ${edge.curve.kind === "line" ? "line" : "quarter circle"} · vertices ${edge.vertices.map((v) => v + 1).join(" → ")}`;
      select.append(option);
    }
    button.id = "measure-edge";
    button.type = "button";
    button.textContent = "Measure edge";
    output.id = "edge-measurement";
    output.setAttribute("role", "status");
    hint.textContent =
      "Edge numbers apply to this saved revision. Some edges are smooth surface seams.";
    select.addEventListener("change", () => {
      output.textContent = "";
    });
    button.addEventListener("click", async () => {
      const index = Number(select.value);
      button.disabled = true;
      select.disabled = true;
      output.textContent = "Measuring…";
      try {
        const result = await onMeasureEdge(index);
        output.textContent = `Edge ${index + 1}: ${result.length_mm} mm (exact); approximately ${result.length_approx_mm.toPrecision(8)} mm. Chord: ${result.chord_mm} mm. ${result.patch_seam ? "Smooth surface seam" : "Boundary between surfaces"}. Endpoints: (${result.endpoints_mm[0].join(", ")}) → (${result.endpoints_mm[1].join(", ")}) mm.`;
      } catch (error) {
        output.textContent = error.message;
      } finally {
        button.disabled = false;
        select.disabled = false;
      }
    });
    section.append(hint, select, button, output);
    container.append(section);
  }
  for (const [reference, surface] of Object.entries(info.surfaces)) {
    const details = document.createElement("details"),
      title = document.createElement("summary"),
      geometry = document.createElement("p"),
      id = document.createElement("p");
    title.textContent = label(reference);
    geometry.textContent =
      surface.kind === "conical_frustum"
        ? `Conical ${surface.inward ? "inner" : "outer"} wall · bottom radius ${surface.bottom_radius} mm · top radius ${surface.top_radius} mm · height ${surface.height} mm · axis (${surface.axis.join(", ")}). Axis origin (${surface.origin.join(", ")}) mm.`
        : surface.kind === "cylinder"
          ? `Cylinder · radius ${surface.radius} mm · axis (${surface.axis.join(", ")}) · ${surface.inward ? "inner" : "outer"} wall. Axis origin (${surface.origin.join(", ")}) mm.`
          : `Plane · normal (${surface.normal.join(", ")}); normal · position = ${surface.offset}.`;
    id.textContent = `Reference: ${reference}`;
    details.append(title, geometry, id);
    if (onSelect) {
      const select = document.createElement("button");
      select.type = "button";
      select.dataset.surface = reference;
      select.textContent = "Select surface";
      select.setAttribute("aria-label", `Select ${label(reference)}`);
      select.addEventListener("click", () => onSelect(reference));
      details.append(select);
    }
    container.append(details);
  }
}
