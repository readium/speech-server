"""Host-wide daily usage budget, backed by a small fcntl-locked JSON file.

Shared across all uvicorn workers on the host and persists across restarts within the
same day, so a per-day cap can't be sidestepped by parallel workers or a quick restart.
Unix only (fcntl) — the server runs on Linux. `{"date": "YYYY-MM-DD", "used": N}`.
"""

from __future__ import annotations

import fcntl
import json
from datetime import UTC, datetime
from pathlib import Path


def reserve(path: str, amount: int, limit: int) -> tuple[bool, int]:
    """Atomically reserve `amount` units against today's (UTC) budget.

    Returns (allowed, used_after_reservation). `limit <= 0` = unlimited (always allowed;
    usage is NOT tracked, to avoid needless file I/O). When the reservation would push
    usage over `limit`, nothing is added and `allowed` is False.
    """
    if limit <= 0:
        return (True, 0)
    today = datetime.now(UTC).date().isoformat()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            raw = f.read()
            data = json.loads(raw) if raw.strip() else {}
            if data.get("date") != today:
                data = {"date": today, "used": 0}
            used = int(data.get("used", 0))
            if used + amount > limit:
                return (False, used)
            used += amount
            f.seek(0)
            f.truncate()
            f.write(json.dumps({"date": today, "used": used}))
            return (True, used)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


if __name__ == "__main__":  # self-check
    import tempfile

    fp = str(Path(tempfile.mkdtemp()) / "u.json")
    assert reserve(fp, 100, 250) == (True, 100)
    assert reserve(fp, 100, 250) == (True, 200)
    assert reserve(fp, 100, 250) == (False, 200)  # would exceed → rejected, not added
    assert reserve(fp, 50, 250) == (True, 250)  # exact fit ok
    assert reserve(fp, 1, 250)[0] is False  # full
    assert reserve(fp, 10_000, 0) == (True, 0)  # limit 0 = unlimited, untracked
    print("daily_limit self-check ok")
