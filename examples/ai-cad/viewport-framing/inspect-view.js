(() => {
  const gl = document.querySelector("#viewport").getContext("webgl2");
  const program = gl.getParameter(gl.CURRENT_PROGRAM);
  const data = new Float32Array(
    gl.getBufferParameter(gl.ARRAY_BUFFER, gl.BUFFER_SIZE) / 4,
  );
  gl.getBufferSubData(gl.ARRAY_BUFFER, 0, data);
  const [yaw, pitch] = gl.getUniform(
    program,
    gl.getUniformLocation(program, "angles"),
  );
  const zoom = gl.getUniform(program, gl.getUniformLocation(program, "zoom"));
  const aspect = gl.getUniform(
    program,
    gl.getUniformLocation(program, "aspect"),
  );
  const projected = [];
  for (let i = 0; i < data.length; i += 6) {
    const [x, y, z] = [data[i] * zoom, data[i + 1] * zoom, data[i + 2] * zoom];
    const xx = Math.cos(yaw) * x - Math.sin(yaw) * y,
      yy = Math.sin(yaw) * x + Math.cos(yaw) * y;
    projected.push([xx / aspect, -Math.sin(pitch) * yy + Math.cos(pitch) * z]);
  }
  return {
    vertices: data.length / 6,
    viewport: [gl.drawingBufferWidth, gl.drawingBufferHeight],
    zoom,
    aspect,
    bounds: [0, 1].map((axis) => [
      Math.min(...projected.map((p) => p[axis])),
      Math.max(...projected.map((p) => p[axis])),
    ]),
    uploads: window.__uploads ?? null,
  };
})();
