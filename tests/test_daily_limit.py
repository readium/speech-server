"""Daily budget counter — reservation, exhaustion, unlimited, and day rollover."""

import json
from pathlib import Path

from app.core.daily_limit import reserve


def test_reserve_tracks_and_blocks_over_limit(tmp_path: Path) -> None:
    fp = str(tmp_path / "u.json")
    assert reserve(fp, 100, 250) == (True, 100)
    assert reserve(fp, 100, 250) == (True, 200)
    assert reserve(fp, 100, 250) == (False, 200)  # would exceed → rejected, nothing added
    assert reserve(fp, 50, 250) == (True, 250)  # exact fit ok
    assert reserve(fp, 1, 250)[0] is False  # full


def test_zero_limit_is_unlimited_and_untracked(tmp_path: Path) -> None:
    fp = str(tmp_path / "u.json")
    assert reserve(fp, 10_000, 0) == (True, 0)
    assert not Path(fp).exists()  # no file I/O when unlimited


def test_resets_on_new_day(tmp_path: Path) -> None:
    fp = str(tmp_path / "u.json")
    reserve(fp, 200, 250)  # today's usage
    # Simulate a stored entry from a previous day; next reserve should reset to 0 first.
    data = json.loads(Path(fp).read_text())
    Path(fp).write_text(json.dumps({"date": "2000-01-01", "used": data["used"]}))
    allowed, used = reserve(fp, 200, 250)
    assert (allowed, used) == (True, 200)  # fresh day → counter reset, 200 fits under 250
