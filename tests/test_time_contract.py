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
from datetime import datetime, timedelta, timezone
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
    """🔴 절대규칙 2 — 표가 `TIMESTAMP`(tz 없음)면 **거기서부터 샌다**.

    ⚠️ **주석을 뺀다**(D46). 금지어를 *설명하는* 줄과 칸을 *선언하는* 줄은
       다르다 — 종전엔 스키마 주석에 `TIMESTAMP` 라고 적기만 해도 빨개졌다.
    """
    sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    bad: list[str] = []
    for ln in sql.splitlines():
        code = ln.split("--", 1)[0]          # 🔴 SQL 주석을 걷는다
        if re.search(r"\bTIMESTAMP\b(?!TZ)", code, re.I):
            bad.append(ln.strip())
    assert not bad, f"🔴 tz 없는 칸이 있다: {bad[:4]}"
    # 🔴 **원본이 비어 있지 않다** — 주석만 걷고 선언을 통째로 날리면
    #    이 계약은 아무것도 막지 않는다(퇴로 막기)
    assert re.search(r"\bTIMESTAMPTZ\b", sql), "🔴 시각 칸 선언이 사라졌다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **SQL 쪽의 같은 병** — `starts_kst` 를 KST 라고 **믿고** 자르지 않는다
# ══════════════════════════════════════════════════════════════════
#
# 실측 2026-10-05(인계 ①-2). `games.starts_kst` 는 `TIMESTAMPTZ` — **순간**만
# 담고 오프셋은 버린다. 라이브 52행 **전부** `starts_kst = starts_utc` 였다.
# 🔴 그런데 질의 여섯 자리가 `starts_kst::date` 로 날짜를 뽑았고, 그 캐스트는
#    **세션 시간대**(운영 `Etc/UTC`)로 돈다 — 52행 중 **16행**이 어긋났다:
#
#    France vs Belgium 2026-10-05 18:45Z → `::date` 10-05 / 🔴 KST 는 **10-06**
#
# 실측으로 센 손해: `sources.slate(2026-10-06)` 가 종전 꼴에서 **0건**,
#                   고친 뒤 **1건**. `오늘 경기수` 가 **3 → 4**.
#
# ⚠️ 이 계약은 **AST 로** 문자열 상수를 꺼내 본다 — 파일을 글자로 훑으면
#    독스트링·주석이 퇴로가 된다(D46 · 이 세션이 여섯 번 당한 자리다).


def _sql_strings(path: Path) -> list[tuple[int, str]]:
    """🔴 그 파일의 **문자열 상수**만. ⚠️ 독스트링은 뺀다(코드가 아니다 · D46).

    f-string 은 `JoinedStr` 로 온다 — 🔴 그 안의 **글자 조각**을 이어 본다
    (`f" WHERE {timefmt.sql_kst_day()} = $1"` 의 글자 부분).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs: set[int] = set()
    for n in ast.walk(tree):
        if not isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef)):
            continue
        body = getattr(n, "body", None) or []
        if body and isinstance(body[0], ast.Expr) and \
                isinstance(body[0].value, ast.Constant) and \
                isinstance(body[0].value.value, str):
            docs.add(id(body[0].value))
    out: list[tuple[int, str]] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) \
                and id(n) not in docs:
            out.append((n.lineno, n.value))
        elif isinstance(n, ast.JoinedStr):
            # 🔴 글자 조각 사이에 **자리표**를 넣는다 — 조각이 우연히 붙어
            #    `starts_kst::date` 처럼 읽히는 것을 막는다
            parts = [v.value if isinstance(v, ast.Constant)
                     and isinstance(v.value, str) else "\x00"
                     for v in n.values]
            out.append((n.lineno, "".join(parts)))
    return out


#: 🔴 **금지하는 꼴** — `starts_kst` 를 날짜와 **바로** 비교하는 SQL.
#   ⚠️ `AT TIME ZONE` 을 거친 꼴은 괄호 안에 들어 있어 `(…)::date` 가 되므로
#      `starts_kst::date` 와 글자가 다르다.
_BAD_SQL = re.compile(
    r"(?:\w+\.)?starts_(?:kst|local)\s*(?:::\s*date|[<>]=?\s*\$?\d*\s*::\s*date)",
    re.I)


def test_KST_날짜를_세션_시간대로_뽑지_않는다():
    """🔴🔴 **`starts_kst::date` 는 KST 날짜가 아니다** — 세션 시간대 날짜다."""
    bad: list[str] = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        for lineno, text in _sql_strings(p):
            if "starts_kst" not in text and "starts_local" not in text:
                continue
            for m in _BAD_SQL.finditer(text):
                bad.append(f"{p.relative_to(ROOT)}:{lineno} …{m.group(0)}…")
    assert not bad, (
        "🔴 `starts_kst` 를 날짜와 바로 비교한다 — **세션 시간대(UTC)** 로 "
        "돈다. `timefmt.sql_kst_day()` 를 써라:\n  " + "\n  ".join(bad))


def test_KST_날짜_조각이_한_곳에만_적혀_있다():
    """🔴 #1 사본 금지 — `AT TIME ZONE 'Asia/Seoul'` 을 손으로 적지 않는다.

    ⚠️ 실사고: `app/slate.py` 가 이 조각을 손으로 적고, 그 주석에 *"`main.py`·
       `sources.py` 가 이미 그 꼴을 쓰고 있었다"* 라고 적어 뒀다. 🔴 **둘 다
       안 쓰고 있었다** — 사본은 언제나 한 발 늦는다.
    """
    from app import timefmt
    owners: list[str] = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        for lineno, text in _sql_strings(p):
            if "AT TIME ZONE" in text.upper():
                owners.append(f"{p.relative_to(ROOT)}:{lineno}")
    stray = [o for o in owners if not o.startswith("app/timefmt.py")]
    assert not stray, (
        "🔴 `AT TIME ZONE` 을 적은 자리가 `app/timefmt.py` 밖에 있다 — "
        "`timefmt.sql_kst_day()`·`timefmt.SQL_TODAY_KST` 를 불러라:\n  "
        + "\n  ".join(stray))
    # 🔴 **원본이 비어 있지 않다** — 전부 지워도 초록이 되는 계약은 아무것도
    #    막지 않는다(⚠️ 이 세션이 반복해 당한 퇴로다)
    assert owners, "🔴 조각을 적은 자리가 **하나도 없다** — 원본이 사라졌다"
    # 🔴 그 하나가 **옳은 글자**를 만드는지 — 이름이고(오프셋이 아니고), KST 다
    assert timefmt.SQL_TZ == "Asia/Seoul"
    assert timefmt.sql_kst_day() == "(starts_kst AT TIME ZONE 'Asia/Seoul')::date"
    assert timefmt.sql_kst_day("g.starts_kst").startswith("(g.starts_kst AT TIME")


def test_수집기가_KST_로_속이지_않는다():
    """🔴🔴 **`.astimezone(KST)` 는 `timestamptz` 에서 아무 효과가 없다.**

    ⚠️ 수집기 일곱 곳이 그것을 넣고 있었고, 읽는 쪽은 *"이 칸에 KST 가 들어
       있다"* 고 믿었다. 🔴 그 믿음이 위 두 계약이 막는 병의 **뿌리**다.
    🔴 그래서 입구는 `timefmt.db_instant` **하나**다 — UTC 를 돌려준다.
    """
    bad: list[str] = []
    for p in sorted((ROOT / "app" / "collect").rglob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if not isinstance(n, ast.Dict):
                continue
            for k, v in zip(n.keys, n.values):
                if not (isinstance(k, ast.Constant)
                        and k.value in ("starts_kst", "starts_local")):
                    continue
                said = ast.unparse(v)
                if "astimezone" in said:
                    bad.append(f"{p.relative_to(ROOT)}:{n.lineno} "
                               f"{k.value} = {said[:60]}")
    assert not bad, (
        "🔴 `timestamptz` 칸에 `astimezone` 으로 **KST 를 넣는 척** 한다 — "
        "`timefmt.db_instant()` 를 써라:\n  " + "\n  ".join(bad))


def test_db_instant_가_UTC_를_돌려준다():
    """🔴 그 입구가 실제로 UTC 인가 — 반대 증거까지 센다."""
    from app import timefmt
    when = datetime(2026, 10, 5, 13, tzinfo=timezone.utc)
    got = timefmt.db_instant(when)
    assert got == when and got.utcoffset() == timedelta(0), got
    # 🔴 KST 로 들어온 값도 **같은 순간의 UTC** 로 나간다
    assert timefmt.db_instant(when.astimezone(timefmt.KST)) == when
    # 🔴 모르면 멈춘다 — naive 를 UTC 라고 가정하지 않는다
    with pytest.raises(ValueError, match="시간대 없는"):
        timefmt.db_instant(datetime(2026, 10, 5, 13))
