const $ = id => document.getElementById(id);
// Task-based workspace: one page at a time, all existing API actions preserved.
const workspaceTitles={
  overview:"Overview",apps:"Applications",store:"App Store",
  manage:"Manage staging",monitor:"Monitoring",admin:"Release & migration"
};
function workspaceView(name,changeHash=true){
  if (!Object.prototype.hasOwnProperty.call(workspaceTitles,name))name="overview";
  document.querySelectorAll("#workspace > [data-view]").forEach(panel=>{
    panel.hidden=panel.dataset.view!==name;
  });
  document.body.dataset.activeView=name;
  document.querySelectorAll("[data-nav]").forEach(button=>{
    const active=button.dataset.nav===name;
    button.classList.toggle("is-active",active);
    if(active)button.setAttribute("aria-current","page");
    else button.removeAttribute("aria-current");
  });
  $("page-title").textContent=workspaceTitles[name];
  document.title="OpenServerDesk Alpha · "+workspaceTitles[name];
  document.body.classList.remove("nav-open");
  $("nav-toggle").setAttribute("aria-expanded","false");
  $("mobile-nav-backdrop").hidden=true;
  if(changeHash && window.location.hash!=="#"+name)
    window.history.replaceState(null,"","#"+name);
  window.scrollTo({top:0,behavior:"instant"});
}
document.querySelectorAll("[data-nav]").forEach(button=>{
  button.addEventListener("click",()=>workspaceView(button.dataset.nav));
});
document.querySelectorAll("[data-go]").forEach(button=>{
  button.addEventListener("click",()=>workspaceView(button.dataset.go));
});
$("nav-toggle").addEventListener("click",()=>{
  const open=!document.body.classList.contains("nav-open");
  document.body.classList.toggle("nav-open",open);
  $("nav-toggle").setAttribute("aria-expanded",String(open));
  $("mobile-nav-backdrop").hidden=!open;
});
$("mobile-nav-backdrop").addEventListener("click",()=>{
  document.body.classList.remove("nav-open");
  $("nav-toggle").setAttribute("aria-expanded","false");
  $("mobile-nav-backdrop").hidden=true;
});
$("topbar-connect").addEventListener("click",()=>{
  workspaceView("manage");
  $("stage-token").focus();
});
window.addEventListener("hashchange",()=>{
  workspaceView(window.location.hash.slice(1),false);
});
workspaceView(window.location.hash.slice(1)||"overview",false);

function renderOverviewFromInventory(data){
  if(!data || data.source!=="local_docker_engine_read_only" ||
     !Array.isArray(data.containers))return;
  $("overview-total").textContent=String(data.container_count);
  $("overview-running").textContent=String(data.states.running||0);
  $("overview-compose").textContent=String(data.compose_projects.length);
  const projects=new Map();
  for(const app of data.containers){
    const name=app.compose_project||app.name||"Unnamed container";
    if(!projects.has(name))projects.set(name,[]);
    projects.get(name).push(app);
  }
  const preview=$("overview-app-preview");
  preview.replaceChildren();
  for(const [name,items] of [...projects].sort((a,b)=>
      a[0].localeCompare(b[0])).slice(0,6)){
    const card=document.createElement("article");
    card.className="preview-app";
    const label=document.createElement("strong");
    label.textContent=name;
    label.title=name;
    const state=document.createElement("small");
    const count=items.filter(item=>item.state==="running").length;
    state.textContent=count+"/"+items.length+" running · Docker read-only";
    card.append(label,state);
    preview.appendChild(card);
  }
  if(!projects.size)preview.textContent="No Docker apps discovered.";
}
async function overviewMemoryRefresh(){
  try{
    const response=await fetch("/api/v1/system/status",{cache:"no-store"});
    if(!response.ok)throw Error("Host metrics unavailable");
    const data=await response.json();
    if(data.source!=="local_linux_readonly" || data.production_modified!==false)
      throw Error("Unexpected server metric scope");
    $("overview-memory").textContent=data.memory.used_percent.toFixed(1)+"%";
  }catch(error){$("overview-memory").textContent="—";}
}
overviewMemoryRefresh();

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
    renderOverviewFromInventory(data);
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
// Apps Hub: a single user-facing entrypoint, reusing existing guarded APIs.
// The host Docker inventory is ALWAYS read-only; only owner-verified staging
// apps expose management navigation.
let hubDockerData=null;
let hubStageData=null;
let hubView="installed";
let hubLimit=12;
const hubDestinations={
  docker:"stage-apps-list",
  compose:"stage-compose-list",
  store_pilot:"appstore-pilot-apps",
  store_general:"store-general-list",
  store_compiled:"compiled-list"
};
function hubNavigate(id) {
  const target=$(id);
  if (!target)return;
  if (target.closest("[data-view]"))workspaceView(target.closest("[data-view]").dataset.view);
  target.scrollIntoView({behavior:"smooth",block:"start"});
  target.setAttribute("tabindex","-1");
  target.focus({preventScroll:true});
}
function hubMetric(label,value){
  const item=document.createElement("span");
  item.className="hub-metric";
  item.textContent=String(value)+" "+label;
  return item;
}
function hubCard(item) {
  const card=document.createElement("article");
  card.className="hub-card";
  const title=document.createElement("h3");
  title.textContent=item.title;
  const flag=document.createElement("span");
  flag.className="hub-state"+(item.running?" running":"");
  flag.textContent=item.scope+" · "+item.state;
  const description=document.createElement("p");
  description.textContent=item.description;
  const actions=document.createElement("div");
  actions.className="hub-actions";
  if (item.manage) {
    if(item.lifecycleApp && stageCanWrite && item.lifecycleApp.lifecycle_writable){
      const app=item.lifecycleApp;
      const menu=document.createElement("details");
      menu.className="hub-lifecycle-menu";
      const toggle=document.createElement("summary");
      toggle.textContent="Lifecycle";
      menu.appendChild(toggle);
      const controls=document.createElement("div");
      controls.className="hub-menu-actions";
      const action=app.lifecycle==="stopped"?"start":"stop";
      controls.appendChild(stageButton(action==="start"?"Start":"Stop",false,
        ()=>hubStageAction(app,action)));
      if(action==="stop")
        controls.appendChild(stageButton("Restart",false,
          ()=>hubStageAction(app,"restart")));
      if(app.source==="store_compiled"){
        controls.appendChild(stageButton("Update",false,
          ()=>hubStageAction(app,"update")));
        if(app.stage_rollback_available)
          controls.appendChild(stageButton("Rollback",false,
            ()=>hubStageAction(app,"rollback")));
        controls.appendChild(stageButton(app.lifecycle==="running"?
          "Backup + restart":"Backup",false,()=>hubStageAction(app,
            app.lifecycle==="running"?"backup-online":"checkpoint")));
      }
      controls.appendChild(stageButton("Uninstall",false,
        ()=>hubStageAction(app,"uninstall")));
      menu.appendChild(controls);
      actions.appendChild(menu);
    }
    actions.appendChild(stageButton("Details",false,()=>hubNavigate(item.manage)));
  } else if (item.store_id) {
    actions.appendChild(stageButton("View compatibility",false,()=>{
      hubNavigate("appstore-panel");
      appstoreDetails(item.store_id);
    }));
  } else {
    const note=document.createElement("span");
    note.className="hub-state";
    note.textContent="Read-only";
    actions.appendChild(note);
  }
  card.append(title,flag,description,actions);
  return card;
}
function hubRender() {
  const rows=[];
  const metrics=$("hub-metrics");
  metrics.replaceChildren();
  const needle=$("hub-search").value.trim().toLowerCase();
  if (hubView==="installed") {
    if (hubDockerData) {
      const groups=new Map();
      for (const service of hubDockerData.containers) {
        const group=service.compose_project||service.name||"Unnamed container";
        if (!groups.has(group))groups.set(group,[]);
        groups.get(group).push(service);
      }
      for (const [name,services] of groups) {
        const active=services.filter(x=>x.state==="running").length;
        rows.push({
          title:name,scope:"Docker host / read-only",
          state:active+"/"+services.length+" running",running:active===services.length,
          description:services.map(x=>x.name+" · "+x.state).join(" | "),
        });
      }
      metrics.appendChild(hubMetric("host Docker projects/containers",groups.size));
    }
    if (hubStageData) {
      for (const app of hubStageData.applications) {
        rows.push({
          title:app.name,scope:"Isolated staging / "+app.source,
          state:app.lifecycle.replaceAll("_"," "),
          running:app.lifecycle==="running",
          description:(app.project?app.project+" · ":"")+
            app.readiness.replaceAll("_"," ")+
            (app.service_counts?" · "+app.service_counts.running+
              "/"+app.service_counts.total+" services":""),
          manage:hubDestinations[app.source],
          lifecycleApp:app
        });
      }
      for (const restricted of (hubStageData.restricted_projects||[])) {
        rows.push({
          title:restricted.project,scope:"Isolated staging / restricted",
          state:"Read-only",running:false,
          description:restricted.reason.replaceAll("_"," ")
        });
      }
      metrics.appendChild(hubMetric("staging projects",
        hubStageData.applications.length+(hubStageData.restricted_projects||[]).length));
    }
  } else if (casaosStoreData) {
    for (const app of casaosStoreData.apps) {
      rows.push({
        title:app.title,scope:"CasaOS Store / "+app.store,
        state:app.category,running:false,
        description:(app.tagline||"App Store catalogue")+
          " · "+app.service_count+" service(s)",
        store_id:app.id
      });
    }
    metrics.appendChild(hubMetric("catalogue apps",casaosStoreData.app_count));
  }
  const matches=rows.filter(item=>!needle ||
    [item.title,item.scope,item.state,item.description]
      .some(value=>String(value).toLowerCase().includes(needle)));
  const grid=$("hub-cards");
  grid.replaceChildren(...matches.slice(0,hubLimit).map(hubCard));
  $("hub-more").hidden=matches.length<=hubLimit;
  if (hubView==="store"&&!casaosStoreData) {
    $("hub-status").textContent="Loading local CasaOS App Store catalogue…";
  } else if (hubView==="installed"&&!hubDockerData&&!hubStageData) {
    $("hub-status").textContent="Docker inventory unavailable; refresh to retry.";
  } else {
    $("hub-status").textContent=matches.length+" matching "+
      (hubView==="installed"?"installed/staging entries":"catalogue apps")+
      " · showing "+Math.min(matches.length,hubLimit)+
      (hubView==="installed"&&!stageToken?" · Connect for staging management":"")+
      (hubStageData&&hubView==="installed"&&!hubStageData.complete?
       " · staging inventory incomplete":"");
  }
}
async function hubStageAction(app,action){
  if(!stageToken||!stageCanWrite || app.lifecycle_writable!==true)return;
  const standard=["start","stop","restart","uninstall"];
  const compiled=["update","rollback","checkpoint","backup-online"];
  if(!standard.includes(action) &&
     !(app.source==="store_compiled" && compiled.includes(action)))return;
  if(action==="rollback" && !app.stage_rollback_available)return;
  if(action==="checkpoint" && app.lifecycle!=="stopped")return;
  if(action==="backup-online" && app.lifecycle!=="running")return;
  if(["uninstall","update","rollback","backup-online"].includes(action) &&
     !confirm(action+" "+app.name+" in isolated staging? "+
       "Original CasaOS apps and data remain unchanged."))return;
  $("hub-status").textContent="Running "+action+" on isolated staging "+app.name+"…";
  try{
    if(app.source==="docker")
      await stageRequest("POST",{action,name:app.name});
    else if(app.source==="compose")
      await stageComposeRequest("POST",{action,project:app.project});
    else if(app.source==="store_pilot")
      await appstorePilotRequest("POST",{action,project:app.project});
    else if(app.source==="store_general")
      await storeGeneralApi("POST",{action,project:app.project});
    else if(app.source==="store_compiled")
      await compiledApi("POST",{action,project:app.project});
    else throw Error("Unknown isolated staging source");
    await hubRefresh();
    // Refresh existing management panels without changing their permissions.
    if(app.source==="store_compiled")await compiledRefresh();
    else if(app.source==="store_general")await storeGeneralRefresh();
    else if(app.source==="store_pilot")await appstorePilotRefresh();
    else if(app.source==="compose")await stageComposeRefresh();
    else if(app.source==="docker")await stageRefresh();
  }catch(err){
    $("hub-status").textContent="Staging "+action+" failed: "+err.message;
  }
}
async function hubRefresh(){
  $("hub-refresh").disabled=true;
  try {
    const response=await fetch("/api/v1/docker/containers",{cache:"no-store"});
    if (!response.ok)throw Error("Docker inventory HTTP "+response.status);
    const data=await response.json();
    if (data.source!=="local_docker_engine_read_only" ||
        !Array.isArray(data.containers) ||
        data.container_count!==data.containers.length)
      throw Error("Invalid host Docker inventory scope");
    hubDockerData=data;
    renderOverviewFromInventory(data);
  }catch(err){
    hubDockerData=null;
    $("hub-status").textContent="Host Docker inventory: "+err.message;
  }
  if (stageToken) {
    try {
      const response=await fetch("/api/v1/stage/unified-inventory",{
        cache:"no-store",headers:{"Authorization":"Bearer "+stageToken}});
      if (!response.ok)throw Error("Staging access HTTP "+response.status);
      const data=await response.json();
      if (data.scope!=="stage_owned_inventory_only" ||
          data.production_mutation_allowed!==false ||
          !Array.isArray(data.applications))
        throw Error("Invalid isolated staging scope");
      hubStageData=data;
    }catch(err){
      hubStageData=null;
      $("hub-status").textContent="Staging inventory: "+err.message;
    }
    if (hubView==="store"&&!casaosStoreData)await appstoreRefresh();
  } else {
    hubStageData=null;
  }
  $("hub-refresh").disabled=false;
  hubRender();
}
$("hub-refresh").addEventListener("click",hubRefresh);
$("hub-tab-installed").addEventListener("click",()=>{
  hubView="installed";hubLimit=12;
  $("hub-tab-installed").setAttribute("aria-pressed","true");
  $("hub-tab-store").setAttribute("aria-pressed","false");
  hubRender();
});
$("hub-tab-store").addEventListener("click",async()=>{
  hubView="store";hubLimit=12;
  $("hub-tab-store").setAttribute("aria-pressed","true");
  $("hub-tab-installed").setAttribute("aria-pressed","false");
  if (!casaosStoreData)await appstoreRefresh();
  hubRender();
});
$("hub-search").addEventListener("input",()=>{hubLimit=12;hubRender();});
$("hub-more").addEventListener("click",()=>{hubLimit+=12;hubRender();});
hubRefresh();

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
async function updateUnifiedInventoryAfterAction() {
  try { await unifiedStageInventoryRefresh(); }
  catch(err) { $("stage-unified-summary").textContent="Unified inventory: "+err.message; }
  await hubRefresh();
}
// Docker healthchecks are optional and only describe the in-container probe.
function stageHealthLabel(running, health) {
  const descriptions={
    healthy:"Docker healthcheck passed",
    unhealthy:"Docker healthcheck failed",
    starting:"Docker healthcheck starting",
    not_configured:"Docker healthcheck not configured",
    unknown:"Docker healthcheck unknown"
  };
  if (typeof running!=="boolean" ||
      !Object.prototype.hasOwnProperty.call(descriptions,health))
    throw Error("Invalid isolated staging health status");
  return running ? descriptions[health] : "Not ready (stopped)";
}
async function unifiedStageInventoryRefresh() {
  if (!stageToken) return;
  const response=await fetch("/api/v1/stage/unified-inventory",{
    cache:"no-store",headers:{"Authorization":"Bearer "+stageToken}
  });
  const result=await response.json();
  if (!response.ok) throw Error(result.error||"Unified inventory unavailable");
  if (result.scope!=="stage_owned_inventory_only" ||
      result.production_mutation_allowed!==false)
    throw Error("Unsafe unified inventory scope");
  const counts=result.counts;
  const expected=["docker","compose","store_pilot","store_general","store_compiled"];
  const unavailable=result.unavailable_sources;
  const partial=result.partial_sources;
  const restricted=result.restricted_projects;
  if (!Array.isArray(unavailable) || !Array.isArray(partial) ||
      !Array.isArray(restricted) ||
      unavailable.some(key=>!expected.includes(key)) ||
      partial.some(key=>key!=="store_compiled" || unavailable.includes(key)) ||
      new Set(unavailable).size!==unavailable.length ||
      new Set(partial).size!==partial.length ||
      result.complete!==(unavailable.length===0 && partial.length===0) ||
      !expected.every(key=>unavailable.includes(key)?
        counts[key]===null:(Number.isInteger(counts[key]) && counts[key]>=0)) ||
      restricted.some(r=>r.source!=="store_compiled" ||
        typeof r.project!=="string" ||
        !["protected_stage_credentials","pending_staging_recovery"].includes(r.reason)) ||
      (partial.includes("store_compiled") !== (restricted.length>0)))
    throw Error("Invalid unified inventory source availability");
  if (!Array.isArray(result.applications) ||
      result.applications.length!==result.total ||
      result.total!==expected.reduce((sum,key)=>sum+(counts[key]||0),0))
    throw Error("Invalid unified inventory entries");
  const tbody=$("stage-unified-apps-list");
  const rows=[];
  for (const app of result.applications) {
    const compiled=app.source==="store_compiled";
    const validHealth=["healthy","unhealthy","starting","not_configured","unknown"];
    const validReadiness=["not_ready","not_verified","healthcheck_passed",
                          "healthcheck_failed","checking"];
    if (!expected.includes(app.source) || typeof app.name!=="string" ||
        typeof app.lifecycle_writable!=="boolean" ||
        (app.stage_revision!==null &&
          (!Number.isInteger(app.stage_revision) || app.stage_revision<1)) ||
        typeof app.stage_rollback_available!=="boolean" ||
        !Number.isInteger(app.stage_checkpoint_count) ||
        app.stage_checkpoint_count<0 ||
        typeof app.running!=="boolean" ||
        !validHealth.includes(app.health_status) ||
        !validReadiness.includes(app.readiness) ||
        (app.project!==null && typeof app.project!=="string"))
      throw Error("Invalid staged application record");
    if (compiled) {
      const n=app.service_counts;
      if (!["running","stopped","partially_running"].includes(app.lifecycle) ||
          app.running!==(app.lifecycle==="running") ||
          typeof app.project!=="string" ||
          !n || !Number.isInteger(n.total) || n.total<1 ||
          !Number.isInteger(n.running) || !Number.isInteger(n.stopped) ||
          n.running+n.stopped!==n.total ||
          typeof app.partial_failure!=="boolean")
        throw Error("Invalid compiled application lifecycle");
    } else if (app.lifecycle!==(app.running?"running":"stopped") ||
        app.readiness!==(app.running?
          ({healthy:"healthcheck_passed",unhealthy:"healthcheck_failed",
            starting:"checking",not_configured:"not_verified",
            unknown:"not_verified"})[app.health_status]:"not_ready")) {
      throw Error("Invalid isolated application lifecycle");
    }
    const tr=document.createElement("tr");
    cell(tr,app.source);cell(tr,app.name);cell(tr,app.project||"—");
    const state=cell(tr,app.lifecycle.replaceAll("_"," "));
    state.className=app.lifecycle==="running"?"running":"inactive";
    const readinessText={
      not_ready:"Not ready",not_verified:"Not verified",
      healthcheck_passed:"Healthcheck passed",healthcheck_failed:"Healthcheck failed",
      checking:"Checking"
    };
    cell(tr,readinessText[app.readiness]+(compiled?
      " · "+app.service_counts.running+"/"+app.service_counts.total+" services running":""));
    const destinations={
      docker:"stage-apps-list",
      compose:"stage-compose-list",
      store_pilot:"appstore-pilot-apps",
      store_general:"store-general-list",
      store_compiled:"compiled-list"
    };
    const actionCell=document.createElement("td");
    const go=stageButton("Manage",false,()=>{
      const target=$(destinations[app.source]);
      target.scrollIntoView({behavior:"smooth",block:"center"});
      target.setAttribute("tabindex","-1");
      target.focus({preventScroll:true});
    });
    go.setAttribute("aria-label","Manage "+app.name+" in "+app.source+" staging");
    actionCell.appendChild(go);
    tr.appendChild(actionCell);
    rows.push(tr);
  }
  for (const restrictedProject of restricted) {
    const tr=document.createElement("tr");
    cell(tr,restrictedProject.source);
    cell(tr,"Restricted stage project");
    cell(tr,restrictedProject.project);
    cell(tr,"restricted");
    cell(tr,restrictedProject.reason==="protected_stage_credentials"?
      "Root-protected credentials":"Staging recovery required");
    cell(tr,"—");
    rows.push(tr);
  }
  tbody.replaceChildren(...rows);
  const lifecycle=result.lifecycle_counts;
  if (!lifecycle || !Number.isInteger(lifecycle.running) ||
      !Number.isInteger(lifecycle.stopped) ||
      !Number.isInteger(lifecycle.partially_running) ||
      lifecycle.running+lifecycle.stopped+lifecycle.partially_running!==result.total)
    throw Error("Invalid lifecycle counts");
  $("stage-unified-summary").textContent="Managed staging inventory: "+
    result.total+" total · "+counts.docker+" Docker · "+counts.compose+
    " Compose · "+counts.store_pilot+" Store pilot · "+
    counts.store_general+" Store catalog · "+
    (counts.store_compiled===null?"Store multi-service unavailable":
      counts.store_compiled+" Store multi-service")+
    " · "+lifecycle.running+" running · "+
    lifecycle.partially_running+" partially running · "+
    lifecycle.stopped+" stopped"+
    (result.complete?"":" · Incomplete inventory: "+
      [...unavailable,...partial.map(x=>x+" (restricted)")].join(", "))+
    (restricted.length?" · "+restricted.length+" project(s) restricted":"");
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
    hubRefresh();
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
    compiledRefresh();
    storeGeneralRefresh();
    appstorePilotRefresh();
    if (!casaosStoreData) appstoreRefresh();
    if (appstoreSelectedId && appstoreCompatibilityItem(appstoreSelectedId)?.sandbox_plan_supported) {
      Promise.all([storeGeneralPreflight(appstoreSelectedId),
                   storeCompilerPreview(appstoreSelectedId)])
        .then(appstoreSelectionSync).catch(()=>appstoreSelectionSync());
    }
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
    await stageComposeRefresh();
    try { await unifiedStageInventoryRefresh(); }
    catch(err) { $("stage-unified-summary").textContent="Unified inventory: "+err.message; }
  } catch(err) {
    stageCanWrite=false;
    $("stage-compose-install").disabled=true;
    $("stage-compose-refresh").disabled=true;
    $("topology-install").disabled=true;
    $("topology-refresh").disabled=true;
    $("appstore-refresh").disabled=false;
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
      cell(tr,stageHealthLabel(project.running,project.health_status));
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
    await updateUnifiedInventoryAfterAction();
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
    await updateUnifiedInventoryAfterAction();
    refresh();
  } catch(err) {
    $("stage-compose-status").textContent=err.message;
  } finally {
    $("stage-compose-install").disabled=!stageCanWrite;
  }
});
$("stage-compose-refresh").addEventListener("click",stageRefresh);

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
let casaosStoreMatrix=null;
let appstoreSelectedId=null;
let appstoreVisibleCount=30;
function appstoreCompatibilityItem(id) {
  return casaosStoreMatrix?.byId.get(id)||null;
}
function appstoreSelectionSync() {
  const panel=$("store-selection");
  const id=appstoreSelectedId;
  panel.hidden=!id;
  if (!id)return;
  const item=casaosStoreData?.apps.find(app=>app.id===id);
  const compat=appstoreCompatibilityItem(id);
  $("store-selection-name").textContent=item?.title||id;
  const supported=compat?.sandbox_plan_supported===true;
  $("store-selection-gaps").textContent=compat?.feature_gaps?.length?
    "Source features intentionally not preserved in sandbox: "+
      compat.feature_gaps.join(", ").replaceAll("_"," "):
    "Only isolated staging functionality is assessed. Original CasaOS settings and data are not imported.";
  const ready=compiledSelectedId===id || generalInstallSelection===id;
  const prepare=compiledPrepareId===id || generalPrepareSelection===id;
  $("store-selection-prepare").disabled=!stageCanWrite||!supported||!prepare;
  $("store-selection-install").disabled=!stageCanWrite||!supported||!ready;
  $("store-selection-prepare").textContent=stageCanWrite?"Prepare image":"Prepare (login required)";
  $("store-selection-install").textContent=stageCanWrite?"Install in staging":"Install (login required)";
  $("store-selection-manage").textContent=stageToken?"Manage installed apps":"Connect staging";
  $("store-selection-status").textContent=!supported
    ? "Additional compatibility work required: "+(compat?.reason||"unverified")
    : !stageToken
      ? "Sandbox plan available. Connect a staging operator to prepare images and install."
      : !stageCanWrite
        ? "Read-only operator. App lifecycle controls require a write role."
        : ready
          ? "Image cached and sandbox plan ready. Installation affects staging only."
          : prepare
            ? "Sandbox plan supported. Prepare an exact image before installing."
            : "Checking local image cache and safe staging readiness…";
}
async function appstoreRefresh() {
  $("appstore-refresh").disabled=true;
  $("appstore-status").textContent="Loading local CasaOS catalogue and staging compatibility…";
  try {
    const [catalogResponse,matrixResponse]=await Promise.all([
      fetch("/api/v1/appstore/catalog",{cache:"no-store"}),
      fetch("/api/v1/appstore/compatibility-matrix",{cache:"no-store"})
    ]);
    if (!catalogResponse.ok||!matrixResponse.ok)
      throw Error("App Store metadata unavailable ("+
        catalogResponse.status+"/"+matrixResponse.status+")");
    const result=await catalogResponse.json();
    const matrix=await matrixResponse.json();
    if (result.source!=="existing_casaos_appstore_cache_readonly"
        || result.production_modified!==false
        || result.nextcloud_user_data_inspected!==false
        || result.app_install_enabled!==false
        || matrix.scope!=="sanitized_local_casaos_appstore_sandbox_plans"
        || matrix.production_mutation_allowed!==false
        || matrix.production_equivalence_proven!==false
        || matrix.runtime_compatibility_proven!==false
        || matrix.nextcloud_user_data_inspected!==false
        || matrix.app_count!==result.app_count || !Array.isArray(matrix.apps))
      throw Error("Unexpected App Store compatibility boundary");
    const byId=new Map(matrix.apps.map(entry=>[entry.id,entry]));
    if(byId.size!==result.app_count ||
       !result.apps.every(item=>byId.has(item.id)) ||
       matrix.sandbox_plan_supported+matrix.sandbox_plan_blocked!==result.app_count)
      throw Error("Inconsistent App Store compatibility matrix");
    casaosStoreData=result;
    casaosStoreMatrix={...matrix,byId};
    hubRender();
    const category=$("appstore-category");
    const priorCategory=category.value;
    category.replaceChildren(new Option("All categories",""));
    for(const name of result.categories)category.add(new Option(name,name));
    category.value=priorCategory;
    const store=$("appstore-source");
    const priorStore=store.value;
    store.replaceChildren(new Option("All stores",""));
    for(const name of Object.keys(result.store_counts).sort())
      store.add(new Option(name+" ("+result.store_counts[name]+")",name));
    store.value=priorStore;
    const metrics=$("store-compat-kpis");
    metrics.replaceChildren(
      hubMetric("catalogue apps",result.app_count),
      hubMetric("sandbox plans supported",matrix.sandbox_plan_supported),
      hubMetric("needing additional support",matrix.sandbox_plan_blocked),
      hubMetric("fully digest-pinned plans",matrix.supported_with_all_images_digest_pinned)
    );
    appstoreVisibleCount=30;
    appstoreRender();
    appstoreSelectionSync();
    $("appstore-status").textContent=result.app_count+
      " available catalogue records · "+matrix.sandbox_plan_supported+
      " statically supported sandbox plans · "+
      "app functionality and CasaOS production equivalence not yet verified.";
  }catch(err){
    $("appstore-status").textContent="App Store: "+err.message;
  }finally{
    $("appstore-refresh").disabled=false;
  }
}

function appstoreRender() {
  if (!casaosStoreData)return;
  const search=$("appstore-search").value.trim().toLowerCase();
  const category=$("appstore-category").value;
  const source=$("appstore-source").value;
  const matches=casaosStoreData.apps.filter(app=>{
    return (!source||app.store===source)&&(!category||app.category===category)
      && (!$("appstore-compat-filter").value ||
          (appstoreCompatibilityItem(app.id)?.sandbox_plan_supported===
           ($("appstore-compat-filter").value==="supported")))
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
    const status=cell(tr,appstoreCompatibilityItem(app.id)?.sandbox_plan_supported
      ? "Sandbox plan available":"Additional support needed");
    status.className=appstoreCompatibilityItem(app.id)?.sandbox_plan_supported
      ? "running":"inactive";
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
  appstoreSelectedId=id;
  compiledSelectedId=null;compiledPrepareId=null;
  generalInstallSelection=null;generalPrepareSelection=null;
  appstoreSelectionSync();
  const item=casaosStoreData?.apps.find(row=>row.id===id);
  if (!item) {
    $("appstore-details").textContent="App is not present in the local catalogue.";
    return;
  }
  const compat=appstoreCompatibilityItem(id);
  const risks=Object.entries(item.compatibility||{})
    .filter(([key,value])=>value===true && key!=="metadata_read")
    .map(([key])=>key.replaceAll("_"," "));
  $("appstore-details").textContent=item.title+": "+item.service_count+
    " service(s). Original Compose features: "+(risks.join(", ")||"none indicated")+
    ". This is a fresh sandbox deployment, never an import of production data.";
  if (stageToken && compat?.sandbox_plan_supported===true) {
    await Promise.all([storeGeneralPreflight(id),storeCompilerPreview(id)]);
  }
  if(appstoreSelectedId===id)appstoreSelectionSync();
  $("store-selection").scrollIntoView({behavior:"smooth",block:"center"});
}
$("appstore-refresh").addEventListener("click",appstoreRefresh);
$("appstore-compat-filter").addEventListener("change",()=>{
  appstoreVisibleCount=30;appstoreRender();
});
$("store-selection-prepare").addEventListener("click",()=>{
  if(!appstoreSelectedId||!stageCanWrite)return;
  if(compiledPrepareId===appstoreSelectedId) $("compiled-prepare").click();
  else if(generalPrepareSelection===appstoreSelectedId)
    $("store-general-prepare").click();
});
$("store-selection-install").addEventListener("click",()=>{
  if(!appstoreSelectedId||!stageCanWrite)return;
  if(compiledSelectedId===appstoreSelectedId) $("compiled-install").click();
  else if(generalInstallSelection===appstoreSelectedId)
    $("store-general-install").click();
});
$("store-selection-manage").addEventListener("click",()=>{
  workspaceView(stageToken?"apps":"manage");
  if (!stageToken) $("stage-token").focus();
});

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
function stageStoreInventorySummary(pilotCount, generalCount) {
  const node=$("stage-store-inventory-summary");
  if (!node) return;
  node.textContent="App Store staging: "+pilotCount+
    " approved pilot(s) · "+generalCount+
    " catalog-derived install(s). Managed below with isolated lifecycle controls.";
}
let stageStorePilotCount=0;
let stageStoreGeneralCount=0;
async function appstorePilotRefresh() {
  try {
    const result=await appstorePilotRequest("GET");
    if (result.scope!=="approved_isolated_casaos_store_pilot"
        || result.production_mutation_allowed!==false)
      throw Error("Unexpected App Store installation scope");
    stageStorePilotCount=result.apps.length;
    stageStoreInventorySummary(stageStorePilotCount,stageStoreGeneralCount);
    const holder=$("appstore-pilot-apps");
    holder.replaceChildren();
    $("appstore-pilot-install").disabled=!stageCanWrite||result.apps.length>0;
    for (const app of result.apps) {
      const row=document.createElement("div");
      const label=document.createElement("span");
      label.textContent=app.app_id+" · "+app.state+" · "+
        stageHealthLabel(app.running,app.health_status)+" · ";
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
            await updateUnifiedInventoryAfterAction();
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
    await updateUnifiedInventoryAfterAction();
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
    stageStoreGeneralCount=result.apps.length;
    stageStoreInventorySummary(stageStorePilotCount,stageStoreGeneralCount);
    const holder=$("store-general-list");
    holder.replaceChildren();
    for (const entry of result.apps) {
      const row=document.createElement("div");
      const label=document.createElement("span");
      label.textContent=entry.app_id+" · "+(entry.running?"running":"stopped")+" · "+
        stageHealthLabel(entry.running,entry.health_status)+" · ";
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
            await updateUnifiedInventoryAfterAction();
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
    await updateUnifiedInventoryAfterAction();
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
    appstoreSelectionSync();
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
      " · strict single-service sandbox eligible "+c.eligible_for_isolated_staging+
      " · multi-service "+c.requires_multiservice_engine+
      " · advanced runtime "+c.advanced_runtime_options+
      " · unpinned images "+c.image_tag_not_pinned+
      " · volumes to resolve "+c.unsupported_volume_mapping+
      ". Not a runtime installation success count.";
  } catch(error) {
    $("store-general-coverage").textContent="Coverage unavailable: "+error.message;
  }
}


async function storeCompilerPreview(id) {
  compiledSelectedId=null;
  compiledPrepareId=null;
  $("compiled-install").disabled=true;
  $("compiled-prepare").disabled=true;
  if (!stageToken)return;
  $("appstore-compile-preview").textContent="Checking multi-service staging compatibility…";
  try {
    const response=await fetch(
      "/api/v1/stage/store-compile?id="+encodeURIComponent(id),
      {cache:"no-store",headers:{"Authorization":"Bearer "+stageToken}});
    const data=await response.json();
    if (!response.ok)throw Error(data.error||"Staging compiler unavailable");
    compiledSelectedId=data.all_images_cached===true ? id : null;
    compiledPrepareId=data.all_images_cached===false && data.sandbox_plan_supported===true ? id : null;
    $("compiled-install").disabled=!stageCanWrite||!compiledSelectedId;
    $("compiled-prepare").disabled=!stageCanWrite||!compiledPrepareId;
    if (data.migration_allowed!==false
        || data.nextcloud_user_data_inspected!==false
        || data.production_mutation_allowed!==false)
      throw Error("Invalid compiler safety scope");
    $("appstore-compile-preview").textContent=
      "Staging service plan: "+data.service_count+
      " services; start order: "+data.startup_order.join(" → ")+
      "; isolated volumes: "+data.stage_volume_count+
      "; immutable images cached: "+data.cached_immutable_images+
      "/"+data.service_count+
      ". Network: "+(data.outbound_network_pilot?
      "explicit MySpeed outbound pilot; private LAN is not separately firewalled":
      "internal-only")+
      ". Original ports, env and host bind sources discarded. "+
      "App runtime functionality not yet verified.";
  } catch(err) {
    $("appstore-compile-preview").textContent="Multi-service plan: "+err.message;
  }
}


// Multi-service App Store project lifecycle. Authorization lives on the API;
// control state here only improves the operator experience.
let compiledSelectedId=null;
let compiledPrepareId=null;
async function compiledApi(method,payload){
  if(!stageToken)throw Error("Authenticate to use the App Store");
  const opts={method,cache:"no-store",headers:{"Authorization":"Bearer "+stageToken}};
  if(payload){opts.headers["Content-Type"]="application/json";opts.body=JSON.stringify(payload);}
  const response=await fetch("/api/v1/stage/store-compiled",opts);
  const data=await response.json();
  if(!response.ok)throw Error(data.error || "Managed App Store unavailable ("+response.status+")");
  return data;
}
async function compiledRefresh(){
  try{
    const state=await compiledApi("GET");
    if(state.production_mutation_allowed!==false || state.migration_allowed!==false ||
       !state.capacity || !Number.isInteger(state.capacity.limit) ||
       !Number.isInteger(state.capacity.installed) ||
       state.capacity.available!==state.capacity.limit-state.capacity.installed ||
       !Number.isInteger(state.capacity.services_in_use) ||
       !Number.isInteger(state.capacity.service_limit) ||
       state.capacity.services_in_use<0 ||
       state.capacity.services_in_use>state.capacity.service_limit)
      throw Error("Invalid staging ownership or capacity declaration");
    const body=$("compiled-list");body.replaceChildren();
    for(const app of state.apps){
      const row=document.createElement("tr");
      cell(row,app.app_id+" · "+app.project);
      cell(row,app.services.map(x=>x.name+":"+(x.running?"running":
        (x.status==="exited"?"exited (code "+String(x.exit_code)+")":"stopped"))+
        " · "+(x.readiness||"not_verified").replaceAll("_"," ")+
        (x.depends_on&&x.depends_on.length?" ← "+x.depends_on.join("+"):"")).join(", "));
      const health=app.health_summary;
      if (!health || !health.counts || health.counts.total!==app.services.length ||
          !["running","stopped","partially_running"].includes(health.lifecycle) ||
          !["not_ready","not_verified","checking","healthcheck_passed","healthcheck_failed"].includes(health.readiness))
        throw Error("Invalid compiled multi-service health summary");
      cell(row,health.lifecycle.replaceAll("_"," ")+" · "+
        health.counts.running+"/"+health.counts.total+" running · "+
        health.readiness.replaceAll("_"," ")+
        (health.partial_failure?" · partial failure":"")+
        (app.health_inspection_only?" · credential provenance unverified; read-only":""));
      cell(row,String(app.revision)+(app.application_data_rollback?
        " · configuration + data rollback ready":" · no linked data rollback")+
        (app.outbound_network_pilot?
        " · outbound staging bridge (not LAN-isolated)":" · internal-only staging bridge")+
        (app.web_url?" · server loopback: "+app.web_url:""));
      const controls=document.createElement("td");
      const running=app.services.some(x=>x.running);
      const actions=app.online_data_recovery_pending?["recover-online"]:
        app.data_recovery_pending?["recover-data"]:
         running?["Backup + restart","stop","restart","update","rollback","uninstall"]:
                 ["start","update","rollback","checkpoint","uninstall"];
      for(const action of actions){
        controls.appendChild(stageButton(action,!stageCanWrite || app.health_inspection_only===true,
          ()=>compiledAct(action==="Backup + restart"?"backup-online":action,app.project)));
      }
      if((app.app_id==="default:MySpeed" || app.app_id==="casaos.app:org.icewhale.qui")
         && app.stage_browser_app===true
         && app.all_running && !app.data_recovery_pending
         && !app.health_inspection_only){
        controls.appendChild(stageButton("Open app",!stageCanWrite,
          ()=>compiledOpenWeb(app.project)));
      }
      if(!app.data_recovery_pending && !app.online_data_recovery_pending){
        for(const snapshot of (app.data_checkpoints||[])){
          controls.appendChild(stageButton("Restore + restart "+snapshot,
            !stageCanWrite || app.health_inspection_only===true,
            ()=>compiledAct("restore-online",app.project,snapshot)));
          controls.appendChild(stageButton("Delete backup "+snapshot,
            !stageCanWrite || app.health_inspection_only===true,
            ()=>compiledAct("delete-checkpoint",app.project,snapshot)));
        }
      }
      if(!running && !app.data_recovery_pending && !app.online_data_recovery_pending){
        for(const snapshot of (app.data_checkpoints||[])){
          controls.appendChild(stageButton("Restore "+snapshot,
            !stageCanWrite || app.health_inspection_only===true,
            ()=>compiledAct("restore-data",app.project,snapshot)));
        }
      }
      row.appendChild(controls);body.appendChild(row);
    }
    if (!Array.isArray(state.unavailable_projects))
      throw Error("Invalid compiled protected staging project list");
    for (const restrictedProject of state.unavailable_projects) {
      if (restrictedProject.reason!=="protected_stage_credentials" ||
          typeof restrictedProject.project!=="string")
        throw Error("Invalid compiled protected project");
      const row=document.createElement("tr");
      cell(row,restrictedProject.project);
      cell(row,"Protected staging credentials");
      cell(row,"Restricted — cannot verify health");
      cell(row,"—");
      cell(row,"—");
      body.appendChild(row);
    }
    for(const project of state.pending_recovery){
      const row=document.createElement("tr");
      cell(row,project);cell(row,"Recovery required");
      cell(row,"Recovery required");cell(row,"—");
      const controls=document.createElement("td");
      controls.appendChild(stageButton("Recover",!stageCanWrite,()=>compiledAct("recover",project)));
      row.appendChild(controls);body.appendChild(row);
    }
    $("compiled-status").textContent=state.apps.length+" readable managed project(s); "+
      state.capacity.installed+"/"+state.capacity.limit+" staging slots; "+
      state.capacity.services_in_use+"/"+state.capacity.service_limit+
      " isolated service budget in use; "+
      state.unavailable_projects.length+" restricted; "+
      state.pending_recovery.length+" pending recovery; "+
      (state.unregistered_stage_directories||[]).length+
      " unregistered staging directorie(s). Image/config rollback only; not database contents.";
    $("compiled-refresh").disabled=false;
  }catch(err){$("compiled-status").textContent="Managed store: "+err.message;}
}
async function compiledOpenWeb(project){
  if(!stageToken||!stageCanWrite)return;
  $("compiled-status").textContent="Authorizing isolated staging app browser…";
  try{
    const response=await fetch("/api/v1/stage/app-web-session",{
      method:"POST",cache:"no-store",
      headers:{"Authorization":"Bearer "+stageToken,"Content-Type":"application/json"},
      body:JSON.stringify({project})
    });
    const result=await response.json();
    if(!response.ok)throw Error(result.error||"Staging app access failed");
    if(result.production_mutation_allowed!==false ||
       !["authenticated_myspeed_stage_only","authenticated_qui_stage_only"].includes(result.scope) ||
       typeof result.entry!=="string" || !result.entry.startsWith("/stage-app/"+project+"/"))
       throw Error("Unexpected staging app gateway scope");
    window.location.assign(result.entry);
  }catch(err){$("compiled-status").textContent="Cannot open app: "+err.message;}
}
async function compiledAct(action,project,checkpoint){
  if(["uninstall","rollback","recover","recover-data","restore-data","restore-online","recover-online","delete-checkpoint"].includes(action) &&
     !confirm(action+" "+project+"? This only affects the isolated staging project."))return;
  $("compiled-status").textContent="Running "+action+" on staging "+project+"…";
  try{
    await compiledApi("POST",checkpoint?{action,project,checkpoint}:{action,project});
    await compiledRefresh();
    await updateUnifiedInventoryAfterAction();
  }catch(err){$("compiled-status").textContent=action+" failed: "+err.message;}
}
$("compiled-install").addEventListener("click",async()=>{
  const app=compiledSelectedId;
  if(!app || !stageCanWrite)return;
  if(!confirm("Install "+app+" as a new staging-owned multi-service project? This does not install into CasaOS."))return;
  $("compiled-install").disabled=true;
  $("compiled-status").textContent="Installing "+app+" in staging…";
  try{
    await compiledApi("POST",{action:"install",id:app});
    await compiledRefresh();
    await updateUnifiedInventoryAfterAction();
  }catch(err){$("compiled-status").textContent="Install failed: "+err.message;}
  finally{$("compiled-install").disabled=!stageCanWrite||!compiledSelectedId;}
});
$("compiled-refresh").addEventListener("click",compiledRefresh);


$("compiled-prepare").addEventListener("click",async()=>{
  const app=compiledPrepareId;
  if(!app||!stageCanWrite)return;
  if(!confirm("Prepare the catalogue images for "+app+" in the Docker cache? "+
              "This downloads images, but does not install or run them."))return;
  $("compiled-prepare").disabled=true;
  $("compiled-status").textContent="Preparing immutable image cache for "+app+"…";
  try{
    const result=await compiledApi("POST",{action:"prepare",id:app});
    $("compiled-status").textContent="Prepared "+result.prepared_images+" image(s). "+
                                  "Select the app to confirm readiness.";
    await storeCompilerPreview(app);
    appstoreSelectionSync();
  }catch(err){$("compiled-status").textContent="Image preparation failed: "+err.message;}
  finally{$("compiled-prepare").disabled=!stageCanWrite||!compiledPrepareId;}
});

appstoreRefresh();
