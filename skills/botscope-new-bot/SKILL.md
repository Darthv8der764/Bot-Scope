---
name: botscope-new-bot
description: Write a new BotScope bot from a plain-English idea - the one-class bot format, rules that match the code, near misses, and the first honest test. Use when the user says "make a bot that...", "turn this strategy into a bot", or "add a bot".
---

# A new bot in the BotScope format

1. `save_checkpoint` ("before adding <name>").
2. `new_bot` with a name, a 1-2 sentence description, timeframe and symbols: it writes a starter file in the bots
   folder from the template. Then fill in `indicators()`, `entry()` and `exit()` (see `botscope/bot.py`):
   - No peeking: only `view.bars` (finished bars). Every Entry has a stop. Every NoTrade has a plain reason.
   - Put every tunable number in `params`. Write `rules` in plain English, one per line, matching the code.
   - Optional near misses: `NoTrade("range too narrow", almost=Entry(...))` shows ghost trades.
   - `status = "untested"`, `tuned_on = None` until settings are picked on a date range.
   - Daily bots that look far back (a 200-day average, a 50-day high): set `lookback_days` to that many trading days,
     so every backtest fetches enough earlier days. `check_bot` flags a long `*_days` setting without it.
   - Crypto: symbols like `BTC/USD` with `asset = "crypto"` trade every day (keyless Alpaca crypto history, from 2021).
   - Have a TradingView strategy? `import_pine` translates the common subset into a bot file and lists every line it
     couldn't translate (say them all). It fills at the signal bar's close, so results can differ a little from TradingView.
   - Options: bots don't trade options; `option_spread_plan` turns a bot's signal into a defined-risk debit spread plan
     (max loss, max gain, breakeven), paper only and not backtested.
3. `check_bot` - loads it, runs the no-peek check and the rules-vs-params check on made-up bars.
4. `run_backtest`, then `honest_report` (see the botscope-honest-test skill). Paper only. Not financial advice.
