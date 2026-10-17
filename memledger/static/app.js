// MemLedger operator console. Plain JS, no build step.
(() => {
  const $ = (id) => document.getElementById(id);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const C = {
    active: css("--active"), quarantined: css("--quarantined"), closed: css("--closed"),
    revoked: css("--revoked"), agent: css("--accent"), source: css("--source"),
    dispute: css("--dispute"), ink: css("--ink"), muted: css("--muted"), line: css("--line"),
  };
  const LINK = {
    SUPERSEDES: C.dispute, CONFLICTS_WITH: C.revoked, DERIVED_FROM: C.source,
    FROM_SOURCE: "#3a4454", WROTE: "#2c3442", CARRIES: "#4b3f8a", SENT: "#4b3f8a", TO: "#4b3f8a",
    RETRACTED: C.revoked, RETRACTS: C.revoked, LOGGED: "#2c3442",
  };

  const S = {
    tenant: null, demo: null, at: null, live: true, nodes: new Map(), sig: "",
    highlight: new Set(), timeMin: 0, timeMax: 0, busy: false, previewing: null, fit: true, hasGraph: {}, failed: new Set(),
  };

  // ------------------------------------------------------------- utils
  async function api(path, opts = {}) {
    const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.detail || r.statusText);
    return body;
  }
  const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body || {}) });
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const hhmm = (ms) => new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  const T = () => `/api/${encodeURIComponent(S.tenant)}`;

  function withCites(text, cites) {
    const inactive = new Set([...(cites?.inactive || []), ...(cites?.unknown || [])]);
    return esc(text).replace(/\[(f-[0-9a-f]{8})\]/g, (_, id) =>
      `<span class="cite${inactive.has(id) ? " inactive" : ""}" data-fact="${id}" role="button" tabindex="0">${id}</span>`);
  }

  function entry(title, meta, html, ok = true) {
    const div = document.createElement("div");
    div.className = `entry ${ok ? "ok" : "bad"}`;
    div.innerHTML = `<h4>${esc(title)} <span class="meta">${esc(meta || "")}</span></h4>${html}`;
    $("feed").prepend(div);
  }

  function checksHtml(checks) {
    if (!checks?.length) return "";
    return `<div class="checks">${checks.map((c) =>
      `<span class="${c.ok ? "pass" : c.soft ? "warn" : "fail"}">${c.ok ? "✓" : c.soft ? "~" : "✗"} ${esc(c.check)}</span>`).join(" · ")}</div>`;
  }

  function factsList(o) {
    const li = [];
    (o.stored || []).forEach((s) => li.push(`<li class="${s.status === "active" ? "plus" : "q"}">+ ${esc(s.predicate)} = ${esc(s.value)} <span class="pill ${s.status}">${s.status}</span>${s.replaced ? " replaced " + s.replaced : ""}${s.disputes ? " · disputed" : ""}</li>`));
    (o.retracted || []).forEach((r) => li.push(`<li class="minus">− ruled out ${esc(r.predicate)} = ${esc(r.value)}</li>`));
    (o.dropped || []).forEach((d) => li.push(`<li class="drop">· dropped ${esc(d.predicate || "")}: ${esc(d.reason)}</li>`));
    return li.length ? `<ul>${li.join("")}</ul>` : "";
  }

  function radiusList(o) {
    return `<div>${o.facts.length} fact(s): ${o.direct} direct, ${o.derived} derived</div><ul>${o.facts.map((f) =>
      `<li class="minus">✗ ${esc(f.predicate)} = ${esc(f.object)} <span class="meta">(${esc(f.writer)}, ${esc(f.status)})</span></li>`).join("")}</ul>`;
  }

  // ------------------------------------------------------------- graph
  const fg = ForceGraph()($("graph"))
    .backgroundColor(css("--bg"))
    .nodeId("id")
    .linkColor((l) => LINK[l.type] || C.line)
    .linkWidth((l) => (["SUPERSEDES", "CONFLICTS_WITH", "DERIVED_FROM"].includes(l.type) ? 1.6 : 0.6))
    .linkLineDash((l) => (l.type === "CONFLICTS_WITH" ? [3, 3] : null))
    .linkDirectionalArrowLength((l) => (["SUPERSEDES", "DERIVED_FROM", "CONFLICTS_WITH"].includes(l.type) ? 4 : 0))
    .linkDirectionalArrowRelPos(1)
    .nodeLabel((n) => esc(n.kind === "fact" ? `${n.name} (${n.status})` : `${n.kind}: ${n.name}`))
    .nodeCanvasObject(drawNode)
    .nodePointerAreaPaint((n, color, ctx) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(n.x, n.y, 9, 0, 2 * Math.PI); ctx.fill(); })
    .onNodeClick((n) => { if (n.kind === "fact") openWhy(n.id); })
    .cooldownTicks(150)
    .onEngineStop(() => { if (S.fit) { fg.zoomToFit(500, 80); S.fit = false; } });
  fg.d3Force("charge").strength(-260);
  fg.d3Force("link").distance((l) => (["SUPERSEDES", "CONFLICTS_WITH", "DERIVED_FROM"].includes(l.type) ? 45 : 75));
  const sizeGraph = () => { const el = $("graph"); fg.width(el.clientWidth).height(el.clientHeight); };
  sizeGraph();
  window.addEventListener("resize", () => { sizeGraph(); S.fit = true; });

  function factColor(n) {
    if (S.at !== null) return n.believed_at ? C.active : C.closed;
    return C[n.status] || C.muted;
  }

  function drawNode(n, ctx, scale) {
    const dim = S.highlight.size && !S.highlight.has(n.id);
    ctx.globalAlpha = dim ? 0.18 : (S.at !== null && n.kind === "fact" && !n.believed_at ? 0.35 : 1);
    let r = 5;
    if (n.kind === "agent") {
      r = 8; ctx.fillStyle = C.agent; ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 2 * Math.PI); ctx.fill();
    } else if (n.kind === "source") {
      r = 7; ctx.fillStyle = n.compromised ? C.revoked : C.source;
      ctx.fillRect(n.x - r, n.y - r, 2 * r, 2 * r);
    } else if (n.kind === "handoff") {
      r = 3; ctx.fillStyle = "#4b3f8a"; ctx.beginPath();
      ctx.moveTo(n.x, n.y - r); ctx.lineTo(n.x + r, n.y); ctx.lineTo(n.x, n.y + r); ctx.lineTo(n.x - r, n.y); ctx.fill();
    } else if (n.kind === "fact") {
      const col = factColor(n);
      ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
      if (n.status === "quarantined" && S.at === null) {
        ctx.setLineDash([2, 2]); ctx.strokeStyle = col; ctx.lineWidth = 1.5; ctx.stroke(); ctx.setLineDash([]);
      } else { ctx.fillStyle = col; ctx.fill(); }
    } else {
      ctx.fillStyle = C.muted; ctx.beginPath(); ctx.arc(n.x, n.y, 3, 0, 2 * Math.PI); ctx.fill();
    }
    if (S.highlight.has(n.id)) {
      ctx.strokeStyle = C.dispute; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(n.x, n.y, r + 4, 0, 2 * Math.PI); ctx.stroke();
    }
    if (n.kind !== "handoff" && scale > 0.45) {
      const label = n.name;
      ctx.font = `${(n.kind === "fact" ? 10 : 11) / scale}px ${css("--mono")}`;
      ctx.textAlign = "center"; ctx.textBaseline = "top";
      ctx.fillStyle = n.kind === "fact" && n.status !== "active" ? C.muted : C.ink;
      ctx.fillText(label.length > 34 ? label.slice(0, 33) + "…" : label, n.x, n.y + r + 3 / scale);
    }
    ctx.globalAlpha = 1;
  }

  async function refreshGraph() {
    if (!S.tenant) return;
    if (!S.hasGraph[S.tenant]) { fg.graphData({ nodes: [], links: [] }); S.nodes.clear(); S.sig = ""; return; }
    let data;
    try {
      data = await api(`${T()}/graph${S.at !== null ? `?at=${S.at}` : ""}`);
    } catch (e) { fg.graphData({ nodes: [], links: [] }); S.nodes.clear(); S.sig = ""; return; }
    const sig = JSON.stringify(data);
    if (sig === S.sig) return;
    S.sig = sig;
    if (data.nodes.length !== S.nodes.size) S.fit = true;
    const nodes = data.nodes.map((n) => Object.assign(S.nodes.get(n.id) || {}, n));
    S.nodes = new Map(nodes.map((n) => [n.id, n]));
    fg.graphData({ nodes, links: data.links });
    const times = data.nodes.filter((n) => n.kind === "fact").flatMap((n) => [n.valid_from, n.valid_to].filter(Boolean));
    if (S.at === null && times.length) {
      S.timeMin = Math.min(...times) - 60000;
      S.timeMax = Math.max(...times) + 60000;
    }
  }

  // ------------------------------------------------------------- time travel
  function setTime(ms) {
    S.at = ms;
    if (ms !== null && S.timeMax > S.timeMin) $("time").value = Math.round(1000 * (ms - S.timeMin) / (S.timeMax - S.timeMin));
    $("timeLabel").textContent = ms === null ? "Live" : `Memory as of ${hhmm(ms)}`;
    $("timeLabel").classList.toggle("past", ms !== null);
    if (ms === null) $("time").value = 1000;
    S.sig = ""; refreshGraph();
  }
  $("time").addEventListener("input", (e) => {
    const v = Number(e.target.value);
    if (v >= 1000 || !S.timeMax) return setTime(null);
    setTime(Math.round(S.timeMin + (S.timeMax - S.timeMin) * (v / 1000)));
  });
  $("live").addEventListener("click", () => setTime(null));

  // ------------------------------------------------------------- why panel
  async function openWhy(id) {
    let w;
    try { w = await api(`${T()}/facts/${encodeURIComponent(id)}/why`); }
    catch (e) { return entry("Why", id, `<div class="text">${esc(e.message)}</div>`, false); }
    S.highlight = new Set([id, ...w.upstream, ...w.sources.map((s) => `source:${s}`), ...w.agents.map((a) => `agent:${a}`)]);
    fg.nodeCanvasObject(drawNode);
    $("whyBody").innerHTML = `
      <div class="eyebrow">Why do we believe this?</div>
      <h3>${esc(w.predicate)} = ${esc(w.object)}</h3>
      <span class="pill ${w.status}">${w.status}</span>
      <dl>
        <dt>Written by</dt><dd>${esc(w.agents.join(", ") || "—")}</dd>
        <dt>Sources</dt><dd>${esc(w.sources.join(", ") || "—")}</dd>
        <dt>Based on</dt><dd>${w.upstream.map((u) => u.startsWith("f-") ? `<span class="cite" data-fact="${esc(u)}" role="button" tabindex="0">${esc(u)}</span>` : esc(u)).join(" ") || "—"}</dd>
        <dt>Replaced</dt><dd>${esc(w.replaced.join(", ") || "—")}</dd>
        <dt>Fact id</dt><dd>${esc(w.id)}</dd>
      </dl>
      <div class="eyebrow">Versions of ${esc(w.predicate)}</div>
      <ul class="versions">${w.versions.map((v) => `<li>${hhmm(v.valid_from)}${v.valid_to ? "–" + hhmm(v.valid_to) : "–now"} <span class="pill ${v.status}">${v.status}</span> ${esc(v.object)}</li>`).join("")}</ul>`;
    $("why").hidden = false;
  }
  $("whyClose").addEventListener("click", () => { $("why").hidden = true; S.highlight = new Set(); fg.nodeCanvasObject(drawNode); });
  document.addEventListener("click", (e) => { const c = e.target.closest(".cite"); if (c) openWhy(c.dataset.fact); });
  document.addEventListener("keydown", (e) => { const c = e.target.closest?.(".cite"); if (c && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openWhy(c.dataset.fact); } });

  // ------------------------------------------------------------- sources & quarantine
  async function refreshSources() {
    if (!S.tenant) return;
    if (!S.hasGraph[S.tenant]) { $("sources").innerHTML = `<div class="drop">No graph yet. Press Reset to start the story.</div>`; $("quarantine").innerHTML = ""; return; }
    let rows = [], q = [];
    try { [rows, q] = await Promise.all([api(`${T()}/sources`), api(`${T()}/quarantine`)]); } catch (e) { /* no graph yet */ }
    $("sources").innerHTML = rows.map((s) => `
      <div class="src ${s.compromised ? "comp" : ""}" data-src="${esc(s.id)}">
        <div class="src-head"><span>${esc(s.id)}</span><span class="pill ${s.compromised ? "revoked" : s.trusted ? "active" : "quarantined"}">${s.compromised ? "compromised" : s.trusted ? "trusted" : "untrusted"}</span></div>
        <div class="trust" title="trust ${s.trust}"><i style="width:${s.trust * 100}%"></i><b style="left:50%"></b></div>
        <div class="src-meta"><span>${esc(s.kind)} · ${s.trust.toFixed(2)} · ${s.active}a ${s.quarantined}q ${s.revoked}r</span>
          ${s.compromised ? "" : `<button class="ghost small" data-preview="${esc(s.id)}" type="button">Preview revoke</button>`}</div>
        <div class="radius"></div>
      </div>`).join("") || `<div class="drop">No sources yet. Reset the tenant.</div>`;
    $("quarantine").innerHTML = q.map((f) => `
      <div class="src">
        <div class="src-head"><span>${esc(f.predicate)} = ${esc(f.object)}</span></div>
        <div class="src-meta"><span>from ${esc(f.sources.join(", "))}${f.disputes ? ` · disputes ${esc(f.disputes.believed)}` : ""}</span>
          <button class="ghost small" data-promote="${esc(f.id)}" type="button">Promote</button></div>
      </div>`).join("") || `<div class="drop">Nothing in quarantine.</div>`;
  }

  document.addEventListener("click", async (e) => {
    const p = e.target.closest("[data-preview]");
    if (p) {
      const src = p.dataset.preview, box = p.closest(".src").querySelector(".radius");
      const r = await api(`${T()}/sources/${encodeURIComponent(src)}/blast-radius`);
      S.highlight = new Set([`source:${src}`, ...r.facts.map((f) => f.id)]);
      fg.nodeCanvasObject(drawNode);
      S.previewing = src;
      box.innerHTML = radiusList(r) + `<button class="danger small" data-revoke="${esc(src)}" type="button">Revoke ${esc(src)}</button> <button class="ghost small" data-cancel type="button">Cancel</button>`;
      return;
    }
    if (e.target.closest("[data-cancel]")) { S.previewing = null; S.highlight = new Set(); fg.nodeCanvasObject(drawNode); refreshSources(); return; }
    const rv = e.target.closest("[data-revoke]");
    if (rv) {
      S.previewing = null;
      const r = await post(`${T()}/sources/${encodeURIComponent(rv.dataset.revoke)}/revoke`);
      entry(`Revoked ${rv.dataset.revoke}`, `${r.revoked.length} fact(s)`, radiusList(r));
      S.highlight = new Set(r.revoked); fg.nodeCanvasObject(drawNode);
      setTimeout(() => { S.highlight = new Set(); fg.nodeCanvasObject(drawNode); }, 4000);
      refreshAll(); return;
    }
    const pr = e.target.closest("[data-promote]");
    if (pr) {
      await post(`${T()}/facts/${encodeURIComponent(pr.dataset.promote)}/promote`);
      entry("Promoted", pr.dataset.promote, ""); refreshAll();
    }
  });

  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("on", x === t));
    $("sources").hidden = t.dataset.tab !== "sources";
    $("quarantine").hidden = t.dataset.tab !== "quarantine";
  }));

  // ------------------------------------------------------------- demo
  async function loadDemo() {
    try { S.demo = await api(`${T()}/demo`); } catch (e) { S.demo = null; }
    const d = S.demo;
    $("incident").textContent = d ? `${d.subject} · ${d.title}` : S.tenant;
    $("next").disabled = !d; $("reset").disabled = !d || !d.allow_reset;
    if (!d) { $("stepCount").textContent = "No scenario"; $("dots").innerHTML = ""; return; }
    $("stepCount").textContent = `Step ${d.last_step} of ${d.steps.length}`;
    const next = d.steps[d.last_step];
    $("say").textContent = next ? `Next: ${next.say}` : "Story complete. Reset to replay.";
    $("dots").innerHTML = d.steps.map((s) => `<li class="${S.failed.has(s.n) ? "fail" : s.n <= d.last_step ? "done" : ""}" title="${s.n}. ${esc(s.action)}"></li>`).join("");
  }

  function showStep(r) {
    const o = r.output, title = `${r.n}. ${r.action}${o.agent ? " · " + o.agent : ""}`;
    let html = `<div class="text">${esc(r.say)}</div>`;
    if (r.action === "observe") html += factsList(o);
    if (["status_update", "ask", "investigate"].includes(r.action)) html += `<div class="text">${withCites(o.text, o.citations)}</div>`;
    if (["preview", "revoke"].includes(r.action)) html += radiusList(o);
    if (r.action === "as_of") { html += `<ul>${o.facts.map((f) => `<li>· ${esc(f.predicate)} = ${esc(f.object)}</li>`).join("")}</ul>`; setTime(Date.parse(o.time)); }
    if (r.action === "isolation") html += `<div class="text">${esc(o.other)} sees none of this incident; this tenant sees none of ${esc(o.other_subject || "—")}.</div>`;
    if (!r.ok) S.failed.add(r.n);
    entry(title, `${r.session} · ${hhmm(Date.parse(r.at))}`, html + checksHtml(r.checks), r.ok);
    if (r.action === "preview") { S.highlight = new Set(o.facts.map((f) => f.id)); fg.nodeCanvasObject(drawNode); }
    else if (r.action !== "as_of") { S.highlight = new Set(); }
  }

  $("next").addEventListener("click", async () => {
    if (S.busy) return; S.busy = true; $("next").disabled = true;
    try {
      if (S.at !== null && S.demo?.steps[S.demo.last_step]?.action !== "as_of") setTime(null);
      showStep(await post(`${T()}/demo/next`));
    } catch (e) { entry("Step failed", "", `<div class="text">${esc(e.message)}</div>`, false); }
    S.busy = false; await refreshAll();
  });

  $("reset").addEventListener("click", async () => {
    if (S.busy) return;
    if ($("reset").dataset.armed !== "1") {
      $("reset").dataset.armed = "1"; $("reset").textContent = "Confirm reset";
      setTimeout(() => { $("reset").dataset.armed = ""; $("reset").textContent = "Reset"; }, 3000);
      return;
    }
    $("reset").dataset.armed = ""; $("reset").textContent = "Reset";
    S.busy = true;
    try { await post(`${T()}/demo/reset`); S.hasGraph[S.tenant] = true; S.failed = new Set(); $("feed").innerHTML = ""; S.nodes.clear(); S.sig = ""; setTime(null); }
    catch (e) { entry("Reset failed", "", `<div class="text">${esc(e.message)}</div>`, false); }
    S.busy = false; refreshAll();
  });

  // ------------------------------------------------------------- ask
  $("askForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const agent = $("askAgent").value, q = $("askQ").value.trim();
    if (!q) return;
    const btn = e.target.querySelector("button"); btn.disabled = true;
    try {
      const r = await post(`${T()}/ask`, { agent, session: $("askSession").value || "s1", question: q });
      entry(`Ask · ${agent}`, r.tools.join(", "), `<div class="text">${esc(q)}</div><div class="text">${withCites(r.text, r.citations)}</div>`);
    } catch (err) { entry(`Ask · ${agent}`, "", `<div class="text">${esc(err.message)}</div>`, false); }
    btn.disabled = false;
  });

  // ------------------------------------------------------------- boot
  async function refreshAll() { await Promise.all([loadDemo(), refreshGraph(), refreshSources()]); }

  async function boot() {
    const [health, tenants] = await Promise.all([api("/api/health"), api("/api/tenants")]);
    $("modes").innerHTML = `<span class="chip">extract: ${esc(health.extract)}</span><span class="chip">agents: ${esc(health.agents)}</span>`;
    tenants.forEach((t) => { S.hasGraph[t.tenant] = t.has_graph; });
    $("tenant").innerHTML = tenants.map((t) => `<option value="${esc(t.tenant)}">${esc(t.tenant)}</option>`).join("");
    S.tenant = tenants.find((t) => t.tenant === "acme")?.tenant || tenants[0]?.tenant || null;
    if (S.tenant) $("tenant").value = S.tenant;
    $("tenant").addEventListener("change", () => {
      S.tenant = $("tenant").value; S.failed = new Set(); S.nodes.clear(); S.sig = ""; S.highlight = new Set();
      $("feed").innerHTML = ""; $("why").hidden = true; setTime(null); refreshAll();
    });
    await refreshAll();
    setInterval(() => { if (!S.busy) { refreshGraph(); if (!S.previewing) refreshSources(); } }, 2500);
  }
  boot().catch((e) => entry("Could not load", "", `<div class="text">${esc(e.message)}</div>`, false));
})();
