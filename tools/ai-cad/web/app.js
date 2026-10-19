import { installBooleanEditor } from "/boolean-editor.mjs";
import { booleanCandidates } from "/boolean-model.mjs";
import { previewJob } from "/preview-client.mjs";
import { installRotationEditor } from "/rotation-editor.mjs";
import { installTranslateEditor } from "/translate-editor.mjs";
import { pickBody } from "/picking.mjs";
import { installIntersectionEditor } from "/intersection-editor.mjs";
import { intersectionCandidates } from "/intersection-model.mjs";
import { installStockEditor } from "/stock-editor.mjs";
import { planeCandidate } from "/plane-model.mjs";
import { installPlaneEditor } from "/plane-editor.mjs";
import {
  packVertices,
  formatMeasurement,
  displayFrame,
  fittedZoom,
} from "/display-data.mjs";
import { installSketchEditor } from "/sketch-editor.mjs";
import { installHoleEditor } from "/hole-editor.mjs";
import { availableHoleInputs } from "/hole-model.mjs";
let sketches,
  holes,
  planes,
  stocks,
  intersections,
  translations,
  rotations,
  booleans;
const $ = (id) => document.getElementById(id);
let saved,
  preview,
  proposed,
  commitAction = "commit",
  editPending = false,
  busy = false;
const canvas = $("viewport");
const gl = canvas.getContext("webgl2", { antialias: true });
let yaw = -0.65,
  pitch = 0.65,
  zoom = 1,
  selectedBody = null,
  visibleBodies = [],
  bodyGroups = [],
  packedDisplay = new Float32Array(),
  triangles = [],
  lines = [],
  center = [0, 0, 0],
  extent = 100;
function shader(type, source) {
  const s = gl.createShader(type);
  gl.shaderSource(s, source);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS))
    throw Error(gl.getShaderInfoLog(s));
  return s;
}
let program,
  buffer,
  geometryDirty = true,
  contextLost = false;
function initializeGL() {
  program = gl.createProgram();
  gl.attachShader(
    program,
    shader(
      gl.VERTEX_SHADER,
      `#version 300 es
    in vec3 position; in vec3 color; out vec3 tint;
    uniform vec2 angles; uniform float zoom; uniform float aspect;
    void main(){ vec3 p=position*zoom;
      float c=cos(angles.x),s=sin(angles.x);p=vec3(c*p.x-s*p.y,s*p.x+c*p.y,p.z);
      c=cos(angles.y);s=sin(angles.y);p=vec3(p.x,-s*p.y+c*p.z,c*p.y+s*p.z);
      gl_Position=vec4(p.x/aspect,p.y,-p.z*0.2,1.0);tint=color; }`,
    ),
  );
  gl.attachShader(
    program,
    shader(
      gl.FRAGMENT_SHADER,
      `#version 300 es
    precision highp float; in vec3 tint; uniform float selected; out vec4 outputColor;
    void main(){outputColor=vec4(mix(tint,vec3(0.95,0.69,0.17),selected*0.6),1.0);}`,
    ),
  );
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS))
    throw Error(gl.getProgramInfoLog(program));
  buffer = gl.createBuffer();
  gl.useProgram(program);
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  for (const [name, offset] of [
    ["position", 0],
    ["color", 12],
  ]) {
    const location = gl.getAttribLocation(program, name);
    gl.enableVertexAttribArray(location);
    gl.vertexAttribPointer(location, 3, gl.FLOAT, false, 24, offset);
  }
  gl.enable(gl.DEPTH_TEST);
  geometryDirty = true;
}
if (gl) {
  initializeGL();
} else {
  $("status").textContent =
    "WebGL 2 is unavailable. Model editing remains available.";
}
const number = (s) => {
  const parts = s.split("/").map(Number);
  return parts.length === 2 ? parts[0] / parts[1] : parts[0];
};
function geometry(bodies, profiles) {
  triangles = [];
  lines = [];
  const all = [];
  bodyGroups = [];
  visibleBodies = bodies;
  if (!bodies.some((b) => b.feature_id === selectedBody)) selectedBody = null;
  for (const body of bodies) {
    const first = triangles.length / 6,
      lineFirst = lines.length / 6;
    const record = () =>
      bodyGroups.push({
        feature_id: body.feature_id,
        first,
        count: triangles.length / 6 - first,
        lineFirst,
        lineCount: lines.length / 6 - lineFirst,
      });
    if (body.analytic || body.components) {
      const mesh = body.display_mesh;
      if (!mesh) {
        continue;
      }
      const vertices = mesh.vertices;
      all.push(...vertices);
      for (const ids of mesh.triangles) {
        const [a, b, c] = ids.map((i) => vertices[i]);
        const u = b.map((v, i) => v - a[i]),
          v = c.map((x, i) => x - a[i]);
        const n = [
          u[1] * v[2] - u[2] * v[1],
          u[2] * v[0] - u[0] * v[2],
          u[0] * v[1] - u[1] * v[0],
        ];
        const shade =
          0.72 +
          (0.25 * (n[0] * 0.3 - n[1] * 0.4 + n[2] * 0.86)) / Math.hypot(...n);
        for (const id of ids)
          triangles.push(
            ...vertices[id],
            0.36 * shade,
            0.65 * shade,
            0.58 * shade,
          );
      }
      for (const edge of mesh.edges)
        for (const id of edge) lines.push(...vertices[id], 0.15, 0.31, 0.27);
      record();
      continue;
    }
    const b = body.boundary,
      vertices = b.vertices.map((p) => p.map(number));
    all.push(...vertices);
    for (const face of b.faces) {
      const ids = face.loops[0].map(
        (u) => b.edges[u.edge].vertices[u.forward ? 0 : 1],
      );
      const n = face.normal.map(number),
        length = Math.hypot(...n);
      const shade =
        0.72 + (0.25 * (n[0] * 0.3 + n[1] * -0.4 + n[2] * 0.86)) / length;
      const color = [0.36 * shade, 0.65 * shade, 0.58 * shade];
      for (let i = 1; i < ids.length - 1; i++)
        for (const id of [ids[0], ids[i], ids[i + 1]])
          triangles.push(...vertices[id], ...color);
    }
    for (const edge of b.edges)
      for (const id of edge.vertices)
        lines.push(...vertices[id], 0.15, 0.31, 0.27);
    record();
  }
  for (const profile of profiles) {
    const vertices = profile.vertices.map((v) => v.position.map(number));
    all.push(...vertices);
    for (let i = 0; i < vertices.length; i++)
      for (const p of [vertices[i], vertices[(i + 1) % vertices.length]])
        lines.push(...p, 0.85, 0.56, 0.18);
  }
  ({ center, extent } = displayFrame(all));
  geometryDirty = true;
  updateSelection();
  draw();
}
function draw() {
  if (!gl || contextLost) return;
  if (geometryDirty) {
    packedDisplay = packVertices(triangles, lines, center, extent);
    gl.bufferData(gl.ARRAY_BUFFER, packedDisplay, gl.STATIC_DRAW);
    geometryDirty = false;
  }
  const ratio = Math.min(devicePixelRatio, 2),
    w = Math.round(canvas.clientWidth * ratio),
    h = Math.round(canvas.clientHeight * ratio);
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  gl.viewport(0, 0, w, h);
  gl.clearColor(0, 0, 0, 0);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  gl.uniform2f(gl.getUniformLocation(program, "angles"), yaw, pitch);
  gl.uniform1f(gl.getUniformLocation(program, "zoom"), fittedZoom(zoom, w / h));
  gl.uniform1f(gl.getUniformLocation(program, "aspect"), w / h);
  gl.enable(gl.POLYGON_OFFSET_FILL);
  gl.polygonOffset(1, 1);
  const highlight = gl.getUniformLocation(program, "selected");
  for (const group of bodyGroups) {
    gl.uniform1f(highlight, group.feature_id === selectedBody ? 1 : 0);
    gl.drawArrays(gl.TRIANGLES, group.first, group.count);
  }
  gl.disable(gl.POLYGON_OFFSET_FILL);
  let bodyLineCount = 0;
  for (const group of bodyGroups) {
    gl.uniform1f(highlight, group.feature_id === selectedBody ? 1 : 0);
    gl.drawArrays(
      gl.LINES,
      triangles.length / 6 + group.lineFirst,
      group.lineCount,
    );
    bodyLineCount += group.lineCount;
  }
  gl.uniform1f(highlight, 0);
  gl.drawArrays(
    gl.LINES,
    triangles.length / 6 + bodyLineCount,
    lines.length / 6 - bodyLineCount,
  );
}
canvas.addEventListener("webglcontextlost", (event) => {
  event.preventDefault();
  contextLost = true;
  $("display-status").textContent =
    "Graphics context lost. Your saved model is intact; waiting for recovery.";
});
canvas.addEventListener("webglcontextrestored", () => {
  contextLost = false;
  initializeGL();
  draw();
  $("display-status").textContent = "";
});
let intentKey = null,
  intentPending = false;
function intentControls() {
  $("explain-selection").disabled =
    intentPending || busy || !!preview || editPending || !selectedBody;
  const key = saved && !preview ? `${saved.revision}:${selectedBody}` : null;
  if (intentKey !== key) {
    $("intent-info").replaceChildren();
    intentKey = key;
  }
}
$("explain-selection").addEventListener("click", async () => {
  const feature = selectedBody,
    revision = saved.revision,
    key = `${revision}:${feature}`;
  intentPending = true;
  intentControls();
  $("intent-info").textContent = "Reading controlling features and dimensions…";
  try {
    const reply = await (
      await fetch("/api/explain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_revision: revision,
          feature_id: feature,
        }),
      })
    ).json();
    if (intentKey !== key) return;
    if (reply.error) throw Error(`${reply.error.code}: ${reply.error.message}`);
    const info = reply.result,
      container = $("intent-info");
    container.replaceChildren();
    const source = document.createElement("p");
    source.textContent = `Source features: ${info.source_features.map((f) => f.id).join(", ")}.`;
    container.append(source);
    const note = document.createElement("p");
    note.textContent =
      "Potential dependency impact. Preview still validates the edit.";
    container.append(note);
    for (const [id, parameter] of Object.entries(info.parameters)) {
      const item = document.createElement("details"),
        title = document.createElement("summary"),
        description = document.createElement("p");
      const state = parameter.relation
        ? "derived"
        : parameter.fixed_mm !== null
          ? "fixed"
          : "editable";
      title.textContent = `${id}: ${parameter.value_mm} mm · ${state}`;
      description.textContent = [
        parameter.fixed_mm !== null ? `Fixed at ${parameter.fixed_mm} mm.` : "",
        parameter.relation
          ? `Driven by: ${parameter.driving_parameters.join(", ") || "constant relationship"}.`
          : "",
        `May affect solids: ${parameter.affected_bodies.join(", ") || "none"}.`,
        `Dependent features: ${parameter.affected_features.join(", ")}.`,
      ]
        .filter(Boolean)
        .join(" ");
      item.append(title, description);
      container.append(item);
    }
  } catch (error) {
    if (intentKey === key) $("intent-info").textContent = error.message;
  } finally {
    intentPending = false;
    intentControls();
  }
});
function updateSelection() {
  const body = visibleBodies.find((b) => b.feature_id === selectedBody);
  $("selection-info").textContent = body
    ? `${body.feature_id} · ${body.volume_mm3} mm³ (exact)`
    : "Click a solid or select it in the feature list.";
  $("clear-selection").disabled = !saved;
  intentControls();
  for (const button of document.querySelectorAll(".select-body")) {
    const active = button.dataset.body === selectedBody;
    button.setAttribute("aria-pressed", String(active));
    button.closest(".feature").classList.toggle("selected-feature", active);
  }
}
let selectionQueue = Promise.resolve(),
  selectionRequest = 0,
  selectionPending = false;
async function readSelectionContext() {
  if (!saved || preview || editPending || selectionPending || busy) return;
  const requested = selectionRequest;
  const reply = await (await fetch("/api/context")).json();
  if (
    requested !== selectionRequest ||
    selectionPending ||
    preview ||
    editPending ||
    busy
  )
    return;
  if (reply.error) {
    $("selection-context").textContent = reply.error.message;
    return;
  }
  const context = reply.result;
  if (context.revision !== saved.revision) return;
  const id = context.selected_body?.feature_id ?? null;
  const changed = selectedBody !== id;
  selectedBody = id;
  $("selection-context").textContent =
    context.selection_status === "current"
      ? `Shared with AI tools at revision ${context.revision}.`
      : context.selection_status === "stale"
        ? "The model changed. Reselect a saved solid to share its current geometry."
        : "No saved solid shared with AI tools.";
  updateSelection();
  if (changed) draw();
}
function shareSelection(id) {
  const request = ++selectionRequest,
    revision = saved.revision;
  selectionPending = true;
  $("selection-context").textContent = "Sharing saved selection…";
  selectionQueue = selectionQueue
    .catch(() => {})
    .then(async () => {
      try {
        const reply = await (
          await fetch("/api/selection", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              action: "select",
              expected_revision: revision,
              feature_id: id,
            }),
          })
        ).json();
        if (reply.error) throw Error(reply.error.message);
        if (request === selectionRequest)
          $("selection-context").textContent = id
            ? `Shared with AI tools at revision ${revision}.`
            : "No saved solid shared with AI tools.";
      } catch (error) {
        if (request === selectionRequest)
          $("selection-context").textContent =
            `Selection was not shared: ${error.message}`;
      } finally {
        if (request === selectionRequest) selectionPending = false;
      }
    });
}
function selectBody(id) {
  selectedBody = id;
  updateSelection();
  draw();
  if (saved && !preview && !editPending && !busy) shareSelection(id);
  else
    $("selection-context").textContent =
      "Preview selection is local. Select the saved result after committing.";
}
$("clear-selection").addEventListener("click", () => selectBody(null));
let pointer;
canvas.addEventListener("pointerdown", (e) => {
  if (e.button !== 0 || pointer) return;
  pointer = {
    id: e.pointerId,
    start: [e.clientX, e.clientY],
    last: [e.clientX, e.clientY],
    dragged: false,
  };
  canvas.setPointerCapture(e.pointerId);
});
canvas.addEventListener("pointermove", (e) => {
  if (!pointer || pointer.id !== e.pointerId) return;
  if (
    Math.hypot(e.clientX - pointer.start[0], e.clientY - pointer.start[1]) > 4
  )
    pointer.dragged = true;
  if (!pointer.dragged) return;
  yaw += (e.clientX - pointer.last[0]) * 0.008;
  pitch += (e.clientY - pointer.last[1]) * 0.008;
  pointer.last = [e.clientX, e.clientY];
  draw();
});
canvas.addEventListener("pointerup", (e) => {
  if (!pointer || pointer.id !== e.pointerId) return;
  if (!pointer.dragged && gl && !contextLost) {
    const rect = canvas.getBoundingClientRect(),
      aspect = canvas.width / canvas.height;
    selectBody(
      pickBody(
        packedDisplay,
        bodyGroups,
        { yaw, pitch, zoom: fittedZoom(zoom, aspect), aspect },
        (2 * (e.clientX - rect.left)) / rect.width - 1,
        1 - (2 * (e.clientY - rect.top)) / rect.height,
      ),
    );
  }
  pointer = null;
});
canvas.addEventListener("pointercancel", () => (pointer = null));
canvas.addEventListener("lostpointercapture", () => (pointer = null));
canvas.addEventListener(
  "wheel",
  (e) => {
    e.preventDefault();
    zoom = Math.min(4, Math.max(0.3, zoom * Math.exp(-e.deltaY * 0.001)));
    draw();
  },
  { passive: false },
);
$("fit-view").addEventListener("click", () => {
  zoom = 1;
  draw();
});
new ResizeObserver(draw).observe(canvas);
function controls() {
  intentControls();
  $("new-sketch").disabled = busy || !!preview || editPending || !saved;
  $("new-stock").disabled = busy || !!preview || editPending || !saved;
  $("new-boolean").disabled =
    busy ||
    !!preview ||
    editPending ||
    !saved ||
    booleanCandidates(saved).length < 2;
  $("new-intersection").disabled =
    busy ||
    !!preview ||
    editPending ||
    !saved ||
    intersectionCandidates(saved).length < 2;
  for (const button of document.querySelectorAll(
    ".edit-sketch, .edit-holes, .edit-plane, .edit-move, .edit-rotation, .edit-boolean",
  ))
    button.disabled = busy || !!preview || editPending;
  $("undo").disabled = busy || !!preview || !saved?.can_undo;
  $("redo").disabled = busy || !!preview || !saved?.can_redo;
  $("commit").disabled = busy;
  $("cancel").disabled = busy;
  for (const id of ["export-native", "import-native", "native-file"])
    $(id).disabled = busy || !!preview || editPending || !saved;
  $("export-stl").disabled =
    busy || !!preview || editPending || !saved?.bodies.length;
  $("dimensions").querySelector("button").disabled = busy || !!preview;
}
function render(state) {
  $("display-status").textContent = state.bodies
    .filter((b) => b.display_error)
    .map((b) => `${b.feature_id}: ${b.display_error.message}`)
    .join(" · ");
  const profiles = state.profiles ?? [];
  const extruded = new Set(
    state.model.features
      .filter((f) => f.kind === "extrude")
      .map((f) => f.profile),
  );
  const visibleProfiles = profiles.filter((p) => !extruded.has(p.feature_id));
  $("model-title").textContent = profiles.length
    ? "Profile model"
    : "Solid model";
  $("revision").textContent = `Revision ${state.revision} · Millimeters`;
  $("mode").textContent = preview ? "EDIT PREVIEW" : "SAVED MODEL";
  $("preview-actions").hidden = !preview;
  $("commit").textContent =
    commitAction === "import" ? "Replace model" : "Save edit";
  $("features").replaceChildren(
    ...state.model.features.map((f) => {
      const div = document.createElement("div");
      div.className = "feature";
      div.textContent = `${f.kind === "block" ? "◇" : "◩"}  ${f.id} · ${f.kind.replaceAll("_", " ")}`;
      if (state.bodies.some((b) => b.feature_id === f.id)) {
        const select = document.createElement("button");
        select.className = "select-body";
        select.dataset.body = f.id;
        select.textContent = "Select solid";
        select.setAttribute("aria-label", `Select solid ${f.id}`);
        select.addEventListener("click", () => selectBody(f.id));
        div.append(select);
      }
      if (["polygon_profile", "planar_profile"].includes(f.kind)) {
        const button = document.createElement("button");
        button.className = "edit-sketch";
        button.textContent = "Edit sketch";
        button.setAttribute("aria-label", `Edit sketch ${f.id}`);
        button.addEventListener("click", () => sketches.open(f.id));
        div.append(button);
      }
      if (
        ["through_holes", "blind_holes"].includes(f.kind) ||
        availableHoleInputs(state.model).some((e) => e.id === f.id)
      ) {
        const button = document.createElement("button");
        button.className = "edit-holes";
        button.textContent = ["through_holes", "blind_holes"].includes(f.kind)
          ? "Edit holes"
          : "Add holes";
        button.setAttribute("aria-label", `${button.textContent} ${f.id}`);
        button.addEventListener("click", () =>
          holes.open(
            !["through_holes", "blind_holes"].includes(f.kind) ? f.id : null,
            ["through_holes", "blind_holes"].includes(f.kind) ? f.id : null,
          ),
        );
        div.append(button);
      }
      if (
        f.kind === "plane_cut" ||
        state.bodies.some((b) => b.feature_id === f.id && planeCandidate(b))
      ) {
        const button = document.createElement("button");
        button.className = "edit-plane";
        button.textContent =
          f.kind === "plane_cut" ? "Edit plane" : "Cut with plane";
        button.setAttribute("aria-label", `${button.textContent} ${f.id}`);
        button.addEventListener("click", () =>
          planes.open(f.id, f.kind === "plane_cut" ? f.id : null),
        );
        div.append(button);
        if (
          f.kind === "plane_cut" &&
          state.bodies.some((b) => b.feature_id === f.id && planeCandidate(b))
        ) {
          const next = document.createElement("button");
          next.className = "edit-plane";
          next.textContent = "Add next plane cut";
          next.addEventListener("click", () => planes.open(f.id));
          div.append(next);
        }
      }
      if (
        f.kind === "translate" ||
        state.bodies.some((b) => b.feature_id === f.id && planeCandidate(b))
      ) {
        const move = document.createElement("button");
        move.className = "edit-move";
        move.textContent = f.kind === "translate" ? "Edit move" : "Move solid";
        move.setAttribute("aria-label", `${move.textContent} ${f.id}`);
        move.addEventListener("click", () =>
          translations.open(f.id, f.kind === "translate" ? f.id : null),
        );
        div.append(move);
      }
      if (
        f.kind === "rotate_quarter" ||
        state.bodies.some((b) => b.feature_id === f.id && planeCandidate(b))
      ) {
        const button = document.createElement("button");
        button.className = "edit-rotation";
        button.textContent =
          f.kind === "rotate_quarter" ? "Edit turn" : "Quarter-turn solid";
        button.setAttribute("aria-label", `${button.textContent} ${f.id}`);
        button.addEventListener("click", () =>
          rotations.open(f.id, f.kind === "rotate_quarter" ? f.id : null),
        );
        div.append(button);
      }
      if (f.kind === "boolean") {
        const button = document.createElement("button");
        button.className = "edit-boolean";
        button.textContent = `Edit ${f.operation}`;
        button.setAttribute("aria-label", `Edit Boolean ${f.id}`);
        button.addEventListener("click", () => booleans.open(f.id));
        div.append(button);
      }
      return div;
    }),
  );
  $("parameters").replaceChildren(
    ...Object.entries(state.model.parameters).map(([id, value]) => {
      const div = document.createElement("div");
      div.className = "field";
      const label = document.createElement("label");
      label.htmlFor = `p-${id}`;
      label.textContent = id.replaceAll("_", " ");
      const fixed = id in state.model.fixed;
      const relation = state.model.relations?.[id];
      if (fixed) {
        const note = document.createElement("small");
        note.textContent = relation ? "FIXED · DERIVED" : "FIXED";
        label.append(note);
      }
      if (relation && !fixed) {
        const note = document.createElement("small");
        note.textContent = "DERIVED";
        label.append(note);
      }
      const input = document.createElement("input");
      input.id = `p-${id}`;
      input.name = id;
      input.value = value;
      input.disabled = fixed || !!relation || !!preview;
      input.autocomplete = "off";
      input.addEventListener("input", () => {
        editPending = true;
        controls();
      });
      div.append(label, input);
      if (relation) {
        const formula = document.createElement("small");
        formula.className = "relationship";
        formula.textContent = `${id} = ${relation.offset_mm} + ${
          Object.entries(relation.terms)
            .map(([source, coefficient]) => `(${coefficient} × ${source})`)
            .join(" + ") || "0"
        }`;
        div.append(formula);
      }
      return div;
    }),
  );
  $("export-stl").textContent =
    state.bodies.length > 1
      ? "Download saved STLs (ZIP)"
      : "Download saved STL";
  $("volume").textContent = state.bodies.length
    ? state.bodies
        .map(
          (b) =>
            `${formatMeasurement(b.volume_approx_mm3 ?? number(b.volume_mm3))} mm³`,
        )
        .join(" + ")
    : profiles.length
      ? "Profile only · no solid"
      : "Empty document";
  $("volume").title = state.bodies
    .map((b) => `${b.feature_id}: ${b.volume_mm3} mm³ (exact)`)
    .join("\n");
  $("profile-area").textContent = profiles
    .map((p) => `${p.feature_id}: ${formatMeasurement(number(p.area_mm2))} mm²`)
    .join(" · ");
  $("profile-area").title = profiles
    .map((p) => `${p.feature_id}: ${p.area_mm2} mm² (exact)`)
    .join("\n");
  geometry(state.bodies, visibleProfiles);
  controls();
}
async function requestJSON(path, command) {
  const response = await fetch(
    path,
    command === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(command),
        },
  );
  const data = await response.json();
  if (data.error) throw Error(`${data.error.code}: ${data.error.message}`);
  return data.result;
}
let activePreviewJob = null,
  previewCancellationRequested = false;
$("cancel-preview-job").addEventListener("click", async () => {
  const id = activePreviewJob;
  if (!id) return;
  previewCancellationRequested = true;
  $("cancel-preview-job").disabled = true;
  $("compute-status").textContent = "Cancelling calculation…";
  try {
    await requestJSON("/api/preview-jobs", { action: "cancel", job_id: id });
  } catch (error) {
    if (activePreviewJob === id) {
      $("compute-status").textContent = error.message;
      $("cancel-preview-job").disabled = false;
    }
  }
});
$("compute-dialog").addEventListener("cancel", (event) => {
  event.preventDefault();
  if (!$("cancel-preview-job").disabled) $("cancel-preview-job").click();
});
async function call(command) {
  if (command.action !== "preview") return requestJSON("/api/command", command);
  const dialog = $("compute-dialog");
  previewCancellationRequested = false;
  $("compute-status").textContent = "Preparing the saved model…";
  $("cancel-preview-job").disabled = true;
  dialog.showModal();
  try {
    const result = await previewJob(command, {
      request: requestJSON,
      isCancelled: () => previewCancellationRequested,
      pause: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
      onStatus: (job) => {
        activePreviewJob = job.job_id;
        $("cancel-preview-job").disabled =
          previewCancellationRequested ||
          !["queued", "running"].includes(job.status);
        $("compute-status").textContent =
          {
            queued: "Waiting for the current calculation…",
            running: "Checking geometry and preparing the preview…",
            cancelling: "Cancelling calculation…",
          }[job.status] ?? "Calculation finished.";
      },
    });
    return result;
  } finally {
    activePreviewJob = null;
    dialog.close();
  }
}
async function refresh(force = false) {
  if (busy) return;
  try {
    const data = await (await fetch("/api/model")).json();
    if (data.error) throw Error(data.error.message);
    if (busy || (saved && data.result.revision < saved.revision)) return;
    if ((preview || editPending) && !force) {
      if (data.result.revision !== saved.revision)
        $("status").textContent =
          "The saved model changed elsewhere. Your edit remains visible; refresh to discard it and replan.";
      return;
    }
    if (force || !saved || data.result.revision !== saved.revision) {
      saved = data.result;
      preview = null;
      editPending = false;
      render(saved);
      $("status").textContent =
        "Saved model loaded. All geometric checks passed.";
    }
    await readSelectionContext();
  } catch (e) {
    $("status").textContent = e.message;
  }
}
async function task(fn) {
  busy = true;
  controls();
  try {
    await fn();
  } catch (e) {
    $("status").textContent = e.message;
  } finally {
    busy = false;
    controls();
  }
}
$("dimensions").addEventListener("submit", (e) => {
  e.preventDefault();
  task(async () => {
    if (!saved) return;
    const operations = [];
    for (const input of $("parameters").querySelectorAll("input"))
      if (!input.disabled && input.value !== saved.model.parameters[input.name])
        operations.push({
          op: "set_parameter",
          id: input.name,
          mm: input.value,
        });
    if (!operations.length)
      throw Error(
        "Change an unlocked dimension first. Use integers or fractions, such as 25/2.",
      );
    const changed = new Set(operations.map((o) => o.id));
    proposed = {
      expected_revision: saved.revision,
      operations,
      preserve: Object.keys(saved.model.parameters).filter(
        (id) => !changed.has(id) && !(id in (saved.model.relations ?? {})),
      ),
    };
    preview = await call({ action: "preview", ...proposed });
    commitAction = "commit";
    render(preview);
    $("status").textContent =
      "Preview valid. Fixed dimensions and preserved parameters are unchanged.";
  });
});
$("commit").addEventListener("click", () =>
  task(async () => {
    // Retain the same transaction ID for an uncertain acknowledgement and retry.
    proposed.transaction_id ??= crypto.randomUUID();
    saved = await call({ action: commitAction, ...proposed });
    preview = null;
    editPending = false;
    render(saved);
    $("status").textContent = "Edit saved. Undo is available.";
  }),
);
$("cancel").addEventListener("click", () => {
  preview = null;
  editPending = false;
  render(saved);
  $("status").textContent = "Preview discarded.";
});
for (const action of ["undo", "redo"])
  $(action).addEventListener("click", () =>
    task(async () => {
      saved = await call({
        action,
        expected_revision: saved.revision,
        transaction_id: crypto.randomUUID(),
      });
      editPending = false;
      render(saved);
      $("status").textContent =
        `${action === "undo" ? "Undo" : "Redo"} saved as revision ${saved.revision}.`;
    }),
  );
$("refresh").addEventListener("click", () => refresh(true));
const editorCallbacks = (name) => ({
  getState: () => saved,
  onOpen: () => {
    editPending = true;
    controls();
  },
  onClose: () => {
    editPending = false;
    controls();
  },
  onPreview: async (proposal) => {
    const result = await call({ action: "preview", ...proposal });
    proposed = proposal;
    commitAction = "commit";
    preview = result;
    render(preview);
    $("status").textContent =
      `${name} preview valid. Save edit to commit the model.`;
  },
});
sketches = installSketchEditor(editorCallbacks("Sketch"));
holes = installHoleEditor(editorCallbacks("Hole"));
planes = installPlaneEditor(editorCallbacks("Plane cut"));
stocks = installStockEditor(editorCallbacks("Stock"));
translations = installTranslateEditor(editorCallbacks("Move"));
rotations = installRotationEditor(editorCallbacks("Rotation"));
intersections = installIntersectionEditor(editorCallbacks("Intersection"));
$("new-intersection").addEventListener("click", () => intersections.open());
$("new-stock").addEventListener("click", () => stocks.open());
$("new-sketch").addEventListener("click", () => sketches.open());
await refresh();
setInterval(() => refresh(), 2000);

$("export-stl").addEventListener("click", async () => {
  if (busy || preview || editPending || !saved?.bodies.length) return;
  busy = true;
  controls();
  try {
    const revision = saved.revision;
    const bundled = saved.bodies.length > 1;
    const query = new URLSearchParams({
      revision,
      segments: 128,
      ...(bundled ? {} : { body: saved.bodies[0].feature_id }),
    });
    const response = await fetch(
      `/api/export.${bundled ? "zip" : "stl"}?${query}`,
    );
    if (!response.ok) throw Error((await response.json()).error.message);
    const url = URL.createObjectURL(await response.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = bundled
      ? `cad-r${revision}.zip`
      : `${saved.bodies[0].feature_id}-r${revision}.stl`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    $("status").textContent =
      `Exported saved revision ${revision}. ${bundled ? "ZIP contains all bodies and a units/precision manifest. " : ""}STL uses millimeters and 128 segments per circle.`;
  } catch (error) {
    $("status").textContent = error.message;
  } finally {
    busy = false;
    controls();
  }
});

$("export-native").addEventListener("click", () =>
  task(async () => {
    const revision = saved.revision;
    const response = await fetch(`/api/export.cad?revision=${revision}`);
    if (!response.ok) throw Error((await response.json()).error.message);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `cad-r${revision}.cad.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    $("status").textContent =
      `Downloaded editable revision ${revision}, including its undo history.`;
  }),
);
$("import-native").addEventListener("click", () => $("native-file").click());
$("native-file").addEventListener("change", () => {
  const file = $("native-file").files[0];
  $("native-file").value = "";
  if (!file || busy || preview || editPending || !saved) return;
  task(async () => {
    const revision = saved.revision;
    if (file.size > 16 * 1024 * 1024)
      throw Error("Native files must be at most 16 MiB.");
    const document = JSON.parse(await file.text());
    const proposal = { expected_revision: revision, document };
    const result = await call({ action: "preview_import", ...proposal });
    proposed = proposal;
    commitAction = "import";
    preview = result;
    render(preview);
    $("status").textContent =
      `${file.name}: validated import preview. Replace model saves this model as one undoable edit. This workspace keeps its history; source history is not copied.`;
  });
});

booleans = installBooleanEditor(editorCallbacks("Boolean"));
$("new-boolean").addEventListener("click", () => booleans.open());
