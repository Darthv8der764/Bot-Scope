// First-run tour: a short guided walk that points at the real parts of the page, one step at a time.
// Shown once per page (remembered in this browser only, never sent anywhere); "Tour" in the header replays it.
// Usage: botscopeTour("chart", [{ el: "#stopbtn", title: "...", text: "..." }, ...]);
(function () {
  const css = `
  .tour-shade{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9998}
  .tour-ring{position:fixed;z-index:9999;border:3px solid #f5b400;border-radius:8px;box-shadow:0 0 0 4px rgba(245,180,0,.25);pointer-events:none;transition:all .2s}
  .tour-box{position:fixed;z-index:10000;max-width:320px;background:var(--panel,#fff);color:var(--ink,#111);border:1px solid var(--line,#ccc);border-radius:10px;padding:14px 16px;box-shadow:0 8px 30px rgba(0,0,0,.3);font:14px/1.45 system-ui,sans-serif}
  .tour-box h3{margin:0 0 6px;font-size:15px;color:inherit}.tour-box p{margin:0 0 10px;color:inherit}
  .tour-box .row{display:flex;gap:8px;align-items:center}.tour-box .row span{margin-right:auto;opacity:.7;font-size:12px}
  .tour-box button{font:inherit;padding:4px 10px;border-radius:6px;border:1px solid #888;background:transparent;color:var(--ink,#111);cursor:pointer}
  .tour-box button.next{background:#2563eb;border-color:#2563eb;color:#fff}`;
  const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } },
                  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private window: just show it again */ } } };

  window.botscopeTour = function (page, steps, opts = {}) {
    const key = "botscope-tour-done-" + page;
    let i = 0, shade, ring, box;
    function end() { [shade, ring, box].forEach((x) => x && x.remove()); store.set(key, "1"); document.removeEventListener("keydown", keys); }
    function keys(e) { if (e.key === "Escape") end(); if (e.key === "ArrowRight") go(1); if (e.key === "ArrowLeft") go(-1); }
    function go(d) { i += d; if (i >= steps.length) return end(); i = Math.max(0, i); show(); }
    function show() {
      const s = steps[i], el = s.el && document.querySelector(s.el);
      if (s.el && (!el || el.offsetParent === null) && steps.length > 1) { steps.splice(i, 1); return i < steps.length ? show() : end(); }
      if (el) el.scrollIntoView({ block: "nearest" });
      const r = el ? el.getBoundingClientRect() : { left: innerWidth / 2, top: innerHeight / 3, width: 0, height: 0 };
      ring.style.display = el ? "block" : "none";
      Object.assign(ring.style, { left: r.left - 6 + "px", top: r.top - 6 + "px", width: r.width + 12 + "px", height: r.height + 12 + "px" });
      box.innerHTML = `<h3></h3><p></p><div class="row"><span>${i + 1} of ${steps.length}</span>
        <button class="skip">Skip tour</button>${i ? '<button class="back">Back</button>' : ""}<button class="next">${i === steps.length - 1 ? "Done" : "Next"}</button></div>`;
      box.querySelector("h3").textContent = s.title; box.querySelector("p").textContent = s.text;
      const w = Math.min(320, innerWidth - 32);
      const below = r.top + r.height + 14, left = Math.min(Math.max(16, r.left), innerWidth - w - 16);
      Object.assign(box.style, { width: w + "px", left: left + "px",
        top: (below + 170 < innerHeight ? below : Math.max(16, r.top - 190)) + "px" });
      box.querySelector(".skip").onclick = end; box.querySelector(".next").onclick = () => go(1);
      const b = box.querySelector(".back"); if (b) b.onclick = () => go(-1);
      box.querySelector(".next").focus();
    }
    function start() {
      steps = steps.slice(); i = 0;
      const style = document.createElement("style"); style.textContent = css; document.head.appendChild(style);
      shade = document.createElement("div"); shade.className = "tour-shade"; shade.onclick = end;
      ring = document.createElement("div"); ring.className = "tour-ring";
      box = document.createElement("div"); box.className = "tour-box"; box.setAttribute("role", "dialog"); box.setAttribute("aria-label", "Tour");
      document.body.append(shade, ring, box); document.addEventListener("keydown", keys); show();
    }
    const btn = opts.button && document.querySelector(opts.button);
    if (btn) btn.onclick = start;
    if (!store.get(key) && !new URLSearchParams(location.search).has("notour")) setTimeout(start, opts.delay ?? 800);
    return { start, end };
  };
})();
