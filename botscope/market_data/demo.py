"""One live call per source, short sample of each (.venv/bin/python -m botscope.market_data.demo). Information only."""
import json
import sys

from botscope.market_data import analyst, calendars, fed_odds, finra_short, fred_econ, price_feed, sec_edgar
from botscope.market_data import bot_tickers as local_tickers


def show(title, fn):
    try:
        rows = fn()
    except Exception as e:
        rows = [{"error": str(e)}]
    print(f"\n## {title}")
    for r in (rows if isinstance(rows, list) else [rows])[:6]:
        print(json.dumps(r, default=str))


if __name__ == "__main__":
    bots = local_tickers.bot_tickers()
    print("bot tickers:", len(bots), bots[:12])
    show("1 Fed odds", lambda: fed_odds.fed_odds(1))
    show("2 Price feed", lambda: [{"use": k, **v} for k, v in price_feed.describe().items()])
    show("3 FINRA short interest AAPL", lambda: finra_short.short_interest("AAPL"))
    show("4 Analyst trends NVDA", lambda: analyst.recommendations("NVDA"))
    show("5a SEC full text 'guidance' 8-K", lambda: sec_edgar.full_text_search("guidance", days=14))
    show("5b New 8-Ks for bot tickers", lambda: sec_edgar.recent_8ks(bots, days=7))
    show("6 FRED actuals", fred_econ.latest)
    show("7a Earnings (movers)", lambda: calendars.earnings(14, extra=bots))
    show("7b IPOs", lambda: calendars.ipos(30))
    sys.exit(0)
