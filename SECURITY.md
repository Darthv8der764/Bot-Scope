# Security policy

## Reporting a problem
Please report security problems **privately**, not in a public issue:

1. Go to https://github.com/Darthv8der764/Bot-Scope/security
2. Click **Report a vulnerability** and describe what you found, how to reproduce it, and what it could affect.

You'll get an answer within a few days. Fixes are published as a new version, and the report is credited unless you
ask not to be.

## What BotScope protects
- **Paper only:** BotScope never places, changes or cancels an order. Its guard hook blocks live-money orders that
  other tools try to send through the Alpaca connector.
- **Local only:** its pages are served on 127.0.0.1, check the exact host and origin, and refuse other websites.
  Studio's Claude panel is off at every launch, needs a one-time confirmation, and every request needs a token made
  fresh at each launch.
- **Keys:** kept in your computer's secure credential store or in `~/.botscope/.env` (readable only by you), never shown
  back in full, never logged.
- **Friend codes and imports** are read as data and never run.

## Supported versions
Only the latest version on the `main` branch gets security fixes.
