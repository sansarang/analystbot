"""[P0 2026-09-04] 폼(보조)의 크레딧 오류가 종목 전체를 죽였다.

🔴 실측 2026-09-04 16:37 (운영 로그):
   `[judge-route] 💸 Anthropic 폴백 2/10 (role=form) — 무료 경로가 실패했다`
   `[form] 크레딧 소진 — 슬레이트 중단 sport=npb done=[…2팀] remaining_at=Hiroshima Toyo Carp`
   `[pipeline] 단계 실패 — 🔴 팀 폼 0/10팀 — 크레딧 부족(credit_400)`
   `[scheduler] prefetch npb halted`
   → **NPB 판정 0건 · 카드 0장.** KBO 는 같은 실행에서 정상 완주했다.

원인: 종목 중단은 Anthropic 이 **유일한** provider 이던 시절의 보호다.
무료 전환 뒤 크레딧 오류는 "비상 꼬리가 없다"는 뜻이지 "무료가 죽었다"가
아니다. 그런데 첫 한 팀이 유료로 떨어지는 순간 슬레이트가 멈췄다.

폼은 보조 신호다 — 판정 게이트는 3경기 박스스코어에 걸리고, 뉴스가 없어도
`[matchup] … 뉴스 없음 — 숫자만으로 판정한다` 가 정상 경로다.
**보조가 필수를 죽이면 안 된다.**
"""
import pytest

from app.engine.team_form import CAUSE_CREDIT


@pytest.mark.asyncio
async def test_credit_error_degrades_one_team_and_keeps_going(monkeypatch):
    import app.engine.team_form as tf
    from app.collectors.base import ApiQuotaError

    monkeypatch.setattr(tf, "_free_primary", lambda role: True)

    seen = []

    async def _analyze(redis, sport, team, date, pkt, news, *, force, mock):
        seen.append(team)
        if team == "B":
            raise ApiQuotaError("anthropic(form)", "credit")
        return {"team": team, "unavailable": False}

    monkeypatch.setattr(tf, "analyze_team", _analyze)
    games = [{"home": "A", "away": "B", "research": {}},
             {"home": "C", "away": "A", "research": {}}]
    out = await tf.analyze_games(_FakeRedis(), "npb", "2026-09-04", games)

    assert seen == ["A", "B", "C"], "B 에서 멈추지 않고 C 까지 갔다"
    assert out["B"]["unavailable"] is True
    assert out["B"]["cause"] == CAUSE_CREDIT
    assert out["A"]["unavailable"] is False and out["C"]["unavailable"] is False


@pytest.mark.asyncio
async def test_halt_is_kept_when_anthropic_is_primary(monkeypatch):
    """무료 경로가 없으면 종전 보호를 그대로 둔다 — 그때는 정말 못 한다."""
    import app.engine.team_form as tf
    from app.collectors.base import ApiQuotaError

    monkeypatch.setattr(tf, "_free_primary", lambda role: False)

    async def _analyze(redis, sport, team, date, pkt, news, *, force, mock):
        raise ApiQuotaError("anthropic(form)", "credit")

    monkeypatch.setattr(tf, "analyze_team", _analyze)
    with pytest.raises(ApiQuotaError):
        await tf.analyze_games(_FakeRedis(), "npb", "2026-09-04",
                               [{"home": "A", "away": "B", "research": {}}])


def test_free_primary_reads_the_chain_not_a_copy():
    """🔴 사본 금지 — '무료가 주전인가'의 원본은 judge_route.chain 이다."""
    import inspect

    import app.engine.team_form as tf

    src = inspect.getsource(tf._free_primary)
    assert "judge_route import chain" in src
    assert "anthropic" in src


class _FakeRedis:
    async def get(self, *a, **k):
        return None

    async def set(self, *a, **k):
        return None
