---
name: botscope-setup
description: Walk a new BotScope user through setup, one easy step at a time - try the demo, add free Alpaca paper keys for real data, bring in their own bots, switch on Claude inside Studio. Use when the user says "set me up", "get started", "I just installed BotScope", "how do I use real data", "add my keys", "it says DEMO DATA", or seems new and stuck.
---

# BotScope setup, made easy

Paper trading only. Not financial advice. One step at a time; short messages; never a wall of text.

1. `doctor` - read it quietly. Say in one line where they are: demo or real data, and the one thing to do next.
2. `open_studio(tab="start")` - give them the link and say: "the Get started tab shows each step with a ✓ when it's done."
   Open it in the browser pane if you can.
3. Keys (the step most people get stuck on):
   - They type their keys into the Get started tab themselves. NEVER ask them to paste keys into the chat, and never
     put keys in a command, a file or a URL yourself.
   - Free Alpaca PAPER account: alpaca.markets -> sign up -> make sure the account switch (top left) says Paper ->
     API Keys (right side of the home page) -> Generate New Keys -> copy the Key ID (starts PK) and the Secret Key.
   - If they already run a bot on Alpaca: use the SAME keys that bot uses (new keys switch off the old ones).
   - A key starting with AK is a LIVE money key: BotScope refuses it. Paper keys start with PK.
   - The tab checks the keys with Alpaca before saving. "didn't accept" = wrong copy or old keys.
4. After keys work: `doctor` again to confirm "real data", then offer ONE next step: `import_my_bots(how="alpaca")`
   if they trade on Alpaca already, or the Factory tab to make a first bot.
5. Claude inside Studio (only if they ask): Settings -> Switch on; their `claude` command needs its own login
   (Claude panel -> Terminal -> type `claude`).
6. If something fails, say what failed in plain words and the single next thing to try.
