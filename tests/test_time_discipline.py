"""시간 원칙 — 내부 표준은 UTC, naive datetime 금지.

나라·리그·사이트마다 시간대가 달라서 나는 버그를 원천 차단한다.
경계에서만 변환한다: ① 수집 시 소스 현지 시각 → UTC 저장 ② 표시 시 UTC → KST.
그 밖에서는 어떤 로컬 시간도 다루지 않는다.
"""
import ast
import pathlib
import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = sorted(p for p in (ROOT / "app").rglob("*.py") if "__pycache__" not in str(p))

KST = ZoneInfo("Asia/Seoul")
JST = ZoneInfo("Asia/Tokyo")
ET = ZoneInfo("America/New_York")


# ─────────────────────────────────────────────── ① 소스 검사 (lint 수준 방어)

def _calls(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def test_no_naive_now_or_today():
    """`datetime.now()` / `utcnow()` / `.today()` — 서버 로컬시간 의존.

    ⚠️ 소스 **텍스트**가 아니라 AST를 본다. 주석·독스트링에서 이 이름을
       설명만 해도 걸리면, 규율을 적어두는 일 자체가 벌을 받는다.
    """
    bad = []
    for p in SRC:
        for node in _calls(ast.parse(p.read_text(encoding="utf-8"))):
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            where = f"{p.relative_to(ROOT)}:{node.lineno}"
            if name == "now" and not node.args and not node.keywords:
                bad.append(f"{where} now() — tz 인자 없음")
            elif name == "utcnow":
                bad.append(f"{where} utcnow() — naive, deprecated")
            elif name == "today":
                bad.append(f"{where} today() — 서버 로컬 날짜")
    assert not bad, "naive/서버로컬 시간 사용:\n  " + "\n  ".join(bad)


def test_no_hardcoded_interleague_offsets():
    """리그 간 시차를 상수로 박지 않는다 — DST가 있으면 반드시 틀린다."""
    bad = []
    pat = re.compile(r"timedelta\(hours\s*=\s*(?:13|14|9)\)")
    for p in SRC:
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line) and "ZoneInfo" not in line:
                bad.append(f"{p.relative_to(ROOT)}:{i} {line.strip()}")
    assert not bad, "시차 하드코딩:\n  " + "\n  ".join(bad)


def test_statsapi_gamedate_is_parsed_as_utc_without_reconversion():
    """statsapi gameDate는 이미 UTC(Z)다 — 오프셋을 다시 적용하면 안 된다."""
    src = (ROOT / "app/collectors/mlb.py").read_text(encoding="utf-8")
    i = src.index('"starts_at": datetime.fromisoformat(')
    line = src[i:src.index("\n", i)]
    assert 'g["gameDate"].replace("Z", "+00:00")' in line, line
    # 파싱 뒤에 tz를 덮어쓰거나 시간을 더하는 코드가 붙으면 안 된다
    after = src[i:i + 400]
    for banned in ("tzinfo=KST", "tzinfo=ZoneInfo", "+ timedelta(hours"):
        assert banned not in after, f"gameDate에 재변환이 붙었다: {banned}"


def test_league_ingest_attaches_source_timezone():
    """수집 경계에서 소스 타임존을 붙여 UTC로 저장한다."""
    kbo = (ROOT / "app/collectors/kbo.py").read_text(encoding="utf-8")
    assert 'ZoneInfo("Asia/Seoul")' in kbo and "astimezone(UTC)" in kbo
    npb = (ROOT / "app/collectors/yahoo_npb.py").read_text(encoding="utf-8")
    assert 'ZoneInfo("Asia/Tokyo")' in npb and "astimezone(UTC)" in npb


# ─────────────────────────────────────────────── ② 변환 왕복

@pytest.mark.parametrize("tz,local,expect_utc", [
    (KST, "2026-08-30T18:30:00", "2026-08-30T09:30:00+00:00"),   # KBO
    (JST, "2026-08-30T14:00:00", "2026-08-30T05:00:00+00:00"),   # NPB 데이게임
    (JST, "2026-08-30T18:00:00", "2026-08-30T09:00:00+00:00"),   # NPB 나이터
])
def test_local_to_utc_roundtrip(tz, local, expect_utc):
    aware = datetime.fromisoformat(local).replace(tzinfo=tz)
    utc = aware.astimezone(UTC)
    assert utc.isoformat() == expect_utc
    assert utc.astimezone(tz).isoformat() == aware.isoformat()


def test_mlb_gamedate_utc_is_not_shifted():
    """ISO8601 Z 를 신뢰해 파싱하면 KST 표시가 저절로 맞는다."""
    got = datetime.fromisoformat("2026-08-30T23:05:00Z".replace("Z", "+00:00"))
    assert got == datetime(2026, 8, 30, 23, 5, tzinfo=UTC)
    assert got.astimezone(KST).isoformat() == "2026-08-31T08:05:00+09:00"
    # 미국 DST 경계 — statsapi가 UTC를 주므로 우리가 할 일이 없다
    winter = datetime.fromisoformat("2026-11-05T00:10:00+00:00")
    assert winter.astimezone(ET).utcoffset().total_seconds() == -5 * 3600
    summer = datetime.fromisoformat("2026-08-30T23:05:00+00:00")
    assert summer.astimezone(ET).utcoffset().total_seconds() == -4 * 3600


# ─────────────────────────────────────────────── ③ NPB 개시 시각 파싱

def test_npb_schedule_parses_per_game_start_time():
    """전 경기 18:00 고정은 T-기준 트리거를 무너뜨린다 (실조회 2026-08-30)."""
    from app.collectors.yahoo_npb import parse_schedule

    html = (
        '<a href="/npb/game/1/top">横浜 DeNA 中日 18:00 見どころ (予)篠木</a>'
        '<a href="/npb/game/2/top">京セラD大阪 オリックス ソフトバンク 14:00 (先)曽谷</a>'
        '<a href="/npb/game/3/top">ベルーナドーム 西武 楽天 17:00 (予)武内</a>'
        '<a href="/npb/game/4/top">エスコンF ライブ配信中 日本ハム ロッテ 0 - 2 1回表</a>'
    )
    by_id = {g["game_id"]: g for g in parse_schedule(html)}
    assert by_id["1"]["start_hhmm"] == "18:00"
    assert by_id["2"]["start_hhmm"] == "14:00"
    assert by_id["3"]["start_hhmm"] == "17:00"
    # 이미 시작한 경기는 시각 대신 스코어·이닝이 실린다 → None (폴백은 호출부)
    assert by_id["4"]["start_hhmm"] is None
    assert by_id["2"]["starters_confirmed"] is True
    assert by_id["1"]["starters_confirmed"] is False


def test_npb_upsert_uses_parsed_time_not_fixed_1800():
    """upsert_schedule 이 파싱된 시각을 쓰는지 — 소스 텍스트로 고정."""
    src = (ROOT / "app/collectors/yahoo_npb.py").read_text(encoding="utf-8")
    i = src.index("async def upsert_schedule")
    body = src[i:src.index("\nasync def ", i + 10)] if "\nasync def " in src[i + 10:] else src[i:]
    assert 'g.get("start_hhmm")' in body, "파싱된 개시 시각을 쓰지 않는다"
    assert 'f"{date}T18:00:00"' not in body, "18:00 하드코딩이 남아 있다"


# ─────────────────────────────────────────────── ④ AST — naive datetime 생성

def test_no_naive_datetime_literals():
    """`datetime(2026, 8, 30, 18, 0)` 처럼 tzinfo 없는 생성 금지."""
    bad = []
    for p in SRC:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and getattr(node.func, "id", None) == "datetime"):
                continue
            if len(node.args) < 4:          # date만 만드는 건 tz가 의미 없다
                continue
            if not any(k.arg == "tzinfo" for k in node.keywords):
                bad.append(f"{p.relative_to(ROOT)}:{node.lineno} "
                           f"{ast.unparse(node)[:60]}")
    assert not bad, "tzinfo 없는 datetime 생성:\n  " + "\n  ".join(bad)
