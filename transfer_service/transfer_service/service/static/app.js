const $ = (id) => document.getElementById(id);

function stdToast(msg, kind="ok"){
  const el = $("stdToast");
  if(!el) { console.log(msg); return; }
  el.textContent = msg;
  el.classList.remove("hidden");
  el.classList.toggle("toast-err", kind==="err");
  el.classList.toggle("toast-ok", kind!=="err");
  clearTimeout(stdToast._t);
  stdToast._t = setTimeout(() => el.classList.add("hidden"), 1800);
}

function apiBase(){
  return ($("serverUrl").value || "http://127.0.0.1:8000").replace(/\/+$/,'');
}

function setStatus(status){
  $("txtStatus").textContent = status;
  const dot = $("dotStatus");
  if(status === "running" || status === "started"){
    dot.style.background = "#22c55e";
  }else if(status === "done"){
    dot.style.background = "#16a34a";
  }else if(status === "error"){
    dot.style.background = "#ef4444";
  }else{
    dot.style.background = "#94a3b8";
  }
}

async function loadStandards(){
  const base = apiBase();
  const r = await fetch(base + "/api/standards");
  if(!r.ok) throw new Error("Failed to load standards");
  standardsData = await r.json();
  populateRefSelects();
}

function optionLabel(level, id, s){
  const v = (s && s.value_V != null) ? s.value_V : "";
  const ch = (s && s.channel != null) ? s.channel : "";
  return `${id}  (ch${ch}, ${v} V)`;
}

function populateRefSelect(selectEl, level){
  selectEl.innerHTML = "";
  const items = (standardsData && standardsData[level]) ? standardsData[level] : {};
  const keys = Object.keys(items);
  if(!keys.length){
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No standards";
    selectEl.appendChild(opt);
    return;
  }
  // keep previous selection if possible
  const prev = selectEl.value;
  keys.sort().forEach(id => {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = optionLabel(level, id, items[id]);
    selectEl.appendChild(opt);
  });
  if(prev && keys.includes(prev)) selectEl.value = prev;
  else{
    // choose first active if exists
    const firstActive = keys.find(k => items[k] && items[k].active);
    selectEl.value = firstActive || keys[0];
  }
}

function applySelectedStandard(level){
  if(!standardsData) return;
  if(level === "10V"){
    const id = $("ref10Select").value;
    const s = (standardsData["10V"]||{})[id];
    $("ref10Ch").value = s ? s.channel : "";
    $("ref10Val").value = s ? s.value_V : "";
    $("ref10U").value = s ? s.u_ref_V : "";
  }else{
    const id = $("ref1018Select").value;
    const s = (standardsData["1.018V"]||{})[id];
    $("ref1018Ch").value = s ? s.channel : "";
    $("ref1018Val").value = s ? s.value_V : "";
    $("ref1018U").value = s ? s.u_ref_V : "";
  }
}

function populateRefSelects(){
  populateRefSelect($("ref10Select"), "10V");
  populateRefSelect($("ref1018Select"), "1.018V");
  applySelectedStandard("10V");
  applySelectedStandard("1.018V");
}


async function openStandardsModal(){
  const base = apiBase();
  const r = await fetch(base + "/api/standards");
  const data = await r.json();
  standardsData = data || {};
  // default structures
  standardsData["10V"] = standardsData["10V"] || {};
  standardsData["1.018V"] = standardsData["1.018V"] || {};
  $("standardsJson").value = JSON.stringify(standardsData, null, 2);

  // default level selection
  if(!$("stdLevel").value) $("stdLevel").value = "10V";
  renderStandardsTable();
  hideStdEditor();

  // default tab = table
  setStandardsTab("table");

  $("modalStandards").classList.remove("hidden");
}

function closeStandardsModal(){
  $("modalStandards").classList.add("hidden");
  hideStdEditor();
}

function setStandardsTab(which){
  const tTable = $("tabStdTable");
  const tJson = $("tabStdJson");
  const pTable = $("stdTablePane");
  const pJson = $("stdJsonPane");

  if(which === "json"){
    tTable.classList.remove("tab-active");
    tJson.classList.add("tab-active");
    pTable.style.display = "none";
    pJson.style.display = "block";
    // keep JSON up-to-date
    $("standardsJson").value = JSON.stringify(standardsData || {}, null, 2);
  }else{
    tJson.classList.remove("tab-active");
    tTable.classList.add("tab-active");
    pJson.style.display = "none";
    pTable.style.display = "block";
    renderStandardsTable();
  }
}

function currentStdLevel(){
  return $("stdLevel").value || "10V";
}

function stdLevelObj(level){
  if(!standardsData) standardsData = {};
  standardsData[level] = standardsData[level] || {};
  return standardsData[level];
}

function renderStandardsTable(){
  const level = currentStdLevel();
  const obj = stdLevelObj(level);

  const ids = Object.keys(obj).sort((a,b)=>a.localeCompare(b, undefined, {numeric:true}));
  const tbody = $("stdTableBody");
  tbody.innerHTML = "";

  for(const id of ids){
    const s = obj[id] || {};
    const tr = document.createElement("tr");

    const active = (s.active === undefined) ? true : !!s.active;

    tr.innerHTML = `
      <td><code>${escapeHtml(id)}</code></td>
      <td>${safeNum(s.channel)}</td>
      <td>${safeNum(s.value_V)}</td>
      <td>${safeNum(s.u_ref_V)}</td>
      <td>${escapeHtml(s.description || "")}</td>
      <td>${escapeHtml(s.cal_date || "")}</td>
      <td>${active ? "true" : "false"}</td>
      <td>
        <button class="btn btn-small" data-act="edit" data-id="${escapeAttr(id)}">Edit</button>
        <button class="btn btn-small btn-danger" data-act="del" data-id="${escapeAttr(id)}">Delete</button>
      </td>
    `;
    tbody.appendChild(tr);
  }

  // bind row actions
  tbody.querySelectorAll("button[data-act]").forEach(btn=>{
    btn.addEventListener("click", ()=>{
      const act = btn.getAttribute("data-act");
      const id = btn.getAttribute("data-id");
      if(act === "edit") openStdEditor("edit", id);
      if(act === "del") deleteStandard(id);
    });
  });
}

function safeNum(v){
  if(v === null || v === undefined) return "";
  if(typeof v === "number") return v;
  const n = Number(v);
  return Number.isFinite(n) ? n : "";
}

function escapeHtml(s){
  return String(s)
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#39;");
}
function escapeAttr(s){ return escapeHtml(s); }

let stdEditorMode = null; // "add"|"edit"
let stdEditorId = null;

function openStdEditor(mode, id=null){
  stdEditorMode = mode;
  stdEditorId = id;

  const level = currentStdLevel();
  const obj = stdLevelObj(level);

  $("stdEditor").style.display = "block";
  $("stdEditorTitle").textContent = (mode === "add") ? `Add standard (${level})` : `Edit standard (${level})`;

  if(mode === "add"){
    $("stdId").value = "";
    $("stdId").disabled = false;
    $("stdCh").value = "";
    $("stdValue").value = "";
    $("stdUref").value = "";
    $("stdDesc").value = "";
    $("stdCalDate").value = "";
    $("stdActive").value = "true";
  }else{
    const s = obj[id] || {};
    $("stdId").value = id;
    $("stdId").disabled = true;
    $("stdCh").value = (s.channel ?? "");
    $("stdValue").value = (s.value_V ?? "");
    $("stdUref").value = (s.u_ref_V ?? "");
    $("stdDesc").value = (s.description ?? "");
    $("stdCalDate").value = (s.cal_date ?? "");
    $("stdActive").value = ((s.active === undefined) ? true : !!s.active) ? "true" : "false";
  }
}

function hideStdEditor(){
  $("stdEditor").style.display = "none";
  stdEditorMode = null;
  stdEditorId = null;
}

function applyStdEditor(){
  const level = currentStdLevel();
  const obj = stdLevelObj(level);

  const id = $("stdId").value.trim();
  const channel = Number($("stdCh").value);
  const valueV = Number($("stdValue").value);
  const urefV = Number($("stdUref").value);
  const desc = $("stdDesc").value.trim();
  const calDate = $("stdCalDate").value;
  const active = $("stdActive").value === "true";

  if(!id) { alert("ID is required"); return; }
  if(!Number.isFinite(channel) || channel <= 0){ alert("Channel must be a positive number"); return; }
  if(!Number.isFinite(valueV)){ alert("Value (V) must be a number"); return; }
  if(!Number.isFinite(urefV) || urefV <= 0){ alert("u(ref) (V) must be > 0"); return; }

  if(stdEditorMode === "add"){
    if(obj[id]){ alert("ID already exists at this level"); return; }
    obj[id] = {};
  }
  obj[id] = {
    channel: channel,
    value_V: valueV,
    u_ref_V: urefV,
    description: desc || "",
    cal_date: calDate || "",
    active: active
  };

  $("standardsJson").value = JSON.stringify(standardsData || {}, null, 2);
  hideStdEditor();
  renderStandardsTable();
  // also refresh selects on main page
  try{ populateRefSelects(); }catch(e){}
}

function deleteStandard(id){
  const level = currentStdLevel();
  const obj = stdLevelObj(level);
  if(!obj[id]) return;
  if(!confirm(`Delete ${id} from ${level}?`)) return;
  delete obj[id];
  $("standardsJson").value = JSON.stringify(standardsData || {}, null, 2);
  hideStdEditor();
  renderStandardsTable();
  try{ populateRefSelects(); }catch(e){}
}

async function saveStandardsAll(){
  const base = apiBase();
  const r = await fetch(base + "/api/standards", {
    method: "PUT",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(standardsData || {})
  });
  if(!r.ok){
    const t = await r.text();
    stdToast("Save failed: " + t, "err");
    return;
  }
  stdToast("Saved.");
  // ensure main selects use latest server copy (in case server normalizes)
  await loadStandards();
}

async function saveStandardsFromModal(){
  // Advanced JSON Save
  const base = apiBase();
  let data;
  try{
    data = JSON.parse($("standardsJson").value);
  }catch(e){
    stdToast("JSON error: " + e.message, "err");
    return;
  }
  const r = await fetch(base + "/api/standards", {
    method: "PUT",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(data)
  });
  if(!r.ok){
    const t = await r.text();
    stdToast("Save failed: " + t, "err");
    return;
  }
  standardsData = data;
  standardsData["10V"] = standardsData["10V"] || {};
  standardsData["1.018V"] = standardsData["1.018V"] || {};
  stdToast("Saved.");
  await loadStandards();
  renderStandardsTable();
}

function dutRowTemplate(level, idx){
  const row = document.createElement("div");
  row.className = "dut-row";
  row.dataset.level = level;
  row.innerHTML = `
    <div>
      <label>DUT id</label>
      <input class="dut-id" placeholder="DUT${level}-${idx}" />
    </div>
    <div>
      <label>ch</label>
      <input class="dut-ch" placeholder="1..32" />
    </div>
    <div style="align-self:end">
      <button class="btn btn-small trash" title="Удалить">🗑</button>
    </div>
  `;
  row.querySelector(".trash").addEventListener("click", () => row.remove());
  return row;
}

function addDut(level){
  const list = level === "10" ? $("dut10List") : $("dut1018List");
  const idx = list.children.length + 1;
  list.appendChild(dutRowTemplate(level, idx));
}

function collectDuts(listEl){
  const duts = [];
  listEl.querySelectorAll(".dut-row").forEach(r => {
    const id = r.querySelector(".dut-id").value.trim();
    const ch = parseInt(r.querySelector(".dut-ch").value.trim(), 10);
    if(id && Number.isFinite(ch)) duts.push({id, channel: ch});
  });
  return duts;
}

function collectPayload(){
  const cellType = $("cellType").value;
  const alpha = (cellType === "unsaturated") ? parseFloat($("alphaUV").value) : null;

  const levels = [];

  const duts10 = collectDuts($("dut10List"));
  if(duts10.length){
    levels.push({
      name: "10V",
      ref: {
        id: $("ref10Select").value,
        channel: parseInt($("ref10Ch").value, 10),
        value_v: parseFloat($("ref10Val").value),
        u_std_v: parseFloat($("ref10U").value),
      },
      duts: duts10,
      cell_type: cellType,
      alpha_uV_per_C: alpha,
    });
  }

  const duts1018 = collectDuts($("dut1018List"));
  if(duts1018.length){
    levels.push({
      name: "1.018V",
      ref: {
        id: $("ref1018Select").value,
        channel: parseInt($("ref1018Ch").value, 10),
        value_v: parseFloat($("ref1018Val").value),
        u_std_v: parseFloat($("ref1018U").value),
      },
      duts: duts1018,
      cell_type: cellType,
      alpha_uV_per_C: alpha,
    });
  }

  const sim = $("simEnable").checked;

  const blockEl = document.getElementById('block');
  const delayEl = document.getElementById('delay');
  const block_s = blockEl ? parseFloat(blockEl.value) : 180.0;
  const delay_s = delayEl ? parseFloat(delayEl.value) : 0.0;

  // IMPORTANT: keys must match StartRequest in service/server.py
  return {
    meter_resource: $("meterRes").value.trim(),
    switch_resource: $("switchRes").value.trim(),
    lte_port: $("ltePort").value.trim(),
    cycles: parseInt($("cycles").value,10),
    settle_after_switch_s: parseFloat($("settle").value),
    block_s,
    delay_s,
    samples_per_polarity: parseInt($("samplesPerPol").value, 10),
    delay_between_samples_s: parseFloat($("sampleDelay").value),
    levels,
    simulate: sim,
    sim_offset_uV: parseFloat($("simOffset").value),
    sim_noise_uV_RMS: parseFloat($("simNoise").value),
    sim_drift_uV_per_min: parseFloat($("simDrift").value),
    sim_outlier_prob: parseFloat($("simOutP").value),
    sim_outlier_uV: parseFloat($("simOutU").value),
    sim_temp_C: parseFloat($("simTemp").value),
  };
}

let standardsData = null;

let currentJobId = null;
let pollTimer = null;
let envTimer = null;

async function startJob(){
  const base = apiBase();
  const payload = collectPayload();

  if(!payload.levels.length){
    alert("Нет DUT для измерения. Добавь хотя бы один DUT в 10V или 1.018V.");
    return;
  }

  $("btnStart").disabled = true;
  $("btnStart").classList.remove("btn-primary");
  $("btnStart").classList.add("btn-danger");
  $("btnStart").textContent = "⏳ Running...";
  $("btnRefreshFiles").disabled = true;
  $("btnZip").disabled = true;
  $("filesList").textContent = "—";
  $("jobMsg").textContent = "starting...";
  $("jobId").textContent = "—";
  setStatus("started");
  setProgress(0);

  try{
    const r = await fetch(`${base}/start`, {
      method:"POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(payload),
    });
    if(!r.ok) throw new Error(await r.text());
    const j = await r.json();
    currentJobId = j.job_id;
    $("jobId").textContent = currentJobId;
    pollStatus();
    if(pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollStatus, 1000);
  }catch(e){
    $("btnStart").disabled = false;
    setStatus("error");
    $("jobMsg").textContent = `start error: ${e}`;
    alert(`Start error: ${e}`);
  }
}

function setProgress(pct){
  const p = Math.max(0, Math.min(100, pct));
  $("barIn").style.width = `${p}%`;
  $("pct").textContent = `${p.toFixed(0)}%`;
}

async function pollStatus(){
  if(!currentJobId) return;
  const base = apiBase();
  try{
    const r = await fetch(`${base}/status/${currentJobId}`);
    if(!r.ok) throw new Error(await r.text());
    const j = await r.json();
    setStatus(j.status || "—");
    $("jobMsg").textContent = j.message || "—";
    setProgress((j.progress || 0) * 100);

    if(j.status === "done" || j.status === "error"){
      $("btnStart").disabled = false;
      $("btnStart").classList.remove("btn-danger");
      $("btnStart").classList.add("btn-primary");
      $("btnStart").textContent = "▶ Start transfer";
      $("btnRefreshFiles").disabled = false;
      $("btnZip").disabled = false;
      if(pollTimer) { clearInterval(pollTimer); pollTimer = null; }
      await refreshFiles();
    }
  }catch(e){
    $("jobMsg").textContent = `poll error: ${e}`;
  }
}

async function refreshEnv(){
  const base = apiBase();
  try{
    const r = await fetch(`${base}/env`);
    if(!r.ok) return;
    const e = await r.json();
    $("envT").textContent = e.t_c == null ? "—" : Number(e.t_c).toFixed(2);
    $("envRH").textContent = e.rh_pct == null ? "—" : Number(e.rh_pct).toFixed(1);
    $("envP").textContent = e.p_kpa == null ? "—" : Number(e.p_kpa).toFixed(2);
    $("envLTE").textContent = e.lte_c == null ? "—" : Number(e.lte_c).toFixed(2);
  }catch(_e){}
}

async function refreshFiles(){
  if(!currentJobId) return;
  const base = apiBase();
  $("filesList").textContent = "loading...";
  try{
    const r = await fetch(`${base}/list/${currentJobId}`);
    if(!r.ok) throw new Error(await r.text());
    const j = await r.json();
    const files = j.files || [];
    if(!files.length){
      $("filesList").textContent = "Файлов нет.";
      return;
    }
    const box = document.createElement("div");
    box.className = "files-list";
    files.forEach(fn => {
      const ext = fn.endsWith(".xlsx") ? "XLSX" : (fn.endsWith(".csv") ? "CSV" : "FILE");
      const item = document.createElement("div");
      item.className = "file-item";
      const a = document.createElement("a");
      a.href = `${base}/file/${currentJobId}/${encodeURIComponent(fn)}`;
      a.textContent = fn;
      a.target = "_blank";
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = ext;
      item.appendChild(a);
      item.appendChild(badge);
      box.appendChild(item);
    });
    $("filesList").innerHTML = "";
    $("filesList").appendChild(box);
  }catch(e){
    $("filesList").textContent = `list error: ${e}`;
  }
}

function downloadZip(){
  if(!currentJobId) return;
  const base = apiBase();
  window.open(`${base}/zip/${currentJobId}`, "_blank");
}

function init(){

  // DUT list initially EMPTY

  $("addDut10").addEventListener("click", () => addDut("10"));
  $("addDut1018").addEventListener("click", () => addDut("1018"));

  $("btnStart").addEventListener("click", startJob);
  $("btnDocs").addEventListener("click", () => window.open(`${apiBase()}/docs`, "_blank"));

  $("btnStandards").addEventListener("click", window.openStandardsModal);
  $("btnStandardsClose").addEventListener("click", window.closeStandardsModal);
  $("btnStandardsSave").addEventListener("click", window.saveStandardsFromModal);
  $("btnStandardsReload").addEventListener("click", window.openStandardsModal);

  $("tabStdTable").addEventListener("click", () => setStandardsTab("table"));
  $("tabStdJson").addEventListener("click", () => setStandardsTab("json"));
  $("stdLevel").addEventListener("change", () => { hideStdEditor(); renderStandardsTable(); });
  $("btnStdAdd").addEventListener("click", () => openStdEditor("add"));
  $("btnStdSaveAll").addEventListener("click", saveStandardsAll);
  $("btnStdReload").addEventListener("click", window.openStandardsModal);
  $("btnStdCancel").addEventListener("click", hideStdEditor);
  $("btnStdApply").addEventListener("click", applyStdEditor);

  $("ref10Select").addEventListener("change", () => applySelectedStandard("10V"));
  $("ref1018Select").addEventListener("change", () => applySelectedStandard("1.018V"));

  loadStandards().catch(err => {
    console.error(err);
    alert("Cannot load standards from server. Check Server URL and that service is running.");
  });

  $("btnRefreshFiles").addEventListener("click", refreshFiles);
  $("btnZip").addEventListener("click", downloadZip);

  $("simEnable").addEventListener("change", () => {
    $("simBox").classList.toggle("hidden", !$("simEnable").checked);
  });

  setStatus("idle");
  refreshEnv();
  envTimer = setInterval(refreshEnv, 1500);
}
document.addEventListener("DOMContentLoaded", init);
