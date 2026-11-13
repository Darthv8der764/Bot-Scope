// Studio's My trades tab: the trades you placed yourself, imported read-only. Import (a Webull CSV or a fills CSV
// read in this browser and sent only to BotScope on this computer, your Alpaca paper history, or made-up demo
// trades), the pattern table (plain counts, dollars and R; small rows say so) and the trade list with your notes.
// Nothing here can place, change or cancel an order. Uses Studio's $, esc, enc, fmtR.
(function () {
  const css = document.createElement("style");
  css.textContent = `
  .mt .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 6px 0; }
  .mt [hidden] { display: none !important; }                     /* .row's flex would show hidden rows */
  .mt .row > input[type=text], .mt .row > select, .mt .row > input[type=file] { flex: 1 1 180px; min-width: 0; }
  .mt .primary { background: color-mix(in srgb, var(--accent) 72%, #000); color: #fff; border-color: transparent; font-weight: 600; }
  .mt h3 { font-size: 13px; margin: 14px 0 0; }
  .mt tr.small td { color: var(--muted); }
  .mt td.grp { font-weight: 600; }
  .mt .noteform { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 6px 10px; padding: 8px 0; }
  .mt .noteform label { display: flex; flex-direction: column; gap: 2px; font-size: 12px; color: var(--muted); }
  .mt .noteform input, .mt .noteform select { color: var(--ink); width: 100%; }
  .mt .noteform .wide { grid-column: 1 / -1; }
  .mt tr.noterow > td { background: var(--bg); }
  .mt .srcs li { margin: 2px 0; }
  .mt .cal { display: grid; grid-template-columns: auto repeat(5, minmax(0, 1fr)); gap: 4px; max-width: 520px; font-size: 12px; }
  .mt .cal .wd { color: var(--muted); text-align: center; } .mt .cal .wk { color: var(--muted); padding-right: 6px; white-space: nowrap; }
  .mt .cal .d { border-radius: 6px; min-height: 34px; padding: 3px 5px; background: var(--bg); border: 1px solid var(--line); line-height: 1.2; }
  .mt .cal .d b { display: block; font-size: 11px; } .mt .cal .d.empty { border-style: dashed; opacity: .5; }
  @media (max-width: 600px) { .mt table.trades tr.noterow { display: block; } .mt table.trades tr.noterow > td { display: block; } }`;
  document.head.appendChild(css);

  const ZONES = ["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Phoenix",
    "America/Anchorage", "Pacific/Honolulu", "Europe/London", "UTC"];
  window.mytradesShell = () => `<div class="mt">
  <div class="card"><h2>My trades</h2>
    <p class="muted">Trades you placed yourself (not a bot's), imported read-only and saved on this computer only.
    Plain numbers from your own past trades: counts, dollars, and R when you note a stop. Nothing here places, changes
    or cancels an order, and it isn't financial advice.</p></div>
  <div class="card"><h2>Import</h2>
    <div class="row"><select id="mtBroker" aria-label="Where the trades come from">
      <option value="webull">Webull orders CSV</option>
      <option value="robinhood">Robinhood account activity CSV</option>
      <option value="fidelity">Fidelity account history CSV</option>
      <option value="fills">Fills CSV (symbol, side, qty, price, time, tz)</option>
      <option value="alpaca">Alpaca paper account (last 90 days)</option>
      <option value="demo">Demo trades (made up)</option></select></div>
    <div class="row" id="mtFileRow"><input type="file" id="mtFile" accept=".csv,text/csv" aria-label="CSV file"></div>
    <div class="row" id="mtTzRow"><label class="muted" for="mtTz">Time zone of the file's times</label>
      <input type="text" id="mtTz" list="mtZones" placeholder="e.g. America/Chicago" aria-label="Time zone of the file's times">
      <datalist id="mtZones">${ZONES.map((z) => `<option value="${z}">`).join("")}</datalist></div>
    <p class="muted" id="mtHint"></p>
    <div class="row"><button type="button" class="primary" id="mtGo">Import</button><span class="muted" id="mtMsg" role="status"></span></div>
    <div id="mtSources"></div></div>
  <div class="card"><h2>Pattern table</h2>
    <div class="row"><label class="muted" for="mtFrom">From</label><input type="date" id="mtFrom" aria-label="Trades opened from">
      <label class="muted" for="mtTo">to</label><input type="date" id="mtTo" aria-label="Trades opened up to">
      <button type="button" class="linkbtn" id="mtAll">all dates</button></div>
    <div id="mtPatterns"><p class="muted">Loading…</p></div></div>
  <div class="card"><h2>Calendar</h2><div id="mtCal"><p class="muted">Loading…</p></div></div>
  <div class="card"><h2>Trades and notes</h2><div id="mtTrades"><p class="muted">Loading…</p></div></div></div>`;

  const post = async (path, body) => {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json();
    if (!r.ok || j.error) throw new Error(j.error || r.statusText);
    return j;
  };
  const usd = (x) => x == null ? "–" : (x < 0 ? "-$" : "$") + Math.abs(x).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const px = (x) => x == null ? "" : "$" + (+x).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  const cls = (x) => x > 0 ? "up" : x < 0 ? "down" : "";
  const when = (s) => esc((s || "").replace("T", " ").slice(0, 16));
  let data = null, showAll = false;

  function brokerUi() {
    const b = $("mtBroker").value, file = ["webull", "fills", "robinhood", "fidelity"].includes(b);
    $("mtFileRow").hidden = !file; $("mtTzRow").hidden = !(b === "webull" || b === "fills");
    $("mtHint").textContent = {
      webull: "Webull: History tab → Export Orders (it's emailed to you). Its column names aren't confirmed yet: if they don't match, you'll see the file's columns. Times are read in the time zone you pick, and shown in US Eastern.",
      robinhood: "Robinhood: Account → Reports and statements → Account activity reports → Generate new report (it can take a few hours). Stock trades only, dates but no times, so they stay out of the time-of-day tables. Its column names aren't confirmed yet: if they don't match, you'll see the file's columns.",
      fidelity: "Fidelity: Activity & Orders → download the history as a CSV. Stock trades only, dates but no times, so they stay out of the time-of-day tables. Its column names aren't confirmed yet: if they don't match, you'll see the file's columns.",
      fills: "One row per fill. The tz column (or the time zone above) says what time zone each time is in.",
      alpaca: "Reads your filled orders from your Alpaca PAPER account (read-only). Orders marked as a bot's are left out.",
      demo: "A made-up trader's 8 weeks of trades with notes, to see how the table works. Not real.",
    }[b];
  }

  async function doImport() {
    const b = $("mtBroker").value, body = { broker: b };
    $("mtMsg").textContent = "";
    if (["webull", "fills", "robinhood", "fidelity"].includes(b)) {
      const f = $("mtFile").files[0];
      if (!f) { $("mtMsg").textContent = "Pick the CSV file first."; return; }
      if (b === "webull" && !$("mtTz").value.trim()) { $("mtMsg").textContent = "Which time zone are the file's times in?"; $("mtTz").focus(); return; }
      body.text = await f.text(); body.name = f.name; body.tz = $("mtTz").value.trim() || null;
    }
    $("mtGo").disabled = true; $("mtMsg").textContent = "Importing…";
    try {
      const r = await post("/api/mytrades/import", body);
      const parts = [`${r.round_trips} round trips from ${r.fills_read} fills`];
      if (r.bot_orders_skipped) parts.push(`${r.bot_orders_skipped} bot orders left out`);
      if (r.options_skipped) parts.push(`${r.options_skipped} option rows skipped (stocks only for now)`);
      if (r.not_trades) parts.push(`${r.not_trades} rows that aren't trades (dividends, transfers…) skipped`);
      if (r.duplicates_skipped) parts.push(`${r.duplicates_skipped} already imported from another source, left out`);
      if (r.not_filled) parts.push(`${r.not_filled} rows not filled (cancelled or open)`);
      if (r.unreadable) parts.push(`${r.unreadable} rows couldn't be read: ${r.unreadable_lines.join("; ")}`);
      if (r.still_open) parts.push(r.still_open);
      if (r.sold_before) parts.push(r.sold_before);
      if (r.demo_removed) parts.push(r.demo_removed);
      $("mtMsg").textContent = parts.join(" · ") + ".";
      await load();
    } catch (e) { $("mtMsg").textContent = e.message; }
    $("mtGo").disabled = false;
  }

  const head = `<tr><th>Group</th><th class="num">Trades</th><th class="num">Won</th><th class="num">Total $</th><th class="num">Avg $</th><th class="num">Avg R</th></tr>`;
  const prow = (r) => `<tr class="${r.enough ? "" : "small"}"><td class="grp" data-l="Group">${esc(r.group)}</td>
    <td class="num" data-l="Trades">${r.trades}</td>
    ${r.enough ? `<td class="num" data-l="Won">${r.won} of ${r.trades}</td>
    <td class="num ${cls(r.total_usd)}" data-l="Total $">${usd(r.total_usd)}</td><td class="num ${cls(r.avg_usd)}" data-l="Avg $">${usd(r.avg_usd)}</td>
    <td class="num" data-l="Avg R">${r.avg_r == null ? "–" : `${fmtR(r.avg_r)} <span class="muted">(${r.trades_with_r} with a stop)</span>`}</td>`
    : `<td colspan="4">${esc(r.note)}</td>`}</tr>`;
  const ptable = (title, rows) => rows && rows.length ? `<h3>${title}</h3><div class="tablewrap"><table class="trades">${head}${rows.map(prow).join("")}</table></div>` : "";

  function drawPatterns(p) {
    if (p && p.error && data.total) { $("mtPatterns").innerHTML = `<p class="muted">${esc(p.error)}</p>`; return; }
    if (!p || !p.trades) { $("mtPatterns").innerHTML = `<p class="muted">No trades imported yet. Import yours above, or see how it works first:</p>
      <p><button type="button" class="primary" data-demo>Try it on made-up demo trades</button></p>`; return; }
    $("mtPatterns").innerHTML = `<p class="muted">${p.trades} trades, ${esc(p.from)} to ${esc(p.to)} · ${esc(p.times)} ·
      rows under ${p.min_trades} trades are too small to compare.${p.sources.some((s) => /MADE-UP/.test(s)) ? " <b>Includes made-up demo trades.</b>" : ""}</p>
      ${ptable("All trades", [p.all])}${ptable("By setup", p.by_setup)}${ptable("By hour (entry)", p.by_hour)}
      ${ptable("By weekday", p.by_weekday)}${ptable("By weekday and time of day", p.by_day_part)}${ptable("By holding time", p.by_holding)}${ptable("By the trade before it (same day)", p.by_trade_before)}
      ${p.date_only_note ? `<p class="muted">${esc(p.date_only_note)}</p>` : ""}<p class="muted">${esc(p.note)}</p>`;
  }

  const sel = (id, key, val) => `<select id="${id}"><option value=""></option>${(data.choices[key] || []).map((c) => `<option${c === val ? " selected" : ""}>${esc(c)}</option>`).join("")}</select>`;
  function noteForm(t) {
    const c = t.checklist || {}, id = esc(t.trade_id);
    return `<tr class="noterow" data-for="${id}"><td colspan="10"><form class="noteform" data-id="${id}">
      <label>Setup tag<input type="text" name="setup" maxlength="40" value="${esc(t.setup || "")}" placeholder="e.g. pullback"></label>
      <label>Stop (gives R)<input type="number" name="stop" step="any" min="0" value="${t.stop ?? ""}"></label>
      <label>Risk ($ or %)<input type="text" name="risk" maxlength="40" value="${esc(c.risk || "")}"></label>
      <label>Profit target<input type="text" name="target" maxlength="40" value="${esc(c.target || "")}" placeholder="or: no plan yet"></label>
      <label>Last trade before it${sel("mtLast" + id, "last_trade", c.last_trade)}</label>
      <label>Trades today so far<input type="number" name="trades_today" min="0" step="1" value="${esc(c.trades_today || "")}"></label>
      <label>Big news soon?${sel("mtNews" + id, "big_news", c.big_news)}</label>
      <label>How did you feel?${sel("mtFeel" + id, "feeling", c.feeling)}</label>
      <label class="wide">Note<input type="text" name="note" maxlength="500" value="${esc(t.note || "")}"></label>
      <div class="row wide"><button type="submit" class="primary">Save note</button><button type="button" data-close>Close</button><span class="muted" role="status"></span></div>
    </form></td></tr>`;
  }
  const trow = (t) => `<tr data-id="${esc(t.trade_id)}"><td data-l="Opened">${when(t.opened)}</td><td data-l="Symbol"><b>${esc(t.symbol)}</b></td>
    <td data-l="Side">${esc(t.side)}</td><td class="num" data-l="Qty">${t.qty}</td><td class="num" data-l="Entry">${px(t.entry)}</td>
    <td class="num" data-l="Exit">${px(t.exit)}</td><td class="num ${cls(t.pnl)}" data-l="$">${usd(t.pnl)}</td><td class="num" data-l="R">${fmtR(t.r)}</td>
    <td data-l="Setup">${esc(t.setup || "")}</td><td data-l="Note"><button type="button" class="linkbtn" data-note="${esc(t.trade_id)}">${t.note || t.setup || t.stop ? "Edit note" : "Add note"}</button></td></tr>`;

  function drawCalendar() {             // one square per weekday: the day's total, green made money, red lost
    const from = $("mtFrom").value, to = $("mtTo").value, days = {};
    for (const t of data.trades) {
      const d = t.opened.slice(0, 10);
      if ((from && d < from) || (to && d > to)) continue;
      (days[d] = days[d] || { n: 0, usd: 0 }).n++; days[d].usd += t.pnl;
    }
    const keys = Object.keys(days).sort();
    if (!keys.length) { $("mtCal").innerHTML = `<p class="muted">No trades to show.</p>`; return; }
    const big = Math.max(...keys.map((k) => Math.abs(days[k].usd))) || 1;
    const day = (s) => new Date(s + "T12:00:00Z"), iso = (d) => d.toISOString().slice(0, 10);
    let d = day(keys[0]); d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));        // back to Monday
    const end = day(keys[keys.length - 1]), cells = ["<span></span>", ..."Mon Tue Wed Thu Fri".split(" ").map((w) => `<span class="wd">${w}</span>`)];
    for (; d <= end; d.setUTCDate(d.getUTCDate() + 7)) {
      cells.push(`<span class="wk">${esc(iso(d).slice(5))}</span>`);
      for (let i = 0; i < 5; i++) {
        const k = iso(new Date(d.getTime() + i * 864e5)), x = days[k];
        if (!x) { cells.push(`<span class="d empty" title="${k}: no trades"></span>`); continue; }
        const mix = Math.round(20 + 60 * Math.abs(x.usd) / big), c = x.usd > 0 ? "--up" : x.usd < 0 ? "--down" : "--line";
        const say = `${k}: ${x.n} trade${x.n === 1 ? "" : "s"}, ${usd(Math.round(x.usd * 100) / 100)}`;
        cells.push(`<span class="d" title="${esc(say)}" aria-label="${esc(say)}" style="background: color-mix(in srgb, var(${c}) ${mix}%, var(--panel))">
          <b>${x.usd > 0 ? "+" : x.usd < 0 ? "−" : "="} ${k.slice(8)}</b>${x.n}</span>`);
      }
    }
    $("mtCal").innerHTML = `<p class="muted">One square per weekday: + made money, − lost, darker means a bigger day. The number is
      how many trades. Hover or tap a square for the day's total.${data.total > data.trades.length ? ` Newest ${data.trades.length} trades only.` : ""}</p>
      <div class="cal" role="list">${cells.join("")}</div>`;
  }

  function drawTrades() {
    const ts = data.trades, list = showAll ? ts : ts.slice(0, 50);
    if (!ts.length) { $("mtTrades").innerHTML = `<p class="muted">No trades yet.</p>`; return; }
    $("mtTrades").innerHTML = `<p class="muted">Newest first · times in US Eastern · R shows when the note has a stop.</p>
      <div class="tablewrap"><table class="trades"><tr><th>Opened</th><th>Symbol</th><th>Side</th><th class="num">Qty</th><th class="num">Entry</th><th class="num">Exit</th><th class="num">$</th><th class="num">R</th><th>Setup</th><th>Note</th></tr>
      ${list.map(trow).join("")}</table></div>
      ${ts.length > list.length ? `<button type="button" id="mtMore">Show all ${ts.length} (${data.total > ts.length ? `newest ${ts.length} of ${data.total}` : "all"})</button>` : ""}`;
    if ($("mtMore")) $("mtMore").onclick = () => { showAll = true; drawTrades(); };
  }

  function drawSources() {
    const s = data.sources;
    $("mtSources").innerHTML = s.length ? `<h3>Imported</h3><ul class="srcs">${s.map((x) => `<li>${esc(x.source)}: ${x.trades} trades, ${esc(x.from)} to ${esc(x.to)}
      <button type="button" class="linkbtn" data-forget="${esc(x.source)}">remove</button></li>`).join("")}</ul>
      <p><a href="/api/mytrades/export.csv" download="my-trades.csv">Download my trades and notes (CSV)</a>
      <span class="muted">· saved to this computer, for any spreadsheet</span></p>` : "";
  }

  const mtUrl = () => {                           // the pattern table's date range, when one is set
    const p = new URLSearchParams();
    if ($("mtFrom").value) p.set("from", $("mtFrom").value);
    if ($("mtTo").value) p.set("to", $("mtTo").value);
    return "/api/mytrades" + (p.toString() ? "?" + p : "");
  };

  async function load() {
    try { data = await (await fetch(mtUrl())).json(); }
    catch (e) { $("mtPatterns").innerHTML = `<p class="muted">Could not load: ${esc(e.message)}</p>`; return; }
    drawSources(); drawPatterns(data.patterns); drawCalendar(); drawTrades();
  }

  window.tryMyTradesDemo = async () => {         // Get started's button: import the made-up trades, then open the tab
    await post("/api/mytrades/import", { broker: "demo" });
    show("mytrades");
    if (document.querySelector(".mt").dataset.wired) await load();
  };

  window.loadMyTrades = () => {
    const root = document.querySelector(".mt");
    if (!root.dataset.wired) {
      root.dataset.wired = "1";
      $("mtBroker").onchange = brokerUi; $("mtGo").onclick = doImport;
      $("mtFrom").onchange = $("mtTo").onchange = load;
      $("mtAll").onclick = () => { $("mtFrom").value = ""; $("mtTo").value = ""; load(); };
      root.addEventListener("click", async (e) => {
        if (e.target.closest("[data-demo]")) { $("mtBroker").value = "demo"; brokerUi(); doImport(); return; }
        const n = e.target.closest("[data-note]"), c = e.target.closest("[data-close]"), f = e.target.closest("[data-forget]");
        if (n) {
          const tr = n.closest("tr"), open = tr.nextElementSibling && tr.nextElementSibling.classList.contains("noterow");
          if (open) { tr.nextElementSibling.remove(); return; }
          tr.insertAdjacentHTML("afterend", noteForm(data.trades.find((t) => t.trade_id === n.dataset.note)));
          tr.nextElementSibling.querySelector("input").focus();
        }
        if (c) c.closest("tr.noterow").remove();
        if (f) {
          if (!confirm(`Remove the trades imported from "${f.dataset.forget}"? Your notes stay, in case you import it again.`)) return;
          try { await post("/api/mytrades/forget", { source: f.dataset.forget }); await load(); } catch (err) { $("mtMsg").textContent = err.message; }
        }
      });
      root.addEventListener("submit", async (e) => {
        const form = e.target.closest("form.noteform");
        if (!form) return;
        e.preventDefault();
        const g = (k) => form.elements[k].value.trim(), id = form.dataset.id, msg = form.querySelector("[role=status]");
        const body = { trade_id: id, setup: g("setup"), note: g("note"), stop: g("stop") === "" ? 0 : +g("stop"),
          checklist: { setup: g("setup"), stop: g("stop"), risk: g("risk"), target: g("target"), trades_today: g("trades_today"),
            last_trade: $("mtLast" + id).value, big_news: $("mtNews" + id).value, feeling: $("mtFeel" + id).value } };
        try {
          const t = await post("/api/mytrades/note", body);
          data.trades = data.trades.map((x) => x.trade_id === id ? t : x);
          msg.textContent = "Saved.";
          const tr = form.closest("tr.noterow").previousElementSibling;
          tr.outerHTML = trow(t);
          fetch(mtUrl()).then((r) => r.json()).then((d) => { data = d; drawPatterns(d.patterns); }).catch(() => {});
        } catch (err) { msg.textContent = err.message; }
      });
      brokerUi();
    }
    load();
  };
})();
