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
    let resourceById = new Map();
    try {
      const statsResponse = await fetch("/api/v1/docker/resources", {cache:"no-store"});
      if (!statsResponse.ok) throw Error("Live resource counters unavailable");
      const stats = await statsResponse.json();
      if (stats.source !== "local_docker_resource_metrics_readonly" ||
          stats.production_modified !== false ||
          stats.external_user_data_inspected !== false)
        throw Error("Unexpected Docker resource data");
      resourceById = new Map(stats.containers.map(r => [r.id, r]));
      $("docker-resources-status").textContent =
        "Live CPU, RAM and process counters for " + stats.container_count +
        " Docker containers · read-only";
    } catch (statsError) {
      $("docker-resources-status").textContent = statsError.message;
    }
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
      const resource = resourceById.get(c.id);
      cell(row, resource ? resource.cpu_percent.toFixed(2) + "%" : "—");
      cell(row, resource ? (resource.memory_used_bytes / (1024 * 1024)).toFixed(1) + " MiB" : "—");
      cell(row, resource && resource.pids != null ? resource.pids : "—");
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
let stageCanWrite = false;
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
    const identityResponse=await fetch("/api/v1/stage/whoami", {
      cache:"no-store",headers:{"Authorization":"Bearer "+stageToken}
    });
    const identity=await identityResponse.json();
    if (!identityResponse.ok) throw Error(identity.error||"Stage identity unavailable");
    stageCanWrite=Array.isArray(identity.permissions) &&
      identity.permissions.includes("write");
    const data=await stageRequest("GET");
    $("stage-message").textContent="Authenticated "+identity.actor+
      " ("+identity.role+"); "+data.apps.length+
      " isolated stage apps · production CasaOS is not editable.";
    $("stage-install").disabled=!stageCanWrite;
    $("stage-file-save").disabled=!stageCanWrite;
    $("stage-file-read").disabled=false;
    $("stage-file-delete").disabled=!stageCanWrite;
    $("stage-binary-upload").disabled=!stageCanWrite;
    $("stage-binary-download").disabled=false;
    stageFilesRefresh();
    $("stage-compose-install").disabled=!stageCanWrite;
    $("stage-compose-refresh").disabled=false;
    $("topology-install").disabled=!stageCanWrite;
    $("topology-refresh").disabled=false;
    topologyRefresh();
    $("appstore-refresh").disabled=false;
    $("appstore-pilot-install").disabled=!stageCanWrite;
    $("appstore-pilot-refresh").disabled=false;
    $("store-general-refresh").disabled=false;
    storeCoverageRefresh();
    storeGeneralRefresh();
    appstorePilotRefresh();
    if (!casaosStoreData) appstoreRefresh();
    stageComposeRefresh();
    for (const name of ["stage-compose-checkpoint", "stage-compose-checkpoints-refresh",
                        "stage-compose-recover"])
      $(name).disabled=!stageCanWrite;
    stageComposeBackupsRefresh();
    $("stage-checkpoint").disabled=!stageCanWrite;
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
        tools.appendChild(stageButton(action,!stageCanWrite,()=>stageAct(action,a.name)));
      }
      tr.appendChild(tools);tbody.appendChild(tr);
    }
  } catch(err) {
    stageCanWrite=false;
    $("stage-compose-install").disabled=true;
    $("stage-compose-refresh").disabled=true;
    $("topology-install").disabled=true;
    $("topology-refresh").disabled=true;
    $("appstore-refresh").disabled=true;
    $("appstore-pilot-install").disabled=true;
    $("appstore-pilot-refresh").disabled=true;
    $("store-general-refresh").disabled=true;
    $("store-general-install").disabled=true;
    $("store-general-prepare").disabled=true;
    for (const name of ["stage-compose-checkpoint", "stage-compose-checkpoints-refresh",
                        "stage-compose-recover"])
      $(name).disabled=true;
    $("stage-install").disabled=true;
    $("stage-binary-upload").disabled=true;
    $("stage-binary-download").disabled=true;
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
  $("stage-recover-interrupted").disabled=true;
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

async function stageBinaryUpload() {
  const selected=$("stage-binary-input").files?.[0];
  if (!selected || selected.size>65536 || !stageCanWrite) {
    $("stage-files-status").textContent="Choose a writable stage-only file up to 64 KiB";
    return;
  }
  try {
    const result=await fetch("/api/v1/stage/upload",{
      method:"POST",cache:"no-store",
      headers:{
        "Authorization":"Bearer "+stageToken,
        "Content-Type":"application/octet-stream",
        "X-OSD-Filename":selected.name
      },
      body:await selected.arrayBuffer()
    });
    const message=await result.json();
    if (!result.ok) throw Error(message.error||"Stage upload rejected");
    $("stage-files-status").textContent="Uploaded "+message.created+" to isolated stage only";
    $("stage-file-name").value=message.created;
    await stageFilesRefresh();
  } catch(error) {
    $("stage-files-status").textContent="Stage upload error: "+error.message;
  }
}
async function stageBinaryDownload() {
  const name=$("stage-file-name").value.trim();
  if (!name || !stageToken) return;
  try {
    const response=await fetch("/api/v1/stage/download?name="+encodeURIComponent(name),{
      method:"GET",cache:"no-store",
      headers:{"Authorization":"Bearer "+stageToken}
    });
    if (!response.ok) {
      const error=await response.json();
      throw Error(error.error||"Stage download rejected");
    }
    const file=await response.blob();
    const objectUrl=URL.createObjectURL(file);
    const link=document.createElement("a");
    link.href=objectUrl;
    link.download=name;
    link.click();
    URL.revokeObjectURL(objectUrl);
    $("stage-files-status").textContent="Downloaded "+name+" from isolated stage";
  } catch(error) {
    $("stage-files-status").textContent="Stage download error: "+error.message;
  }
}
$("stage-binary-upload").addEventListener("click",stageBinaryUpload);
$("stage-binary-download").addEventListener("click",stageBinaryDownload);

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
        !stageCanWrite,()=>stageRestore(item.id));
      const remove=stageButton("Delete "+item.id,!stageCanWrite,async()=>{
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


async function refreshCutoverPlan() {
  try {
    const response=await fetch("/api/v1/migration/cutover-plan", {cache:"no-store"});
    if (!response.ok) throw Error("Cutover planning unavailable ("+response.status+")");
    const report=await response.json();
    if (report.migration_allowed !== false || report.user_data_content_accessed !== false)
      throw Error("Unexpected unsafe cutover report");
    $("cutover-status").textContent="CUTOVER BLOCKED";
    $("cutover-checked").textContent="Read-only evidence checked " +
      new Date(report.checked_at_utc).toLocaleString("id-ID",{timeZone:"Asia/Jakarta"})+" WIB";
    $("cutover-files").textContent=report.verified_config_files;
    $("cutover-dbs").textContent=report.verified_sqlite_databases;
    $("cutover-protected").textContent=report.protected_bind_references_preserved;
    const descriptions={
      platform_scope_not_user_data:"Platform configuration selected; Nextcloud uploads excluded",
      backup_on_independent_ssd:"Platform backup is on an independent SSD filesystem",
      backed_up_platform_source_set_matches_current:"Backup covers selected current platform roots",
      verified_ssd_snapshot_and_independent_restore:"SSD backup and separate restore independently verified",
      six_casaos_units_healthy:"All six original CasaOS services healthy",
      cross_service_consistent_snapshot:"Cross-service transaction consistency verified",
      production_switch_and_undo_rehearsed:"Production-equivalent activation and complete rollback proven",
      independent_security_and_signed_release:"Independent security and signed release acceptance",
      explicit_maintenance_authorization:"Explicitly authorized production maintenance",
    };
    const holder=$("cutover-gates");holder.replaceChildren();
    for (const [key,label] of Object.entries(descriptions)) {
      const item=document.createElement("div");item.className="milestone";
      const state=document.createElement("strong");
      state.className=report.gates[key]?"running":"inactive";
      state.textContent=report.gates[key]?"VERIFIED":"BLOCKED";
      const explanation=document.createElement("span");explanation.textContent=" "+label;
      item.append(state,explanation);holder.appendChild(item);
    }
    $("cutover-next").textContent=report.next_priority;
  } catch(err) {
    $("cutover-status").textContent="Unavailable";
    $("cutover-checked").textContent="Cutover report: "+err.message;
  }
}
refreshCutoverPlan();

async function stageComposeRequest(method, body) {
  if (!stageToken) throw Error("Stage authentication required");
  const opts={method,headers:{"Authorization":"Bearer "+stageToken},cache:"no-store"};
  if (body) {
    opts.headers["Content-Type"]="application/json";
    opts.body=JSON.stringify(body);
  }
  const response=await fetch("/api/v1/stage/compose",opts);
  const data=await response.json();
  if (!response.ok) throw Error(data.error || "Compose action failed");
  return data;
}
async function stageComposeRefresh() {
  try {
    const result=await stageComposeRequest("GET");
    $("stage-compose-status").textContent=result.projects.length+
      " isolated Compose projects; no existing CasaOS container can be changed.";
    const tbody=$("stage-compose-list");
    tbody.replaceChildren();
    for (const project of result.projects) {
      const tr=document.createElement("tr");
      cell(tr,project.project);cell(tr,project.template);
      const status=cell(tr,project.running?"running":"stopped");
      status.className=project.running?"running":"inactive";
      const tools=document.createElement("td");
      for (const action of (project.running?["stop","restart","uninstall"]:["start","uninstall"])) {
        tools.appendChild(stageButton(action,false,()=>stageComposeAct(action,project.project)));
      }
      tr.appendChild(tools);tbody.appendChild(tr);
    }
  } catch(err) {
    $("stage-compose-status").textContent=err.message;
  }
}
async function stageComposeAct(action, project) {
  $("stage-compose-status").textContent="Stage Compose "+action+" in progress…";
  try {
    await stageComposeRequest("POST",{action,project});
    await stageComposeRefresh();
    refresh();
  } catch(err) {
    $("stage-compose-status").textContent=err.message;
  }
}
$("stage-compose-install").addEventListener("click",async()=>{
  $("stage-compose-install").disabled=true;
  $("stage-compose-status").textContent="Installing the isolated Compose template…";
  try {
    await stageComposeRequest("POST",{action:"install",template:$("stage-compose-template").value});
    await stageComposeRefresh();
    refresh();
  } catch(err) {
    $("stage-compose-status").textContent=err.message;
  } finally {
    $("stage-compose-install").disabled=!stageCanWrite;
  }
});
$("stage-compose-refresh").addEventListener("click",stageComposeRefresh);

async function composeBackupRequest(method, data) {
  if (!stageToken) throw Error("Stage authentication required");
  const opts={method,headers:{"Authorization":"Bearer "+stageToken},cache:"no-store"};
  if (data) {
    opts.headers["Content-Type"]="application/json";
    opts.body=JSON.stringify(data);
  }
  const response=await fetch("/api/v1/stage/compose-backups",opts);
  const result=await response.json();
  if (!response.ok) throw Error(result.error || "Compose backup action failed");
  return result;
}
async function stageComposeBackupsRefresh() {
  try {
    const result=await composeBackupRequest("GET");
    $("stage-compose-backup-status").textContent=result.backups.length+
      " isolated Compose checkpoints; pending recovery="+result.pending_recovery;
    const holder=$("stage-compose-checkpoints");holder.replaceChildren();
    for (const checkpoint of result.backups) {
      const item=document.createElement("div");
      item.textContent=checkpoint.id+" · "+checkpoint.projects+" projects ";
      item.appendChild(stageButton("Restore",false,()=>stageComposeBackupAct("restore",checkpoint.id)));
      item.appendChild(stageButton("Delete",false,()=>stageComposeBackupAct("delete",checkpoint.id)));
      holder.appendChild(item);
    }
  } catch(err) {
    $("stage-compose-backup-status").textContent=err.message;
  }
}
async function stageComposeBackupAct(action,checkpoint) {
  $("stage-compose-backup-status").textContent="Compose "+action+" in progress…";
  try {
    const body={action};
    if (checkpoint) body.checkpoint=checkpoint;
    await composeBackupRequest("POST",body);
    await stageComposeBackupsRefresh();
    await stageComposeRefresh();
  } catch(err) {
    $("stage-compose-backup-status").textContent=err.message;
  }
}
$("stage-compose-checkpoint").addEventListener("click",()=>stageComposeBackupAct("checkpoint"));
$("stage-compose-checkpoints-refresh").addEventListener("click",stageComposeBackupsRefresh);
$("stage-compose-recover").addEventListener("click",()=>stageComposeBackupAct("recover"));

async function refreshComposeParity() {
  try {
    const response=await fetch("/api/v1/m1/compose-parity",{cache:"no-store"});
    if (!response.ok) throw Error("Compatibility baseline unavailable ("+response.status+")");
    const data=await response.json();
    if (data.migration_allowed !== false || data.nextcloud_user_files_opened !== false)
      throw Error("Unexpected unsafe compatibility report");
    $("parity-config-count").textContent=data.source_config_definitions;
    $("parity-valid-count").textContent=data.valid_definitions;
    $("parity-service-count").textContent=data.source_services;
    $("parity-import-count").textContent=data.generally_importable_apps_e2e_verified+
      "/"+data.source_config_definitions;
    $("parity-gap-count").textContent=data.definitions_needing_additional_compose_support;
    $("parity-status").textContent=data.general_casaos_compose_parity_proven ?
      "App compatibility proven" : "APP PARITY NOT YET PROVEN";
    $("parity-message").textContent="Safe YAML-only baseline checked "+
      new Date(data.checked_at_utc).toLocaleString("id-ID",{timeZone:"Asia/Jakarta"})+
      " WIB. No external user files accessed.";
  } catch(err) {
    $("parity-message").textContent=err.message;
  }
}
refreshComposeParity();

async function refreshHostStatus() {
  $("host-refresh").disabled=true;
  try {
    const response=await fetch("/api/v1/system/status",{cache:"no-store"});
    if (!response.ok) throw Error("Host metrics unavailable ("+response.status+")");
    const d=await response.json();
    if (d.external_user_data_disks_inspected !== false ||
        d.source !== "local_linux_readonly")
      throw Error("Unexpected host status report scope");
    $("host-cpus").textContent=d.cpu_logical_cores;
    $("host-load").textContent=d.load_averages.join(" / ");
    $("host-memory").textContent=d.memory.used_percent+"%";
    $("host-uptime").textContent=Math.floor(d.uptime_seconds/86400)+" days";
    $("host-root").textContent=d.filesystems.system.used_percent+"%";
    $("host-ssd").textContent=d.filesystems.ssd.used_percent+"%";
    $("host-status-message").textContent="Live OS metrics refreshed; no external user HDD access.";
  } catch(err) {
    $("host-status-message").textContent=err.message;
  } finally { $("host-refresh").disabled=false; }
}
$("host-refresh").addEventListener("click",refreshHostStatus);
refreshHostStatus();


async function topologyApi(method,payload) {
  if (!stageToken) throw Error("Staging authorization required");
  const opts={method,cache:"no-store",headers:{"Authorization":"Bearer "+stageToken}};
  if (payload) {
    opts.headers["Content-Type"]="application/json";
    opts.body=JSON.stringify(payload);
  }
  const response=await fetch("/api/v1/stage/topologies",opts);
  const content=await response.json();
  if (!response.ok) throw Error(content.error||"Isolated topology request failed");
  return content;
}

async function topologyRefresh() {
  try {
    const data=await topologyApi("GET");
    const body=$("topology-list");
    body.replaceChildren();
    for (const item of data.topologies) {
      const row=document.createElement("tr");
      cell(row,item.project);
      cell(row,item.services.map(s=>s.name).join(", "));
      cell(row,item.services.filter(s=>s.running).length+" / "+item.services.length);
      const actions=document.createElement("td");
      for (const action of (item.running ? ["stop","restart","uninstall"] :
                              ["start","uninstall"])) {
        actions.appendChild(stageButton(action,!stageCanWrite,async()=>{
          if (action==="uninstall" && !confirm("Delete this isolated staging topology?"))return;
          try {
            $("topology-status").textContent="Running isolated "+action+"…";
            await topologyApi("POST",{action,project:item.project});
            await topologyRefresh();
          } catch(err) {
            $("topology-status").textContent=err.message;
          }
        }));
      }
      row.appendChild(actions);
      body.appendChild(row);
    }
    $("topology-status").textContent=data.topologies.length+
      " isolated multi-service projects; original CasaOS apps are not editable";
  } catch(err) {
    $("topology-status").textContent="Stage topologies: "+err.message;
  }
}
$("topology-refresh").addEventListener("click",topologyRefresh);
$("topology-install").addEventListener("click",async()=>{
  const three=$("topology-template").value==="three";
  const services=[
    {name:"frontend",depends_on:["db"]},
    {name:"db",depends_on:[]}
  ];
  if (three)services.push({name:"worker",depends_on:["db"]});
  try {
    $("topology-install").disabled=true;
    $("topology-status").textContent="Installing offline multi-service topology…";
    await topologyApi("POST",{action:"install",services});
    await topologyRefresh();
  } catch(err) {
    $("topology-status").textContent=err.message;
  } finally {
    $("topology-install").disabled=!stageCanWrite;
  }
});


let casaosStoreData=null;
let appstoreVisibleCount=30;

async function appstoreRefresh() {
  if (!stageToken) {
    $("appstore-status").textContent="Staging authentication is required.";
    return;
  }
  $("appstore-refresh").disabled=true;
  $("appstore-status").textContent="Reading locally cached CasaOS App Store…";
  try {
    const response=await fetch("/api/v1/stage/casaos-appstore",{
      cache:"no-store",headers:{"Authorization":"Bearer "+stageToken}
    });
    const result=await response.json();
    if (!response.ok)throw Error(result.error||"App Store request failed");
    if (result.source!=="existing_casaos_appstore_cache_readonly"
        || result.production_modified!==false
        || result.nextcloud_user_data_inspected!==false
        || result.app_install_enabled!==false)
      throw Error("Unexpected App Store scope");
    casaosStoreData=result;
    const category=$("appstore-category");
    category.replaceChildren();
    category.add(new Option("All categories",""));
    for (const name of result.categories) category.add(new Option(name,name));
    const store=$("appstore-source");
    store.replaceChildren();
    store.add(new Option("All stores",""));
    for (const name of Object.keys(result.store_counts).sort())
      store.add(new Option(name+" ("+result.store_counts[name]+")",name));
    appstoreVisibleCount=30;
    appstoreRender();
    $("appstore-status").textContent=result.app_count+
      " CasaOS catalogue records loaded from local store cache · install disabled until staging parity is proven";
  } catch(err) {
    $("appstore-status").textContent="App Store unavailable: "+err.message;
  } finally {
    $("appstore-refresh").disabled=!stageToken;
  }
}

function appstoreRender() {
  if (!casaosStoreData)return;
  const search=$("appstore-search").value.trim().toLowerCase();
  const category=$("appstore-category").value;
  const source=$("appstore-source").value;
  const matches=casaosStoreData.apps.filter(app=>{
    return (!source||app.store===source)&&(!category||app.category===category)
      && (!search||[app.title,app.tagline,app.category,app.store]
                         .some(v=>String(v).toLowerCase().includes(search)));
  });
  const tbody=$("appstore-list");
  tbody.replaceChildren();
  for (const app of matches.slice(0,appstoreVisibleCount)) {
    const tr=document.createElement("tr");
    cell(tr,app.title);
    cell(tr,app.category);
    cell(tr,app.store);
    cell(tr,app.service_count);
    const actions=document.createElement("td");
    const button=document.createElement("button");
    button.type="button";
    button.textContent="Compatibility";
    button.addEventListener("click",()=>appstoreDetails(app.id));
    actions.appendChild(button);
    tr.appendChild(actions);
    tbody.appendChild(tr);
  }
  $("appstore-result-count").textContent=
    "Showing "+Math.min(matches.length,appstoreVisibleCount)+
    " / "+matches.length+" matching apps";
  $("appstore-more").disabled=matches.length<=appstoreVisibleCount;
}
async function appstoreDetails(id) {
  $("appstore-details").textContent="Checking CasaOS App Store compatibility…";
  try {
    const response=await fetch("/api/v1/stage/casaos-appstore?id="+encodeURIComponent(id),{
      cache:"no-store",headers:{"Authorization":"Bearer "+stageToken}
    });
    const app=await response.json();
    if (!response.ok)throw Error(app.error||"Compatibility unavailable");
    const risks=Object.entries(app.compatibility)
      .filter(([key,value])=>value===true && key!=="metadata_read")
      .map(([key])=>key.replaceAll("_"," "));
    $("appstore-details").textContent=app.title+": "+app.service_count+
      " service(s). Review: "+(risks.join(", ")||"none indicated")+
      ". Production installation remains blocked.";
    await storeGeneralPreflight(id);
  } catch(err) {
    $("appstore-details").textContent=err.message;
  }
}
$("appstore-refresh").addEventListener("click",appstoreRefresh);
$("appstore-search").addEventListener("input",()=>{
  appstoreVisibleCount=30;appstoreRender();
});
$("appstore-category").addEventListener("change",()=>{
  appstoreVisibleCount=30;appstoreRender();
});
$("appstore-source").addEventListener("change",()=>{
  appstoreVisibleCount=30;appstoreRender();
});
$("appstore-more").addEventListener("click",()=>{
  appstoreVisibleCount+=30;appstoreRender();
});


async function appstorePilotRequest(method,payload) {
  if (!stageToken) throw Error("Staging authorization required");
  const opts={method,cache:"no-store",headers:{"Authorization":"Bearer "+stageToken}};
  if (payload) {
    opts.headers["Content-Type"]="application/json";
    opts.body=JSON.stringify(payload);
  }
  const response=await fetch("/api/v1/stage/casaos-store-pilot",opts);
  const output=await response.json();
  if (!response.ok)throw Error(output.error||"Stage App Store pilot unavailable");
  return output;
}
async function appstorePilotRefresh() {
  try {
    const result=await appstorePilotRequest("GET");
    if (result.scope!=="approved_isolated_casaos_store_pilot"
        || result.production_mutation_allowed!==false)
      throw Error("Unexpected App Store installation scope");
    const holder=$("appstore-pilot-apps");
    holder.replaceChildren();
    $("appstore-pilot-install").disabled=!stageCanWrite||result.apps.length>0;
    for (const app of result.apps) {
      const row=document.createElement("div");
      const label=document.createElement("span");
      label.textContent=app.app_id+" · "+app.state+" · ";
      row.appendChild(label);
      const operations=app.running?["stop","restart","uninstall"]:["start","uninstall"];
      for (const action of operations) {
        const button=document.createElement("button");
        button.type="button";
        button.disabled=!stageCanWrite;
        button.textContent=action;
        button.addEventListener("click",async()=>{
          if (action==="uninstall" && !confirm("Uninstall the isolated MySpeed staging app?"))return;
          try {
            $("appstore-pilot-status").textContent="Running "+action+"…";
            await appstorePilotRequest("POST",{action,project:app.project});
            await appstorePilotRefresh();
          } catch(err) {
            $("appstore-pilot-status").textContent=err.message;
          }
        });
        row.appendChild(button);
      }
      holder.appendChild(row);
    }
    $("appstore-pilot-status").textContent=result.apps.length+
      " real CasaOS Store app pilot(s) in isolated staging; no production app changes";
  } catch(err) {
    $("appstore-pilot-status").textContent=err.message;
  }
}
$("appstore-pilot-refresh").addEventListener("click",appstorePilotRefresh);
$("appstore-pilot-install").addEventListener("click",async()=>{
  if (!confirm("Install a separate MySpeed 1.0.8 container ONLY in isolated staging?"))return;
  $("appstore-pilot-install").disabled=true;
  $("appstore-pilot-status").textContent="Installing exact original MySpeed App Store image…";
  try {
    await appstorePilotRequest("POST",{action:"install",id:"default:MySpeed"});
    await appstorePilotRefresh();
  } catch(err) {
    $("appstore-pilot-status").textContent=err.message;
    $("appstore-pilot-install").disabled=!stageCanWrite;
  }
});


let generalInstallSelection=null;
let generalPrepareSelection=null;
async function storeGeneralApi(method,payload,id) {
  if (!stageToken)throw Error("Staging operator authentication required");
  const suffix=id?"?id="+encodeURIComponent(id):"";
  const opts={method,cache:"no-store",headers:{"Authorization":"Bearer "+stageToken}};
  if (payload){
    opts.headers["Content-Type"]="application/json";
    opts.body=JSON.stringify(payload);
  }
  const response=await fetch("/api/v1/stage/store-general"+suffix,opts);
  const result=await response.json();
  if (!response.ok)throw Error(result.error||"Staging app installation unavailable");
  return result;
}
async function storeGeneralPreflight(id) {
  generalInstallSelection=null;
  generalPrepareSelection=null;
  $("store-general-install").disabled=true;
  $("store-general-prepare").disabled=true;
  $("store-general-status").textContent="Evaluating safe staging install requirements…";
  try{
    const plan=await storeGeneralApi("GET",null,id);
    const available=plan.eligible===true && plan.image_cached===true;
    generalInstallSelection=available?id:null;
    generalPrepareSelection=plan.eligible&&!plan.image_cached?id:null;
    $("store-general-install").disabled=!stageCanWrite||!available;
    $("store-general-prepare").disabled=!stageCanWrite||!generalPrepareSelection;
    $("store-general-status").textContent=available
      ? "Ready: "+plan.title+" · "+plan.image+" · "+plan.mount_count+
        " isolated volume(s); original host ports and network disabled"
      : "Staging install: "+(plan.reason||"unsupported application");
  }catch(err){
    $("store-general-status").textContent="Staging plan: "+err.message;
  }
}
async function storeGeneralRefresh() {
  try {
    const result=await storeGeneralApi("GET");
    if (result.scope!=="catalog_derived_isolated_singlestage"
        || result.production_mutation_allowed!==false)
      throw Error("Unexpected staging lifecycle scope");
    const holder=$("store-general-list");
    holder.replaceChildren();
    for (const entry of result.apps) {
      const row=document.createElement("div");
      const label=document.createElement("span");
      label.textContent=entry.app_id+" · "+(entry.running?"running":"stopped")+" · ";
      row.append(label);
      for (const op of (entry.running?["stop","restart","uninstall"]:["start","uninstall"])) {
        const btn=document.createElement("button");
        btn.type="button";btn.disabled=!stageCanWrite;btn.textContent=op;
        btn.addEventListener("click",async()=>{
          if (op==="uninstall" && !confirm("Delete this isolated staged container? Stage data will be retained."))return;
          try{
            $("store-general-status").textContent="Staging "+op+" in progress…";
            await storeGeneralApi("POST",{action:op,project:entry.project});
            await storeGeneralRefresh();
          }catch(err){$("store-general-status").textContent=err.message;}
        });
        row.append(btn);
      }
      holder.append(row);
    }
    if (result.apps.length)
      $("store-general-status").textContent=result.apps.length+
        " staged App Store install(s), never production Docker projects";
  }catch(err){
    $("store-general-status").textContent="App Store staging status: "+err.message;
  }
}
$("store-general-install").addEventListener("click",async()=>{
  if (!generalInstallSelection||!stageCanWrite)return;
  if (!confirm("Install "+generalInstallSelection+
      " into a new isolated staging container with NO external network or published ports?"))return;
  const appId=generalInstallSelection;
  $("store-general-install").disabled=true;
  $("store-general-status").textContent="Installing sandboxed native catalog image…";
  try{
    await storeGeneralApi("POST",{action:"install",id:appId});
    await storeGeneralRefresh();
  }catch(err){
    $("store-general-status").textContent=err.message;
  }finally{
    $("store-general-install").disabled=!stageCanWrite||!generalInstallSelection;
  }
});
$("store-general-refresh").addEventListener("click",storeGeneralRefresh);


$("store-general-prepare").addEventListener("click",async()=>{
  if (!generalPrepareSelection||!stageCanWrite)return;
  const id=generalPrepareSelection;
  if (!confirm("Download the original, exact-version CasaOS app image "+
      "to Docker cache? This will not install or run it."))return;
  $("store-general-prepare").disabled=true;
  $("store-general-status").textContent="Preparing exact catalog image…";
  try{
    await storeGeneralApi("POST",{action:"prepare",id});
    await storeGeneralPreflight(id);
  }catch(err){
    $("store-general-status").textContent="Image preparation: "+err.message;
    $("store-general-prepare").disabled=!stageCanWrite;
  }
});

async function storeCoverageRefresh() {
  if (!stageToken)return;
  try {
    const response=await fetch("/api/v1/stage/store-coverage",{
      cache:"no-store",headers:{"Authorization":"Bearer "+stageToken}
    });
    if (!response.ok)throw Error("coverage endpoint unavailable: "+response.status);
    const report=await response.json();
    if (report.production_modified!==false
        || report.external_nextcloud_user_data_inspected!==false
        || report.migration_allowed!==false)
      throw Error("invalid coverage scope");
    const c=report.staging_static_eligibility;
    $("store-general-coverage").textContent=
      "CasaOS definitions "+report.definitions_examined+
      " · static staging eligible "+c.eligible_for_isolated_staging+
      " · multi-service "+c.requires_multiservice_engine+
      " · advanced runtime "+c.advanced_runtime_options+
      " · unpinned images "+c.image_tag_not_pinned+
      " · volumes to resolve "+c.unsupported_volume_mapping+
      ". Not a runtime installation success count.";
  } catch(error) {
    $("store-general-coverage").textContent="Coverage unavailable: "+error.message;
  }
}
