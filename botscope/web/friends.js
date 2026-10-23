// Studio's Friends tab: swap friend codes and compare bots, read-only. A friend code is one block of text with a
// bot's honest numbers (untested years, after costs); a friend's card is shown and compared as numbers only, never
// run, and nothing is copied or changed. No server: codes travel by any chat app. Uses Studio's $, esc, enc, botList.
(function () {
  const css = document.createElement("style");
  css.textContent = `
  .fr textarea { width: 100%; font: 12px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; color: inherit; background: var(--bg);
    border: 1px solid var(--line); border-radius: 6px; padding: 6px; resize: vertical; word-break: break-all; }
  .fr .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 6px 0; }
  .fr .row > input[type=text], .fr .row > select { flex: 1 1 160px; min-width: 0; }
  .fr .primary { background: color-mix(in srgb, var(--accent) 72%, #000); color: #fff; border-color: transparent; font-weight: 600; }
  .fr .lesson { border-top: 1px solid var(--line); padding: 8px 0; }
  .fr .lesson b { display: block; }
  .fr ul.inside { margin: 4px 0; padding-left: 18px; font-size: 13px; }
  .fr .who { font-weight: 600; }
  .fr td.y, .fr td.t { white-space: nowrap; }
  .fr td.act .linkbtn + .linkbtn { margin-left: 8px; }
  @media (max-width: 600px) { .fr table.cmp td, .fr table.cmp th { font-size: 12px; padding: 4px; } .fr td.y, .fr td.t { white-space: normal; } .fr .dat { display: none; } .fr td.act .linkbtn { display: block; margin: 0 0 4px; } }`;
  document.head.appendChild(css);

  window.friendsShell = () => `<div class="fr">
  <h2 style="font-size:16px;margin:0">Friends</h2>
  <p class="muted">Swap friend codes and compare bots. Read-only: a code holds a bot's honest numbers (untested years, after
  costs), never its code, keys, account or dollars. Nothing is copied, run or changed, and there's no server: you send
  the code any way you like.</p>
  <p class="muted"><b>Friends can't take or edit your bot, and you can't take or edit theirs.</b> A code has no bot code
  in it, and nothing here can write to your bots folder.</p>
  <div class="card"><h2>Your friend code</h2>
    <div class="row"><select id="frBot" aria-label="Which of your bots"></select>
      <input type="text" id="frName" maxlength="30" placeholder="Your name for friends (e.g. Alex)" aria-label="Your name for friends"></div>
    <label class="row muted"><input type="checkbox" id="frRules"> Include its rules and tickers (off = only results are shared)</label>
    <div class="row"><button type="button" class="primary" id="frMake">Make code</button><span class="muted" id="frMakeMsg" role="status"></span></div>
    <div id="frOut" hidden><textarea id="frCode" rows="4" readonly aria-label="Your friend code"></textarea>
      <div class="row"><button type="button" id="frCopy">Copy</button><span class="muted">Send it to a friend; they paste it into their Friends tab.</span></div>
      <details><summary class="muted">Exactly what's inside</summary><ul class="inside" id="frInside"></ul></details></div></div>
  <div class="card"><h2>Add a friend</h2>
    <textarea id="frPaste" rows="3" maxlength="13000" placeholder="Paste a friend code (starts with BOTSCOPE-FRIEND-1:)" aria-label="Friend code"></textarea>
    <div class="row"><button type="button" id="frCheck">Check it</button><span class="muted" id="frAddMsg" role="status"></span></div>
    <div id="frPreview"></div></div>
  <div class="card"><h2>Your friends</h2><div id="frList"><p class="muted">Loading…</p></div></div>
  <div class="card" id="frCmpCard" hidden><h2>Compare</h2>
    <div class="row"><select id="frMine" aria-label="Your bot"></select><span class="muted">vs</span><select id="frTheirs" aria-label="Friend's bot"></select></div>
    <div id="frCmp"></div></div></div>`;

  const post = async (path, body) => {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json();
    if (!r.ok || j.error) throw new Error(j.error || r.statusText);
    return j;
  };
  const get = async (path) => { const r = await fetch(path); const j = await r.json(); if (!r.ok || j.error) throw new Error(j.error || r.statusText); return j; };
  const R = (x) => x == null ? "–" : `${x > 0 ? "+" : ""}${(+x).toFixed(2)}R`;
  function inside(c) {                       // every field the card holds, in plain words
    const items = [["Name", c.name], ["Bot", `${c.bot} (${c.timeframe || "?"}, ${c.sides || "?"})`], ["Data", c.data],
      ["Report day", c.report_day], ["Untested trades", c.untested_trades], ["Untested years", c.untested_years],
      ["Losing years", c.losing_years], ["Average per trade", R(c.avg_r)], ["Total", R(c.total_r)], ["Bad end of the range", R(c.range_low_r)],
      ["Costs (total)", c.costs_r == null ? "–" : `${(+c.costs_r).toFixed(2)}R`], ["Trades won", c.wins == null ? "–" : `${c.wins} of ${c.untested_trades}`], ["Average win / loss", `${R(c.avg_win_r)} / ${R(c.avg_loss_r)}`],
      ["Worst losing streak", c.worst_losing_streak ?? "–"], ["Deepest drop", R(c.max_drawdown_r)], ["If costs doubled", R(c.if_costs_doubled_r)],
      ["Without best 3 trades", R(c.without_best_3_r)], ["Years beat holding SPY", c.years_beat_spy ?? "–"], ["Luck meter", c.luck], ["Confidence", c.confidence],
      ["Each year", (c.by_year || []).map((y) => `${y.year}: ${y.trades} trades, ${R(y.avg_r)}`).join("; ") || "–"]];
    if (c.rules) items.push(["Rules", c.rules.join(" · ") || "–"]);
    if (c.symbols) items.push(["Tickers", c.symbols.join(", ") || "–"]);
    return items.map(([k, v]) => `<li><b>${esc(k)}:</b> ${esc(v)}</li>`).join("");
  }

  let friends = [];
  window.loadFriends = async function () {
    const bots = (typeof botList !== "undefined" && botList) || [];
    const opts = bots.map((b) => `<option value="${esc(b.id)}">${esc(b.name)}</option>`).join("");
    if (!$("frBot").options.length) { $("frBot").innerHTML = opts; $("frMine").innerHTML = opts; $("frBot").value = $("frMine").value = bot();
      try { $("frName").value = localStorage.getItem("botscope-friend-name") || ""; } catch { /* private window */ } }
    try { friends = (await get("/api/friends")).friends; } catch (e) { $("frList").innerHTML = `<p class="err">${esc(e.message)}</p>`; return; }
    $("frList").innerHTML = friends.length ? `<div class="tablewrap"><table><tr><th>Friend</th><th>Bot</th><th class="num">Untested trades</th><th class="num">Per trade</th><th class="dat">Data</th><th></th></tr>
      ${friends.map((f) => `<tr><td class="who">${esc(f.card.name)}</td><td>${esc(f.card.bot)}${f.card.rules ? ' <span class="muted">(rules shared)</span>' : ""}</td>
        <td class="num">${f.card.untested_trades}</td><td class="num">${R(f.card.avg_r)}</td><td class="dat">${esc(f.card.data)}</td>
        <td class="act"><button type="button" class="linkbtn" data-frcmp="${esc(f.id)}">Compare</button> <button type="button" class="linkbtn" data-frdel="${esc(f.id)}">Remove</button></td></tr>`).join("")}</table></div>`
      : `<p class="muted">No friends yet. Make your code above and send it; paste theirs under "Add a friend".</p>`;
    $("frCmpCard").hidden = !friends.length;
    const keep = $("frTheirs").value;
    $("frTheirs").innerHTML = friends.map((f) => `<option value="${esc(f.id)}">${esc(f.card.name)}: ${esc(f.card.bot)}</option>`).join("");
    if (friends.some((f) => f.id === keep)) $("frTheirs").value = keep;
    if (friends.length) compare();
  };

  async function compare() {
    const el = $("frCmp");
    el.innerHTML = `<p class="muted">Comparing…</p>`;
    let r;
    try { r = await get(`/api/friends/compare?bot=${enc($("frMine").value)}&friend=${enc($("frTheirs").value)}&name=${enc($("frName").value || "me")}`); }
    catch (e) { el.innerHTML = `<p class="err">${esc(e.message)}</p>`; return; }
    const who = r.theirs.name;
    const list = (ls) => ls.map((l) => `<div class="lesson"><b>${esc(l.title)}</b>${esc(l.what)}<div class="muted">${esc(l.use)}</div></div>`).join("");
    el.innerHTML = `<div class="tablewrap"><table class="cmp"><tr><th></th><th>Yours</th><th>${esc(who)}'s</th></tr>
      ${r.rows.map((x) => `<tr><th title="${esc(x.why)}">${esc(x.row)}</th><td class="y">${esc(x.yours)}</td><td class="t">${esc(x.theirs)}</td></tr>`).join("")}</table></div>
      <h3 style="font-size:14px;margin:12px 0 0">What your bot can learn from ${esc(who)}'s</h3>${list(r.for_you)}
      <details><summary class="muted">What ${esc(who)}'s summary will say (made on their computer when they paste your code)</summary>${list(r.for_friend)}</details>
      ${r.theirs.rules ? `<details><summary class="muted">${esc(who)}'s rules (read-only)</summary><ol class="muted">${r.theirs.rules.map((x) => `<li>${esc(x)}</li>`).join("")}</ol></details>` : ""}
      <p class="muted">${esc(r.note)}</p>
      <button type="button" class="linkbtn" data-ask="${esc(`Compare my bot ${$("frMine").value} with my friend ${who}'s bot ${r.theirs.bot} (BotScope Friends tab, untested years after costs). Which lesson is worth testing first on mine, and how would I test it with run_backtest?`)}">Ask Claude about this</button>`;
  }

  document.addEventListener("change", (e) => { if (e.target.id === "frMine" || e.target.id === "frTheirs") compare(); });
  document.addEventListener("click", async (e) => {
    const t = e.target.closest("button");
    if (!t || !t.closest(".fr")) return;
    if (t.id === "frMake") {
      $("frMakeMsg").textContent = "Making…";
      try { localStorage.setItem("botscope-friend-name", $("frName").value); } catch { /* private window */ }
      try {
        const r = await post("/api/friends/code", { bot: $("frBot").value, name: $("frName").value || "me", include_rules: $("frRules").checked });
        $("frCode").value = r.code; $("frInside").innerHTML = inside(r.card); $("frOut").hidden = false;
        $("frMakeMsg").textContent = `${r.characters} characters${r.includes_rules ? ", rules included" : ", results only"}.`;
      } catch (err) { $("frMakeMsg").innerHTML = `<span class="err">${esc(err.message)}</span>`; }
    } else if (t.id === "frCopy") {
      try { await navigator.clipboard.writeText($("frCode").value); t.textContent = "Copied"; }
      catch { $("frCode").select(); t.textContent = "Press ⌘C to copy"; }
      setTimeout(() => { t.textContent = "Copy"; }, 2000);
    } else if (t.id === "frCheck") {              // preview first: see exactly what the card holds before adding it
      const code = $("frPaste").value.trim();
      $("frAddMsg").textContent = ""; $("frPreview").innerHTML = "";
      if (!code) { $("frAddMsg").textContent = "Paste a friend code first."; return; }
      try {
        const c = await post("/api/friends/check", { code });
        $("frPreview").innerHTML = `<p><span class="who">${esc(c.card.name)}</span>: ${esc(c.card.bot)}. It holds:</p><ul class="inside">${inside(c.card)}</ul>
          <div class="row"><button type="button" class="primary" id="frAdd">Add ${esc(c.card.name)}</button><button type="button" id="frCancel">Cancel</button></div>`;
      } catch (err) { $("frAddMsg").innerHTML = `<span class="err">${esc(err.message)}</span>`; }
    } else if (t.id === "frAdd") {
      try { await post("/api/friends/add", { code: $("frPaste").value.trim() }); $("frPaste").value = ""; $("frPreview").innerHTML = "";
        $("frAddMsg").textContent = "Added."; await loadFriends(); }
      catch (err) { $("frAddMsg").innerHTML = `<span class="err">${esc(err.message)}</span>`; }
    } else if (t.id === "frCancel") { $("frPreview").innerHTML = ""; }
    else if (t.dataset.frcmp) { $("frTheirs").value = t.dataset.frcmp; compare(); $("frCmpCard").scrollIntoView({ block: "start", behavior: "smooth" }); }
    else if (t.dataset.frdel) { await post("/api/friends/remove", { id: t.dataset.frdel }); await loadFriends(); }
  });
})();
