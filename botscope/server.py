"""BotScope MCP server (stdio). Plugs into the user's own Claude. No tool here can place an order: chart changes
(moved stops, vetoes, drawings) only replay the day on paper and are saved to local JSON.

Run: .venv/bin/python -m botscope.server
"""
from __future__ import annotations

import functools
import threading

from mcp.server.mcpserver import MCPServer

from . import account, backtest, loader, view
from .errtext import say

mcp = MCPServer(
    "botscope",
    instructions=("BotScope: look inside your own trading bots. Paper trading only, nothing here places orders. "
                  "Not financial advice. Show results as short tables; always say which numbers are from TUNED "
                  "days and which are from UNTESTED days, and name the data source."),
)
_register = mcp.tool


def _demo_aware_tool(*a, **k):
    """Every tool's result gets the DEMO DATA badge in demo mode (no keys): see demo.label."""
    reg = _register(*a, **k)

    def deco(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kw):
            from . import demo
            return demo.label(fn(*args, **kw))
        return reg(wrapped)
    return deco


mcp.tool = _demo_aware_tool
FREE_MODE = False                         # True when run from the terminal (botscope <tool>), not by Claude
_one_backtest = threading.Lock()          # at most one backtest at a time (keeps the computer responsive)


@mcp.tool()
def doctor() -> dict:
    """Is this setup ready? Checks the .env (where it was found), Alpaca paper keys (present or not, never their
    values), optional FRED / Finnhub / SEC keys, bots, the page port, STOP and the live lock. Show `summary`, then
    the checks table with each `fix` in plain words. Reads only."""
    from . import doctor as d
    return d.check(via_mcp=not FREE_MODE)


@mcp.tool()
def list_bots() -> dict:
    """List the user's bots (from the bots folder) with their plain-English rules, tickers and honest status."""
    bots, errors = loader.load_all()
    return {"folder": str(loader.bots_dir()),
            "bots": [{"id": k, **{f: c.card()[f] for f in ("name", "description", "rules", "symbols", "timeframe",
                                                            "sides", "status", "tuned_on")}}
                     for k, c in bots.items()],
            "files_with_errors": errors}


@mcp.tool()
def run_backtest(bot: str, symbols: list[str] | None = None, days: int = 30, position_size_usd: float = 10_000,
                 params: dict | None = None, filters: dict | None = None) -> dict:
    """Quick backtest of one bot with real trading costs, split into TUNED days (where its settings were picked)
    and UNTESTED days (the honest test). `days` = calendar days per period (max 60). Up to 5 symbols.
    `params` tries changed settings (e.g. a rule idea from the chart: {"r_multiple": 1.5}); run it once without
    and once with, and show both. `filters` tests a skip rule without editing the bot: skip_side ("long"/"short"),
    skip_before / skip_after ("HH:MM" New York), skip_symbols, skip_weekdays (0=Mon), max_risk_pct. Data: Alpaca SIP feed with the user's own keys. `settings_tried_on_these_days` (+ `tries_note`): repeat the note when it is there. `if_costs_doubled_r` = the total if trading costs were twice as high (does it survive worse fills?). `without_best_3_r` = the total with its 3 best trades taken out (does it rest on a few lucky trades?). `confidence` is a five-level meter
    (very low .. very high) from untested trades and live paper results, never a percentage: show the level and
    its `why` lines."""
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        out = backtest.run(loader.get(bot), symbols=symbols, days=max(5, min(days, 60)),
                           notional=position_size_usd, feed="sip", params=params, filters=filters)
        u = (out.get("periods") or {}).get("untested")
        if u and u.get("from"):
            from . import tries
            out |= tries.note(loader.bot_id(loader.get(bot)), u["from"], u["to"], params, filters)
        return out
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def honest_report(bot: str, symbols: list[str] | None = None, position_size_usd: float = 10_000,
                  crashes: bool = True) -> dict:
    """The full honest report: every year since 2016 (Alpaca's data start), split into TUNED years (settings were
    picked there) and UNTESTED years (the real test), with real costs (`costs_r` = what costs took), a range of
    outcomes (5th/50th/95th of 1,000 reshuffles), worst losing streak, deepest drop, near misses (ghost trades) and
    the crash time machine. Intraday bots test one month per year to stay light; the first run downloads a lot, so
    it can take a few minutes. Show: the headline, a by-year table (mark tuned rows), the crash table, confidence."""
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        from . import report
        return report.full_report(loader.get(bot), symbols, position_size_usd, crashes=crashes)
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def ask_market_question(question: str, idea_from: str = "recent", position_size_usd: float = 10_000) -> dict:
    """A plain-English one-off market question ("how did buying SPY on red Mondays do?", "buy QQQ after 3 down days
    in a row, hold 5 days", "short IWM when it gaps up 1%") becomes an instant honest test on daily candles, without
    writing a bot: every year since the data starts, after costs, vs just holding SPY, with a confidence level. The
    last 12 months count as TUNED (where the user probably noticed the idea) unless idea_from="elsewhere". Show
    `understood_as` first (so the user can correct it), then the untested numbers, the by-year table (mark tuned
    rows), vs_spy and the confidence level with its why lines. Counts and R only, never a win %."""
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        from . import question as q
        return q.ask(question, idea_from=idea_from, notional=position_size_usd)
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def crash_test(bot: str, symbols: list[str] | None = None, params: dict | None = None) -> dict:
    """The crash time machine: the bot through the 2018 Q4 sell-off, the 2020 covid crash and the 2022 bear market.
    2008 is listed as NOT TESTED (Alpaca's data starts in 2016); never guess its result. Show one row per crash."""
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        from . import report
        return report.crash_test(loader.get(bot), symbols, params=params)
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def luck_meter(bot: str, symbols: list[str] | None = None, all_years: bool = False) -> dict:
    """Could a bot with no idea have done as well? On UNTESTED days: 100 random twins (same trades, random entry
    candle) and 10 runs on shuffled days (same candles in random order). Answers with counts ("beat 87 of 100"),
    never a probability. `all_years` = every untested year since 2016 instead of the quick window (slower).
    Show the level, the why lines and the twin numbers."""
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        from . import luck
        return luck.luck_meter(loader.get(bot), symbols, years=all_years)
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def bot_arena(bot_a: str, bot_b: str | None = None, params_a: dict | None = None, params_b: dict | None = None,
              symbols: list[str] | None = None, days: int = 60) -> dict:
    """Bot vs bot: race two bots, or two versions of one bot (leave bot_b empty and give params_a / params_b), on
    the same symbols and the same UNTESTED days (never days either was tuned on), with real costs. Says who won and
    whether the gap beats luck (how often each stays ahead when the days are reshuffled 1,000 times: counts, not a
    probability). Show `table` as a two-row table, then the level and why lines."""
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        from . import arena
        return arena.race(loader.get(bot_a), loader.get(bot_b) if bot_b else None, params_a, params_b,
                          symbols, days=max(10, min(days, 120)))
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def teach_me(bot: str, symbol: str | None = None, day: str | None = None, position_size_usd: float = 10_000) -> dict:
    """Teach-me mode: the bot explains one day like a tutor, step by step (its rules, what it waited for, each
    trade's entry / stop / target / result in plain words, near misses, your vetoes), plus the words it used and one
    quiz question. Built only from the real replay. Show each lesson part as a short heading + bullets, then
    `words_used` as a small table, then ask the quiz and wait for the answer before saying more. Paper only."""
    try:
        from . import teach
        return teach.teach_me(bot, symbol, day, position_size_usd)
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}


@mcp.tool()
def market_weather(bot: str | None = None) -> dict:
    """Market weather: trending up / trending down / choppy / panic (plus quiet / normal / jumpy), from SPY's
    finished daily closes, with the why lines and numbers. Lists each bot's saved fit: its UNTESTED trades grouped
    by the weather on their entry day, and whether it does well or struggles in today's weather. Pass `bot` to
    measure (or re-measure) one bot's fit now (a 90-day untested backtest). Show the weather + why first, then one
    small table per bot."""
    from . import weather
    if not bot:
        try:
            return weather.market_weather()
        except RuntimeError as e:
            return {"error": say(e)}
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        return weather.market_weather(loader.get(bot))
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def weather_calendar(months: int = 6, bot: str | None = None) -> dict:
    """Weather calendar: past trading days colored by the market weather known at each day's open (trending up /
    down, choppy, panic) with SPY's move; clicking a day on the page opens that day's replay in the bot view. Give
    the `url`, then the counts per weather."""
    def go():
        from . import weather
        d = weather.calendar_days(months)
        url = view.ensure_server() + "/weather" + (f"?bot={loader.bot_id(loader.get(bot))}" if bot else "")
        return {"url": url, "from": d["from"], "to": d["to"], "counts": d["counts"], "trading_days": len(d["days"]),
                "last_10": d["days"][-10:], "source": d["source"], "note": d["note"]}
    return _safe(go)


@mcp.tool()
def days_like_today(bot: str, symbol: str | None = None, count: int = 10) -> dict:
    """Days like today: past days whose market looked like today's at the open (SPY's last 20 days: swings,
    one-way-ness, 20-day move, distance from the 60-day high, worst recent day), and what the bot did on each (one
    symbol, light replay). Show today's weather, then a short table (day, tuned/untested, how alike, bot result),
    then the summary with wins as a count. Always say the sample is small and it's not a forecast."""
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        from . import alike
        return alike.days_like_today(loader.get(bot), symbol, max(3, min(count, 20)))
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def time_of_day_map(bot: str, symbols: list[str] | None = None, days: int = 60) -> dict:
    """Time-of-day map: which hours (US Eastern, by entry time) the bot makes or loses money, on UNTESTED days only
    (daily bots: by weekday). Show a short table: hour, trades, wins as a count ("3 of 8", never a %), total R,
    verdict. Repeat the hint and that picking hours from this makes these days tuned."""
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        from . import timemap
        return timemap.time_map(loader.get(bot), symbols, max(10, min(days, 90)))
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def size_by_risk(entry: float, stop: float, account_usd: float = 10_000, risk_pct: float = 1.0) -> dict:
    """Size by risk: turns "risk 1% per trade" into a share count for a paper trade (shares = account x risk % /
    distance to the stop, never more than the account can buy). Show shares, position $, risk $ and the explain
    line. Information only: nothing is ordered. Not financial advice."""
    from . import sizing
    return _safe(sizing.shares_for, entry, stop, account_usd, risk_pct)


@mcp.tool()
def what_if_stop_target(bot: str, symbols: list[str] | None = None, days: int = 30,
                        position_size_usd: float = 10_000) -> dict:
    """What-if grid for the chart's sliders: the bot on its UNTESTED days with the stop 0.5x-2x as far as it chose,
    and the target kept or set to 1/1.5/2/3x the risk (30 combinations, computed once and saved; the sliders on
    the chart then update instantly). Show the baseline vs `best_looking` as a two-row table with trades, total R,
    wins (as "5 of 12", never a %) and $ per win, and always repeat the caution: picking the best cell on these days makes them tuned."""
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        from . import whatif
        return whatif.grid(loader.get(bot), symbols, max(5, min(days, 60)), position_size_usd)
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def weekly_recap(week_of: str | None = None) -> dict:
    """Weekly recap: one shareable image (SVG saved under data/recaps) of the week's closed PAPER trades per bot, in
    R after costs, next to each bot's untested backtest per-trade result, with the vetoes count and an honesty line
    (a small week says it's small). `week_of` = any date in the week (default this week). Show the table and give
    the image path; never add numbers that aren't in the result."""
    from datetime import date as _d
    from . import recap
    try:
        return recap.save(_d.fromisoformat(week_of) if week_of else None)
    except ValueError as e:
        return {"error": say(e)}


@mcp.tool()
def mistake_mirror(trades_csv: str, bots: list[str] | None = None) -> dict:
    """Mistake mirror: the user's own trades (a CSV they point to: date, time HH:MM New York, symbol, side, entry,
    exit, optional stop) next to what each bot would have done that day: agreed / other way / stayed out, with the
    bot's own reason. Then: how the user's trades did when a bot agreed vs when every bot stayed out. Reads the file
    only; nothing is copied or saved. Show the summary lines, then a short table (date, symbol, side, your %, each
    bot's verdict). Be kind and factual; never call a trade a mistake, let the numbers speak. Last 50 trades."""
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        from . import mirror
        return mirror.mirror(trades_csv, bots)
    except FileNotFoundError:
        return {"error": f"no file at {trades_csv}. Export your trades as a CSV with the columns date, time, symbol, "
                         "side, entry, exit (and optional stop), then give its full path."}
    except (KeyError, RuntimeError, ValueError, OSError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def project_map() -> dict:
    """The project map page: an Obsidian-style graph of BotScope's own parts (what uses what, which Claude tools each
    serves, a timelapse of the build from git) and a Bot family tab (one dot per change to each bot, with the latest
    saved results). Colors, dot shapes, connectors and labels can be changed on the page. Give the user the URL."""
    return _safe(lambda: {"url": view.ensure_server() + "/map",
                          "note": "Built from your own files and git history on this computer."})


@mcp.tool()
def nutrition_label(bot: str) -> dict:
    """The bot's nutrition label: one standard card (untested years, trades, per-trade result after costs, range,
    worst drop and streak, costs, crashes, luck, near misses, live paper trades, confidence) from results saved on
    this computer. Rows not measured yet say so; offer to run honest_report / luck_meter. Show `markdown` as is and
    give the `url` (a page on this computer)."""
    def go():
        from . import label
        lb = label.build(bot)
        return lb | {"markdown": label.markdown(lb), "url": view.ensure_server() + "/label?bot=" + lb["id"]}
    return _safe(go)


@mcp.tool()
def stop_everything(reason: str = "") -> dict:
    """STOP: the user said stop (or "STOP", "pause everything", "kill switch"). Do it at once, no questions: every
    order is blocked (paper and live) and every bot counts as OFF until resume_trading. Open positions are not
    closed; ask whether they want that separately."""
    from . import guard
    return _safe(guard.stop_everything, reason)


@mcp.tool()
def set_loss_budget(weekly_r: float | None = None, confirm: bool = False) -> dict:
    """One weekly loss limit across all bots, in R (e.g. 5 = stop after losing 5R this week, Monday to Sunday, from
    paper results). When it's used up, STOP everything is pressed once that week (resume_trading undoes it).
    Without `weekly_r` it shows where the week stands. Lowering works at once; raising it or turning it off (0) asks
    first: call with confirm=true only after the user says yes."""
    from . import loss_budget
    if weekly_r is None:
        return _safe(loss_budget.status)
    return _safe(loss_budget.set_budget, weekly_r, confirm)


@mcp.tool()
def export_to_gallery(bot: str) -> dict:
    """Honest bot gallery: write a GitHub-ready folder (gallery/<bot>/: the bot file, README with its full nutrition
    label, label.json). Needs a saved honest report. Never pushes or uploads: tell the user to read README.md and
    publish it themselves if they want. Failed bots are marked FAILED at the top."""
    from . import gallery
    return _safe(gallery.export, bot)


@mcp.tool()
def screenshot_confidence(symbol: str, setup: str, timeframe: str = "1Day", as_of: str | None = None) -> dict:
    """Screenshot confidence check (see the botscope-screenshot-check skill): after YOU read the user's screenshot
    and identified the ticker, timeframe, date and setup, find every past match of that setup on that stock (bars
    before `as_of` only), play each out the same simple way, and return a confidence level from very low to very
    high with the sample size and source. setup: breakout, breakdown, gap_up, gap_down, dip_in_uptrend,
    rally_in_downtrend, oversold_bounce, tight_range_uptrend (anything else = "very low: not enough to go on").
    Show: confidence, sample size, source, the why line. Wins only as a count, never a percentage; always "not financial advice"."""
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        from . import setups
        return setups.check(symbol, setup, timeframe, as_of)
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def scam_check(text: str, source: str = "", let_through_reason: str = "") -> dict:
    """Scam checker: run on ANY pasted or researched text (transcript, article, strategy, signal-group pitch) BEFORE
    using it. Returns red / yellow / green with each red flag and why. Red is held back: show the reasons and only
    continue if the user says so on purpose (call again with let_through_reason, which is logged). Green/yellow can
    go to the honest backtest (botscope-fact-check). Not financial advice."""
    from . import scam
    out = scam.check(text)
    if out["held_back"] and let_through_reason.strip():
        out |= {"held_back": False, "override": scam.let_through(source or text[:80], let_through_reason)}
    return out


@mcp.tool()
def phone_alert_test() -> dict:
    """Send one test alert to every channel the user set up in .env (ntfy NTFY_TOPIC, Discord DISCORD_WEBHOOK_URL,
    Telegram TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID) so they can check it arrives. If none is set, say how (the free
    ntfy app with a long random topic is the simplest). Never show topics, webhooks or tokens back. Alerts never
    carry keys or dollar amounts."""
    from . import alerts
    return alerts.send("BotScope test", "If you can read this, phone alerts work. Paper only.", "white_check_mark",
                       demo_ok=True)


@mcp.tool()
def resume_trading(confirm: bool = False) -> dict:
    """Undo STOP. Ask the user first, then call with confirm=true."""
    from . import guard
    return _safe(guard.resume, confirm)


@mcp.tool()
def check_order(symbol: str, side: str, qty: float | None = None, notional: float | None = None,
                limit_price: float | None = None, bot: str | None = None) -> dict:
    """Would BotScope's guard let this order through? (allow / ask / deny + why). Never sends anything. Live money
    needs the live switch in the user's .env, a graduated bot (for bot orders), a known size under the cap, and the
    user's yes."""
    from . import guard
    return _safe(guard.check_order, {"symbol": symbol, "side": side, "qty": qty, "notional": notional,
                                     "limit_price": limit_price}, bot)


@mcp.tool()
def drift_alarm(bot: str) -> dict:
    """Are the bot's live paper results still what its backtest expected? Compares them with 1,000 backtest-like runs
    of the same length (from the saved untested trades). Levels: ok / watch / alarm / too good. Counts, never a
    probability. On "alarm", suggest pausing the bot (the daily on/off list) and looking at recent trades."""
    from . import drift
    return _safe(drift.for_bot, bot)


@mcp.tool()
def graduation_test(bot: str) -> dict:
    """Has the bot earned a live-money switch? Checklist: not failed, 20+ paper days, 30+ paper trades, paper making
    money, confidence high+, honest report positive on untested years and made from today's code, luck meter not
    luck, no drift alarm. Show the checklist as a table (check / needs / has / pass)."""
    from . import graduation
    return _safe(graduation.test, bot)


@mcp.tool()
def switch_live(bot: str, on: bool, confirm: bool = False) -> dict:
    """Turn a bot's live-money switch on or off. OFF works at once. ON needs a passed graduation test, the live switch
    in the user's own .env, and the user's yes (confirm=true only after they say yes). Paper is the default."""
    from . import graduation
    return _safe(graduation.switch_live, bot, on, confirm)


@mcp.tool()
def morning_brief(push_to_phone: bool = False) -> dict:
    """Morning brief: 3 lines before the open (market weather, today's events with before-open / after-close times,
    what each bot that's ON will watch + its confidence level). No AI, no new data: reuses the weather, calendar,
    pre-flight answers and confidence meter. `push_to_phone` sends the 3 lines to your own ntfy topic. Show the 3
    lines as they are, then the sources line."""
    from . import brief
    return _safe(lambda: brief.brief(push=push_to_phone))


@mcp.tool()
def weekly_checkup() -> dict:
    """Weekly checkup (a Sunday card): drift per bot, whether trading costs changed since the last checkup, data gaps
    (weekdays last week with no paper results), old or missing honest reports, and bots changed since their report.
    No new backtests. Show the 4 `lines`, then `summary` and a small table of bots with flags."""
    from . import checkup
    return _safe(checkup.checkup)


@mcp.tool()
def loss_autopsy(bot: str | None = None, day: str | None = None) -> dict:
    """Loss autopsy: why a paper day lost (default: the newest losing bot-day in the paper log). Five checks: the
    market (weather that morning + the bot's fit), the market's own move vs the bot's side, costs (would it have lost before costs?), fills (stop exits that
    slipped past -1R), and normal-or-not (the loss vs the bot's worst untested drop). Show the checks as a short
    table, then the chart link (url)."""
    from . import autopsy

    def go():
        out = autopsy.autopsy(bot, day)
        if out.get("found"):
            out["url"] = view.ensure_server() + out.pop("chart_path")
        return out
    return _safe(go)


@mcp.tool()
def shadow_scoreboard(day: str | None = None) -> dict:
    """Shadow mode scoreboard: each bot family (a bot plus new versions that declare  shadows = "<old bot id>")
    with every version's paper result for the day, its total on the SAME days (from the newest version's first
    paper result), trade counts and confidence level, plus a verdict that won't pick a leader under 20 trades each.
    Show one small table per family, then the verdict."""
    from . import shadow
    return _safe(shadow.scoreboard, day)


@mcp.tool()
def export_paper_results(bot: str | None = None, path: str | None = None) -> dict:
    """Export the live paper log as a CSV for your own spreadsheet (day, bot, symbol, side, R, why it closed). Default
    file: data/journal/exports/paper_results.csv on this computer. Say how many trades and the date span, and that
    these are paper trades, not a backtest."""
    from . import export
    return _safe(export.paper_csv, bot, path)


@mcp.tool()
def backup_my_data(path: str | None = None) -> dict:
    """Backup: one zip of your bots and your journal (paper results, reports, settings), saved outside the BotScope
    folder (default ~/.botscope/backups/) so a plugin update can't take them. Keys are never included. Say where it
    went and how to restore."""
    from . import backup
    return _safe(backup.backup, path)


@mcp.tool()
def key_dates(symbol: str, bot: str | None = None) -> dict:
    """Stock lookup + key dates for one ticker: earnings (before open / after close), splits, dividends and its
    biggest move days over the last year, plus what's coming in the next 90 days. Each source is named; a missing
    one is listed in `problems`. Pass `bot` to get chart links for the past dates (that bot trading that stock on
    that day). Show 'coming' first, then the past dates as a short table."""
    from . import keydates

    def go():
        out = keydates.key_dates(symbol)
        if bot:
            cls = loader.get(bot)
            base = view.ensure_server()
            for r in out["past"]:
                r["chart"] = f"{base}/?bot={loader.bot_id(cls)}&symbol={out['symbol']}&day={r['date']}"
        return out
    return _safe(go)


@mcp.tool()
def rule_playground(bot: str, rules_off: list[str] | None = None, side: str = "both",
                    position_size_usd: float = 10_000) -> dict:
    """Rule playground: turn a bot's blocking rules off (or trade one side only) and see a one-month projection for
    that mix as a range from UNTESTED history (bad / middle / good, with the sample size), next to the bot as coded.
    Each rule says whether it matters (how much its blocked trades would have made or lost). The first call runs one
    untested backtest and caches it; every toggle after that is instant. Also give the page link (url) with on/off
    switches. Never present the middle as a promise."""
    from . import playground
    if side not in ("both", "long", "short"):
        return {"error": "side must be both, long or short"}
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        cls = loader.get(bot)
        out = playground.play(loader.bot_id(cls), rules_off, side, position_size_usd)
        return out | {"url": view.ensure_server() + f"/playground?bot={out['bot']}"}
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def event_days(bot: str) -> dict:
    """Event-day split: the bot's UNTESTED trades on options-expiration and economic-release days (CPI, jobs, GDP,
    PCE...) vs ordinary days: trades, average and total R, and a verdict only for groups with 10+ trades. Shares
    the rule playground's cached backtest. Show one small table."""
    from . import eventdays
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        return eventdays.event_days(loader.bot_id(loader.get(bot)))
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def preflight_list() -> dict:
    """Today's pre-flight list: every bot with red flags (failed, losing untested years, looks like luck, drift),
    confidence, today's market events, and whether it is on. Ask the user on/off for each (red-flag bots first),
    then call set_bots_on_off. No answer = yesterday's settings; a never-answered bot stays off. Also give the
    page link (url)."""
    from . import preflight
    return _safe(lambda: preflight.today_list() | {"url": view.ensure_server() + "/preflight"})


@mcp.tool()
def set_bots_on_off(choices: dict[str, bool]) -> dict:
    """Save today's on/off answers, e.g. {"nr7_swing": true, "first_hour_breakout": false}. Bots not named keep
    their setting. Paper by default; live money also needs switch_live."""
    from . import preflight
    return _safe(preflight.answer, choices)


@mcp.tool()
def save_checkpoint(note: str = "") -> dict:
    """Save a checkpoint of every bot file BEFORE changing a bot (say what is about to change in `note`)."""
    from . import checkpoints
    return _safe(checkpoints.save, note)


@mcp.tool()
def list_checkpoints() -> dict:
    """Saved checkpoints of the bots folder, newest first, with the files changed since each."""
    from . import checkpoints
    return _safe(checkpoints.list_all)


@mcp.tool()
def show_changes(checkpoint: str) -> dict:
    """Before/after: a diff of every bot file that differs from the checkpoint. Show the key lines, not walls."""
    from . import checkpoints
    return _safe(checkpoints.changes, checkpoint)


@mcp.tool()
def restore_checkpoint(checkpoint: str, confirm: bool = False) -> dict:
    """Undo bot changes back to a checkpoint. Ask the user first, then confirm=true. The current state is saved
    first, so the restore can be undone too (undo_with)."""
    from . import checkpoints
    return _safe(checkpoints.restore, checkpoint, confirm)


@mcp.tool()
def security_check(fix: bool = True) -> dict:
    """Devil's advocate: probe the setup like an attacker would (leaked keys, key file permissions, getting around
    the live-money lock, runaway orders, bad data, the local chart page, risky bot code), without breaking anything.
    Safe fixes (file permissions, .gitignore, STOP on) are applied at once with an undo_id. Lead with the headline,
    then one row per finding (probe / result / what / fixed)."""
    from . import redteam
    return _safe(redteam.run, fix)


@mcp.tool()
def undo_security_fix(undo_id: str) -> dict:
    """Undo one automatic fix from security_check."""
    from . import redteam
    return _safe(redteam.undo_fix, undo_id)


@mcp.tool()
def market_board() -> dict:
    """Market board: the ETFs SPY, QQQ, DIA, IWM (they track the S&P 500, Nasdaq 100, Dow, Russell 2000; prices are
    ETF prices, never call them index levels) and the 11 sector ETFs, change vs yesterday's close,
    plus how many sectors are up (breadth). Show indexes in one line and sectors as a short sorted table; mention the
    desk page (open_desk) for the heat map. Source: Alpaca IEX (free, one exchange)."""
    from . import desk
    return _safe(desk.market_board)


@mcp.tool()
def top_movers(top: int = 10) -> dict:
    """Today's biggest gainers, losers and most active stocks (whole US market, Alpaca screener), filtered to real
    stocks at $5+ (no warrants, rights, units or pennies). Information only: big moves are not a signal."""
    from . import desk
    return _safe(desk.movers, max(1, min(top, 20)))


@mcp.tool()
def market_news(symbols: list[str] | None = None, limit: int = 10) -> dict:
    """Latest news headlines for these tickers (default: the tickers your bots trade), newest first, each with the
    article's own first sentence. Write ONE plain line per headline yourself (what happened, no hype, no advice),
    and link the url. Source: Alpaca news (Benzinga)."""
    from . import desk
    return _safe(desk.news, symbols, max(1, min(limit, 30)))


@mcp.tool()
def fed_odds(meetings: int = 3) -> dict:
    """What traders on Kalshi are paying for each outcome of the next Fed meetings (cut / hold / hike). These are
    market prices, not BotScope's forecast: say "Kalshi traders price ..." and name the source."""
    from . import desk
    return _safe(desk.fed, max(1, min(meetings, 6)))


@mcp.tool()
def yield_curve() -> dict:
    """US Treasury yields from 1 month to 30 years (FRED), change vs a month ago, the 10y-3m and 10y-2y spreads and
    whether the curve is inverted. Show a small table and one line on the shape."""
    from . import desk
    return _safe(desk.yields)


@mcp.tool()
def economy() -> dict:
    """Latest released economic numbers (FRED): CPI inflation, jobs added, unemployment, GDP growth, Fed funds.
    Actual numbers only, no forecasts. For upcoming release dates use market_calendar."""
    from . import desk
    return _safe(desk.econ)


@mcp.tool()
def stock_panels(symbol: str, panels: list[str] | None = None) -> dict:
    """Facts about one stock, from free public sources (each names its source): "short" (FINRA short interest,
    twice a month), "analysts" (Finnhub buy/hold/sell counts), "insiders" (SEC Form 4 insider trades + 8-K filings;
    needs SEC_USER_AGENT in the user's .env), "options" (Alpaca options board near the price, with the move the
    options price in). Default: all four. Information only, never a buy/sell call."""
    from . import desk
    want = panels or ["short", "analysts", "insiders", "options"]
    bad = [p for p in want if p not in ("short", "analysts", "insiders", "options")]
    if bad:
        return {"error": f"unknown panels {bad}"}
    return {p: desk.panel(p, {"symbol": symbol}) for p in want} | {"note": "Information only. Not financial advice."}


@mcp.tool()
def portfolio_risk(only_bots_on_today: bool = False) -> dict:
    """Are all the bots betting on the same thing? Correlation between the bots' tickers (6 months of daily closes),
    the sector each acts most like (measured), beta to the S&P 500, and whether the bots all lean long or short.
    Lead with the verdict, then a short table."""
    from . import risk
    return _safe(risk.portfolio_risk, only_bots_on_today)


@mcp.tool()
def open_desk() -> dict:
    """Open the market desk page on this computer (board + sector heat map, movers, news, Fed odds, yield curve,
    calendar, stock panels, portfolio risk). Returns a localhost URL."""
    return _safe(lambda: {"url": view.ensure_server() + "/desk"})


@mcp.tool()
def parent_view() -> dict:
    """Parent view: a read-only page (and summary) for a parent: what each bot does, the limits, paper vs real money,
    the live lock, STOP, recent paper trades and guard alerts. Nothing on it can change a setting. Give the `url`."""
    def go():
        from . import parent
        return parent.summary() | {"url": view.ensure_server() + "/parent"}
    return _safe(go)


@mcp.tool()
def open_studio(bot: str | None = None, tab: str | None = None) -> dict:
    """Open BotScope Studio on this computer: one page with tabs for the bot view, the desk, the rule playground, the
    family tree / project map, strategy factory results and the tutorial. `tab` = "start" opens Get started (the
    newcomer's step-by-step setup: free paper keys, your bots, Claude inside Studio). Returns a localhost URL; give it
    to the user (or open it in the browser pane). Works on a phone-width window too."""
    from urllib.parse import quote
    tab = tab if tab and tab.isalnum() else None
    return _safe(lambda: {"url": view.ensure_server() + "/studio" + (f"?bot={quote(bot)}" if bot else "")
                                 + (f"#{tab}" if tab else "")})


@mcp.tool()
def new_bot(name: str, description: str, timeframe: str = "5Min", symbols: list[str] | None = None,
            sides: str = "both", r_multiple: float = 2.0) -> dict:
    """One-sentence start: write a starter bot file in the bots folder (a checkpoint is saved first). It loads and
    runs but takes no trades until you write entry() and the plain-English rules (see the botscope-new-bot skill),
    then run check_bot and run_backtest. timeframe: 1Min/5Min/15Min/1Hour/1Day; sides: long/short/both."""
    from . import scaffold
    return _safe(scaffold.new_bot, name, description, timeframe, symbols, sides, r_multiple)


@mcp.tool()
def make_shadow(bot: str, version: str | None = None) -> dict:
    """Shadow mode starter: copy a bot as a new version (new name "<name> v<version>", next major version by
    default) with  shadows = "<old id>"  so both run on paper and shadow_scoreboard compares them. Saves a checkpoint
    first. Then help the user change the new file and run check_bot on it."""
    from . import scaffold
    return _safe(scaffold.make_shadow, bot, version)


@mcp.tool()
def strategy_factory(goal: str, symbols: list[str] | None = None, max_candidates: int = 5) -> dict:
    """Strategy factory: the user describes a goal in a sentence ("a calm daily ETF bot"); BotScope writes up to 5
    candidate bots from textbook templates (settings never tuned here, so every year is UNTESTED), runs each one at a
    time through check_bot, the honest report (costs, doubled costs, without its 3 best trades, stops wider than
    their costs, losing years, the
    later half of the years, the goal's own limits such as "calm" or "hands-off"), settings 20% smaller and bigger,
    and the luck meter, and keeps only the survivors. Every keep/drop decision leaves out the last year; survivors
    then show that held-out year. Show `understood.read_as`
    (so the user can correct it), then `markdown` as is (ranked survivors with confidence levels + every dropped
    candidate with its plain-English reason), then `tries_note`. "No candidate survived" is a real answer: say it
    plainly. Can take a few minutes the first time (downloads). Then offer adopt_candidate for a survivor."""
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        from . import strategy_factory as sf
        return sf.run(goal, symbols, max_candidates)
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def import_pine(script: str, name: str | None = None, timeframe: str = "1Day", symbols: list[str] | None = None,
                stop_pct: float = 2.0) -> dict:
    """Pine Script import: paste a TradingView strategy script; BotScope translates the common subset (number inputs,
    plain variables, ta.sma/ema/rsi/highest/lowest/atr/crossover..., strategy.entry/close/exit) into a bot file in
    the bots folder (checkpoint first), lists every line it did NOT translate and anything it added (a stop_pct stop
    when the script has none), runs check_bot, then the honest report. Show: `not_translated` and `added` first
    (the bot is only as faithful as the translation), then `check`, then the report headline with tuned vs
    untested. Entries fill at the signal bar's close (Pine's default is the next open)."""
    from . import pine, report, strategy_factory as sf
    try:
        out = pine.write_bot(script, name, timeframe, symbols, stop_pct)
    except (KeyError, RuntimeError, ValueError, SyntaxError) as e:
        return {"error": say(e)}
    cls = loader.get(out["bot_id"])
    chk = sf.scaffold.check_class(cls)
    out["check"] = [c for c in chk["checks"] if not c["pass"]] or "all checks pass"
    if not _one_backtest.acquire(blocking=False):
        return out | {"report": "another backtest is running: run honest_report for this bot when it finishes"}
    try:
        rep = report.full_report(cls, crashes=False)
        out["report"] = {"headline": rep["headline"], "data": rep["data"], "years": rep["years"],
                         "confidence": rep["confidence"]["level"]}
    except (KeyError, RuntimeError, ValueError) as e:
        out["report"] = {"error": say(e)}
    finally:
        _one_backtest.release()
    return out


@mcp.tool()
def honest_optimizer(bot: str, setting_a: str | None = None, setting_b: str | None = None,
                     symbols: list[str] | None = None) -> dict:
    """Honest optimizer: a heat map of two number settings (5x5 for daily bots, 3x3 intraday; each cell a full
    honest report on untested years, leaving out the last year), the best spot, and how much luck is in it: best vs
    the middle cell (settings-tried penalty), whether its neighbors also make money (plateau vs island), and the
    held-out year for the best spot vs today's settings. Never changes the bot. Show `markdown`, `luck_in_best`,
    `neighbors.summary`, the held-out pair and `verdict`; Studio's Optimizer tab draws the heat map."""
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        from . import optimizer
        out = optimizer.optimize(loader.get(bot), setting_a, setting_b, symbols)
        return out | {"markdown": optimizer.markdown(out)}
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def team_report(bots: list[str] | None = None) -> dict:
    """Team of bots: run all your bots (or the ones named) together on their UNTESTED years for one combined result
    in R, the team's worst drop next to the sum of each bot's own worst drop, and how much they overlap (shared
    entries, same-day correlation). Show `markdown`, `drop_note`, the overlap pairs and `same_bet`. Several
    backtests: can take a minute or more with intraday bots."""
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        from . import team
        return team.team(bots)
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def strategy_dna(bots: list[str] | None = None) -> dict:
    """Strategy DNA: fingerprint each bot (trend following vs dip buying, holding time, time of day, long/short
    lean, symbols) and flag near-twins (bots that are really the same bet). Runs a short untested-days backtest per
    bot, one at a time. Show one table row per bot, then the near-twin pairs with their why lines."""
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        from . import dna
        return dna.dna(bots)
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def option_spread_plan(bot: str, symbol: str | None = None, side: str | None = None) -> dict:
    """Defined-risk option spread plan from a bot's stock signal (paper only, never ordered): a long signal becomes a
    bull call debit spread, a short one a bear put debit spread, 7-45 days out, priced at the cautious side of the
    quotes, with max loss (the debit), max gain and breakeven in dollars. With no `side`, it uses the bot's decision
    on its newest candle and says so when there's no signal. Spreads aren't backtested: say so."""
    from . import spreads
    return _safe(spreads.spread_plan, bot, symbol, side)


@mcp.tool()
def data_sources() -> dict:
    """Which data adapters BotScope has (Alpaca by default; Coinbase public candles for crypto, keyless, read-only),
    which one each kind of symbol uses now, and how to switch (BOTSCOPE_CRYPTO_DATA in .env). Adapters only read
    data; orders never go through them. Reads only."""
    from . import brokers
    return brokers.sources()


@mcp.tool()
def add_alert(text: str) -> dict:
    """Plain-English alert: "tell me when NVDA breaks yesterday's high", "when SPY falls below 590", "when AAPL moves
    3% today", "when TSLA crosses its 50-day average" becomes a saved rule. Show `reads_as` so the user can check
    it was understood. Information only: alerts never trade. They go to the user's own ntfy / Discord / Telegram."""
    from . import price_alerts
    return _safe(price_alerts.add, text)


@mcp.tool()
def list_alerts() -> dict:
    """The saved plain-English alert rules: id, what each one reads as, and the last day it fired. Reads only."""
    from . import journal
    return {"rules": [{k: r.get(k) for k in ("id", "text", "reads_as", "fired_on")} for r in journal.load("alert_rules")],
            "channels": __import__("botscope.alerts", fromlist=["x"]).channels()}


@mcp.tool()
def remove_alert(rule_id: str) -> dict:
    """Delete one saved alert rule by its id (from list_alerts)."""
    from . import price_alerts
    return price_alerts.remove(rule_id)


@mcp.tool()
def check_alerts() -> dict:
    """Check every saved alert rule against today's finished 5-minute candles (and yesterday's daily candle) and send
    the ones that hit to the user's own channels, at most once a day per rule. Run it on a schedule from free mode
    (`botscope check_alerts`) to keep watching. Information only."""
    from . import price_alerts
    return _safe(price_alerts.check)


@mcp.tool()
def friends_league(export_bot: str | None = None, owner: str = "me") -> dict:
    """Friends league: compare bots by an honest score (bad end of the untested range per trade after costs, luck
    meter, trade count), never raw profit. `export_bot` writes that bot's league card (one JSON file, no keys, no
    account, no dollars) to share by hand; friends' cards dropped in the league folder are read as data only. No
    server, no account, nothing uploaded. Show the table: place, owner, bot, honest score, trades, luck, confidence."""
    from . import league
    if export_bot:
        return _safe(league.export, export_bot, owner)
    return _safe(league.league)


@mcp.tool()
def friends(how: str = "list", bot: str | None = None, name: str = "me", include_rules: bool = False,
            code: str | None = None, friend: str | None = None) -> dict:
    """Friends (read-only): how = "code" (make a friend code for `bot`: one block of text with its honest numbers,
    UNTESTED years after costs; rules and tickers only if include_rules), "add" (paste a friend's `code`), "list",
    "compare" (your `bot` vs a saved `friend` id: side-by-side rows plus what your bot can learn and what theirs can
    learn) or "remove" (`friend` id). No server, nothing uploaded; a friend's card is numbers only and is never run,
    and nothing is copied or changed. Show the rows as a short table, then the lessons, and say each one needs a
    run_backtest before any change. Not financial advice."""
    from . import friends as fr
    if how == "code":
        return _safe(fr.my_code, bot or "", name, include_rules)
    if how == "add":
        return _safe(fr.add, code or "")
    if how == "compare":
        return _safe(fr.compare, bot or "", friend or "", name)
    if how == "remove":
        return _safe(fr.remove, friend or "")
    return _safe(fr.listing)


@mcp.tool()
def export_report_page(bot: str) -> dict:
    """Share as a page: write one bot's saved honest report (rules, nutrition label, every year with TUNED vs
    untested marked) as a single standalone HTML file on this computer. No keys, account info or file paths go in.
    It is never uploaded; publishing it is a separate step the user starts and approves. Needs honest_report first."""
    from . import share
    return _safe(share.export, bot)


@mcp.tool()
def robustness_check(bot: str, symbols: list[str] | None = None) -> dict:
    """The strategy factory's full checklist on any bot, including your own: check_bot, 30+ untested trades, money
    after costs, doubled costs, without its 3 best trades, stops wider than their costs, most untested years, still
    working in the later years,
    settings 20% smaller and bigger, and the luck meter. Every check is shown pass/fail (it doesn't stop at the
    first). Decisions leave out the last year, then `held_out` shows it. Show the checks table, `passed`, and the
    held-out year with its note. Several backtests: can take a minute or two."""
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        from . import strategy_factory as sf
        return sf.robustness(loader.get(bot), symbols, save=True)
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def factory_history(limit: int = 10) -> dict:
    """Past strategy-factory runs, newest first: goal, candidates tried, survivors (DEMO DATA runs are marked), plus
    how many candidates each symbol set has seen in all (more tries = more chances for a lucky survivor). Show a
    short table. Reads only."""
    from . import strategy_factory as sf
    return _safe(sf.history, max(1, min(limit, 50)))


@mcp.tool()
def adopt_candidate(run: str, candidate: str) -> dict:
    """Copy one strategy-factory survivor (`run` and the candidate's `id` from strategy_factory) into the user's bots
    folder, after a checkpoint. Ask the user first. It's still untested on paper: suggest nutrition_label,
    open_bot_view and paper trading next."""
    from . import strategy_factory as sf
    return _safe(sf.adopt, run, candidate)


@mcp.tool()
def check_bot(bot: str) -> dict:
    """Check a bot on made-up bars: it loads, never peeks at future bars, runs, gives a reason for every decision,
    and its plain-English rules mention every setting in params. Show failing checks first."""
    from . import scaffold
    return _safe(scaffold.check_bot, bot)


@mcp.tool()
def account_summary() -> dict:
    """The user's Alpaca PAPER account: equity, cash, today's change and open positions. Read only."""
    try:
        return account.summary()
    except RuntimeError as e:
        return {"error": say(e)}


@mcp.tool()
def market_calendar(days: int = 30) -> dict:
    """Upcoming market events for the next `days` days (max 90): holidays and half days, monthly options
    expiration, Fed decisions, CPI / jobs / GDP / PCE releases, and earnings (before open / after close) for
    market movers and the user's bots' tickers. Every row names its source."""
    from .market_data import market_calendar as mc
    return {"events": mc.upcoming(max(1, min(days, 90))), "note": "Information only. Not financial advice."}


def _safe(fn, *a, **k):
    try:
        return fn(*a, **k)
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}


@mcp.tool()
def open_bot_view(bot: str, symbol: str | None = None, day: str | None = None) -> dict:
    """Open the "what the bot sees" chart on this computer: candles, the bot's indicators, entries/exits, stop and
    target lines (draggable), vetoes and the user's drawings. `day` = YYYY-MM-DD (default: the latest session; today
    refreshes every 30 s). Returns a localhost URL; give it to the user (or open it in the browser pane)."""
    return _safe(view.open_view, bot, symbol, day)


@mcp.tool()
def trade_clip(bot: str, symbol: str | None = None, day: str | None = None, trade_id: str | None = None) -> dict:
    """Trade clip: a page that replays one finished trade candle by candle with its honest label (paper, tuned or
    untested day, result in R after costs, confidence) and records it as a short WebM saved on this computer only
    (data/clips; nothing uploaded). Default: the day's last finished trade. Give the `url`; the user presses
    "Record and save"."""
    def go():
        from urllib.parse import urlencode
        from . import clip
        c = clip.clip_data(bot, symbol, day, trade_id)
        qs = urlencode({"bot": c["bot"], "symbol": c["symbol"], "day": c["day"], "trade": c["trade"]["id"]})
        return {"url": view.ensure_server() + "/clip?" + qs, "label": c["label"], "folder": str(clip.folder()),
                "note": "The clip is recorded by the page and saved locally only."}
    return _safe(go)


@mcp.tool()
def why_not_here(bot: str, symbol: str, day: str, time: str) -> dict:
    """What the bot decided on one candle and why (e.g. "range too narrow"). `time` = HH:MM New York time."""
    return _safe(view.why_not_here, bot, symbol, day, time)


@mcp.tool()
def move_stop_target(bot: str, symbol: str, day: str, trade_id: str | None = None, stop: float | None = None,
                     target: float | None = None, scope: str | None = None, confirm: bool = False) -> dict:
    """Move a trade's stop and/or take-profit (prices). For "move the stop up a bit", pick a concrete price from the
    chart (open_bot_view shows the current lines) and say it. ALWAYS ask the user first: just this trade
    (scope="this_trade", replays the day on paper) or the rule for all future trades (scope="rule", saved as an idea
    that must be backtested with run_backtest before anything changes). Without a scope nothing is saved. Real money
    always needs confirm=true after the user says yes. trade_id defaults to the day's last trade."""
    return _safe(view.move_lines, bot, symbol, day, trade_id, stop, target, scope, confirm)


@mcp.tool()
def veto_trade(bot: str, symbol: str, day: str, trade_id: str | None = None, reason: str = "") -> dict:
    """The user says a trade looks bad ("I wouldn't take it"). Paper: the bot skips it, and the veto (with the
    user's reason) is logged to local JSON for veto_scorecard. trade_id defaults to the day's last trade."""
    return _safe(view.veto, bot, symbol, day, trade_id, reason)


@mcp.tool()
def veto_scorecard(bot: str | None = None) -> dict:
    """Did the user's vetoes help or hurt? Replays every logged veto on paper: "helped" = the skipped trade would
    have lost, "hurt" = it would have won, with R per veto and the net R saved. Show the verdict plus a short table
    (day, symbol, reason given, would-have R, verdict). `bot` = one bot (default: all)."""
    return _safe(view.veto_scorecard, bot)


@mcp.tool()
def suggest_rules_from_vetoes(bot: str) -> dict:
    """When the user keeps vetoing the same kind of trade (shorts, late trades, one ticker, far stops), turn the
    pattern into a rule idea and backtest it with and without the rule (tuned vs untested days). Saved as a
    SUGGESTION only; nothing changes unless the user approves and the bot file is edited. Show each suggestion's
    plain rule, evidence, before/after table and verdict."""
    if not _one_backtest.acquire(blocking=False):
        return {"error": "another backtest is already running; try again when it finishes"}
    try:
        from . import veto_rules
        return veto_rules.suggest(bot)
    except (KeyError, RuntimeError, ValueError) as e:
        return {"error": say(e)}
    finally:
        _one_backtest.release()


@mcp.tool()
def get_chart_drawings(bot: str | None = None, symbol: str | None = None, day: str | None = None) -> dict:
    """The lines and circles the user drew on the chart, with their notes, the time/price span, the candles under
    them and what the bot did there. Read these together with what the user says ("bad trades look like this")."""
    return _safe(lambda: {"drawings": view.drawings_for_claude(bot, symbol, day),
                          "note": "Times are New York time. Circles are stored as the box around them."})


@mcp.tool()
def log_paper_results(day: str | None = None) -> dict:
    """After the close: replay the day (YYYY-MM-DD, default today) for every bot and symbol and save the closed paper
    trades as live paper results, which feed the confidence meter. Paper only; nothing is traded."""
    from . import daily_log
    from datetime import date
    return _safe(daily_log.run, date.fromisoformat(day) if day else None)


@mcp.tool()
def import_my_bots(how: str = "summary", name: str | None = None, path: str | None = None, mapping: dict | None = None,
                   days: int = 90, rules: dict | None = None, link_to: str | None = None) -> dict:
    """Import my bots (read-only): bring results of bots you already run into BotScope. how = "alpaca" (filled orders
    from your PAPER account, last `days` days, grouped by client_order_id prefix or symbol via `rules`
    {"prefix": {"swing-": "swing"}, "symbols": {"BTC/USD": "crypto"}}, paired first-in-first-out), "file" (a CSV/JSON
    trade log at `path`; `mapping` = {botscope field: your column}, fields symbol side entry exit qty pnl r opened
    closed bot why), "local" (the imports listed in the git-ignored botscope.local.json), "orders" (an imported bot's
    open orders and past orders from your paper account, read-only; `name` = the bot, `days` back) or "summary". `link_to` = a
    BotScope bot id: its imported trades with an R count as live evidence on the confidence meter. Nothing is traded.
    Show a short table per bot: trades, won, total $, average win $, dates, and say these are past trades, not a
    backtest."""
    from . import imports
    if how == "alpaca":
        return _safe(imports.from_alpaca, name or "alpaca", days, rules, link_to)
    if how == "file":
        if not path:
            return {"error": "give the file's path"}
        return _safe(imports.from_file, path, name or path.rsplit("/", 1)[-1].rsplit(".", 1)[0], mapping, link_to)
    if how == "local":
        return _safe(imports.from_local, name)
    if how == "orders":
        return _safe(imports.orders, name, days, rules)
    return _safe(imports.summary, name)


@mcp.tool()
def auto_setup(how: str = "scan", path: str | None = None, bot: str | None = None,
               translated: list[str] | None = None, not_translated: list[str] | None = None,
               added: list[str] | None = None) -> dict:
    """Auto setup for someone's existing bot (read-only, nothing is run or ordered). how = "scan": read the bot's code
    and trade logs at `path` (a file or folder; its code is never run) and list hints: symbols, timeframe,
    indicators, stop/target hints, order calls, and a column mapping per trade log. Then write the bot file with
    new_bot + the code (botscope-auto-setup skill). how = "finish": check_bot on `bot` plus a mapping report of what
    was `translated`, `not_translated` and `added` by BotScope; then run honest_report. Show not_translated first."""
    from . import autosetup
    if how == "finish":
        if not bot:
            return {"error": "give the new bot's id"}
        return _safe(autosetup.finish, bot, path or "", translated, not_translated, added)
    if not path:
        return {"error": "give the path of the bot's code or trade logs"}
    return _safe(autosetup.scan, path)


@mcp.tool()
def publish_check(how: str = "check", out: str | None = None, sources: list[str] | None = None) -> dict:
    """publish-check (local only, nothing is published): how = "check" builds a clean export of the outline from an
    allowlist into a separate folder (default ~/.botscope/publish-export) and scans it for personal info (keys, IPs,
    emails, home paths, Tailscale names, account numbers) and for your own strategies (names, code hashes, rule
    fingerprints from the git-ignored botscope.private.json). how = "build_private" makes that private list from
    `sources` (your strategy files or folders; default botscope.local.json "private"). how = "make_repo" (only after
    a PASS) turns the export into a brand-new git repo with exactly one commit: no history, no remote, nothing pushed;
    show its to_publish_later commands as they are and never run them. Show the verdict first; on FAIL list the hits
    by kind. Going public still needs the user's (and a parent's) go-ahead."""
    from . import publish_check as pc
    if how == "build_private":
        return _safe(pc.build_private, sources)
    if how == "make_repo":
        return _safe(pc.make_repo, out)
    return _safe(pc.run, out)


@mcp.tool()
def phantom_test(how: str = "report", run: str | None = None, candidates: list[str] | None = None,
                 name: str | None = None) -> dict:
    """Phantom test: a live paper forward test of strategy-factory candidates, no orders, nothing adopted. how =
    "start" (run = a factory run id, candidates = names or ids from it), "update" (replay every finished day since the
    last check; the after-close daily log also does this), "report" or "stop" (name). Show a short table: name, since,
    signals, R per signal vs the backtest's untested R per trade, and the verdict; say few signals mean little."""
    from . import phantom
    if how == "start":
        if not run or not candidates:
            return {"error": "give the factory run id and the candidate names"}
        return _safe(phantom.start, run, candidates)
    if how == "update":
        return _safe(phantom.update)
    if how == "stop":
        return _safe(phantom.stop, name or "")
    return _safe(phantom.report)


def main():
    mcp.run("stdio")


if __name__ == "__main__":
    main()
