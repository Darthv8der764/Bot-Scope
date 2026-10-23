// Themes for every BotScope page: Auto (follows the computer), Light, Dark, plus a color-blind-safe palette
// (blue for up/target, orange for down/stop, instead of green and red). Remembered in this browser only.
(function () {
  // botscopeReadable(els): give each element black or white text, whichever reads better on its actual background
  // (colored tiles such as the weather calendar and heat maps, where one fixed text color can't work in every theme)
  window.botscopeReadable = function (els) {
    const rgba = (c) => {                              // "rgb(a)(0-255...)" or color-mix's "color(srgb 0-1 0-1 0-1 / a)"
      const n = (c.match(/[\d.]+/g) || []).map(Number);
      return c.startsWith("color(") ? [n[0] * 255, n[1] * 255, n[2] * 255, n.length > 3 ? n[3] : 1] : n;
    };
    const lum = ([r, g, b]) => [r, g, b].map((v) => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; })
      .reduce((a, v, i) => a + v * [.2126, .7152, .0722][i], 0);
    for (const el of els) {
      const see = [];                                  // backgrounds from the element up to the first solid one
      for (let e = el; e; e = e.parentElement) {
        const [r, g, b, a = 1] = rgba(getComputedStyle(e).backgroundColor);
        if (a > 0) see.push([r, g, b, a]);
        if (a >= 0.99) break;
      }
      let rgb = see.length && see[see.length - 1][3] >= 0.99 ? see.pop().slice(0, 3) : [255, 255, 255];
      for (const [r, g, b, a] of see.reverse()) rgb = [r * a + rgb[0] * (1 - a), g * a + rgb[1] * (1 - a), b * a + rgb[2] * (1 - a)];
      const L = lum(rgb);
      el.style.color = (L + .05) / .05 >= 1.05 / (L + .05) ? "#111" : "#fff";
    }
  };
  const KEY = "botscope-theme";
  const DEMO = /*DEMO*/null/*/DEMO*/;
  const get = () => { try { return JSON.parse(localStorage.getItem(KEY) || "null") || { mode: "auto", cb: false }; } catch { return { mode: "auto", cb: false }; } };
  const set = (v) => { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch { /* private window: this visit only */ } };
  const t = get(), root = document.documentElement;
  if (t.mode === "light" || t.mode === "dark") root.dataset.theme = t.mode;
  if (t.cb) root.dataset.cb = "1";
  const style = document.createElement("style");
  style.textContent = `
  /* text on accent / STOP buttons: white on the light-mode colors, near-black on the lighter dark-mode ones
     (white on #6d97ee or on the color-blind orange is under 3:1) */
  :root { --on-accent: #fff; --on-down: #fff; }
  @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --on-accent: #0d1220; }
    :root[data-cb]:not([data-theme="light"]) { --on-down: #111; } }
  :root[data-theme="dark"] { --on-accent: #0d1220; }
  :root[data-theme="dark"][data-cb] { --on-down: #111; }
  :root[data-cb] { --up: #0072b2; --down: #d55e00; --stop: #d55e00; --target: #0072b2; }
  @media (prefers-color-scheme: dark) { :root[data-cb]:not([data-theme="light"]) { --up: #56b4e9; --down: #e69f00; --stop: #e69f00; --target: #56b4e9; } }
  :root[data-cb][data-theme="dark"] { --up: #56b4e9; --down: #e69f00; --stop: #e69f00; --target: #56b4e9; }
  /* links in dark modes: a soft blue instead of the browser's harsh one (lavender with the color-blind palette, so a
     link never looks like an "up" color); page rules still win (:where has no weight) */
  @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) :where(a:link, a:visited) { color: #9fb7e0; }
    :root[data-cb]:not([data-theme="light"]) :where(a:link, a:visited) { color: #cdbfe9; } }
  :root[data-theme="dark"] :where(a:link, a:visited) { color: #9fb7e0; }
  :root[data-theme="dark"][data-cb] :where(a:link, a:visited) { color: #cdbfe9; }
  .theme-pick { font: inherit; font-size: 12px; padding: 3px 6px; border-radius: 6px; border: 1px solid currentColor; background: transparent; color: inherit; }
  .theme-pick option { color: #111; }
  .demo-badge { position: fixed; right: 10px; bottom: 10px; z-index: 9999; padding: 5px 10px; border-radius: 999px;
    background: #b45309; color: #fff; font: 700 12px/1.2 system-ui, sans-serif; letter-spacing: .06em;
    box-shadow: 0 1px 4px rgba(0,0,0,.3); cursor: help; }
  [data-closable] { position: relative; }
  .bs-x { position: absolute; top: 2px; right: 2px; width: 24px; height: 24px; padding: 0; border: 0; border-radius: 6px;
    background: transparent; color: inherit; opacity: .6; font: 18px/1 system-ui, sans-serif; cursor: pointer; }
  .bs-x:hover, .bs-x:focus-visible { opacity: 1; background: rgba(127,127,127,.18); }
  .bs-closed { font-size: 12px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .bs-closed button { font: inherit; font-size: 12px; padding: 2px 8px; border-radius: 999px; border: 1px solid currentColor;
    background: transparent; color: inherit; cursor: pointer; }`;
  document.head.appendChild(style);
  const i18n = document.createElement("script");   // the language switch (English / Spanish), same origin only
  i18n.src = "/i18n.js"; document.head.appendChild(i18n);
  // Every panel and popup can be closed. Panels ([data-closable] with an id and a data-title) get an x and stay closed
  // (this browser only) until reopened from the "Closed" strip. Popups ([data-popup], shown) close with Esc, and with a
  // click outside unless they say data-outside="no"; a popup can set el.bsClose to close itself its own way.
  const shown = (el) => el.isConnected && !el.hidden && getComputedStyle(el).display !== "none" && el.getClientRects().length > 0;
  const closePopup = (el) => { if (el.bsClose) el.bsClose(); else el.hidden = true; };
  window.bsOpenPopups = () => [...document.querySelectorAll("[data-popup]")].filter(shown);
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || document.querySelector(".tour-box")) return;     // the tour closes itself on Esc
    const top = window.bsOpenPopups().at(-1);
    if (top) { e.preventDefault(); closePopup(top); }
  });
  document.addEventListener("pointerdown", (e) => {
    for (const el of window.bsOpenPopups())
      if (el.dataset.outside !== "no" && !el.contains(e.target) && !(el.bsOpener && el.bsOpener.contains(e.target))) closePopup(el);
  });
  const CKEY = "botscope-closed:" + location.pathname;
  const closed = () => { try { return JSON.parse(localStorage.getItem(CKEY) || "[]"); } catch { return []; } };
  const saveClosed = (v) => { try { localStorage.setItem(CKEY, JSON.stringify(v)); } catch { /* private window */ } };
  window.bsPanels = function () {
    const panels = [...document.querySelectorAll("[data-closable][id]")];
    if (!panels.length) return;
    let strip = document.querySelector(".bs-closed");
    if (!strip) { strip = document.createElement("div"); strip.className = "bs-closed muted"; panels[0].parentNode.appendChild(strip); }
    const draw = () => {
      const c = closed();
      for (const p of panels) p.hidden = c.includes(p.id);
      const gone = panels.filter((p) => c.includes(p.id));
      strip.hidden = !gone.length;
      strip.innerHTML = gone.length ? "<span>Closed:</span>" + gone.map((p) => `<button type="button" data-open="${p.id}" title="Open it again">${p.dataset.title.replace(/[<>&"]/g, "")} ↺</button>`).join("") : "";
      strip.querySelectorAll("button").forEach((b) => b.onclick = () => { saveClosed(closed().filter((x) => x !== b.dataset.open)); draw(); });
    };
    for (const p of panels) {
      if (p.querySelector(":scope > .bs-x")) continue;
      const x = document.createElement("button");
      x.type = "button"; x.className = "bs-x"; x.textContent = "×"; x.setAttribute("aria-label", "Close " + p.dataset.title);
      x.title = "Close (reopen it from the Closed list)";
      x.onclick = () => { saveClosed([...new Set([...closed(), p.id])]); draw(); };
      p.prepend(x);
    }
    draw();
  };
  document.addEventListener("DOMContentLoaded", () => {
    window.bsPanels();
    const sel = document.createElement("select");
    sel.className = "theme-pick"; sel.setAttribute("aria-label", "Theme"); sel.title = "Theme (remembered in this browser)";
    sel.innerHTML = [["auto", "Auto"], ["light", "Light"], ["dark", "Dark"], ["auto-cb", "Auto, color-blind"],
      ["light-cb", "Light, color-blind"], ["dark-cb", "Dark, color-blind"]].map(([v, l]) => `<option value="${v}">${l}</option>`).join("");
    sel.value = t.mode + (t.cb ? "-cb" : "");
    sel.onchange = () => { const [mode, cb] = sel.value.split("-"); set({ mode, cb: cb === "cb" }); location.reload(); };   // charts read colors once
    if (window.top === window) (document.querySelector("header") || document.body).appendChild(sel);   // in Studio, its own picker
    // Demo mode (no keys): a badge on every page so made-up prices are never mistaken for real ones.
    const m = DEMO;     // filled in by the page server; a page opened as a file shows no badge
    if (m && m.demo && window.top === window && !document.querySelector(".demo-badge")) {   // Studio's tabs: one badge
      const b = document.createElement("div");
      b.className = "demo-badge"; b.setAttribute("role", "status"); b.textContent = m.badge;
      b.title = "Made-up prices: results mean nothing about real markets. " + m.how;
      document.body.appendChild(b);
    }
  });
})();
