// src/exif_dashboard/static/dashboard.js
"use strict";
const PAYLOAD = JSON.parse(document.getElementById("payload").textContent);
// Derivatives are always excluded from charts (spec); footnote shows the count.
const ALL = PAYLOAD.shots.filter(s => !s.is_derivative);
const N_DERIV = PAYLOAD.shots.length - ALL.length;

// Spec: fixed focal-length bin edges, closed underflow, open top.
const BIN_EDGES = [0, 10, 14, 18, 24, 35, 50, 70, 85, 105, 135, 200, 300, 400, Infinity];
const BIN_LABELS = ["<10", "10", "14", "18", "24", "35", "50", "70", "85", "105", "135", "200", "300", "400+"];

// Apertures are bucketed around conventional full-stop values. Boundaries
// are geometric midpoints, which puts intermediate values (f/3.2, f/4.5,
// etc.) with their nearest full stop.
const APERTURE_STOPS = [1, 1.4, 2, 2.8, 4, 5.6, 8, 11, 16, 22, 32];
const APERTURE_EDGES = [0];
for (let i = 0; i < APERTURE_STOPS.length - 1; i++) {
  APERTURE_EDGES.push(Math.sqrt(APERTURE_STOPS[i] * APERTURE_STOPS[i + 1]));
}
APERTURE_EDGES.push(Infinity);
const APERTURE_LABELS = APERTURE_STOPS.map(n => `f/${n}`);

const UNKNOWN = "Unknown";
const val = (s, k) => (s[k] == null ? UNKNOWN : String(s[k]));
const year = s => (s.datetime ? +s.datetime.slice(0, 4) : null);
const fmt = n => n.toLocaleString("en-US");

// ---------- filters ----------
const uniq = key => [...new Set(ALL.map(s => val(s, key)))].sort();
const years = [...new Set(ALL.map(year).filter(y => y !== null))].sort((a, b) => a - b);
const state = { top_folder: new Set(), camera_model: new Set(), lens: new Set(),
                yearMin: null, yearMax: null };

function filtered() {
  return ALL.filter(s => {
    for (const key of ["top_folder", "camera_model", "lens"]) {
      if (state[key].size && !state[key].has(val(s, key))) return false;
    }
    const y = year(s);
    if (state.yearMin !== null && (y === null || y < state.yearMin)) return false;
    if (state.yearMax !== null && (y === null || y > state.yearMax)) return false;
    return true;
  });
}

function multiSelect(labelText, key) {
  const label = document.createElement("label");
  label.textContent = labelText;
  const sel = document.createElement("select");
  sel.multiple = true;
  for (const v of uniq(key)) {
    const o = document.createElement("option");
    o.value = o.textContent = v;
    sel.appendChild(o);
  }
  sel.addEventListener("change", () => {
    state[key] = new Set([...sel.selectedOptions].map(o => o.value));
    renderAll();
  });
  label.appendChild(sel);
  return label;
}

function yearSelect(labelText, stateKey, defaultLabel) {
  const label = document.createElement("label");
  label.textContent = labelText;
  const sel = document.createElement("select");
  sel.appendChild(new Option(defaultLabel, ""));
  for (const y of years) sel.appendChild(new Option(y, y));
  sel.addEventListener("change", () => {
    state[stateKey] = sel.value === "" ? null : +sel.value;
    renderAll();
  });
  label.appendChild(sel);
  return label;
}

function buildFilters() {
  const el = document.getElementById("filters");
  el.appendChild(multiSelect("Top folder", "top_folder"));
  el.appendChild(multiSelect("Camera", "camera_model"));
  el.appendChild(multiSelect("Lens", "lens"));
  el.appendChild(yearSelect("From year", "yearMin", "first"));
  el.appendChild(yearSelect("To year", "yearMax", "last"));
  const clear = document.createElement("button");
  clear.textContent = "Clear filters";
  clear.addEventListener("click", () => {
    for (const k of ["top_folder", "camera_model", "lens"]) state[k] = new Set();
    state.yearMin = state.yearMax = null;
    el.querySelectorAll("select").forEach(s => { s.selectedIndex = -1; if (!s.multiple) s.selectedIndex = 0; });
    renderAll();
  });
  el.appendChild(clear);
}

// ---------- svg helpers ----------
const SVG_NS = "http://www.w3.org/2000/svg";
function el(name, attrs) {
  const e = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}
// Bar with 4px rounded data-end, square at the baseline (dataviz mark spec).
function barPathH(x, y, w, h) {   // grows rightward
  const r = Math.min(4, w, h / 2);
  return `M${x},${y} h${w - r} a${r},${r} 0 0 1 ${r},${r} v${h - 2 * r} a${r},${r} 0 0 1 -${r},${r} h${-(w - r)} z`;
}
function barPathV(x, y, w, h, baseY) {  // grows upward from baseY
  const r = Math.min(4, h, w / 2);
  return `M${x},${baseY} v${-(h - r)} a${r},${r} 0 0 1 ${r},-${r} h${w - 2 * r} a${r},${r} 0 0 1 ${r},${r} v${h - r} z`;
}
const tooltip = document.getElementById("tooltip");
function hover(target, text) {
  target.addEventListener("mousemove", ev => {
    tooltip.hidden = false;
    tooltip.textContent = text();
    tooltip.style.left = Math.min(ev.clientX + 12, window.innerWidth - 180) + "px";
    tooltip.style.top = (ev.clientY + 12) + "px";
  });
  target.addEventListener("mouseleave", () => { tooltip.hidden = true; });
}

// ---------- charts ----------
function countBy(rows, keyFn) {
  const m = new Map();
  for (const r of rows) {
    const k = keyFn(r);
    m.set(k, (m.get(k) || 0) + 1);
  }
  return m;
}

// Horizontal bar chart: filtered (series) bar over an "all shots" track.
function hBarChart(container, title, keyFn, rows) {
  const totals = countBy(ALL, keyFn);
  const counts = countBy(rows, keyFn);
  const cats = [...totals.keys()].sort((a, b) => (totals.get(b) - totals.get(a)) || a.localeCompare(b));
  const card = document.createElement("div");
  card.className = "chart-card";
  card.innerHTML = `<h2>${title}</h2>`;
  const labelW = 230, valueW = 60, barMaxW = 420, rowH = 24, barH = 16;
  const svg = el("svg", { width: labelW + barMaxW + valueW, height: cats.length * rowH + 4 });
  const max = Math.max(...totals.values(), 1);
  cats.forEach((c, i) => {
    const y = i * rowH + (rowH - barH) / 2;
    const name = el("text", { x: labelW - 8, y: y + barH - 4, "text-anchor": "end", class: "lbl" });
    name.textContent = c.length > 34 ? c.slice(0, 33) + "…" : c;
    svg.appendChild(name);
    const tw = Math.round((totals.get(c) / max) * barMaxW);
    const fw = Math.round(((counts.get(c) || 0) / max) * barMaxW);
    if (tw > 0) svg.appendChild(el("path", { d: barPathH(labelW, y, tw, barH), fill: "var(--track)" }));
    if (fw > 0) svg.appendChild(el("path", { d: barPathH(labelW, y, fw, barH), fill: "var(--series-1)" }));
    const v = el("text", { x: labelW + tw + 6, y: y + barH - 4 });
    v.textContent = fmt(counts.get(c) || 0);
    svg.appendChild(v);
    const hit = el("rect", { x: 0, y: i * rowH, width: labelW + barMaxW + valueW, height: rowH, fill: "transparent" });
    hover(hit, () => `${c}: ${fmt(counts.get(c) || 0)} selected of ${fmt(totals.get(c))}`);
    svg.appendChild(hit);
  });
  card.appendChild(svg);
  container.appendChild(card);
}

function binIndex(value, edges) {
  if (value == null) return -1;
  for (let i = 0; i < edges.length - 1; i++) {
    if (value >= edges[i] && value < edges[i + 1]) return i;
  }
  return -1;
}

function rowsByLens(rows) {
  const byLens = new Map();
  for (const s of rows) {
    const k = val(s, "lens");
    if (!byLens.has(k)) byLens.set(k, []);
    byLens.get(k).push(s);
  }
  return byLens;
}

// Per-lens small-multiple histogram for a numeric shot field.
function lensHistogram(container, rows, config) {
  const card = document.createElement("div");
  card.className = "chart-card";
  card.innerHTML = `<h2>${config.title}</h2>`;
  const grid = document.createElement("div");
  grid.className = "facet-grid";
  const byLens = rowsByLens(rows);
  const lenses = [...byLens.keys()].sort((a, b) => byLens.get(b).length - byLens.get(a).length);
  const W = 240, H = 110, padB = 18, padT = 6;
  for (const lens of lenses) {
    const shots = byLens.get(lens);
    const bins = new Array(config.labels.length).fill(0);
    let unknown = 0;
    for (const s of shots) {
      const i = binIndex(s[config.key], config.edges);
      if (i < 0) unknown++;
      else bins[i]++;
    }
    const facet = document.createElement("div");
    const h3 = document.createElement("h3");
    h3.textContent = lens;
    const sub = document.createElement("div");
    sub.className = "sub";
    sub.textContent = `${fmt(shots.length)} shots` + (unknown ? ` · ${fmt(unknown)} unknown ${config.unknownLabel}` : "");
    facet.appendChild(h3);
    facet.appendChild(sub);
    const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` });
    const max = Math.max(...bins, 1);
    const slot = W / config.labels.length, barW = Math.min(24, slot - 2);  // 2px surface gap
    const baseY = H - padB;
    svg.appendChild(el("line", { x1: 0, y1: baseY, x2: W, y2: baseY, stroke: "var(--baseline)", "stroke-width": 1 }));
    bins.forEach((n, i) => {
      const x = i * slot + (slot - barW) / 2;
      if (n > 0) {
        const h = Math.max(2, Math.round((n / max) * (baseY - padT)));
        const p = el("path", { d: barPathV(x, baseY - h, barW, h, baseY), fill: "var(--series-1)" });
        hover(p, () => `${lens} @ ${config.tooltipLabel(config.labels[i])}: ${fmt(n)} shots`);
        svg.appendChild(p);
      }
      if (i % config.labelEvery === 0 || config.labels.length <= 8) {
        const t = el("text", { x: x + barW / 2, y: H - 5, "text-anchor": "middle" });
        t.textContent = config.labels[i];
        svg.appendChild(t);
      }
    });
    facet.appendChild(svg);
    grid.appendChild(facet);
  }
  card.appendChild(grid);
  container.appendChild(card);
}

function focalLengthPlot(container, rows) {
  lensHistogram(container, rows, {
    title: "Focal length by lens", key: "focal_length", edges: BIN_EDGES,
    labels: BIN_LABELS, unknownLabel: "fl", labelEvery: 2,
    tooltipLabel: label => `${label}mm`,
  });
}

function aperturePlot(container, rows) {
  lensHistogram(container, rows, {
    title: "Aperture by lens", key: "aperture", edges: APERTURE_EDGES,
    labels: APERTURE_LABELS, unknownLabel: "aperture", labelEvery: 2,
    tooltipLabel: label => label,
  });
}

// Per-lens joint distribution of focal length (x) and aperture (y).
function exposureHeatmap(container, rows) {
  const card = document.createElement("div");
  card.className = "chart-card";
  card.innerHTML = "<h2>Focal length × aperture by lens</h2>";
  const grid = document.createElement("div");
  grid.className = "facet-grid heatmap-grid";
  const byLens = rowsByLens(rows);
  const lenses = [...byLens.keys()].sort((a, b) => byLens.get(b).length - byLens.get(a).length);
  const cell = 15, left = 34, top = 4, bottom = 34;
  const W = left + BIN_LABELS.length * cell;
  const H = top + APERTURE_LABELS.length * cell + bottom;
  for (const lens of lenses) {
    const shots = byLens.get(lens);
    const counts = Array.from({ length: APERTURE_LABELS.length }, () => new Array(BIN_LABELS.length).fill(0));
    let known = 0;
    for (const s of shots) {
      const x = binIndex(s.focal_length, BIN_EDGES);
      const y = binIndex(s.aperture, APERTURE_EDGES);
      if (x >= 0 && y >= 0) { counts[y][x]++; known++; }
    }
    const facet = document.createElement("div");
    const h3 = document.createElement("h3");
    h3.textContent = lens;
    const sub = document.createElement("div");
    sub.className = "sub";
    sub.textContent = `${fmt(known)} of ${fmt(shots.length)} shots with both values`;
    facet.appendChild(h3);
    facet.appendChild(sub);
    const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` });
    const max = Math.max(...counts.flat(), 1);
    counts.forEach((row, y) => row.forEach((n, x) => {
      const rect = el("rect", {
        x: left + x * cell, y: top + y * cell, width: cell - 1, height: cell - 1,
        fill: n ? "var(--series-1)" : "var(--grid)",
        "fill-opacity": n ? (0.18 + 0.82 * Math.sqrt(n / max)).toFixed(2) : 0.35,
      });
      hover(rect, () => `${lens} · ${BIN_LABELS[x]}mm · ${APERTURE_LABELS[y]}: ${fmt(n)} shots`);
      svg.appendChild(rect);
    }));
    APERTURE_LABELS.forEach((label, y) => {
      if (y % 2) return;
      const t = el("text", { x: left - 4, y: top + y * cell + cell - 4, "text-anchor": "end" });
      t.textContent = label;
      svg.appendChild(t);
    });
    BIN_LABELS.forEach((label, x) => {
      if (x % 2) return;
      const cx = left + x * cell + cell / 2;
      const t = el("text", { x: cx, y: top + APERTURE_LABELS.length * cell + 5,
        transform: `rotate(55 ${cx} ${top + APERTURE_LABELS.length * cell + 5})`, "text-anchor": "start" });
      t.textContent = label;
      svg.appendChild(t);
    });
    facet.appendChild(svg);
    grid.appendChild(facet);
  }
  card.appendChild(grid);
  container.appendChild(card);
}

// Shots over time: per-month columns.
function timeChart(container, rows) {
  const card = document.createElement("div");
  card.className = "chart-card";
  card.innerHTML = "<h2>Shots over time</h2>";
  const months = countBy(rows.filter(s => s.datetime), s => s.datetime.slice(0, 7));
  if (!months.size) {
    card.insertAdjacentHTML("beforeend", '<div class="sub">No dated shots in selection.</div>');
    container.appendChild(card);
    return;
  }
  const keys = [...months.keys()].sort();
  const [y0, m0] = keys[0].split(":").map(Number);
  const [y1, m1] = keys[keys.length - 1].split(":").map(Number);
  const seq = [];
  for (let y = y0, m = m0; y < y1 || (y === y1 && m <= m1); m === 12 ? (m = 1, y++) : m++) {
    seq.push(`${y}:${String(m).padStart(2, "0")}`);
  }
  const W = 1000, H = 140, padB = 18, padT = 6, baseY = H - padB;
  const svg = el("svg", { width: "100%", height: H, viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" });
  const slot = W / seq.length, barW = Math.max(1, Math.min(24, slot - 2));
  const max = Math.max(...months.values());
  seq.forEach((k, i) => {
    const n = months.get(k) || 0;
    if (n === 0) return;
    const h = Math.max(1, Math.round((n / max) * (baseY - padT)));
    const x = i * slot + (slot - barW) / 2;
    const p = el("path", { d: barPathV(x, baseY - h, barW, h, baseY), fill: "var(--series-1)" });
    hover(p, () => `${k.replace(":", "-")}: ${fmt(n)} shots`);
    svg.appendChild(p);
  });
  svg.appendChild(el("line", { x1: 0, y1: baseY, x2: W, y2: baseY, stroke: "var(--baseline)", "stroke-width": 1 }));
  for (let y = y0; y <= y1; y++) {
    const i = seq.indexOf(`${y}:01`);
    if (i < 0) continue;
    const t = el("text", { x: i * slot, y: H - 5 });
    t.textContent = y;
    svg.appendChild(t);
  }
  card.appendChild(svg);
  container.appendChild(card);
}

// ---------- page assembly ----------
function renderAll() {
  const rows = filtered();
  const stat = document.getElementById("stat-row");
  stat.innerHTML =
    `<div class="stat-tile"><div class="label">Shots selected</div><div class="value">${fmt(rows.length)}</div></div>` +
    `<div class="stat-tile"><div class="label">All shots</div><div class="value">${fmt(ALL.length)}</div></div>` +
    `<div class="stat-tile"><div class="label">Lenses</div><div class="value">${fmt(new Set(rows.map(s => val(s, "lens"))).size)}</div></div>` +
    `<div class="stat-tile"><div class="label">Cameras</div><div class="value">${fmt(new Set(rows.map(s => val(s, "camera_model"))).size)}</div></div>`;
  const charts = document.getElementById("charts");
  charts.innerHTML = "";
  const legend = document.createElement("div");
  legend.className = "legend";
  legend.innerHTML =
    '<span><span class="swatch" style="background:var(--series-1)"></span>selected</span>' +
    '<span><span class="swatch" style="background:var(--track)"></span>all shots</span>';
  charts.appendChild(legend);
  focalLengthPlot(charts, rows);
  aperturePlot(charts, rows);
  exposureHeatmap(charts, rows);
  hBarChart(charts, "Shots per lens", s => val(s, "lens"), rows);
  hBarChart(charts, "Shots per camera", s => val(s, "camera_model"), rows);
  hBarChart(charts, "Shots per folder", s => val(s, "top_folder"), rows);
  timeChart(charts, rows);
}

document.getElementById("meta-line").textContent =
  `${fmt(ALL.length)} shots · scanned ${PAYLOAD.meta.scanned_at} · exif-dashboard ${PAYLOAD.meta.tool_version}`;
document.getElementById("footnote").textContent =
  N_DERIV ? `${fmt(N_DERIV)} derivative files (−Edit, −HDR, …) excluded from all charts.` : "";
buildFilters();
renderAll();
