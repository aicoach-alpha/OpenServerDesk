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
      " WIB · AUTOMATIC MONITORING DISABLED (historical snapshot only)";
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
// 15-minute server monitor explicitly disabled by operator; no timed polling.

let stageToken = "";
async function stageRequest(method, body) {
  if (!stageToken) throw Error("Enter operator token first");
  const options = {method, cache:"no-store", headers:{"Authorization":"Bearer " + stageToken}};
  if (body) {
    options.headers["Content-Type"]="application/json";
    options.body=JSON.stringify(body);
  }
  const response = await fetch("/api/v1/stage/apps", options);
  const data = await response.json();
  if (!response.ok) throw Error(data.error || "Stage API unavailable ("+response.status+")");
  return data;
}
function stageButton(text, disabled, callback) {
  const b=document.createElement("button");
  b.type="button";
  b.textContent=text;
  b.disabled=disabled;
  b.addEventListener("click", callback);
  return b;
}
async function stageRefresh() {
  try {
    const data=await stageRequest("GET");
    $("stage-message").textContent="Authorized; " + data.apps.length +
      " isolated stage apps · CasaOS production is not editable.";
    $("stage-install").disabled=false;
    for (const id of ["stage-file-save","stage-file-read","stage-file-delete"])
      $(id).disabled=false;
    stageFilesRefresh();
    $("stage-checkpoint").disabled=false;
    $("stage-recovery-refresh").disabled=false;
    stageRecoveryRefresh();
    const tbody=$("stage-apps-list");
    tbody.replaceChildren();
    for (const a of data.apps) {
      const tr=document.createElement("tr");
      cell(tr,a.name);cell(tr,a.image);
      const state=cell(tr,a.state);
      state.className=a.running?"running":"inactive";
      const tools=document.createElement("td");
      const actions=a.running?["stop","restart","uninstall"]:["start","uninstall"];
      for (const action of actions) {
        tools.appendChild(stageButton(action,false,()=>stageAct(action,a.name)));
      }
      tr.appendChild(tools);tbody.appendChild(tr);
    }
  } catch(err) {
    $("stage-install").disabled=true;
    $("stage-message").textContent="Stage access: "+err.message;
  }
}
async function stageAct(action,name) {
  if (action==="uninstall" && !confirm("Remove this isolated stage app?")) return;
  $("stage-message").textContent="Executing staged "+action+"…";
  try {
    const result=await stageRequest("POST",name?{action,name}:{action});
    $("stage-message").textContent="Stage "+result.operation+" succeeded";
    await stageRefresh();
  } catch(err) {
    $("stage-message").textContent="Stage action rejected: "+err.message;
  }
}
$("stage-connect").addEventListener("click",()=>{
  stageToken=$("stage-token").value.trim();
  $("stage-token").value="";
  $("stage-recover-interrupted").disabled=!stageToken;
  stageRefresh();
});
$("stage-install").addEventListener("click",()=>stageAct("install"));

async function stageFileApi(method, payload, name) {
  if (!stageToken) throw Error("Operator token required");
  let url="/api/v1/stage/files";
  if (name) url+="?name="+encodeURIComponent(name);
  const options={method,cache:"no-store",headers:{"Authorization":"Bearer "+stageToken}};
  if (payload) {
    options.headers["Content-Type"]="application/json";
    options.body=JSON.stringify(payload);
  }
  const resp=await fetch(url,options);
  const data=await resp.json();
  if (!resp.ok) throw Error(data.error || "File action failed");
  return data;
}
async function stageFilesRefresh() {
  const body=$("stage-files-list");
  try {
    const data=await stageFileApi("GET");
    body.replaceChildren();
    for (const f of data.files) {
      const item=document.createElement("button");
      item.type="button";
      item.textContent=f.name+" ("+f.bytes+" bytes)";
      item.addEventListener("click",()=>{
        $("stage-file-name").value=f.name;
        stageFileAction("read");
      });
      body.appendChild(item);
    }
    $("stage-files-status").textContent=data.files.length+" isolated stage files";
  } catch(error) {
    $("stage-files-status").textContent=error.message;
  }
}
async function stageFileAction(action) {
  const name=$("stage-file-name").value.trim();
  if (!name) {
    $("stage-files-status").textContent="Enter a file name first";
    return;
  }
  if (action==="delete" && !confirm("Delete this isolated stage file?")) return;
  try {
    if (action==="read") {
      const data=await stageFileApi("GET",null,name);
      $("stage-file-content").value=data.content;
      $("stage-files-status").textContent="Read "+name;
      return;
    }
    const payload=action==="create" ?
      {action,name,content:$("stage-file-content").value} : {action,name};
    await stageFileApi("POST",payload);
    $("stage-files-status").textContent=action+" complete for "+name;
    await stageFilesRefresh();
  } catch(err) {
    $("stage-files-status").textContent=err.message;
  }
}
$("stage-file-save").addEventListener("click",()=>stageFileAction("create"));
$("stage-file-read").addEventListener("click",()=>stageFileAction("read"));
$("stage-file-delete").addEventListener("click",()=>stageFileAction("delete"));

async function stageRecoveryApi(method,payload) {
  if (!stageToken) throw Error("Operator token required");
  const opts={method,cache:"no-store",headers:{"Authorization":"Bearer "+stageToken}};
  if (payload) {
    opts.headers["Content-Type"]="application/json";
    opts.body=JSON.stringify(payload);
  }
  const r=await fetch("/api/v1/stage/recovery",opts);
  const value=await r.json();
  if (!r.ok) throw Error(value.error || "Stage recovery unavailable");
  return value;
}
async function stageRecoveryRefresh() {
  try {
    const data=await stageRecoveryApi("GET");
    const list=$("stage-checkpoints");
    list.replaceChildren();
    for (const item of data.backups.slice().reverse()) {
      const b=stageButton("Restore "+item.id+" ("+item.files+" files)",
        false,()=>stageRestore(item.id));
      const remove=stageButton("Delete "+item.id,false,async()=>{
        if (!confirm("Permanently delete this STAGING backup?")) return;
        try {
          await stageRecoveryApi("POST",{action:"delete",checkpoint:item.id});
          stageRecoveryRefresh();
        } catch(err) {
          $("stage-recovery-status").textContent=err.message;
        }
      });
      list.appendChild(b);
      list.appendChild(remove);
    }
    $("stage-recovery-status").textContent=data.backups.length+
      " stage-only backups · production rollback NOT implemented";
  } catch(err) {
    $("stage-recovery-status").textContent=err.message;
  }
}
async function stageRestore(checkpoint) {
  if (!confirm("Restore "+checkpoint+" to isolated STAGING files? This changes only staging."))return;
  try {
    $("stage-recovery-status").textContent="Restoring stage data...";
    const result=await stageRecoveryApi("POST",{action:"restore",checkpoint});
    $("stage-recovery-status").textContent="Stage restored "+result.restored_checkpoint;
    stageFilesRefresh();
    stageRefresh();
  } catch(err) {
    $("stage-recovery-status").textContent="Restore failed: "+err.message+
      " (stage recovery journal may require operator inspection)";
  }
}
$("stage-checkpoint").addEventListener("click",async()=>{
  try {
    $("stage-recovery-status").textContent="Creating stage checkpoint...";
    const result=await stageRecoveryApi("POST",{action:"checkpoint"});
    $("stage-recovery-status").textContent="Created "+result.checkpoint;
    stageRecoveryRefresh();
  } catch(err) {
    $("stage-recovery-status").textContent="Stage checkpoint failed: "+err.message;
  }
});
$("stage-recovery-refresh").addEventListener("click",stageRecoveryRefresh);

$("stage-recover-interrupted").addEventListener("click",async()=>{
  if (!confirm("Recover an interrupted STAGE-only rollback from its undo journal?"))return;
  try {
    const result=await stageRecoveryApi("POST",{action:"recover"});
    $("stage-recovery-status").textContent=result.recovered;
    await stageRecoveryRefresh();
    await stageRefresh();
  } catch(err) {
    $("stage-recovery-status").textContent="Recovery operation failed: "+err.message;
  }
});

async function topology() {
  try {
    const response = await fetch("/api/v1/migration/topology", {cache:"no-store"});
    if (!response.ok) throw Error("Read-only topology unavailable");
    const report = await response.json();
    $("bind-filesystems").textContent = report.filesystem_count;
    $("shared-binds").textContent = report.shared_writable_source_count;
  } catch (_error) {
    $("bind-filesystems").textContent = "—";
    $("shared-binds").textContent = "—";
  }
}
topology();
