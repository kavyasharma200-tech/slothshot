/* The story page's choreography. Content lives in index.html and assets/night/*.json (a real run). */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const html = document.documentElement;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const hasGsap = !!(window.gsap && window.ScrollTrigger);
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const ramp = (p, a, b) => clamp((p - a) / (b - a));
  const ease = (t) => 1 - Math.pow(1 - t, 3);
  const mmss = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  $$("[data-sloth]").forEach(Sloth.draw);
  Sloth.branch($('[data-branch="hero"]'), { seed: 2, leaves: 22 });
  Sloth.branch($('[data-branch="footer"]'), { seed: 5, leaves: 18 });
  $$("[data-canopy]").forEach((s) => Sloth.canopy(s, +s.dataset.canopy));

  /* ---------- install commands ---------- */
  const OS = [
    { id: "win", label: "Windows", cmd: "irm https://raw.githubusercontent.com/kavyasharma200-tech/slothshot/main/install.ps1 | iex" },
    { id: "unix", label: "macOS · Linux", cmd: "curl -fsSL https://raw.githubusercontent.com/kavyasharma200-tech/slothshot/main/install.sh | sh" },
    { id: "repo", label: "From the repo", cmd: "git clone https://github.com/kavyasharma200-tech/slothshot && cd slothshot && uv run slothshot up" },
  ];
  let os = /Win/.test(navigator.platform || navigator.userAgent) ? "win" : "unix";
  function paintOS() {
    $$("[data-os-tabs]").forEach((tabs) => {
      if (!tabs.dataset.built) {
        for (const o of OS) tabs.insertAdjacentHTML("beforeend", `<button type="button" role="tab" data-os="${o.id}">${o.label}</button>`);
        tabs.dataset.built = "1";
      }
      let on = null;
      $$("button", tabs).forEach((b) => { b.setAttribute("aria-selected", b.dataset.os === os); if (b.dataset.os === os) on = b; });
      const bead = $(".bead", tabs);
      if (on) requestAnimationFrame(() => { bead.style.left = on.offsetLeft + "px"; bead.style.width = on.offsetWidth + "px"; });
    });
    $$("[data-os-cmd]").forEach((c) => (c.textContent = OS.find((o) => o.id === os).cmd));
  }
  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-os]");
    if (t) { os = t.dataset.os; paintOS(); }
    const c = e.target.closest("[data-copy]");
    if (c) {
      const text = c.parentElement.querySelector("code").textContent;
      navigator.clipboard?.writeText(text).then(() => { c.classList.add("done"); setTimeout(() => c.classList.remove("done"), 1400); });
    }
  });
  paintOS();
  addEventListener("resize", paintOS);

  /* ---------- live mode: served by your own `slothshot up` ---------- */
  let live = null;
  (async () => {
    // Only your own `slothshot up` has an API; the public copy (GitHub Pages) just replays the recorded night.
    if (!/^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname)) return;
    try {
      const ctl = new AbortController();
      setTimeout(() => ctl.abort(), 1500);
      const r = await fetch("/api/health", { cache: "no-store", signal: ctl.signal });
      if (!r.ok) return;
      live = await r.json();
      html.classList.add("live");
      const cta = $("#cta");
      cta.textContent = "Open the app";
      cta.href = "/app";
      $$("[data-live-only]").forEach((a) => (a.hidden = false));
      const ok = (b) => (b ? "awake" : "asleep");
      $("#live-cap").textContent = `This page is your own Slothshot · Temporal ${live.temporal.ok ? "on" : "off"} · worker ${ok(live.worker.alive)} · ${live.model.name}`;
    } catch (e) { /* a static copy of the page: everything replays from the recorded night */ }
  })();

  /* ---------- smooth scroll ---------- */
  let lenis = null;
  if (hasGsap) gsap.registerPlugin(ScrollTrigger);
  if (hasGsap && !reduce && window.Lenis) {
    lenis = new Lenis({ duration: 1.25, easing: (t) => 1 - Math.pow(1 - t, 4), smoothWheel: true });
    lenis.on("scroll", ScrollTrigger.update);
    gsap.ticker.add((t) => lenis.raf(t * 1000));
    gsap.ticker.lagSmoothing(0);
  }
  document.addEventListener("click", (e) => {
    const a = e.target.closest('a[href^="#"]');
    if (!a) return;
    const target = a.getAttribute("href") === "#top" ? 0 : $(a.getAttribute("href"));
    if (target === null) return;
    e.preventDefault();
    if (lenis) lenis.scrollTo(target, { duration: 1.8 });
    else (target === 0 ? scrollTo({ top: 0 }) : target.scrollIntoView());
  });

  /* ---------- intro ---------- */
  function afterIntro(fn) {
    const d = html.dataset.intro;
    if (d === "done" || d === "none") fn();
    else addEventListener("intro:reveal", fn, { once: true });
  }
  function heroIn() {
    if (!hasGsap || reduce) return;
    gsap.fromTo("[data-hero]", { opacity: 0, y: 26, filter: "blur(8px)" },
      { opacity: 1, y: 0, filter: "blur(0px)", duration: 1.3, ease: "expo.out", stagger: .12, clearProps: "filter" });
    gsap.fromTo(".hero__stage", { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 1.8, ease: "expo.out", delay: .2 });
  }
  (function intro() {
    const mode = html.dataset.intro;
    const done = () => { html.dataset.intro = "done"; try { sessionStorage.setItem("slothshot-intro", "1"); } catch (e) {} lenis?.start(); dispatchEvent(new Event("intro:done")); };
    if (mode === "none" || !hasGsap) { html.dataset.intro = mode === "none" ? "none" : "done"; return; }
    const el = $(".intro");
    lenis?.stop();
    const g = $(".intro__sloth");
    g.innerHTML = Sloth.markup;
    g.classList.add("sloth", "asleep");
    const now = new Date();
    $(".intro__caption .i1").textContent = `${now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} here · getting dark`;
    const tl = gsap.timeline({ onComplete: done });
    if (mode === "long") {
      tl.to(".intro__branch", { strokeDashoffset: 0, duration: 1.1, ease: "power2.inOut" })
        .to(g, { opacity: 1, duration: .6, ease: "power2.out" }, .7)
        .add(() => g.classList.remove("asleep"), 1.45)
        .to(".intro__caption span", { yPercent: -100, duration: .6, ease: "expo.inOut" }, 1.5);
    }
    const t = mode === "long" ? 2.05 : .15;
    // The page rises from the horizon like morning light, so the sloth stays in view until it passes.
    tl.set(el, { "--y": "112vh" }, t)
      .fromTo(el, { "--hole": "0vmax" }, { "--hole": "170vmax", duration: 1.3, ease: "expo.inOut" }, t)
      .add(() => { html.dataset.intro = "reveal"; dispatchEvent(new Event("intro:reveal")); }, t + .3);
  })();
  afterIntro(heroIn);

  /* ---------- reveals ---------- */
  const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("is-in"); io.unobserve(e.target); } }),
    { rootMargin: "0px 0px -12% 0px" });
  $$("[data-reveal]").forEach((n) => io.observe(n));

  /* ---------- chrome tone + rail ---------- */
  const chrome = $(".chrome"), rail = $(".rail"), railTime = $("#rail-time");
  const sections = $$("[data-tone]").filter((s) => s !== chrome && s !== rail && s.tagName !== "BODY");
  function tone() {
    const probe = 34;
    for (const s of sections) {
      const r = s.getBoundingClientRect();
      if (r.top <= probe && r.bottom > probe) { chrome.dataset.tone = s.dataset.tone; break; }
    }
  }
  addEventListener("scroll", tone, { passive: true });
  tone();

  /* ---------- data: the real night ---------- */
  Promise.all([fetch("assets/night/night.json").then((r) => r.json()), fetch("assets/night/answers.json").then((r) => r.json())])
    .then(([night, answers]) => {
      night.shots.forEach((s) => (s.answers = answers.answers[s.name] || []));
      grave(night);
      theNight(night);
      morning(night);
      remember(night);
      if (hasGsap) ScrollTrigger.refresh();
    })
    .catch((e) => console.warn("night data missing", e));

  /* ---------- the graveyard: a wall of identical names ---------- */
  function grave(night) {
    const rows = $("[data-grave]");
    const names = night.shots.map((s) => s.name);
    for (let r = 0; r < 3; r++) {
      const order = names.slice(r * 7).concat(names.slice(0, r * 7));
      const row = document.createElement("div");
      row.className = "grave__row";
      row.innerHTML = order.concat(order).map((n) => `<b class="${n.includes("150433") && r === 1 ? "hit" : ""}">${esc(n)}</b>`).join("");
      rows.appendChild(row);
      if (hasGsap && !reduce) {
        const dir = r % 2 ? 1 : -1;
        gsap.fromTo(row, { xPercent: dir > 0 ? -30 : 0 }, { xPercent: dir > 0 ? 0 : -30, ease: "none",
          scrollTrigger: { trigger: ".grave", start: "top bottom", end: "bottom top", scrub: .6 } });
      }
    }
  }

  /* ---------- the night: one sticky stage, rendered from scroll progress ---------- */
  function theNight(night) {
    const stage = $(".night__stage"), track = $("[data-track]"), shots = night.shots;
    const sloth1 = $("[data-stage-sloth]"), sloth2 = $("[data-stage-sloth2]");
    const ocr = $("[data-ocr]"), ocrTxt = $(".txt", ocr), ans = $("[data-answers]"), log = $("[data-log]"), counter = $("[data-counter]");
    const flash = document.createElement("i"); flash.className = "flash"; stage.appendChild(flash);
    const dim = document.createElement("i"); dim.className = "dim"; stage.appendChild(dim);
    const crack = $("[data-crack]");
    const beats = Object.fromEntries($$("[data-beat]").map((b) => [b.dataset.beat, b]));
    const N = shots.length;

    // The script: segments in "units"; each unit is a slice of scroll.
    const SEG = [
      ["wake", 1.3], ["k0", 2.3], ["k1", 2.8], ["k2", 1.0], ["k3", .6], ["k4", .6], ["k5", 1.5], ["k6", .55], ["k7", .55],
      ["storm", 3.8], ["fast", 3.0], ["k19", .8], ["dawn", 1.5],
    ];
    const total = SEG.reduce((a, s) => a + s[1], 0);
    const starts = {}; let acc = 0;
    for (const [k, len] of SEG) { starts[k] = [acc, len]; acc += len; }
    const local = (u, k) => (u - starts[k][0]) / starts[k][1];
    $(".night").style.height = `${Math.round(total * 46 + 100)}svh`;

    // Real kills from the worker logs: during the bakery retries (knot 1), mid-call at knot 8, and at knot 9.
    const KILLS = [1, 8, 9];

    let G = {};
    let cards = [];
    function layout() {
      // Measure the stage itself: on phones innerHeight moves with the URL bar, the sticky stage (100svh) does not.
      const W = stage.clientWidth || innerWidth, H = stage.clientHeight || innerHeight, mobile = W < 760;
      const cardW = mobile ? 150 : clamp(W * .145, 180, 250);
      const gap = cardW * (mobile ? 1.45 : 1.75);
      const branchY = H * (mobile ? .17 : .27);
      const slothX = W * (mobile ? .2 : .3);
      const margin = W * 1.1;
      const width = margin * 2 + (N - 1) * gap;
      G = { W, H, mobile, cardW, gap, branchY, slothX, margin, width };
      stage.style.setProperty("--branch-y", branchY + "px");
      stage.style.setProperty("--card-w", cardW + "px");
      stage.style.setProperty("--sloth-x", slothX + "px");
      stage.style.setProperty("--sloth-w", cardW * .8 + "px");
      stage.style.setProperty("--thread", (mobile ? 46 : 64) + "px");
      track.style.width = width + "px";
      const knotX = (i) => margin + i * gap;
      // Notches: one for every finished activity, placed by when it finished, and a red one where the heartbeat stopped.
      const times = shots.map((s) => s.named_at ?? s.read_at ?? 0);
      const posAt = (t) => { let i = 0; while (i < N - 1 && (times[i + 1] ?? 1e9) < t) i++; const a = times[i], b = times[i + 1] ?? a + 30; return i + clamp((t - a) / Math.max(b - a, 1)); };
      const notches = night.marks.filter((m) => m[1] === "ActivityTaskCompleted").map((m) => [knotX(posAt(m[0]) - .5), false]);
      night.moments.filter((m) => m.kind === "heartbeat-timeout").forEach((m) => notches.push([knotX(posAt(m.t) - .5), true]));
      const b = Sloth.branch($('[data-branch="night"]'), { width, seed: 3, knots: shots.map((_, i) => knotX(i)), notches, leaves: Math.round(width / 120), memory: true });
      $('[data-branch="night"]').style.width = width + "px";
      G.memory = b.memory; G.memLen = b.memory.getTotalLength(); G.knotX = knotX;
      cards.forEach((c, i) => (c.style.left = knotX(i) + "px"));
      crack.style.left = slothX - 10 + "px";
      crack.style.top = branchY - 34 + "px";
      crack.style.width = "40px";
      last = -1;
    }

    track.insertAdjacentHTML("beforeend", shots.map((s, i) => `
      <div class="knot-card" data-i="${i}">
        <div class="pic"><img src="assets/night/shots/${String(i).padStart(2, "0")}.jpg" alt="" loading="lazy"><i class="scan"></i></div>
        <div class="tag"><div class="old">${esc(s.name)}</div><div class="new">${s.slug ? `<i>${esc(s.category)}</i>${esc(s.taken.slice(0, 10))}-${esc(s.slug)}.png` : "no words on it, left alone"}</div></div>
      </div>`).join(""));
    cards = $$(".knot-card", track);
    cards.forEach((c, i) => { if (!shots[i].slug) c.classList.add("left"); });

    // Where the sloth is along the branch (a continuous knot index) at script time u.
    function posOf(u) {
      const go = (k, from, to, a = 0, b = .3) => from + (to - from) * ease(ramp(local(u, k), a, b));
      if (u < starts.k0[0]) return go("wake", -1.4, -.75, .2, 1);
      for (let i = 0; i <= 7; i++) { const k = i === 0 ? "k0" : i <= 7 ? `k${i}` : null; if (u < starts[k][0] + starts[k][1]) return go(k, i - 1 + (i === 0 ? .25 : 0), i); }
      if (u < starts.fast[0]) return go("storm", 7, 8, 0, .16);
      if (u < starts.k19[0]) return 8 + 10 * ramp(local(u, "fast"), .05, .95);
      if (u < starts.dawn[0]) return go("k19", 18, 19, 0, .35);
      return 19;
    }

    // Which card is named by u: a card's name lands near the end of its own segment.
    const NAMED_AT = shots.map((_, i) => {
      if (i === 0) return starts.k0[0] + starts.k0[1] * .72;
      if (i <= 7) { const [a, l] = starts[`k${i}`]; return a + l * (i === 1 || i === 2 ? .9 : .7); }
      if (i === 8) return starts.storm[0] + starts.storm[1] * .86;
      if (i <= 18) return starts.fast[0] + starts.fast[1] * (.05 + .9 * (i - 8) / 10);
      return starts.k19[0] + starts.k19[1] * .6;
    });

    function showBeat(name, p, a, b) {
      const n = beats[name]; if (!n) return;
      const o = Math.min(ramp(p, a, a + .07), 1 - ramp(p, b - .07, b));
      n.style.opacity = o.toFixed(3);
      n.style.transform = `translateY(${((1 - ramp(p, a, a + .1)) * 24 - ramp(p, b - .1, b) * 30).toFixed(1)}px)`;
    }

    function answersFor(i, p, appearFrom, appearTo) {
      const list = shots[i].answers;
      if (ans.dataset.for != i) {
        ans.dataset.for = i;
        ans.innerHTML = list.map((a) => a.startsWith("=>")
          ? `<li><span class="yes">${esc(a.slice(2))}</span><span class="why">${list.length === 1 ? "first try" : "on the screen"}</span></li>`
          : `<li><span class="no">${esc(a)}</span><span class="why">not on the screen</span></li>`).join("")
          + (shots[i].fallback ? `<li><span class="yes">${esc(shots[i].slug)}</span><span class="why">the first words on the screen</span></li>` : "");
      }
      const items = $$("li", ans);
      items.forEach((li, k) => li.classList.toggle("on", p >= appearFrom + (appearTo - appearFrom) * (k / Math.max(items.length, 1))));
    }

    let last = -1;
    function render(u) {
      if (Math.abs(u - last) < 1e-4) return;
      last = u;
      const p = (k) => local(u, k);
      const pos = posOf(u);
      const x = G.slothX + G.gap * .62 - G.knotX(pos);
      track.style.transform = `translate3d(${x.toFixed(1)}px,0,0)`;
      const cur = clamp(Math.round(pos), 0, N - 1);

      // Cards: named once their moment has passed; the one in front of the sloth is lit.
      let named = 0, calls = 0;
      cards.forEach((c, i) => {
        const isNamed = u >= NAMED_AT[i];
        c.classList.toggle("named", isNamed);
        c.classList.toggle("on", i === cur);
        if (isNamed && shots[i].slug) { named++; calls += shots[i].tries || 1; }
      });
      // The memory: the part of the branch Temporal has already written down glows.
      const memX = G.knotX(pos) - G.gap * .62;
      G.memory.setAttribute("stroke-dasharray", `${clamp(memX / G.width) * G.memLen} 99999`);

      // Sloth crawl and the wake / sleep of its eyes.
      const crawl = Math.sin(pos * Math.PI * 2);
      const s1 = $("svg", sloth1), s2 = $("svg", sloth2);
      s1.classList.toggle("asleep", p("wake") < .35);
      const st = p("storm"), fell = ease(ramp(st, .25, .42)), climbed = ease(ramp(st, .6, .84));
      const afterStorm = u >= starts.storm[0] + starts.storm[1] * .6;
      sloth1.style.opacity = afterStorm ? 0 : 1;
      sloth1.style.transform = `translate3d(0, ${(fell * G.H * 1.1).toFixed(1)}px, 0) rotate(${(fell * 38 + crawl * 2.5).toFixed(2)}deg)`;
      sloth2.style.opacity = st >= .6 ? 1 : 0;
      sloth2.style.transform = `translate3d(0, ${((1 - climbed) * G.H * .9).toFixed(1)}px, 0) rotate(${(crawl * 2.5).toFixed(2)}deg)`;
      s2.classList.toggle("asleep", p("dawn") > .55);

      // Storm: flash, crack, dim, the log, then the climb back.
      const fl = Math.max(ramp(st, .2, .22) * (1 - ramp(st, .22, .3)), .5 * ramp(st, .255, .265) * (1 - ramp(st, .265, .3)));
      flash.style.opacity = (fl * .85).toFixed(3);
      const killFlash = KILLS.filter((k) => k !== 8).some((k) => Math.abs(u - (k === 1 ? starts.k1[0] + starts.k1[1] * .55 : starts.fast[0] + starts.fast[1] * .1)) < .05);
      if (killFlash) flash.style.opacity = ".25";
      crack.style.opacity = (ramp(st, .22, .24) * (1 - ramp(st, .62, .72))).toFixed(3);
      dim.style.opacity = (Math.min(ramp(st, .23, .32), 1 - ramp(st, .8, .95)) * .55).toFixed(3);
      log.style.opacity = Math.min(ramp(st, .27, .31), 1 - ramp(st, .9, .97)).toFixed(3);
      $$("div", log).forEach((d, k) => (d.style.opacity = ramp(st, .3 + k * .07, .33 + k * .07).toFixed(2)));

      // OCR for the slow chapters.
      let ocrOn = 0, ocrFor = -1, ocrP = 0;
      if (u >= starts.k0[0] && u < starts.k1[0]) { ocrFor = 0; ocrP = ramp(p("k0"), .14, .55); ocrOn = Math.min(ramp(p("k0"), .12, .18), 1 - ramp(p("k0"), .56, .62)); }
      if (u >= starts.k1[0] && u < starts.k2[0]) { ocrFor = 1; ocrP = ramp(p("k1"), .12, .3); ocrOn = Math.min(ramp(p("k1"), .1, .14), 1 - ramp(p("k1"), .32, .36)); }
      if (u >= starts.storm[0] && u < starts.fast[0]) { ocrFor = 8; ocrP = ramp(st, .08, .2); ocrOn = Math.min(ramp(st, .06, .1), 1 - ramp(st, .2, .23)); }
      ocr.style.opacity = ocrOn.toFixed(3);
      if (ocrFor >= 0) { const t = shots[ocrFor].ocr || ""; ocrTxt.textContent = t.slice(0, Math.round(t.length * ocrP)); }
      cards.forEach((c, i) => {
        const scan = $(".scan", c);
        const on = i === ocrFor && ocrOn > 0;
        scan.style.opacity = on ? ocrOn.toFixed(2) : "0";
        if (on) scan.style.transform = `translateY(${(-110 + ocrP * 500).toFixed(1)}%)`;
      });

      // The model's answers, in order, for the chapters that show them.
      let ansOn = 0;
      const A = [["k0", 0, .62, .66, .7, .97], ["k1", 1, .36, .4, .82, .97], ["k2", 2, 0, .1, .7, .95], ["k3", 3, 0, .15, .6, .95], ["k4", 4, 0, .15, .55, .95], ["k5", 5, 0, .2, .6, .95]];
      for (const [k, i, a, b, c, d] of A) {
        const q = p(k);
        if (q >= 0 && q < 1) { answersFor(i, q, b, c); ansOn = Math.min(ramp(q, a, b), 1 - ramp(q, d, 1)); }
      }
      ans.style.opacity = ansOn.toFixed(3);

      // Words.
      showBeat("wake", p("wake"), .05, 1.05);
      showBeat("read", p("k0"), .08, .58);
      showBeat("name", p("k0"), .6, 1.02);
      showBeat("wrong", p("k1"), .02, 1.0);
      showBeat("right", p("k5"), .05, .98);
      showBeat("storm", st, .2, .6);
      showBeat("kept", st, .66, 1.04);
      showBeat("rest", u < starts.dawn[0] ? p("fast") : 1 + p("dawn") * .4, .45, 1.25);

      // Counter, during the fast part of the night and the dawn.
      const kills = KILLS.filter((k) => u >= (k === 1 ? starts.k1[0] + starts.k1[1] * .55 : k === 8 ? starts.storm[0] + starts.storm[1] * .22 : starts.fast[0] + starts.fast[1] * .1)).length;
      counter.style.opacity = Math.min(ramp(p("fast"), 0, .08), 1 - ramp(p("dawn"), .6, .9)).toFixed(3);
      setNum("named", named); setNum("calls", calls); setNum("kills", kills);

      // Dawn and the replay clock.
      stage.style.setProperty("--dawn", ease(ramp(p("dawn"), .1, .9)).toFixed(3));
      const tReal = realTime(pos, u);
      railTime.textContent = mmss(tReal);
      rail.style.setProperty("--p", clamp(u / total).toFixed(4));
    }
    const nums = {};
    function setNum(k, v) { if (nums[k] !== v) { nums[k] = v; $(`[data-c="${k}"]`, counter).textContent = v; } }
    function realTime(pos, u) {
      if (pos < 0) return 0;
      const i = Math.floor(pos), f = pos - i;
      const a = shots[i]?.named_at ?? shots[i]?.read_at ?? 0, b = shots[i + 1]?.named_at ?? shots[i + 1]?.read_at ?? a;
      return a + (b - a) * f;
    }

    layout();
    addEventListener("resize", () => { layout(); render(state.u + 1e-6); });
    const state = { u: 0 };
    if (hasGsap && !reduce) {
      gsap.to(state, { u: total, ease: "none", onUpdate: () => render(state.u),
        scrollTrigger: { trigger: ".night", start: "top top", end: "bottom bottom", scrub: .9,
          onToggle: (self) => rail.classList.toggle("on", self.isActive) } });
      render(0);
    } else {
      // Reduced motion: one screen holding the night's last frame, every card named, nothing moving.
      $(".night").style.height = "100svh";
      render(starts.dawn[0] + starts.dawn[1] * .3);
    }
  }

  /* ---------- morning: the real UI, replaying the real plan ---------- */
  function morning(night) {
    const box = $("[data-demo]"), say = $("[data-say]"), sub = $("[data-sub]"), acts = $("[data-acts]"), pile = $("[data-pile]"), folders = $("[data-folders]");
    const shots = night.shots;
    const named = shots.filter((s) => s.slug);
    const fname = (s) => `${s.taken.slice(0, 10)}-${s.slug}.png`;
    pile.innerHTML = shots.map((s, i) => `<div data-i="${i}"><img src="assets/night/shots/${String(i).padStart(2, "0")}.jpg" alt="" loading="lazy">
      <span><span class="o">${esc(s.name)}</span><br><span class="n">${s.slug ? `<i>${esc(s.category)}</i>${esc(fname(s))}` : "no words on it, stays where it is"}</span></span></div>`).join("");
    let state = "waiting", busy = false;
    function paint() {
      const btn = (label, act, kind) => `<button class="btn ${kind}" type="button" data-act="${act}">${label}</button>`;
      if (state === "waiting") {
        say.innerHTML = `${named.length} screenshots have names. I'll move them in <em>${night.apply_after_minutes} minutes</em> unless you stop me.`;
        sub.textContent = "Saying nothing counts as yes.";
        acts.innerHTML = btn("Move them now", "approve", "go") + btn("Leave them", "veto", "no");
        pile.hidden = false; folders.hidden = true;
      } else if (state === "done") {
        const until = new Date(Date.now() + 24 * 3600e3).toLocaleString([], { weekday: "long", hour: "numeric", minute: "2-digit" });
        say.innerHTML = `Filed <em>${named.length}</em> screenshots.`;
        sub.textContent = `Changed your mind? You can put them back until ${until}.`;
        acts.innerHTML = btn("Put them back", "undo", "no");
      } else if (state === "vetoed") {
        say.innerHTML = "Left everything where it was.";
        sub.textContent = "Nothing moved, and the names are still in the report.";
        acts.innerHTML = btn("Start over", "reset", "no");
      } else if (state === "undone") {
        say.innerHTML = "Every file is back where it was.";
        sub.textContent = "The undo is the same put-back the saga uses when a move fails.";
        acts.innerHTML = btn("Start over", "reset", "no");
        pile.hidden = false; folders.hidden = true;
      }
    }
    async function move() {
      busy = true;
      $$("button", acts).forEach((b) => (b.disabled = true));
      folders.hidden = false; folders.innerHTML = "";
      const byCat = {};
      for (let k = 0; k < named.length; k++) {
        const s = named[k];
        say.innerHTML = `Moving <em>${k + 1}</em> of ${named.length}.`;
        sub.textContent = fname(s);
        const row = $(`[data-i="${shots.indexOf(s)}"]`, pile);
        if (row && !reduce) { row.style.transition = "opacity .35s, transform .35s"; row.style.opacity = "0"; row.style.transform = "translateX(16px)"; }
        if (!byCat[s.category]) {
          byCat[s.category] = document.createElement("div");
          byCat[s.category].className = "folder";
          byCat[s.category].innerHTML = `<b><svg aria-hidden="true"><use href="#i-folder"/></svg>${esc(s.category)}</b><ul></ul>`;
          folders.appendChild(byCat[s.category]);
        }
        $("ul", byCat[s.category]).insertAdjacentHTML("beforeend", `<li>${esc(fname(s))}</li>`);
        await new Promise((r) => setTimeout(r, reduce ? 0 : 110));
      }
      pile.hidden = true;
      $$("div", pile).forEach((r) => { r.style.opacity = ""; r.style.transform = ""; });
      busy = false; state = "done"; paint();
    }
    acts.addEventListener("click", (e) => {
      const a = e.target.closest("[data-act]")?.dataset.act;
      if (!a || busy) return;
      if (a === "approve") move();
      if (a === "veto") { state = "vetoed"; paint(); }
      if (a === "undo") { state = "undone"; paint(); }
      if (a === "reset") { state = "waiting"; paint(); }
    });
    paint();

    $("[data-live-try]")?.addEventListener("click", async (e) => {
      const b = e.currentTarget;
      b.disabled = true; b.textContent = "Drawing 20 screenshots…";
      try {
        const f = await (await fetch("/api/demo-folder", { method: "POST", headers: { "X-Slothshot": "1" } })).json();
        b.textContent = "Waking the sloth…";
        const r = await fetch("/api/runs", { method: "POST", headers: { "Content-Type": "application/json", "X-Slothshot": "1" }, body: JSON.stringify({ folder: f.folder, apply_after_minutes: 60 }) });
        const run = await r.json();
        if (!r.ok) throw new Error(run.detail || "could not start");
        location.href = `/app?id=${encodeURIComponent(run.id)}`;
      } catch (err) { b.disabled = false; b.textContent = `Couldn't start it: ${err.message}`; }
    });
  }

  /* ---------- how it remembers: a graph that replays the real history ---------- */
  function remember(night) {
    const host = $("[data-graph]");
    const NSs = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NSs, "svg");
    svg.setAttribute("viewBox", "0 0 640 560");
    host.appendChild(svg);
    const C = [320, 268];
    const ACTS = ["scan_folder", "read_screenshot", "name_screenshot", "move_file", "put_back", "write_report"];
    const nodes = { core: { x: C[0], y: C[1], r: 58, label: "workflow", kind: "core" } };
    ACTS.forEach((a, i) => { const ang = (-150 + i * 60) * Math.PI / 180; nodes[a] = { x: C[0] + Math.cos(ang) * 178, y: C[1] + Math.sin(ang) * 178, r: 34, label: a.replace("_", " "), kind: "act" }; });
    nodes.history = { x: 92, y: 496, r: 66, label: "history", kind: "store" };
    nodes.folder = { x: 556, y: 500, r: 50, label: "your folder", kind: "store" };
    nodes.ollama = { x: 572, y: 72, r: 48, label: "gemma3:1b", kind: "store" };
    const WIRES = [...ACTS.map((a) => ["core", a]), ["core", "history"], ["read_screenshot", "folder"], ["scan_folder", "folder"], ["move_file", "folder"], ["put_back", "folder"], ["write_report", "folder"], ["name_screenshot", "ollama"]];
    const wires = {};
    const g = (tag, attrs, parent = svg) => { const n = document.createElementNS(NSs, tag); for (const k in attrs) n.setAttribute(k, attrs[k]); parent.appendChild(n); return n; };
    for (const [a, b] of WIRES) {
      const A = nodes[a], B = nodes[b], mx = (A.x + B.x) / 2, my = (A.y + B.y) / 2, dx = B.x - A.x, dy = B.y - A.y;
      const bow = .14, cx = mx - dy * bow, cy = my + dx * bow;
      wires[a + ">" + b] = g("path", { class: "wire", d: `M${A.x} ${A.y} Q ${cx} ${cy} ${B.x} ${B.y}`, "data-a": a, "data-b": b });
    }
    for (const [k, n] of Object.entries(nodes)) {
      const grp = g("g", { class: `node ${n.kind}`, "data-n": k });
      g("circle", { cx: n.x, cy: n.y, r: n.r }, grp);
      const t = g("text", { x: n.x, y: n.y + (n.kind === "act" ? n.r + 18 : 5) }, grp); t.textContent = n.label;
      if (n.kind === "act") { const c = g("text", { class: "n", x: n.x, y: n.y + 7 }, grp); c.textContent = "0"; n.count = c; }
      if (k === "history") { const c = g("text", { class: "n", x: n.x, y: n.y + 30 }, grp); c.textContent = "0"; n.count = c; }
      n.el = grp;
    }
    const pulses = [];
    function pulse(a, b, bad) {
      const w = wires[a + ">" + b] || wires[b + ">" + a];
      if (!w) return;
      const dot = g("circle", { class: "pulse" + (bad ? " bad" : ""), r: bad ? 6 : 3.4 });
      pulses.push({ w, rev: !wires[a + ">" + b], t0: performance.now(), dur: bad ? 900 : 620, dot });
    }

    // Replay: the history's own clock, sped up.
    const marks = night.marks, END = marks[marks.length - 1][0];
    const hb = night.moments.find((m) => m.kind === "heartbeat-timeout");
    const events = $("[data-events]"), when = $("[data-when]"), scrub = $("[data-scrub]"), play = $("[data-play]");
    let t = 0, idx = 0, playing = true, visible = false, lastNow = 0;
    const SPEED = END / 46; // the whole night in about 46 seconds
    const counts = {};
    function line(m, bad) {
      const d = document.createElement("div");
      d.innerHTML = `${mmss(m[0])}  <span class="${bad ? "bad" : "k"}">${m[1]}</span>  ${m[2] || ""}${bad ? "  attempt 2 · Heartbeat timeout" : ""}`;
      events.appendChild(d);
      while (events.children.length > 9) events.firstChild.remove();
    }
    function apply(m, animate) {
      const [, type, act] = m;
      counts.history = (counts.history || 0) + 1;
      if (type === "ActivityTaskScheduled" && animate) pulse("core", act);
      if (type === "ActivityTaskStarted" && animate) {
        const bad = hb && Math.abs(m[0] - hb.t) < .01 && act === hb.activity;
        if (bad) { pulse("core", act, true); nodes[act].el.classList.add("hurt"); setTimeout(() => nodes[act].el.classList.remove("hurt"), 1600); }
        const store = act === "name_screenshot" ? "ollama" : act === "write_report" || act === "scan_folder" || act === "read_screenshot" || act === "move_file" || act === "put_back" ? "folder" : null;
        if (store) pulse(act, store);
        if (bad) line(m, true);
      }
      if (type === "ActivityTaskCompleted") { counts[act] = (counts[act] || 0) + 1; if (animate) { pulse(act, "core"); pulse("core", "history"); } }
      if (animate && (type.startsWith("Activity") || type.startsWith("WorkflowExecution") || type.startsWith("Timer"))) line(m, false);
    }
    function paintCounts() {
      for (const a of ACTS) nodes[a].count.textContent = counts[a] || 0;
      nodes.history.count.textContent = counts.history || 0;
    }
    function seek(to) {
      t = clamp(to, 0, END); idx = 0;
      for (const k in counts) delete counts[k];
      events.innerHTML = "";
      while (idx < marks.length && marks[idx][0] <= t) apply(marks[idx++], false);
      paintCounts(); when.textContent = mmss(t); scrub.value = Math.round(t / END * 1000);
    }
    function frame(now) {
      const dt = Math.min((now - (lastNow || now)) / 1000, .1); lastNow = now;
      if (playing && visible) {
        t += dt * SPEED;
        if (t > END + 4) seek(0);
        let n = 0;
        while (idx < marks.length && marks[idx][0] <= t && n < 14) { apply(marks[idx++], true); n++; }
        paintCounts(); when.textContent = mmss(Math.min(t, END)); scrub.value = Math.round(Math.min(t, END) / END * 1000);
      }
      for (let i = pulses.length - 1; i >= 0; i--) {
        const p = pulses[i], k = (now - p.t0) / p.dur;
        if (k >= 1) { p.dot.remove(); pulses.splice(i, 1); continue; }
        const L = p.w.getTotalLength(), pt = p.w.getPointAtLength((p.rev ? 1 - k : k) * L);
        p.dot.setAttribute("cx", pt.x.toFixed(1)); p.dot.setAttribute("cy", pt.y.toFixed(1));
      }
      if (visible || pulses.length) requestAnimationFrame(frame); else lastNow = 0;
    }
    new IntersectionObserver(([e]) => { const was = visible; visible = e.isIntersecting && !reduce; if (visible && !was) requestAnimationFrame(frame); }, { threshold: .15 }).observe(host);
    if (reduce) { seek(END); playing = false; play.textContent = "Play"; }
    play.addEventListener("click", () => { playing = !playing; play.textContent = playing ? "Pause" : "Play"; if (playing && reduce) { visible = true; requestAnimationFrame(frame); } });
    scrub.addEventListener("input", () => { seek(scrub.value / 1000 * END); });

    // What can go wrong, and what catches it. Each one lights its part of the graph and, if it happened tonight, seeks to it.
    const FAILS = [
      { t: "The worker dies mid-call", tag: "heartbeat", n: ["name_screenshot", "history"], at: hb?.t,
        p: "The model call runs in a thread while the activity heartbeats every 3 s. When the beats stop, Temporal hands the call to the next worker after 20 s instead of waiting out the 5 minute timeout.",
        c: "heartbeat_timeout=timedelta(seconds=20)" },
      { t: "Ollama is closed", tag: "retry policy", n: ["name_screenshot", "ollama"],
        p: "No attempt limit, backing off to one try every 30 s, so the sloth simply waits for the model to come back.",
        c: "RetryPolicy(initial_interval=timedelta(seconds=2),\n            backoff_coefficient=2.0,\n            maximum_interval=timedelta(seconds=30))" },
      { t: "The model says “recipe”", tag: "next_retry_delay", n: ["name_screenshot", "ollama"], at: 22,
        p: "At least two words of a name must really be on the screenshot. If not, the activity fails and asks again one second later, a little warmer.",
        c: 'raise ApplicationError("weak name", type="WeakAnswer",\n                       next_retry_delay=timedelta(seconds=1))' },
      { t: "A file is corrupt", tag: "non-retryable", n: ["read_screenshot", "folder"],
        p: "Some errors will never get better, so they are marked and skipped instead of retried forever.",
        c: 'raise ApplicationError("could not read image",\n                       non_retryable=True, type="Unreadable")' },
      { t: "A move fails halfway", tag: "saga", n: ["move_file", "put_back", "folder"],
        p: "A half-tidied folder is worse than an untidy one, so everything already moved is put back before the workflow ends.",
        c: "except ActivityError:\n    await self._put_everything_back()" },
      { t: "You change your mind", tag: "update + validator", n: ["core", "put_back"], at: 748,
        p: "Approve, veto and undo are updates with validators, so a veto after the move gets a plain “too late, try undo” instead of being ignored.",
        c: "@undo.validator\ndef _undo_ok(self):\n    if self.s.phase != \"done\":\n        raise ValueError(\"Nothing to undo yet\")" },
      { t: "Five thousand screenshots", tag: "continue-as-new", n: ["core", "history"],
        p: "Every 25 screenshots the workflow starts a fresh run carrying its state, so no history ever grows large.",
        c: "workflow.continue_as_new(dataclasses.replace(inp, state=s))" },
      { t: "Every night, forever", tag: "schedule", n: ["core", "scan_folder"],
        p: "One command creates a Temporal Schedule, and the sloth tidies the folder at 01:30 every night.",
        c: "slothshot schedule ~/Pictures/Screenshots --at 01:30" },
    ];
    const list = $("[data-fails]");
    list.innerHTML = FAILS.map((f, i) => `<li data-f="${i}" aria-current="${i === 0}"><button type="button"><span>${f.t}</span><span>${f.tag}</span></button>
      <div class="more"><div><p>${f.p}</p><pre><code>${esc(f.c)}</code></pre></div></div></li>`).join("");
    function focus(i, light = true) {
      $$("li", list).forEach((li) => li.setAttribute("aria-current", li.dataset.f == i));
      if (!light) return;
      const lit = new Set(FAILS[i].n);
      Object.entries(nodes).forEach(([k, n]) => { n.el.classList.toggle("lit", lit.has(k)); n.el.classList.toggle("dim", !lit.has(k) && k !== "core"); });
      Object.values(wires).forEach((w) => { const on = lit.has(w.dataset.a) && lit.has(w.dataset.b) || (lit.has(w.dataset.b) && w.dataset.a === "core"); w.classList.toggle("lit", on); w.classList.toggle("dim", !on); });
      if (FAILS[i].at != null) seek(FAILS[i].at - 4);
    }
    list.addEventListener("click", (e) => { const li = e.target.closest("[data-f]"); if (li) focus(+li.dataset.f); });
    seek(0);
    focus(0, false);
  }
})();
