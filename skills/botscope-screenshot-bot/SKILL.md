---
name: botscope-screenshot-bot
description: Turn a trade setup in a chart screenshot into a paper bot and test it honestly. Use when the user pastes a chart screenshot and says "make a bot from this", "turn this setup into a bot", "automate this", or "trade this pattern".
---

# Screenshot to bot

Paper only. Not financial advice.

1. Read the screenshot: ticker, timeframe, date, and the setup. Write the setup as numbers you can test, for
   example "close above the highest high of the last 20 bars, stop 1 ATR below, target 2x the risk". Anything
   you can't measure from the picture (indicator settings, the exact level), ask once or propose a number and say
   it's your guess. Never guess the ticker.
2. Optional first look: `screenshot_confidence` with the closest known setup, so the user sees how the plain
   version did before any code is written.
3. `save_checkpoint`, then `new_bot` (status "untested", tuned_on None) with the timeframe from the screenshot, and
   fill in the rules and `entry()` (see botscope-new-bot). `check_bot`.
4. `open_bot_view` on the screenshot's day: the bot should take the trade in the picture. If it doesn't, use
   `why_not_here` at that time and fix the rule, not the picture.
5. Honest test: `run_backtest`, `honest_report`, `luck_meter`. The screenshot's day is where the idea came from,
   so it proves nothing: only untested days count. Show "Beat just holding?" too.
6. Before it's shared anywhere, the honest bot gallery (`export_to_gallery`) packages it with its label.
