/* Fantasy Football Lab: a phone-first version of the Power BI report.
   Data comes from site/data/*.json (built by scripts/build_site_data.py). */
"use strict";

const POSITIONS = ["WR", "RB", "QB", "TE"];
const POS_NAME = { WR: "Wide receivers", RB: "Running backs", QB: "Quarterbacks", TE: "Tight ends" };
const POS_SHAPE = { WR: "circle", RB: "triangle", QB: "rect", TE: "rectRot" };
const MATCHUP_SEASONS = [2025, 2026];

// ---------------------------------------------------------------- data
const cache = {};
async function load(name) {
  if (!cache[name]) {
    cache[name] = fetch(`data/${name}.json`).then(r => {
      if (!r.ok) throw new Error(`${name}: ${r.status}`);
      return r.json();
    }).then(({ columns, rows }) => rows.map(r => Object.fromEntries(columns.map((c, i) => [c, r[i]]))));
  }
  return cache[name];
}

// ---------------------------------------------------------------- helpers
const $ = (sel, root = document) => root.querySelector(sel);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const posColor = p => css(`--${p.toLowerCase()}`);
const fmt = (v, d = 1) => (v == null || Number.isNaN(v) ? "–" : v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }));
const pct = (v, d = 0) => (v == null || Number.isNaN(v) ? "–" : `${(v * 100).toFixed(d)}%`);
const signed = (v, d = 1) => (v == null || Number.isNaN(v) ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}`);
const sum = (a, f) => a.reduce((s, r) => s + (f(r) || 0), 0);
const mean = (a, f) => { const v = a.map(f).filter(x => x != null); return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null; };
function groupBy(a, key) { const m = new Map(); for (const r of a) { const k = key(r); if (!m.has(k)) m.set(k, []); m.get(k).push(r); } return m; }
function pearson(xs, ys) {
  const n = xs.length; if (n < 10) return null;
  const mx = xs.reduce((s, x) => s + x, 0) / n, my = ys.reduce((s, y) => s + y, 0) / n;
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i++) { const dx = xs[i] - mx, dy = ys[i] - my; sxy += dx * dy; sxx += dx * dx; syy += dy * dy; }
  return sxx && syy ? sxy / Math.sqrt(sxx * syy) : null;
}
const linkPhrase = r => (Math.abs(r) >= 0.6 ? "a strong link" : Math.abs(r) >= 0.4 ? "a moderate link" : Math.abs(r) >= 0.2 ? "a weak link" : "almost no link");
const strength = r => (r == null ? "Not enough seasons" : Math.abs(r) >= 0.6 ? "Strong link" : Math.abs(r) >= 0.4 ? "Moderate link" : Math.abs(r) >= 0.2 ? "Weak link" : "Almost no link");

// Controls ------------------------------------------------------------
function chips(el, label, options, value, onChange, { dots = false } = {}) {
  const wrap = document.createElement("div"); wrap.className = "control";
  wrap.innerHTML = `<div class="clabel">${esc(label)}</div><div class="chips" role="group" aria-label="${esc(label)}"></div>`;
  const box = $(".chips", wrap);
  for (const o of options) {
    const [val, text] = Array.isArray(o) ? o : [o, o];
    const b = document.createElement("button");
    b.className = "chip"; b.type = "button"; b.setAttribute("aria-pressed", String(val === value));
    b.innerHTML = (dots && POS_NAME[val] ? `<span class="dot" style="background:${posColor(val)}"></span>` : "") + esc(text);
    b.onclick = () => { box.querySelectorAll(".chip").forEach(c => c.setAttribute("aria-pressed", "false")); b.setAttribute("aria-pressed", "true"); onChange(val); };
    box.appendChild(b);
  }
  el.appendChild(wrap);
}

function range(el, label, min, max, step, value, onChange, show = v => v, { onRelease = false } = {}) {
  // value: [lo, hi] for a two-thumb range, or a number for a single slider.
  // onRelease: apply only when the thumb is let go (for views that redraw their own controls).
  const dual = Array.isArray(value);
  const wrap = document.createElement("div"); wrap.className = "control";
  wrap.innerHTML = `<div class="clabel"><span>${esc(label)}</span><span class="cval"></span></div>
    <div class="range"><div class="track"></div><div class="fill"></div>
    <input type="range" min="${min}" max="${max}" step="${step}" aria-label="${esc(label)}${dual ? " minimum" : ""}">
    ${dual ? `<input type="range" min="${min}" max="${max}" step="${step}" aria-label="${esc(label)} maximum">` : ""}</div>`;
  const [a, b] = wrap.querySelectorAll("input"), fill = $(".fill", wrap), out = $(".cval", wrap);
  a.value = dual ? value[0] : value; if (b) b.value = value[1];
  const paint = () => {
    let lo = +a.value, hi = b ? +b.value : max;
    if (b && lo > hi) [lo, hi] = [hi, lo];
    const p = v => ((v - min) / (max - min)) * 100;
    fill.style.left = `${dual ? p(lo) : 0}%`; fill.style.right = `${100 - p(dual ? hi : lo)}%`;
    out.textContent = dual ? `${show(lo)} – ${show(hi)}` : show(lo);
    return dual ? [lo, hi] : lo;
  };
  let t;
  const fire = () => { const v = paint(); clearTimeout(t); t = setTimeout(() => onChange(v), 60); };
  for (const inp of [a, b].filter(Boolean)) {
    if (onRelease) { inp.oninput = paint; inp.onchange = () => onChange(paint()); } else inp.oninput = fire;
  }
  paint();
  el.appendChild(wrap);
}

function select(el, label, options, value, onChange) {
  const wrap = document.createElement("div"); wrap.className = "control";
  wrap.innerHTML = `<label class="clabel">${esc(label)}</label><select></select>`;
  const s = $("select", wrap); s.setAttribute("aria-label", label);
  s.innerHTML = options.map(([v, t]) => `<option value="${esc(v)}"${v === value ? " selected" : ""}>${esc(t)}</option>`).join("");
  s.onchange = () => onChange(s.value);
  el.appendChild(wrap);
}

function stat(label, value, sub = "") {
  return `<div class="stat"><div class="label">${esc(label)}</div><div class="value">${value}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;
}

function rankedBars(rows, { value, label, sub, show, color, limit = 25 }) {
  if (!rows.length) return `<div class="empty">Nothing matches these filters.</div>`;
  const top = rows.slice(0, limit), maxV = Math.max(...top.map(r => Math.abs(value(r)))) || 1;
  return `<div class="bars">${top.map((r, i) => `<div class="bar-row">
      <div class="name">${i + 1}. ${esc(label(r))} ${sub ? `<small>${esc(sub(r))}</small>` : ""}</div>
      <div class="num">${show(value(r))}</div>
      <div class="track"><span style="width:${(Math.abs(value(r)) / maxV) * 100}%;background:${color}"></span></div>
    </div>`).join("")}</div>${rows.length > limit ? `<p class="note">Top ${limit} of ${rows.length}.</p>` : ""}`;
}

// Charts --------------------------------------------------------------
const charts = new Set();
function chart(canvas, config) {
  const ink2 = css("--text-2"), grid = css("--grid");
  Chart.defaults.color = ink2;
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.borderColor = grid;
  const c = new Chart(canvas, Object.assign({ options: {} }, config));
  charts.add(c);
  return c;
}
function clearCharts() { charts.forEach(c => c.destroy()); charts.clear(); }
const axis = (title, extra = {}) => ({ title: { display: !!title, text: title }, grid: { color: css("--grid") }, border: { color: css("--baseline") }, ...extra });

// ---------------------------------------------------------------- views
const VIEWS = [
  ["past", "Past → Future", viewPast],
  ["similar", "Similar Players", viewSimilar],
  ["history", "27 Seasons", viewHistory],
  ["player", "Players", viewPlayer],
  ["week", "This Week", viewWeek],
  ["wrcb", "WR vs CB", viewWrCb],
  ["matchups", "Matchups", viewMatchups],
];

// 1. Past -> Future -----------------------------------------------------
const STATS = {
  "PPG": { col: "ppg", show: v => fmt(v, 1), axis: "PPG this season" },
  "Touches/G": { col: "touches_pg", show: v => fmt(v, 1), axis: "Touches per game" },
  "Targets/G": { col: "targets_pg", show: v => fmt(v, 1), axis: "Targets per game (none 2003-08)" },
  "TDs/G": { col: "td_pg", show: v => fmt(v, 2), axis: "Touchdowns per game" },
  "TD rate": { col: "td_rate", show: v => pct(v, 1), axis: "Touchdowns per touch" },
  "Snap share": { col: "snap_pct", show: v => pct(v), axis: "Snap share (2013+)" },
  "Age": { col: "age_years", show: v => fmt(v, 0), axis: "Age" },
};
const past = { pos: "All", stat: "PPG", seasons: [1999, 2024], minGames: 6 };

async function viewPast(root) {
  root.innerHTML = `<h2 class="view-title">Does this season predict next season?</h2>
    <p class="view-sub">Each dot is one player-season, plotted against the same player's PPG the following year.</p>
    <div class="layout"><aside class="panel" id="ctl"></aside><section id="out"></section></div>`;
  const ctl = $("#ctl", root), out = $("#out", root);
  const all = (await load("seasons")).filter(r => r.has_next === 1);
  const draw = () => {
    clearCharts();
    const s = STATS[past.stat];
    const rows = all.filter(r => (past.pos === "All" || r.position === past.pos) && r.season >= past.seasons[0]
      && r.season <= past.seasons[1] && r.games >= past.minGames && r[s.col] != null);
    const r = pearson(rows.map(d => d[s.col]), rows.map(d => d.next_ppg));
    const who = past.pos === "All" ? "all positions" : POS_NAME[past.pos].toLowerCase();
    out.innerHTML = `<div class="stats">
        ${stat("Correlation (r)", r == null ? "–" : r.toFixed(2), strength(r))}
        ${stat("Explains", r == null ? "–" : pct(r * r), "of next-season PPG differences")}
        ${stat("Player-seasons", rows.length.toLocaleString())}
        ${stat("Seasons", `${past.seasons[0]}–${past.seasons[1]}`)}
      </div>
      <div class="insight">For ${who}, <b>${esc(past.stat)}</b> this season ${r == null ? "doesn't have enough data here" :
        `has <b>${linkPhrase(r)}</b> to next season's PPG (r = ${r.toFixed(2)})`}.
        ${past.stat === "TD rate" ? "Touchdown rate swings a lot from year to year." : past.stat === "PPG" ? "Try Touches/G or TD rate to compare." : ""}</div>
      <div class="panel"><h3>${esc(past.stat)} this season vs. PPG next season</h3>
        <p class="hint">Tap a dot for the player. Colors and shapes mark positions.</p>
        <div class="legend">${POSITIONS.filter(p => past.pos === "All" || p === past.pos).map(p => `<span style="--c:${posColor(p)}">${p}</span>`).join("")}</div>
        <div class="chart tall"><canvas aria-label="Scatter of ${esc(past.stat)} vs next-season PPG"></canvas></div></div>
      <div class="panel"><h3>Is the link stable over time?</h3><p class="hint">r for each season (needs 10+ player-seasons).</p>
        <div class="chart short"><canvas aria-label="Correlation by season"></canvas></div></div>`;
    const [sc, ln] = out.querySelectorAll("canvas");
    // Cap the x-axis at the 99th percentile so a few tiny samples (1 touch, 1 TD) don't squash the plot.
    const xs = rows.map(d => d[s.col]).sort((a, b) => a - b), xMax = xs.length ? xs[Math.floor(xs.length * 0.99)] * 1.05 : undefined;
    const small = innerWidth < 600;
    chart(sc, {
      type: "scatter",
      data: { datasets: POSITIONS.filter(p => past.pos === "All" || p === past.pos).map(p => ({
        label: p, pointStyle: POS_SHAPE[p], backgroundColor: posColor(p) + (past.pos === "All" ? "66" : "99"), borderColor: posColor(p),
        pointRadius: small ? 2.2 : 3, pointHoverRadius: 6, borderWidth: 0.5,
        data: rows.filter(d => d.position === p).map(d => ({ x: d[s.col], y: d.next_ppg, d })) })) },
      options: { maintainAspectRatio: false, animation: false, plugins: { legend: { display: false },
        tooltip: { callbacks: { label: c => { const d = c.raw.d; return `${d.player} ${d.season}: ${s.show(d[s.col])} → ${fmt(d.next_ppg)} PPG`; } } } },
        scales: { x: axis(s.axis, { min: s.col === "age_years" ? undefined : 0, max: s.col === "age_years" ? undefined : xMax, ...(s.col === "td_rate" || s.col === "snap_pct" ? { ticks: { callback: v => pct(v) } } : {}) }), y: axis("Next-season PPG", { min: 0 }) } },
    });
    const bySeason = [...groupBy(rows, d => d.season)].sort((a, b) => a[0] - b[0])
      .map(([season, g]) => ({ x: season, y: pearson(g.map(d => d[s.col]), g.map(d => d.next_ppg)) })).filter(p => p.y != null);
    chart(ln, { type: "line", data: { datasets: [{ data: bySeason, borderColor: css("--accent"), backgroundColor: css("--accent"), borderWidth: 2, pointRadius: 2.5, tension: 0 }] },
      options: { maintainAspectRatio: false, animation: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `r = ${c.parsed.y.toFixed(2)}` } } },
        scales: { x: axis("", { type: "linear", min: past.seasons[0], max: past.seasons[1], ticks: { callback: v => String(v), stepSize: 5 } }), y: axis("r", { suggestedMin: 0, suggestedMax: 1 }) } } });
  };
  chips(ctl, "Position", ["All", ...POSITIONS], past.pos, v => { past.pos = v; draw(); }, { dots: true });
  chips(ctl, "This-season stat", Object.keys(STATS), past.stat, v => { past.stat = v; draw(); });
  range(ctl, "Seasons", 1999, 2024, 1, past.seasons, v => { past.seasons = v; draw(); });
  range(ctl, "Minimum games played", 1, 17, 1, past.minGames, v => { past.minGames = v; draw(); });
  draw();
}

// 2. Similar players --------------------------------------------------
const sim = { pos: "All", age: [20, 40], ppg: [0, 35], touches: [0, 35], tds: [0, 2], games: [1, 17] };
async function viewSimilar(root) {
  root.innerHTML = `<h2 class="view-title">If a player looks like this, what happened next year?</h2>
    <p class="view-sub">Slide to describe a season. Every matching player-season from 1999-2024 is checked against the year after.</p>
    <div class="layout"><aside class="panel" id="ctl"></aside><section id="out"></section></div>`;
  const ctl = $("#ctl", root), out = $("#out", root);
  const data = await load("seasons");
  const match = r => (sim.pos === "All" || r.position === sim.pos) && r.age_years >= sim.age[0] && r.age_years <= sim.age[1]
    && r.ppg >= sim.ppg[0] && r.ppg <= sim.ppg[1] && r.touches_pg >= sim.touches[0] && r.touches_pg <= sim.touches[1]
    && r.td_pg >= sim.tds[0] && r.td_pg <= sim.tds[1] && r.games >= sim.games[0] && r.games <= sim.games[1];
  const draw = () => {
    const hist = data.filter(r => r.has_next === 1 && match(r));
    const now = data.filter(r => r.season === 2025 && r.proj_next_ppg != null && match(r)).sort((a, b) => b.proj_next_ppg - a.proj_next_ppg);
    const improved = hist.length ? hist.filter(r => r.ppg_change > 0).length / hist.length : null;
    const top12 = hist.length ? hist.filter(r => r.next_pos_rank != null && r.next_pos_rank <= 12).length / hist.length : null;
    const change = mean(hist, r => r.ppg_change);
    const best = [...hist].sort((a, b) => b.ppg - a.ppg).slice(0, 20);
    out.innerHTML = `<div class="stats">
        ${stat("Matching seasons", hist.length.toLocaleString())}
        ${stat("Improved next year", pct(improved))}
        ${stat("Average PPG change", `<span class="${change > 0 ? "up" : change < 0 ? "down" : ""}">${signed(change)}</span>`)}
        ${stat("Top-12 at position", pct(top12), "the next season")}
      </div>
      <div class="grid2">
        <div class="panel"><h3>Matching seasons, and what came next</h3><p class="hint">Highest PPG first.</p>
          ${best.length ? `<ul class="list">${best.map(r => `<li><div class="who"><b>${esc(r.player)}</b><small>${r.season} · ${r.position} · age ${r.age_years} · ${r.team}</small></div>
            <div class="right">${fmt(r.ppg)} → ${fmt(r.next_ppg)}<small class="${r.ppg_change > 0 ? "up" : "down"}">${signed(r.ppg_change)}</small></div></li>`).join("")}</ul>` : `<div class="empty">No seasons match. Widen a slider.</div>`}
        </div>
        <div class="panel"><h3>2025 players who fit → 2026</h3><p class="hint">Season-model projection, and 2026 so far.</p>
          ${now.length ? `<ul class="list">${now.slice(0, 20).map(r => `<li><div class="who"><b>${esc(r.player)}</b><small>${r.position} · ${r.team} · age ${r.age_years} · 2025: ${fmt(r.ppg)} PPG</small></div>
            <div class="right">${fmt(r.proj_next_ppg)} proj<small>${r.current_ppg != null ? `${fmt(r.current_ppg)} so far (${r.current_games} g)` : "no 2026 games"}</small></div></li>`).join("")}</ul>` : `<div class="empty">No 2025 players match.</div>`}
        </div>
      </div>`;
  };
  chips(ctl, "Position", ["All", ...POSITIONS], sim.pos, v => { sim.pos = v; draw(); }, { dots: true });
  range(ctl, "Age that season", 20, 40, 1, sim.age, v => { sim.age = v; draw(); });
  range(ctl, "PPG", 0, 35, 0.5, sim.ppg, v => { sim.ppg = v; draw(); });
  range(ctl, "Touches per game", 0, 35, 0.5, sim.touches, v => { sim.touches = v; draw(); });
  range(ctl, "Touchdowns per game", 0, 2, 0.05, sim.tds, v => { sim.tds = v; draw(); }, v => v.toFixed(2));
  range(ctl, "Games played", 1, 17, 1, sim.games, v => { sim.games = v; draw(); });
  draw();
}

// 3. History --------------------------------------------------------
const hist = { seasons: [1999, 2026], pos: "All" };
async function viewHistory(root) {
  root.innerHTML = `<h2 class="view-title">27 seasons of fantasy football</h2>
    <p class="view-sub">How the sources of fantasy points shifted, the workhorse back, and how players age. 2026 is partial.</p>
    <div class="layout"><aside class="panel" id="ctl"></aside><section id="out"></section></div>`;
  const ctl = $("#ctl", root), out = $("#out", root);
  const data = await load("seasons");
  const draw = () => {
    clearCharts();
    const shown = POSITIONS.filter(p => hist.pos === "All" || p === hist.pos);
    const inRange = data.filter(r => r.season >= hist.seasons[0] && r.season <= hist.seasons[1]);
    const seasons = [...new Set(inRange.map(r => r.season))].sort((a, b) => a - b);
    const bySeason = groupBy(inRange.filter(r => r.top150 === 1), r => r.season);
    const share = p => seasons.map(s => { const g = bySeason.get(s) || []; return { x: s, y: sum(g.filter(r => r.position === p), r => r.ppr_points) / sum(g, r => r.ppr_points) }; });
    const work = seasons.map(s => ({ x: s, y: inRange.filter(r => r.season === s && r.position === "RB" && r.carries >= 300).length }));
    const pairs = data.filter(r => r.has_next === 1 && r.games >= 8 && r.next_games >= 8 && r.season >= hist.seasons[0] && r.season <= hist.seasons[1]);
    const aging = p => [...groupBy(pairs.filter(r => r.position === p), r => r.age_years)].filter(([, g]) => g.length >= 20)
      .map(([age, g]) => ({ x: age, y: mean(g, r => r.ppg_change) })).sort((a, b) => a.x - b.x);
    out.innerHTML = `<div class="panel"><h3>Share of top-150 fantasy points</h3><p class="hint">Top 150 PPR scorers each season, by position.</p>
        <div class="legend">${shown.map(p => `<span style="--c:${posColor(p)}">${POS_NAME[p]}</span>`).join("")}</div>
        <div class="chart"><canvas aria-label="Position share by season"></canvas></div></div>
      <div class="grid2">
        <div class="panel"><h3>300-carry running backs</h3><p class="hint">Per season.</p><div class="chart short"><canvas aria-label="300-carry backs by season"></canvas></div></div>
        <div class="panel"><h3>Aging: PPG change to the next season</h3><p class="hint">By age, players with 8+ games both years (20+ players per age). Below 0 = usually declines.</p>
          <div class="legend">${shown.map(p => `<span style="--c:${posColor(p)}">${p}</span>`).join("")}</div>
          <div class="chart short"><canvas aria-label="Aging curves"></canvas></div></div>
      </div>`;
    const [a, b, c] = out.querySelectorAll("canvas");
    const line = (p, d) => ({ label: p, data: d, borderColor: posColor(p), backgroundColor: posColor(p), borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0 });
    const lin = (title, extra = {}) => axis(title, { type: "linear", ticks: { callback: v => String(v) }, ...extra });
    const years = { min: seasons[0], max: seasons[seasons.length - 1] };
    chart(a, { type: "line", data: { datasets: shown.map(p => line(p, share(p))) },
      options: { maintainAspectRatio: false, animation: false, interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false }, tooltip: { callbacks: { title: i => String(i[0].parsed.x), label: i => `${i.dataset.label}: ${pct(i.parsed.y)}` } } },
        scales: { x: lin("", years), y: axis("", { min: 0, ticks: { callback: v => pct(v) } }) } } });
    chart(b, { type: "bar", data: { datasets: [{ data: work, backgroundColor: posColor("RB"), borderRadius: 3 }] },
      options: { maintainAspectRatio: false, animation: false, plugins: { legend: { display: false }, tooltip: { callbacks: { title: i => String(i[0].parsed.x), label: i => `${i.parsed.y} RBs` } } },
        scales: { x: lin("", { ...years, offset: true, grid: { display: false } }), y: axis("", { beginAtZero: true, ticks: { precision: 0 } }) } } });
    chart(c, { type: "line", data: { datasets: shown.map(p => ({ ...line(p, aging(p)), pointRadius: 2.5 })) },
      options: { maintainAspectRatio: false, animation: false, interaction: { mode: "nearest", intersect: false },
        plugins: { legend: { display: false }, tooltip: { callbacks: { title: i => `Age ${i[0].parsed.x}`, label: i => `${i.dataset.label}: ${signed(i.parsed.y)} PPG` } } },
        scales: { x: lin("Age"), y: axis("PPG change") } } });
  };
  chips(ctl, "Positions", ["All", ...POSITIONS], hist.pos, v => { hist.pos = v; draw(); }, { dots: true });
  range(ctl, "Seasons", 1999, 2026, 1, hist.seasons, v => { hist.seasons = v; draw(); });
  draw();
}

// 4. Player explorer --------------------------------------------------
let playerLabel = null;
async function viewPlayer(root) {
  root.innerHTML = `<h2 class="view-title">Player explorer</h2>
    <p class="view-sub">Any player since 1999: PPG by season vs. the top-24 average at their position.</p>
    <div class="panel search-wrap"><label class="clabel" for="q" style="display:block;font-size:13px;font-weight:600;color:var(--text-2);margin-bottom:6px">Search a player</label>
      <input id="q" type="search" placeholder="e.g. Ja'Marr Chase" autocomplete="off"><ul class="suggest" id="sug"></ul></div>
    <section id="out"></section>`;
  const data = await load("seasons");
  const byLabel = groupBy(data, r => r.player_label);
  const labels = [...byLabel.keys()];
  const top24 = new Map();
  for (const [k, g] of groupBy(data.filter(r => r.pos_rank <= 24), r => `${r.season}|${r.position}`)) top24.set(k, sum(g, r => r.ppr_points) / sum(g, r => r.games));
  playerLabel ||= labels.find(l => l.startsWith("Ja'Marr Chase")) || labels[0];
  const q = $("#q", root), sug = $("#sug", root), out = $("#out", root);
  const draw = () => {
    clearCharts();
    const rows = [...byLabel.get(playerLabel)].sort((a, b) => a.season - b.season);
    const done = rows.filter(r => r.season < 2026);
    const last = rows.find(r => r.season === 2025), pos = rows[rows.length - 1].position;
    const best = rows.filter(r => r.games >= 6).sort((a, b) => b.ppg - a.ppg)[0];
    out.innerHTML = `<div class="stats">
        ${stat("Career PPG", fmt(sum(done, r => r.ppr_points) / sum(done, r => r.games)), `${sum(done, r => r.games)} games`)}
        ${stat("Best season", best ? fmt(best.ppg) : "–", best ? `${best.season}` : "")}
        ${stat("2026 projection", last?.proj_next_ppg != null ? fmt(last.proj_next_ppg) : "–", "season model, from 2025")}
        ${stat("2026 so far", last?.current_ppg != null ? fmt(last.current_ppg) : fmt(rows.find(r => r.season === 2026)?.ppg), "PPG")}
      </div>
      <div class="panel"><h3>${esc(playerLabel)}</h3><div class="legend"><span style="--c:${posColor(pos)}">PPG</span><span style="--c:${css("--muted")}">Top-24 ${pos} average</span></div>
        <div class="chart"><canvas aria-label="PPG by season"></canvas></div></div>
      <div class="panel"><h3>Season by season</h3><div class="scroll"><table><thead><tr><th>Season</th><th>Team</th><th>Age</th><th>G</th><th>PPG</th><th>Rank</th><th>Touch/G</th><th>Tgt/G</th><th>TD/G</th><th>Snap</th></tr></thead>
        <tbody>${[...rows].reverse().map(r => `<tr><td>${r.season}</td><td>${r.team}</td><td>${r.age_years}</td><td>${r.games}</td><td><b>${fmt(r.ppg)}</b></td><td>${r.position}${r.pos_rank}</td><td>${fmt(r.touches_pg)}</td><td>${fmt(r.targets_pg)}</td><td>${fmt(r.td_pg, 2)}</td><td>${pct(r.snap_pct)}</td></tr>`).join("")}</tbody></table></div></div>`;
    chart($("canvas", out), { type: "line", data: { datasets: [
      { label: "PPG", data: rows.map(r => ({ x: r.season, y: r.ppg })), borderColor: posColor(pos), backgroundColor: posColor(pos), borderWidth: 2, pointRadius: 3 },
      { label: `Top-24 ${pos} avg`, data: rows.map(r => ({ x: r.season, y: top24.get(`${r.season}|${r.position}`) })), borderColor: css("--muted"), backgroundColor: css("--muted"), borderWidth: 2, borderDash: [5, 4], pointRadius: 0 }] },
      options: { maintainAspectRatio: false, animation: false, interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false }, tooltip: { callbacks: { title: i => String(i[0].parsed.x), label: i => `${i.dataset.label}: ${fmt(i.parsed.y)}` } } },
        scales: { x: axis("", { type: "linear", ticks: { callback: v => String(v), stepSize: 1 } }), y: axis("PPG", { min: 0 }) } } });
  };
  q.oninput = () => {
    const t = q.value.trim().toLowerCase();
    const hits = t.length < 2 ? [] : labels.filter(l => l.toLowerCase().includes(t)).slice(0, 8);
    sug.innerHTML = hits.map(l => `<li><button type="button">${esc(l)}</button></li>`).join("");
    sug.querySelectorAll("button").forEach((b, i) => b.onclick = () => { playerLabel = hits[i]; q.value = ""; sug.innerHTML = ""; draw(); });
  };
  draw();
}

// 5. This week --------------------------------------------------------
const wk = { pos: "WR", min: 0 };
async function viewWeek(root) {
  const [rows, back] = await Promise.all([load("week"), load("backtest")]);
  const label = rows.length ? `${rows[0].season} week ${rows[0].week}` : "This week";
  root.innerHTML = `<h2 class="view-title">${label} projections</h2>
    <p class="view-sub">PPR projections from the weekly model (ridge regression with snap share and injury reports).</p>
    <div class="layout"><aside class="panel" id="ctl"></aside><section id="out"></section></div>`;
  const ctl = $("#ctl", root), out = $("#out", root);
  const acc = k => mean(back, r => r[k]);
  const draw = () => {
    clearCharts();
    const list = rows.filter(r => r.position === wk.pos && r.projection >= wk.min).sort((a, b) => b.projection - a.projection);
    out.innerHTML = `<div class="stats">
        ${stat("Model start/sit", pct(acc("model_start_sit"), 1), "2026 weeks so far")}
        ${stat("Season average", pct(acc("season_avg_start_sit"), 1), "same pairs, 50% = coin flip")}
      </div>
      <div class="panel"><h3>${POS_NAME[wk.pos]}</h3><p class="hint">Projection, with season and last-3 averages. Tags come from the injury report once it's out.</p>
        ${list.length ? `<ul class="list">${list.map(r => `<li><div class="who"><b>${r.pos_rank}. ${esc(r.player)}${r.injury ? `<span class="tag">${esc(r.injury)}</span>` : ""}</b>
          <small>${r.team} vs ${r.opponent} · team total ${fmt(r.implied_total)}${r.no_line === "True" || r.no_line === true ? "†" : ""} · avg ${fmt(r.avg_season)} · last 3 ${fmt(r.avg_last3)}</small></div>
          <div class="right"><b style="font-size:17px">${fmt(r.projection)}</b><small>proj</small></div></li>`).join("")}</ul>` : `<div class="empty">No players above that projection.</div>`}
        ${rows.some(r => r.no_line === "True" || r.no_line === true) ? `<p class="note">† No Vegas line yet; the week's average team total was used.</p>` : ""}</div>
      <div class="panel"><h3>2026 so far: start/sit accuracy by week</h3><div class="legend"><span style="--c:${css("--accent")}">Model</span><span style="--c:${css("--baseline")}">Season average</span></div>
        <div class="chart short"><canvas aria-label="Accuracy by week"></canvas></div></div>`;
    chart($("canvas", out), { type: "bar", data: { labels: back.map(r => `Wk ${r.week}`), datasets: [
      { label: "Model", data: back.map(r => r.model_start_sit), backgroundColor: css("--accent"), borderRadius: 3 },
      { label: "Season average", data: back.map(r => r.season_avg_start_sit), backgroundColor: css("--baseline"), borderRadius: 3 }] },
      options: { maintainAspectRatio: false, animation: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: i => `${i.dataset.label}: ${pct(i.parsed.y, 1)}` } } },
        scales: { x: axis("", { grid: { display: false } }), y: axis("", { min: 0.5, ticks: { callback: v => pct(v) } }) } } });
  };
  chips(ctl, "Position", POSITIONS, wk.pos, v => { wk.pos = v; draw(); }, { dots: true });
  range(ctl, "Minimum projection", 0, 25, 0.5, wk.min, v => { wk.min = v; draw(); });
  draw();
}

// 6-7. WR vs CB, Matchups (shared filters) ----------------------------
let filtersOpen = false;
const mf = { season: "All", weeks: [1, 18], game: "", offense: "", defense: "", side: "All", wrStat: "Success rate", wrMin: 20, cbStat: "Yards allowed", cbMin: 15, cbOrder: "Most" };
async function matchupData() {
  const [games, receivers, targets, wrGames, cbGames] = await Promise.all(["games", "receivers", "targets", "wr_games", "cb_games"].map(load));
  return { games, receivers: new Map(receivers.map(r => [r.receiver_id, r.receiver_label])), targets, wrGames, cbGames };
}
function matchupFilters(el, d, redraw) {
  const det = document.createElement("details"); det.className = "filters"; det.open = innerWidth >= 860 || filtersOpen;
  det.ontoggle = () => { if (innerWidth < 860) filtersOpen = det.open; };
  const active = [mf.season !== "All", mf.weeks[0] > 1 || mf.weeks[1] < 18, mf.game, mf.offense, mf.defense, mf.side !== "All"].filter(Boolean).length;
  det.innerHTML = `<summary>Filters${active ? ` (${active} on)` : ""}</summary><div class="body"></div>`;
  const body = $(".body", det);
  const teams = [...new Set(d.targets.map(r => r.offense))].sort();
  const gameOpts = d.games.filter(g => (mf.season === "All" || g.season === +mf.season) && g.week >= mf.weeks[0] && g.week <= mf.weeks[1]).map(g => [g.game_id, g.label]);
  chips(body, "Season", ["All", ...MATCHUP_SEASONS.map(String)], mf.season, v => { mf.season = v; mf.game = ""; redraw(); });
  range(body, "Weeks", 1, 18, 1, mf.weeks, v => { mf.weeks = v; mf.game = ""; redraw(); }, String, { onRelease: true });
  select(body, "Game", [["", "All games"], ...gameOpts], mf.game, v => { mf.game = v; redraw(); });
  select(body, "Offense (receivers' team)", [["", "All teams"], ...teams.map(t => [t, t])], mf.offense, v => { mf.offense = v; redraw(); });
  select(body, "Defense (corners' team)", [["", "All teams"], ...teams.map(t => [t, t])], mf.defense, v => { mf.defense = v; redraw(); });
  chips(body, "Side of field (offense's view)", ["All", "Left", "Middle", "Right"], mf.side, v => { mf.side = v; redraw(); });
  el.appendChild(det);
}
function gameSet(d) {
  return new Set(d.games.filter(g => (mf.season === "All" || g.season === +mf.season) && g.week >= mf.weeks[0] && g.week <= mf.weeks[1]
    && (!mf.game || g.game_id === mf.game)).map(g => g.game_id));
}
function filteredTargets(d, ids) {
  return d.targets.filter(r => ids.has(r.game_id) && (!mf.offense || r.offense === mf.offense) && (!mf.defense || r.defense === mf.defense)
    && (mf.side === "All" || r.side === mf.side));
}
const WR_STATS = {
  "Success rate": { v: g => g.succ / g.tg, show: v => pct(v, 1) },
  "Receiving yards": { v: g => g.yds, show: v => fmt(v, 0) },
  "Yards per target": { v: g => g.yds / g.tg, show: v => fmt(v, 1) },
  "Catch rate": { v: g => g.rec / g.tg, show: v => pct(v, 1) },
  "Targets": { v: g => g.tg, show: v => fmt(v, 0) },
  "Separation": { v: g => g.sep, show: v => `${fmt(v, 2)} yd` },
};
const CB_STATS = {
  "Yards allowed": { v: g => g.yds, show: v => fmt(v, 0) },
  "Yards/target allowed": { v: g => g.yds / g.tg, show: v => fmt(v, 1) },
  "Catch % allowed": { v: g => g.comp / g.tg, show: v => pct(v, 1) },
  "Passer rating allowed": { v: g => g.rating / g.tg, show: v => fmt(v, 1) },
  "Targets": { v: g => g.tg, show: v => fmt(v, 0) },
  "TDs allowed": { v: g => g.tds, show: v => fmt(v, 0) },
};

async function viewWrCb(root) {
  root.innerHTML = `<h2 class="view-title">Receivers vs. corners (2025-2026)</h2>
    <p class="view-sub">Pick a stat for each side; filter by season, weeks, game, team and side of the field.</p>
    <div class="layout"><aside id="ctl"></aside><section id="out"></section></div>`;
  const d = await matchupData();
  const redraw = () => viewWrCb(root);
  matchupFilters($("#ctl", root), d, redraw);
  const out = $("#out", root), ids = gameSet(d);
  const tg = filteredTargets(d, ids);
  const sep = new Map();
  for (const [id, g] of groupBy(d.wrGames.filter(r => ids.has(r.game_id) && (!mf.offense || r.team === mf.offense) && (!mf.defense || r.opponent === mf.defense)), r => r.receiver_id))
    sep.set(id, sum(g, r => r.avg_separation * r.targets) / sum(g, r => r.targets));
  const wr = [...groupBy(tg, r => r.receiver_id)].map(([id, g]) => ({ id, name: d.receivers.get(id) || id, tg: g.length, rec: sum(g, r => r.complete), yds: sum(g, r => r.yards), succ: sum(g, r => r.success), sep: sep.get(id) ?? null }));
  const ws = WR_STATS[mf.wrStat];
  const wrRows = wr.filter(g => g.tg >= Math.max(1, mf.wrMin) && ws.v(g) != null).sort((a, b) => ws.v(b) - ws.v(a));
  const cbAll = d.cbGames.filter(r => ids.has(r.game_id) && (!mf.offense || r.offense === mf.offense) && (!mf.defense || r.defense === mf.defense) && (mf.side === "All" || r.side === mf.side));
  const cb = [...groupBy(cbAll, r => `${r.cb}|${r.defense}`)].map(([k, g]) => ({ name: g[0].cb, team: [...new Set(g.map(r => r.defense))].join("/"), tg: sum(g, r => r.targets), comp: sum(g, r => r.completions), yds: sum(g, r => r.yards), tds: sum(g, r => r.tds), rating: sum(g, r => r.rating * r.targets) }));
  const cs = CB_STATS[mf.cbStat], dir = mf.cbOrder === "Most" ? -1 : 1;
  const cbRows = cb.filter(g => g.tg >= Math.max(1, mf.cbMin)).sort((a, b) => dir * (cs.v(a) - cs.v(b)));
  out.innerHTML = `<div class="grid2"><div class="panel" id="wrp"></div><div class="panel" id="cbp"></div></div>
    <p class="note">Receiver stats: every targeted pass (nflverse play-by-play); separation from Next Gen Stats and not split by side. Corner stats: Pro Football Reference coverage numbers (lower = better coverage). Separation allowed by corners isn't public.</p>`;
  const wrp = $("#wrp", out), cbp = $("#cbp", out);
  wrp.innerHTML = `<h3>Receivers</h3>`;
  chips(wrp, "Stat", Object.keys(WR_STATS), mf.wrStat, v => { mf.wrStat = v; redraw(); });
  range(wrp, "Minimum targets", 0, 150, 1, mf.wrMin, v => { mf.wrMin = v; redraw(); }, String, { onRelease: true });
  wrp.insertAdjacentHTML("beforeend", rankedBars(wrRows, { value: ws.v, label: g => g.name, sub: g => `${g.tg} tgt`, show: ws.show, color: css("--wr") }));
  cbp.innerHTML = `<h3>Corners</h3>`;
  chips(cbp, "Stat", Object.keys(CB_STATS), mf.cbStat, v => { mf.cbStat = v; redraw(); });
  chips(cbp, "Order", [["Most", "Highest first"], ["Least", "Lowest first"]], mf.cbOrder, v => { mf.cbOrder = v; redraw(); });
  range(cbp, "Minimum targets", 0, 120, 1, mf.cbMin, v => { mf.cbMin = v; redraw(); }, String, { onRelease: true });
  cbp.insertAdjacentHTML("beforeend", rankedBars(cbRows, { value: cs.v, label: g => g.name, sub: g => `${g.team} · ${g.tg} tgt`, show: cs.show, color: css("--cb") }));
}

async function viewMatchups(root) {
  root.innerHTML = `<h2 class="view-title">Where the targets go, and who was probably covering</h2>
    <p class="view-sub">Targets by side of the field, and receivers against the corner each defense listed on that side.</p>
    <div class="layout"><aside id="ctl"></aside><section id="out"></section></div>`;
  const d = await matchupData();
  const redraw = () => viewMatchups(root);
  matchupFilters($("#ctl", root), d, redraw);
  const out = $("#out", root), tg = filteredTargets(d, gameSet(d));
  const n = tg.length, sideRows = ["Left", "Middle", "Right"].map(s => { const g = tg.filter(r => r.side === s); return { s, tg: g.length, succ: g.length ? sum(g, r => r.success) / g.length : null }; });
  const pairs = [...groupBy(tg, r => `${r.receiver_id}|${r.est_cb}`)].map(([, g]) => ({ wr: d.receivers.get(g[0].receiver_id) || g[0].receiver_id, cb: g[0].est_cb, slot: g[0].est_cb_slot, def: g[0].defense, tg: g.length, yds: sum(g, r => r.yards), succ: sum(g, r => r.success) / g.length, rec: sum(g, r => r.complete) }))
    .sort((a, b) => b.tg - a.tg || b.yds - a.yds);
  out.innerHTML = `<div class="stats">
      ${stat("Targets", n.toLocaleString())}
      ${stat("Success rate", n ? pct(sum(tg, r => r.success) / n, 1) : "–")}
      ${stat("Yards per target", n ? fmt(sum(tg, r => r.yards) / n) : "–")}
      ${stat("Catch rate", n ? pct(sum(tg, r => r.complete) / n, 1) : "–")}
    </div>
    <div class="grid2">
      <div class="panel"><h3>By side of the field</h3><p class="hint">Offense's view: left is across from the defense's right corner.</p>
        ${sideRows.map(s => `<div class="bar-row" style="margin-bottom:10px"><div class="name"><b>${s.s}</b> <small>${s.s === "Middle" ? "vs nickel" : s.s === "Left" ? "vs RCB" : "vs LCB"}</small></div>
          <div class="num">${s.tg.toLocaleString()} tgt · ${pct(s.succ, 0)} success</div>
          <div class="track"><span style="width:${n ? (s.tg / n) * 100 : 0}%;background:${css("--wr")}"></span></div></div>`).join("")}
      </div>
      <div class="panel"><h3>About these matchups</h3><p class="hint" style="margin:0">Estimated: a pass to the offense's left is credited to the defense's listed right corner, middle to the nickel, right to the left corner (depth chart before each game). Real coverage assignments aren't public, and corners shadow and switch sides; on 2025-26 data the listed sides only weakly track where passes go (r ≈ 0.1). Treat this as a rough guide.</p></div>
    </div>
    <div class="panel"><h3>Receiver vs. estimated corner</h3><p class="hint">Most targets first.</p>
      ${pairs.length ? `<ul class="list">${pairs.slice(0, 40).map(p => `<li><div class="who"><b>${esc(p.wr)}</b><small>vs ${esc(p.cb)} (${p.def} ${p.slot})</small></div>
        <div class="right">${p.tg} tgt · ${fmt(p.yds, 0)} yds<small>${pct(p.succ)} success · ${pct(p.rec / p.tg)} caught</small></div></li>`).join("")}</ul>` : `<div class="empty">Nothing matches these filters.</div>`}
      ${pairs.length > 40 ? `<p class="note">Top 40 of ${pairs.length} pairs.</p>` : ""}</div>`;
}

// ---------------------------------------------------------------- router
async function route() {
  const key = location.hash.slice(1) || "past";
  const v = VIEWS.find(x => x[0] === key) || VIEWS[0];
  document.querySelectorAll(".tab").forEach(t => t.setAttribute("aria-current", t.dataset.key === v[0] ? "page" : "false"));
  $(`.tab[data-key="${v[0]}"]`)?.scrollIntoView({ block: "nearest", inline: "center" });
  clearCharts();
  const root = $("#view");
  root.innerHTML = `<div class="loading">Loading…</div>`;
  try { await v[2](root); } catch (e) { root.innerHTML = `<div class="panel">Couldn't load this view: ${esc(e.message)}</div>`; console.error(e); }
}
$("#tabs").innerHTML = VIEWS.map(([k, t]) => `<button class="tab" type="button" data-key="${k}">${esc(t)}</button>`).join("");
document.querySelectorAll(".tab").forEach(b => b.onclick = () => { location.hash = b.dataset.key; });
addEventListener("hashchange", route);
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", route);
route();
