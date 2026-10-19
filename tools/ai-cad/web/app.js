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
let sketches, holes, planes, stocks, intersections;
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
    precision highp float; in vec3 tint; out vec4 outputColor;
    void main(){outputColor=vec4(tint,1.0);}`,
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
  for (const body of bodies) {
    if (body.analytic) {
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
  draw();
}
function draw() {
  if (!gl || contextLost) return;
  if (geometryDirty) {
    const vertices = packVertices(triangles, lines, center, extent);
    gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);
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
  gl.drawArrays(gl.TRIANGLES, 0, triangles.length / 6);
  gl.disable(gl.POLYGON_OFFSET_FILL);
  gl.drawArrays(gl.LINES, triangles.length / 6, lines.length / 6);
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
let pointer;
canvas.addEventListener("pointerdown", (e) => {
  pointer = [e.clientX, e.clientY];
  canvas.setPointerCapture(e.pointerId);
});
canvas.addEventListener("pointermove", (e) => {
  if (!pointer) return;
  yaw += (e.clientX - pointer[0]) * 0.008;
  pitch += (e.clientY - pointer[1]) * 0.008;
  pointer = [e.clientX, e.clientY];
  draw();
});
canvas.addEventListener("pointerup", () => (pointer = null));
canvas.addEventListener("pointercancel", () => (pointer = null));
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
  $("new-sketch").disabled = busy || !!preview || editPending || !saved;
  $("new-stock").disabled = busy || !!preview || editPending || !saved;
  $("new-intersection").disabled =
    busy ||
    !!preview ||
    editPending ||
    !saved ||
    intersectionCandidates(saved).length < 2;
  for (const button of document.querySelectorAll(
    ".edit-sketch, .edit-holes, .edit-plane",
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
async function call(command) {
  const response = await fetch("/api/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(command),
  });
  const data = await response.json();
  if (data.error) throw Error(`${data.error.code}: ${data.error.message}`);
  return data.result;
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
