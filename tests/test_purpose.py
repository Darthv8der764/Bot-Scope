from botscope import doctor, view
from botscope.env import ROOT


def test_purpose_line_everywhere():
    p = doctor.PURPOSE
    assert "never places real orders" in p and "isn't financial advice" in p
    assert p in (ROOT / "README.md").read_text()[:400]                       # at the top
    assert p in view.PAGE.with_name("studio.html").read_text()
    assert p in view.PAGE.read_text()                                        # tutorial step 1
