---
name: botscope-safety
description: BotScope safety rules - paper by default, the live-money lock, STOP, graduation test, checkpoints and the devil's-advocate security check. Use whenever the user talks about live/real money, placing orders, "go live", stopping bots, undoing a bot change, or security.
---

# Safety first

- Paper is the default. Real money needs ALL of: `BOTSCOPE_LIVE_TRADING=1` in the user's own .env (they add it
  themselves), a bot that passed `graduation_test`, `switch_live` with the user's yes, an order under the size cap,
  and a yes for each order. Never talk the user into live trading.
- Before any order through another tool, `check_order` says allow / ask / deny. Respect deny.
- "STOP" means `stop_everything` immediately. Resuming always asks first.
- Before editing a bot file: `save_checkpoint` with a note. To undo: `list_checkpoints`, `show_changes`,
  `restore_checkpoint` (asks first; the restore itself can be undone).
- `security_check` probes the setup without breaking anything and fixes safe holes with an undo id. Lead with its
  headline. Never print keys; keys live only in the user's .env.
- Anything with money, payments, sign-ups or agreements for a minor: a parent decides.
