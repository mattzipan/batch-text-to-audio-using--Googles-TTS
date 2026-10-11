"use strict";

const $ = (id) => document.getElementById(id);
const RECENT_KEY = "wordtape_recent";
const SAMPLE_FALLBACK = "Selamat pagi. Ini contoh suara.";

const state = { project: null, rows: [], track: null };
let screen = "words";
let jobRunning = false;
let currentJobId = null;
let pollTimer = null;
let pendingDeleteId = null;
let editingRowId = null;
let unchecked = new Set();
let testBlobUrl = null;

function toast(message) {
  const box = $("toasts");
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = message;
  box.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

async function api(path, opts) {
  const method = (opts && opts.method) || "GET";
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: opts && opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  let data = null;
  try {
    data = await res.json();
  } catch (err) {
    data = null;
  }
  if (!res.ok) {
    const detail = (data && data.detail) || ("request failed with " + res.status);
    if (res.status === 401 || res.status === 403 || res.status >= 500) {
      toast("Oof — the API said no. Check the key?");
    } else {
      toast(String(detail));
    }
    throw new Error(String(detail));
  }
  return data;
}

function fmtDur(totalS) {
  const total = Math.max(0, Math.round(totalS));
  const m = Math.floor(total / 60);
  const r = total % 60;
  return m > 0 ? m + "m " + r + "s" : r + "s";
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

// Mirrors app.costs.fmt_est: 4 decimals under $0.01, else 2 — always an
// estimate ("~$…"), never a final cost.
function fmtEst(usd) {
  const n = Number(usd);
  return n < 0.01 ? "~$" + n.toFixed(4) : "~$" + n.toFixed(2);
}

function estSuffix(usd) {
  return " (" + fmtEst(usd) + " est.)";
}

// Generate-job completion toast (spec F11): fires only when the server
// reported a known estimate — without one, today's silent behavior stands.
function toastBaked(job) {
  if (job.error || job.cancelled || job.cost_est == null) return;
  const n = job.done;
  toast("Baked " + n + (n === 1 ? " clip" : " clips") + estSuffix(job.cost_est));
}

function monthLabel(key) {
  const m = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(String(key));
  if (!m) return String(key);
  return MONTH_NAMES[Number(m[2]) - 1] + " " + m[1];
}

function loadRecent() {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    const list = raw ? JSON.parse(raw) : [];
    return Array.isArray(list) ? list.filter((x) => typeof x === "string") : [];
  } catch (err) {
    return [];
  }
}

function saveRecent(path) {
  const list = loadRecent().filter((x) => x !== path);
  list.unshift(path);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 8)));
  } catch (err) {
    /* storage full or blocked: recent list is best-effort */
  }
  renderRecent();
}

function renderRecent() {
  const box = $("recentList");
  box.textContent = "";
  const list = loadRecent();
  if (list.length === 0) {
    const hint = document.createElement("span");
    hint.className = "hint";
    hint.textContent = "Nothing here yet — open a project to pin it.";
    box.appendChild(hint);
    return;
  }
  list.forEach((path) => {
    const btn = document.createElement("button");
    btn.className = "btn btn-ghost btn-sm";
    btn.type = "button";
    btn.textContent = path;
    btn.addEventListener("click", () => {
      $("openPath").value = path;
      doOpen();
    });
    box.appendChild(btn);
  });
}

const ORDER = ["words", "voice", "bake"];

function goto(name) {
  screen = name;
  const sections = document.querySelectorAll("section[data-screen]");
  sections.forEach((el) => {
    el.hidden = el.getAttribute("data-screen") !== name;
  });
  const btns = [$("stepWords"), $("stepVoice"), $("stepBake")];
  const nums = [$("numWords"), $("numVoice"), $("numBake")];
  const cur = ORDER.indexOf(name);
  btns.forEach((btn, i) => {
    const li = btn.parentElement;
    li.classList.toggle("current", i === cur);
    li.classList.toggle("done", i < cur);
    nums[i].classList.toggle("pulse", i === cur);
  });
  if (name === "bake") {
    updateEstimate();
  }
  if (name === "settings") {
    loadSettings();
  }
}

async function refresh() {
  const data = await api("/api/state");
  state.project = data.project;
  state.rows = data.rows || [];
  state.track = data.track || null;
  render();
}

function render() {
  renderTopbar();
  renderRecent();
  renderRows();
  renderVoice();
  renderBake();
}

function renderTopbar() {
  $("projectName").textContent = state.project ? state.project.name : "no project open";
  $("dirtyDot").hidden = !jobRunning;
}

function needProject() {
  if (!state.project) {
    toast("Create or open a project first.");
    return false;
  }
  return true;
}

/* ---------- words ---------- */

function statusChip(status) {
  const el = document.createElement("span");
  el.className = "chip";
  if (status === "ok") el.className = "chip chip-ok";
  else if (status === "stale") el.className = "chip chip-stale";
  else if (status === "error") el.className = "chip chip-error";
  else if (status === "pending") el.className = "chip chip-pending";
  else if (status === "generating") el.className = "chip chip-generating pulse";
  el.textContent = status;
  return el;
}

function styleChip(style) {
  const el = document.createElement("span");
  el.className = "chip chip-main";
  if (style === "formal") el.className = "chip chip-formal";
  else if (style === "informal") el.className = "chip chip-informal";
  el.textContent = style;
  return el;
}

function rowRollup(row) {
  const stats = row.variants.map((v) => v.status);
  if (stats.includes("error")) return "error";
  if (stats.includes("stale")) return "stale";
  if (stats.includes("generating")) return "generating";
  if (stats.includes("pending")) return "pending";
  return "ok";
}

function ghostBtn(label) {
  const btn = document.createElement("button");
  btn.className = "btn btn-ghost btn-sm";
  btn.type = "button";
  btn.textContent = label;
  return btn;
}

function renderRows() {
  const table = $("rowsTable");
  table.textContent = "";
  const heads = ["#", "Source", "Translations", "Status", "Actions"];
  heads.forEach((h) => {
    const cell = document.createElement("div");
    cell.className = "row-head";
    cell.textContent = h;
    table.appendChild(cell);
  });
  if (state.rows.length === 0) {
    const cell = document.createElement("div");
    cell.className = "empty-state";
    cell.textContent = "Nothing to drill yet.";
    table.appendChild(cell);
    for (let i = 0; i < 4; i++) table.appendChild(document.createElement("div"));
  }
  state.rows.forEach((row) => {
    const pos = document.createElement("div");
    pos.className = "mono";
    pos.textContent = String(row.position);
    table.appendChild(pos);

    const src = document.createElement("div");
    if (editingRowId === row.id) {
      const input = document.createElement("input");
      input.type = "text";
      input.setAttribute("data-f", "source");
      input.value = row.source;
      input.setAttribute("aria-label", "Source text");
      src.appendChild(input);
    } else {
      src.textContent = row.source;
    }
    table.appendChild(src);

    const trans = document.createElement("div");
    if (editingRowId === row.id) {
      row.variants.forEach((v) => {
        const wrap = document.createElement("div");
        wrap.appendChild(styleChip(v.style));
        const input = document.createElement("input");
        input.type = "text";
        input.setAttribute("data-f", v.id);
        input.value = v.text;
        input.setAttribute("aria-label", v.style + " translation");
        wrap.appendChild(input);
        trans.appendChild(wrap);
      });
    } else {
      row.variants.forEach((v) => {
        const wrap = document.createElement("div");
        wrap.appendChild(styleChip(v.style));
        const text = document.createElement("span");
        text.textContent = v.text || "—";
        wrap.appendChild(text);
        wrap.appendChild(statusChip(v.status));
        trans.appendChild(wrap);
      });
    }
    table.appendChild(trans);

    const st = document.createElement("div");
    st.appendChild(statusChip(rowRollup(row)));
    table.appendChild(st);

    const acts = document.createElement("div");
    acts.className = "row-actions";
    if (editingRowId === row.id) {
      const save = ghostBtn("Save");
      save.addEventListener("click", () => saveEdit(row));
      const cancel = ghostBtn("Cancel");
      cancel.addEventListener("click", () => {
        editingRowId = null;
        renderRows();
      });
      acts.appendChild(save);
      acts.appendChild(cancel);
    } else {
      const edit = ghostBtn("Edit");
      edit.addEventListener("click", () => {
        editingRowId = row.id;
        renderRows();
      });
      const regen = ghostBtn("↻");
      regen.title = "Regenerate audio for this row";
      regen.setAttribute("aria-label", "Regenerate audio for row " + row.position);
      regen.addEventListener("click", () => regenRow(row));
      const up = ghostBtn("↑");
      up.setAttribute("aria-label", "Move row " + row.position + " up");
      up.addEventListener("click", () => moveRow(row, "up"));
      const down = ghostBtn("↓");
      down.setAttribute("aria-label", "Move row " + row.position + " down");
      down.addEventListener("click", () => moveRow(row, "down"));
      const below = ghostBtn("+ Below");
      below.addEventListener("click", () => insertBelow(row));
      const del = ghostBtn("✕");
      del.setAttribute("aria-label", "Delete row " + row.position);
      del.addEventListener("click", () => {
        pendingDeleteId = row.id;
        $("modalBackdrop").hidden = false;
      });
      [edit, regen, up, down, below, del].forEach((b) => acts.appendChild(b));
    }
    table.appendChild(acts);
  });
  $("dropText").textContent =
    state.rows.length === 0
      ? "No words yet — drop a .txt or .csv here and let's cook."
      : state.rows.length + " rows loaded — drop another file to replace them.";
  $("translateBtn").disabled = jobRunning || !state.project;
}

async function saveEdit(row) {
  const table = $("rowsTable");
  const srcInput = table.querySelector('input[data-f="source"]');
  const edits = [];
  const inputs = table.querySelectorAll("input[data-f]");
  inputs.forEach((input) => {
    const key = input.getAttribute("data-f");
    if (key !== "source") edits.push({ id: key, text: input.value });
  });
  const updated = await api("/api/rows/" + row.id, {
    method: "PATCH",
    body: { source: srcInput ? srcInput.value : row.source, variants: edits },
  });
  editingRowId = null;
  await refresh();
  if (updated.variants.some((v) => v.status === "stale")) {
    toast("Row " + updated.position + " is stale — regenerate it.");
  }
}

async function regenRow(row) {
  if (!needProject()) return;
  const ids = row.variants.map((v) => v.id);
  const data = await api("/api/tts/generate", {
    method: "POST",
    body: { variant_ids: ids, force: true },
  });
  startPoll(data.job_id, "voice", async (job) => {
    await refresh();
    toastBaked(job);
  });
}

async function moveRow(row, direction) {
  await api("/api/rows/" + row.id + "/move", {
    method: "POST",
    body: { direction },
  });
  await refresh();
}

async function insertBelow(row) {
  const created = await api("/api/rows", {
    method: "POST",
    body: { after_row_id: row.id, source: "New term" },
  });
  editingRowId = created.id;
  await refresh();
}

async function doTranslate() {
  if (!needProject()) return;
  const data = await api("/api/translate", { method: "POST", body: {} });
  startPoll(data.job_id, "voice", async (job) => {
    await refresh();
    if (!job.error && !job.cancelled) {
      toast(
        "Translated " + job.done + " rows." +
          (job.cost_est != null ? estSuffix(job.cost_est) : "")
      );
    }
  });
}

async function doImport(file) {
  if (!needProject()) return;
  const name = file.name || "words.txt";
  const lower = name.toLowerCase();
  const kind = lower.endsWith(".csv") ? "csv" : "txt";
  const content = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });
  const data = await api("/api/project/import", {
    method: "POST",
    body: {
      filename: name,
      content,
      kind,
      has_header: $("hasHeader").checked,
    },
  });
  await refresh();
  toast("Imported " + data.imported + " rows.");
}

/* ---------- voice ---------- */

function selectedModel() {
  return $("modelSelect").value;
}

async function refreshVoices() {
  if (!state.project) {
    $("voiceSelect").textContent = "";
    return;
  }
  const keep = $("voiceSelect").value || state.project.voice;
  const qs = "model=" + encodeURIComponent(selectedModel()) + "&language=" + encodeURIComponent(state.project.target_lang);
  const voices = await api("/api/voices?" + qs);
  const sel = $("voiceSelect");
  sel.textContent = "";
  const groups = new Map();
  voices.forEach((v) => {
    const langs = v.languages && v.languages.length ? v.languages : ["Other"];
    const key = langs[0];
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(v);
  });
  const flat = voices.length === 0 ? [] : [...groups.entries()];
  if (flat.length === 0) {
    const opt = document.createElement("option");
    opt.value = keep;
    opt.textContent = keep;
    sel.appendChild(opt);
  }
  flat.forEach(([lang, list]) => {
    const group = document.createElement("optgroup");
    group.label = lang;
    list.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v.name;
      opt.textContent = v.gender ? v.name + " (" + v.gender + ")" : v.name;
      group.appendChild(opt);
    });
    sel.appendChild(group);
  });
  const names = voices.map((v) => v.name);
  sel.value = names.includes(keep) ? keep : names[0] || keep;
  if (!names.includes(sel.value) && names.length > 0) {
    await api("/api/project/settings", { method: "PATCH", body: { voice: sel.value } });
    await refresh();
    return;
  }
  if (state.project && sel.value !== state.project.voice && names.includes(sel.value)) {
    await api("/api/project/settings", { method: "PATCH", body: { voice: sel.value } });
    state.project.voice = sel.value;
  }
}

function firstTranslationText() {
  for (const row of state.rows) {
    for (const v of row.variants) {
      if ((v.status === "ok" || v.status === "pending") && v.text) return v.text;
    }
  }
  return null;
}

function renderVoice() {
  if (state.project) {
    if ($("modelSelect").value !== state.project.tts_model) {
      const known = [...$("modelSelect").options].map((o) => o.value);
      if (known.includes(state.project.tts_model)) {
        $("modelSelect").value = state.project.tts_model;
      }
    }
  }
  if (!$("sampleText").value) {
    $("sampleText").value = firstTranslationText() || SAMPLE_FALLBACK;
  }
  let n = 0;
  state.rows.forEach((row) =>
    row.variants.forEach((v) => {
      if (v.status === "pending" || v.status === "stale") n++;
    })
  );
  $("generateBtn").textContent = "Bake " + n + " clips";
  $("generateBtn").disabled = jobRunning || !state.project || (n === 0 && !$("forceRegen").checked);
}

async function testVoice() {
  if (!needProject()) return;
  const body = {
    voice: $("voiceSelect").value,
    model: selectedModel(),
    text: $("sampleText").value || SAMPLE_FALLBACK,
  };
  const res = await fetch("/api/voice/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = "voice test failed";
    try {
      detail = (await res.json()).detail || detail;
    } catch (err) {
      /* keep default */
    }
    toast(String(detail));
    return;
  }
  const blob = await res.blob();
  if (testBlobUrl) URL.revokeObjectURL(testBlobUrl);
  testBlobUrl = URL.createObjectURL(blob);
  const player = $("testAudio");
  player.src = testBlobUrl;
  player.hidden = false;
  player.play();
  // Estimate rides in a response header (spec F11); no header → no toast.
  const estRaw = res.headers.get("X-Est-Cost-USD");
  const est = Number(estRaw);
  if (estRaw != null && estRaw !== "" && Number.isFinite(est)) {
    toast("Sample ready" + estSuffix(est));
  }
}

async function generateAll() {
  if (!needProject()) return;
  const data = await api("/api/tts/generate", {
    method: "POST",
    body: { force: $("forceRegen").checked },
  });
  startPoll(data.job_id, "voice", async (job) => {
    await refresh();
    toastBaked(job);
  });
}

/* ---------- bake ---------- */

function checkedIncluded() {
  const boxes = document.querySelectorAll("input[data-inc]");
  const ids = [];
  boxes.forEach((box) => {
    if (box.checked) ids.push(box.getAttribute("data-inc"));
  });
  return ids;
}

function renderBake() {
  if (state.project) {
    if (document.activeElement !== $("repeatsInput")) {
      $("repeatsInput").value = String(state.project.repeats);
    }
    if (document.activeElement !== $("repeatGapInput")) {
      $("repeatGapInput").value = String(state.project.repeat_gap_s);
    }
    if (document.activeElement !== $("itemGapInput")) {
      $("itemGapInput").value = String(state.project.item_gap_s);
    }
  }
  const box = $("inclusionList");
  box.textContent = "";
  state.rows.forEach((row) => {
    row.variants.forEach((v) => {
      const key = row.id + ":" + v.id;
      const wrap = document.createElement("div");
      wrap.className = "switch-row";
      const sw = document.createElement("span");
      sw.className = "switch";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.setAttribute("data-inc", key);
      input.checked = !unchecked.has(key);
      input.setAttribute("aria-label", "Include row " + row.position + " " + v.style);
      input.addEventListener("change", () => {
        if (input.checked) unchecked.delete(key);
        else unchecked.add(key);
        updateEstimate();
      });
      const track = document.createElement("span");
      track.className = "track";
      sw.appendChild(input);
      sw.appendChild(track);
      wrap.appendChild(sw);
      const label = document.createElement("span");
      label.appendChild(styleChip(v.style));
      const text = document.createElement("span");
      text.textContent = "#" + row.position + " " + (v.text || row.source);
      label.appendChild(text);
      label.appendChild(statusChip(v.status));
      wrap.appendChild(label);
      box.appendChild(wrap);
    });
  });
  $("buildBtn").disabled = jobRunning || !state.project;
  const track = state.track;
  if (track && track.exists) {
    $("successCard").hidden = false;
    $("finalAudio").src = track.mp3_url;
    $("downloadMp3").href = track.mp3_url;
    $("downloadWav").href = track.wav_url;
    $("outputPath").textContent = track.output_dir || state.project.path;
    $("openFolderBtn").disabled = false;
    $("showMp3Btn").disabled = false;
  } else {
    $("successCard").hidden = true;
    $("openFolderBtn").disabled = true;
    $("showMp3Btn").disabled = true;
  }
}

async function updateEstimate() {
  if (!state.project) {
    $("estimate").textContent = "Estimate: —";
    return;
  }
  const okChecked = checkedIncluded().filter((key) => {
    const [rid, vid] = key.split(":");
    const row = state.rows.find((r) => r.id === rid);
    const v = row && row.variants.find((x) => x.id === vid);
    return v && v.status === "ok";
  });
  if (okChecked.length === 0) {
    $("estimate").textContent = "Estimate: 0s";
    return;
  }
  const qs = "?included=" + encodeURIComponent(okChecked.join(","));
  try {
    const data = await api("/api/track/estimate" + qs);
    $("estimate").textContent =
      data.duration_s === null || data.duration_s === undefined
        ? "Estimate: unavailable"
        : "Estimate: " + fmtDur(data.duration_s);
  } catch (err) {
    $("estimate").textContent = "Estimate: unavailable";
  }
}

async function buildTape() {
  if (!needProject()) return;
  const okChecked = checkedIncluded().filter((key) => {
    const [rid, vid] = key.split(":");
    const row = state.rows.find((r) => r.id === rid);
    const v = row && row.variants.find((x) => x.id === vid);
    return v && v.status === "ok";
  });
  const data = await api("/api/track/build", {
    method: "POST",
    body: { included: okChecked },
  });
  startPoll(data.job_id, "bake", async (job) => {
    await refresh();
    if (!job.error && !job.cancelled) {
      const dur = state.track && state.track.duration_s;
      toast("Tape is ready. " + (dur === null || dur === undefined ? "?" : fmtDur(dur)) + " of pure repetition.");
    }
  });
}

/* ---------- jobs ---------- */

function setBar(which, frac, message) {
  const bar = which === "voice" ? $("voiceProgress") : $("bakeProgress");
  const fill = which === "voice" ? $("voiceProgressFill") : $("bakeProgressFill");
  const text = which === "voice" ? $("voiceProgressText") : $("bakeProgressText");
  const pct = Math.round(Math.max(0, Math.min(1, frac)) * 100);
  fill.style.setProperty("--p", pct + "%");
  bar.classList.toggle("running", jobRunning);
  text.textContent = message || "";
}

function startPoll(jobId, which, onDone) {
  jobRunning = true;
  currentJobId = jobId;
  renderTopbar();
  renderRows();
  renderVoice();
  renderBake();
  const cancelBtn = which === "voice" ? $("cancelVoiceBtn") : $("cancelBakeBtn");
  cancelBtn.hidden = false;
  setBar(which, 0, "");
  let polls = 0;
  pollTimer = setInterval(async () => {
    polls++;
    let job;
    try {
      job = await api("/api/jobs/" + jobId);
    } catch (err) {
      return;
    }
    const frac = job.total > 0 ? job.done / job.total : 0;
    setBar(which, frac, job.message || "");
    const finished =
      job.error ||
      job.cancelled ||
      (job.total > 0 && job.done >= job.total) ||
      (polls >= 3 && job.message && job.done >= job.total);
    if (finished) {
      clearInterval(pollTimer);
      pollTimer = null;
      jobRunning = false;
      currentJobId = null;
      cancelBtn.hidden = true;
      setBar(which, job.error ? 0 : 1, job.message || "");
      if (job.error) toast(String(job.error));
      else if (job.cancelled) toast("Cancelled.");
      await onDone(job);
    }
  }, 500);
}

async function cancelJob() {
  if (!currentJobId) return;
  await api("/api/jobs/" + currentJobId + "/cancel", { method: "POST" });
}

/* ---------- project ---------- */

async function doNew() {
  const data = await api("/api/project/new", {
    method: "POST",
    body: {
      name: $("newName").value.trim(),
      source_lang: $("newSource").value,
      target_lang: $("newTarget").value,
      variants_enabled: $("variantsSwitch").checked,
    },
  });
  state.project = data.project;
  state.rows = data.rows || [];
  state.track = data.track || null;
  saveRecent(data.project.path);
  await refresh();
  await refreshVoices();
  toast("Created project " + data.project.name + ".");
}

async function doOpen() {
  const path = $("openPath").value.trim();
  if (!path) {
    toast("Type a project folder path first.");
    return;
  }
  const data = await api("/api/project/open", {
    method: "POST",
    body: { path },
  });
  state.project = data.project;
  state.rows = data.rows || [];
  state.track = data.track || null;
  saveRecent(data.project.path);
  await refresh();
  await refreshVoices();
}

/* ---------- settings ---------- */

async function loadSettings() {
  const data = await api("/api/settings");
  $("apiKeyStatus").textContent = data.has_key
    ? "Active key: " + (data.key_hint || "set")
    : "No API key found — save one below.";
  $("exportDefaultHint").textContent = "Default: " + data.export_default;
  if (document.activeElement !== $("exportRootInput")) {
    $("exportRootInput").value = data.export_root || "";
  }
  await loadCosts();
}

async function loadCosts() {
  let data;
  try {
    data = await api("/api/costs");
  } catch (err) {
    return;
  }
  const currentEl = $("costsCurrent");
  const tableEl = $("costsTable");
  const noteEl = $("costsNote");
  tableEl.textContent = "";
  noteEl.textContent =
    "Estimates only — check AI Studio Billing for actual charges. " +
    "Introductory TTS pricing ends Dec 31, 2026; rates double Jan 1, 2027.";
  const history = Array.isArray(data.history) ? data.history : [];
  if (history.length === 0) {
    currentEl.hidden = true;
    currentEl.textContent = "";
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No API calls recorded yet.";
    tableEl.appendChild(empty);
    return;
  }
  const current = data.current || {};
  currentEl.hidden = false;
  currentEl.textContent =
    monthLabel(data.current_month) + ": " + fmtEst(current.total_usd || 0) +
    " est. (translate " + fmtEst(current.translate_usd || 0) +
    " + voice " + fmtEst(current.tts_usd || 0) +
    ", " + (current.calls || 0) + " calls)";
  ["Month", "Translate", "Voice", "Total", "Calls"].forEach((h) => {
    const cell = document.createElement("div");
    cell.className = "row-head";
    cell.textContent = h;
    tableEl.appendChild(cell);
  });
  history.forEach((row) => {
    const isCurrent = row.month === data.current_month;
    [
      monthLabel(row.month),
      fmtEst(row.translate_usd),
      fmtEst(row.tts_usd),
      fmtEst(row.total_usd),
      String(row.calls),
    ].forEach((text) => {
      const cell = document.createElement("div");
      if (isCurrent) cell.className = "row-current";
      cell.textContent = text;
      tableEl.appendChild(cell);
    });
  });
}

async function saveKey() {
  const value = $("apiKeyInput").value.trim();
  if (!value) {
    toast("Paste an API key first.");
    return;
  }
  await api("/api/settings", { method: "PATCH", body: { gemini_api_key: value } });
  $("apiKeyInput").value = "";
  toast("API key saved.");
  await loadSettings();
}

async function removeKey() {
  await api("/api/settings", { method: "PATCH", body: { gemini_api_key: "" } });
  $("apiKeyInput").value = "";
  toast("API key removed — using baked key.");
  await loadSettings();
}

async function saveExportRoot(value) {
  await api("/api/settings", { method: "PATCH", body: { export_root: value } });
  toast("Output folder updated.");
  await loadSettings();
}

async function browseFolder() {
  const bridge = window.pywebview && window.pywebview.api;
  if (bridge && typeof bridge.pick_folder === "function") {
    try {
      const result = await bridge.pick_folder();
      const path = Array.isArray(result) ? result[0] : result;
      if (path) {
        $("exportRootInput").value = path;
        await saveExportRoot(path);
      }
      return;
    } catch (err) {
      /* dialog unavailable — fall through to typed path */
    }
  }
  const typed = window.prompt(
    "Output folder (absolute path):",
    $("exportRootInput").value || ""
  );
  if (typed !== null && typed.trim()) {
    $("exportRootInput").value = typed.trim();
    await saveExportRoot(typed.trim());
  }
}

async function resetExportRoot() {
  await saveExportRoot(null);
  $("exportRootInput").value = "";
}

function selectOutputPath() {
  const el = $("outputPath");
  const range = document.createRange();
  range.selectNodeContents(el);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}

async function revealTarget(target) {
  let ok = false;
  try {
    const res = await fetch("/api/system/reveal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target }),
    });
    ok = res.ok;
  } catch (err) {
    ok = false;
  }
  if (!ok) {
    toast("Couldn't open the folder. Path copied above.");
    selectOutputPath();
  }
}

/* ---------- boot ---------- */

function bind() {
  $("stepWords").addEventListener("click", () => goto("words"));
  $("stepVoice").addEventListener("click", () => goto("voice"));
  $("stepBake").addEventListener("click", () => goto("bake"));
  $("settingsBtn").addEventListener("click", () => goto("settings"));

  $("saveKeyBtn").addEventListener("click", saveKey);
  $("removeKeyBtn").addEventListener("click", removeKey);
  $("apiKeyInput").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") saveKey();
  });
  $("exportRootInput").addEventListener("change", () =>
    saveExportRoot($("exportRootInput").value.trim() || null)
  );
  $("exportRootInput").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") saveExportRoot($("exportRootInput").value.trim() || null);
  });
  $("browseFolderBtn").addEventListener("click", browseFolder);
  $("resetFolderBtn").addEventListener("click", resetExportRoot);
  $("openFolderBtn").addEventListener("click", () => revealTarget("folder"));
  $("showMp3Btn").addEventListener("click", () => revealTarget("mp3"));

  $("newProjectBtn").addEventListener("click", doNew);
  $("openBtn").addEventListener("click", doOpen);
  $("swapLangs").addEventListener("click", () => {
    const a = $("newSource").value;
    $("newSource").value = $("newTarget").value;
    $("newTarget").value = a;
  });

  const dz = $("dropzone");
  dz.addEventListener("click", () => $("fileInput").click());
  dz.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" || ev.key === " ") $("fileInput").click();
  });
  dz.addEventListener("dragover", (ev) => {
    ev.preventDefault();
    dz.classList.add("dragging");
  });
  dz.addEventListener("dragleave", () => dz.classList.remove("dragging"));
  dz.addEventListener("drop", (ev) => {
    ev.preventDefault();
    dz.classList.remove("dragging");
    if (ev.dataTransfer && ev.dataTransfer.files.length > 0) {
      doImport(ev.dataTransfer.files[0]);
    }
  });
  $("fileInput").addEventListener("change", () => {
    if ($("fileInput").files.length > 0) doImport($("fileInput").files[0]);
    $("fileInput").value = "";
  });

  $("translateBtn").addEventListener("click", doTranslate);
  $("addRowBtn").addEventListener("click", async () => {
    if (!needProject()) return;
    const body = { source: $("addSource").value };
    if ($("addTranslation").value) body.translation = $("addTranslation").value;
    await api("/api/rows", { method: "POST", body });
    $("addSource").value = "";
    $("addTranslation").value = "";
    await refresh();
  });
  $("addAtBtn").addEventListener("click", async () => {
    if (!needProject()) return;
    const body = { source: $("addSource").value, position: Number($("addAtN").value) };
    if ($("addTranslation").value) body.translation = $("addTranslation").value;
    await api("/api/rows", { method: "POST", body });
    $("addSource").value = "";
    $("addTranslation").value = "";
    await refresh();
  });

  $("modelSelect").addEventListener("change", async () => {
    await refreshVoices();
    if (state.project) {
      await api("/api/project/settings", { method: "PATCH", body: { tts_model: selectedModel() } });
      await refresh();
    }
  });
  $("voiceSelect").addEventListener("change", async () => {
    if (state.project) {
      await api("/api/project/settings", { method: "PATCH", body: { voice: $("voiceSelect").value } });
      await refresh();
    }
  });
  $("testVoiceBtn").addEventListener("click", testVoice);
  $("generateBtn").addEventListener("click", generateAll);
  $("forceRegen").addEventListener("change", renderVoice);
  $("cancelVoiceBtn").addEventListener("click", cancelJob);
  $("cancelBakeBtn").addEventListener("click", cancelJob);

  const pushSetting = async (key, value) => {
    if (!needProject()) return;
    const body = {};
    body[key] = value;
    await api("/api/project/settings", { method: "PATCH", body });
    await refresh();
    await updateEstimate();
  };
  $("repeatsInput").addEventListener("change", () => pushSetting("repeats", Number($("repeatsInput").value)));
  $("repeatGapInput").addEventListener("change", () => pushSetting("repeat_gap_s", Number($("repeatGapInput").value)));
  $("itemGapInput").addEventListener("change", () => pushSetting("item_gap_s", Number($("itemGapInput").value)));

  $("buildBtn").addEventListener("click", buildTape);

  $("modalKeep").addEventListener("click", () => {
    pendingDeleteId = null;
    $("modalBackdrop").hidden = true;
  });
  $("modalDelete").addEventListener("click", async () => {
    const id = pendingDeleteId;
    pendingDeleteId = null;
    $("modalBackdrop").hidden = true;
    if (id) {
      await api("/api/rows/" + id, { method: "DELETE" });
      await refresh();
    }
  });
}

bind();
goto("words");
refresh().then(() => refreshVoices());
