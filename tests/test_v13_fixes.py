"""[v1.3] 상태 결함 3건 + 재료 대칭화 — **결함별 재현 → 수정 → 재현불가**.

이 파일의 테스트는 전부 2026-09-02 슬레이트에서 실제로 터진 것이다.
각 테스트는 "옛 규칙이면 실패하고 새 규칙이면 통과함"을 함께 보인다.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest


# ─────────────── A-1. 라인업 확정 단일 저장소 ───────────────

def test_reproduce_npb_regression_with_the_old_time_rule():
    """🔴 재현: NPB 창은 T-30인데 타순이 T-44에 오면 옛 규칙은 'predicted'.

    2026-09-02 17:16 에 정확히 이 일이 벌어졌고, 17:51(T-9)에 "라인업 미확정 —
    관망" 카드 4장이 나갔다. 같은 경기가 17:35 에는 T6(확정일 때만 발동)를
    통과한 상태였다 — 두 저장소가 서로 다른 말을 하고 있었다.
    """
    from app.pipeline import is_final_window

    now = datetime.now(UTC)
    arrived_at_t44 = now + timedelta(minutes=44)
    # 옛 규칙: 시각으로 판정 → NPB 창(T-30) 밖이라 미확정
    assert is_final_window(arrived_at_t44, now, sport="npb") is False


def test_new_rule_confirms_on_nine_names_regardless_of_time():
    """수정: 확정의 정의는 **타순 9명 유무** 하나다. 시각은 안 본다."""
    from app.engine.pregame_push import lineup_confirmed

    nine = "-".join(f"선수{i}(포)" for i in range(1, 10))
    eight = "-".join(f"선수{i}(포)" for i in range(1, 9))
    assert lineup_confirmed(nine, nine) is True      # T-44든 T-9든 동일
    assert lineup_confirmed(nine, eight) is False    # 한쪽만 오면 미확정
    assert lineup_confirmed("", "") is False


def test_hyphenated_names_do_not_break_confirmation():
    """`Pete Crow-Armstrong` 이 10조각으로 갈려 확정을 놓치면 안 된다."""
    from app.engine.lineup_diff import NAME_REGISTRY, register_names
    from app.engine.pregame_push import lineup_confirmed

    before = set(NAME_REGISTRY)
    try:
        register_names({"Pete Crow-Armstrong"})
        order = ("Pete Crow-Armstrong-B-C-D-E-F-G-H-I")   # 9명
        assert lineup_confirmed(order, order, NAME_REGISTRY) is True
    finally:
        NAME_REGISTRY.clear()
        NAME_REGISTRY.update(before)


def test_promotion_marks_the_row_for_db_sync():
    """🔴 캐시만 올리면 두 저장소가 어긋난다 — DB 원본에 밀어 넣을 표시를 남긴다."""
    from app.pipeline import promote_lineup_status

    nine = "-".join(f"P{i}(포)" for i in range(9))
    jg = {"sport": "kbo", "game_id": 1, "lineup_status": "none"}
    research = {"home_lineup": {"order": nine}, "away_lineup": {"order": nine}}
    assert promote_lineup_status(research, jg, "크롤러") is True
    assert jg["lineup_status"] == "confirmed"
    assert jg["_lineup_promoted"] is True, "DB 반영 표시가 없으면 또 어긋난다"


@pytest.mark.asyncio
async def test_sync_writes_to_db_once_and_never_downgrades():
    from app.pipeline import sync_lineup_status

    calls = []

    class Pool:
        async def execute(self, sql, *a):
            calls.append((sql, a))

    jg = {"game_id": 7, "_lineup_promoted": True}
    assert await sync_lineup_status(Pool(), jg) is True
    assert "lineup_status = 'confirmed'" in calls[0][0]
    assert "<> 'confirmed'" in calls[0][0], "이미 확정이면 건드리지 않는다"
    # 표시가 소비돼 두 번 쓰지 않는다
    assert await sync_lineup_status(Pool(), jg) is False


# ─────────────── A-2. 배당 재부착 ───────────────

@pytest.mark.asyncio
async def test_reproduce_odds_never_attached_after_late_ingest(monkeypatch):
    """🔴 재현: 분석 캐시 14:12 · 배당 적재 17:01 → 재판정이 배당을 안 붙였다.

    2026-09-02 KBO 5경기 전부 "가치 배당 미수집" 으로 나갔다. DB 에는 있었다.
    """
    import app.pipeline as P

    async def fake_probs(pool, gid, home, away):
        return None, {"Doosan Bears": 1.71, "LG Twins": 2.15}

    monkeypatch.setattr(P, "_market_probs", fake_probs)
    jg = {"game_id": 1, "home": "Doosan Bears", "away": "LG Twins"}
    assert jg.get("best_odds") is None          # 판정 시점엔 없었다
    assert await P.refresh_odds_for_game(object(), jg) is True
    assert jg["best_odds"]["Doosan Bears"] == 1.71


@pytest.mark.asyncio
async def test_odds_refresh_never_invents_a_value(monkeypatch):
    """배당이 없으면 아무것도 하지 않는다 — 없는 값을 만들지 않는다."""
    import app.pipeline as P

    async def empty(pool, gid, home, away):
        return None, {}

    monkeypatch.setattr(P, "_market_probs", empty)
    jg = {"game_id": 1, "home": "H", "away": "A"}
    assert await P.refresh_odds_for_game(object(), jg) is False
    assert "best_odds" not in jg


def test_odds_refresh_runs_before_picks_are_built():
    """순서가 규율이다 — 픽이 `best_odds` 를 읽어 가치·EV 를 만든다."""
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    seg = src[src.index("async def rejudge_after_lineup"):]
    seg = seg[:seg.index("async def ensure_game_fresh")]
    # ⚠️ 주석 안의 `_compute_picks` 문자열이 먼저 잡힌다 — **실제 호출**만 본다.
    call = seg.index("_compute_picks(\n")
    assert seg.index("await refresh_odds_for_game") < call


# ─────────────── A-3. max_tokens 절단 ───────────────

def test_reproduce_truncation_headroom_was_too_thin():
    """🔴 재현: 성공 output 3661~3789 인데 상한이 4000이었다 — 여유 200토큰.

    output=4000 stop=max_tokens 로 잘린 응답이 JSON 파싱 2회 실패 →
    KIA@NC 판정 탈락(2026-09-02).
    """
    from app.config import Settings

    s = Settings(_env_file=None)
    observed_max_success = 3789
    assert s.matchup_max_tokens >= observed_max_success * 1.5, "여유가 얇다"
    # 딥서치는 기사 본문이 얹혀 더 필요하다 — 불변식 유지
    assert s.deepsearch_max_tokens > s.matchup_max_tokens


def test_truncated_response_retries_with_a_bigger_budget():
    """절단이면 **한도를 올려** 재시도한다 — "짧게 쓰라"가 아니라."""
    from pathlib import Path

    src = Path("app/engine/matchup.py").read_text(encoding="utf-8")
    assert "budget = min(budget * 2, MAX_TOKENS_CEILING)" in src
    assert "truncated" in src
    from app.engine.matchup import MAX_TOKENS_CEILING

    assert MAX_TOKENS_CEILING <= 16000, "SDK 비스트리밍 거부 사고 이력"


# ─────────────── B. 재료 대칭화 ───────────────

def test_starter_season_is_no_longer_mlb_only():
    """🔴 자료7 이 MLB 전용이라 KBO·NPB 는 표본 부족을 보정할 수 없었다.

    실측 2026-09-02 LG@두산: "김윤식은 선발등판 0경기 → 대표성 없음" 에서 멈췄다.
    """
    from pathlib import Path

    src = Path("app/collectors/starter_season.py").read_text(encoding="utf-8")
    assert 'if (jg.get("sport") or "") != "mlb":' not in src
    assert 'sport not in ("mlb", "kbo", "npb")' in src


def test_asia_starter_line_has_the_same_shape_as_mlb():
    """프롬프트가 리그를 구분하지 않으려면 **모양이 같아야** 한다."""
    from app.collectors.starter_season import slim_asia, slim_season

    asia = slim_asia(era="3.55", ip="101 1/3", g="18")
    mlb = slim_season({"era": "3.55", "inningsPitched": "101.1",
                       "gamesStarted": 18, "whip": "1.20"})
    assert "ERA" in asia and "ERA" in mlb
    assert "이닝" in asia and "이닝" in mlb


def test_mlb_bullpen_uses_the_same_basis_as_kbo_npb():
    """⚠️ KBO·NPB 는 `team_era`(팀 투수 방어율)를 자료9 에 넣는다.

    MLB 만 구원 전용 ERA 를 쓰면 리그 간 비교가 거짓이 된다.
    """
    from pathlib import Path

    for path, needle in (("app/collectors/naver_kbo.py", "team_era"),
                         ("app/collectors/npb_stats.py", "team_era"),
                         ("app/collectors/mlb_team_pitching.py", '"era"')):
        src = Path(path).read_text(encoding="utf-8")
        assert needle in src and "_bullpen" in src


@pytest.mark.asyncio
async def test_mlb_bullpen_never_overwrites_an_existing_source(monkeypatch):
    """다른 소스가 이미 채웠으면 덮지 않는다."""
    from app.collectors import mlb_team_pitching as mtp

    async def table(season, redis=None):
        return {"H": {"era": 9.99}}

    monkeypatch.setattr(mtp, "fetch", table)
    jg = {"sport": "mlb", "home": "H", "away": "A",
          "research": {"home_bullpen": {"era": 3.10}}}
    await mtp.attach(jg)
    assert jg["research"]["home_bullpen"]["era"] == 3.10


def test_all_three_leagues_reach_the_same_prompt_slots():
    """세 리그가 **같은 자리**를 채운다 — 어느 것은 되고 어느 것은 안 되면 안 된다."""
    from pathlib import Path

    season = Path("app/collectors/starter_season.py").read_text(encoding="utf-8")
    pen = Path("app/pipeline.py").read_text(encoding="utf-8")
    assert "_starter_season" in season          # 자료7 · 세 리그
    assert "mlb_team_pitching" in pen           # 자료9 · MLB 보강


# ─────────────── D. 동결 선언 ───────────────

def test_freeze_is_declared_where_every_session_reads_it():
    """규율이 코드에만 있으면 다음 세션이 또 만진다."""
    from pathlib import Path

    md = Path("CLAUDE.md").read_text(encoding="utf-8")
    assert "v1.3 동결" in md
    assert "리그별 `graded` 50건" in md
    assert "발송 중단급 P0" in md


@pytest.mark.asyncio
async def test_freeze_counter_starts_from_todays_slate():
    """⚠️ 9/3 이전 기록은 판정 설계가 계속 바뀌던 구간이라 같은 시스템이 아니다."""
    from app.engine.daily_summary import FREEZE_TARGET, freeze_progress_lines

    seen = {}

    class Pool:
        async def fetch(self, sql, *a):
            seen["sql"], seen["args"] = sql, a
            return [{"sport": "kbo", "n": 3}, {"sport": "npb", "n": 5}]

    lines = await freeze_progress_lines(Pool(), ("kbo", "npb"))
    assert FREEZE_TARGET == 50
    # ⚠️ 시작일은 **인자**로 간다(리그마다 다르다). SQL 문자열이 아니라
    #    실제로 넘어간 값을 본다 — 리터럴을 찾으면 파라미터화에 깨진다.
    assert seen["args"][1] == ["2026-09-03", "2026-09-03"], \
        "이전 표본이 섞이면 안 된다"
    assert "graded_at IS NOT NULL" in seen["sql"] and "NOT l.void" in seen["sql"]
    assert "KBO 3/50" in lines[0] and "NPB 5/50" in lines[0]
