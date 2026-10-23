---
name: botscope-strategy-factory
description: Turn a goal like "a calm daily ETF bot" into a few candidate bots, test each honestly, and keep only the survivors. Use when the user asks Claude to "find me a strategy", "make a bot that...", "what bot fits my goal", or wants several bot ideas compared honestly.
---

# Strategy factory

Rules: never a win %, never "guaranteed", confidence levels instead of percentages, every year here is UNTESTED
(the candidates use textbook settings never tuned on this data). Not financial advice.

1. Ask for the goal in one sentence if it isn't clear (timeframe, calm or not, ETFs or stocks, long only or both).
2. Run `strategy_factory(goal)`. It tries at most 5 candidates, one backtest at a time.
3. Show `understood.read_as` first and ask if it read the goal right; rerun with `symbols` or clearer words if not.
4. Show `markdown` as is: the ranked survivors (confidence, untested trades, per trade after costs, costs doubled,
   without the 3 best trades, settings ±20%, luck, vs holding SPY, held-out year) and every dropped candidate with
   its reason and, when there is one, the research note that explains it.
5. Say `tries_note` out loud: picking the best of several on the same years flatters the winner, and reruns on the
   same symbols add up (at 15+ candidates survivors drop one confidence level).
6. The held-out year was never used to keep or drop anything: a loss there is a warning, a gain is not proof (one
   year is noisy). If the result has a hindsight line (hand-picked stocks), suggest the same goal on index ETFs.
7. If nothing survived, say so plainly and read the "Closest miss" line. That is a useful answer, not a failure.
8. If the user likes a survivor: ask, then `adopt_candidate(run, id)` (checkpoint first), then `nutrition_label`,
   `open_bot_view`, and paper trading. A survivor is a lead to paper trade, not a bot to trust with money.
9. If the result says DEMO DATA, repeat that the prices are made up and the numbers mean nothing about real markets.
