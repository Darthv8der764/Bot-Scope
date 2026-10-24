"""Tool annotations for the MCP server (Anthropic's directory asks every tool for a title, readOnlyHint and
destructiveHint). One table here; server.py applies it to every tool, and a test fails if a tool has no row.

read-only  = only reads (market data, saved results, settings); never writes a file or the journal.
destructive = can overwrite or remove something of yours, or switch real-money trading back on.
open world  = reaches services outside this computer (market data, news, alerts to your phone).
Nothing in BotScope places, changes or cancels an order; the order tools it mentions are only checked by its guard.
"""
from __future__ import annotations

TITLES = {
    "doctor": "Check my BotScope setup", "list_bots": "List my bots", "run_backtest": "Quick backtest",
    "honest_report": "Honest report (tuned vs untested years)", "ask_market_question": "Ask a market question",
    "crash_test": "Crash test (past sell-offs)", "luck_meter": "Luck meter", "bot_arena": "Bot vs bot",
    "teach_me": "Teach me a day", "market_weather": "Market weather", "weather_calendar": "Weather calendar",
    "days_like_today": "Days like today", "time_of_day_map": "Time-of-day map", "size_by_risk": "Size a paper trade by risk",
    "what_if_stop_target": "What-if stop and target grid", "weekly_recap": "Weekly recap image",
    "mistake_mirror": "Mistake mirror (my own trades)", "project_map": "Project map page",
    "nutrition_label": "Bot nutrition label", "stop_everything": "STOP everything",
    "set_loss_budget": "Set weekly loss budget", "export_to_gallery": "Export a bot to the gallery",
    "screenshot_confidence": "Screenshot confidence check", "scam_check": "Scam check",
    "phone_alert_test": "Send a test phone alert", "resume_trading": "Resume after STOP",
    "check_order": "Would the guard allow this order?", "drift_alarm": "Drift alarm",
    "graduation_test": "Graduation test", "switch_live": "Switch a bot's live-money flag",
    "morning_brief": "Morning brief", "weekly_checkup": "Weekly checkup", "loss_autopsy": "Loss autopsy",
    "shadow_scoreboard": "Shadow scoreboard", "export_paper_results": "Export paper results (CSV)",
    "backup_my_data": "Back up my data", "key_dates": "Key dates for a stock", "rule_playground": "Rule playground",
    "event_days": "Event-day split", "preflight_list": "Today's pre-flight list", "set_bots_on_off": "Set bots on or off today",
    "save_checkpoint": "Save a checkpoint", "list_checkpoints": "List checkpoints", "show_changes": "Show bot changes",
    "restore_checkpoint": "Restore a checkpoint", "security_check": "Security check", "undo_security_fix": "Undo a security fix",
    "market_board": "Market board", "top_movers": "Top movers", "market_news": "Market news", "fed_odds": "Fed odds",
    "yield_curve": "Yield curve", "economy": "Economy numbers", "stock_panels": "Stock facts",
    "portfolio_risk": "Portfolio risk", "open_desk": "Open the market desk", "parent_view": "Parent view",
    "open_studio": "Open BotScope Studio", "new_bot": "Write a new bot", "make_shadow": "Make a shadow version",
    "strategy_factory": "Strategy factory", "import_pine": "Import a Pine Script strategy",
    "honest_optimizer": "Honest optimizer", "team_report": "Team of bots", "strategy_dna": "Strategy DNA",
    "option_spread_plan": "Option spread plan (paper)", "data_sources": "Data sources", "add_alert": "Add a price alert",
    "list_alerts": "List price alerts", "remove_alert": "Remove a price alert", "check_alerts": "Check price alerts",
    "friends_league": "Friends league", "friends": "Friends (friend codes)", "export_report_page": "Share a report page",
    "robustness_check": "Robustness check", "factory_history": "Factory history", "adopt_candidate": "Adopt a factory bot",
    "check_bot": "Check a bot file", "account_summary": "Paper account summary", "market_calendar": "Market calendar",
    "open_bot_view": "Open the bot view chart", "trade_clip": "Trade clip", "why_not_here": "Why not here?",
    "move_stop_target": "Move a stop or target (paper)", "veto_trade": "Veto a trade (paper)",
    "veto_scorecard": "Veto scorecard", "suggest_rules_from_vetoes": "Suggest rules from vetoes",
    "get_chart_drawings": "Get my chart drawings", "log_paper_results": "Log paper results",
    "import_my_bots": "Import my bots (read-only)", "auto_setup": "Map an existing bot into BotScope",
    "publish_check": "Publish check (local)", "phantom_test": "Phantom test (live paper)",
}

READ_ONLY = {   # only reads: nothing written, nothing saved
    "doctor", "list_bots", "ask_market_question", "teach_me", "market_weather", "weather_calendar", "days_like_today",
    "size_by_risk", "nutrition_label", "screenshot_confidence", "scam_check", "check_order", "graduation_test",
    "morning_brief", "key_dates", "event_days", "preflight_list", "list_checkpoints", "show_changes", "market_board",
    "top_movers", "market_news", "fed_odds", "yield_curve", "economy", "stock_panels", "portfolio_risk",
    "option_spread_plan", "data_sources", "list_alerts", "factory_history", "check_bot", "account_summary",
    "market_calendar", "why_not_here", "veto_scorecard", "get_chart_drawings", "open_desk", "open_studio",
    "open_bot_view", "project_map", "parent_view", "strategy_dna",
}

DESTRUCTIVE = {   # can overwrite or remove something of yours, or switch real-money trading back on
    "restore_checkpoint", "remove_alert", "undo_security_fix", "security_check", "switch_live", "resume_trading",
    "import_my_bots", "publish_check", "set_bots_on_off", "friends", "adopt_candidate",
}

LOCAL_ONLY = {   # never reaches a service outside this computer
    "doctor", "list_bots", "size_by_risk", "check_order", "graduation_test", "set_loss_budget", "stop_everything",
    "resume_trading", "switch_live", "set_bots_on_off", "save_checkpoint", "list_checkpoints", "show_changes",
    "restore_checkpoint", "security_check", "undo_security_fix", "open_studio", "open_desk", "parent_view",
    "project_map", "list_alerts", "remove_alert", "factory_history", "check_bot", "get_chart_drawings",
    "friends", "friends_league", "export_to_gallery", "export_paper_results", "backup_my_data", "veto_trade",
    "move_stop_target", "suggest_rules_from_vetoes", "data_sources", "scam_check", "screenshot_confidence",
    "publish_check", "auto_setup", "new_bot", "make_shadow", "adopt_candidate", "import_pine",
}


def annotations(name: str):
    """ToolAnnotations for one tool. KeyError for a tool missing from the table (the test catches that)."""
    from mcp.types import ToolAnnotations
    title = TITLES[name]
    ro = name in READ_ONLY
    return title, ToolAnnotations(title=title, read_only_hint=ro, destructive_hint=(not ro and name in DESTRUCTIVE),
                                  idempotent_hint=ro, open_world_hint=name not in LOCAL_ONLY)
