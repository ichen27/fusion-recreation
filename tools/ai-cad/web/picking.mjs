// Disposable display-space selection. Exact modeling uses the returned feature ID.
function projector({ yaw, pitch, zoom, aspect }) {
  const cy = Math.cos(yaw),
    sy = Math.sin(yaw),
    cp = Math.cos(pitch),
    sp = Math.sin(pitch);
  return (x, y, z) => {
    x *= zoom;
    y *= zoom;
    z *= zoom;
    const xx = cy * x - sy * y,
      yy = sy * x + cy * y;
    return [xx / aspect, -sp * yy + cp * z, -0.2 * (cp * yy + sp * z)];
  };
}
export function projectVertex(point, camera) {
  return projector(camera)(...point);
}
export function pickSurface(packed, groups, camera, x, y) {
  if (
    ![x, y, camera.yaw, camera.pitch, camera.zoom, camera.aspect].every(
      Number.isFinite,
    ) ||
    camera.aspect <= 0 ||
    Math.abs(x) > 1 ||
    Math.abs(y) > 1
  )
    return null;
  const project = projector(camera);
  let nearest = Infinity,
    selected = null;
  for (const group of groups) {
    for (
      let first = group.first;
      first < group.first + group.count;
      first += 3
    ) {
      const p = [0, 1, 2].map((j) => {
        const i = (first + j) * 6;
        return project(packed[i], packed[i + 1], packed[i + 2]);
      });
      const [a, b, c] = p;
      const determinant =
        (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1]);
      if (Math.abs(determinant) < 1e-14) continue;
      const u =
        ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / determinant;
      const v =
        ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / determinant;
      const w = 1 - u - v;
      if (Math.min(u, v, w) < -1e-7) continue;
      const depth = u * a[2] + v * b[2] + w * c[2];
      // Match the viewport's orthographic clip/depth direction. Stable group
      // order breaks coplanar ties. Returned surface IDs must be revision-validated.
      if (depth >= -1 && depth <= 1 && depth < nearest - 1e-10) {
        nearest = depth;
        selected = {
          feature_id: group.feature_id,
          surface_id:
            group.triangle_surfaces?.[(first - group.first) / 3] ?? null,
        };
      }
    }
  }
  return selected;
}

export function pickBody(packed, groups, camera, x, y) {
  return pickSurface(packed, groups, camera, x, y)?.feature_id ?? null;
}
