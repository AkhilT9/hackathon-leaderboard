"use strict";
(async () => {
  const { esc, fmt, fmtFull, avatar, link, badge } = HC;
  const name = new URLSearchParams(location.search).get("name") || "";
  await HC.nav("home");
  const defs = await HC.badges();
  document.getElementById("shapes").innerHTML = HC.shapes();
  const KIND = { edit: "#ea4335", exec: "#1a73e8", verify: "#1e8e3e", read: "#9aa0a8", search: "#f9ab00", web: "#12b5cb", tool: "#a142f4", mcp: "#d01884", commit: "#0b0b0f", error: "#ea4335" };
  let open = null;

  async function load() {
    let p;
    try { p = await HC.api("/api/player?name=" + encodeURIComponent(name)); }
    catch (e) { document.getElementById("hero").innerHTML = `<div class="empty">${esc(e.message)}. <a href="/" style="color:var(--blue)">Back to the leaderboard</a></div>`; return; }
    document.title = `${p.name} · Builder`;
    const t = p.totals;
    const deltaTxt = p.delta ? `<span class="chip" style="color:${p.delta > 0 ? "var(--green)" : "var(--red)"}">${p.delta > 0 ? "▲" : "▼"} ${Math.abs(p.delta)} places</span>` : "";

    document.getElementById("hero").innerHTML = `
      <div style="display:flex;gap:28px;align-items:center;flex-wrap:wrap">
        ${avatar(p.name, 112, p.rank <= 3 ? ["#c9971c", "#8d97a5", "#b0652a"][p.rank - 1] : null)}
        <div style="min-width:0">
          <span class="eyebrow"><span class="live-dot ${p.live ? "" : "off"}"></span>${p.live ? "Building now" : "Last active " + HC.ago(p.lastActive)}</span>
          <h1 class="display" style="margin-top:8px">${esc(p.name)}</h1>
          <div style="display:flex;gap:8px;margin-top:14px;flex-wrap:wrap">
            <span class="chip dark">#${p.rank} of ${p.of}</span>${deltaTxt}
            <a class="chip" href="${link.team(p.team)}">${HC.icon("users", 14)} ${esc(p.team)}</a>
            ${p.agentTools.map((a) => `<span class="chip">${esc(a)}</span>`).join("")}
          </div>
        </div>
      </div>
      <div class="stats four">${[["Tool calls", fmt(t.calls)], ["Tokens", fmt(t.tokens)], ["Commits + PRs", fmt(t.commits + t.prs)],
        ["Lines changed", fmt(t.linesChanged)], ["Test runs", fmt(t.verifyRuns)], ["MCP calls", fmt(t.mcpCalls)],
        ["Active time", HC.fmtHours(t.activeMs)], ["Spend", HC.fmtUsd(t.costUsd)]].map(([l, v], i) =>
        `<div class="stat"><div class="label">${l}</div><div class="value">${v}</div><div class="bar" style="background:${HC.COLORS[i % 4]}"></div></div>`).join("")}</div>`;

    document.getElementById("sync").innerHTML = syncCard(p);

    const earned = p.progress.filter((x) => x.tier > 0).sort((a, b) => (p.crowns.includes(b.id) - p.crowns.includes(a.id)) || b.tier - a.tier);
    document.getElementById("earned").innerHTML = earned.length ? earned.map((x) => {
      const d = defs.by[x.id];
      return `<div class="card badge-card">${badge(d, x.tier, 96, { crown: p.crowns.includes(x.id) })}
        <div class="name">${esc(d.name)}</div><span class="tier-pill tier-${x.tier}">${HC.TIER[x.tier]}${p.crowns.includes(x.id) ? " · Crown" : ""}</span>
        <div class="rule">${esc(d.rule)} · ${HC.fmtBadgeValue(d, x.value)}</div></div>`;
    }).join("") : `<div class="card soft empty">No badges yet. Keep your sync running and they'll start landing.</div>`;

    const next = p.progress.filter((x) => x.tier < 3).sort((a, b) => b.pct - a.pct);
    document.getElementById("next").innerHTML = next.map((x) => {
      const d = defs.by[x.id];
      return `<div style="display:flex;gap:14px;align-items:center">${badge(d, x.tier, 48)}
        <div style="flex:1;min-width:0"><div style="display:flex;justify-content:space-between;gap:8px"><b>${esc(d.name)}</b>
        <span class="muted num" style="font-size:13px">${HC.fmtBadgeValue(d, x.value)} / ${HC.fmtBadgeValue(d, x.next)}</span></div>
        <div class="muted" style="font-size:13px;margin:2px 0 8px">${HC.TIER[x.tier + 1]} · ${esc(d.rule)}</div>
        <div class="progress"><i style="width:${x.pct}%;background:${d.color}"></i></div></div></div>`;
    }).join("") || `<div class="empty">Every badge at gold. Legendary.</div>`;

    document.getElementById("hourly").innerHTML = HC.hourlyBars(t.hourly);
    const tools = Object.entries(t.tools).slice(0, 8);
    const max = Math.max(1, ...tools.map(([, v]) => v));
    document.getElementById("tools").innerHTML = tools.length ? tools.map(([k, v], i) => `
      <div class="hbar"><span class="lab">${esc(k)}</span><div class="track"><i style="width:${(v / max) * 100}%;background:${HC.COLORS[i % 4]}"></i></div>
      <span class="num muted">${fmtFull(v)}</span></div>`).join("") : `<div class="empty">No tool calls yet.</div>`;

    const box = document.getElementById("sessions");
    box.innerHTML = p.sessions.length ? `<table class="lb"><thead><tr><th>Agent</th><th class="hide-sm">Started</th><th class="r">Calls</th>
      <th class="r hide-sm">Tokens</th><th class="r hide-sm">Errors</th><th class="r hide-sm">Commits</th></tr></thead><tbody>
      ${p.sessions.map((s) => `<tr data-sid="${esc(s.id)}"><td><b>${esc(s.agentTool)}</b><div class="faint" style="font-size:12px">${esc(s.id.slice(-12))}</div></td>
        <td class="hide-sm muted">${s.startedAt ? new Date(s.startedAt).toLocaleString() : "—"}</td>
        <td class="r metric sorted">${fmt(s.calls)}</td><td class="r metric hide-sm">${fmt(s.tokens)}</td>
        <td class="r metric hide-sm">${fmt(s.errors)}</td><td class="r metric hide-sm">${fmt(s.commits)}</td></tr>
        <tr class="tl-host hidden" data-for="${esc(s.id)}"><td colspan="6"></td></tr>`).join("")}</tbody></table>`
      : `<div class="empty">No sessions synced yet.</div>`;
    if (open) toggle(open, true);
  }

  // What this builder's sync loop last reported: answers "why am I not on the board?"
  function syncCard(p) {
    const s = p.sync;
    if (!s) {
      return `<div style="display:flex;gap:12px;align-items:center"><span class="live-dot off"></span>
        <div><b>Sync not connected yet.</b> <span class="muted">Run the command from <a href="/join" style="color:var(--blue)">/join</a> and keep its window open.
        Older sync scripts don't report status; re-copy the command if this stays empty.</span></div></div>`;
    }
    const head = p.connected
      ? `<span class="live-dot"></span><b>Sync connected</b> <span class="muted">· last report ${HC.ago(s.ts)}</span>`
      : `<span class="live-dot off"></span><b>Sync not running</b> <span class="muted">· last report ${HC.ago(s.ts)}. Is the sync window still open?</span>`;
    const skipped = Object.entries(s.skipped || {});
    let hint = "";
    if (s.error) hint = `<div style="color:var(--red);margin-top:8px">agentplay build failed: ${esc(s.error)}</div>`;
    else if (!s.found) hint = `<div class="muted" style="margin-top:8px">No agent sessions found on this laptop yet. Use a supported tool (Claude Code, Cursor, Codex, Copilot, Gemini CLI, OpenCode, Antigravity); activity shows up within 20 s.</div>`;
    else if (!s.eligible) hint = `<div class="muted" style="margin-top:8px">Sessions were found but none count yet. Start (or keep using) an agent session now.</div>`;
    return `<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${head}</div>
      <div class="chips" style="margin-top:12px">
        <span class="chip">${fmt(s.found)} session${s.found === 1 ? "" : "s"} found${s.agents && s.agents.length ? " · " + esc(s.agents.join(", ")) : ""}</span>
        <span class="chip">${fmt(s.eligible)} count</span>
        <span class="chip">${fmt(s.synced)} synced</span>
        ${skipped.map(([why, n]) => `<span class="chip" title="Not counted">${fmt(n)} ${esc(why)}</span>`).join("")}
      </div>${hint}`;
  }

  async function toggle(sid, force) {
    const host = [...document.querySelectorAll(".tl-host")].find((r) => r.dataset.for === sid);
    if (!host) return;
    if (!force && !host.classList.contains("hidden")) { host.classList.add("hidden"); open = null; return; }
    open = sid;
    host.classList.remove("hidden");
    const td = host.firstElementChild;
    if (td.dataset.loaded) return;
    td.innerHTML = '<div class="muted" style="padding:8px">Loading steps…</div>';
    try {
      const d = await HC.api(`/api/session?participant=${encodeURIComponent(name)}&id=${encodeURIComponent(sid)}`);
      td.dataset.loaded = "1";
      td.innerHTML = `<div class="tl">${d.steps.map((s) => `<div class="tl-row">
        <span class="faint num">${Math.floor(s.t / 60000)}m</span><span class="k" style="background:${KIND[s.mcp ? "mcp" : s.kind] || "#9aa0a8"}"></span>
        <span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><span class="tool">${esc(s.tool)}</span>
          <span class="muted">${esc(s.verb || s.target || "")}</span></span>
        <span>${s.err ? '<span class="err">ERROR</span>' : `<span class="faint num">${s.durMs >= 1000 ? (s.durMs / 1000).toFixed(1) + "s" : s.durMs + "ms"}</span>`}</span></div>`).join("") || '<div class="empty">No steps.</div>'}</div>`;
    } catch (e) { td.innerHTML = `<div class="muted" style="padding:8px">${esc(e.message)}</div>`; }
  }

  document.getElementById("sessions").addEventListener("click", (e) => {
    const row = e.target.closest("tr[data-sid]");
    if (row) toggle(row.dataset.sid);
  });

  await load();
  setInterval(load, 20000);
})();
