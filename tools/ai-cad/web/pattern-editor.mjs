import {
  patternDraft,
  patternProposal,
  stepEditable,
} from "./pattern-model.mjs";
const $ = (id) => document.getElementById(id);
const axes = ["x", "y", "z"];
export function installPatternEditor({ getState, onOpen, onClose, onPreview }) {
  const dialog = $("pattern-dialog");
  let state,
    draft,
    pending = false;
  function controls() {
    $("pattern-count").disabled = pending;
    $("pattern-close").disabled = pending;
    $("pattern-preview").disabled = pending;
    axes.forEach(
      (axis, i) =>
        ($("pattern-" + axis).disabled =
          pending || !stepEditable(state, draft.step[i])),
    );
  }
  function close() {
    if (pending) return;
    dialog.close();
    onClose();
  }
  $("pattern-close").addEventListener("click", close);
  dialog.addEventListener("cancel", (e) => {
    e.preventDefault();
    close();
  });
  axes.forEach((axis, i) =>
    $("pattern-" + axis).addEventListener("input", () => {
      const value = $("pattern-" + axis).value;
      axes.forEach((other, j) => {
        if (draft.step[j] === draft.step[i])
          $("pattern-" + other).value = value;
      });
    }),
  );
  $("pattern-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (pending) return;
    draft.count = Number($("pattern-count").value);
    draft.values = axes.map((axis) => $("pattern-" + axis).value);
    try {
      const proposal = patternProposal(state, draft);
      pending = true;
      controls();
      $("pattern-feedback").textContent =
        "Combining repeated material and checking downstream features…";
      await onPreview(proposal);
      pending = false;
      dialog.close();
      onClose();
    } catch (error) {
      pending = false;
      controls();
      $("pattern-feedback").textContent = error.message;
    }
  });
  return {
    open(input, featureId = null) {
      state = structuredClone(getState());
      draft = patternDraft(state, input, featureId);
      $("pattern-count").value = draft.count;
      $("pattern-title").textContent = featureId
        ? `Edit ${featureId}`
        : `Pattern ${input}`;
      axes.forEach((axis, i) => ($("pattern-" + axis).value = draft.values[i]));
      $("pattern-feedback").textContent =
        "Count includes the source. Global step offsets repeat its material; overlaps and face joins combine into one result. Source dimensions remain editable.";
      controls();
      onOpen();
      dialog.showModal();
    },
  };
}
