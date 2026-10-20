// Disposable samples of an exact measured edge. Never used for native length.
const color = [0.62, 0.12, 0.78];
function rational(value) {
  const parts = value.split("/").map(Number);
  const result = parts.length === 2 ? parts[0] / parts[1] : parts[0];
  if (!Number.isFinite(result)) throw Error("Edge exceeds display precision");
  return result;
}
export function edgeVertices(measurement, segments = 32) {
  if (!Number.isInteger(segments) || segments < 1 || segments > 256)
    throw Error("Expected 1..256 display segments");
  const [a, b] = measurement.endpoints_mm.map((p) => p.map(rational));
  if (measurement.curve.kind === "line")
    return [...a, ...color, ...b, ...color];
  if (measurement.curve.kind !== "quarter_circle")
    throw Error("Unsupported edge display");
  const center = measurement.curve.center.map(rational),
    axis = measurement.curve.axis,
    u = a.map((v, i) => v - center[i]),
    v = [
      axis[1] * u[2] - axis[2] * u[1],
      axis[2] * u[0] - axis[0] * u[2],
      axis[0] * u[1] - axis[1] * u[0],
    ],
    result = [...a, ...color];
  for (let i = 1; i < segments; i++) {
    const angle = (Math.PI * i) / (2 * segments);
    result.push(
      ...center.map(
        (c, j) => c + Math.cos(angle) * u[j] + Math.sin(angle) * v[j],
      ),
      ...color,
    );
  }
  result.push(...b, ...color);
  if (result.some((n) => !Number.isFinite(n)))
    throw Error("Edge exceeds display precision");
  return result;
}
