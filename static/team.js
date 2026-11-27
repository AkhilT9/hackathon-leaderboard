"use strict";
(async () => {
  const { esc, fmt, fmtMetric, avatar, link, badge, badgeRow, METRICS } = HC;
  const name = new URLSearchParams(location.search).get("name") || "";
  await HC.nav("home");
  const defs = await HC.badges();
  document.getElementById("shapes").innerHTML = HC.shapes();

  const SPLIT = ["calls", "tokens", "commits", "linesChanged", "mcpCalls", "verifyRuns", "errors", "costUsd"];

  function progressRow(p) {
    const d = defs.by[p.id];
    const next = p.next == null ? "Maxed out" : `Next: ${HC.TIER[p.tier + 1]} at ${HC.fmtBadgeValue(d, p.next)}`;
    return `<div style="display:flex;gap:14px;align-items:center">${badge(d, p.tier, 52)}
      <div style="flex:1;min-width:0"><div style="display:flex;justify-content:space-between;gap:8px"><b>${esc(d.name)}</b>
        <span class="tier-pill tier-${p.tier}">${HC.TIER[p.tier]}</span></div>
        <div class="muted" style="font-size:13px;margin:2px 0 8px">${esc(d.rule)} · now ${HC.fmtBadgeValue(d, p.value)} · ${next}</div>
        <div class="progress"><i style="width:${p.pct}%;background:${d.color}"></i></div></div></div>`;
  }

  async function load() {
    let t;
    try { t = await HC.api("/api/team?name=" + encodeURIComponent(name)); }
    catch (e) { document.getElementById("hero").innerHTML = `<div class="empty">${esc(e.message)}. <a href="/" style="color:var(--blue)">Back to the leaderboard</a></div>`; return; }
    document.title = `${t.name} · Team`;
    const m = t.metrics;

    document.getElementById("hero").innerHTML = `
      <span class="eyebrow"><span class="live-dot ${t.live ? "" : "off"}"></span>Team · rank #${t.rank} of ${t.of}</span>
      <h1 class="display">${esc(t.name)}</h1>
      <div style="display:flex;gap:8px;margin-top:22px;flex-wrap:wrap">${t.members.map((mb) =>
        `<a class="chip" href="${link.player(mb.name)}">${avatar(mb.name, 22)} ${esc(mb.name)}</a>`).join("")}</div>
      <div class="stats">${[["Tool calls", fmt(m.calls)], ["Tokens", fmt(m.tokens)], ["Commits", fmt(m.commits)],
        ["Lines changed", fmt(m.linesChanged)], ["MCP calls", fmt(m.mcpCalls)], ["Badges", Object.keys(t.badges).length +
        t.members.reduce((s, x) => s + Object.keys(x.badges).length, 0)]].map(([l, v], i) =>
        `<div class="stat"><div class="label">${l}</div><div class="value">${v}</div><div class="bar" style="background:${HC.COLORS[i % 4]}"></div></div>`).join("")}</div>`;

    document.getElementById("legend").innerHTML = t.members.map((mb, j) =>
      `<span><i style="background:${HC.memberColor(j)}"></i>${esc(mb.name)}</span>`).join("");
    document.getElementById("split").innerHTML = SPLIT.map((k) => {
      const total = t.members.reduce((s, mb) => s + (mb.metrics[k] || 0), 0);
      return `<div><div style="display:flex;justify-content:space-between;font-size:14px;margin-bottom:8px">
        <b>${METRICS[k]}</b><span class="muted num">${fmtMetric(k, total)}</span></div>
        <div class="split tall">${total ? t.members.map((mb, j) => {
          const v = mb.metrics[k] || 0;
          return v ? `<i title="${esc(mb.name)}: ${fmtMetric(k, v)} (${Math.round((100 * v) / total)}%)" style="flex-grow:${v / total};background:${HC.memberColor(j)}"></i>` : "";
        }).join("") : ""}</div></div>`;
    }).join("");

    const sorted = [...t.members].sort((a, b) => b.metrics.calls - a.metrics.calls);
    const tbl = document.getElementById("members");
    tbl.innerHTML = `<thead><tr><th>Builder</th><th class="r">Rank</th><th class="r">Tool calls</th><th class="r hide-sm">Tokens</th>
      <th class="r hide-sm">Commits</th><th class="r hide-sm">Lines</th><th class="r hide-sm">Errors</th><th class="r">Share</th><th class="hide-sm">Badges</th></tr></thead>
      <tbody>${sorted.map((mb) => `<tr data-href="${link.player(mb.name)}">
        <td><div class="who">${avatar(mb.name, 36)}<div class="n">${esc(mb.name)} ${mb.live ? '<span class="live-dot"></span>' : ""}</div></div></td>
        <td class="r metric">#${mb.rank}</td><td class="r metric sorted">${fmt(mb.metrics.calls)}</td>
        <td class="r metric hide-sm">${fmt(mb.metrics.tokens)}</td><td class="r metric hide-sm">${fmt(mb.metrics.commits)}</td>
        <td class="r metric hide-sm">${fmt(mb.metrics.linesChanged)}</td><td class="r metric hide-sm">${fmt(mb.metrics.errors)}</td>
        <td class="r metric">${m.calls ? Math.round((100 * mb.metrics.calls) / m.calls) : 0}%</td>
        <td class="hide-sm">${badgeRow(mb.badges, [], 5)}</td></tr>`).join("")}</tbody>`;
    tbl.onclick = (e) => { const r = e.target.closest("tr[data-href]"); if (r) location.href = r.dataset.href; };

    document.getElementById("teamBadges").innerHTML = t.progress.map(progressRow).join("");
    document.getElementById("hourly").innerHTML = HC.hourlyBars(t.totals.hourly, "#1e8e3e");
  }

  await load();
  setInterval(load, 15000);
})();
