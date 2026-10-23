# How many trades before you know?

*A research note for BotScope users. The numbers below are arithmetic on a made-up example, not results. Not
financial advice.*

## The idea in one line
A bot's average result per trade wobbles a lot when there are few trades. How much it wobbles shrinks with the
**square root** of the trade count: 4x the trades only halves the wobble.

## A simple example
Take a bot whose trades either lose 1R (stopped out) or make 2R (target hit), one target for every two stops. On
average it makes nothing (0R a trade), and one trade's result spreads about **1.4R** around that average.

The usual rough band for the average is **± 2 x 1.4R / √(trades)**:

| Trades | Rough band around the true average |
|--------|------------------------------------|
| 30 | ± 0.52R a trade |
| 100 | ± 0.28R a trade |
| 300 | ± 0.16R a trade |
| 1,000 | ± 0.09R a trade |

So with 30 trades, a bot that really makes nothing can easily show +0.4R a trade by luck. And a bot that really
makes +0.10R a trade needs roughly **(2 x 1.4 / 0.10)² ≈ 800 trades** before its band stops touching zero.

## Why real life is worse
- **Trades aren't independent.** Trades on the same day or in the same market mood tend to win or lose together,
  so 100 trades can carry less information than 100 separate coin flips.
- **Markets change.** Old trades describe old markets; a long backtest mixes several of them.
- **Tries add up.** Picking the best of many settings makes its average look better than it is (see
  [why the best setting looks better](why-the-best-setting-looks-better.md)).

## How BotScope handles it
| Question | Where to look |
|----------|---------------|
| How wide is the wobble for my bot? | The label's **range (bad / middle / good)**: 1,000 resamples of the bot's own untested trades (drawn with repeats) |
| Is the sample big enough? | The **confidence meter** needs 30+ untested trades to leave "very low", 100+ for "high" and 300+ for "very high", and it caps the level until there are 10+ live paper trades |
| How many more do I need? | The meter's **"to move up"** line |

## What you can do
1. Read the bad end of the range, not the middle.
2. If a bot trades rarely, add symbols or years before believing it, not more settings.
3. Treat any result under about 100 untested trades as a hint, not a finding.
