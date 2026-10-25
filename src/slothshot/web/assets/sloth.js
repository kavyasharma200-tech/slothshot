/* The drawing kit shared by the story and the app: the sloth, branches and the canopy, all drawn in code. */
(function () {
  const NS = "http://www.w3.org/2000/svg";

  // A three-toed sloth hanging under a branch at y = 14 of a 200 x 200 box. Arms in front, legs behind.
  const SLOTH = `
    <g class="legs" fill="none" stroke="var(--bark-700)" stroke-width="15" stroke-linecap="round">
      <path d="M78 146 C 50 132, 36 74, 44 16"/>
      <path d="M122 146 C 150 132, 164 74, 156 16"/>
    </g>
    <g fill="none" stroke="var(--bark-900)" stroke-width="2.6" stroke-linecap="round">
      <path d="M38 19 q 4 -11 13 -8 M43 21 q 5 -10 13 -6"/><path d="M162 19 q -4 -11 -13 -8 M157 21 q -5 -10 -13 -6"/>
    </g>
    <ellipse cx="100" cy="116" rx="45" ry="48" fill="var(--bark-500)"/>
    <path d="M70 104 c 8 -10 22 -12 30 -4 c -10 2 -20 10 -24 18 z M118 132 c 10 -2 18 4 18 14 c -8 -6 -14 -8 -20 -6 z" fill="var(--moss-600)" opacity=".38"/>
    <path d="M62 126 l -5 4 M60 112 l -5 2 M138 120 l 5 3 M136 136 l 5 4" stroke="var(--bark-600)" stroke-width="2" stroke-linecap="round"/>
    <g class="arms" fill="none" stroke="var(--bark-600)" stroke-width="14" stroke-linecap="round">
      <path class="arm-l" d="M80 98 C 68 74, 66 44, 78 16"/>
      <path class="arm-r" d="M120 98 C 132 74, 134 44, 122 16"/>
    </g>
    <g fill="none" stroke="var(--bark-900)" stroke-width="2.6" stroke-linecap="round">
      <path d="M73 19 q 3 -11 12 -9 M78 20 q 4 -10 12 -6"/><path d="M127 19 q -3 -11 -12 -9 M122 20 q -4 -10 -12 -6"/>
    </g>
    <circle cx="100" cy="140" r="31" fill="var(--bark-400)"/>
    <ellipse cx="100" cy="144" rx="24" ry="20" fill="var(--bark-100)"/>
    <path d="M77 139 C 83 132, 92 133, 95 140 C 90 146, 82 147, 77 139 Z" fill="var(--bark-800)"/>
    <path d="M123 139 C 117 132, 108 133, 105 140 C 110 146, 118 147, 123 139 Z" fill="var(--bark-800)"/>
    <g class="eye-open"><circle cx="88.5" cy="139.5" r="3.3" fill="var(--moss-950)"/><circle cx="111.5" cy="139.5" r="3.3" fill="var(--moss-950)"/>
      <circle cx="89.6" cy="138.4" r="1" fill="var(--bark-50)"/><circle cx="112.6" cy="138.4" r="1" fill="var(--bark-50)"/></g>
    <g class="eye-shut" fill="none" stroke="var(--moss-950)" stroke-width="2" stroke-linecap="round"><path d="M84.5 140 q 4 3 8 0"/><path d="M107.5 140 q 4 3 8 0"/></g>
    <ellipse cx="100" cy="150" rx="5.2" ry="3.7" fill="var(--bark-900)"/>
    <path d="M94.5 156 q 5.5 4.5 11 0" fill="none" stroke="var(--bark-800)" stroke-width="1.8" stroke-linecap="round"/>`;

  // Deterministic noise, so the same branch is drawn on every load.
  function rand(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }

  function el(tag, attrs, parent) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }

  function branchY(x, seed) { return 30 + 5 * Math.sin(x / 180 + seed) + 2.6 * Math.sin(x / 61 + seed * 2); }

  /* A branch `width` units long in a viewBox of width x 60. Options: knots (x positions), notches ([x, bad]), leaves. */
  function branch(svg, opts) {
    const o = Object.assign({ width: 1440, seed: 1, knots: [], notches: [], leaves: 14, memory: false }, opts);
    const W = o.width;
    svg.setAttribute("viewBox", `0 0 ${W} 60`);
    svg.innerHTML = "";
    let d = `M -20 ${branchY(-20, o.seed).toFixed(1)}`;
    for (let x = 20; x <= W + 40; x += 40) d += ` L ${x} ${branchY(x, o.seed).toFixed(1)}`;
    const r = rand(o.seed * 977);
    const leaves = el("g", {}, svg);
    for (let i = 0; i < o.leaves; i++) {
      const x = r() * W, y = branchY(x, o.seed) + 4, len = 18 + r() * 22, a = -30 + r() * 60;
      el("path", { d: `M0 0 C ${len * .35} ${len * .25}, ${len * .3} ${len * .85}, 0 ${len} C ${-len * .3} ${len * .85}, ${-len * .35} ${len * .25}, 0 0 Z`,
        transform: `translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${a.toFixed(1)})`, fill: r() > .5 ? "var(--moss-700)" : "var(--moss-800)" }, leaves);
    }
    el("path", { d, fill: "none", stroke: "var(--bark-700)", "stroke-width": 13, "stroke-linecap": "round", "vector-effect": "non-scaling-stroke" }, svg);
    el("path", { d, fill: "none", stroke: "var(--bark-500)", "stroke-width": 9, "stroke-linecap": "round", transform: "translate(0 -1.5)", "vector-effect": "non-scaling-stroke" }, svg);
    let memory = null;
    if (o.memory) memory = el("path", { d, fill: "none", stroke: "var(--moss-300)", "stroke-width": 2.4, "stroke-linecap": "round",
      transform: "translate(0 -4.5)", opacity: .9, "vector-effect": "non-scaling-stroke", "stroke-dasharray": "0 99999" }, svg);
    for (const x of o.knots) el("ellipse", { cx: x, cy: branchY(x, o.seed) + 1, rx: 9, ry: 7, fill: "var(--bark-700)" }, svg);
    for (const [x, bad] of o.notches) {
      const y = branchY(x, o.seed) - 6;
      el("line", { x1: x, x2: x, y1: y, y2: y - (bad ? 11 : 6), stroke: bad ? "var(--hib-400)" : "var(--bark-300)", "stroke-width": bad ? 2.4 : 1.3, "stroke-linecap": "round" }, svg);
    }
    return { memory, y: (x) => branchY(x, o.seed) };
  }

  /* A canopy edge: overlapping hanging leaves, filled with currentColor. */
  function canopy(svg, seed) {
    svg.innerHTML = "";
    const r = rand(seed * 131);
    el("rect", { x: 0, y: 0, width: 1440, height: 18, fill: "currentColor" }, svg);
    for (let i = 0; i < 90; i++) {
      const x = r() * 1440, len = 30 + r() * 80, w = 10 + r() * 16, a = -25 + r() * 50;
      el("path", { d: `M0 0 C ${w} ${len * .3}, ${w * .8} ${len * .8}, 0 ${len} C ${-w * .8} ${len * .8}, ${-w} ${len * .3}, 0 0 Z`,
        transform: `translate(${x.toFixed(1)} 6) rotate(${a.toFixed(1)})`, fill: "currentColor" }, svg);
    }
  }

  function draw(svg) { svg.innerHTML = SLOTH; }

  window.Sloth = { draw, branch, canopy, branchY, markup: SLOTH };
})();
