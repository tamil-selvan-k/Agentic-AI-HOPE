"""Lab 4 — kill -9 a real worker process mid-run, restart, and count the side effects."""
from scripts import crash_drill


def test_crash_drill_passes(capsys):
    assert crash_drill.main() == 0
    assert "PASS" in capsys.readouterr().out
