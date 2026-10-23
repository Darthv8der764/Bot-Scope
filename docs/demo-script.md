# 60-second demo script (demo mode)

Recorded in demo mode, so the **DEMO DATA** badge is on screen the whole time. Say it out loud once: the prices are
made up, so the numbers mean nothing about real markets. Not financial advice.

| Time | On screen | Say |
|---|---|---|
| 0:00-0:08 | Terminal: `uv run botscope doctor` | "BotScope plugs trading-bot tools into your own Claude. No keys yet, so it's in demo mode: made-up prices, clearly badged." |
| 0:08-0:22 | Terminal: `uv run botscope strategy_factory "a calm daily ETF bot"` | "I describe the bot I want. It writes a few candidates and tests each one on years nobody tuned it on, with costs, doubled costs and a luck check." |
| 0:22-0:30 | The factory table: survivors + "Dropped / Why" | "Only survivors are kept, ranked by a confidence level, never a percentage. Every dropped one says why, like 'lost money once costs doubled'. The last year is held out, so each survivor also gets one test nothing was chosen on." |
| 0:30-0:42 | `uv run botscope open_studio`, Bot view tab; click a candle | "Studio shows what the bot sees. Click any candle and it tells you why it did or didn't trade there." |
| 0:42-0:50 | Desk tab, then the STOP button | "A free market desk, every number with its source. And one STOP button blocks every order." |
| 0:50-0:60 | Tutorial tab | "Paper trading only, keys stay on your computer. The tutorial walks you through it in two minutes. Free for personal use." |

Tips: dismiss the first-run tours before recording (or add `?notour=1` to a page link), use a phone-width window
for a second take, and never show a real `.env` or account screen.
