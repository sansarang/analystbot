"""[2026-09-03 사용자 결정] **첫 카드 보장선 = 시작 T-30.**

🔴 그 시점에 카드가 없으면 라인업이 미공시여도 지금 있는 재료로 판정해
   내보낸다. "라인업을 기다리다 카드가 아예 안 나가는" 것이 가장 나쁘다.

⚠️ 이건 **첫 카드 보장선**이지 마감이 아니다. 확정 공시가 오면 종전 재판정
   경로가 수정 카드를 보낸다 — 그 경로는 한 줄도 바뀌지 않았다.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.engine.pregame_push import (
    FIRST_CARD_GUARANTEE_MIN, guarantee_due, in_send_window,
)

NOW = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)


def _at(minutes_left: int):
    return NOW + timedelta(minutes=minutes_left)


def test_guarantee_line_is_thirty_minutes():
    assert FIRST_CARD_GUARANTEE_MIN == 30


def test_due_only_inside_the_line():
    assert guarantee_due(_at(29), NOW) is True
    assert guarantee_due(_at(30), NOW) is True
    assert guarantee_due(_at(31), NOW) is False      # 아직 보장선 전
    assert guarantee_due(_at(-1), NOW) is False      # 이미 시작


def test_send_window_is_already_open_at_the_line():
    """창을 넓힐 필요가 없다 — KBO T-70 · NPB T-40 · MLB T-180 전부 T-30 을 덮는다.

    창까지 건드리면 발송 스케줄 말고 다른 것이 바뀐다. 보장 로직만 더한다.
    """
    for sport in ("kbo", "npb", "mlb"):
        assert in_send_window(sport, _at(FIRST_CARD_GUARANTEE_MIN), NOW), sport


class _Redis:
    def __init__(self, sent=(), analysis=True):
        self._sent = set(sent)
        self._analysis = analysis

    async def get(self, key):
        if key.startswith("analysis:"):
            return '{"games": []}' if self._analysis else None
        for gid in self._sent:
            if str(gid) in key:
                return "x"
        return None

    async def set(self, *a, **kw):
        return None


ROW = {"id": 77, "sport": "kbo", "home": "LG", "away": "KIA",
       "starts_at": _at(25), "lineup_status": "predicted",
       "home_pitcher": "A", "away_pitcher": "B"}


@pytest.mark.asyncio
async def test_unsent_game_at_t30_is_forced(monkeypatch):
    """① T-35 에 미발송이던 경기가 T-30 안에서 강제로 나간다."""
    import app.scheduler as S

    calls = {"send": 0, "rejudge": 0}

    async def fake_send(redis, row, date, *, now=None):
        calls["send"] += 1
        return "skipped" if calls["send"] == 1 else "sent"

    async def fake_rejudge(row, payload):
        calls["rejudge"] += 1
        return True

    monkeypatch.setattr("app.engine.pregame_push.send_game_prediction", fake_send)
    monkeypatch.setattr("app.pipeline.rejudge_after_lineup", fake_rejudge)
    monkeypatch.setattr("app.pipeline.ensure_analysis_cache",
                        lambda *a, **kw: _true())
    monkeypatch.setattr("app.pipeline.analysis_cache_ready",
                        lambda *a, **kw: True)

    n = await S.guarantee_first_cards(object(), _Redis(), "kbo", "2026-09-03",
                                      [ROW], NOW)
    assert n == 1, "보장선에서 카드를 못 냈다"
    assert calls["rejudge"] == 1, "판정을 강제하지 않았다"


async def _true():
    return True


@pytest.mark.asyncio
async def test_already_sent_game_is_untouched(monkeypatch):
    """② 이미 나간 경기는 **건드리지 않는다** — 중복 발송 금지."""
    import app.scheduler as S

    calls = {"send": 0}

    async def fake_send(*a, **kw):
        calls["send"] += 1
        return "sent"

    monkeypatch.setattr("app.engine.pregame_push.send_game_prediction", fake_send)
    n = await S.guarantee_first_cards(object(), _Redis(sent=[77]), "kbo",
                                      "2026-09-03", [ROW], NOW)
    assert n == 0 and calls["send"] == 0


@pytest.mark.asyncio
async def test_game_before_the_line_is_not_touched(monkeypatch):
    """보장선 전(T-45)에는 강제하지 않는다 — 평상시 폴링 몫이다."""
    import app.scheduler as S

    calls = {"send": 0}

    async def fake_send(*a, **kw):
        calls["send"] += 1
        return "sent"

    monkeypatch.setattr("app.engine.pregame_push.send_game_prediction", fake_send)
    row = {**ROW, "starts_at": _at(45)}
    assert await S.guarantee_first_cards(object(), _Redis(), "kbo",
                                         "2026-09-03", [row], NOW) == 0
    assert calls["send"] == 0


def test_rejudge_path_is_unchanged():
    """③ 확정 도착 시 재판정 경로는 **한 줄도 안 바뀌었다.**"""
    from app.engine.pregame_push import (
        NPB_FINISH_MIN, NPB_REJUDGE_FINISH_MIN, SEND_OPEN_MIN, analysis_open,
        rejudge_open,
    )

    assert NPB_FINISH_MIN == 15 and NPB_REJUDGE_FINISH_MIN == 10
    assert SEND_OPEN_MIN == {"kbo": 70, "npb": 40, "mlb": 180}
    assert analysis_open("npb", _at(14), NOW) is False       # NPB T-15 종료
    assert rejudge_open("npb", _at(12), NOW) is True         # NPB 경량은 T-10
    # [2026-09-03] KBO 도 T-15 마감. 보장선(T-30)과는 별개다 —
    #   보장선은 **첫 카드**, 이건 **재판정**이다.
    assert rejudge_open("kbo", _at(21), NOW) is True
    assert rejudge_open("kbo", _at(5), NOW) is False


def test_guarantee_is_symmetric_across_leagues():
    """🔴 감시 3층이 MLB 를 빠뜨렸던 실수를 반복하지 않는다."""
    from pathlib import Path

    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    assert src.count("guarantee_first_cards(") >= 3, \
        "보장 호출부가 부족하다 — 리그 하나가 빠졌을 수 있다"
    assert 'guarantee_first_cards(pool, redis, "mlb"' in src


def test_watchdog_code_is_registered():
    from app.alerts import WATCHDOG_CODES
    from app.watchdog import check_card_late

    assert "W-CARD-LATE" in WATCHDOG_CODES
    assert check_card_late is not None


def test_watchdog_reads_the_line_from_source_not_a_copy():
    """보장선 숫자를 워치독에 손으로 적지 않았다 (사본 금지)."""
    from pathlib import Path

    src = Path("app/watchdog.py").read_text(encoding="utf-8")
    i = src.index("async def check_card_late")
    seg = src[i:src.index("\nasync def ", i + 10)]
    assert "FIRST_CARD_GUARANTEE_MIN" in seg
    # ⚠️ 주석·독스트링의 "T-30" 은 설명이다. **코드 줄**만 본다 —
    #    넓게 잡으면 왜 그런지를 적을 수 없게 된다.
    code = "\n".join(l for l in seg.splitlines()
                     if not l.lstrip().startswith(("#", '"""', "⚠️", "🔴")))
    assert "T-30" not in code and "30" not in code.replace("2026-09-03", ""), \
        "보장선 숫자를 코드에 박았다"


def test_kbo_cutoff_is_derived_from_the_arrival_target():
    """🔴 마감선은 **도착 목표에서 유도**된 값이다 — 마법 숫자가 아니다.

    사용자 결정 2026-09-03(B안): 수정 카드가 **T-15 에 손에 있어야** 한다.
    마감선은 "재판정을 시작할 수 있는 마지막 시점"이라 도착 시각이 아니다 —
    카드 도착 = 폴링 틱 + 재판정 소요. 그래서 예산만큼 앞당긴다.
    """
    from app.engine.pregame_push import (
        CARD_IN_HAND_MIN, KBO_FINISH_MIN, REJUDGE_BUDGET_MIN,
        REJUDGE_FINISH_MIN,
    )

    assert CARD_IN_HAND_MIN == 15
    assert KBO_FINISH_MIN == CARD_IN_HAND_MIN + REJUDGE_BUDGET_MIN == 20
    assert REJUDGE_FINISH_MIN["kbo"] == KBO_FINISH_MIN
    # NPB 는 요청 밖이다 — 종전 이원화를 유지한다
    assert REJUDGE_FINISH_MIN["npb"] == 10


def test_kbo_full_and_light_share_one_line():
    """KBO 는 풀·경량이 **같은 선**이다 — 갈리면 도착 보장이 깨진다."""
    from app.engine.pregame_push import ANALYSIS_FINISH_MIN, REJUDGE_FINISH_MIN

    assert ANALYSIS_FINISH_MIN["kbo"] == REJUDGE_FINISH_MIN["kbo"]
    assert ANALYSIS_FINISH_MIN["npb"] != REJUDGE_FINISH_MIN["npb"]   # NPB 는 갈린다
