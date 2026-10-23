"""Offline checks of the market desk panels (made-up data, no network)."""
from botscope import desk


def snaps(chg: dict):
    out = {s: (100 * (1 + c / 100), 100.0) for s, c in chg.items()}
    return out


def test_board_sorts_sectors_and_compares_to_spy():
    chg = {"SPY": 1.0, "QQQ": 1.5, **{s: (i - 5) * 0.5 for i, s in enumerate(desk.SECTORS)}}
    b = desk.market_board(snapshots=lambda syms: snaps(chg))
    sec = b["sectors"]
    assert sec[0]["change_pct"] >= sec[-1]["change_pct"] and sec[0]["vs_spy"] == round(sec[0]["change_pct"] - 1.0, 2)
    assert b["missing"] == ["DIA", "IWM"] and b["mood"] == "mixed" and "IEX" in b["source"]


def test_mood_needs_breadth():
    up = desk.board_rows(snaps({s: 1.0 for s in desk.SECTORS}))
    assert up["mood"] == "broad rally" and up["sectors_up"] == 11


def test_movers_drop_pennies_warrants_and_units():
    assert desk.is_plain_stock("NVDA") and desk.is_plain_stock("FMC")
    for junk in ("SEATW", "PAII.WS", "BCAT.RT", "ABCDU", "BRK.B", "FBYDP"):
        assert not desk.is_plain_stock(junk), junk
    g = [{"symbol": "SEATW", "price": 0.02, "percent_change": 500}, {"symbol": "ESLA", "price": 0.53, "percent_change": 68},
         {"symbol": "BETR", "price": 10.76, "percent_change": 32.51}]
    a = [{"symbol": "SDST", "volume": 1e9, "trade_count": 5}, {"symbol": "INTC", "volume": 1e8, "trade_count": 9}]
    out = desk.mover_rows(g, [], a, {"SDST": 0.4, "INTC": 95.0})
    assert [r["symbol"] for r in out["gainers"]] == ["BETR"] and [r["symbol"] for r in out["most_active"]] == ["INTC"]


def test_one_line_takes_the_first_sentence_and_cuts():
    assert desk.one_line("<p>Shares rose after earnings beat. More text here.</p>") == "Shares rose after earnings beat."
    long = "word " * 60
    out = desk.one_line(long)
    assert len(out) <= 140 and out.endswith("…")
    assert desk.one_line("") == "" and desk.one_line("PPI Spikes Please click here for a chart") == ""
    assert desk._et("2026-10-15T18:56:27Z") == "2026-10-15 14:56"


def test_news_dedupes_and_sorts_newest_first():
    items = [{"headline": "A", "created_at": "2026-10-15T10:00", "symbols": ["AAPL"], "summary": "x", "source": "b", "url": "u"},
             {"headline": "B", "created_at": "2026-10-15T12:00", "symbols": ["NVDA"], "summary": "", "source": "b", "url": "u"},
             {"headline": "a", "created_at": "2026-10-15T09:00", "symbols": ["AAPL"], "summary": "", "source": "b", "url": "u"}]
    out = desk.news(["aapl"], fetch=lambda syms: items)
    assert [n["headline"] for n in out["news"]] == ["B", "A"] and out["tickers"] == ["AAPL"]


def test_fed_groups_meetings_most_likely_first():
    rows = [{"source": "Kalshi", "meeting": "2026-12-09", "outcome": "Hold", "prob": 0.2},
            {"source": "Kalshi", "meeting": "2026-12-09", "outcome": "Hike 25bps", "prob": 0.7},
            {"source": "Kalshi", "meeting": "2026-10-28", "outcome": "Hold", "prob": 0.9}]
    out = desk.fed(fetch=lambda n: rows)
    assert [m["meeting"] for m in out["meetings"]] == ["2026-10-28", "2026-12-09"]
    assert out["meetings"][1]["most_likely"] == "Hike 25bps" and "not a forecast" in out["note"]
    assert "error" in desk.fed(fetch=lambda n: [{"meeting": None, "outcome": "unavailable: x", "prob": None}])


def test_yield_curve_shape_and_change():
    def fake(sid):
        base = {"DGS1MO": 4.3, "DGS3MO": 4.28, "DGS6MO": 4.2, "DGS1": 4.1, "DGS2": 4.0, "DGS5": 4.3, "DGS10": 5.19, "DGS30": 5.5}[sid]
        return [(f"2026-10-{14 - i:02d}", round(base - 0.01 * i, 2)) for i in range(25)]
    out = desk.yields(fetch=fake)
    assert out["shape"].startswith("normal") and out["spreads"]["10yr minus 3mo"] == 0.91
    assert out["curve"][0]["change"] == 0.21
    inv = desk.curve_rows({"DGS3MO": [("d", 5.0)], "DGS10": [("d", 4.0)], "DGS2": [("d", 4.5)]})
    assert inv["shape"].startswith("inverted")


FORM4 = """<?xml version="1.0"?><ownershipDocument>
<reportingOwner><reportingOwnerId><rptOwnerName>COOK TIMOTHY D</rptOwnerName></reportingOwnerId>
<reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>1</isOfficer><officerTitle>Chief Executive Officer</officerTitle></reportingOwnerRelationship></reportingOwner>
<nonDerivativeTable>
<nonDerivativeTransaction><transactionDate><value>2026-10-01</value></transactionDate><transactionCoding><transactionCode>S</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>1000</value></transactionShares><transactionPricePerShare><value>250.5</value></transactionPricePerShare>
<transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode></transactionAmounts></nonDerivativeTransaction>
<nonDerivativeTransaction><transactionDate><value>2026-10-02</value></transactionDate><transactionCoding><transactionCode>P</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>10</value></transactionShares><transactionPricePerShare><value>240</value></transactionPricePerShare>
<transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts></nonDerivativeTransaction>
</nonDerivativeTable></ownershipDocument>"""


def test_form4_parse_and_summary():
    rows = desk.parse_form4(FORM4)
    assert rows[0]["insider"] == "Cook Timothy D" and rows[0]["role"] == "Chief Executive Officer"
    assert rows[0]["what"] == "sold (open market)" and rows[0]["value_usd"] == 250500
    s = desk.insider_summary(rows)
    assert s == {"open_market_buys": 1, "bought_usd": 2400, "open_market_sells": 1, "sold_usd": 250500}


def test_insiders_reads_form4_xml_not_the_styled_page():
    from datetime import date
    today = date.today().isoformat()
    sub = {"filings": {"recent": {"form": ["4", "8-K", "10-Q"], "filingDate": [today] * 3,
                                  "accessionNumber": ["0001-26-000001", "0001-26-000002", "0001-26-000003"],
                                  "primaryDocument": ["xslF345X05/wk-form4.xml", "aapl-8k.htm", "q.htm"],
                                  "items": ["", "2.02,9.01", ""]}}}
    asked = []
    js = lambda url: {"0": {"ticker": "AAPL", "cik_str": 320193}} if "company_tickers" in url else sub   # noqa: E731
    out = desk.insiders("aapl", fetch_json=js, fetch_text=lambda url: asked.append(url) or FORM4)
    assert asked[0].endswith("/000126000001/wk-form4.xml") and "xsl" not in asked[0]
    assert out["summary"]["open_market_sells"] == 1 and out["filings_8k"][0]["items"] == "2.02,9.01"
    assert "error" in desk.insiders("ZZZZ", fetch_json=js, fetch_text=lambda u: FORM4)


def test_options_board_near_the_money_and_expected_move():
    assert desk.occ("AAPL261021P00365000") == {"root": "AAPL", "expires": "2026-10-21", "type": "put", "strike": 365.0}
    q = lambda b, a: {"bid_price": b, "ask_price": a}   # noqa: E731
    chain = {"AAPL991217C00100000": {"latest_quote": q(5, 5.2), "implied_volatility": 0.3, "greeks": {"delta": 0.5}},
             "AAPL991217P00100000": {"latest_quote": q(4.8, 5), "implied_volatility": 0.3, "greeks": {"delta": -0.5}},
             "AAPL991217C00150000": {"latest_quote": q(0, 0.1), "implied_volatility": 0.5},
             "AAPL991231C00100000": {"latest_quote": q(9, 9.5), "implied_volatility": 0.3}}
    out = desk.options_board("aapl", chain=chain, spot=100.0)
    assert out["expires"] == "2099-12-17" and [r["strike"] for r in out["rows"]] == [100.0]
    assert out["rows"][0]["put_delta"] == -0.5 and out["expected_move_usd"] > 0


def test_short_interest_and_analyst_trends():
    rows = [{"symbol": "X", "settled": "2026-09-30", "short_shares": 110}, {"symbol": "X", "settled": "2026-09-15", "short_shares": 100}]
    assert desk.short_interest("x", fetch=lambda s: rows)["trend"] == "up 10.0% since the report before"
    rec = lambda sb, b, h: {"strong_buy": sb, "buy": b, "hold": h, "sell": 1, "strong_sell": 0}   # noqa: E731
    out = desk.analysts("x", fetch=lambda s, n: [rec(10, 20, 5), rec(5, 10, 20)])
    assert out["trend"] == "more analysts saying buy than before" and out["months"][0]["total"] == 36


def test_calendar_groups_by_day_and_lists_problems():
    rows = [{"date": "2026-10-16", "event": "Monthly options expiration", "source": "computed"},
            {"date": None, "event": "unavailable: no key", "source": "FRED"},
            {"date": "2026-10-16", "event": "CPI inflation (8:30 AM ET)", "source": "FRED"}]
    out = desk.calendar(14, fetch=lambda d: rows)
    assert out["days"] == [{"date": "2026-10-16", "events": [{"event": "Monthly options expiration", "source": "computed"},
                                                             {"event": "CPI inflation (8:30 AM ET)", "source": "FRED"}]}]
    assert out["problems"] == ["FRED: unavailable: no key"]
    assert desk.events_on("2020-01-01") == []


def test_dividends_and_splits_rows():
    from datetime import date
    from botscope.market_data import corporate
    data = {"cash_dividends": [{"symbol": "KO", "rate": 0.53, "ex_date": date(2026, 10, 20)},
                               {"symbol": "MSFT", "rate": 0.98, "ex_date": date(2027, 1, 1)}],
            "forward_splits": [{"symbol": "NVDA", "new_rate": 10, "old_rate": 1, "ex_date": date(2026, 10, 21)}]}
    out = corporate.rows_from(data, date(2026, 10, 15), date(2026, 11, 15))
    assert [r["event"] for r in out] == ["KO ex-dividend ($0.53/share)", "NVDA split 10-for-1"]


def test_desk_layout_controls_are_on_the_page():
    from pathlib import Path
    html = (Path(__file__).parent.parent / "botscope" / "web" / "desk.html").read_text()
    for bit in ('class="grip"', 'class="hbtn"', 'class="wbtn"', 'id="resetlayout"', "botscope-desk-layout-v1",
                'id: "weather"'):
        assert bit in html
    assert "try { localStorage.setItem" in html                  # storage off never breaks the page


def test_one_line_decodes_html_codes():
    assert desk.one_line("China&#39;s oil use is dropping fast &amp; EVs keep rising.") == \
        "China's oil use is dropping fast & EVs keep rising."


def test_board_labels_etfs_not_index_levels():
    b = desk.board_rows({"SPY": (773.24, 770.0), "QQQ": (600.0, 601.0)})
    names = {r["symbol"]: r["name"] for r in b["indexes"]}
    assert names["SPY"] == "SPY (tracks S&P 500)"
    assert all(n.startswith(s) for s, n in names.items())


def test_movers_leave_out_etfs_and_leveraged_single_stock_products():
    names = {"CRWU": "T-Rex 2X Long CRWV Daily Target ETF", "NBIL": "Neos Enhanced Income ETF",
             "CWVX": "Tradr 2X Long CRWV Daily ETF", "SQQQ": "ProShares UltraPro Short QQQ",
             "NVDA": "NVIDIA Corporation Common Stock", "BETR": "Better Home & Finance Holding Company Class A Common Stock"}
    for fund in ("CRWU", "NBIL", "CWVX", "SQQQ", "CRWG"):          # CRWG: not in the active list at all
        assert not desk.is_plain_stock(fund, names), fund
    assert desk.is_plain_stock("NVDA", names) and desk.is_plain_stock("BETR", names)
    lo = [{"symbol": "NBIL", "price": 12.0, "percent_change": -48}, {"symbol": "NVDA", "price": 180.0, "percent_change": -3}]
    assert [r["symbol"] for r in desk.mover_rows([], lo, [], {}, names=names)["losers"]] == ["NVDA"]


def test_movers_say_so_when_funds_cant_be_told_apart():
    class SC:
        def get_market_movers(self, req):
            return type("M", (), {"gainers": [], "losers": []})()
        def get_most_actives(self, req):
            return type("A", (), {"most_actives": []})()
    def no_names():
        raise ConnectionError("down")
    ok = desk.movers(screener=SC(), snapshots=lambda s: {}, asset_names=lambda: {"NVDA": "NVIDIA Corp"})
    bad = desk.movers(screener=SC(), snapshots=lambda s: {}, asset_names=no_names)
    assert "ETFs, ETNs, leveraged" in ok["filtered"] and "may show up" in bad["filtered"]


def test_movers_fill_up_from_the_most_active_stocks_when_the_top_50_are_mostly_etfs():
    funds = {f"ETF{i}": f"Fund {i} 2X Daily Target ETF" for i in range(50)}
    stocks = {f"S{i}": f"Stock {i} Inc Common Stock" for i in range(30)}
    names = funds | stocks
    asked = {}

    class SC:
        def get_market_movers(self, req):
            asked["movers"] = req.top
            rows = [{"symbol": s, "price": 20.0, "percent_change": 40.0} for s in funds]
            return type("M", (), {"gainers": rows[:25], "losers": [r | {"percent_change": -40.0} for r in rows[25:]]})()
        def get_most_actives(self, req):
            asked["actives"] = req.top
            return type("A", (), {"most_actives": [{"symbol": s, "volume": 1e6, "trade_count": 1} for s in stocks]})()
    snaps = {s: (100 + (i - 15), 100.0) for i, s in enumerate(stocks)}          # S0..S14 down, S16..S29 up
    out = desk.movers(screener=SC(), snapshots=lambda syms: {s: snaps[s] for s in syms}, asset_names=lambda: names)
    assert asked == {"movers": desk.MOVERS_MAX, "actives": desk.ACTIVES_MAX}
    assert len(out["gainers"]) == 10 and len(out["losers"]) == 10
    assert out["gainers"][0]["symbol"] == "S29" and out["losers"][0]["symbol"] == "S0"
    assert not any(r["symbol"].startswith("ETF") for r in out["gainers"] + out["losers"])
    assert "most active" in out["source"].split(" (")[0] and "left out" in out["filtered"]   # visible in the header


def test_my_bots_panel_lists_every_bot_with_its_confidence():
    from botscope import desk
    d = desk.panel("mybots")
    ids = {b["id"] for b in d["bots"]}
    assert {"first_hour_breakout", "nr7_swing"} <= ids and all(b["confidence"] for b in d["bots"])
    assert all(b["changed_since_report"] is False for b in d["bots"])     # no fingerprinted reports in a fresh journal
    assert "%" not in str(d)


def test_my_bots_last_paper_day():
    from botscope import desk, journal
    assert desk._last_paper("nr7_swing") is None
    for i, (day, r) in enumerate((("2026-10-14", 1.0), ("2026-10-15", -0.5), ("2026-10-15", -0.25))):
        journal.upsert("paper_results", {"bot": "nr7_swing", "symbol": "SPY", "day": day, "trade_id": str(i)}, {"r": r})
    assert desk._last_paper("nr7_swing") == {"day": "2026-10-15", "r": -0.75, "trades": 2}


def test_my_bots_last_paper_day_says_trades():
    from pathlib import Path
    html = (Path(__file__).resolve().parent.parent / "botscope/web/desk.html").read_text()
    assert '${r.last_paper.trades} trade${r.last_paper.trades === 1 ? "" : "s"}' in html
