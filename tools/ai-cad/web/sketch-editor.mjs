import { dimensionNumber as number } from "./dimension-input.mjs";
import {
  draftSketch,
  nextSketchPrefix,
  editable,
  addPoint,
  removeLastPoint,
  setCoordinate,
  sketchProposal,
  alignEdge,
  clearSketchRelation,
  draftRelation,
} from "./sketch-model.mjs";
const $ = (id) => document.getElementById(id);
const svgElement = (name, attrs) => {
  const e = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
};
export function installSketchEditor({ getState, onOpen, onClose, onPreview }) {
  const dialog = $("sketch-dialog"),
    svg = $("sketch-canvas");
  let draft,
    state,
    dragging = null,
    pending = false,
    relationshipsOpen = false;
  function message(error) {
    $("sketch-feedback").textContent = error.message ?? error;
  }
  function render() {
    const points = draft.vertices.map((v) => [
      number(draft.values[v.x]),
      number(draft.values[v.y]),
    ]);
    const finite = points.every((p) => p.every(Number.isFinite));
    const shapes = [];
    if (finite && points.length) {
      shapes.push(
        svgElement("polygon", {
          points: points.map((p) => `${p[0]},${-p[1]}`).join(" "),
          class: "sketch-outline",
        }),
      );
      points.forEach(([x, y], i) =>
        shapes.push(
          svgElement("circle", {
            cx: x,
            cy: -y,
            r: 2,
            "data-index": i,
            class: "sketch-point",
          }),
        ),
      );
    }
    $("sketch-shapes").replaceChildren(...shapes);
    $("sketch-count").textContent = `${points.length} points · millimeters`;
    $("sketch-coordinates").replaceChildren(
      ...draft.vertices.map((vertex, index) => {
        const row = document.createElement("div");
        row.className = "sketch-coordinate";
        const title = document.createElement("span");
        title.textContent = vertex.id;
        row.append(title);
        for (const axis of ["x", "y"]) {
          const label = document.createElement("label");
          label.textContent = axis.toUpperCase();
          const input = document.createElement("input");
          input.value = draft.values[vertex[axis]];
          input.setAttribute(
            "aria-label",
            `${vertex.id} ${axis.toUpperCase()}`,
          );
          input.disabled = !editable(draft, vertex[axis]) || pending;
          input.addEventListener("change", () => {
            try {
              setCoordinate(draft, index, axis, input.value);
              render();
              message(
                "Draft changed. Preview to validate geometry and update derived coordinates.",
              );
            } catch (error) {
              message(error);
            }
          });
          label.append(input);
          row.append(label);
        }
        return row;
      }),
    );
    if (draft.vertices.length >= 3) {
      const details = document.createElement("details");
      details.className = "sketch-relationships";
      details.open = relationshipsOpen;
      details.addEventListener("toggle", () => {
        relationshipsOpen = details.open;
      });
      const summary = document.createElement("summary");
      summary.textContent = "Edge relationships";
      details.append(summary);
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent =
        "Horizontal links the end Y to the start Y; vertical links end X to start X. Linked coordinates update at preview. These are directed relationships, not a general sketch solver.";
      details.append(hint);
      draft.vertices.forEach((start, index) => {
        const end = draft.vertices[(index + 1) % draft.vertices.length];
        const row = document.createElement("div");
        row.className = "edge-relationship";
        const name = document.createElement("strong");
        name.textContent = `${start.id} → ${end.id}`;
        row.append(name);
        for (const orientation of ["horizontal", "vertical"]) {
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = orientation;
          button.setAttribute(
            "aria-label",
            `${orientation} edge ${start.id} to ${end.id}`,
          );
          button.disabled = pending;
          button.addEventListener("click", () => {
            try {
              const changed = alignEdge(draft, index, orientation);
              render();
              message(
                changed
                  ? "Relationship added to draft. Preview to rebuild coordinates and dependent solids."
                  : "These coordinates already share that relationship.",
              );
            } catch (error) {
              message(error);
            }
          });
          row.append(button);
        }
        for (const axis of ["x", "y"]) {
          const target = end[axis],
            rule = draftRelation(draft, target);
          if (!rule) continue;
          const label = document.createElement("small");
          label.textContent = `${target} = ${rule.offset_mm} + ${
            Object.entries(rule.terms)
              .map(([source, c]) => `(${c} × ${source})`)
              .join(" + ") || "0"
          }`;
          const clear = document.createElement("button");
          clear.type = "button";
          clear.textContent = `Clear ${axis.toUpperCase()} link`;
          clear.setAttribute("aria-label", `Clear relationship ${target}`);
          clear.disabled = pending;
          clear.addEventListener("click", () => {
            try {
              clearSketchRelation(draft, target);
              render();
              message(
                "Relationship removed from draft. Preview to apply; the current coordinate value is retained.",
              );
            } catch (error) {
              message(error);
            }
          });
          row.append(label, clear);
        }
        details.append(row);
      });
      $("sketch-coordinates").append(details);
    }
    $("sketch-remove").disabled =
      !!draft.featureId || !points.length || pending;
    $("sketch-rectangle").disabled = !!draft.featureId || pending;
    $("sketch-preview").disabled = pending;
    $("sketch-close").disabled = pending;
    $("sketch-profile-only-row").hidden = !!draft.featureId;
    $("sketch-profile-only").disabled = pending;
    $("sketch-height-row").hidden = !!draft.featureId || draft.profileOnly;
    $("sketch-preview").textContent = draft.profileOnly
      ? "Preview sketch"
      : "Preview solid";
    $("sketch-height").disabled = pending;
  }
  function fit() {
    const points = draft.vertices.map((v) => [
      number(draft.values[v.x]),
      -number(draft.values[v.y]),
    ]);
    if (!points.length || !points.every((p) => p.every(Number.isFinite)))
      return;
    const min = [0, 1].map((i) => Math.min(...points.map((p) => p[i]))),
      max = [0, 1].map((i) => Math.max(...points.map((p) => p[i])));
    const width = Math.max(20, max[0] - min[0]),
      height = Math.max(20, max[1] - min[1]);
    const pad = Math.max(width, height) * 0.2;
    svg.setAttribute(
      "viewBox",
      `${min[0] - pad} ${min[1] - pad} ${width + 2 * pad} ${height + 2 * pad}`,
    );
  }
  function close() {
    if (pending) return;
    dialog.close();
    onClose();
  }
  $("sketch-profile-only").addEventListener("change", () => {
    draft.profileOnly = $("sketch-profile-only").checked;
    render();
  });
  $("sketch-close").addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  $("sketch-fit").addEventListener("click", fit);
  $("sketch-remove").addEventListener("click", () => {
    removeLastPoint(draft);
    render();
  });
  $("sketch-rectangle").addEventListener("click", () => {
    draft.vertices = [];
    draft.relationEdits = {};
    for (const [x, y] of [
      [0, 0],
      [100, 0],
      [100, 60],
      [0, 60],
    ])
      addPoint(draft, x, y);
    render();
    fit();
  });
  function position(event) {
    const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(
      svg.getScreenCTM().inverse(),
    );
    return [Math.round(p.x), Math.round(-p.y)];
  }
  svg.addEventListener("pointerdown", (event) => {
    if (pending || event.button !== 0) return;
    try {
      const target = event.target.closest("[data-index]");
      if (target) dragging = Number(target.dataset.index);
      else if (!draft.featureId) {
        addPoint(draft, ...position(event));
        dragging = draft.vertices.length - 1;
        render();
      }
      if (dragging !== null) {
        svg.setPointerCapture(event.pointerId);
        event.preventDefault();
      }
    } catch (error) {
      message(error);
    }
  });
  svg.addEventListener("pointermove", (event) => {
    if (dragging === null || pending) return;
    const [x, y] = position(event),
      vertex = draft.vertices[dragging];
    for (const [axis, value] of [
      ["x", x],
      ["y", y],
    ])
      if (editable(draft, vertex[axis]))
        setCoordinate(draft, dragging, axis, value);
    render();
    message(
      "Draft changed. Dragging snaps to 1 mm; coordinate fields accept decimals, fractions and units (mm, cm, m, in, ft).",
    );
  });
  for (const event of ["pointerup", "pointercancel"])
    svg.addEventListener(event, () => {
      dragging = null;
    });
  $("sketch-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (pending) return;
    try {
      draft.height = $("sketch-height").value;
      const proposal = sketchProposal(state, draft);
      pending = true;
      render();
      message("Validating profile and dependent solids…");
      await onPreview(proposal);
      pending = false;
      dialog.close();
      onClose();
    } catch (error) {
      pending = false;
      render();
      message(error);
    }
  });
  return {
    isOpen: () => dialog.open,
    open(featureId = null) {
      state = structuredClone(getState());
      draft = draftSketch(
        state.model,
        nextSketchPrefix(state.model),
        featureId,
      );
      $("sketch-title").textContent = featureId
        ? `Edit ${featureId}`
        : "Draw a planar profile";
      $("sketch-height").value = "6";
      $("sketch-profile-only").checked = false;
      svg.setAttribute("viewBox", "-20 -140 240 160");
      message(
        featureId
          ? "Shared parameters move together. Fixed/derived coordinates stay locked. Derived coordinates update on preview. Older polygon_profile features still require convexity."
          : "Click around a closed outline, including inward corners. Drag points or type exact coordinates.",
      );
      render();
      if (featureId) fit();
      onOpen();
      dialog.showModal();
    },
  };
}
