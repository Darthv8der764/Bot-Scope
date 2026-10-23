"""Offline check of the backup zip (temporary bots and journal folders)."""
import zipfile

from botscope import backup


def test_backup_zips_bots_and_journal_but_never_keys(tmp_path, monkeypatch):
    bots, jr = tmp_path / "bots", tmp_path / "journal"
    (bots / "__pycache__").mkdir(parents=True)
    (jr / "playground").mkdir(parents=True)
    (bots / "my_bot.py").write_text("# a bot\n")
    (bots / "__pycache__" / "my_bot.pyc").write_text("x")
    (bots / ".env").write_text("ALPACA_API_KEY=PKSECRET\n")
    (jr / "paper_results.json").write_text("[]")
    (jr / "playground" / "my_bot.json").write_text("{}")
    monkeypatch.setenv("BOTSCOPE_BOTS_DIR", str(bots))
    monkeypatch.setenv("BOTSCOPE_JOURNAL_DIR", str(jr))
    out = backup.backup(str(tmp_path / "b.zip"))
    names = zipfile.ZipFile(out["path"]).namelist()
    assert sorted(names) == ["bots/my_bot.py", "journal/paper_results.json", "journal/playground/my_bot.json"]
    assert out["files"] == {"bots": 1, "journal": 2} and "never" in out["note"]


def test_backup_age_for_the_doctor(tmp_path, monkeypatch):
    from datetime import date, timedelta
    monkeypatch.setenv("BOTSCOPE_BOTS_DIR", str(tmp_path))
    monkeypatch.setenv("BOTSCOPE_JOURNAL_DIR", str(tmp_path / "journal"))
    assert backup.last_age_days() is None
    out = backup.backup(str(tmp_path / "b.zip"))
    assert backup.last_age_days() == 0
    assert backup.last_age_days(date.today() + timedelta(days=9)) == 9
    import os
    os.remove(out["path"])                                 # moved or deleted zip: doesn't count
    assert backup.last_age_days() is None


def test_ages_use_the_local_day_not_the_utc_one(monkeypatch):
    """Stamps are UTC: at 8:30 PM in New York it's already tomorrow in UTC, and a fresh backup read '-1 days old'."""
    import time
    from datetime import date
    from botscope import journal
    monkeypatch.setenv("TZ", "America/New_York"); time.tzset()
    try:
        assert journal.local_day("2026-10-18T00:30:00+00:00") == date(2026, 10, 17)
        assert journal.local_day("2026-10-18T05:00:00+00:00") == date(2026, 10, 18)
        assert journal.local_day("2026-10-18") == date(2026, 10, 18)
    finally:
        monkeypatch.undo(); time.tzset()
