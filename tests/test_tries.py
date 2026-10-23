"""Settings-tried counter: more tries on the same days = the best one is more likely luck."""
from botscope import tries


def test_counts_distinct_settings_on_the_same_days():
    assert tries.note("b", "2026-08-01", "2026-09-01", None, None) == {"settings_tried_on_these_days": 1}
    assert tries.note("b", "2026-08-01", "2026-09-01", None, None)["settings_tried_on_these_days"] == 1   # same again
    out = tries.note("b", "2026-08-01", "2026-09-01", {"r_multiple": 1.5}, None)
    assert out["settings_tried_on_these_days"] == 2 and "tuned days" in out["tries_note"]
    assert tries.note("b", "2026-07-01", "2026-08-01", {"r_multiple": 1.5}, None)["settings_tried_on_these_days"] == 1
    assert tries.note("other", "2026-08-01", "2026-09-01", None, None)["settings_tried_on_these_days"] == 1
