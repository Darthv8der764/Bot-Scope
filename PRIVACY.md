# BotScope privacy policy

_Last updated: 2026-10-23_

BotScope runs on your own computer. **Its developer collects nothing.** There is no BotScope server, no account, no
analytics and no tracking of any kind. Nothing about you, your bots or your trades is ever sent to the developer.

## What BotScope stores, and where
Everything stays on your computer, in folders you control:

- **Your keys** (Alpaca paper keys and any optional data keys you add). Either in your computer's secure credential
  store (when you enter them in Claude Code's plugin settings), or in `~/.botscope/.env`, a file readable only by you
  (when you add them in Studio's Get started tab). Keys are never shown back in full, never logged, and never sent
  anywhere except to the service they belong to.
- **Your bots** (`~/.botscope/bots`) and **your journal** (`~/.botscope/journal`): backtest reports, paper results,
  vetoes, chart drawings, alerts, imported trades, friend cards and settings.
- **Market data caches**, backups you make, and files you export (reports, CSVs, images).

BotScope keeps these until you delete them. To remove everything, delete the `~/.botscope` folder (and uninstall the
plugin). For a developer copy, delete the `data/` folder in it as well.

## What BotScope sends, and to whom
BotScope only contacts outside services to do what you ask, and only the ones you set up. Each request goes straight
from your computer to that service, under that service's own privacy policy:

| Service | When | What is sent |
|---|---|---|
| [Alpaca](https://alpaca.markets) | Market data, your paper account (read-only), importing your past orders | Your Alpaca keys, and the symbols and dates requested |
| [Coinbase](https://www.coinbase.com) public data | Only if you choose it for crypto prices | The crypto symbols and dates requested (no keys) |
| [FRED](https://fred.stlouisfed.org) (St. Louis Fed) | Economy panels, if you add a FRED key | Your FRED key and the data series requested |
| [Finnhub](https://finnhub.io) | Earnings and analyst panels, if you add a Finnhub key | Your Finnhub key and the symbols requested |
| [SEC EDGAR](https://www.sec.gov) | Insider and filing panels, if you add an SEC contact | The contact line you gave (the SEC requires one) and the symbols requested |
| [FINRA](https://www.finra.org) | Short-interest panel | The symbols requested |
| [Kalshi](https://kalshi.com) public data | Fed-meeting odds panel | Nothing about you |
| [ntfy](https://ntfy.sh), Discord or Telegram | Only if you set up phone alerts | The alert text, to the channel you chose |
| Your own Claude Code | When you use BotScope's tools, or Studio's Claude panel | Tool results become part of your Claude conversation, under [Anthropic's privacy policy](https://www.anthropic.com/legal/privacy) |

BotScope never places, changes or cancels an order. It never reads your Claude conversations, memory or chat
history.

## Friend codes
A friend code holds only a bot's summary numbers (and its rules and tickers only if you tick "include rules"). It goes
only where you paste it yourself. BotScope has no server to send it to.

## Children
BotScope is a trading research tool and is not intended for people under 18.

## Changes and contact
Changes to this policy appear in this file, with a new date. Questions: open an issue at
https://github.com/Darthv8der764/Bot-Scope/issues. To report a security problem privately, see
[SECURITY.md](SECURITY.md).
