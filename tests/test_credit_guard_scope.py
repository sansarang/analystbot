"""[P0 2026-09-06] Anthropic 차단기는 Anthropic 경로에만 걸린다.

🔴 실사고: 축구 실험(`soccer_trial`)이 Anthropic 400 을 맞고 공용 차단기를
   내렸다. 야구 판정은 무료 사슬(Gemini)로 도는데도 **호출을 시도조차 못 하고**
   전부 죽었다 — MLB 발송 0/85 (0%), 밤새 W-RESCUE-DEAD·W-CARD-LATE.

   오류 문자열이 구조를 그대로 보여줬다:
     "잔액 소진으로 중단 (matchup:SF@NYM): soccer-trial/claude-sonnet-5"
      └ 야구 호출부가 만든 위치          └ 축구가 남긴 사유

   차단기 자체는 옳다(잔액 0인 키로 계속 때리지 않는다). 틀린 것은
   **적용 범위**였다.
"""
from __future__ import annotations

import pytest

from app.engine import credit_guard


@pytest.fixture(autouse=True)
def _clean():
    credit_guard.reset()
    yield
    credit_guard.reset()


def _trip():
    credit_guard.trip_credit("soccer-trial/claude-sonnet-5",
                             RuntimeError("credit balance is too low"))


def test_free_chain_is_not_blocked_by_anthropic_exhaustion(monkeypatch):
    """무료가 주전이면 Anthropic 잔액과 무관하다."""
    import app.engine.team_form as tf

    monkeypatch.setattr(tf, "_free_primary", lambda role: True)
    _trip()
    # 무료 주전이면 호출부가 abort 를 부르지 않는다 — 부르면 여기서 터진다.
    if not tf._free_primary("matchup"):
        credit_guard.abort_if_credit_gone("matchup:A@B")


def test_paid_chain_is_still_blocked(monkeypatch):
    """반대 위험 — Anthropic 이 주전이면 차단기는 그대로 살아 있어야 한다.

    잔액 0인 키로 계속 때리면 요금만 태우고 종목이 통째로 멈춘다.
    """
    from app.collectors.base import ApiQuotaError

    _trip()
    with pytest.raises(ApiQuotaError):
        credit_guard.abort_if_credit_gone("matchup:A@B")


@pytest.mark.parametrize("path,func", [
    ("app/engine/matchup.py", "judge_matchup"),
    ("app/engine/team_form.py", "analyze_team"),
])
def test_call_sites_check_the_route_first(path, func):
    """호출부가 `_free_primary` 로 경로를 확인한 뒤에만 abort 를 부른다."""
    from pathlib import Path

    src = Path(path).read_text(encoding="utf-8")
    i = src.index("abort_if_credit_gone(f")
    window = src[max(0, i - 700):i]
    assert "_free_primary" in window, (
        f"{path} 의 abort_if_credit_gone 앞에 경로 확인이 없다 — "
        "무료 사슬이 Anthropic 잔액에 인질로 잡힌다")


def test_soccer_trial_still_trips_for_itself():
    """축구는 실제로 Anthropic 을 쓴다 — 거기서는 차단기가 필요하다."""
    from pathlib import Path

    src = Path("app/engine/soccer_trial.py").read_text(encoding="utf-8")
    assert "trip_credit(" in src
    assert "abort_if_credit_gone(" in src


# ─────────────────────────────────────────────────────────────────────
# [CG-1 2026-09-08] 같은 결함이 **`provider.py` 에도** 있었다.
#
# 2026-09-06 에는 `matchup.py` 호출부만 좁혔다. 그런데 무료 사슬 역할 넷
# (interpreter·narrator·intent·judge_a)이 지나는 `provider.complete()` 는
# 사슬을 보기도 전에 `abort_if_credit_gone(role)` 을 무조건 불렀다.
# 운영 실효 사슬은 셋 다 `groq → gemini` 다 — Anthropic 과 무관한데
# Anthropic 이 소진되면 통째로 죽었다. 실제 피해는 2026-09-07 자료6
# (라인업 의도) 해석 20여 건이다(감사 CG-1·CG-3).
#
# ⚠️ 위의 기존 계약은 그대로 둔다 — 삭제·약화 금지. 아래는 **추가**다.
# ─────────────────────────────────────────────────────────────────────
from types import SimpleNamespace

from app.collectors.base import ApiQuotaError
from app.llm import provider as P

class _FakeProvider:
    def __init__(self, name: str, fail: bool = False):
        self.name, self.model, self.fail = name, f"{name}-m", fail

    async def complete(self, messages, **kw):
        if self.fail:
            raise RuntimeError(f"{self.name} 일시 장애")
        return SimpleNamespace(text="ok", data={"ok": True}, provider=self.name,
                               model=self.model, attempts=1)


_SETTINGS = SimpleNamespace(is_disabled=lambda name: False)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    credit_guard.reset()

    async def _no_redis():
        return None

    monkeypatch.setattr(P, "_ledger_redis", _no_redis)
    yield
    credit_guard.reset()


def _chain(monkeypatch, *providers):
    monkeypatch.setattr(P, "provider_chain",
                        lambda role, settings=None: list(providers))


async def _call(role="interpreter"):
    return await P.complete(role, [{"role": "user", "content": "x"}],
                            thinking=0, settings=_SETTINGS)


@pytest.mark.asyncio
async def test_무료_사슬은_anthropic_소진과_무관하다(monkeypatch):
    """🔴 이것이 CG-1 의 본체 — 운영 사슬 그대로(groq → gemini)."""
    _chain(monkeypatch, _FakeProvider("groq"), _FakeProvider("gemini"))
    P._mark_exhausted("anthropic", "축구 실험이 남긴 400")
    res = await _call()
    assert res.text == "ok" and res.provider == "groq"


@pytest.mark.asyncio
async def test_사슬에_anthropic_이_있고_1순위가_살아_있으면_돈다(monkeypatch):
    _chain(monkeypatch, _FakeProvider("groq"), _FakeProvider("anthropic"))
    P._mark_exhausted("anthropic", "잔액 0")
    res = await _call()
    assert res.provider == "groq"


@pytest.mark.asyncio
async def test_anthropic_단독_사슬은_소진이면_충전_안내로_간다(monkeypatch):
    """반대 위험 — 잔액 없는 키로 계속 호출하지 않는다."""
    _chain(monkeypatch, _FakeProvider("anthropic"))
    P._mark_exhausted("anthropic", "잔액 0")
    with pytest.raises(ApiQuotaError):
        await _call()


@pytest.mark.asyncio
async def test_앞이_죽고_뒤가_anthropic_이면_크레딧_오류로_끝난다(monkeypatch):
    """분류가 `LLMError` 로 뭉개지면 충전 안내가 안 나간다 — 그건 다른 결함이다."""
    _chain(monkeypatch, _FakeProvider("groq", fail=True), _FakeProvider("anthropic"))
    P._mark_exhausted("anthropic", "잔액 0")
    with pytest.raises(ApiQuotaError):
        await _call()


@pytest.mark.asyncio
async def test_소진이_아니면_anthropic_도_그대로_호출된다(monkeypatch):
    _chain(monkeypatch, _FakeProvider("anthropic"))
    res = await _call()
    assert res.provider == "anthropic"
