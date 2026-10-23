---
name: botscope-honest-test
description: How to judge a trading bot honestly with BotScope - tuned vs untested years, costs, luck, crashes, ghosts, and the nutrition label. Use when the user asks "is my bot any good", "test this bot", "backtest", "should I trust it", or wants to compare settings.
---

# Honest test of a bot

Rules: never a made-up number, never a win-rate promise, confidence levels instead of percentages, always say which
numbers are TUNED (settings picked there) and which are UNTESTED (the real test). Not financial advice.

1. Quick look: `run_backtest` (tuned month vs untested month). Say it is noisy.
2. Full test: `honest_report` (every year since 2016). Show the headline, a by-year table with tuned rows marked,
   and costs taken (`costs_r`). Point out losing untested years.
3. Luck: `luck_meter`. Say "beat N of 100 random twins" and the level.
4. Crashes: the `crashes` part of the report (2008 is NOT tested: data starts in 2016; never guess it).
   If the headline has the ⚠ tight-stop warning, say it first: R per trade is inflated, judge by dollars.
   If the report has `warming_up_note`, say it: those years have fewer trades because the bot's lookback was still filling.
5. Near misses: if ghosts made money, the bot's filter may be costing money; if they lost, the filter helps.
6. Robustness: `robustness_check` runs the strategy factory's whole checklist on this bot (doubled costs, without
   its 3 best trades, stops wider than their costs, later years, settings 20% smaller and bigger, luck), every check pass/fail, plus a held-out
   year that none of those checks saw. Each failure is a caution, not a verdict on its own.
7. Crypto-only bots: the report starts when the crypto data does (Alpaca: 2021) and also says whether the bot beat
   just holding BTC (`vs_btc`), next to SPY. Show both lines.
8. Wrap up with `nutrition_label` (show its markdown) and the confidence level with its reasons.

Trying changed settings: run `run_backtest` once without and once with `params` (or `filters`), show before/after
on UNTESTED days. Nothing changes in the bot unless the user approves; save a checkpoint first (`save_checkpoint`).

Best settings? `honest_optimizer` (heavy: minutes) makes a heat map of two settings on untested years up to a year
ago. Say the verdict, the best vs middle cell, plateau or island, and the held-out year. A better cell is a lead to
test with `make_shadow`, never a switch. If it says `tries_across_runs`, repeat it: more tries, more luck.

All the bots together: `team_report` (combined result, team worst drop, bots that are mostly one bet).
To share a result: `export_report_page` saves one local HTML file (no keys, no account); it is never uploaded.
Publishing it anywhere is the user's own step.

Which rules matter? `rule_playground` (give the page link). Every mix tried counts as a setting tried on the same
untested days: repeat its warning. A rule whose blocked trades made money is a lead, not a fix: test it with
`make_shadow` (a copy without the rule) on paper and on other days. `event_days` shows CPI / jobs / opex days vs
ordinary days (no verdict under 10 trades).

A quick market question with no bot ("how did buying SPY on red Mondays do?"): `ask_market_question`. Show
`understood_as` first so the user can correct it, then untested vs tuned numbers (the last 12 months count as
tuned unless the idea came from elsewhere), vs SPY and the confidence level. Repeat `questions_note` when it's there.
