# What trading costs do to small edges

*A research note for BotScope users. Worked examples use BotScope's own cost model. Not financial advice.*

## The idea in one line
Costs are paid in dollars per share, but a bot's edge is measured in **R** (its risk per trade). So the same cost
is tiny for a wide stop and huge for a tight one:

**cost in R = cost in % of price ÷ stop distance in % of price**

## BotScope's cost model
`botscope/costs.json` holds costs in basis points (1 bp = 0.01% of price), one side. The starting values were
measured from real paper fills in the prototype (October 2026, a small sample), so re-measure with your own fills.

| Kind | Entry | Exit | Extra when the stop hits |
|------|-------|------|--------------------------|
| Stock intraday | 0.5 bp | 0.5 bp | 7.7 bp (measured) |
| Swing | 5 bp | 5 bp | 5 bp (a guess, no fills yet) |
| Crypto | 57.5 bp | 57.5 bp | 20 bp (a guess, no fills yet) |

## Worked examples (arithmetic, not results)
| Trade | Stop distance | Round trip, normal exit | Round trip, stopped out |
|-------|---------------|-------------------------|-------------------------|
| Stock intraday, tight stop | 0.20% | 1 bp = **0.05R** | 8.7 bp = **0.44R** |
| Stock intraday, wider stop | 0.50% | 1 bp = 0.02R | 8.7 bp = 0.17R |
| Swing | 2% | 10 bp = 0.05R | 15 bp = 0.08R |
| Crypto | 2% | 115 bp = **0.58R** | 135 bp = **0.68R** |

What this means:
- A tight intraday stop is cheap to enter, but **every stop-out costs almost half an R** in slippage. A bot that
  makes +0.10R a trade before costs and gets stopped out often can turn negative.
- Crypto at these fill costs needs an edge of more than half an R a trade **just to break even**.
- Swing trades pay more basis points but risk more per trade, so costs are a smaller share of R. Overnight gaps
  are a different risk: they can jump past the stop (the stop-out cost above doesn't cover them).

## What you can do
1. Look at the label's **costs** row: it shows the total costs in R and in dollars per trade.
2. If costs are more than about a third of the edge before costs, a small change in fills can erase it.
3. Re-measure costs from your own paper fills and edit `costs.json`; the label then warns that its report was
   saved with older costs.
4. Prefer wider stops (with smaller size, see `size_by_risk`) over tight stops on the same idea, then test both
   on untested days.

## Source
- BotScope `botscope/costs.json` (measured from prototype paper fills, October 2026, small sample; the swing and
  crypto stop-out extras are guesses).
