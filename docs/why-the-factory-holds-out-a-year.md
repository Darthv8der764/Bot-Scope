# Why the strategy factory holds out the last year

*A research note for BotScope users. Plain words, sources at the bottom. Not financial advice.*

## The problem
The strategy factory never tunes settings: every candidate uses textbook values, so every year is "untested" for
that one bot. But the factory still **chooses**. It tries up to 5 candidates on the same years and keeps the ones
that held up. Choosing is a kind of tuning: if you look at 5 results and keep the best, the best one is partly
there because it was lucky on those years. Run the factory again with a slightly different goal on the same
symbols, and you have now looked at 10. The years stay the same; only your number of looks grows.

## What BotScope does about it
| Risk | What the factory does |
|------|--------------------|
| Keeping the luckiest of several | Every keep/drop decision uses the years up to one year ago. The last year is **held out**: no check sees it. Survivors then show it as the "Held-out year" column. |
| Many looks at the same years | Every run on the same symbols and candle size counts toward one total. At 15+ candidates, survivors drop one confidence level, and the note says how many runs it took. |
| Settings that only work at one exact value | Every candidate is re-run with all settings 20% smaller and 20% bigger; if either version loses money, it's dropped ("knife-edge settings"). |
| An edge that faded | If the later half of the untested years lost money while the earlier half made money, it's dropped. |
| A few lucky trades | It must still make money without its 3 best trades, and with trading costs doubled. |
| Stops a few cents away | Trades whose stop is closer than their own trading costs (or 0.05% of price) blow R up; if 5%+ of trades do, the R numbers can't be trusted and the candidate is dropped. |
| Plain luck | The luck meter compares it with random "twins" that take the same trades at random times. |

## How to read the held-out year
- It is **one year** (for intraday bots, one month). That is a small sample, so it wobbles a lot
  (see [How many trades before you know?](how-many-trades-before-you-know.md)).
- A **loss** there is a real warning: the closest-to-now data disagreed with everything before it.
- A **gain** there is not proof. It only means the survivor didn't fail its one fresh test.
- Once you have looked at the held-out year, it is no longer fresh for you. If you rerun the factory because you
  didn't like it, that year has become one more year you chose on.

Researchers call the held-out piece an **out-of-sample** or **holdout** test; trading researchers often roll it forward
(walk-forward testing). The factory uses the simplest version: one fixed held-out year at the end.

## Sources
- Bailey, Borwein, López de Prado and Zhu (2017), "The Probability of Backtest Overfitting", Journal of
  Computational Finance: with many tries on one history, the best backtest tends to disappoint on new data.
- White (2000), "A Reality Check for Data Snooping", Econometrica: testing the best of many models needs a
  correction for how many were looked at.
- Pardo (2008), *The Evaluation and Optimization of Trading Strategies* (2nd ed.), Wiley: walk-forward testing.

See also [Why the best setting looks better than it is](why-the-best-setting-looks-better.md).
