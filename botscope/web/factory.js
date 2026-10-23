// Studio's Factory tab: describe a goal; your own Claude Code researches 5 published strategies that fit it and writes
// them as bot files (BotScope refuses any file that does more than a bot should), then every candidate goes through
// the same honest tests and only survivors are kept. Research runs your Claude, so it needs the Claude panel switched
// on; the textbook templates work without it. Uses Studio's $, esc, enc, fmtR, H, cons, show and frames.
(function () {
  const css = document.createElement("style");
  css.textContent = `
  .fx .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .fx .primary { background: color-mix(in srgb, var(--accent) 72%, #000); color: #fff; border-color: transparent; font-weight: 600; }
  .fx ol.steps:not([hidden]) { display: flex; flex-wrap: wrap; gap: 4px 14px; list-style: none; padding: 0; margin: 8px 0 0; font-size: 12px; color: var(--muted); }
  .fx ol.steps li[aria-current="step"] { color: var(--ink); font-weight: 600; }
  .fx ol.steps li.done::after { content: " ✓"; }
  .fx .src { font-weight: 400; overflow-wrap: anywhere; }
  .fx .offer { border-left: 3px solid var(--accent); padding: 6px 10px; margin: 8px 0; }
  .fx .offer p { margin: 0 0 6px; }`;
  document.head.appendChild(css);

  window.factoryShell = () => `<div class="fx"><h2 style="font-size:16px;margin:0">Strategy factory</h2>
  <p class="muted">Describe the bot you want. Your own Claude Code looks up 5 well-known, published strategies that fit
  it and writes each as a bot, with its rules in plain English and where the idea comes from. BotScope reads every file
  first and refuses anything a bot shouldn't do, then tests each one on untested years with costs, doubled costs, luck,
  a held-out year and the goal's limits. Only survivors are kept; every drop says why.</p>
  <form class="run" id="fform"><input id="goal" placeholder="e.g. a swing bot for SPY and QQQ" aria-label="Goal" maxlength="200">
  <button type="submit" id="frun" class="primary">Research and test 5</button>
  <button type="button" id="ftpl" title="No Claude: BotScope's built-in textbook templates, picked by keywords">Textbook templates only</button></form>
  <p class="muted" id="fmode"></p>
  <div id="foffer"></div>
  <p class="muted" id="fstatus" role="status" aria-live="polite"></p><ol class="steps" id="fsteps" hidden></ol>
  <div id="phantoms"></div><div id="runs"></div></div>`;

  function mode() {
    const m = $("fmode");
    if (m) m.textContent = cons.on
      ? "Research uses your own Claude Code (your plan, your login) and can take several minutes. Paper only."
      : "The Claude panel is off, so “Research and test 5” will ask to switch it on. “Textbook templates only” works without it.";
  }

  // A cited source as text, with its web address (http/https only) as a link.
  function source(s) {
    if (!s) return "";
    return String(s).split(/(https?:\/\/[^\s<>"'()]+)/).map((part, i) => i % 2
      ? `<a href="${esc(part)}" target="_blank" rel="noopener noreferrer">${esc(part.replace(/^https?:\/\//, "").slice(0, 60))}</a>`
      : esc(part)).join("");
  }
  const idea = (k) => k.idea_source ? `<div class="muted src">${k.idea ? esc(k.idea) + " · " : ""}Source: ${source(k.idea_source)}</div>` : "";

  window.runCard = function (r) {
    const kept = r.kept || [], dropped = r.dropped || [], rs = r.research;
    return `<div class="card"><h2>${esc(r.goal)}</h2>
  <div class="muted">${esc(r.when?.replace("T", " "))}${r.demo ? " · <b>DEMO DATA</b> (made-up prices)" : ""} · read as: ${esc(r.understood)} · ${r.tried} tried, all years UNTESTED</div>
  ${rs ? `<p class="muted">${rs.used ? "🔎 " : "⚠ "}${esc(rs.note)}</p>` : `<p class="muted">Candidates from BotScope's built-in textbook templates.</p>`}
  ${kept.length ? `<div class="tablewrap"><table class="kept"><tr><th>Survivor</th><th>Confidence</th><th class="num">Untested trades</th><th class="num">Per trade after costs</th><th class="num">Costs doubled</th><th class="num">Without best 3</th><th class="num">Settings ±20%</th><th>Luck</th><th>vs holding SPY</th><th>Held-out year</th></tr>
  ${kept.map((k, i) => `<tr><td class="name">${i + 1}. ${esc(k.name)}<div class="muted">${esc(k.id)} · <a href="#bot" data-cand="factory/${esc(r.run)}/${esc(k.id)}">open its chart</a> · <button type="button" class="linkbtn" data-phantom="${esc(r.run)}|${esc(k.id)}" title="Run it forward on live days, paper only, no orders">Phantom test</button></div>${rs && rs.used ? idea(k) : ""}${(k.rules || []).length ? `<details><summary class="muted">Its rules</summary><ol class="muted" style="margin:4px 0;padding-left:18px;font-weight:400">${k.rules.map((x) => `<li>${esc(x)}</li>`).join("")}</ol></details>` : ""}</td><td data-l="Confidence"><span class="lvl" title="${esc((k.confidence_why || []).join("; "))}">${esc(k.confidence)}</span></td>
  <td class="num" data-l="Untested trades">${k.untested_trades}</td><td class="num" data-l="Per trade">${fmtR(k.avg_r)}</td><td class="num" data-l="Costs doubled">${fmtR(k.if_costs_doubled_r)}</td><td class="num" data-l="Without best 3">${fmtR(k.without_best_3_r)}</td><td class="num" data-l="Settings ±20%" title="every setting 20% smaller / bigger: per trade after costs">${k.settings_nudged ? Object.values(k.settings_nudged).map((n) => fmtR(n.avg_r)).join(" / ") : "–"}</td><td data-l="Luck">${esc(k.luck)}</td>
  <td data-l="vs SPY">${k.years_beat_spy ?? "–"} of ${k.untested_years} yrs</td>
  <td data-l="Held-out year" title="${esc(k.held_out?.note || "")}">${k.held_out ? (k.held_out.trades ? `${k.held_out.trades} trades, ${fmtR(k.held_out.avg_r)} each` : "no trades") : "–"}</td></tr>`).join("")}</table></div>
  ${r.hindsight ? `<p class="muted">⚠ ${esc(r.hindsight)}</p>` : ""}
  ${(r.same_bets || []).map((o) => `<p class="muted">Same bet? ${esc(o)}</p>`).join("")}
  <p class="muted">${esc(r.tries_note || `${r.tried} candidates were tried on the same years, so the top one looks a bit better than it is.`)} Ask Claude to adopt_candidate one, then paper trade it.</p>`
  : `<p><b>No candidate survived.</b> That's a real answer: none of these ideas held up honestly for this goal.</p>`}
  <button type="button" class="linkbtn" data-ask="${esc(`Walk me through factory run ${r.run} ("${r.goal}"): which survivor is most trustworthy and why were the others dropped?`)}">Ask Claude about this run</button>
  ${dropped.length ? `<div class="tablewrap"><table><tr><th>Dropped</th><th>Why</th></tr>${dropped.map((d) => `<tr><td>${esc(d.name)}${rs && rs.used ? idea(d) : ""}</td><td>${esc(d.reason)}${d.learn ? ` <span class="muted">(why this matters: ${esc(d.learn.replace("docs/", "").replace(".md", "").replaceAll("-", " "))})</span>` : ""}</td></tr>`).join("")}</table></div>` : ""}
  </div>`;
  };

  async function loadPhantoms() {               // live paper forward tests: no orders, nothing adopted
    try {
      const r = await (await fetch("/api/phantom")).json(), ps = r.phantoms || [];
      $("phantoms").innerHTML = ps.length ? `<div class="card"><h2>Phantom tests (live paper, no orders)</h2><div class="tablewrap"><table>
      <tr><th>Candidate</th><th>Since</th><th class="num">Signals</th><th class="num">Per signal</th><th class="num">Backtest (untested)</th><th>So far</th></tr>
      ${ps.map((p) => `<tr><td>${esc(p.name)}${p.active ? "" : " <span class='muted'>(stopped)</span>"}</td><td data-l="Since">${esc(p.since)}</td><td class="num" data-l="Signals">${p.signals}</td><td class="num" data-l="Per signal">${fmtR(p.avg_r)}</td><td class="num" data-l="Backtest">${fmtR(p.backtest_avg_r)}</td><td data-l="So far">${esc(p.verdict)}</td></tr>`).join("")}</table></div>
      <p class="muted">${esc(r.note)}</p></div>` : "";
    } catch { $("phantoms").innerHTML = ""; }
  }
  document.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-phantom]");
    if (!b) return;
    const [run, cand] = b.dataset.phantom.split("|");
    b.disabled = true; b.textContent = "Starting…";
    try {
      const r = await (await fetch("/api/phantom", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run, candidates: [cand] }) })).json();
      b.textContent = r.error || (r.problems || [])[0] || "Phantom test started";
      await loadPhantoms();
    } catch (err) { b.textContent = err.message; }
  });

  window.loadRuns = async function () {
    mode();
    loadPhantoms();
    try {
      const runs = await (await fetch("/api/factory")).json();
      $("runs").innerHTML = runs.length ? runs.map(runCard).join("") : `<p class="muted">No factory runs yet. Try "a swing bot for SPY and QQQ".</p>`;
    } catch (e) { $("runs").innerHTML = `<p class="err">Couldn't load factory runs: ${esc(e.message)}</p>`; }
  };

  // The live steps: research → write 5 → safety check → test each (templates: test each only).
  const STEPS = [["research", "Research"], ["writing", "Write 5 candidates"], ["retry", "Safety check"], ["testing", "Honest tests"]];
  function steps(phase, research) {
    const el = $("fsteps");
    if (!research) { el.hidden = true; return; }
    const at = Math.max(0, STEPS.findIndex(([k]) => k === phase));
    el.innerHTML = STEPS.map(([, label], i) => `<li${i === at ? ' aria-current="step"' : ""}${i < at ? ' class="done"' : ""}>${i + 1}. ${label}</li>`).join("");
    el.hidden = false;
  }

  async function go(research) {
    const goal = $("goal").value.trim();
    $("foffer").innerHTML = "";
    if (!goal) { $("fstatus").textContent = "Describe the bot first, in one sentence."; $("goal").focus(); return; }
    mode();
    if (research && !cons.on) { offer(); return; }
    $("frun").disabled = $("ftpl").disabled = true;
    $("fstatus").textContent = research ? "Asking your Claude Code to research strategies that fit the goal…"
                                        : "Testing candidates one at a time… (the first run with real data can take a few minutes)";
    steps("research", research);
    const tick = setInterval(async () => {        // what's happening right now
      try {
        const p = await (await fetch("/api/factory/progress")).json();
        if (p.phase && p.phase !== "testing" && p.say) { $("fstatus").textContent = p.say; steps(p.phase, research); }
        else if (p.total && p.now) { $("fstatus").textContent = `Testing ${p.now} (${p.done + 1} of ${p.total}); ${p.kept} survived so far…`; steps("testing", research); }
      } catch { /* the run's own answer still arrives */ }
    }, 1500);
    try {
      const resp = await fetch(research ? "/api/factory/research" : "/api/factory",
        { method: "POST", headers: research ? H() : { "Content-Type": "application/json" }, body: JSON.stringify({ goal }) });
      const r = await resp.json();
      clearInterval(tick);
      if (r.offer === "templates") { cons.on = false; offer(r.error); $("fstatus").textContent = ""; }
      else if (r.error) $("fstatus").innerHTML = `<span class="err">${esc(/wrong token/.test(r.error) ? "This page is from an earlier launch of BotScope's page server: reload the page." : r.error)}</span>`;
      else $("fstatus").textContent = `Done: ${r.kept.length} of ${r.tried} survived.${r.research && !r.research.used ? " Research didn't run, so these are the textbook templates (why: see the run below)." : ""}`;
      await loadRuns();
    } catch (err) { $("fstatus").innerHTML = `<span class="err">${esc(err.message)}</span>`; }
    clearInterval(tick);
    $("fsteps").hidden = true;
    $("frun").disabled = $("ftpl").disabled = false;
    mode();
  }

  // Research runs the user's own Claude: only with the Claude panel on. Otherwise say so and offer the templates.
  function offer(why) {
    $("foffer").innerHTML = `<div class="offer" role="alert"><p>${esc(why || "Research runs your own Claude Code, so the Claude panel must be switched on first.")}</p>
    <div class="row"><button type="button" id="fsettings">Open settings to switch it on</button><button type="button" id="ftpl2">Run with the textbook templates</button></div></div>`;
    $("fsettings").onclick = () => { $("setbtn").click(); };
    $("ftpl2").onclick = () => go(false);
  }

  document.addEventListener("submit", (e) => {
    if (e.target.id !== "fform") return;
    e.preventDefault();
    go(true);
  });
  document.addEventListener("click", (e) => { if (e.target.id === "ftpl") go(false); });
  document.addEventListener("focusin", (e) => { if (e.target.id === "goal") mode(); });   // the panel may have been switched since
})();
