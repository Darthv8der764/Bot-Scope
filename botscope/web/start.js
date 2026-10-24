// Studio's Get started tab: the newcomer's setup, one step at a time, each with a live status. Keys are typed here and
// saved to your own .env on this computer (checked with Alpaca first, paper keys only); they're never shown back.
// Uses Studio's $, esc, capi (token-checked calls), show and openDock.
(function () {
  const css = document.createElement("style");
  css.textContent = `
  .gs .step { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 12px; margin-top: 10px; }
  .gs .step h3 { font-size: 15px; margin: 0 0 4px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .gs .chip { font-size: 12px; font-weight: 600; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--line); color: var(--muted); }
  .gs .chip.ok { color: var(--up); border-color: var(--up); }
  .gs .chip.bad { color: var(--down); border-color: var(--down); }
  .gs ol { margin: 6px 0; padding-left: 20px; } .gs li { margin: 3px 0; }
  .gs .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 8px 0; }
  .gs .row input { flex: 1 1 220px; min-width: 0; font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }
  .gs .primary { background: color-mix(in srgb, var(--accent) 72%, #000); color: #fff; border-color: transparent; font-weight: 600; }
  .gs .msg { font-size: 13px; margin: 6px 0 0; } .gs .msg.ok { color: var(--up); } .gs .msg.bad { color: var(--down); }
  .gs .bar { height: 8px; border-radius: 999px; background: var(--line); overflow: hidden; margin: 6px 0 2px; }
  .gs .bar > i { display: block; height: 100%; background: var(--up); }
  .gs code { font: 12px ui-monospace, SFMono-Regular, Menlo, monospace; background: var(--bg); padding: 1px 4px; border-radius: 4px; }
  .gs a { color: inherit; }`;
  document.head.appendChild(css);

  const chip = (ok, yes, no, bad) => `<span class="chip ${ok ? "ok" : bad ? "bad" : ""}">${ok ? "✓ " + yes : no}</span>`;

  window.startShell = () => `<div class="gs"><h2 style="font-size:16px;margin:0">Get started</h2>
    <p class="muted">Five short steps. Only step 2 is needed for real market data; the rest are optional. You can come back here any time.</p>
    <div id="gsbody"><p class="muted">Checking your setup…</p></div></div>`;

  window.loadStart = async function (fresh) {
    let s;
    try { s = await capi("/api/setup/status", { fresh: !!fresh }); }
    catch (e) { $("gsbody").innerHTML = `<p class="err">${esc(e.message)}</p>`; return; }
    const k = s.keys, keysOk = k.state === "ok";
    const keyNote = { none: "Not set up yet: you're seeing made-up demo prices (plus real crypto history).",
      rejected: `Alpaca didn't accept your saved keys (${esc(k.masked)}). Make new paper keys and paste them below.`,
      live_key: `Your saved key (${esc(k.masked)}) isn't a paper key. BotScope is paper only: paste paper keys below.`,
      offline: "Couldn't reach Alpaca to check your keys: are you online?",
      ok: `Working: Alpaca paper account, key ${esc(k.masked)}.` }[k.state];
    const cl = s.claude;
    $("gsbody").innerHTML = `
    <div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="${s.total}" aria-valuenow="${s.done}" aria-label="Setup progress"><i style="width:${100 * s.done / s.total}%"></i></div>
    <p class="muted">${s.done} of ${s.total} done</p>

    <div class="step"><h3>1. Try it ${chip(true, "done", "")}</h3>
      <p>You're in BotScope Studio. Every tab works now. Without keys, stock prices are made up (the <b>DEMO DATA</b> badge) and crypto uses real past prices.
      Try the <a href="#tutorial">Tutorial</a> or click any candle in the <a href="#bot">Bot view</a>.</p></div>

    <div class="step" id="gs-keys"><h3>2. Real market data (free) ${chip(keysOk, "working", "to do", k.state === "rejected" || k.state === "live_key")}</h3>
      <p>${keyNote}</p>
      ${k.from_environment ? `<p class="msg bad">Note: your environment sets ALPACA_API_KEY, which wins over anything saved here.</p>` : ""}
      <details ${keysOk ? "" : "open"}><summary>${keysOk ? "Replace my keys" : "How to get your free keys (about 2 minutes)"}</summary>
      <ol>
        <li>Go to <a href="https://alpaca.markets" target="_blank" rel="noopener noreferrer">alpaca.markets</a> and sign up (free). You don't need to add money.</li>
        <li>After you log in, make sure you're in your <b>Paper</b> account: top left, the account switch says <b>Paper</b>.</li>
        <li>On the home page, find <b>API Keys</b> on the right and press <b>Generate New Keys</b>.</li>
        <li>Copy the <b>Key ID</b> (starts with <code>PK</code>) and the <b>Secret Key</b> into the boxes below. Alpaca shows the secret only once.</li>
      </ol>
      <p class="muted">Already have a bot using Alpaca? Use the <b>same</b> keys it uses: making new ones switches off the old ones.</p>
      <form id="gskeys" autocomplete="off">
        <div class="row"><input id="gsk" aria-label="Key ID" placeholder="Key ID (starts with PK)" spellcheck="false" autocomplete="off"></div>
        <div class="row"><input id="gss" type="password" aria-label="Secret Key" placeholder="Secret Key" spellcheck="false" autocomplete="new-password">
          <button type="submit" class="primary">Check and save</button></div>
        <p class="muted">BotScope checks them with Alpaca's paper account (read-only), then saves them in <code>${esc(k.file || "")}</code> on this computer, readable only by you. They're never shown again or sent anywhere else. Paper keys only.</p>
        <p class="msg" id="gskmsg" role="status"></p></form></details></div>

    <div class="step"><h3>3. Your bots ${chip(s.bots.imported > 0, `${s.bots.imported} imported`, "optional")}</h3>
      <p>BotScope has ${s.bots.count} bot${s.bots.count === 1 ? "" : "s"} in your bots folder now (the examples to start). Bring in your own:</p>
      <ul>
        <li><b>Already trading on your Alpaca paper account?</b> ${s.bots.imported ? `✓ Already imported: see <a href="#imported">My bots</a>.` : keysOk ? `<button type="button" id="gsimp">Import my trades (read-only)</button>` : "Do step 2 first, then come back here."}
          <span class="msg" id="gsimpmsg" role="status"></span></li>
        <li><b>Have a trade log (CSV)?</b> Ask Claude: <code>import my bot from ~/path/trades.csv</code></li>
        <li><b>Have a TradingView strategy?</b> Ask Claude: <code>import this Pine script</code> and paste it.</li>
        <li><b>Want a new one?</b> Describe it in the <a href="#factory">Factory</a> tab.</li></ul>
      <p class="muted">See them all in <a href="#imported">My bots</a>. BotScope only reads your trades: it never places, changes or cancels an order.</p></div>

    <div class="step"><h3>4. Claude inside Studio (optional) ${chip(s.console_on && cl.logged_in, "ready", "optional")}</h3>
      <ol>
        <li>${s.console_on ? "✓ The Claude panel is on." : `Open <button type="button" class="linkbtn" id="gsset">⚙ Settings</button> and press <b>Switch on</b> (it's off every time BotScope starts).`}</li>
        <li>${!cl.found ? "Claude Code (the <code>claude</code> command) isn't installed on this computer: get it at claude.com/claude-code." :
            cl.logged_in ? "✓ Your <code>claude</code> command is logged in." :
            `Your <code>claude</code> command needs its own login (separate from the Claude app). ${s.terminal ? "Open the <b>Claude</b> panel → <b>Terminal</b>" : "Open your computer's Terminal app"}, type <code>claude</code>, press Enter and follow the login steps.`}</li>
      </ol></div>

    <div class="step"><h3>5. Extra market data (optional) ${chip(Object.values(s.optional).every((o) => o.set), "all set", "optional")}</h3>
      <p class="muted">Each is free and unlocks more Desk panels. Skip any you don't need.</p>
      ${Object.entries(s.optional).map(([n, o]) => `<form class="gsopt" data-name="${esc(n)}" autocomplete="off">
        <b>${esc(n)}</b> ${o.set ? `<span class="chip ok">✓ set</span>` : ""} <span class="muted">${esc(o.unlocks)} · <a href="${esc(o.where)}" target="_blank" rel="noopener noreferrer">get it</a></span>
        <div class="row"><input aria-label="${esc(n)}" placeholder="${n === "SEC_USER_AGENT" ? "Your Name your@email.com" : "paste it here"}" spellcheck="false" autocomplete="off"><button type="submit">Save</button></div>
        <p class="msg" role="status"></p></form>`).join("")}
      <h3 style="margin-top:14px">Other API keys <span class="chip">optional</span></h3>
      <p class="muted">Have a key for another data service (Polygon, Tiingo, a news API, a Discord webhook…)? Save it here under a name you choose. Then ask Claude to wire it in, e.g. <code>use my POLYGON_API_KEY to add a Desk panel for options flow</code>: Claude writes that code in BotScope, and nothing uses the key until it exists. BotScope's own switches and your Alpaca keys can't be set here.</p>
      ${(s.custom || []).length ? `<ul class="inside" id="gscustomlist">${s.custom.map((c) => `<li><code>${esc(c.name)}</code> ${esc(c.masked)} <button type="button" class="linkbtn" data-rmkey="${esc(c.name)}">Remove</button></li>`).join("")}</ul>` : ""}
      <form id="gscustom" autocomplete="off"><div class="row">
        <input id="gscn" aria-label="Key name" placeholder="NAME_OF_THE_KEY" spellcheck="false" autocomplete="off" style="flex:0 1 220px">
        <input id="gscv" type="password" aria-label="Key value" placeholder="paste the key" spellcheck="false" autocomplete="new-password">
        <button type="submit">Add key</button></div><p class="msg" id="gscmsg" role="status"></p></form></div>

    <p class="muted">Want a friend to compare bots with? See the <a href="#friends">Friends</a> tab.</p>`;

    $("gskeys").onsubmit = async (e) => {
      e.preventDefault();
      const m = $("gskmsg"); m.className = "msg"; m.textContent = "Checking with Alpaca…";
      try {
        const r = await capi("/api/setup/keys", { api_key: $("gsk").value, secret: $("gss").value });
        $("gss").value = "";
        if (!r.saved) { m.className = "msg bad"; m.textContent = r.why; return; }
        $("gsk").value = "";
        m.className = "msg ok"; m.textContent = `Saved (${r.masked}). ${r.warning || ""} Reloading with real data…`;
        setTimeout(() => location.reload(), 1500);
      } catch (err) { m.className = "msg bad"; m.textContent = err.message; }
    };
    if ($("gsimp")) $("gsimp").onclick = async () => {
      const m = $("gsimpmsg"); $("gsimp").disabled = true; m.className = "msg"; m.textContent = " Reading your order history…";
      try {
        const r = await capi("/api/setup/import", {});
        if (r.error) throw new Error(r.error);
        m.className = "msg ok"; m.textContent = ` Imported ${r.trades} trades. See them in My bots.`;
      } catch (err) { m.className = "msg bad"; m.textContent = " " + err.message; }
      $("gsimp").disabled = false;
    };
    if ($("gsset")) $("gsset").onclick = () => $("setbtn").click();
    $("gscustom").onsubmit = async (e) => {
      e.preventDefault();
      const m = $("gscmsg");
      try {
        const r = await capi("/api/setup/custom", { name: $("gscn").value, value: $("gscv").value });
        $("gscv").value = "";
        m.className = "msg " + (r.saved ? "ok" : "bad"); m.textContent = r.saved ? `Saved ${r.name} (${r.masked}). ${r.next}` : r.why;
        if (r.saved) { $("gscn").value = ""; setTimeout(() => loadStart(), 2500); }
      } catch (err) { m.className = "msg bad"; m.textContent = err.message; }
    };
    document.querySelectorAll("[data-rmkey]").forEach((b) => b.onclick = async () => {
      if (!confirm(`Remove ${b.dataset.rmkey} from your .env?`)) return;
      try { await capi("/api/setup/custom_remove", { name: b.dataset.rmkey }); loadStart(); } catch (err) { $("gscmsg").textContent = err.message; }
    });
    document.querySelectorAll(".gsopt").forEach((f) => f.onsubmit = async (e) => {
      e.preventDefault();
      const m = f.querySelector(".msg"), inp = f.querySelector("input");
      try {
        const r = await capi("/api/setup/optional", { name: f.dataset.name, value: inp.value });
        m.className = "msg " + (r.saved ? "ok" : "bad"); m.textContent = r.saved ? "Saved. " + r.next : r.why;
        if (r.saved) inp.value = "";
      } catch (err) { m.className = "msg bad"; m.textContent = err.message; }
    });
  };
})();
