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

async function refreshProgress() {
  $("progress-updated").textContent = "Checking latest verified server snapshot…";
  try {
    const response = await fetch("/api/v1/m1/progress", {cache:"no-store"});
    if (!response.ok) throw Error("M1 progress report unavailable (" + response.status + ")");
    const report = await response.json();
    if (typeof report.progress_percent !== "number") throw Error("Invalid progress evidence");
    $("m1-progress").value = report.progress_percent;
    $("progress-number").textContent = report.progress_percent + "%";
    const checked = new Date(report.checked_at_utc);
    const age = Date.now() - checked.getTime();
    $("progress-updated").textContent =
      "Last server check " + checked.toLocaleString("id-ID", {timeZone:"Asia/Jakarta"}) +
      " WIB · " + (age > 21 * 60 * 1000 ? "STALE REPORT — latest check overdue" : "15-minute host reports enabled");
    const delta = report.delta_percent_since_previous;
    $("progress-delta").textContent = (delta === null ? "Initial verified baseline" :
      delta === 0 ? "NO NEW VERIFIED MILESTONE (+0%)" :
      "Verified milestone change: " + (delta > 0 ? "+" : "") + delta + "%") +
      ". This is weighted accepted scope, NOT the percentage of time remaining.";
    $("progress-commit").textContent = "Commit: " + report.git_sha +
      " · " + report.git_message + " · " + report.git_commit_at +
      (report.new_git_commit_since_previous === false ? " · NO NEW COMMIT THIS INTERVAL" :
       report.new_git_commit_since_previous === true ? " · NEW COMMIT" : "");
    $("progress-readiness").textContent = report.migration_allowed ?
      "Migration status: eligible for further authorization and safety verification" :
      "Migration BLOCKED: " + report.migration_reason;
    const gates = $("progress-gates");
    gates.replaceChildren();
    for (const item of report.milestones) {
      const div = document.createElement("div");
      div.className = "milestone";
      const status = document.createElement("strong");
      status.className = item.verified ? "running" : "inactive";
      status.textContent = item.verified ? "VERIFIED" : "NOT VERIFIED";
      div.appendChild(status);
      const label = document.createElement("span");
      label.textContent = " " + item.weight_percent + "% · " + item.label;
      div.appendChild(label);
      const cls = document.createElement("small");
      cls.textContent = item.evidence_class.replaceAll("_", " ");
      div.appendChild(cls);
      gates.appendChild(div);
    }
    const h = await fetch("/api/v1/m1/progress/history", {cache:"no-store"});
    if (!h.ok) throw Error("History unavailable (" + h.status + ")");
    const history = await h.json();
    const rows = $("progress-history");
    rows.replaceChildren();
    for (const item of history.entries.slice(-12).reverse()) {
      const tr = document.createElement("tr");
      cell(tr, item.checked_at_wib.replace("T"," ").slice(0,19));
      cell(tr, item.progress_percent + "%");
      cell(tr, item.delta_percent_since_previous == null ? "—" :
        (item.delta_percent_since_previous > 0 ? "+" : "") + item.delta_percent_since_previous + "%");
      cell(tr, item.git_sha);
      rows.appendChild(tr);
    }
  } catch (error) {
    $("progress-updated").textContent = "Progress reporting error: " + error.message;
  }
}
refreshProgress();
setInterval(refreshProgress, 60 * 1000);
