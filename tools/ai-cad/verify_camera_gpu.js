// Run in the local viewer with agent-browser eval. No model/document mutation.
(async () => {
  const { cameraShader, presetCamera, projector, displayCamera } = await import(
    "/camera.mjs"
  );
  const canvas = document.createElement("canvas"),
    gl = canvas.getContext("webgl2");
  if (!gl) throw Error("WebGL 2 unavailable");
  const compile = (type, text) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, text);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS))
      throw Error(gl.getShaderInfoLog(s));
    return s;
  };
  const program = gl.createProgram();
  const vertex = compile(
    gl.VERTEX_SHADER,
    `#version 300 es
  in vec3 position; uniform vec2 angles; uniform vec2 pan; uniform float aspect; uniform float zoom;
  out vec3 projected;
  ${cameraShader}
  void main(){projected=cameraProject(position);gl_Position=vec4(projected,1.0);}`,
  );
  const fragment = compile(
    gl.FRAGMENT_SHADER,
    `#version 300 es
  precision highp float;out vec4 color;void main(){color=vec4(1);}`,
  );
  gl.attachShader(program, vertex);
  gl.attachShader(program, fragment);
  gl.transformFeedbackVaryings(program, ["projected"], gl.INTERLEAVED_ATTRIBS);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS))
    throw Error(gl.getProgramInfoLog(program));
  gl.useProgram(program);
  const input = gl.createBuffer(),
    output = gl.createBuffer(),
    feedback = gl.createTransformFeedback();
  const points = new Float32Array([
    0.1, 0.2, 0.3, -0.3, 0.5, 0.1, 0.8, -0.1, -0.6, 0, 0, 0,
  ]);
  gl.bindBuffer(gl.ARRAY_BUFFER, input);
  gl.bufferData(gl.ARRAY_BUFFER, points, gl.STATIC_DRAW);
  const attribute = gl.getAttribLocation(program, "position");
  gl.enableVertexAttribArray(attribute);
  gl.vertexAttribPointer(attribute, 3, gl.FLOAT, false, 0, 0);
  gl.bindTransformFeedback(gl.TRANSFORM_FEEDBACK, feedback);
  gl.bindBuffer(gl.TRANSFORM_FEEDBACK_BUFFER, output);
  gl.bufferData(
    gl.TRANSFORM_FEEDBACK_BUFFER,
    points.byteLength,
    gl.DYNAMIC_READ,
  );
  gl.bindBufferBase(gl.TRANSFORM_FEEDBACK_BUFFER, 0, output);
  gl.enable(gl.RASTERIZER_DISCARD);
  let maximumError = 0,
    cases = 0;
  for (const name of [
    "isometric",
    "front",
    "back",
    "left",
    "right",
    "top",
    "bottom",
  ])
    for (const aspect of [0.4, 1, 2])
      for (const zoom of [0.3, 1, 4]) {
        const camera = displayCamera(
          { ...presetCamera(name), zoom, pan: [0.23, -0.17] },
          aspect,
        );
        gl.uniform2f(
          gl.getUniformLocation(program, "angles"),
          camera.yaw,
          camera.pitch,
        );
        gl.uniform2f(gl.getUniformLocation(program, "pan"), ...camera.pan);
        gl.uniform1f(gl.getUniformLocation(program, "zoom"), camera.zoom);
        gl.uniform1f(gl.getUniformLocation(program, "aspect"), camera.aspect);
        gl.beginTransformFeedback(gl.POINTS);
        gl.drawArrays(gl.POINTS, 0, points.length / 3);
        gl.endTransformFeedback();
        const actual = new Float32Array(points.length);
        gl.getBufferSubData(gl.TRANSFORM_FEEDBACK_BUFFER, 0, actual);
        const project = projector(camera);
        for (let i = 0; i < points.length; i += 3) {
          const expected = project(...points.subarray(i, i + 3));
          for (let j = 0; j < 3; j++)
            maximumError = Math.max(
              maximumError,
              Math.abs(expected[j] - actual[i + j]),
            );
        }
        cases++;
      }
  const info = gl.getExtension("WEBGL_debug_renderer_info");
  const renderer = info
    ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL)
    : gl.getParameter(gl.RENDERER);
  const vendor = info
    ? gl.getParameter(info.UNMASKED_VENDOR_WEBGL)
    : gl.getParameter(gl.VENDOR);
  const error = gl.getError();
  gl.deleteBuffer(input);
  gl.deleteBuffer(output);
  gl.deleteTransformFeedback(feedback);
  gl.deleteProgram(program);
  gl.deleteShader(vertex);
  gl.deleteShader(fragment);
  gl.getExtension("WEBGL_lose_context")?.loseContext();
  if (error !== gl.NO_ERROR || maximumError > 2e-6)
    throw Error(`GPU/CPU projection mismatch: ${error}, ${maximumError}`);
  return {
    renderer,
    vendor,
    userAgent: navigator.userAgent,
    cases,
    pointsPerCase: points.length / 3,
    maximumError,
    glError: error,
    tolerance: 2e-6,
  };
})();
