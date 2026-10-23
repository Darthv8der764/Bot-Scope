# Contributing to BotScope

Thanks for helping. BotScope is small on purpose: honest, safe, and cheap to run.

## Ground rules
- **Paper first.** No tool may place an order. Anything near live money goes through `botscope/guard.py` and its tests.
- **Honest numbers.** Results say tuned vs untested, name their data source, take costs out, and never show a win %,
  "guaranteed" or an unlabeled projection. `tests/test_honesty_lint.py` enforces this on code, pages, skills and docs.
- **No market data in the repo.** Users download data with their own keys. Demo mode uses prices generated on the
  user's computer (`botscope/demo.py`); never commit vendor data, cached bars, journals or `.env` files.
- **No personal data.** No keys, account numbers, IPs, trade journals or emails in code, tests, docs or screenshots.
- **Not financial advice.** No buy/sell calls, no signal selling, no managing other people's money.

## Setup
```bash
uv venv && uv pip install -e .
```
```bash
.venv/bin/python -m pytest -q
```
The whole suite runs offline in seconds (tests use made-up bars and a throwaway journal).

## Making a change
1. Keep it small: one idea per pull request, with its tests.
2. New MCP tool: write its description for Claude (what to show, what to say about tuned vs untested), then
   regenerate the README tools table: `python -c 'from botscope import cli; print(cli.tools_table())'`.
3. Pages: one shared look (`botscope/web/theme.js` + the same CSS variables), check at 375 px wide, dark and light.
4. Heavy work (backtests) takes the one-backtest-at-a-time lock (`_one_backtest` in `botscope/server.py`).
5. Run the full suite before you open a pull request.

## New example bots
Put them in `bots/` with plain-English rules that mention every setting (`check_bot` checks), an honest `status`,
and `tuned_on` if you picked any setting by looking at results.
