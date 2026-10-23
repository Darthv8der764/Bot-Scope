---
name: botscope-sketch
description: Turn a pattern the user drew on the BotScope chart (circles and lines with notes) into a paper bot and test it honestly. Use when the user says "I drew the setup", "make a bot from my drawing", "trade this pattern", or "find more of these".
---

# Sketch a strategy

Paper only. Not financial advice.

1. `get_chart_drawings` (for that bot, symbol and day if the user named them). For each drawing read the note, the
   time and price span, `candles_under` (open, close, high, low, count) and what the bot did there.
2. Say back, in 3-5 short lines, what the pattern seems to be in measurable terms, for example "a 20-30 minute
   range under 0.4% tall, then a close above its high before 11:00". Turn every fuzzy part into a number from the
   drawing (range height in %, length in candles, time of day, line slope) and put it in `params`. Ask the user to
   confirm or correct before writing code, unless they already said "just build it".
3. Where are the entry, the stop and the target? Use the user's lines when they drew them ("stop goes here" = a stop
   rule at that level relative to the pattern). If there is no stop anywhere, propose the pattern's opposite edge
   and say it's your guess.
4. `save_checkpoint`, `new_bot` (status "untested", tuned_on None), fill in the rules (see botscope-new-bot), and
   `check_bot`. Then `open_bot_view` on the drawn day: the bot should trade the drawn spot. If it doesn't,
   `why_not_here` at that time and fix the rule, not the drawing.
5. Honest test: `run_backtest`, then `honest_report`, `luck_meter`. One drawing is one example: say the numbers come
   from days the pattern was NOT picked on, and that a pattern that only shows up a handful of times can't be judged.
6. If the user drew several examples, use `what_if_stop_target` and `bot_arena` (two versions of the fuzzy number)
   rather than tuning on the drawn days.

Never present the drawn days' results as proof; they are where the idea came from (tuned by definition).
