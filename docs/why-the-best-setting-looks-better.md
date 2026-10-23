# Why the best setting looks better than it is

*A research note for BotScope users. Plain words, sources at the bottom. Not financial advice.*

## The problem in one example
Try 20 different stop sizes on the same five years of data and keep the best one. Even if none of the 20 has a real
edge, one of them will usually look good, just by luck: you picked the luckiest of 20 coin-flip runs. The more
settings you try on the same days, the better the best one looks and the less that number tells you.

Researchers call this **overfitting** (or data snooping, or the multiple-testing problem). Two things make it worse:
- **Many tries on the same days.** Each try is another lottery ticket on the same history.
- **Few trades.** With 30 trades, a couple of lucky ones swing the total a lot.

## What the research says
- Bailey, Borwein, López de Prado and Zhu (2015) show that with enough tries on one history, the top backtest
  is expected to look strong even when every strategy tried has no edge, and that it then tends to do worse than
  the middle of the pack on new data.
- Bailey and López de Prado (2014) propose the *deflated Sharpe ratio*: shrink the best result according to how
  many settings were tried and how few trades there were, before believing it.
- Harvey, Liu and Zhu (2016) counted hundreds of published "factors" and argue that, because so many were tried,
  a new one should clear a much higher bar (a t-statistic around 3 instead of 2) before anyone trusts it.

## How BotScope handles it
| Risk | What BotScope does |
|------|--------------------|
| Tuning and judging on the same days | Every report splits **tuned** days from **untested** days; only untested days count |
| Many tries on the same untested days | `run_backtest` and the rule playground count the settings tried and warn when it climbs |
| A few lucky trades carry the total | The label shows the total **without its 3 best trades** |
| Luck versus skill | `luck_meter` runs the bot on shuffled market days: if it does as well there, the edge isn't from real patterns |
| Small samples | The confidence meter says how many more untested trades are needed |

## What you can do
1. Decide the settings **before** looking at untested days, and look at them once.
2. Write down how many settings you tried. If it's more than a handful, trust the best one less.
3. Prefer a setting that's fine across a wide range of values over one sharp peak.
4. Paper trade it next to its old version (`make_shadow`) before believing either one.

## Sources
- Bailey, D. H., Borwein, J., López de Prado, M., Zhu, Q. J. (2015). *The Probability of Backtest Overfitting.*
  Journal of Computational Finance.
- Bailey, D. H., López de Prado, M. (2014). *The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest
  Overfitting and Non-Normality.* Journal of Portfolio Management.
- Harvey, C. R., Liu, Y., Zhu, H. (2016). *...and the Cross-Section of Expected Returns.* Review of Financial
  Studies.
