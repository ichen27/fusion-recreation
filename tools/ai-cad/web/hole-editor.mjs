import {
  draftHoles,
  addHole,
  removeHole,
  setHoleValue,
  setHoleDepth,
  setIndividualHoleDepth,
  setCounterboreRadius,
  holeProposal,
  editable,
} from "./hole-model.mjs";
const $ = (id) => document.getElementById(id);
const number = (s) => {
  const p = s.split("/").map(Number);
  return p.length === 2 ? p[0] / p[1] : p[0];
};
const element = (name, attrs) => {
  const e = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
};
export function installHoleEditor({ getState, onOpen, onClose, onPreview }) {
  const dialog = $("hole-dialog"),
    svg = $("hole-canvas");
  let state,
    draft,
    pending = false,
    dragging = null;
  const message = (error) => {
    $("hole-feedback").textContent = error.message ?? error;
  };
  function outline() {
    if (draft.profile.kind === "circle") {
      const x = number(draft.values[draft.profile.x]),
        y = -number(draft.values[draft.profile.y]),
        r = number(draft.values[draft.profile.radius]);
      return [
        [x - r, y - r],
        [x + r, y - r],
        [x + r, y + r],
        [x - r, y + r],
      ];
    }
    return draft.profile.vertices.map((v) => [
      number(draft.values[v.x]),
      -number(draft.values[v.y]),
    ]);
  }
  function render() {
    const points = outline();
    const shapes = [];
    if (points.every((p) => p.every(Number.isFinite)))
      shapes.push(
        draft.profile.kind === "circle"
          ? element("circle", {
              cx: number(draft.values[draft.profile.x]),
              cy: -number(draft.values[draft.profile.y]),
              r: number(draft.values[draft.profile.radius]),
              class: "sketch-outline",
            })
          : element("polygon", {
              points: points.map((p) => p.join(",")).join(" "),
              class: "sketch-outline",
            }),
      );
    draft.holes.forEach((hole, index) => {
      const x = number(draft.values[hole.x]),
        y = -number(draft.values[hole.y]),
        r = number(draft.values[hole.radius]);
      if (![x, y, r].every(Number.isFinite) || r <= 0) return;
      shapes.push(
        element("circle", {
          cx: x,
          cy: y,
          r,
          "data-index": index,
          class: "hole-circle",
        }),
      );
      if (["counterbore_holes", "countersink_holes"].includes(draft.kind)) {
        const bore = number(draft.values[draft.boreRadius]);
        if (Number.isFinite(bore) && bore > 0)
          shapes.push(
            element("circle", {
              cx: x,
              cy: y,
              r: bore,
              "data-index": index,
              class: "hole-circle hole-recess",
            }),
          );
      }
      shapes.push(
        element("circle", {
          cx: x,
          cy: y,
          r: 1,
          "data-index": index,
          class: "hole-center",
        }),
      );
    });
    $("hole-shapes").replaceChildren(...shapes);
    $("hole-coordinates").replaceChildren(
      ...draft.holes.map((hole, index) => {
        const row = document.createElement("fieldset");
        row.className = "hole-coordinate";
        const legend = document.createElement("legend");
        legend.textContent = hole.id;
        row.append(legend);
        for (const axis of ["x", "y", "radius"]) {
          const label = document.createElement("label");
          label.textContent = axis === "radius" ? "Radius" : axis.toUpperCase();
          const input = document.createElement("input");
          input.value = draft.values[hole[axis]];
          input.setAttribute("aria-label", `${hole.id} ${axis}`);
          input.disabled = pending || !editable(draft, hole[axis]);
          input.addEventListener("change", () => {
            try {
              setHoleValue(draft, index, axis, input.value);
              render();
              message(
                "Draft changed. Preview checks the complete model and updates dependent dimensions.",
              );
            } catch (error) {
              message(error);
            }
          });
          label.append(input);
          row.append(label);
        }
        if (draft.kind === "blind_holes") {
          const label = document.createElement("label");
          label.className = "hole-depth-label";
          label.textContent = "Depth (blank uses group)";
          const input = document.createElement("input");
          const ref = draft.depthOverrides[hole.id];
          input.value = ref ? draft.values[ref] : "";
          input.placeholder = draft.values[draft.depth];
          input.setAttribute("aria-label", `${hole.id} depth`);
          input.disabled = pending || (!!ref && !editable(draft, ref));
          input.addEventListener("change", () => {
            try {
              setIndividualHoleDepth(draft, index, input.value);
              render();
              message("Depth changed. Preview checks the remaining floor.");
            } catch (error) {
              message(error);
            }
          });
          label.append(input);
          row.append(label);
          if (ref) {
            const reset = document.createElement("button");
            reset.type = "button";
            reset.textContent = "Use group depth";
            reset.setAttribute("aria-label", `Use group depth for ${hole.id}`);
            reset.disabled = pending;
            reset.addEventListener("click", () => {
              setIndividualHoleDepth(draft, index, "");
              render();
              message(
                "Hole uses group depth. Its former parameter is retained.",
              );
            });
            row.append(reset);
          }
        }
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "Remove";
        remove.setAttribute("aria-label", `Remove hole ${hole.id}`);
        remove.disabled = pending;
        remove.addEventListener("click", () => {
          removeHole(draft, index);
          render();
          message(
            "Hole removed from draft. Preview to validate. Unused parameters are retained.",
          );
        });
        row.append(remove);
        return row;
      }),
    );
    $("hole-count").textContent =
      `${draft.holes.length} ${draft.kind === "blind_holes" ? "blind" : draft.kind === "counterbore_holes" ? "counterbored" : draft.kind === "countersink_holes" ? "countersunk" : "through"} holes · millimeters`;
    $("hole-remove").disabled = pending || !draft.holes.length;
    $("hole-add").disabled = pending || draft.holes.length >= 16;
    $("hole-kind").value = draft.kind;
    $("hole-kind").disabled = pending || !!draft.featureId;
    $("hole-depth-row").hidden = ![
      "blind_holes",
      "counterbore_holes",
      "countersink_holes",
    ].includes(draft.kind);
    $("hole-bore-radius-row").hidden = ![
      "counterbore_holes",
      "countersink_holes",
    ].includes(draft.kind);
    $("hole-bore-radius").value = draft.values[draft.boreRadius];
    $("hole-bore-radius").disabled =
      pending || !editable(draft, draft.boreRadius);
    $("hole-depth").value = draft.values[draft.depth];
    $("hole-depth").disabled = pending || !editable(draft, draft.depth);
    $("hole-radius-row").hidden = false;
    $("hole-radius").disabled = pending;
    $("hole-preview").disabled = pending;
    $("hole-preview").textContent =
      draft.featureId && !draft.holes.length
        ? "Preview group removal"
        : "Preview holes";
    $("hole-close").disabled = pending;
  }
  function fit() {
    const points = outline();
    if (!points.every((p) => p.every(Number.isFinite))) return;
    const min = [0, 1].map((i) => Math.min(...points.map((p) => p[i]))),
      max = [0, 1].map((i) => Math.max(...points.map((p) => p[i])));
    const w = Math.max(20, max[0] - min[0]),
      h = Math.max(20, max[1] - min[1]),
      pad = Math.max(w, h) * 0.15;
    svg.setAttribute(
      "viewBox",
      `${min[0] - pad} ${min[1] - pad} ${w + 2 * pad} ${h + 2 * pad}`,
    );
  }
  function close() {
    if (pending) return;
    dragging = null;
    dialog.close();
    onClose();
  }
  $("hole-close").addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  $("hole-kind").addEventListener("change", () => {
    if (draft.featureId || pending) return;
    draft.kind = $("hole-kind").value;
    render();
  });
  $("hole-depth").addEventListener("change", () => {
    try {
      setHoleDepth(draft, $("hole-depth").value);
      render();
    } catch (error) {
      message(error);
    }
  });
  $("hole-bore-radius").addEventListener("change", () => {
    try {
      setCounterboreRadius(draft, $("hole-bore-radius").value);
      render();
    } catch (error) {
      message(error);
    }
  });
  $("hole-fit").addEventListener("click", fit);
  $("hole-remove").addEventListener("click", () => {
    if (draft.holes.length) removeHole(draft, draft.holes.length - 1);
    render();
  });
  $("hole-add").addEventListener("click", () => {
    try {
      addHole(draft, 0, 0, $("hole-radius").value);
      render();
      message("Set the new hole center inside the outline before previewing.");
    } catch (error) {
      message(error);
    }
  });
  const position = (event) => {
    const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(
      svg.getScreenCTM().inverse(),
    );
    return [Math.round(p.x), Math.round(-p.y)];
  };
  svg.addEventListener("pointerdown", (event) => {
    if (pending || event.button !== 0) return;
    try {
      const target = event.target.closest("[data-index]");
      if (target) dragging = Number(target.dataset.index);
      else {
        addHole(draft, ...position(event), $("hole-radius").value);
        dragging = draft.holes.length - 1;
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
    if (pending || dragging === null) return;
    const [x, y] = position(event),
      hole = draft.holes[dragging];
    for (const [axis, value] of [
      ["x", x],
      ["y", y],
    ])
      if (editable(draft, hole[axis]))
        setHoleValue(draft, dragging, axis, value);
    render();
    message(
      "Dragging snaps to 1 mm. Exact coordinate/radius fields accept integers and fractions.",
    );
  });
  for (const event of ["pointerup", "pointercancel"])
    svg.addEventListener(event, () => {
      dragging = null;
    });
  $("hole-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (pending) return;
    try {
      const proposal = holeProposal(state, draft);
      pending = true;
      render();
      message("Checking circle containment, separation and model constraints…");
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
    open(input = null, featureId = null) {
      state = structuredClone(getState());
      draft = draftHoles(state.model, input, featureId);
      dragging = null;
      $("hole-title").textContent = featureId
        ? `Edit ${featureId}`
        : `Holes in ${input}`;
      $("hole-radius").value = "3";
      message(
        featureId
          ? "Click inside to add, drag to move, or remove a hole. Shared references move together; fixed/derived fields stay locked. Emptying the group previews its removal."
          : "Click inside the outline to place hole centers. Drag to move; use the fields for exact coordinates and radii.",
      );
      render();
      fit();
      onOpen();
      dialog.showModal();
    },
  };
}
