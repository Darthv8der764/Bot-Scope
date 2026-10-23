// Studio's Signals tab: where YOUR strategies' own entry rules fire on the latest finished bar, refreshed every minute
// while the US market is open (crypto: any time). Each row is one strategy's rule with its track record next to it;
// nothing is scored here and nothing places an order. Paper only, not financial advice. Uses Studio's $, esc, enc,
// show, frames and current.
(function () {
  const css = document.createElement("style");
  css.textContent = `
  .sg .row { display: flex; gap: 8px 14px; flex-wrap: wrap; align-items: center; margin: 6px 0; }
  .sg .paper { border: 1px solid #b45309; border-radius: 10px; padding: 8px 10px; font-size: 13px; margin-top: 8px; }
  .sg .status { font-variant-numeric: tabular-nums; }
  .sg .says { font-weight: 600; }
  .sg .track { font-size: 12px; color: var(--muted); }
  .sg td.why { min-width: 180px; }
  .sg td.who { min-width: 230px; } .sg td.at { white-space: nowrap; }
  .sg td.who .lvl { margin-top: 4px; }
  .sg .tag { display: inline-block; font-size: 11px; padding: 0 6px; border: 1px solid var(--line); border-radius: 999px; color: var(--muted); margin-left: 4px; }
  @media (max-width: 600px) {
    .sg table.sig tr:first-child { display: none; }
    .sg table.sig tr { display: grid; grid-template-columns: 1fr 1fr; gap: 2px 10px; padding: 8px 0; border-top: 1px solid var(--line); }
    .sg table.sig td { border: 0; padding: 0; text-align: left; }
    .sg table.sig td[data-l]::before { content: attr(data-l) ": "; color: var(--muted); font-size: 12px; }
    .sg table.sig td.wide { grid-column: 1 / -1; } }`;
  document.head.appendChild(css);

  const EX_KEY = "botscope-signals-examples";
  const exStored = () => { try { return localStorage.getItem(EX_KEY) === "1"; } catch { return false; } };

  window.signalsShell = () => `<div class="sg">
  <h2 style="font-size:16px;margin:0">Signals: what your strategies say right now</h2>
  <div class="paper"><b>Paper only, not financial advice.</b> Each row is what one of <b>your own strategies' rules</b> says on
    the latest finished bar, replayed on today's bars so far, with that strategy's track record next to it. It is not a
    recommendation, and nothing on this page places an order.</div>
  <div class="row"><button type="button" id="sgRefresh">Refresh</button>
    <label class="muted"><input type="checkbox" id="sgEx"> Include example bots</label>
    <span class="muted status" id="sgStatus" role="status" aria-live="polite">Loading…</span></div>
  <div id="sgBody"></div></div>`;

  const px = (x) => x == null ? "–" : "$" + (+x).toLocaleString(undefined, { maximumFractionDigits: x < 10 ? 4 : 2 });
  const R = (x) => x == null ? "–" : `${x > 0 ? "+" : ""}${(+x).toFixed(2)}R`;
  const view = (r) => `<a href="${esc(r.link)}" data-sgview="${esc(r.link)}">Chart</a>`;
  const track = (t) => `<span class="lvl" title="${esc(t.why.join("; "))}">confidence ${esc(t.confidence)}</span>
    <div class="track">${esc(t.untested_trades ? `${t.untested_trades} untested trades, ${R(t.untested_avg_r)} each (${t.untested_source})` : "no untested backtest yet")}${t.live_paper_trades ? ` · ${t.live_paper_trades} live paper, ${R(t.live_paper_avg_r)} each` : ""}</div>`;
  const plan = (r) => `<td class="num" data-l="Price">${px(r.price)}</td><td class="num" data-l="Stop">${px(r.stop)}</td>
    <td class="num" data-l="Target">${r.target == null ? "none" : `${px(r.target)} <span class="muted">(${r.target_r}R)</span>`}</td>
    <td class="num" data-l="Risk">${px(r.risk)} <span class="muted">(${r.risk_pct}%)</span></td>`;
  const head = (extra) => `<tr><th>Your strategy says (and its track record)</th><th>At</th><th class="num">Price</th><th class="num">Stop</th><th class="num">Target</th><th class="num">Risk (1R)</th>${extra}<th>Why (its own words)</th></tr>`;
  const who = (r) => `<td class="wide who" data-l="Says"><span class="says">${esc(r.says)}</span> <b>${esc(r.symbol)}</b>${r.mine ? "" : '<span class="tag">example</span>'} · ${view(r)}
    <div>${track(r.track)}</div></td><td class="at" data-l="At">${esc(r.time_label)}</td>`;
  const tail = (r, why) => `<td class="wide why" data-l="Why">${esc(why)}</td>`;

  function table(rows, kind) {
    if (kind === "signal") return `<table class="sig">${head("")}${rows.map((r) => `<tr>${who(r)}${plan(r)}${tail(r, r.reason)}</tr>`).join("")}</table>`;
    if (kind === "close") return `<table class="sig">${head("")}${rows.map((r) => `<tr>${who(r)}${plan(r)}${tail(r, `would be: ${r.reason}. Held back by its rule: ${r.blocked_by}`)}</tr>`).join("")}</table>`;
    return `<table class="sig">${head('<th class="num">Since</th>')}${rows.map((r) => `<tr>${who(r)}${plan(r)}
      <td class="num ${r.moved_r > 0 ? "up" : r.moved_r < 0 ? "down" : ""}" data-l="Since">${R(r.moved_r)} <span class="muted">(${px(r.last_price)} now)</span></td>${tail(r, r.reason)}</tr>`).join("")}</table>`;
  }

  let timer = null, loading = false, last = null;
  async function load() {
    if (loading) return;
    loading = true;
    $("sgStatus").textContent = "Checking your strategies…";
    try {
      const res = await fetch(`/api/signals?examples=${$("sgEx").checked ? 1 : 0}`);
      const r = await res.json();
      if (!res.ok || r.error) throw new Error(r.error || res.statusText);
      last = r; draw(r);
    } catch (e) {
      $("sgStatus").innerHTML = `<span class="err">Could not check: ${esc(e.message)}</span>${last ? ` · showing ${esc(last.as_of_label)}` : ""}`;
    } finally { loading = false; schedule(); }
  }

  function draw(r) {
    const live = r.refresh_s && !document.hidden;
    $("sgStatus").textContent = `Updated ${r.as_of_label} · ${r.market.note}${r.busy ? ` (${r.busy})` : ""}${live ? "" : r.refresh_s ? " Paused while hidden." : " Not refreshing: press Refresh."}`;
    const card = (title, sub, rows, kind, none) => `<div class="card"><h2>${title} (${rows.length})</h2><p class="muted">${sub}</p>
      ${rows.length ? `<div class="tablewrap">${table(rows, kind)}</div>` : `<p class="muted">${none}</p>`}</div>`;
    const bots = r.bots.map((b) => `<tr><td data-l="Strategy"><b>${esc(b.name)}</b>${b.mine ? "" : '<span class="tag">example</span>'}</td>
      <td data-l="Bars">${esc(b.timeframe)}</td><td data-l="Symbols">${b.checked} of ${b.symbols.length}: ${esc(b.symbols.join(", "))}</td>
      <td class="wide" data-l="Track record">${track(b.track)}</td>
      <td class="wide muted" data-l="Notes">${esc(b.problems.join("; ")) || "–"}</td></tr>`).join("");
    $("sgBody").innerHTML = (r.empty_reason ? `<div class="card"><p>${esc(r.empty_reason)}</p></div>` : "") +
      card("Your strategy says buy (or sell short) now", `Its entry rule fired on the latest finished bar, or within the last ${r.window_min} minutes. Daily strategies: at the last daily close.`,
           r.signals, "signal", "None of your strategies' entry rules fire right now.") +
      card("Close to firing", "The strategy's own near miss on the latest bar: the trade it would take if the rule that held it back passed.",
           r.close, "close", "No near misses on the latest bar.") +
      card("Already in a trade", "Entries from earlier in the session (daily strategies: earlier days) that are still open on paper.",
           r.in_trade, "in_trade", "None of your strategies is in a paper trade right now.") +
      `<div class="card"><h2>Strategies watched (${r.bots.length})</h2><p class="muted">Your own first. Track record = the confidence meter, untested backtest days and closed live paper trades saved on this computer.</p>
        ${r.bots.length ? `<div class="tablewrap"><table class="sig"><tr><th>Strategy</th><th>Bars</th><th>Symbols checked</th><th>Track record</th><th>Notes</th></tr>${bots}</table></div>` : ""}
        ${r.problems.length ? `<p class="err">${r.problems.map(esc).join("<br>")}</p>` : ""}
        <p class="muted">${esc(r.note)}</p></div>`;
  }

  function schedule() {
    clearTimeout(timer); timer = null;
    if (!last || !last.refresh_s || document.hidden || current !== "signals") return;
    timer = setTimeout(() => { if (!document.hidden && current === "signals") load(); }, last.refresh_s * 1000);
  }

  window.loadSignals = function () {
    $("sgEx").checked = exStored();
    $("sgEx").onchange = () => { try { localStorage.setItem(EX_KEY, $("sgEx").checked ? "1" : "0"); } catch { /* private window */ } load(); };
    $("sgRefresh").onclick = load;
    load();
  };
  // Pause while the browser tab is hidden or another Studio tab is open; catch up as soon as it's back.
  const wake = () => { if (!last || !$("sgBody")) return; if (document.hidden || current !== "signals") { schedule(); if (last) draw(last); } else load(); };
  document.addEventListener("visibilitychange", wake);
  window.addEventListener("hashchange", () => setTimeout(wake, 0));
  document.addEventListener("keyup", (e) => { if (e.target.closest && e.target.closest("#tabs")) wake(); });
  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-k]");
    if (t && t.closest("#tabs")) setTimeout(wake, 0);
    const a = e.target.closest("a[data-sgview]");
    if (!a) return;
    e.preventDefault();
    show("bot");
    frames.bot.src = a.dataset.sgview;
  });
})();
