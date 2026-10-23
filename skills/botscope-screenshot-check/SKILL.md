---
name: botscope-screenshot-check
description: Give a confidence level (very low to very high) for a trade idea in a chart screenshot, from how similar past setups really did. Use when the user uploads or pastes a chart screenshot and asks "is this a good setup?", "how confident should I be?", "check this trade idea", or "rate this chart".
---

# Screenshot confidence check

Paper only. Not financial advice. Wins only as a count, never a percentage.

1. **Read the image.** Find the ticker, the timeframe (1-minute, 15-minute, hourly, daily...), the date of the last
   candle, and what the setup is (breakout, gap, dip in an uptrend...). Say back in one line what you read.
2. **If anything is unclear, ask** (one short question). If the user can't say, answer
   "very low: not enough to go on" and explain which part was missing. Never guess a ticker.
3. **Map the setup** to one of: `breakout`, `breakdown`, `gap_up`, `gap_down`, `dip_in_uptrend`,
   `rally_in_downtrend`, `oversold_bounce`, `tight_range_uptrend`. If it fits none, say so and give "very low:
   not enough to go on". If it's close to one, say which and that it's an approximation.
4. **Check it:** `screenshot_confidence(symbol, setup, timeframe, as_of=<the screenshot's date>)`. Use `1Day`,
   `1Hour` or `15Min` (round a 5-minute chart to `15Min` and say so).
5. **Answer in a small table:** confidence level, past matches (sample size), date range, source, then the `why`
   line and `how`. Wins are a count ("12 of 40"), never a %. End with "Not financial advice."
6. If the user wants to keep testing the idea, offer the botscope-screenshot-bot skill (turn it into a paper bot
   and run the honest report).

Run the check at most once per screenshot unless the user changes the setup or timeframe.
