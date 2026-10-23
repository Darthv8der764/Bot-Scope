# Paper fills vs real fills

*A research note for BotScope users. Not financial advice.*

## The idea in one line
Paper trading is the right first step, but its fills are usually **kinder than real ones**, so a bot that only
just makes money on paper may not make money with real orders.

## Why paper fills are kinder
Alpaca's paper-trading page lists what its simulation doesn't account for: market impact of your orders,
information leakage, slippage due to latency, order queue position (for limit orders that wait), price
improvement, regulatory fees and dividends. It also says paper order sizes aren't checked against the quoted
size, so a big order can fill in full where a real one couldn't. In practice:
- **No market impact or size limit.** A real order takes liquidity and can move the price; a paper one fills at
  the quote whatever its size.
- **No latency.** A real order arrives a moment later, when the price may have moved, most of all in fast markets
  and on stop-outs.
- **No queue.** A real limit order waits behind others at its price; on paper it fills as soon as the quote
  reaches it.
- **Fees.** Regulatory fees on sells don't show up on paper.
- **One thing goes the other way:** real orders sometimes get a slightly better price than the quote (price
  improvement), which paper doesn't give you either.

Source: Alpaca docs, "Paper Trading" (docs.alpaca.markets/us/docs/paper-trading), read 2026-10-17.

## What that means for BotScope numbers
BotScope's cost model (`botscope/costs.json`) was measured from **paper** fills, so it likely **understates** real
costs, most of all on stop-outs. That's why the label also shows **"if costs doubled"**: a bot that turns negative
there has very little room for real-world fills. See
[what costs do to small edges](what-costs-do-to-small-edges.md) for the arithmetic.

## What you can do
1. Look at the **"if costs doubled"** row before trusting a small edge.
2. Prefer bots whose edge per trade is several times their cost per trade.
3. Keep paper and real results apart; BotScope stays paper only and never places real orders.
4. If you ever compare against real fills, update `costs.json` from them so every backtest pays the real price.
