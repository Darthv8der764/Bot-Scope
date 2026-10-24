"""Every MCP tool has a title and readOnlyHint / destructiveHint annotations (Anthropic's directory requires them),
and the labels never understate what a tool does."""
import asyncio

from botscope import server, tool_labels


def _tools():
    return asyncio.run(server.mcp.list_tools())


def test_every_tool_has_a_title_and_annotations():
    tools = _tools()
    assert len(tools) >= 90
    for t in tools:
        a = t.annotations
        assert t.title and a and a.title == t.title, t.name
        assert a.read_only_hint is not None and a.destructive_hint is not None, t.name
        assert len(t.name) <= 64


def test_tables_name_only_real_tools():
    names = {t.name for t in _tools()}
    for table in (tool_labels.TITLES, tool_labels.READ_ONLY, tool_labels.DESTRUCTIVE, tool_labels.LOCAL_ONLY):
        assert set(table) <= names, set(table) - names
    assert not tool_labels.READ_ONLY & tool_labels.DESTRUCTIVE


def test_tools_that_change_things_are_not_marked_read_only():
    writes = {"stop_everything", "resume_trading", "switch_live", "set_bots_on_off", "restore_checkpoint", "new_bot",
              "adopt_candidate", "veto_trade", "move_stop_target", "add_alert", "remove_alert", "import_my_bots",
              "strategy_factory", "honest_report", "log_paper_results", "backup_my_data", "publish_check"}
    ann = {t.name: t.annotations for t in _tools()}
    for n in writes:
        assert ann[n].read_only_hint is False, n
    for n in ("switch_live", "resume_trading", "restore_checkpoint"):
        assert ann[n].destructive_hint is True, n
