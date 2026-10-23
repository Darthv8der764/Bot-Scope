# When R lies: stops a few cents from the entry

BotScope reports results in **R**: each trade's profit or loss divided by its risk (the distance from the entry to
the stop). R lets you compare a $20 stock with a $500 one. But R has a weak spot. When the stop sits a few cents from
the entry, the risk is tiny, so any normal move becomes a huge number of R.

## A real example

A Pine Script strategy imported on 2026-10-17 (an RSI dip in an uptrend, stop at `ta.lowest(low, 5)`), tested on
SPY / QQQ / IWM daily candles from Alpaca SIP:

| Trade | Entry | Stop | Risk | Exit | Result |
|---|---|---|---|---|---|
| QQQ, 2023-04-25 | $309.99 | $309.89 | $0.10 | $322.56 | **+122.6R** |
| IWM, 2023-08-17 | $183.65 | $183.63 | $0.02 | $182.12 | **-85.7R** |

The 5-day low included the signal day's own low. On days that closed near their low, the stop landed a few cents
under the entry.

- **The win:** QQQ rose 4%. A normal good trade, but divided by a $0.10 risk it reads +122.6R.
- **The loss:** the next day IWM opened at $182.21, below the stop, so the stop filled at that open (plus the stop's
  extra cost): $1.53 under the entry, about 77 times the planned $0.02 risk. Tight stops get jumped like this all
  the time.
- **Costs:** BotScope's swing cost is 0.05% each way, about $0.31 a round trip on QQQ. That's 3R of costs on a
  $0.10 risk before the price moves at all.

Over its untested years the bot read **+590.8R** while making only **+$2,285** on $10,000 a trade. It lost money in
6 of 11 years and trailed just holding SPY (+$15,141). Its 54 tight-stop trades made the R total. Without them it was
**-81.4R**.

## What BotScope does about it

- A trade counts as "tight" when its stop is closer than its own trading costs, or under 0.05% of the price.
- The backtest counts them (`tight_stop_trades`) and shows the total without them (`without_tight_stops_r`).
- If 3 or more trades, and 5% or more of all trades, are tight, or the tight ones move the total by 10R or more, the
  honest report's headline and `run_backtest` warn you. Judge that bot by dollars, not R.
- The strategy factory drops such a candidate ("R can't be trusted"). `robustness_check` fails its "stops wider than
  costs" check.

## What to do with your bot

Put the stop where the idea is wrong, not where it is closest. The same strategy, three stops (untested years, same
data):

| Stop | R total | Dollars ($10k a trade) | Tight-stop trades |
|---|---|---|---|
| `ta.lowest(low, 5)` (includes the signal candle) | +590.8R | +$2,285 | 54 |
| `ta.lowest(low, 5)[1]` (leaves it out) | -474.5R | +$12,413 | 11, one of them -464R |
| `close - 2 * ta.atr(14)` (a distance from the usual range) | +33.8R | +$10,202 | 0 |

Leaving the signal candle out isn't enough: after a dip, the earlier lows can still sit a cent under the close (or
above it, and then BotScope rejects the entry). A distance from the usual daily range keeps every stop wide, and then
R and dollars tell the same story. Here that story is modest: +0.18R a trade, and less than just holding SPY
(+$15,141).

BotScope's Pine import warns when a stop is the lowest low or highest high of a window that includes the signal
candle. Run the honest report again after any stop change: if the edge was only tiny risk turned into big R, it will
be gone, and that is worth knowing before any paper trade.

Not financial advice. Past results, even honest ones, don't predict the future.
