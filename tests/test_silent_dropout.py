"""[부류 차단] 오늘 KBO 고장은 "경기가 조회에서 사라지면 아무도 모른다"였다.

  17:54  잡 executed successfully
  17:54  워치독 이상 없음
  17:54  카드 0장
셋이 동시에 참이었다. 경기가 `status='scheduled'` 에서 빠지면 **미발송으로도
안 잡힌다** — 대상 목록 자체가 비기 때문이다.

원인(0-0 플레이스홀더)은 KBO 파서에서 막았고, 이 파일은 **부류**를 막는다.
"""
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCHED = Path("app/scheduler.py").read_text(encoding="utf-8")
WATCH = Path("app/watchdog.py").read_text(encoding="utf-8")


# ═════════ ① 소스별로 "경기 전 live" 가 가능한가 ═════════

def test_npb_live_requires_positive_evidence_of_having_started():
    """🔴 [계약 갱신 2026-09-07] NPB 도 이제 `live` 를 낸다.

    종전 계약은 "NPB 는 live 가 아예 없어 구조적으로 안전하다"였다. 그런데
    그 안전은 **거짓말로 산 것**이었다 — 이미 시작한 경기를 `scheduled` 로
    넣고 18:00 을 지어냈다. 그래서 09-06(토) 13:00 에 끝난 두 경기가
    "오늘 18:00 예정"으로 슬레이트에 들어와 판정·타순까지 만들어졌고,
    우천취소된 경기에는 픽 카드가 나갔다.

    이제 `live` 를 내되, **시작의 적극적 증거가 있을 때만** 낸다 —
    시각을 못 읽었다는 이유로 경기를 떨구면 그것이 조용한 누락이다.
    (KBO 의 `_has_started` 가드와 같은 정신이다.)
    """
    from app.collectors.yahoo_npb import _state_of

    src = Path("app/collectors/yahoo_npb.py").read_text(encoding="utf-8")
    assert 'status = "live"' in src
    # 증거가 있을 때만 started
    assert _state_of("甲子園 阪神 DeNA 1 - 4 試合終了", None) == "started"
    assert _state_of("エスコンF ライブ配信中 日本ハム 0 - 2 1回表", None) == "started"
    assert _state_of("神宮 ヤクルト 中日 - 試合中止", None) == "cancelled"
    # 🔴 모르면 예정으로 남긴다 — 슬레이트에서 조용히 떨구지 않는다
    assert _state_of("神宮 ヤクルト 巨人", None) == "scheduled"
    assert _state_of("神宮 ヤクルト 巨人 18:00", "18:00") == "scheduled"


def test_mlb_status_comes_from_the_authoritative_field():
    """MLB 는 점수가 아니라 `abstractGameState` 를 읽는다 — 플레이스홀더 무관."""
    src = Path("app/collectors/mlb.py").read_text(encoding="utf-8")
    assert '"Preview": "scheduled", "Live": "live", "Final": "final"' in src


def test_kbo_live_requires_the_game_to_have_started():
    """KBO 만 점수로 판단한다 — 그래서 시작 여부 가드가 붙어야 한다."""
    src = Path("app/collectors/kbo.py").read_text(encoding="utf-8")
    i = src.index('else "live" if')
    assert "_has_started" in src[i:i + 200], "live 판정에 시작 여부가 안 걸려 있다"


# ═════════ ② 감시는 폴링과 **다른 눈**으로 세는가 ═════════

def test_invisible_check_does_not_filter_by_scheduled():
    """🔴 핵심. 같은 눈으로 감시하면 폴링이 못 보는 것을 감시도 못 본다."""
    i = WATCH.index("async def check_invisible_games")
    seg = WATCH[i:WATCH.index("\nasync def ", i + 10)]
    # ⚠️ `FILTER (WHERE status='scheduled')` 는 **세는 식**이지 거르는 조건이
    #    아니다. 구분해서 봐야 한다 — 넓게 잡으면 올바른 구현을 반려한다.
    where = seg[seg.index("WHERE sport = ANY"):seg.index("GROUP BY sport")]
    assert "status" not in where, \
        f"감시가 폴링과 같은 조건으로 거른다 — 맹점이 그대로다: {where}"
    assert "FILTER (WHERE status = 'scheduled') AS visible" in seg, \
        "보이는 수를 따로 세지 않으면 '0건'을 알 수 없다"


def test_invisible_check_is_registered_in_run_checks():
    assert '("invisible", check_invisible_games(pool, redis))' in WATCH


def test_alert_code_is_registered():
    from app.alerts import WATCHDOG_CODES

    assert "W-GAME-INVISIBLE" in WATCHDOG_CODES


# ═════════ ③ 복구가 **상시**로 도는가 (기동 1회로는 부족했다) ═════════

def test_repair_runs_every_watchdog_cycle_not_just_at_boot():
    """🔴 오늘은 오염이 17:42 에 생겼고 **내가 손으로 재기동해서** 풀렸다.

    평상시엔 재기동할 이유가 없다 — 그러면 저녁 내내 침묵했을 것이다.
    """
    assert "_repair_impossible_live" in WATCH, "워치독이 복구를 안 부른다"
    i = WATCH.index("async def check_invisible_games")
    seg = WATCH[i:WATCH.index("\nasync def ", i + 10)]
    assert "await _repair_impossible_live(pool)" in seg


def test_repair_still_runs_at_boot_too():
    """기동 복구도 남긴다 — 다운타임 중 생긴 오염을 즉시 푼다."""
    assert SCHED.count("await _repair_impossible_live(pool)") == 1


def test_repair_returns_rows_so_the_alarm_can_name_games():
    """복구만 하고 조용하면 "왜 갑자기 나왔지"를 설명할 수 없다."""
    seg = SCHED[SCHED.index("async def _repair_impossible_live"):]
    seg = seg[:seg.index("\nasync def ", 10)]
    assert "-> list[dict]" in SCHED[SCHED.index("async def _repair_impossible_live"):
                                    SCHED.index("async def _repair_impossible_live") + 120]
    assert "return [dict(r) for r in rows]" in seg


# ═════════ ④ 불변식 자체 ═════════

@pytest.mark.parametrize("status,future,repaired", [
    ("live", True, True),        # 시작 전 live — 오늘의 고장
    ("live", False, False),      # 시작 후 live — 정상
    ("scheduled", True, False),
    ("final", False, False),
])
def test_invariant_is_exactly_one_condition(status, future, repaired):
    seg = SCHED[SCHED.index("async def _repair_impossible_live"):]
    seg = seg[:seg.index("\nasync def ", 10)]
    assert "status = 'live' AND starts_at > now()" in seg
    assert (status == "live" and future) == repaired


class _Pool:
    """복구 0건 + 전 경기 비정상 상태 → 경보가 떠야 한다."""

    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, sql, *a):
        if "UPDATE games" in sql:
            return []
        return self._rows


@pytest.mark.asyncio
async def test_alarm_fires_when_no_game_is_visible(monkeypatch):
    from app import watchdog as W

    pool = _Pool([{"sport": "kbo", "total": 5, "visible": 0, "odd": 5}])
    out = await W.check_invisible_games(pool, None)
    assert out and out[0][0] == "W-GAME-INVISIBLE"
    assert "0건" in out[0][2]


@pytest.mark.asyncio
async def test_alarm_silent_when_games_are_visible():
    from app import watchdog as W

    pool = _Pool([{"sport": "kbo", "total": 5, "visible": 5, "odd": 0}])
    assert await W.check_invisible_games(pool, None) == []


@pytest.mark.asyncio
async def test_repaired_rows_are_reported():
    from app import watchdog as W

    class P:
        async def fetch(self, sql, *a):
            if "UPDATE games" in sql:
                return [{"id": 1, "sport": "kbo", "away": "LG", "home": "두산",
                         "starts_at": datetime.now(UTC) + timedelta(hours=1)}]
            return []

    out = await W.check_invisible_games(P(), None)
    assert out and out[0][0] == "W-GAME-INVISIBLE"
    assert "복구함" in out[0][2] and "LG@두산" in out[0][2]
