"use strict";
(async () => {
  const { esc, avatar, link, badge } = HC;
  await HC.nav("awards");
  await HC.badges();
  document.getElementById("shapes").innerHTML = HC.shapes();
  document.getElementById("tiers").innerHTML = [1, 2, 3].map((t) =>
    `<span class="chip">${badge({ name: HC.TIER[t], icon: "trophy", color: ["", "#b0652a", "#8d97a5", "#c9971c"][t] }, t, 22)} ${HC.TIER[t]}</span>`).join("") +
    `<span class="chip">${HC.icon("crown", 14, "#f9ab00")} Crown = #1 holder</span>`;

  function card(a, isTeam) {
    const href = (n) => (isTeam ? link.team(n) : link.player(n));
    const best = a.top[0];
    return `<div class="card badge-card">
      ${badge(a, best ? best.tier : 3, 104, { crown: !!best })}
      <div class="name">${esc(a.name)}</div>
      <div class="rule">${esc(a.rule)}</div>
      <div class="thresholds">${a.tiers.map((v, i) => `<span class="tier-pill tier-${i + 1}">${a.lowerBetter ? "≤" : "≥"} ${HC.fmtBadgeValue(a, v)}</span>`).join("")}</div>
      ${best ? `<a class="holder" href="${href(best.name)}">${avatar(best.name, 34)}<div style="flex:1;min-width:0">
          <div style="font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(best.name)}</div>
          <div class="muted" style="font-size:12px">${HC.fmtBadgeValue(a, best.value)} ${esc(a.unit)}</div></div>${HC.icon("crown", 18, "#f9ab00")}</a>`
        : `<div class="holder muted" style="justify-content:center">Unclaimed — be the first</div>`}
      ${a.top.length > 1 ? `<div style="width:100%;display:grid;gap:6px;text-align:left">${a.top.slice(1).map((t, i) => `
        <a href="${href(t.name)}" style="display:flex;justify-content:space-between;font-size:13px;gap:8px">
          <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis"><span class="faint">${i + 2}.</span> ${esc(t.name)}</span>
          <span class="muted num">${HC.fmtBadgeValue(a, t.value)}</span></a>`).join("")}</div>` : ""}
      <div class="muted" style="font-size:12px">${a.earned.map((n, i) => `${n} ${HC.TIER[i + 1].toLowerCase()}`).join(" · ")}</div>
    </div>`;
  }

  async function load() {
    const d = await HC.api("/api/leaderboard");
    document.getElementById("personal").innerHTML = d.awards.personal.map((a) => card(a, false)).join("");
    document.getElementById("team").innerHTML = d.awards.team.map((a) => card(a, true)).join("");
  }
  await load();
  setInterval(() => load().catch(() => {}), 15000);
})();
