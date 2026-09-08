"""PGP-2 — 판정 불가 카드가 **살아 있는 발송 경로**에 배선돼 있는가.

🔴 실측 2026-09-08: `compose_unavailable_card` 는 2026-09-02 에 만들어졌지만
   6일간 **발송 0건**이었다. 호출부가 `run_pregame_push` 안에만 있는데, 그
   함수를 부르는 곳이 없다 — 스케줄러가 같은 일을 따로 구현했고(`send_game_
   prediction` 직접 호출 6곳), 살아 있는 쪽에 "판정 불가" 분기가 없었다.
   운영 확인: `pregame:unavailable:*` 키 **0개**, `pregame_card_sig:*` 11개.
   (감사 PGP-2 · SCH-1 — "5일 전에 죽은 함수에 수정을 넣었다")

배선 지점은 **T-30 보장선 실패**다. 거기가 정확히 "보내야 하는데 못 보냈다"가
확정되는 자리다. 그 앞은 아직 기다릴 수 있는 시간이다.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.engine import pregame_push as pp


class _Redis:
    def __init__(self, analysis=None):
        self.store, self.analysis, self.sent = {}, analysis, []

    async def get(self, k):
        if k.startswith("analysis:"):
            return self.analysis
        return self.store.get(k)

    async def set(self, k, v, ex=None, nx=False):
        if nx and k in self.store:
            return False
        self.store[k] = v
        return True


def _row(minutes_ahead: int = 20):
    return {"id": 4242, "sport": "kbo", "home": "LG 트윈스", "away": "두산 베어스",
            "starts_at": datetime.now(UTC) + timedelta(minutes=minutes_ahead),
            "league": "KBO"}


@pytest.mark.asyncio
async def test_판정이_없으면_사실을_보낸다(monkeypatch):
    """침묵이 가장 나쁜 출력이다 — 재료가 없으면 없다고 보낸다."""
    seen = {}

    async def _fake_send(text, **kw):
        seen["text"] = text
        return True

    monkeypatch.setattr(pp, "_send_card", _fake_send)
    r = _Redis(analysis=None)          # 판정 캐시 자체가 없다
    ok = await pp.explain_missing(r, _row(), "kbo", datetime.now(UTC))
    assert ok is True
    assert "pregame:unavailable:4242" in r.store or any(
        "unavailable" in k for k in r.store), r.store


@pytest.mark.asyncio
async def test_같은_경기에_두_번_보내지_않는다(monkeypatch):
    monkeypatch.setattr(pp, "_send_card", _ok_send)
    r = _Redis(analysis=None)
    now = datetime.now(UTC)
    first = await pp.explain_missing(r, _row(), "kbo", now)
    second = await pp.explain_missing(r, _row(), "kbo", now)
    assert first is True and second is False


@pytest.mark.asyncio
async def test_판정이_있으면_보내지_않는다(monkeypatch):
    """정상 동작을 고장으로 신고하지 않는다 — 오탐이 쌓이면 카드가 소음이 된다."""
    import json

    monkeypatch.setattr(pp, "_send_card", _ok_send)
    # ⚠️ 판정 유무의 기준은 `_judged` 원본 그대로 — `p_claude` 가 숫자인가다.
    #    여기 다른 필드를 지어내면 테스트가 실물과 다른 계약을 잠근다.
    judged = json.dumps({"games": [{"game_id": 4242, "p_claude": 0.55,
                                    "p_home": 0.55}]})
    r = _Redis(analysis=judged)
    assert await pp.explain_missing(r, _row(), "kbo", datetime.now(UTC)) is False


async def _ok_send(text, **kw):
    return True


def test_보장선_실패_경로가_이_함수를_부른다():
    """등록은 배선이 아니다 — 살아 있는 경로가 실제로 부르는지 본문에서 본다."""
    from pathlib import Path

    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    i = src.index("T-30 보장 실패")
    window = src[i:i + 900]
    assert "explain_missing" in window, (
        "T-30 보장 실패 자리에서 판정 불가 카드를 보내지 않는다 — "
        "PGP-2 가 그대로다(6일간 0건)")
