/* The app: start a night, watch it, and see what Temporal keeps. Talks only to the local API. */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const clock = (iso) => {
    const d = new Date(iso), t = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    return d.toDateString() === new Date().toDateString() ? t : `${d.toLocaleDateString([], { weekday: "long" })} ${t}`;
  };
  const ago = (iso) => { const s = Math.max(0, (Date.now() - new Date(iso)) / 1000); return s < 60 ? `${Math.round(s)} s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : clock(iso); };

  async function api(path, opts = {}) {
    const r = await fetch(path, { cache: "no-store", ...opts, headers: { "Content-Type": "application/json", "X-Slothshot": "1", ...(opts.headers || {}) } });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(body.detail || r.statusText), { status: r.status });
    return body;
  }
  const post = (path, data) => api(path, { method: "POST", body: JSON.stringify(data || {}) });

  function toast(text) {
    const t = $("[data-toast]"); t.textContent = text; t.classList.add("on");
    clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("on"), 3600);
  }

  $$("[data-sloth]").forEach(Sloth.draw);
  Sloth.branch($("[data-branch]"), { width: 1000, seed: 4, leaves: 12 });

  /* ---------- routing ---------- */
  let route = {};
  function parse() {
    const [, view = "run", id = ""] = (location.hash || "#/run").split("/");
    const q = new URLSearchParams(location.search).get("id");
    route = { view, id: decodeURIComponent(id) || (view === "run" ? q || "" : "") };
    $$("[data-view]").forEach((v) => (v.hidden = v.dataset.view !== route.view));
    $$("[data-tab]").forEach((a) => (a.dataset.tab === route.view ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    requestAnimationFrame(bead);
    if (route.view !== "run") document.body.dataset.world = "day";
    if (route.view === "runs") loadRuns();
    if (route.view === "run") { resetRun(); tick(); }
    if (route.view === "start") paintStart();
  }
  function bead() {
    const on = $(".tabs a[aria-current]"), b = $(".tabs__bead");
    if (!on) { b.style.width = "0"; return; }
    b.style.left = on.offsetLeft + "px"; b.style.width = on.offsetWidth + "px";
  }
  addEventListener("hashchange", parse);
  addEventListener("resize", bead);

  /* ---------- health ---------- */
  let health = null;
  async function pollHealth() {
    try { health = await api("/api/health"); } catch (e) { health = null; }
    paintHealth();
    if (route.view === "start") paintStart();
  }
  function paintHealth() {
    const h = health, box = $("[data-health]");
    if (!h) { box.innerHTML = `<span><i class="bad"></i>Can't reach slothshot up</span>`; return; }
    const w = h.worker;
    box.innerHTML = `
      <span><i class="${h.temporal.ok ? "" : "bad"}"></i>Temporal</span>
      <span><i class="${w.alive ? "" : w.managed ? "wait" : "bad"}"></i>${w.alive ? "Worker" : w.managed ? "Worker restarting" : "No worker"}</span>
      <span><i class="${h.ollama.ok && h.model.present ? "" : "bad"}"></i>${esc(h.model.name)}</span>
      ${h.temporal.ok ? `<a href="${esc(h.temporal.ui)}" target="_blank" rel="noopener">Temporal UI</a>` : ""}`;
    $("[data-worker]").textContent = !w.managed ? "This worker isn't run by slothshot up, so the plug can't be pulled from here."
      : w.alive ? `Worker ${w.pid} is up${w.since ? `, since ${ago(w.since)}` : ""}${w.restarts ? `, restarted ${w.restarts} time${w.restarts > 1 ? "s" : ""}` : ""}.`
      : "No worker right now. A new one starts in a few seconds, and Temporal hands it the work.";
    $("[data-kill]").disabled = !w.managed || !w.alive;
    const ch = $("[data-chaos]");
    if (document.activeElement !== ch) { ch.value = Math.round((h.chaos || 0) * 100); $("[data-chaos-out]").textContent = `${ch.value}%`; }
    const sel = $("[data-models]");
    const models = h.ollama.models.length ? h.ollama.models : [h.model.name];
    if (sel.dataset.list !== models.join()) {
      sel.dataset.list = models.join();
      sel.innerHTML = models.map((m) => `<option ${m === h.model.name ? "selected" : ""}>${esc(m)}</option>`).join("");
    }
  }

  /* ---------- start ---------- */
  let pulling = null;
  function paintStart() {
    const h = health, checks = $("[data-checks]");
    if (!h) { checks.innerHTML = `<div class="check"><i></i><div>The local server isn't answering.<small>Run <code>slothshot up</code> and reload.</small></div></div>`; return; }
    const rows = [];
    if (!h.temporal.ok) rows.push(["Temporal isn't reachable", "slothshot up starts a local Temporal server for you; restart it."]);
    if (!h.worker.alive) rows.push([h.worker.managed ? "The worker is restarting" : "No worker is running", h.worker.managed ? "It comes back on its own in a few seconds." : "Run slothshot up, or slothshot worker in another terminal."]);
    if (!h.ollama.ok) rows.push(["Ollama isn't running", "Install it from ollama.com and open it; Slothshot talks to it on localhost:11434."]);
    else if (!h.model.present) rows.push([`${h.model.name} isn't downloaded yet`, "About 800 MB, once.", true]);
    checks.innerHTML = rows.map(([t, s, pull]) => `<div class="check"><i></i><div>${esc(t)}<small>${esc(s)}</small>
      ${pull ? `<div class="meter"><b data-meter></b></div>` : ""}</div>${pull ? `<button class="btn" type="button" data-pull>Download it</button>` : ""}</div>`).join("");
    const chips = $("[data-chips]");
    const list = [["demo", "Try 20 made-up screenshots"], ...h.suggested_folders.map((f) => [f, f])];
    if (chips.dataset.list !== JSON.stringify(list)) {
      chips.dataset.list = JSON.stringify(list);
      chips.innerHTML = list.map(([v, label]) => `<button type="button" data-folder="${esc(v)}">${v === "demo" ? `<b>${esc(label)}</b>` : esc(label)}</button>`).join("");
    }
  }
  document.addEventListener("click", async (e) => {
    const chip = e.target.closest("[data-folder]");
    if (chip) {
      const input = $('[name="folder"]');
      if (chip.dataset.folder === "demo") {
        chip.disabled = true; chip.textContent = "Drawing 20 screenshots…";
        try { const r = await post("/api/demo-folder"); input.value = r.folder; toast(`${r.count} made-up screenshots are ready.`); }
        catch (err) { toast(`Couldn't make them: ${err.message}`); }
        chip.disabled = false; $("[data-chips]").dataset.list = ""; paintStart();
      } else input.value = chip.dataset.folder;
      input.focus();
    }
    if (e.target.closest("[data-pull]")) pullModel();
  });
  async function pullModel() {
    const model = health.model.name;
    try { await post("/api/ollama/pull", { model }); } catch (err) { toast(err.message); return; }
    clearInterval(pulling);
    pulling = setInterval(async () => {
      const p = await api(`/api/ollama/pull?model=${encodeURIComponent(model)}`).catch(() => null);
      const m = $("[data-meter]");
      if (p && m) m.style.width = `${p.total ? Math.round(p.completed / p.total * 100) : 3}%`;
      if (!p || p.status === "done" || p.status === "error") { clearInterval(pulling); if (p?.status === "error") toast(p.error); pollHealth(); }
    }, 900);
  }
  $("[data-start]").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target), folder = String(f.get("folder") || "").trim();
    const field = $(".field");
    if (!folder) { field.classList.remove("shake"); void field.offsetWidth; field.classList.add("shake"); $('[name="folder"]').focus(); return; }
    const btn = $("[data-submit]");
    btn.disabled = true; btn.textContent = "Waking the sloth…";
    try {
      const r = await post("/api/runs", { folder, apply_after_minutes: +f.get("after"), night: f.get("night") || null, model: f.get("model") || null });
      location.hash = `#/run/${encodeURIComponent(r.id)}`;
    } catch (err) { toast(err.message); }
    btn.disabled = false; btn.textContent = "Hand it to the sloth";
  });

  /* ---------- one night ---------- */
  const LOOKED = new Set(["named", "no-text", "failed", "skipped", "moved", "undone"]);
  const NIGHT = new Set(["starting", "sleeping", "reading", "moving", "undoing"]);
  let runId = "", runRun = "", after = 0, lastKey = "", events = [];
  function resetRun() { runId = route.id; runRun = ""; after = 0; lastKey = ""; events = []; $("[data-events]").innerHTML = ""; }

  function headline(d) {
    const s = d.state, items = s.items, total = items.length;
    const looked = items.filter((i) => LOOKED.has(i.status)).length;
    const named = items.filter((i) => i.status === "named" || i.status === "moved").length;
    const moved = items.filter((i) => i.status === "moved").length;
    const cur = items[s.cursor];
    const b = (label, act, kind = "") => [label, act, kind];
    if (d.running !== "RUNNING" && d.result) return [esc(d.result), "This night is over. Its whole history stays in Temporal.", [b("Start another night", "new", "solid")]];
    switch (s.phase) {
      case "starting": return ["Waking up.", "", []];
      case "sleeping": return ["Asleep until later.", "It starts when it's quiet. Or wake it now.", [b("Wake it now", "wake", "solid")]];
      case "reading":
        if (s.napping) return [`Napping at <em>${looked}</em> of ${total}.`, "Nothing is lost while it sleeps.", [b("Wake up", "wake", "solid")]];
        return [`Reading <em>${Math.min(looked + 1, total)}</em> of ${total}.`, cur ? `<code>${esc(cur.name)}</code>` : "",
          [b("Nap", "nap"), s.decision === "approve" ? null : b("Move them when done", "approve", "solid"), b("Don't move anything", "veto")].filter(Boolean)];
      case "waiting":
        return [`${named} screenshots have names. I'll move them at <em>${clock(s.apply_at)}</em> unless you stop me.`, "Saying nothing counts as yes.",
          [b("Move them now", "approve", "solid"), b("Leave them", "veto")]];
      case "moving": return [`Moving <em>${moved}</em> of ${named}.`, "", []];
      case "done": return [`Filed <em>${moved}</em> screenshots.`, s.undo_until ? `Changed your mind? You can put them back until ${clock(s.undo_until)}.` : "", [b("Put them back", "undo")]];
      case "undoing": return ["Putting them back.", "", []];
      case "undone": return ["Every file is back where it was.", "", []];
      case "vetoed": return ["Left everything where it was.", "", []];
      case "rolled-back": return ["A move failed, so I put everything back.", "", []];
      default: return [esc(s.phase), "", []];
    }
  }

  function paintRun(d) {
    const s = d.state, items = s.items;
    const over = d.running !== "RUNNING";
    document.body.dataset.world = !over && NIGHT.has(s.phase) && !s.napping ? "night" : "day";
    const [say, sub, acts] = headline(d);
    $("[data-say]").innerHTML = say; $("[data-sub]").innerHTML = sub;
    $("[data-acts]").innerHTML = acts.map(([l, a, k]) => `<button class="btn ${k}" type="button" data-act="${a}">${l}</button>`).join("");
    $("[data-tui]").href = d.temporal_ui || "#";

    const n = items.length, looked = items.filter((i) => LOOKED.has(i.status)).length;
    $("[data-count]").textContent = n ? `${looked}/${n}` : "";
    const knots = $("[data-knots]");
    if (knots.children.length !== n) knots.innerHTML = items.map(() => "<i></i>").join("");
    // Knots and the sloth sit inside a 42 px margin, so the sloth never hangs off the edge.
    $$("i", knots).forEach((k, i) => { k.style.left = `calc(42px + (100% - 84px) * ${n > 1 ? (i / (n - 1)).toFixed(4) : 0})`; k.className = LOOKED.has(items[i].status) ? (items[i].status === "failed" ? "bad" : "on") : ""; });
    const at = over || ["waiting", "moving", "done", "undoing", "undone", "vetoed", "rolled-back"].includes(s.phase) ? 1 : Math.min(looked, n - 1) / Math.max(n - 1, 1);
    const sl = $(".branch__sloth");
    sl.style.left = `calc(42px + (100% - 84px) * ${at.toFixed(4)})`;
    sl.classList.toggle("asleep", s.napping || s.phase === "sleeping" || over || s.phase === "done");

    const words = { waiting: "", reading: "reading", naming: "thinking of a name", named: "", "no-text": "no words on it", failed: "couldn't read it", skipped: "skipped", moved: "moved", undone: "put back" };
    $("[data-ledger]").innerHTML = items.map((it, i) => {
      const nu = it.filename ? `<i>${esc(it.category)}</i>${esc(it.filename)}` : esc(it.note || "");
      const canSkip = (it.status === "waiting" || it.status === "named") && (s.phase === "reading" || s.phase === "waiting") && !over;
      const tries = it.tries > 1 ? ` <span class="t">${it.tries} tries</span>` : "";
      return `<li class="row${it.filename ? "" : " dim"}${it.status === "reading" || it.status === "naming" ? " busy" : ""}">
        <img loading="lazy" alt="" src="/api/shot?i=${i}&id=${encodeURIComponent(d.id)}&v=${it.status}">
        <div><div class="old">${esc(it.name)}</div><div class="new">${nu || "&nbsp;"}</div></div>
        <div class="st">${words[it.status] ?? esc(it.status)}${tries}${canSkip ? `<br><button class="btn" type="button" data-skip="${i}">Skip</button>` : ""}</div></li>`;
    }).join("");

    const pend = d.pending || [];
    $("[data-pending]").innerHTML = pend.length ? pend.map((p) => `<div class="pend">
        <div><b>${esc(p.activity)}</b> · attempt <b class="${p.attempt > 1 ? "bad" : ""}">${p.attempt}</b> · ${esc(String(p.state || "").toLowerCase())}</div>
        ${p.last_failure ? `<div class="bad">last try: ${esc(p.last_failure)}</div>` : ""}
        <div class="row2"><span>${p.last_heartbeat ? `heartbeat ${ago(p.last_heartbeat)}` : p.last_started ? `started ${ago(p.last_started)}` : "waiting for a worker"}</span></div></div>`).join("")
      : `<p class="quiet">${over ? "This night is over." : s.phase === "waiting" ? "Waiting for you, on a durable timer." : s.napping ? "Napping between screenshots." : "Between steps."}</p>`;
  }

  async function tick() {
    if (route.view !== "run") return;
    try {
      const d = await api(`/api/status${runId ? `?id=${encodeURIComponent(runId)}` : ""}`);
      $("[data-empty]").hidden = true;
      $$(".run__main > :not([data-empty])").forEach((n) => (n.hidden = false));
      if (!runId) runId = d.id;
      const key = JSON.stringify([d.state, d.pending, d.running, d.result]);
      if (key !== lastKey) { lastKey = key; paintRun(d); }
      if (d.run !== runRun) { runRun = d.run; after = 0; }
      const h = await api(`/api/history?id=${encodeURIComponent(d.id)}&after=${after}`);
      if (h.events.length) { after = h.last; paintEvents(h.events); }
    } catch (err) {
      if (err.status === 404) {
        $("[data-empty]").hidden = false;
        $$(".run__main > :not([data-empty])").forEach((n) => (n.hidden = true));
        document.body.dataset.world = "day";
      }
    }
  }
  function paintEvents(list) {
    const box = $("[data-events]");
    for (const e of list) {
      const bad = /Failed|TimedOut|Terminated/.test(e.type) || (e.attempt > 1) || /timeout|weak|chaos|error/i.test(e.detail || "");
      const li = document.createElement("li");
      if (bad) li.className = "bad";
      li.innerHTML = `<span>${e.id}</span><span><b>${esc(e.type)}</b>${e.activity ? ` ${esc(e.activity)}` : ""}${e.attempt > 1 ? ` · attempt ${e.attempt}` : ""}${e.detail ? `<span class="d">${esc(e.detail)}</span>` : ""}</span>`;
      box.prepend(li);
    }
    while (box.children.length > 140) box.lastChild.remove();
  }

  document.addEventListener("click", async (e) => {
    const a = e.target.closest("[data-act]")?.dataset.act;
    if (a) {
      if (a === "new") { location.hash = "#/start"; return; }
      try { const r = await post("/api/act", { action: a, id: runId }); toast(r.message); } catch (err) { toast(err.message); }
      lastKey = ""; tick();
    }
    const sk = e.target.closest("[data-skip]");
    if (sk) { try { await post("/api/act", { action: "skip", id: runId, index: +sk.dataset.skip }); toast("Skipped."); } catch (err) { toast(err.message); } tick(); }
  });
  $("[data-kill]").addEventListener("click", async (e) => {
    const b = e.currentTarget;
    b.disabled = true;
    try { const r = await post("/api/lab/kill"); toast(`Worker ${r.killed} is gone. A new one starts in ${r.restart_in} s; watch the attempt number.`); }
    catch (err) { toast(err.message); }
    setTimeout(pollHealth, 400);
  });
  $("[data-chaos]").addEventListener("input", (e) => ($("[data-chaos-out]").textContent = `${e.target.value}%`));
  $("[data-chaos]").addEventListener("change", async (e) => {
    try { const r = await post("/api/lab/chaos", { rate: e.target.value / 100 }); toast(r.rate ? `${Math.round(r.rate * 100)}% of OCR and model calls will now fail. Temporal retries every one.` : "The model is back to normal."); }
    catch (err) { toast(err.message); }
  });

  /* ---------- every night ---------- */
  async function loadRuns() {
    const box = $("[data-runs]");
    try {
      const { runs } = await api("/api/runs");
      box.innerHTML = runs.length ? runs.map((r) => `<li><a href="#/run/${encodeURIComponent(r.id)}"><span class="f">${esc(r.folder || r.id)}</span>
        <span class="w">${clock(r.start)}${r.close ? ` to ${clock(r.close)}` : ", still going"}</span><span class="s">${esc(r.status.toLowerCase())}</span></a></li>`).join("")
        : `<li class="quiet">No nights yet.</li>`;
    } catch (err) { box.innerHTML = `<li class="quiet">${esc(err.message)}</li>`; }
  }

  parse();
  pollHealth();
  setInterval(pollHealth, 3000);
  setInterval(tick, 1200);
})();
