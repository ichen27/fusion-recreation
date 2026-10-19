(async () => {
  const { pickBody } = await import("/picking.mjs");
  const gl = document.querySelector("#viewport").getContext("webgl2");
  const program = gl.getParameter(gl.CURRENT_PROGRAM);
  const data = new Float32Array(
    gl.getBufferParameter(gl.ARRAY_BUFFER, gl.BUFFER_SIZE) / 4,
  );
  gl.getBufferSubData(gl.ARRAY_BUFFER, 0, data);
  const state = (await (await fetch("/api/model")).json()).result;
  let first = 0;
  const groups = state.bodies.map((body) => {
    const count = body.display_mesh
      ? body.display_mesh.triangles.length * 3
      : body.boundary.faces.reduce(
          (n, f) => n + (f.loops[0].length - 2) * 3,
          0,
        );
    const group = { feature_id: body.feature_id, first, count };
    first += count;
    return group;
  });
  const [yaw, pitch] = gl.getUniform(
    program,
    gl.getUniformLocation(program, "angles"),
  );
  const camera = {
    yaw,
    pitch,
    zoom: gl.getUniform(program, gl.getUniformLocation(program, "zoom")),
    aspect: gl.getUniform(program, gl.getUniformLocation(program, "aspect")),
  };
  const sample = (packed, bodyGroups, iterations) => {
    for (let i = 0; i < 5; i++) pickBody(packed, bodyGroups, camera, 0, 0);
    const times = [];
    for (let i = 0; i < iterations; i++) {
      const start = performance.now();
      pickBody(packed, bodyGroups, camera, 0, 0);
      times.push(performance.now() - start);
    }
    times.sort((a, b) => a - b);
    return {
      iterations,
      median_ms: times[Math.floor(times.length / 2)],
      p95_ms: times[Math.floor(times.length * 0.95)],
    };
  };
  // Synthetic worst-case overlap workload, independent of the native model limits.
  const repeated = new Float32Array(65536 * 18);
  const triangle = data.subarray(0, 18);
  for (let i = 0; i < 65536; i++) repeated.set(triangle, i * 18);
  const synthetic = Array.from({ length: 32 }, (_, i) => ({
    feature_id: `synthetic${i}`,
    first: i * 2048 * 3,
    count: 2048 * 3,
  }));
  const debug = gl.getExtension("WEBGL_debug_renderer_info");
  return {
    renderer: debug
      ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL)
      : gl.getParameter(gl.RENDERER),
    viewport: [gl.drawingBufferWidth, gl.drawingBufferHeight],
    actual: {
      triangles: first / 3,
      bodies: groups.length,
      ...sample(data, groups, 50),
    },
    synthetic: {
      triangles: 65536,
      bodies: 32,
      ...sample(repeated, synthetic, 20),
    },
    selections: window.__selectionEvidence,
  };
})();
