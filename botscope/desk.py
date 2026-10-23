"""The market desk: free, Bloomberg-style panels. Information only, never a tip: every row names its source, nothing
here changes what a bot does, and nothing is redistributed (each user downloads with their own keys).

Each panel is a thin fetcher plus a pure function that shapes the rows, so the shaping can be tested offline.
"""
from __future__ import annotations

import html
import re

from .env import alpaca_keys

# These are ETF prices, not index levels (SPY is about 1/10 of the S&P 500), so the label names the ETF first.
INDEXES = {"SPY": "SPY (tracks S&P 500)", "QQQ": "QQQ (tracks Nasdaq 100)", "DIA": "DIA (tracks Dow 30)",
           "IWM": "IWM (tracks Russell 2000, small caps)"}
SECTORS = {"XLK": "Tech", "XLC": "Communication", "XLY": "Consumer discretionary", "XLP": "Consumer staples",
           "XLF": "Financials", "XLV": "Health care", "XLI": "Industrials", "XLE": "Energy", "XLB": "Materials",
           "XLU": "Utilities", "XLRE": "Real estate"}
IEX_NOTE = "Alpaca IEX feed (free, real time, one exchange: prices can differ slightly from the full market)"
MIN_PRICE = 5.0
_JUNK = re.compile(r"[.\-/ ]|^[A-Z]{4,}(W|WS|R|RT|U|P|Q)$")   # 5th-letter codes: warrants, rights, units, preferreds, bankrupt
# Funds by their Alpaca name: ETFs/ETNs and leveraged or inverse single-stock products (e.g. "T-Rex 2X Long ... ETF")
_FUND = re.compile(r"\b(ETF|ETN|ETP|ETFs|Fund|Index|Leveraged|Inverse|Daily Target|Bull|Bear|[1-5](\.\d+)?X|"
                   r"Ultra(Pro|Short)?|ProShares|Direxion|GraniteShares|Defiance|Tradr|T-Rex|YieldMax|iShares|"
                   r"SPDR|Invesco QQQ|Vanguard)\b", re.I)
_names: dict = {}


# ---------- fetchers (network; Alpaca with your own keys) ----------
def _snapshots(symbols: list[str]) -> dict[str, tuple[float, float]]:
    """{symbol: (last price, previous close)} from Alpaca IEX snapshots (demo mode: the last two made-up closes)."""
    from .env import demo_mode
    if demo_mode():
        from datetime import date, timedelta
        from . import demo
        out = {}
        for s in symbols:
            bs = demo.bars(s, date.today() - timedelta(days=10), date.today(), "1Day")
            if len(bs) >= 2:
                out[s] = (bs[-1].c, bs[-2].c)
        return out
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockSnapshotRequest
    c = StockHistoricalDataClient(*alpaca_keys())
    snaps = c.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=list(symbols), feed=DataFeed.IEX))
    out = {}
    for sym, s in snaps.items():
        last = s.latest_trade.price if s.latest_trade else (s.daily_bar.close if s.daily_bar else None)
        prev = s.previous_daily_bar.close if s.previous_daily_bar else None
        if last and prev:
            out[sym] = (float(last), float(prev))
    return out


def _asset_names() -> dict[str, str]:
    """{symbol: name} for active US stocks and ETFs, from Alpaca (one call, kept for the day)."""
    from datetime import date
    if _names.get("day") != date.today():
        from alpaca.trading.client import TradingClient
        from alpaca.trading.enums import AssetClass, AssetStatus
        from alpaca.trading.requests import GetAssetsRequest
        tc = TradingClient(*alpaca_keys(), paper=True)
        got = tc.get_all_assets(GetAssetsRequest(asset_class=AssetClass.US_EQUITY, status=AssetStatus.ACTIVE))
        _names.update(day=date.today(), names={a.symbol: a.name or "" for a in got})
    return _names["names"]


def _screener():
    from alpaca.data.historical.screener import ScreenerClient
    return ScreenerClient(*alpaca_keys())


# ---------- market board + sector heat map ----------
def board_rows(snaps: dict[str, tuple[float, float]]) -> dict:
    def row(sym, name):
        last, prev = snaps[sym]
        return {"symbol": sym, "name": name, "price": round(last, 2), "change_pct": round((last / prev - 1) * 100, 2)}
    idx = [row(s, n) for s, n in INDEXES.items() if s in snaps]
    sec = sorted((row(s, n) for s, n in SECTORS.items() if s in snaps), key=lambda r: -r["change_pct"])
    spy = next((r["change_pct"] for r in idx if r["symbol"] == "SPY"), None)
    for r in sec:
        r["vs_spy"] = None if spy is None else round(r["change_pct"] - spy, 2)
    up = sum(r["change_pct"] > 0 for r in sec)
    mood = (None if not sec else "broad rally" if up >= 9 else "broad selloff" if up <= 2 else "mixed")
    return {"indexes": idx, "sectors": sec, "sectors_up": up, "sectors_total": len(sec), "mood": mood,
            "missing": sorted((set(INDEXES) | set(SECTORS)) - set(snaps))}


def market_board(snapshots=None) -> dict:
    snaps = (snapshots or _snapshots)(list(INDEXES) + list(SECTORS))
    from .env import demo_mode
    return board_rows(snaps) | {"source": __import__("botscope.demo", fromlist=["x"]).SOURCE if demo_mode() else IEX_NOTE,
                                "note": "Change vs yesterday's close. Information only, not financial advice."}


# ---------- movers / most active ----------
def is_plain_stock(sym: str, names: dict[str, str] | None = None) -> bool:
    """A common stock: no warrant/right/unit code, and (when names are known) not an ETF, ETN or leveraged product.
    With names known, a symbol missing from them is left out too (not an active plain listing)."""
    if not sym or _JUNK.search(sym):
        return False
    if names is None:
        return True
    return sym in names and not _FUND.search(names[sym])


def mover_rows(gainers, losers, actives, prices: dict[str, float], top: int = 10,
               names: dict[str, str] | None = None) -> dict:
    """Keep common stocks at $5+ (penny stocks, warrants, rights and leveraged ETFs fill the raw lists)."""
    def keep(rows):
        return [r for r in rows if is_plain_stock(r["symbol"], names)
                and (r.get("price") or prices.get(r["symbol"], 0)) >= MIN_PRICE]
    g = [{"symbol": r["symbol"], "price": r["price"], "change_pct": round(r["percent_change"], 2)} for r in keep(gainers)][:top]
    lo = [{"symbol": r["symbol"], "price": r["price"], "change_pct": round(r["percent_change"], 2)} for r in keep(losers)][:top]
    a = [{"symbol": r["symbol"], "price": prices.get(r["symbol"]), "volume": int(r["volume"]),
          "trades": int(r.get("trade_count") or 0)} for r in keep(actives)][:top]
    return {"gainers": g, "losers": lo, "most_active": a}


MOVERS_MAX, ACTIVES_MAX = 50, 100     # Alpaca screener limits: movers return at most 50 rows, most-actives 100


def active_moves(actives, snaps: dict[str, tuple[float, float]]) -> list[dict]:
    """Today's change for the most active stocks, from their snapshots (last vs yesterday's close)."""
    return [{"symbol": a["symbol"], "price": snaps[a["symbol"]][0],
             "percent_change": (snaps[a["symbol"]][0] / snaps[a["symbol"]][1] - 1) * 100}
            for a in actives if a["symbol"] in snaps and snaps[a["symbol"]][1]]


def merge_moves(screener_rows, extra, up: bool) -> list[dict]:
    """Screener movers plus the most active stocks' own moves, one row per symbol, biggest move first."""
    seen, out = set(), []
    for r in sorted([*screener_rows, *extra], key=lambda r: -r["percent_change"] if up else r["percent_change"]):
        if r["symbol"] not in seen and (r["percent_change"] > 0 if up else r["percent_change"] < 0):
            seen.add(r["symbol"]); out.append(r)
    return out


def movers(top: int = 10, screener=None, snapshots=None, asset_names=None) -> dict:
    from alpaca.data.requests import MarketMoversRequest, MostActivesRequest
    sc = screener or _screener()
    m = sc.get_market_movers(MarketMoversRequest(top=MOVERS_MAX))
    act = sc.get_most_actives(MostActivesRequest(top=ACTIVES_MAX))
    dump = lambda xs: [x if isinstance(x, dict) else x.model_dump() for x in xs]   # noqa: E731
    gainers, losers, actives = dump(m.gainers), dump(m.losers), dump(act.most_actives)
    try:
        names = (asset_names or _asset_names)()
    except Exception:            # can't tell funds apart: say so instead of promising "stocks only"
        names = None
    syms = [a["symbol"] for a in actives if is_plain_stock(a["symbol"], names)]
    snaps = (snapshots or _snapshots)(syms) if syms else {}
    prices = {s: p[0] for s, p in snaps.items()}
    extra = active_moves([a for a in actives if a["symbol"] in snaps], snaps)   # most of the top 50 can be ETFs
    gainers, losers = merge_moves(gainers, extra, True), merge_moves(losers, extra, False)
    return mover_rows(gainers, losers, actives, prices, top, names) | {
        # the panel header shows the part before " (", so the useful bit goes first
        "source": f"Alpaca screener: top {MOVERS_MAX} movers + the {ACTIVES_MAX} most active stocks "
                  "(whole US market) + IEX prices",
        "filtered": (f"common stocks at ${MIN_PRICE:.0f}+ only; ETFs, ETNs, leveraged products, warrants, rights and "
                     "units left out" if names is not None else
                     f"${MIN_PRICE:.0f}+ only, warrants/rights/units left out; couldn't load the asset list, so ETFs "
                     "and leveraged products may show up"),
        "note": "Big moves are information, not a signal. Not financial advice."}


# ---------- news with a one-line summary ----------
_TAGS = re.compile(r"<[^>]+>")


def one_line(text: str, limit: int = 140) -> str:
    """First sentence of the source's own summary, cut to one line. (Claude can write a better line from it.)"""
    t = " ".join(html.unescape(_TAGS.sub(" ", text or "")).split())    # "China&#39;s" -> "China's"
    if not t or re.search(r"(?i)click here|subscribe|sign up", t):
        return ""
    m = re.search(r"(.+?[.!?])(\s|$)", t)
    t = m.group(1) if m and len(m.group(1)) >= 25 else t
    return t if len(t) <= limit else t[:limit - 1].rsplit(" ", 1)[0] + "…"


def _et(t) -> str:
    """'YYYY-MM-DD HH:MM' New York time (from a datetime or an ISO string)."""
    from datetime import datetime, timezone
    from .data import ET
    try:
        d = t if isinstance(t, datetime) else datetime.fromisoformat(str(t).replace("Z", "+00:00"))
        d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        return d.astimezone(ET).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(t)[:16]


def news_rows(items: list[dict], limit: int = 15) -> list[dict]:
    seen, out = set(), []
    for x in sorted(items, key=lambda i: str(i.get("created_at")), reverse=True):
        key = (x.get("headline") or "").lower()[:80]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({"time": _et(x.get("created_at")), "tickers": (x.get("symbols") or [])[:5],
                    "headline": html.unescape(x["headline"]), "one_line": one_line(x.get("summary") or ""),
                    "publisher": x.get("source"), "url": x.get("url")})
    return out[:limit]


def news(symbols: list[str] | None = None, limit: int = 15, fetch=None) -> dict:
    from .market_data import bot_tickers
    syms = [s.upper() for s in (symbols or bot_tickers.bot_tickers())][:20]
    if fetch is None:
        from alpaca.data.historical.news import NewsClient
        from alpaca.data.requests import NewsRequest
        res = NewsClient(*alpaca_keys()).get_news(NewsRequest(symbols=",".join(syms), limit=min(50, limit * 2)))
        items = [i.model_dump() for i in res.data.get("news", [])]
    else:
        items = fetch(syms)
    return {"tickers": syms, "news": news_rows(items, limit),
            "source": "Alpaca news (Benzinga), headlines + the article's own summary",
            "note": "one_line is the first sentence of the article's own summary. Claude: write your own 1-line "
                    "summary per headline in plain words, no hype, and say it is from the headline/summary only. "
                    "Not financial advice."}


# ---------- Fed odds (Kalshi) ----------
def fed_rows(rows: list[dict]) -> list[dict]:
    """Group Kalshi rows by meeting; the most likely outcome first. Prices are market prices, not our guesses."""
    meets = {}
    for r in rows:
        if r.get("meeting") and r.get("prob") is not None:
            meets.setdefault(r["meeting"], []).append({"outcome": r["outcome"], "market_odds": r["prob"]})
    out = []
    for m, outs in sorted(meets.items()):
        outs.sort(key=lambda x: -x["market_odds"])
        out.append({"meeting": m, "most_likely": outs[0]["outcome"], "outcomes": outs})
    return out


def fed(meetings: int = 3, fetch=None) -> dict:
    from .market_data import fed_odds
    rows = (fetch or fed_odds.fed_odds)(meetings)
    bad = [r for r in rows if r.get("meeting") is None]
    if bad and len(bad) == len(rows):
        return {"error": bad[0]["outcome"]}
    return {"meetings": fed_rows(rows), "source": "Kalshi prediction market (public prices)",
            "note": "market_odds = the price of a YES contract (0-1), what traders are paying, not a forecast by "
                    "BotScope. Can differ from CME FedWatch. Information only."}


# ---------- yield curve + economic data (FRED) ----------
TENORS = [("1 mo", "DGS1MO"), ("3 mo", "DGS3MO"), ("6 mo", "DGS6MO"), ("1 yr", "DGS1"), ("2 yr", "DGS2"),
          ("5 yr", "DGS5"), ("10 yr", "DGS10"), ("30 yr", "DGS30")]


def curve_rows(series: dict[str, list[tuple[str, float]]]) -> dict:
    """series: {fred_id: [(date, value), ... newest first, ~25 business days]}."""
    pts = []
    for label, sid in TENORS:
        obs = series.get(sid) or []
        if obs:
            ago = obs[min(len(obs) - 1, 21)]          # about a month of business days back
            pts.append({"tenor": label, "fred_id": sid, "yield": obs[0][1], "as_of": obs[0][0],
                        "month_ago": ago[1], "change": round(obs[0][1] - ago[1], 2)})
    y = {p["fred_id"]: p["yield"] for p in pts}
    spreads = {}
    if "DGS10" in y and "DGS3MO" in y:
        spreads["10yr minus 3mo"] = round(y["DGS10"] - y["DGS3MO"], 2)
    if "DGS10" in y and "DGS2" in y:
        spreads["10yr minus 2yr"] = round(y["DGS10"] - y["DGS2"], 2)
    inv = [k for k, v in spreads.items() if v < 0]
    return {"curve": pts, "spreads": spreads,
            "shape": "inverted (" + ", ".join(inv) + " below zero)" if inv else "normal (longer bonds pay more)" if spreads else None}


def yields(fetch=None) -> dict:
    from .market_data import fred_econ
    get = fetch or (lambda sid: fred_econ.series(sid, n=25))
    return curve_rows({sid: get(sid) for _, sid in TENORS}) | {
        "source": "FRED (US Treasury constant-maturity yields, daily)",
        "note": "Percent per year. An inverted curve has often come before recessions, but not on a schedule. "
                "Information only."}


def econ(fetch=None) -> dict:
    from .market_data import fred_econ
    return {"indicators": (fetch or fred_econ.latest)(), "source": "FRED (released numbers only, no forecasts)",
            "note": "Actual released numbers. Information only."}


# ---------- stock panels: short interest, analysts, insiders + filings, options ----------
def short_interest(symbol: str, fetch=None) -> dict:
    from .market_data import finra_short
    rows = (fetch or finra_short.short_interest)(symbol.upper())
    if not rows:
        return {"symbol": symbol.upper(), "reports": [], "source": "FINRA short interest",
                "note": "No FINRA report found (FINRA covers exchange-listed and OTC stocks twice a month)."}
    last = rows[0]
    trend = None
    if len(rows) >= 2 and rows[1]["short_shares"]:
        ch = (last["short_shares"] / rows[1]["short_shares"] - 1) * 100
        trend = f"{'up' if ch > 0 else 'down'} {abs(ch):.1f}% since the report before"
    return {"symbol": symbol.upper(), "latest": last, "trend": trend, "reports": rows[:6],
            "source": "FINRA consolidated short interest (twice a month, about a week late)",
            "note": "days_to_cover = short shares / average daily volume. High short interest is not a signal by "
                    "itself. Information only."}


def analyst_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        tot = r["strong_buy"] + r["buy"] + r["hold"] + r["sell"] + r["strong_sell"]
        out.append(r | {"total": tot, "buy_side": r["strong_buy"] + r["buy"], "sell_side": r["sell"] + r["strong_sell"]})
    return out


def analysts(symbol: str, fetch=None) -> dict:
    from .market_data import analyst
    rows = analyst_rows((fetch or analyst.recommendations)(symbol.upper(), 4))
    trend = None
    if len(rows) >= 2 and rows[0]["total"] and rows[-1]["total"]:
        a, b = rows[0]["buy_side"] / rows[0]["total"], rows[-1]["buy_side"] / rows[-1]["total"]
        trend = "more analysts saying buy than before" if a > b + 0.02 else \
            "fewer analysts saying buy than before" if a < b - 0.02 else "about the same as before"
    return {"symbol": symbol.upper(), "months": rows, "trend": trend,
            "source": "Finnhub analyst recommendation counts (monthly)",
            "note": "Counts of analyst ratings, not price targets. Analysts are often late and rarely say sell. "
                    "Information only."}


FORM4_CODES = {"P": "bought (open market)", "S": "sold (open market)", "A": "award / grant", "M": "option exercise",
               "F": "shares withheld for taxes", "G": "gift", "D": "returned to company", "C": "conversion"}


def parse_form4(xml_text: str) -> list[dict]:
    """Rows from one Form 4 XML: who, role, date, code, shares, price, bought or sold."""
    import xml.etree.ElementTree as ET_
    root = ET_.fromstring(xml_text)
    v = lambda el, path: (el.findtext(path + "/value") or el.findtext(path) or "").strip()   # noqa: E731
    name = root.findtext("reportingOwner/reportingOwnerId/rptOwnerName") or ""
    rel = root.find("reportingOwner/reportingOwnerRelationship")
    role = ""
    if rel is not None:
        role = (rel.findtext("officerTitle") or "").strip() or ("director" if rel.findtext("isDirector") in ("1", "true")
                                                                 else "10% owner" if rel.findtext("isTenPercentOwner") in ("1", "true") else "")
    out = []
    for t in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = (t.findtext("transactionCoding/transactionCode") or "").strip()
        shares = float(v(t, "transactionAmounts/transactionShares") or 0)
        price = float(v(t, "transactionAmounts/transactionPricePerShare") or 0)
        out.append({"insider": name.title(), "role": role, "date": v(t, "transactionDate"), "code": code,
                    "what": FORM4_CODES.get(code, code), "shares": shares, "price": price,
                    "value_usd": round(shares * price, 2), "in_or_out": v(t, "transactionAmounts/transactionAcquiredDisposedCode")})
    return out


def insider_summary(rows: list[dict]) -> dict:
    buys = [r for r in rows if r["code"] == "P"]
    sells = [r for r in rows if r["code"] == "S"]
    return {"open_market_buys": len(buys), "bought_usd": round(sum(r["value_usd"] for r in buys)),
            "open_market_sells": len(sells), "sold_usd": round(sum(r["value_usd"] for r in sells))}


def insiders(symbol: str, days: int = 90, max_filings: int = 15, fetch_json=None, fetch_text=None) -> dict:
    """Form 4 insider trades + recent 8-K filings from SEC EDGAR (needs SEC_USER_AGENT in your .env)."""
    from datetime import date, timedelta
    from .market_data import _http, sec_edgar
    gj = fetch_json or (lambda url: _http.get(url, ttl=3600))
    gt = fetch_text or (lambda url: _http.get(url, ttl=7 * 86400, raw=True))
    ciks = (lambda: {k: v for k, v in sec_edgar._cik_map().items()}) if fetch_json is None else \
        (lambda: {r["ticker"].upper(): int(r["cik_str"]) for r in gj("https://www.sec.gov/files/company_tickers.json").values()})
    cik = ciks().get(symbol.upper().replace(".", "-"))
    if not cik:
        return {"error": f"{symbol.upper()} not found in SEC's ticker list"}
    rec = gj(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")["filings"]["recent"]
    since = (date.today() - timedelta(days=days)).isoformat()
    trades, eights, n4 = [], [], 0
    for i, form in enumerate(rec["form"]):
        if rec["filingDate"][i] < since:
            continue
        acc = rec["accessionNumber"][i].replace("-", "")
        doc = rec["primaryDocument"][i]
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
        if form == "4" and n4 < max_filings:
            n4 += 1
            raw = doc.split("/")[-1]                     # the XML itself, not the styled page
            try:
                for t in parse_form4(gt(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{raw}")):
                    trades.append(t | {"filed": rec["filingDate"][i], "url": url})
            except Exception:
                continue
        elif form == "8-K" and len(eights) < 10:
            eights.append({"filed": rec["filingDate"][i], "items": rec["items"][i], "url": url})
    trades.sort(key=lambda r: r["date"], reverse=True)
    return {"symbol": symbol.upper(), "days": days, "summary": insider_summary(trades), "trades": trades[:30],
            "filings_8k": eights, "source": "SEC EDGAR (Form 4 insider filings, 8-K event filings)",
            "note": "Most insider sales are planned in advance or for taxes; open-market buys are rarer. 8-K items: "
                    "2.02 = results, 5.02 = executive change, 1.01 = big agreement, 8.01 = other news. "
                    "Information only."}


def occ(symbol: str) -> dict:
    """Parse an OCC option symbol like AAPL261021P00365000."""
    m = re.match(r"^([A-Z.]+?)(\d{6})([CP])(\d{8})$", symbol)
    if not m:
        raise ValueError(f"not an option symbol: {symbol}")
    d = m.group(2)
    return {"root": m.group(1), "expires": f"20{d[:2]}-{d[2:4]}-{d[4:]}", "type": "call" if m.group(3) == "C" else "put",
            "strike": int(m.group(4)) / 1000}


MAX_STRIKES = 12


def options_rows(chain: dict[str, dict], spot: float, width: float = 0.08) -> dict:
    """Nearest expiration, strikes within +/- width of the price, calls and puts side by side."""
    parsed = []
    for sym, snap in chain.items():
        try:
            o = occ(sym)
        except ValueError:
            continue
        q, g = snap.get("latest_quote") or {}, snap.get("greeks") or {}
        parsed.append(o | {"bid": q.get("bid_price"), "ask": q.get("ask_price"), "iv": snap.get("implied_volatility"),
                           "delta": g.get("delta")})
    if not parsed:
        return {"expires": None, "rows": []}
    exp = min(p["expires"] for p in parsed)
    near = [p for p in parsed if p["expires"] == exp and abs(p["strike"] / spot - 1) <= width]
    strikes = sorted({p["strike"] for p in near})
    rows = []
    for k in strikes:
        c = next((p for p in near if p["strike"] == k and p["type"] == "call"), {})
        pu = next((p for p in near if p["strike"] == k and p["type"] == "put"), {})
        rows.append({"strike": k, "call_bid": c.get("bid"), "call_ask": c.get("ask"), "call_iv": c.get("iv"),
                     "call_delta": c.get("delta"), "put_bid": pu.get("bid"), "put_ask": pu.get("ask"),
                     "put_iv": pu.get("iv"), "put_delta": pu.get("delta")})
    if len(rows) > MAX_STRIKES:                          # keep the strikes closest to the price
        keep = sorted(rows, key=lambda r: abs(r["strike"] - spot))[:MAX_STRIKES]
        rows = sorted(keep, key=lambda r: r["strike"])
    atm = min(rows, key=lambda r: abs(r["strike"] - spot)) if rows else None
    ivs = [x for x in ((atm or {}).get("call_iv"), (atm or {}).get("put_iv")) if x]
    move = round(spot * (sum(ivs) / len(ivs)) * ((max(1, _days_to(exp)) / 365) ** 0.5), 2) if ivs else None
    return {"expires": exp, "spot": spot, "rows": rows, "expected_move_usd": move}


def _days_to(d: str) -> int:
    from datetime import date
    return (date.fromisoformat(d) - date.today()).days


def options_board(symbol: str, chain=None, spot=None) -> dict:
    sym = symbol.upper()
    if chain is None:
        from datetime import date, timedelta
        from alpaca.data.historical.option import OptionHistoricalDataClient
        from alpaca.data.requests import OptionChainRequest
        c = OptionHistoricalDataClient(*alpaca_keys())
        raw = c.get_option_chain(OptionChainRequest(underlying_symbol=sym, expiration_date_gte=date.today(),
                                                    expiration_date_lte=date.today() + timedelta(days=14)))
        chain = {k: v.model_dump() for k, v in raw.items()}
    if spot is None:
        spot = _snapshots([sym])[sym][0]
    return {"symbol": sym} | options_rows(chain, spot) | {
        "source": "Alpaca options (indicative feed, free: delayed and approximate quotes and greeks)",
        "note": "expected_move_usd = price x at-the-money implied volatility x sqrt(days/365): about a one-standard-"
                "deviation move by expiration that the options are pricing in, not a forecast. Information only."}


# ---------- calendar ----------
_cal_cache: dict = {}


def calendar(days: int = 14, fetch=None) -> dict:
    """Upcoming events grouped by day (cached for an hour in this process)."""
    import time
    from .market_data import market_calendar
    key = days
    hit = _cal_cache.get(key)
    if fetch is None and hit and time.time() - hit[0] < 3600:
        rows = hit[1]
    else:
        rows = (fetch or market_calendar.upcoming)(days)
        if fetch is None:
            _cal_cache[key] = (time.time(), rows)
    by_day, problems = {}, []
    for r in rows:
        if r.get("date") is None:
            problems.append(f"{r['source']}: {r['event']}")
            continue
        by_day.setdefault(r["date"], []).append({"event": r["event"], "source": r["source"]})
    return {"days": [{"date": d, "events": ev} for d, ev in sorted(by_day.items())], "problems": problems,
            "source": "Alpaca, Kalshi, FRED, Finnhub (each event names its own)",
            "note": "Earnings only for market movers (the 10 biggest companies by market cap, bellwethers) and your "
                    "bots' tickers. Information only."}


def events_on(day: str) -> list[dict]:
    """Events on one day (for chart warnings). Empty for past days or if the calendar is unavailable."""
    from datetime import date, timedelta
    try:
        d = date.fromisoformat(day)
        if not date.today() <= d <= date.today() + timedelta(days=13):
            return []
        return next((x["events"] for x in calendar(14)["days"] if x["date"] == day), [])
    except Exception:
        return []


# ---------- one entry point for the page ----------
def _last_paper(bid: str) -> dict | None:
    """The bot's newest paper day: {day, r, trades}, or None before its first paper trade."""
    from . import journal
    rows = journal.find("paper_results", bot=bid)
    if not rows:
        return None
    day = max(r["day"] for r in rows)
    rs = [r["r"] for r in rows if r["day"] == day]
    return {"day": day, "r": round(sum(rs), 2), "trades": len(rs)}


def my_bots() -> dict:
    """One row per bot for the desk's "My bots" panel: links to its chart, label and rule playground."""
    from . import confidence, loader, report
    bots, errors = loader.load_all()
    return {"bots": [{"id": b, "name": c.name, "version": c.version, "timeframe": c.timeframe, "status": c.status,
                      "symbol": (c.symbols or ["SPY"])[0], "confidence": confidence.for_bot(b)["level"],
                      "shadows": c.shadows, "last_paper": _last_paper(b),
                      "changed_since_report": report.changed_since(c)} for b, c in bots.items()],
            "files_with_errors": [e["file"] for e in errors]}


def panel(name: str, q: dict | None = None) -> dict:
    """Page/API entry: one panel by name. Errors come back as {"error"} so one broken source never blanks the page."""
    q = q or {}
    sym = [x.strip().upper() for x in (q.get("symbols") or "").split(",") if x.strip()] or None
    one = re.sub(r"[^A-Z.]", "", (q.get("symbol") or "AAPL").upper())[:10] or "AAPL"
    fns = {"board": lambda: market_board(), "movers": lambda: movers(), "news": lambda: news(sym),
           "fed": lambda: fed(), "yields": lambda: yields(), "econ": lambda: econ(),
           "short": lambda: short_interest(one), "analysts": lambda: analysts(one),
           "insiders": lambda: insiders(one), "options": lambda: options_board(one),
           "risk": lambda: __import__("botscope.risk", fromlist=["x"]).portfolio_risk(),
           "calendar": lambda: calendar(14), "brief": lambda: __import__("botscope.brief", fromlist=["x"]).brief(),
           "keydates": lambda: __import__("botscope.keydates", fromlist=["x"]).key_dates(one)
           | {"bots": list(__import__("botscope.loader", fromlist=["x"]).load_all()[0])},
           "mybots": my_bots,
           "budget": lambda: __import__("botscope.loss_budget", fromlist=["x"]).status(),
           "autopsy": lambda: __import__("botscope.autopsy", fromlist=["x"]).autopsy(),
           "shadow": lambda: __import__("botscope.shadow", fromlist=["x"]).scoreboard(),
           "weather": lambda: __import__("botscope.weather", fromlist=["x"]).market_weather()}
    if name not in fns:
        return {"error": f"no panel {name!r}"}
    from . import demo
    if demo.active() and name in demo.NEEDS_REAL_DATA:
        return demo.needs_real_data(name)
    try:
        return demo.label(fns[name]())
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:200]}"}
