// Language switch for every BotScope page: English (default) or Spanish. Exact phrases on the page are swapped for
// their translation, including text that appears later (panels, results). Numbers, tickers and bot names stay as
// they are. The honesty warnings are translated word for word: no softer, no stronger. Remembered in this browser.
(function () {
  const KEY = "botscope-lang";
  const ES = {
    "BotScope Studio": "BotScope Studio",
    "Paper only · not financial advice": "Solo en papel · no es asesoría financiera",
    "Bot view": "Vista del bot", "Desk": "Mesa", "Pre-flight": "Prevuelo", "Rule playground": "Probador de reglas",
    "Family tree": "Árbol familiar", "Factory": "Fábrica", "Compare": "Comparar", "Optimizer": "Optimizador",
    "Flight sim": "Simulador", "Tutorial": "Tutorial",
    "Bot": "Bot", "Got it": "Entendido",
    "Strategy factory": "Fábrica de estrategias",
    "Run the factory": "Ejecutar la fábrica",
    "Survivor": "Sobreviviente", "Per trade": "Por operación", "vs SPY": "vs. SPY", "e.g. a calm daily ETF bot": "p. ej. un bot diario y tranquilo de ETF", "Confidence": "Confianza", "Untested trades": "Operaciones no probadas",
    "Per trade after costs": "Por operación tras costos", "Costs doubled": "Costos al doble",
    "Without best 3": "Sin las 3 mejores", "Settings ±20%": "Ajustes ±20%", "Luck": "Suerte",
    "vs holding SPY": "vs. mantener SPY", "Held-out year": "Año reservado", "Dropped": "Descartado", "Why": "Por qué",
    "Its rules": "Sus reglas", "open its chart": "abrir su gráfico",
    "very low": "muy baja", "low": "baja", "medium": "media", "high": "alta", "very high": "muy alta",
    "beats luck": "supera a la suerte", "unclear": "no está claro", "looks like luck": "parece suerte",
    "STOP": "ALTO", "Teach me": "Enséñame", "Tour": "Recorrido", "Label": "Etiqueta", "Show": "Mostrar",
    "Play": "Reproducir", "Quiz me": "Ponme a prueba", "Show whole day": "Ver todo el día",
    "Next candle": "Siguiente vela", "Buy": "Comprar", "Short": "Vender en corto", "Close": "Cerrar",
    "End the day": "Terminar el día", "Load day": "Cargar día", "Flight simulator": "Simulador de vuelo",
    "Market desk": "Mesa de mercado", "Reset layout": "Restablecer diseño", "Look up": "Buscar",
    "information only": "solo información", "Daily pre-flight": "Prevuelo diario",
    "Bot Facts": "Datos del bot", "not measured yet": "aún no medido", "Status": "Estado",
    "untested": "no probado", "failed": "falló", "UNTESTED": "NO PROBADO", "TUNED": "AJUSTADO",
    "DEMO DATA": "DATOS DE DEMOSTRACIÓN",
    "Not financial advice.": "No es asesoría financiera.",
    "Not financial advice": "No es asesoría financiera",
    "Paper only.": "Solo en papel.",
    "No candidate survived.": "Ningún candidato sobrevivió.",
    "Day over.": "Fin del día.",
    "★ best cell · • today's settings · grey = under 30 trades": "★ mejor celda · • ajustes actuales · gris = menos de 30 operaciones",
    "Two nutrition labels side by side: same rows, same order. Rows not measured yet say so.":
      "Dos etiquetas una al lado de la otra: mismas filas, mismo orden. Las filas aún no medidas lo dicen.",
    "Describe the bot you want. Up to 5 candidates from textbook settings, each tested on untested years with costs, doubled costs, luck and the goal's limits. Only survivors are kept; every drop says why.":
      "Describe el bot que quieres. Hasta 5 candidatos con ajustes de manual, cada uno probado en años no probados con costos, costos al doble, suerte y los límites del objetivo. Solo se quedan los sobrevivientes; cada descarte dice por qué.",
    "Trade a past day yourself. Only finished candles are shown; the rest of the day, and what the bot did, stay hidden until the end. Paper only, same costs as every BotScope test.":
      "Opera tú mismo un día pasado. Solo se muestran velas terminadas; el resto del día, y lo que hizo el bot, quedan ocultos hasta el final. Solo en papel, con los mismos costos que cada prueba de BotScope.",
    "TUNED years are where the settings were picked, so they look better than they should. UNTESTED years are the real test. Costs are already taken out.":
      "Los años AJUSTADOS son donde se eligieron los ajustes, así que se ven mejor de lo que deberían. Los años NO PROBADOS son la prueba real. Los costos ya están descontados.",
    "Parent view": "Vista para padres",
    "Read only: nothing on this page can change a setting or place an order.": "Solo lectura: nada en esta página puede cambiar un ajuste ni enviar una orden.",
    "Real-money lock": "Bloqueo de dinero real",
    "Locked": "Bloqueado",
    "STOP everything": "ALTO a todo",
    "Not pressed": "No presionado",
    "Bots on real money": "Bots con dinero real",
    "None": "Ninguno",
    "Biggest real order": "Orden real más grande",
    "Orders a day, at most": "Órdenes al día, como máximo",
    "Weekly loss budget": "Límite de pérdida semanal",
    "Not set": "Sin fijar",
    "The bots": "Los bots",
    "paper (pretend money)": "papel (dinero de práctica)",
    "on today": "encendido hoy",
    "off today": "apagado hoy",
    "Recent paper trades": "Operaciones en papel recientes",
    "Day": "Día",
    "Symbol": "Símbolo",
    "Side": "Lado",
    "Result": "Resultado",
    "Why it ended": "Por qué terminó",
    "Recent guard alerts": "Alertas recientes del guardia",
    "When (UTC)": "Cuándo (UTC)",
    "From": "Desde",
    "Decision": "Decisión",
    "stop hit": "stop alcanzado",
    "end of day": "fin del día",
    "target hit": "objetivo alcanzado",
    "Weather calendar": "Calendario del clima",
    "Replay with": "Repetir con",
    "Months": "Meses",
    "Mon": "Lun",
    "Tue": "Mar",
    "Wed": "Mié",
    "Thu": "Jue",
    "Fri": "Vie",
    "Each day's color is the weather known at that day's open. Click a day to replay it in the bot view. Not financial advice.": "El color de cada día es el clima que se conocía a la apertura de ese día. Haz clic en un día para repetirlo en la vista del bot. No es asesoría financiera.",
    "Where the bot stands: untested, on paper, passed or failed its tests.": "Dónde está el bot: sin probar, en papel, aprobó o falló sus pruebas.",
    "Timeframe / sides": "Marco de tiempo / lados",
    "The candle size it trades on, and whether it buys (long), sells short, or both.": "El tamaño de vela con que opera, y si compra (largo), vende en corto, o ambos.",
    "Untested years": "Años no probados",
    "Years the bot's settings were NOT picked on, so its results there are a fair test.": "Años en los que NO se eligieron los ajustes del bot, así que sus resultados ahí son una prueba justa.",
    "How many trades those untested years had; more trades = a result you can lean on more.": "Cuántas operaciones tuvieron esos años no probados; más operaciones = un resultado más confiable.",
    "Per trade, after costs": "Por operación, tras costos",
    "Total, after costs": "Total, tras costos",
    "All untested trades added up, in R.": "Todas las operaciones no probadas sumadas, en R.",
    "Range (bad / middle / good)": "Rango (malo / medio / bueno)",
    "Worst drop": "Peor caída",
    "The biggest fall from a high point to a low point, in R; you'd have to sit through this.": "La mayor caída de un punto alto a uno bajo, en R; tendrías que aguantarla.",
    "Worst losing streak": "Peor racha de pérdidas",
    "The most losing trades in a row.": "La mayor cantidad de operaciones perdedoras seguidas.",
    "Costs took": "Los costos se llevaron",
    "How much fees and slippage took out of the result, in R, and in dollars per trade at the tested size.": "Cuánto se llevaron las comisiones y el deslizamiento del resultado, en R, y en dólares por operación al tamaño probado.",
    "If costs doubled": "Si los costos se duplicaran",
    "The total if fills were twice as bad; a bot that only works with perfect fills shows it here.": "El total si las ejecuciones fueran el doble de malas; un bot que solo funciona con ejecuciones perfectas se nota aquí.",
    "Beat just holding SPY?": "¿Le ganó a solo mantener SPY?",
    "Losing untested years": "Años no probados con pérdida",
    "How many of the fair-test years ended with a loss after costs.": "Cuántos de los años de prueba justa terminaron en pérdida tras costos.",
    "Crashes": "Caídas del mercado",
    "How it did through big market crashes inside its data; older ones say not tested.": "Cómo le fue en las grandes caídas del mercado dentro de sus datos; las más antiguas dicen no probado.",
    "Luck meter": "Medidor de suerte",
    "Robustness checks": "Pruebas de solidez",
    "Near misses": "Casi operaciones",
    "Trades the bot almost took, played out on paper.": "Operaciones que el bot casi tomó, simuladas en papel.",
    "Live paper trades": "Operaciones en papel en vivo",
    "Trades since the bot started running on paper, after the backtest.": "Operaciones desde que el bot empezó a correr en papel, después de la prueba histórica.",
    "Try turning its rules off in the playground": "Prueba apagar sus reglas en el probador",
    "Project map": "Mapa del proyecto",
    "Project": "Proyecto",
    "Bot family": "Familia del bot",
    "▶ Timelapse": "▶ Cámara rápida",
    "Labels": "Etiquetas",
    "Reset look": "Restablecer vista",
    "Core": "Núcleo",
    "See inside": "Ver por dentro",
    "Honesty": "Honestidad",
    "Safety": "Seguridad",
    "Plumbing": "Tuberías",
    "Click a dot to see what that part does. Lines = \"uses\". Dot size = lines of code.": "Haz clic en un punto para ver qué hace esa parte. Líneas = \"usa\". Tamaño del punto = líneas de código.",
    "Click a dot: what changed in that version and, for the newest one, how it did (untested trades, confidence).": "Haz clic en un punto: qué cambió en esa versión y, para la más nueva, cómo le fue (operaciones no probadas, confianza).",
    "no ★: no cell makes money · • today's settings · grey = under 30 trades": "sin ★: ninguna celda gana dinero · • ajustes actuales · gris = menos de 30 operaciones",
    "Without its 3 best trades": "Sin sus 3 mejores operaciones",
    "The total with its 3 luckiest trades taken out; if this flips to a loss, a few trades carried it.": "El total sin sus 3 operaciones con más suerte; si esto pasa a pérdida, unas pocas operaciones lo sostuvieron.",
    "The newest honest optimizer run on two of its settings: whether a different setting is a lead to test or just luck.": "La ejecución más reciente del optimizador honesto en dos de sus ajustes: si otro ajuste es una pista para probar o solo suerte.",
  };
  const PICK = { en: "English", es: "Español" };
  let lang = "en";
  try { lang = localStorage.getItem(KEY) || "en"; } catch { /* private window: English */ }
  const keys = Object.keys(ES).sort((a, b) => b.length - a.length);
  function swap(node) {
    if (lang !== "es") return;
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    const todo = [];
    while (walker.nextNode()) todo.push(walker.currentNode);
    for (const t of todo) {
      const raw = t.nodeValue, s = raw.replace(/\s+/g, " ").trim();
      if (!s || t.parentElement?.closest("script,style,code")) continue;
      if (ES[s] !== undefined) { t.nodeValue = (raw.match(/^\s*/)[0]) + ES[s] + (raw.match(/\s*$/)[0]); continue; }
      let out = raw;
      for (const k of keys) if (k.length > 12 && out.includes(k)) out = out.split(k).join(ES[k]);   // long phrases inside text
      if (out !== raw) t.nodeValue = out;
    }
    for (const el of node.querySelectorAll ? node.querySelectorAll("[placeholder],[title],[aria-label],[data-l]") : []) {
      for (const a of ["placeholder", "title", "aria-label", "data-l"]) { const v = el.getAttribute(a); if (v && ES[v]) el.setAttribute(a, ES[v]); }
    }
  }
  window.botscopeLang = () => lang;
  window.botscopeT = (s) => (lang === "es" && ES[s]) || s;
  function start() {
    document.documentElement.lang = lang;
    swap(document.body);
    new MutationObserver((ms) => { for (const m of ms) for (const n of m.addedNodes) if (n.nodeType === 1) swap(n); else if (n.nodeType === 3 && n.parentElement) swap(n.parentElement); })
      .observe(document.body, { childList: true, subtree: true });
    if (window.top !== window) return;                    // inside Studio: Studio's own picker
    const sel = document.createElement("select");
    sel.className = "theme-pick"; sel.setAttribute("aria-label", "Language / Idioma");
    sel.innerHTML = Object.entries(PICK).map(([v, l]) => `<option value="${v}">${l}</option>`).join("");
    sel.value = lang;
    sel.onchange = () => { try { localStorage.setItem(KEY, sel.value); } catch { /* this visit only */ } location.reload(); };
    (document.querySelector("header") || document.body).appendChild(sel);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);   // loaded by theme.js,
  else start();                                                                                  // maybe after that
})();
