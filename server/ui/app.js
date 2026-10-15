const $ = id => document.getElementById(id);
function cell(row, value) {
  const td = document.createElement("td");
  td.textContent = value || "—";
  row.appendChild(td);
  return td;
}
async function refresh() {
  $("message").textContent = "Refreshing…";
  $("refresh").disabled = true;
  try {
    const response = await fetch("/api/v1/docker/containers", {cache: "no-store"});
    if (!response.ok) throw Error("Inventory unavailable (" + response.status + ")");
    const data = await response.json();
    $("total").textContent = data.container_count;
    $("running").textContent = data.states.running || 0;
    $("projects").textContent = data.compose_projects.length;
    const body = $("containers");
    body.replaceChildren();
    for (const c of data.containers) {
      const row = document.createElement("tr");
      cell(row, c.name);
      cell(row, c.image);
      const status = cell(row, c.state);
      status.className = c.state === "running" ? "running" : "inactive";
      cell(row, c.compose_project);
      cell(row, c.ports.map(p => p.public ? p.public + ":" + p.private : p.private).join(", "));
      body.appendChild(row);
    }
    $("message").textContent = data.container_count + " containers from the local Docker Engine";
  } catch (error) {
    $("message").textContent = error.message;
  } finally {
    $("refresh").disabled = false;
  }
}
$("refresh").addEventListener("click", refresh);
refresh();

async function coverage() {
  try {
    const result = await fetch("/api/v1/migration/data-coverage", {cache: "no-store"});
    if (!result.ok) throw Error("Coverage assessment unavailable ("+result.status+")");
    const data = await result.json();
    $("bind-sources").textContent = data.unique_bind_source_count;
    $("writable-mounts").textContent = data.live_writable_mount_count;
    $("named-volumes").textContent = data.referenced_named_volume_count;
    $("coverage-message").textContent =
      "Inventory snapshot: " + new Date(data.checked_at_utc).toLocaleString() +
      " · Real data backup, restore and cutover not yet verified.";
    $("coverage-status").textContent = "Migration blocked";
  } catch(err) {
    $("coverage-message").textContent = err.message;
  }
}
coverage();
