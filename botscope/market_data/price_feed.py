"""2. Price feed: no new source on purpose. This file only documents what the bots use (information only).

- Live bots: Alpaca IEX feed (free). IEX is one exchange, so its volume
  is ~2-3% of the whole market and quotes can be wider than the real national best bid/offer.
- Backtests: Alpaca SIP (all exchanges) is free for history older than 15 minutes, which is all a backtest needs.
  BotScope backtests default to SIP.
- The paid full real-time SIP feed (Algo Trader Plus) would fix live IEX gaps. Buying it is a parent decision;
  nothing here buys or switches anything."""

FEEDS = {
    "live": {"feed": "iex", "cost": "free", "delay": "real time", "coverage": "IEX exchange only (~2-3% of volume)"},
    "backtest": {"feed": "sip", "cost": "free", "delay": "15 min (history only)", "coverage": "all US exchanges",
                 "note": "BotScope run_backtest uses sip"},
    "paid_option": {"feed": "sip real time", "cost": "paid monthly plan", "decision": "parent", "status": "not bought"},
}


def describe():
    return FEEDS
