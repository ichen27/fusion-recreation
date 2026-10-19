// Convert only disposable display data. Native model coordinates remain exact.
export function packVertices(triangles, lines, center, extent) {
  if (
    !Number.isFinite(extent) ||
    extent <= 0 ||
    center.some((v) => !Number.isFinite(v))
  )
    throw Error(
      "Display coordinates require a finite center and positive extent",
    );
  const packed = new Float32Array(triangles.length + lines.length);
  let offset = 0;
  for (const source of [triangles, lines]) {
    if (source.length % 6)
      throw Error("Expected interleaved position/color vertices");
    for (let i = 0; i < source.length; i += 6) {
      for (let axis = 0; axis < 3; axis++)
        packed[offset + i + axis] = (source[i + axis] - center[axis]) / extent;
      for (let channel = 3; channel < 6; channel++)
        packed[offset + i + channel] = source[i + channel];
    }
    offset += source.length;
  }
  return packed;
}

export function formatMeasurement(value, locale) {
  return value.toLocaleString(
    locale,
    value !== 0 && Math.abs(value) < 0.001
      ? { notation: "scientific", maximumSignificantDigits: 4 }
      : { maximumFractionDigits: 3 },
  );
}

// A containing sphere fits at every orbit angle. Iterate to avoid argument-count
// limits from Math.min(...allVertices) on large display meshes.
export function displayFrame(points) {
  if (!points.length) return { center: [0, 0, 0], extent: 1 };
  const min = [Infinity, Infinity, Infinity],
    max = [-Infinity, -Infinity, -Infinity];
  for (const point of points)
    for (let axis = 0; axis < 3; axis++) {
      if (!Number.isFinite(point[axis]))
        throw Error("Display vertices must be finite");
      min[axis] = Math.min(min[axis], point[axis]);
      max[axis] = Math.max(max[axis], point[axis]);
    }
  const center = min.map((v, i) => v + (max[i] - v) / 2);
  let radius = 0;
  for (const point of points)
    radius = Math.max(
      radius,
      Math.hypot(
        point[0] - center[0],
        point[1] - center[1],
        point[2] - center[2],
      ),
    );
  return { center, extent: radius ? radius * 1.15 : 1 };
}
export function fittedZoom(zoom, aspect) {
  return zoom * Math.min(1, aspect);
}
