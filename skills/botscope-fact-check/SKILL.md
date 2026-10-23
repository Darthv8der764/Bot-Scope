---
name: botscope-fact-check
description: Fact-check a trading strategy from a YouTube video, article or post with BotScope - pull out the claims and the exact rules, turn them into a paper bot, and test them honestly on untested years with real costs and the luck meter. Use when the user pastes a video link or transcript, or says "does this strategy work", "fact check this", or "this YouTuber says...".
---

# YouTuber fact check

Goal: judge the strategy as it was described, not the person. Paper only. Not financial advice.

0. Scam check first: `scam_check` on the text. **Red** = stop and show the flags; only go on if the user says so
   on purpose (call again with `let_through_reason`). Yellow: mention the flags, then continue.
1. Get the words. Use a transcript or article text the user pastes, or fetch the page they link. If you can't get
   the words, ask for them; never guess what a video says.
2. Write down two lists, short, in your own words (no long quotes; one quote under 15 words at most):
   - **Claims**: every number they promise (win rate, returns, "never loses", timeframe, tickers, account growth).
   - **Rules**: entry, stop, target, exit, filters, time of day, tickers. One line each.
   Mark every rule that is vague ("wait for confirmation", "strong candle", "use your judgment"). Pick the simplest
   literal version, say which one you picked, and put the guessed number in `params` so it can be varied later.
   If the stop or the entry can't be pinned down at all, stop here and say the strategy can't be tested as told.
3. `save_checkpoint`, then `new_bot` (status "untested", tuned_on None: we did not tune anything, so every year is
   untested), fill in the rules (see the botscope-new-bot skill), and `check_bot` until it passes.
4. Test, one at a time (they download data):
   - `run_backtest` for a quick look, then `honest_report` (every year since 2016, real costs, crashes).
   - `luck_meter`: does it beat random entries?
   - If a vague rule matters, `bot_arena` with two versions of it (params_a / params_b) on the same untested days.
5. Answer with a table: **Claim | What the test found | Holds up?** (yes / partly / no / can't test). Then the
   nutrition label (`nutrition_label` markdown), the luck level, the guesses you made, and one line on what would
   change the verdict. Use counts and R, never a made-up percentage. Say that past results aren't a promise.

Never: say the creator lied, show their personal info, tell the user to buy or sell, or trade the bot live.
