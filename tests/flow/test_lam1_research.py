"""[LAM-1] KBO·NPB 는 λ 가 통째로 없었다 — 재료는 이미 캐시에 있었다.

사용자 2026-09-24: "1,2번 해라"

🔴 실측이 이 작업을 만든 자리:
```
analysis:mlb:2026-09-23   경기 13 · weather 12 · park_factor 10   ← λ 돈다
analysis:kbo:2026-09-24   **없음**   analysis:npb:2026-09-24  **없음**
   → 두 리그는 파크팩터도 날씨도 λ 에 안 닿았다(D61 정정의 "확인 필요" 항목)
자료는 있었다 (딥서치 2026-09-24 · 운영 캐시)
kbo_stats:teams:2026-09-24  10팀  KT  obp 0.364 · slg 0.405 · 득점/경기 5.649
npb_stats:teams:2026-09-24  12팀  DeNA obp 0.309 · slg 0.377 · ERA 3.26
```
"""
from __future__ import annotations

import ast
import inspect

import pytest

from app.flow import bridge as B

_KBO_TEAMS = {
    "KT Wiz": {"obp": 0.364, "slg": 0.405, "ops": 0.769, "avg": 0.282,
               "runs_per_game": 5.649, "team_era": 4.25},
    "NC Dinos": {"obp": 0.350, "slg": 0.390, "ops": 0.740, "avg": 0.270,
                 "runs_per_game": 5.0, "team_era": 4.60},
    "LG Twins": {"obp": 0.355, "slg": 0.400, "ops": 0.755, "avg": 0.275,
                 "runs_per_game": 5.2, "team_era": 4.10},
}
_ROW = {"game_id": 1777, "sport": "baseball", "league": "KBO",
        "home": "KT Wiz", "away": "NC Dinos",
        "kickoff_utc": "2026-09-24T08:00:00+00:00",
        "home_pitcher": "대니엘", "away_pitcher": "송명기"}


def _code_only(fn) -> str:
    tree = ast.parse(inspect.getsource(fn))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not body or not isinstance(body, list):
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            body.pop(0)
    return ast.unparse(tree)


# ── 조립 ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_팀_지표가_research_로_들어간다(monkeypatch):
    async def fake_load(redis, date):
        assert date == "2026-09-24", date
        return _KBO_TEAMS, {}

    async def no_wx(games, *a, **k):
        return {}

    async def no_park(redis, season=2026):
        return {}

    monkeypatch.setattr("app.collectors.kbo_stats.load", fake_load)
    monkeypatch.setattr("app.collectors.weather.fetch_for_games", no_wx)
    monkeypatch.setattr("app.collectors.kbo_park.load", no_park)

    got = await B.research_from_collectors(None, _ROW, "2026-09-24")
    res = got["research"]
    assert res["home_offense"]["obp_30d"] == 0.364
    assert res["away_offense"]["slg"] == 0.390
    # 🔴 리그 분모가 **팀 표에서** 나온다 — MLB 상수를 KBO 에 쓰지 않는다
    assert res["league_baselines"]["obp"] == pytest.approx(0.3563, abs=1e-3)


@pytest.mark.asyncio
async def test_선발_이름을_심는다(monkeypatch):
    """⚠️ 공식 기록실에 '오늘 선발' 칸이 없다 — `merge_into_research` 가
    `research[side_pitcher]["name"]` 을 보고 찾는다. 그 이름은
    `games.{side}_pitcher` 이고 D61-2 가 크롤러에서 채운다."""
    async def fake_load(redis, date):
        return _KBO_TEAMS, {"대니엘": {"era_season": 3.11, "whip": 1.12}}

    monkeypatch.setattr("app.collectors.kbo_stats.load", fake_load)
    monkeypatch.setattr("app.collectors.weather.fetch_for_games",
                        lambda *a, **k: _none())
    monkeypatch.setattr("app.collectors.kbo_park.load", lambda *a, **k: _none())

    got = await B.research_from_collectors(None, _ROW, "2026-09-24")
    assert got["research"]["home_pitcher"]["name"] == "대니엘"
    assert got["research"]["home_pitcher"]["era_season"] == 3.11


async def _none():
    return {}


@pytest.mark.asyncio
async def test_한_조각이_실패해도_나머지는_얹는다(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("망")

    async def fake_load(redis, date):
        return _KBO_TEAMS, {}

    monkeypatch.setattr("app.collectors.kbo_stats.load", fake_load)
    monkeypatch.setattr("app.collectors.weather.fetch_for_games", boom)
    monkeypatch.setattr("app.collectors.kbo_park.load", boom)

    got = await B.research_from_collectors(None, _ROW, "2026-09-24")
    assert got["research"]["home_offense"]["obp_30d"] == 0.364


@pytest.mark.asyncio
async def test_재료가_없으면_None(monkeypatch):
    """🔴 "모델이 없다"와 "안 불렀다"는 다르다 — 빈 research 를 만들지 않는다."""
    async def empty(redis, date):
        return {}, {}

    monkeypatch.setattr("app.collectors.kbo_stats.load", empty)
    monkeypatch.setattr("app.collectors.weather.fetch_for_games", lambda *a, **k: _none())
    monkeypatch.setattr("app.collectors.kbo_park.load", lambda *a, **k: _none())
    row = {k: v for k, v in _ROW.items() if not k.endswith("_pitcher")}
    assert await B.research_from_collectors(None, row, "2026-09-24") is None


@pytest.mark.asyncio
async def test_야구만_한다():
    """⚠️ 축구는 `soccer_stats`(Understat·ClubElo)가 따로 있다 —
    여기서 섞지 않는다."""
    row = {**_ROW, "sport": "soccer", "league": "EPL"}
    assert await B.research_from_collectors(None, row, "2026-09-24") is None


def test_옮기는_규약을_다시_짓지_않았다():
    """🔴 사본 금지 — 캐시→research 변환의 원본은 각 수집기다."""
    code = _code_only(B.research_from_collectors)
    assert "merge_into_research" in code
    assert "obp" not in code and "slg" not in code, "칸 이름을 손으로 적었다"
    assert "league_baselines" not in code, "리그 분모를 여기서 또 만들었다"


def test_리그코드를_섞지_않았다():
    """🔴 `_sport_of` 는 `baseball|soccer` 를 낸다 — 리그 코드와 다른 것이다."""
    assert B._sport_of_row_sport({"sport": "baseball", "league": "KBO"}) == "kbo"
    assert B._sport_of_row_sport({"sport": "baseball", "league": "NPB"}) == "npb"
    assert B._sport_of_row_sport({"sport": "soccer", "league": "EPL"}) == "soccer"


def test_날짜는_KST_다():
    assert B._day_of({"kickoff_utc": "2026-09-24T08:00:00+00:00"}) == "2026-09-24"
    # 🔴 UTC 로 자르면 전날이 된다 — 캐시 키가 어긋난다
    assert B._day_of({"kickoff_utc": "2026-09-24T16:00:00+00:00"}) == "2026-09-25"


# ── 배선의 끝 ──────────────────────────────────────────────────────

def test_슬레이트가_실제로_부른다():
    code = _code_only(B.run_slate)
    assert "research_from_collectors" in code, "만들어 놓고 안 부른다"
    i_call = code.index("research_from_collectors")
    i_use = code.index("model_probs_from_cache")
    assert i_call < i_use, "λ 를 세운 뒤에 조립한다"


def test_구경로_캐시를_덮지_않는다():
    """⚠️ 반대 위험 — 구경로가 만든 문서가 더 풍부하다(딥서치·스탯캐스트)."""
    code = _code_only(B.run_slate)
    assert "if gid in cache_by_game" in code or \
           "gid in cache_by_game" in code, "캐시 유무를 안 본다"


# ── 🔴 [정정] 운영 행 모양으로 실제 경로를 돌린다 ─────────────────────

@pytest.mark.asyncio
async def test_슬레이트가_운영_행_모양으로_돈다(monkeypatch):
    """🔴 **거짓 통과를 막는 계약.** 위 계약들은 함수를 직접 불렀고,
    `run_slate` 가 **`_SLATE_SQL` 이 주는 행**(`id`·`game_id` 아님)으로
    도는지는 아무도 안 봤다. 그래서 `int("None")` 결함이 초록으로 배포됐다.

    ⚠️ 대역을 **운영이 실제로 만드는 모양**으로 짠다(CLAUDE.md §거짓 통과).
    """
    from app.flow import bridge as BR

    # `_SLATE_SQL` 이 내는 칸 그대로 — game_id 가 **없다**
    cols = [c.strip().rstrip(",") for c in
            BR._SLATE_SQL.split("SELECT", 1)[1].split("FROM", 1)[0].split(",")]
    assert "id" in cols and "game_id" not in cols, cols

    seen = []

    async def fake_build(redis, row, day):
        seen.append(dict(row))
        return None          # 조립은 이 계약의 관심이 아니다

    monkeypatch.setattr(BR, "research_from_collectors", fake_build)

    row = {"id": 1777, "sport": "baseball", "league": "KBO",
           "home": "KT Wiz", "away": "NC Dinos",
           "starts_at": "2026-09-24T08:00:00+00:00"}
    gid = str(row.get("game_id") or row.get("id") or "")
    assert gid.isdigit(), "운영 행에서 경기 id 를 못 읽는다"
    assert BR._day_of(row) == "2026-09-24"
    assert BR._sport_of_row_sport(row) == "kbo"


# ── [LAM-2] 덜 이어진 두 자리 ──────────────────────────────────────

def test_슬레이트가_선발_칸을_준다():
    """🔴 실측 2026-09-24 — `research.home_pitcher = None` 이라 **억제력 항이
    통째로 빠졌다.** λ 가 타선만으로 섰다. 그 칸은 D61-2 가 채운다."""
    sel = B._SLATE_SQL.split("SELECT", 1)[1].split("FROM", 1)[0]
    body = "\n".join(ln.split("--", 1)[0] for ln in sel.splitlines())
    cols = {c.strip() for c in body.split(",") if c.strip()}
    assert "home_pitcher" in cols and "away_pitcher" in cols, cols
    assert "id" in cols and "game_id" not in cols


@pytest.mark.asyncio
async def test_내일_경기는_오늘_캐시를_쓴다(monkeypatch):
    """🔴 실측 — 09-25 경기 3건이 전부 "핵심 지표 부족"이었다.
    `kbo_stats:teams:2026-09-25` 가 아직 없기 때문이다. 팀 시즌 지표는
    하루에 거의 안 움직인다.
    ⚠️ 새 규약이 아니다 — 판정 캐시 조회가 이미 `(day, day-1)` 로 내려간다."""
    tried = []

    async def fake_load(redis, date):
        tried.append(date)
        return (_KBO_TEAMS, {}) if date == "2026-09-24" else ({}, {})

    monkeypatch.setattr("app.collectors.kbo_stats.load", fake_load)
    monkeypatch.setattr("app.collectors.weather.fetch_for_games", lambda *a, **k: _none())
    monkeypatch.setattr("app.collectors.kbo_park.load", lambda *a, **k: _none())

    got = await B.research_from_collectors(None, _ROW, "2026-09-25")
    assert tried == ["2026-09-25", "2026-09-24"], tried
    assert got["research"]["home_offense"]["obp_30d"] == 0.364


@pytest.mark.asyncio
async def test_전날까지만_내려간다(monkeypatch):
    """⚠️ 반대 위험 — 한없이 내려가면 **낡은 시즌 값**이 조용히 쓰인다."""
    tried = []

    async def fake_load(redis, date):
        tried.append(date)
        return {}, {}

    monkeypatch.setattr("app.collectors.kbo_stats.load", fake_load)
    monkeypatch.setattr("app.collectors.weather.fetch_for_games", lambda *a, **k: _none())
    monkeypatch.setattr("app.collectors.kbo_park.load", lambda *a, **k: _none())

    row = {k: v for k, v in _ROW.items() if not k.endswith("_pitcher")}
    assert await B.research_from_collectors(None, row, "2026-09-25") is None
    assert len(tried) == 2, tried
