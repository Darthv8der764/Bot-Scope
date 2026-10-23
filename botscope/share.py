"""Share as a page: one bot's honest report as a single standalone HTML file on this computer.

The file holds only the bot's rules, its saved honest report and its nutrition label: no keys, no account numbers,
no paper-account balances, no file paths. It is never uploaded: publishing it anywhere is a separate step the user
starts and approves themselves.
"""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from . import demo, label, loader, report
from .env import ROOT

STYLE = """
:root { --bg: #fafaf8; --ink: #111; --muted: #66665f; --line: #e3e2dd; --up: #1a7f54; --down: #c03a3a; --card: #fff; }
@media (prefers-color-scheme: dark) { :root { --bg: #121212; --ink: #f1f0ea; --muted: #9a9a94; --line: #2c2c2a;
  --up: #2fbf86; --down: #ef6363; --card: #1b1b1a; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.5 -apple-system, system-ui, sans-serif; }
main { max-width: 760px; margin: 0 auto; padding: 20px 16px 40px; }
h1 { font-size: 24px; margin: 0 0 4px; } h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .05em;
  color: var(--muted); margin: 24px 0 6px; }
.muted { color: var(--muted); font-size: 13px; }
.badge { display: inline-block; padding: 2px 9px; border-radius: 999px; background: #b45309; color: #fff;
  font-weight: 700; font-size: 12px; letter-spacing: .05em; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
.wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 6px 8px; border-top: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: 12px; }
td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.up { color: var(--up); } .down { color: var(--down); }
ol { padding-left: 20px; } footer { margin-top: 28px; font-size: 12px; color: var(--muted); }
"""


ES = {"Headline.": "Resumen.", "Its rules": "Sus reglas", "Bot facts": "Datos del bot", "Every year": "Cada año",
      "Year": "Año", "Period": "Periodo", "Trades": "Operaciones", "Per trade": "Por operación", "Total": "Total",
      "Beat holding SPY?": "¿Superó a mantener SPY?", "yes": "sí", "no": "no",
      "TUNED years are where the settings were picked, so they look better than they should. UNTESTED years are the "
      "real test. Costs are already taken out.": "Los años AJUSTADOS son donde se eligieron los ajustes, así que se "
      "ven mejor de lo que deberían. Los años NO PROBADOS son la prueba real. Los costos ya están descontados.",
      "made-up prices: these results mean nothing about real markets": "precios inventados: estos resultados no dicen "
      "nada sobre los mercados reales",
      "The bot changed after this report, so these numbers are for an older version.": "El bot cambió después de "
      "este informe, así que estas cifras son de una versión anterior.",
      "R = multiples of the risk on each trade (entry to stop). Paper trading only. Past results, even honest ones, "
      "don't predict the future.": "R = múltiplos del riesgo de cada operación (de la entrada al stop). Solo en papel. "
      "Los resultados pasados, aunque sean honestos, no predicen el futuro.",
      "Not financial advice.": "No es asesoría financiera.", "honest report": "informe honesto"}


def t(s: str) -> str:
    """Spanish for the page's fixed text when BOTSCOPE_LANG=es; numbers and names stay as they are."""
    from .env import key
    return ES.get(s, s) if key("BOTSCOPE_LANG").lower().startswith("es") else s


def shares_dir() -> Path:
    from . import userdata
    rel = "demo/shares" if demo.active() else "shares"
    return userdata.place(ROOT / "data" / rel, rel)


def _e(x) -> str:
    return html.escape(str(x if x is not None else "–"))


def _r(x) -> str:
    if x is None:
        return "–"
    cls = "up" if x > 0 else "down" if x < 0 else ""
    return f'<span class="{cls}">{x:+.2f}R</span>'


def page(bot: str) -> str:
    cls = loader.get(bot)
    rep = report.saved(cls)
    if not rep:
        raise ValueError(f"{cls.name} has no saved honest report yet: run honest_report first, then export again")
    lbl = label.build(bot)
    is_demo = demo.active()
    rows = "".join(f"<tr><td>{_e(r['label'])}</td><td>{_e(r['value'])}</td></tr>" for r in lbl["rows"])
    years = "".join(
        f"<tr><td>{_e(y['year'])}</td><td>{'TUNED' if y['period'] == 'tuned' else 'untested'}</td>"
        f"<td class='num'>{_e(y['trades'])}</td><td class='num'>{_r(y.get('avg_r'))}</td>"
        f"<td class='num'>{_r(y.get('total_r'))}</td><td>{t('yes') if y.get('beat') else t('no') if y.get('beat') is not None else '–'}</td></tr>"
        for y in rep.get("by_year", []))
    rules = "".join(f"<li>{_e(r)}</li>" for r in cls.rules)
    changed = report.changed_since(cls, rep)
    return f"""<!doctype html>
<html lang="{'es' if t('yes') == 'sí' else 'en'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(cls.name)} {t("honest report")}</title><style>{STYLE}</style></head>
<body><main>
<p>{'<span class="badge">DEMO DATA</span> ' + t("made-up prices: these results mean nothing about real markets") if is_demo else ''}</p>
<h1>{_e(cls.name)} <span class="muted">v{_e(cls.version)}</span></h1>
<p class="muted">{_e(cls.description)} Status: {_e(cls.status)}. {_e(cls.timeframe)} candles, {_e(cls.sides)} side(s), {_e(", ".join(rep.get("symbols") or cls.symbols))}.</p>
{'<p class="down">' + t("The bot changed after this report, so these numbers are for an older version.") + '</p>' if changed else ''}
<div class="card"><b>{t("Headline.")}</b> {_e(rep.get("headline"))}</div>
<h2>{t("Its rules")}</h2><ol>{rules}</ol>
<h2>{t("Bot facts")}</h2><div class="card wrap"><table>{rows}</table></div>
<h2>{t("Every year")}</h2>
<p class="muted">{t("TUNED years are where the settings were picked, so they look better than they should. UNTESTED years are the real test. Costs are already taken out.")}</p>
<div class="card wrap"><table><tr><th>{t("Year")}</th><th>{t("Period")}</th><th class="num">{t("Trades")}</th><th class="num">{t("Per trade")}</th><th class="num">{t("Total")}</th><th>{t("Beat holding SPY?")}</th></tr>{years}</table></div>
<footer>Made with BotScope on {datetime.now():%Y-%m-%d} from the report saved {_e((rep.get("saved_at") or "")[:10])}. Data: {_e(demo.SOURCE if is_demo else rep.get("data"))}.
{t("R = multiples of the risk on each trade (entry to stop). Paper trading only. Past results, even honest ones, don't predict the future.")} {t("Not financial advice.")}</footer>
</main></body></html>
"""


def export(bot: str) -> dict:
    cls = loader.get(bot)
    text = page(bot)
    folder = shares_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{loader.bot_id(cls)}-{datetime.now():%Y-%m-%d}.html"
    path.write_text(text)
    return {"file": str(path), "bytes": len(text.encode()),
            "contains": "the bot's rules, its saved honest report and nutrition label; no keys, account or file paths",
            "next": "Open it in a browser to check it. It stays on this computer: publishing it anywhere is your own "
                    "separate step (ask first)."}
