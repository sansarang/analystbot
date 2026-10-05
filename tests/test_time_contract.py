"""🔴🔴 **5단계 시간 계약** — tz 없는 값은 비교에 못 들어온다(사용자 설계 2026-10-03).

> **시간 계약**: `datetime` 비교에 **tz 없는 값이 들어오면 실패**.

══════════════════════════════════════════════════════════════════
🔴 왜 — 시차로 **경기를 잃었다**
══════════════════════════════════════════════════════════════════

실측 2026-10-03: `크로아티아 - 잉글랜드` 가 `16:00Z` = **01:00 KST** 인데 "오늘"로
물으니 날짜 창에 안 걸려 **버려졌다.** ⚠️ naive 값은 **조용히 서버 시간대로
가정**되고, 그 가정이 어긋나도 아무 데도 안 적힌다.

🔴 파이썬은 naive 와 aware 를 비교하면 `TypeError` 를 낸다 — 그런데 **naive 끼리는
조용히 비교된다.** 그 자리가 이 저장소를 다치게 한 자리다.
"""
from __future__ import annotations

import ast
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import matchref, timefmt

ROOT = Path(__file__).resolve().parents[1]


def test_tz_없는_값은_안_받는다():
    """🔴 `aware` 는 못 붙이면 **`None`** 이다 — 조용히 UTC 로 가정하지 않는다."""
    assert timefmt.aware(datetime(2026, 10, 3, 16)) is None
    got = timefmt.aware(datetime(2026, 10, 3, 16), assume=timefmt.KST)
    assert got is not None and got.tzinfo is timefmt.KST
    aware = datetime(2026, 10, 3, 16, tzinfo=timezone.utc)
    assert timefmt.aware(aware) is aware
    assert timefmt.aware("2026-10-03") is None


def test_naive_끼리의_비교를_막는다():
    """🔴🔴 파이썬이 **안 막아 주는** 자리다 — naive 끼리는 조용히 비교된다."""
    a, b = datetime(2026, 10, 3), datetime(2026, 10, 4)
    assert a < b                       # ⚠️ 파이썬은 그냥 통과시킨다
    with pytest.raises(ValueError, match="시간대 없는"):
        timefmt.before(a, b)
    with pytest.raises(ValueError, match="시간대 없는"):
        timefmt.before(a.replace(tzinfo=timezone.utc), b)
    assert timefmt.before(a.replace(tzinfo=timezone.utc),
                          b.replace(tzinfo=timezone.utc))


def test_MatchRef_가_naive_를_버린다():
    """🔴 2단계에서 넣은 선금 — 입구에서 막는다."""
    row = {"id": 1, "ext_id": "x-1", "home": "A", "away": "B",
           "starts_kst": datetime(2026, 10, 3, 16)}
    assert matchref.ref_from_row(row).kickoff_utc is None


def test_표시_변환이_tz_를_요구한다():
    """🔴 절대규칙 2 — 모르는 시간대에 `KST` 를 붙이면 **조용한 거짓**이다."""
    with pytest.raises(ValueError, match="시간대 없는"):
        timefmt.kst_label(datetime(2026, 10, 3, 16))
    assert timefmt.kst_label(
        datetime(2026, 10, 3, 16, tzinfo=timezone.utc)) == "10-04 01:00 KST"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **구조 계약** — naive 가 **태어나는 자리**를 막는다
# ══════════════════════════════════════════════════════════════════

#: 🔴 `datetime.now()` 는 **늘 tz 를 받아야** 한다.
#   ⚠️ `utcnow()` 는 **naive 를 돌려준다**(파이썬의 함정) — 아예 금지다.
def test_지금을_tz_없이_읽지_않는다():
    bad: list[str] = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
                continue
            if n.func.attr == "utcnow":
                bad.append(f"{p.relative_to(ROOT)}:{n.lineno} utcnow() — naive 다")
            elif n.func.attr == "now" and not n.args and not n.keywords:
                # ══════════════════════════════════════════════════════
                # 🔴🔴 **이름을 바꿔 들여와도 잡는다**(돌연변이가 통과했다)
                # ══════════════════════════════════════════════════════
                #
                #  ⚠️ 종전엔 `ast.unparse(...).endswith("datetime")` 만 봤다.
                #     그래서 `from datetime import datetime as _dt` 뒤의
                #     **`_dt.now()`** 를 못 잡았다 — 돌연변이를 넣었는데
                #     **초록이었다**(실측 2026-10-04).
                #  🔴 인자 없는 `*.now()` 는 **전부** 잡는다. `datetime` 이 아닌
                #     것에 `.now()` 가 있으면 그것은 여기 적어 예외로 둔다 —
                #     지금은 하나도 없다.
                bad.append(f"{p.relative_to(ROOT)}:{n.lineno} "
                           f"{ast.unparse(n)} — tz 가 없다")
    assert not bad, "🔴 tz 없이 '지금'을 읽는다(5단계):\n  " + "\n  ".join(bad)


def test_fromisoformat_뒤에_tz_를_확인한다():
    """🔴🔴 `replace("Z","+00:00")` 은 **`Z` 가 있을 때만** 듣는다.

    ⚠️ `2026-10-03T16:00:00` 처럼 끝에 아무것도 없으면 **naive 가 그대로 나간다.**
    🔴 그래서 그 자리마다 **tz 를 확인하거나 붙이는 코드가 함께** 있어야 한다.
    """
    bad: list[str] = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        lines = p.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if "datetime.fromisoformat" not in line:
                continue
            # ⚠️ 주석은 센다 — 설명하는 줄과 부르는 줄은 다르다(D46)
            if line.lstrip().startswith("#"):
                continue
            near = "\n".join(lines[max(0, i - 3):i + 6])
            if not re.search(r"tzinfo|astimezone|timefmt\.aware|assume_tz", near):
                bad.append(f"{p.relative_to(ROOT)}:{i + 1} {line.strip()[:60]}")
    assert not bad, ("🔴 `fromisoformat` 뒤에 tz 확인이 없다(naive 가 샌다):\n  "
                     + "\n  ".join(bad))


def test_어댑터가_naive_를_안_내보낸다():
    """🔴 세 어댑터의 `_when` 은 **tz 가 없으면 `None`** 이다.

    ⚠️ 종전엔 `Z` 없는 꼴이 오면 naive 가 그대로 슬레이트로 갔다.
    """
    from app.collect import fdorg, mlb, nhl
    for mod in (mlb, nhl, fdorg):
        assert mod._when("2026-10-03T16:00:00Z") is not None, mod.__name__
        assert mod._when("2026-10-03T16:00:00") is None, (
            f"{mod.__name__}: tz 없는 값을 내보낸다")


def test_DB_가_tz_있는_칸을_쓴다():
    """🔴 절대규칙 2 — 표가 `TIMESTAMP`(tz 없음)면 **거기서부터 샌다**."""
    sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    bad = [ln.strip() for ln in sql.splitlines()
           if re.search(r"\bTIMESTAMP\b(?!TZ)", ln, re.I)]
    assert not bad, f"🔴 tz 없는 칸이 있다: {bad[:4]}"
