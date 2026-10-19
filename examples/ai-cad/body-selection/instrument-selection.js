// Evaluate once after the initial model loads, before exercising selection.
window.__uploads = 0;
const originalBufferData = WebGL2RenderingContext.prototype.bufferData;
WebGL2RenderingContext.prototype.bufferData = function (...args) {
  window.__uploads++;
  return originalBufferData.apply(this, args);
};
window.__selectionEvidence = [];
window.__recordSelection = (action) => {
  const row = {
    action,
    selection: document.querySelector("#selection-info").textContent,
    pressed: [
      ...document.querySelectorAll(".select-body[aria-pressed=true]"),
    ].map((button) => button.dataset.body),
    uploads: window.__uploads,
  };
  window.__selectionEvidence.push(row);
  return row;
};
