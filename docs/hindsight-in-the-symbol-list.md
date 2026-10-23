# Hindsight in the symbol list

*A research note for BotScope users. Not financial advice.*

## The idea in one line
If you pick a bot's symbols because they're big winners **today**, then backtest them over years when nobody knew
they'd win, the backtest borrows knowledge from the future.

## Why it matters
- **Survivorship bias.** Today's list of famous stocks leaves out the ones that shrank, were bought out or went
  bankrupt. A 2016 trader couldn't have known which names would make the 2026 list.
- **Long-only bots get the biggest boost.** A dip-buying bot on a stock that went up many times over will look good
  partly because the stock went up, not because of the bot's rules.
- **It hides in plain sight.** BotScope's examples trade names like NVDA, AAPL and MSFT back to 2016, so their
  untested years carry some of this hindsight. Untested means the *settings* weren't picked on those years; the
  *symbols* still were picked with hindsight.

## How to check your own bot
1. **Compare with just holding.** The label's **"beat just holding SPY?"** row shows whether the bot added anything
   beyond being in the market.
2. **Run it on boring symbols too.** `run_backtest` and `honest_report` take a `symbols` setting: try the same bot on
   names that did poorly, or on broad ETFs (SPY, IWM, DIA). A real edge should still show up, smaller. The pullback
   example, in direct backtests over the same years (2016 to 2026, after costs): +47.0R over 444 trades on its 5
   hand-picked symbols, +20.8R over 265 trades on SPY, IWM and DIA (+0.08R a trade instead of +0.11R). Still
   positive, and clearly smaller.
3. **Prefer index ETFs for examples.** SPY, QQQ, IWM and DIA don't drop out of existence, so they carry less of this
   bias (QQQ still holds today's winners, so it carries some).
4. **Write down why each symbol is in the list**, and whether you'd have picked it at the start of the test.

## What BotScope can't fix
BotScope tests the symbols you give it and has no record of which stocks were around (or popular) in 2016, so it
can't rebuild the list a trader would have picked back then. Treat results on hand-picked stocks as
an upper bound.

## Further reading
- Survivorship bias is a standard topic in finance textbooks and backtesting guides; Elton, Gruber and Blake
  (1996), *Survivorship Bias and Mutual Fund Performance* (Review of Financial Studies), is a classic measurement
  of it in fund returns.
