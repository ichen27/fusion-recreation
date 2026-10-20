// Disposable orthographic camera. These values never enter the native document.
import { fittedZoom } from "./display-data.mjs";
const presets = {
  isometric: [-Math.PI / 4, -Math.atan(1 / Math.sqrt(2))],
  front: [0, 0],
  back: [Math.PI, 0],
  right: [-Math.PI / 2, 0],
  left: [Math.PI / 2, 0],
  top: [0, -Math.PI / 2],
  bottom: [0, Math.PI / 2],
};
export function presetCamera(name) {
  if (!Object.hasOwn(presets, name)) throw Error("Unknown camera view");
  const [yaw, pitch] = presets[name];
  return { yaw, pitch, zoom: 1, pan: [0, 0] };
}
export function fitCamera(camera) {
  return { ...camera, zoom: 1, pan: [0, 0] };
}
export function orbitCamera(camera, dx, dy) {
  return {
    ...camera,
    yaw: Math.atan2(
      Math.sin(camera.yaw + dx * 0.008),
      Math.cos(camera.yaw + dx * 0.008),
    ),
    pitch: Math.max(
      -Math.PI / 2,
      Math.min(Math.PI / 2, camera.pitch + dy * 0.008),
    ),
  };
}
export function panCamera(camera, dx, dy, width, height) {
  if (width <= 0 || height <= 0) return camera;
  return {
    ...camera,
    pan: [camera.pan[0] + (2 * dx) / width, camera.pan[1] - (2 * dy) / height],
  };
}
export function zoomCamera(camera, delta, anchor = [0, 0]) {
  const zoom = Math.max(
    0.3,
    Math.min(4, camera.zoom * Math.exp(-delta * 0.001)),
  );
  const scale = zoom / camera.zoom;
  return {
    ...camera,
    zoom,
    pan: anchor.map((v, i) => v - (v - camera.pan[i]) * scale),
  };
}
export function displayCamera(camera, aspect) {
  return { ...camera, aspect, zoom: fittedZoom(camera.zoom, aspect) };
}
// Right/up/toward form a right-handed frame. At front, +X is right, +Z
// is up and the eye is on -Y; top looks from +Z with +Y up.
export function projector({ yaw, pitch, zoom, aspect, pan = [0, 0] }) {
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
    return [
      xx / aspect + pan[0],
      -sp * yy + cp * z + pan[1],
      0.2 * (cp * yy + sp * z),
    ];
  };
}
export const cameraShader = `
vec3 cameraProject(vec3 position) {
  vec3 p = position * zoom;
  float c = cos(angles.x), s = sin(angles.x);
  p = vec3(c*p.x-s*p.y, s*p.x+c*p.y, p.z);
  c = cos(angles.y); s = sin(angles.y);
  return vec3(p.x/aspect+pan.x, -s*p.y+c*p.z+pan.y, 0.2*(c*p.y+s*p.z));
}`;
