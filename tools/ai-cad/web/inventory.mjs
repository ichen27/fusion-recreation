const $ = (id) => document.getElementById(id);

export function inventoryRows(result) {
  return result.rows.map((row) => [
    row.feature_id,
    row.feature_kind.replaceAll("_", " "),
    row.linked_source ?? "—",
    String(row.quantity),
    row.volume_mm3,
    row.material.status === "assigned"
      ? row.material.material.name
      : row.material.status,
    row.material.status === "assigned"
      ? row.material.material.density_kg_per_m3
      : "—",
  ]);
}

export function installInventory({ getState, onOpen, onClose }) {
  const dialog = $("inventory-dialog");
  let revision,
    generation = 0,
    ready = false,
    pending = false;
  function controls() {
    $("inventory-csv").disabled = $("inventory-json").disabled =
      !ready || pending;
  }
  function close() {
    generation++;
    dialog.close();
    onClose();
  }
  $("inventory-close").addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  async function read() {
    const reply = await (
      await fetch("/api/inventory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_revision: revision }),
      })
    ).json();
    if (reply.error) throw Error(`${reply.error.code}: ${reply.error.message}`);
    if (reply.result.revision !== revision || getState().revision !== revision)
      throw Error("The saved model changed. Close and reopen the inventory.");
    return reply.result;
  }
  function render(result) {
    const body = $("inventory-rows");
    body.replaceChildren();
    for (const cells of inventoryRows(result)) {
      const row = document.createElement("tr");
      for (const value of cells) {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      }
      body.append(row);
    }
    const counts = result.material_counts;
    $("inventory-status").textContent =
      `Saved revision ${result.revision} · ${result.solid_count} solids · Materials: ${counts.assigned} assigned, ${counts.unassigned} unassigned, ${counts.conflict} conflicting.`;
    $("inventory-source").textContent =
      `Source model SHA-256: ${result.source_model_sha256}`;
  }
  for (const format of ["csv", "json"]) {
    $("inventory-" + format).addEventListener("click", async () => {
      if (!ready || pending) return;
      const token = generation;
      pending = true;
      controls();
      try {
        const result = await read();
        if (token !== generation) return;
        render(result);
        const { csv, ...data } = result;
        const blob = new Blob(
          [format === "csv" ? csv : JSON.stringify(data, null, 2) + "\n"],
          {
            type:
              format === "csv" ? "text/csv;charset=utf-8" : "application/json",
          },
        );
        const url = URL.createObjectURL(blob),
          anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `cad-inventory-r${revision}.${format}`;
        anchor.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (error) {
        if (token === generation) {
          ready = false;
          $("inventory-status").textContent = error.message;
        }
      } finally {
        if (token === generation) {
          pending = false;
          controls();
        }
      }
    });
  }
  return {
    async open() {
      revision = getState().revision;
      const token = ++generation;
      ready = false;
      pending = true;
      controls();
      $("inventory-rows").replaceChildren();
      $("inventory-source").textContent = "";
      $("inventory-status").textContent = "Reading saved solids…";
      onOpen();
      dialog.showModal();
      try {
        const result = await read();
        if (token !== generation) return;
        render(result);
        ready = true;
      } catch (error) {
        if (token === generation)
          $("inventory-status").textContent = error.message;
      } finally {
        if (token === generation) {
          pending = false;
          controls();
        }
      }
    },
  };
}
