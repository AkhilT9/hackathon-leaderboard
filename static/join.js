"use strict";
(async () => {
  const { esc, link } = HC;
  const cfg = await HC.nav("join");
  document.getElementById("shapes").innerHTML = HC.shapes();
  const main = document.getElementById("main");

  const save = (me) => { try { localStorage.setItem("hc_me", JSON.stringify(me)); } catch (_) { /* private mode */ } };
  const forget = () => { try { localStorage.removeItem("hc_me"); } catch (_) { /* private mode */ } };

  function registerView(error) {
    main.innerHTML = `
      <div class="steps">
        <div class="step"><span class="step-n" style="background:var(--blue)">1</span><div>
          <h3 class="h3">Register</h3><p class="muted" style="margin:4px 0 16px">Use the name your team knows you by.</p>
          <form id="reg" style="display:grid;gap:14px">
            <div class="field"><label for="name">Your name</label><input class="input" id="name" maxlength="40" required autocomplete="name"></div>
            <div class="field"><label for="team">Team</label><input class="input" id="team" maxlength="40" required list="teams"><datalist id="teams"></datalist></div>
            ${cfg.requiresCode ? `<div class="field"><label for="code">Event code</label><input class="input" id="code" required autocomplete="off"></div>` : ""}
            <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><button class="btn" type="submit">Get my sync command</button>
              <span id="err" style="color:var(--red);font-size:14px">${esc(error || "")}</span></div>
          </form></div></div>
        <div class="step"><span class="step-n" style="background:var(--faint)">2</span><div>
          <h3 class="h3">Already registered?</h3><p class="muted" style="margin:4px 0 12px">Paste the token you were given to get your command back.</p>
          <form id="tok" style="display:flex;gap:10px;flex-wrap:wrap"><input class="input" id="token" placeholder="Your upload token" style="flex:1;min-width:200px" autocomplete="off">
            <button class="btn light" type="submit">Continue</button></form></div></div>
      </div>`;
    HC.api("/api/leaderboard").then((d) => {
      document.getElementById("teams").innerHTML = d.teams.map((t) => `<option value="${esc(t.name)}">`).join("");
    }).catch(() => {});

    document.getElementById("reg").addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = e.target.querySelector("button");
      btn.disabled = true;
      try {
        const body = { name: document.getElementById("name").value, team: document.getElementById("team").value };
        if (cfg.requiresCode) body.code = document.getElementById("code").value;
        const r = await HC.api("/api/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        save({ name: r.name, team: r.team, token: r.token });
        readyView(true);
      } catch (err) { document.getElementById("err").textContent = err.message; btn.disabled = false; }
    });
    document.getElementById("tok").addEventListener("submit", async (e) => {
      e.preventDefault();
      const token = document.getElementById("token").value.trim();
      try {
        const r = await HC.api("/api/me", { headers: { "X-Upload-Token": token } });
        save({ name: r.name, team: r.team, token });
        readyView(false);
      } catch (err) { registerView(err.message); }
    });
  }

  function readyView(fresh) {
    const me = HC.me();
    if (!me) return registerView();
    const origin = location.origin, t = encodeURIComponent(me.token);
    const ps = `irm "${origin}/join.ps1?token=${t}" | iex`;
    const sh = `curl -fsSL "${origin}/join.sh?token=${t}" | bash`;
    main.innerHTML = `
      <div style="display:flex;gap:16px;align-items:center;margin-bottom:24px">${HC.avatar(me.name, 56)}
        <div><span class="eyebrow">${fresh ? "You're registered" : "Welcome back"}</span>
        <div class="h3" style="font-size:24px">${esc(me.name)} <span class="muted" style="font-weight:500">· ${esc(me.team)}</span></div></div></div>
      <div class="steps">
        <div class="step"><span class="step-n" style="background:var(--green)">1</span><div style="min-width:0">
          <h3 class="h3">Run this once and keep the window open</h3>
          <div class="seg" style="margin:12px 0"><button class="on" data-os="ps">Windows PowerShell</button><button data-os="sh">macOS / Linux</button></div>
          <div class="cmd" id="cmdBox" data-text="${esc(ps)}"><span id="cmdText">${esc(ps)}</span><button class="copy" data-copy="cmdBox">Copy</button></div>
          <p class="muted" style="font-size:13px;margin:10px 0 0">It installs <code>agentplay</code> if needed, then syncs every 20 seconds. Needs Python 3.10+.</p></div></div>
        <div class="step"><span class="step-n" style="background:var(--yellow)">2</span><div>
          <h3 class="h3">Keep your token private</h3>
          <p class="muted" style="margin:4px 0 8px">It is your identity on the board. This browser remembers it for you.</p>
          <div class="cmd" id="tokBox" data-text="${esc(me.token)}" style="background:var(--bg-soft);color:var(--ink)">${esc(me.token)}<button class="copy" data-copy="tokBox" style="background:#fff;color:var(--ink)">Copy</button></div></div></div>
        <div class="step"><span class="step-n" style="background:var(--red)">3</span><div>
          <h3 class="h3">Watch yourself climb</h3>
          <div style="display:flex;gap:10px;margin-top:10px;flex-wrap:wrap"><a class="btn" href="${link.player(me.name)}">My profile</a><a class="btn light" href="${link.team(me.team)}">My team</a></div>
          <details style="margin-top:18px"><summary class="muted" style="cursor:pointer">Can't run scripts? Upload a session file instead</summary>
            <p class="muted" style="font-size:13px">Run <code>agentplay export --latest -o session.json.gz</code>, then choose the file.</p>
            <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><input type="file" id="file" accept=".json,.gz">
              <span id="upStatus" class="muted" style="font-size:14px"></span></div></details>
          <p style="margin-top:18px"><a href="#" id="switch" class="muted" style="font-size:13px">Not you? Use a different account</a></p></div></div>
      </div>`;

    const box = document.getElementById("cmdBox");
    main.querySelector(".seg").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-os]");
      if (!b) return;
      main.querySelectorAll(".seg button").forEach((x) => x.classList.toggle("on", x === b));
      const cmd = b.dataset.os === "ps" ? ps : sh;
      box.dataset.text = cmd;
      document.getElementById("cmdText").textContent = cmd;
    });
    HC.copyButtons(main);
    document.getElementById("switch").addEventListener("click", (e) => { e.preventDefault(); forget(); registerView(); });
    document.getElementById("file").addEventListener("change", async (e) => {
      const f = e.target.files[0], st = document.getElementById("upStatus");
      if (!f) return;
      st.textContent = "Uploading…";
      try {
        const r = await HC.api("/api/upload", { method: "POST", headers: { "X-Upload-Token": me.token }, body: f });
        st.textContent = r.skipped ? `Skipped: ${r.skipped}` : r.unchanged ? "Already up to date." : `Synced ${HC.fmtFull(r.calls)} tool calls.`;
      } catch (err) { st.textContent = err.message; }
    });
  }

  HC.me() ? readyView(false) : registerView();
})();
