// Studio's Honest optimizer tab: run one from the page. Pick a bot and the two settings to vary, press Run, watch the
// cells fill in, then the heat map and verdict appear (drawn by Studio's loadOptimizer, newest first). Every square
// is scored on UNTESTED years with the last year held out; the bot file is never changed. Uses Studio's $, esc, enc, bot.
(function () {
  const css = document.createElement("style");
  css.textContent = `
  .optrun .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: end; margin: 6px 0; }
  .optrun label { display: flex; flex-direction: column; gap: 2px; font-size: 12px; flex: 1 1 160px; min-width: 0; }
  .optrun select { width: 100%; }
  .optrun .primary { background: color-mix(in srgb, var(--accent) 72%, #000); color: #fff; border-color: transparent; font-weight: 600; }
  .optrun .primary:disabled { opacity: .55; cursor: default; }
  .optrun progress { width: 100%; height: 8px; accent-color: var(--accent); }
  .optrun .tag { display: inline-block; border: 1px solid var(--line); border-radius: 4px; padding: 0 5px; font-size: 11px; }`;
  document.head.appendChild(css);

  const box = document.createElement("div");
  box.className = "card optrun";
  box.innerHTML = `<h2>Run the honest optimizer</h2>
    <p class="muted">Every square is a backtest on the bot's <span class="tag">UNTESTED</span> years only (not the
    <span class="tag">TUNED</span> years its settings were picked on), after costs, with the last year held out for the
    final check. Your bot file is never changed; a better square is a lead to test on paper, not a fix.</p>
    <form id="optForm"><div class="row">
      <label>Bot<select id="optBot"></select></label>
      <label>Rows: setting to vary<select id="optA"></select></label>
      <label>Columns: setting to vary<select id="optB"></select></label>
      <button type="submit" class="primary" id="optGo">Run</button></div></form>
    <p class="muted" id="optMsg" role="status" aria-live="polite"></p>
    <progress id="optBar" max="1" value="0" hidden aria-label="Cells done"></progress>`;

  let picked = false, running = false;          // picked: the tab's bot no longer follows Studio's bot
  const q = (id) => box.querySelector("#" + id);

  async function loadSettings() {
    const msg = q("optMsg"), go = q("optGo");
    try {
      const r = await (await fetch(`/api/optimizer/settings?bot=${enc(q("optBot").value)}`)).json();
      const opts = (r.settings || []).map((k) => `<option value="${esc(k)}">${esc(k)} (today ${esc(r.today[k])})</option>`).join("");
      q("optA").innerHTML = opts; q("optB").innerHTML = opts;
      if (r.default && r.default.length === 2) { q("optA").value = r.default[0]; q("optB").value = r.default[1]; }
      go.disabled = running || !r.default || r.default.length !== 2;
      if (!running) msg.innerHTML = r.error ? `<span class="err">${esc(r.error)}</span>` :
        `${r.settings.length} number settings; ${esc(r.default[0])} × ${esc(r.default[1])} picked to start.`;
    } catch (e) { msg.innerHTML = `<span class="err">Couldn't read the bot's settings: ${esc(e.message)}</span>`; }
  }

  function syncBots() {                             // the same list as Studio's bot picker; follows it until you pick
    const studio = $("bot"), mine = q("optBot");
    if (mine.options.length !== studio.options.length) mine.innerHTML = studio.innerHTML;
    if (!picked && mine.value !== bot()) { mine.value = bot(); return true; }
    return false;
  }

  q("optBot").addEventListener("change", () => { picked = true; loadSettings(); });

  q("optForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const a = q("optA").value, b = q("optB").value, msg = q("optMsg"), bar = q("optBar"), go = q("optGo");
    if (a === b) { msg.innerHTML = `<span class="err">Pick two different settings.</span>`; return; }
    running = true; go.disabled = true; bar.hidden = false; bar.value = 0;
    msg.textContent = "Starting… (the first run with real data can take a few minutes)";
    const tick = setInterval(async () => {
      try {
        const p = await (await fetch("/api/optimizer/progress")).json();
        if (!p.total) return;
        bar.max = p.total; bar.value = p.done;
        msg.textContent = p.done < p.total ? `Testing ${p.now}: ${p.done} of ${p.total} squares done…`
                                           : `All ${p.total} squares done; now the held-out year…`;
      } catch { /* the run's own answer still arrives */ }
    }, 1000);
    let r;
    try {
      r = await (await fetch("/api/optimizer/run", { method: "POST", headers: { "Content-Type": "application/json" },
                                                     body: JSON.stringify({ bot: q("optBot").value, a, b }) })).json();
    } catch (err) { r = { error: err.message }; }
    clearInterval(tick);
    running = false; go.disabled = false; bar.hidden = true;
    if (r.error) { msg.innerHTML = `<span class="err">${esc(r.error)}</span>`; return; }
    msg.textContent = `Done: ${r.cells_tried} squares tried for ${r.bot}. Heat map below.`;
    await loadOptimizer();                           // redraws the saved maps, newest (this one) first
    const card = box.parentElement && box.parentElement.nextElementSibling;
    if (card) card.scrollIntoView({ block: "nearest", behavior: "smooth" });
  });

  // Studio's loadOptimizer leaves an empty #optrun slot; the same form moves in, so a redraw keeps its state.
  window.optRun = {
    mount(slot) {
      const first = !q("optBot").options.length;    // Studio's $ and bot picker exist by now (this file loads first)
      if (first) $("bot").addEventListener("change", () => { if (syncBots()) loadSettings(); });
      slot.appendChild(box);
      if (syncBots() || first) loadSettings();
    },
  };
})();
