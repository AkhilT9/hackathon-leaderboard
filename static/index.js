"use strict";
(async () => {
  const { esc, fmt, fmtMetric, avatar, link, badge, badgeRow, countUp, METRICS } = HC;
  const SORTS = ["calls", "tokens", "outputTokens", "commits", "mcpCalls", "linesChanged", "verifyRuns", "badges"];
  const state = { view: "people", sort: "calls", q: "", team: "all", data: null };
  const me = HC.me();

  await HC.nav("home");
  await HC.badges();
  document.getElementById("shapes").innerHTML = HC.shapes();

  // controls
  document.getElementById("metricChips").innerHTML = SORTS.map((k) =>
    `<button data-sort="${k}" class="${k === state.sort ? "on" : ""}">${METRICS[k]}</button>`).join("");
  document.getElementById("metricChips").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-sort]");
    if (!b) return;
    state.sort = b.dataset.sort;
    document.querySelectorAll("#metricChips button").forEach((x) => x.classList.toggle("on", x === b));
    render();
  });
  document.querySelector(".seg").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-view]");
    if (!b) return;
    state.view = b.dataset.view;
    document.querySelectorAll(".seg button").forEach((x) => x.classList.toggle("on", x === b));
    render();
  });
  document.getElementById("search").addEventListener("input", (e) => { state.q = e.target.value.trim().toLowerCase(); render(); });
  document.getElementById("teamFilter").addEventListener("change", (e) => { state.team = e.target.value; render(); });
  document.getElementById("table").addEventListener("click", (e) => {
    const row = e.target.closest("tr[data-href]");
    if (row) location.href = row.dataset.href;
  });
  document.getElementById("podium").addEventListener("click", (e) => {
    const card = e.target.closest("[data-href]");
    if (card) location.href = card.dataset.href;
  });

  const value = (x, k) => (k === "badges" ? Object.keys(x.badges).length : x.metrics[k] || 0);

  function rows() {
    const d = state.data;
    let list = state.view === "people" ? d.players : d.teams;
    if (state.team !== "all") {
      list = state.view === "people" ? list.filter((p) => p.team === state.team) : list.filter((t) => t.name === state.team);
    }
    if (state.q) {
      list = list.filter((x) => x.name.toLowerCase().includes(state.q) || (x.team || "").toLowerCase().includes(state.q) ||
        (x.members || []).some((m) => m.name.toLowerCase().includes(state.q)));
    }
    return [...list].sort((a, b) => value(b, state.sort) - value(a, state.sort) || a.rank - b.rank);
  }

  function renderStats() {
    const d = state.data, s = d.summary;
    const tiles = [
      ["Builders", s.participants, "#1a73e8"], ["Teams", s.teams, "#ea4335"], ["Tool calls", s.calls, "#f9ab00"],
      ["Tokens", s.tokens, "#1e8e3e"], ["Commits", s.commits, "#1a73e8"], ["Badges earned", s.badgesEarned, "#ea4335"],
    ];
    const box = document.getElementById("stats");
    if (!box.children.length) {
      box.innerHTML = tiles.map(([l, , c], i) => `<div class="stat reveal" style="animation-delay:${i * 60}ms"><div class="label">${l}</div><div class="value" data-i="${i}">0</div><div class="bar" style="background:${c}"></div></div>`).join("");
    }
    tiles.forEach(([, v], i) => countUp(box.querySelector(`[data-i="${i}"]`), v));

    document.getElementById("liveLabel").textContent = `Live · ${s.live} building now`;
    document.getElementById("liveDot").classList.toggle("off", !s.live);
    document.getElementById("lede").textContent =
      `Every tool call, token and commit from ${s.participants} builders across ${s.teams} teams, updated as it happens.`;
    const chips = [];
    if (d.event.end) chips.push(`<span class="chip dark" id="countdown"></span>`);
    if (me) chips.push(`<a class="chip" href="${link.player(me.name)}">${HC.icon("user", 14)} You: #${(d.players.find((p) => p.name === me.name) || {}).rank || "–"}</a>`);
    chips.push(`<a class="chip" href="/stage">${HC.icon("zap", 14)} Stage view</a>`);
    document.getElementById("heroChips").innerHTML = chips.join("");
    tickCountdown();
  }

  function tickCountdown() {
    const el = document.getElementById("countdown");
    if (!el || !state.data.event.end) return;
    const left = Math.max(0, Date.parse(state.data.event.end) - Date.now());
    const h = Math.floor(left / 3.6e6), m = Math.floor((left % 3.6e6) / 6e4), s = Math.floor((left % 6e4) / 1e3);
    el.textContent = left ? `${h}h ${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s left` : "Time's up";
  }
  setInterval(() => state.data && tickCountdown(), 1000);

  function renderPowerHour() {
    const ph = state.data.powerHour;
    const left = Math.max(0, ph.endsAt - Math.floor(Date.now() / 1000));
    const max = Math.max(1, ...ph.top.map((t) => t.value));
    document.getElementById("powerHour").innerHTML = `
      <div class="card-head"><div><span class="eyebrow">${HC.icon("zap", 14, "#ea4335")} Power hour</span>
        <h3 class="h2" style="font-size:30px;margin-top:6px">${esc(ph.title)}</h3></div>
        <span class="chip">${Math.ceil(left / 60)} min left</span></div>
      ${ph.top.length ? ph.top.slice(0, 9).map((t, i) => `
        <div class="hbar"><a class="lab" href="${link.player(t.name)}">${i + 1}. ${esc(t.name)}</a>
          <div class="track"><i style="width:${(t.value / max) * 100}%;background:${HC.COLORS[i % 4]}"></i></div>
          <span class="num" style="font-weight:700">${fmtMetric(ph.metric, t.value)}</span></div>`).join("")
        : `<div class="empty">No activity yet this hour. The board is wide open.</div>`}`;
  }

  function renderPodium(list) {
    const top = list.slice(0, 3);
    const box = document.getElementById("podium");
    if (top.length < 3 || state.q) { box.innerHTML = ""; return; }
    const order = [1, 0, 2];
    box.innerHTML = order.map((i) => {
      const x = top[i], people = state.view === "people";
      const href = people ? link.player(x.name) : link.team(x.name);
      return `<div class="pod p${i + 1}" data-href="${href}">
        <div class="place">${["1st", "2nd", "3rd"][i]}</div>
        <div style="margin-top:14px">${avatar(x.name, i === 0 ? 72 : 56, ["#c9971c", "#8d97a5", "#b0652a"][i])}</div>
        <div class="who">${esc(x.name)}</div>
        <div class="team">${people ? esc(x.team) : `${x.memberCount} member${x.memberCount === 1 ? "" : "s"}`}</div>
        <div class="big">${state.sort === "badges" ? value(x, "badges") : fmtMetric(state.sort, value(x, state.sort))}</div>
        <div class="muted" style="font-size:13px">${METRICS[state.sort]}</div></div>`;
    }).join("");
  }

  function delta(d) {
    if (!d || state.sort !== "calls") return "";
    return `<span class="delta ${d > 0 ? "up" : "down"}">${d > 0 ? "▲" : "▼"} ${Math.abs(d)}</span>`;
  }

  function cell(k, x) {
    return `<td class="r metric hide-sm ${state.sort === k ? "sorted" : ""}">${fmtMetric(k, value(x, k))}</td>`;
  }

  function renderTable() {
    const list = rows();
    renderPodium(list);
    const t = document.getElementById("table");
    const sortCol = !["calls", "tokens", "commits"].includes(state.sort) && state.sort !== "badges" ? state.sort : null;
    if (!list.length) { t.innerHTML = `<tbody><tr><td class="empty">Nobody here yet. <a href="/join" style="color:var(--blue)">Join the board →</a></td></tr></tbody>`; return; }
    if (state.view === "people") {
      t.innerHTML = `<thead><tr><th>#</th><th>Builder</th><th class="r">Tool calls</th><th class="r hide-sm">Tokens</th><th class="r hide-sm">Commits</th>
        ${sortCol ? `<th class="r hide-sm">${METRICS[sortCol]}</th>` : ""}<th class="hide-sm">Badges</th><th class="r hide-sm">Active</th></tr></thead>
        <tbody>${list.map((p, i) => `<tr data-href="${link.player(p.name)}" class="${me && me.name === p.name ? "me" : ""}">
          <td class="rank">${i + 1}${delta(p.delta)}</td>
          <td><div class="who">${avatar(p.name, 38)}<div style="min-width:0"><div class="n">${esc(p.name)} ${p.live ? '<span class="live-dot" title="Live"></span>' : ""}</div>
            <div class="t">${esc(p.team)} · ${esc(p.agentTools.join(", ") || "no sessions yet")}</div></div></div></td>
          <td class="r metric ${state.sort === "calls" ? "sorted" : ""}">${fmt(p.metrics.calls)}</td>
          ${cell("tokens", p)}${cell("commits", p)}${sortCol ? cell(sortCol, p) : ""}
          <td class="hide-sm">${badgeRow(p.badges, p.crowns, 5)}</td>
          <td class="r hide-sm faint" style="white-space:nowrap">${HC.ago(p.lastActive)}</td></tr>`).join("")}</tbody>`;
    } else {
      t.innerHTML = `<thead><tr><th>#</th><th>Team</th><th class="r">Tool calls</th><th class="r hide-sm">Tokens</th><th class="r hide-sm">Commits</th>
        ${sortCol ? `<th class="r hide-sm">${METRICS[sortCol]}</th>` : ""}<th class="hide-sm" style="min-width:200px">Who's doing the work</th><th class="hide-sm">Badges</th></tr></thead>
        <tbody>${list.map((tm, i) => {
          const k = state.sort === "badges" ? "calls" : state.sort;
          const total = tm.members.reduce((s, m) => s + (m.metrics[k] || 0), 0) || 1;
          return `<tr data-href="${link.team(tm.name)}">
          <td class="rank">${i + 1}</td>
          <td><div class="who">${avatar(tm.name, 38)}<div style="min-width:0"><div class="n">${esc(tm.name)} ${tm.live ? '<span class="live-dot"></span>' : ""}</div>
            <div class="t">${tm.memberCount} member${tm.memberCount === 1 ? "" : "s"}</div></div></div></td>
          <td class="r metric ${state.sort === "calls" ? "sorted" : ""}">${fmt(tm.metrics.calls)}</td>
          ${cell("tokens", tm)}${cell("commits", tm)}${sortCol ? cell(sortCol, tm) : ""}
          <td class="hide-sm"><div class="split" title="${esc(METRICS[k])} by member">${tm.members.map((m, j) =>
            `<i title="${esc(m.name)}: ${fmtMetric(k, m.metrics[k] || 0)}" style="flex-grow:${(m.metrics[k] || 0) / total};background:${HC.memberColor(j)}"></i>`).join("")}</div></td>
          <td class="hide-sm">${badgeRow(tm.badges, tm.crowns, 4)}</td></tr>`;
        }).join("")}</tbody>`;
    }
  }

  function renderFilter() {
    const sel = document.getElementById("teamFilter");
    const teams = state.data.teams.map((t) => t.name).sort((a, b) => a.localeCompare(b));
    const want = `all|${teams.join("|")}`;
    if (sel.dataset.v === want) return;
    sel.dataset.v = want;
    sel.innerHTML = `<option value="all">All teams</option>` + teams.map((t) => `<option ${t === state.team ? "selected" : ""}>${esc(t)}</option>`).join("");
  }

  function renderCrowns() {
    const aw = state.data.awards.personal.filter((a) => a.holder).slice(0, 8);
    document.getElementById("crowns").innerHTML = aw.length ? aw.map((a) => `
      <a class="card" href="${link.player(a.holder)}" style="display:flex;gap:16px;align-items:center">
        ${badge(a, a.top[0] ? a.top[0].tier : 1, 60, { crown: true })}
        <div style="min-width:0"><div style="font-weight:700">${esc(a.name)}</div>
        <div class="muted" style="font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(a.holder)} · ${HC.fmtBadgeValue(a, a.top[0] && a.top[0].value)} ${esc(a.unit)}</div></div></a>`).join("")
      : `<div class="card soft empty">Crowns appear as soon as someone earns a badge.</div>`;
  }

  function render() {
    if (!state.data) return;
    renderStats();
    renderPowerHour();
    renderFilter();
    renderTable();
    renderCrowns();
  }

  async function load() {
    try { state.data = await HC.api("/api/leaderboard"); render(); } catch (_) { /* keep last view */ }
  }
  await load();
  setInterval(load, 10000);

  HC.listen((fresh, all) => {
    const feed = document.getElementById("feed");
    if (fresh.length === 0 && all.length) feed.innerHTML = all.slice().reverse().map(HC.feedItem).join("");
    else if (fresh.length) {
      feed.insertAdjacentHTML("afterbegin", fresh.slice().reverse().map(HC.feedItem).join(""));
      fresh.filter((e) => e.type !== "joined").slice(-3).forEach(HC.toast);
      load();
    }
  });
})();
