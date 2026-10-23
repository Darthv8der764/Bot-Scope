---
name: botscope-daily
description: The daily BotScope routine - morning brief and pre-flight on/off list before the open, and the end-of-day paper log with loss autopsy and shadow scoreboard. Use when the user says "start my trading day", "morning brief", "pre-flight", "which bots today", "end of day", "why did it lose", or asks how their bots did today.
---

# BotScope daily routine

Paper trading by default. Not financial advice. Keep replies short: tables, not walls of text.

## Before the open (pre-flight)
0. `morning_brief` - show its 3 lines as they are (weather, today's events, what each bot that's on will watch).
1. `preflight_list` - show bots as a table: bot, red flags, confidence, on/off now. Red-flag bots first.
2. Mention today's events from the result (Fed, CPI, jobs, earnings of a bot ticker) in one line.
3. Ask ONE question: which bots should run today? Then `set_bots_on_off`.
   - No answer is fine: yesterday's settings carry over. A never-answered bot stays off.
4. If STOP is on, say so first and ask whether to `resume_trading` (only with a yes).

## During the day
- "STOP" / "pause everything" -> `stop_everything` at once, no questions.
- "Show me" -> `open_bot_view` and give the link.

- "Tell me when NVDA breaks yesterday's high" -> `add_alert` (plain English, info only); `check_alerts` checks the
  rules on finished candles, `list_alerts` / `remove_alert` manage them. Alerts go to the channels set in .env
  (ntfy, Discord, Telegram); `doctor` says which are on. Never echo a topic, webhook or token.

## After the close (after 16:00 New York)
1. `log_paper_results` - save today's closed paper trades.
2. For each bot that traded: `drift_alarm`. On "alarm", suggest switching it off tomorrow.
3. One small table: bot, trades today, R today, confidence. No percentages for confidence.
4. A bot lost today? `loss_autopsy` - its 4 checks as a table (market, costs, fills, normal or not), then the chart link.
5. Shadow versions running? `shadow_scoreboard` - one table per family; repeat its verdict (it won't pick a leader
   under 20 trades each).

## Now and then
- Fridays, or before updating or reinstalling BotScope: `backup_my_data` - say where the zip went (never has keys).
- "Put my paper trades in a spreadsheet" -> `export_paper_results`; say they're paper trades, not a backtest.
- A red flag says "changed since its report"? Offer `honest_report` for that bot (heavy: minutes) before trusting its label.
