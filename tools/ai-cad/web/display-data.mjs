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
