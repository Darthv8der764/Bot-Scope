---
name: botscope-auto-setup
description: Bring someone's existing trading bot (their code and/or trade logs) into BotScope - read it without running it, write the standard bot file, list what was and wasn't translated, then check it and run the honest test. Use when a newcomer says "set up my bot", "import my strategy code", "here's my bot folder" or "use my trade log".
---

# Auto setup for an existing bot

Read-only and paper only: never run the newcomer's code, never place an order. Not financial advice.

1. `auto_setup(how="scan", path=...)` on their bot file or folder. It reads (never runs) the code and trade logs and
   returns hints: symbols, timeframe, indicators, stop/target hints, order calls, and a column mapping per trade log.
   Show the hints as a short table and say they are guesses from the text.
2. Pine Script? Use `import_pine` with the script's text instead of writing the bot by hand.
3. Otherwise read the code yourself (it is the source of truth; the hints only point the way), `save_checkpoint`,
   then `new_bot` and fill in the file the botscope-new-bot way: every Entry has a stop, every NoTrade a reason,
   every number in `params`, `rules` in plain English matching the code, `status = "untested"`, `tuned_on = None`.
   Keep three lists while you write: translated (rule by rule), not translated (anything BotScope can't express:
   options legs, scaling in, news, order types, outside data) and added by BotScope (e.g. a stop the original
   didn't have, closing at the bell).
4. Trade logs: `import_my_bots(how="file", path=..., mapping=...)` with the scan's mapping (fix any column it
   guessed wrong), `link_to` the new bot id so trades with an R count as live evidence.
5. `auto_setup(how="finish", bot=..., path=..., translated=[...], not_translated=[...], added=[...])`: it runs
   check_bot and returns the mapping report. Show "Not translated" first, then the failing checks.
6. `honest_report` on the new bot. Say which numbers are from TUNED years and which from UNTESTED years, name the
   data source, and remind them the BotScope copy is only as faithful as the translation.
