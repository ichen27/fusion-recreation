// Load failures must leave an actionable page even before the model app runs.
const panel = document.getElementById("startup-panel");
const message = document.getElementById("startup-message");
const reload = document.getElementById("startup-reload");
reload.addEventListener("click", () => window.location.reload());
function showRecovery(text) {
  panel.hidden = false;
  message.textContent = text;
  reload.hidden = false;
}
const deadline = setTimeout(() => {
  showRecovery(
    "The workspace is taking longer to load. Check that the local viewer is running, then reload.",
  );
}, 10000);
import("/app.js").then(
  () => {
    clearTimeout(deadline);
    panel.hidden = true;
  },
  () => {
    clearTimeout(deadline);
    showRecovery(
      "The workspace could not load. Check that the local viewer is running, then reload.",
    );
  },
);
