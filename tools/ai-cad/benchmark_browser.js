// Run with agent-browser eval --stdin on the loaded viewer. Synthetic orbit only.
(async () => {
  const canvas = document.getElementById("viewport");
  const gl = canvas.getContext("webgl2");
  if (!gl) return { error: "WebGL 2 unavailable" };
  const info = gl.getExtension("WEBGL_debug_renderer_info");
  const timer = gl.getExtension("EXT_disjoint_timer_query_webgl2");
  const prototype = Object.getPrototypeOf(gl);
  const originalUpload = prototype.bufferData;
  const originalCapture = canvas.setPointerCapture;
  let uploads = 0,
    bytes = 0;
  const cpu = [],
    intervals = [],
    queries = [],
    gpu = [];
  prototype.bufferData = function (...args) {
    if (this === gl) {
      uploads++;
      bytes += args[1]?.byteLength ?? 0;
    }
    return originalUpload.apply(this, args);
  };
  canvas.setPointerCapture = () => {};
  const median = (values) =>
    values.length
      ? [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)]
      : null;
  let last;
  try {
    canvas.dispatchEvent(
      new PointerEvent("pointerdown", { clientX: 400, clientY: 400 }),
    );
    for (let i = 0; i < 60; i++) {
      const time = await new Promise((resolve) =>
        requestAnimationFrame(resolve),
      );
      if (last !== undefined) intervals.push(time - last);
      last = time;
      const query = timer ? gl.createQuery() : null;
      if (query) gl.beginQuery(timer.TIME_ELAPSED_EXT, query);
      const start = performance.now();
      canvas.dispatchEvent(
        new PointerEvent("pointermove", {
          clientX: 400 + i,
          clientY: 400 + i / 4,
        }),
      );
      cpu.push(performance.now() - start);
      if (query) {
        gl.endQuery(timer.TIME_ELAPSED_EXT);
        queries.push(query);
      }
    }
    // Queries are asynchronous; bounded wait and explicit missing results.
    for (
      let i = 0;
      i < 60 &&
      queries.some((q) => !gl.getQueryParameter(q, gl.QUERY_RESULT_AVAILABLE));
      i++
    )
      await new Promise((resolve) => requestAnimationFrame(resolve));
    const disjoint = timer ? gl.getParameter(timer.GPU_DISJOINT_EXT) : null;
    if (timer && !disjoint)
      for (const query of queries)
        if (gl.getQueryParameter(query, gl.QUERY_RESULT_AVAILABLE))
          gpu.push(gl.getQueryParameter(query, gl.QUERY_RESULT) / 1e6);
    return {
      renderer: info
        ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL)
        : gl.getParameter(gl.RENDERER),
      vendor: info
        ? gl.getParameter(info.UNMASKED_VENDOR_WEBGL)
        : gl.getParameter(gl.VENDOR),
      user_agent: navigator.userAgent,
      viewport: [canvas.width, canvas.height],
      frames: 60,
      upload_calls: uploads,
      upload_bytes: bytes,
      cpu_submit_ms: cpu,
      cpu_submit_median_ms: median(cpu),
      frame_intervals_ms: intervals,
      frame_interval_median_ms: median(intervals),
      gpu_timer_supported: !!timer,
      gpu_disjoint: disjoint,
      gpu_samples_ms: gpu,
      gpu_median_ms: median(gpu),
      limits:
        "Synthetic orbit on the loaded bracket. CPU measures event dispatch and draw submission, not GPU completion. RAF intervals include browser scheduling. GPU timings are reported only when available and non-disjoint; renderer identity determines whether this is hardware or software. Not a physical-display latency or memory benchmark.",
    };
  } finally {
    canvas.dispatchEvent(new PointerEvent("pointerup"));
    prototype.bufferData = originalUpload;
    canvas.setPointerCapture = originalCapture;
    for (const query of queries) gl.deleteQuery(query);
  }
})();
