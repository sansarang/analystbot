"""[XI-1] 축구 확정 XI 를 `predicted` 로 잘못 적고, ⑤가 읽지도 않았다.

사용자 2026-09-23: (축구 `xi_confirmed` 배선) "진행해"

🔴 실측 — flashscore 라인업 **122행 전수**:
```
수집시각 − 킥오프   최소 -48분 · 중앙 -15분 · 최대 -3분
킥오프 60분+ 전     0행        60~0분 전  122행        킥오프 후  0행
명단 인원          11명 → 122행 (다른 값 없음)
```
축구 공식 선발 XI 는 킥오프 약 1시간 전에 발표된다. 우리 자료는 **전건이 그
창 안**이고 인원도 정확히 11명이다 — **예상이 아니라 공식 발표분**이다.

🔴 그런데 적재기가 문자열을 **손으로 박고 있었다**:
```python
VALUES ($1, $2, $3, $4, …)   #  ← $3 자리에 언제나 "predicted"
        jg.get("game_id"), side, "predicted", "flashscore", …
```
그래서 `xi_confirmed` 는 최근 3일 **305건 전건 미상**이었다. ⑦은 `confirmed`
에만 조정을 거는데, 확정 XI 를 손에 쥐고도 한 번도 confirmed 가 못 됐다.

⚠️ 판정 규율 "**예상을 확정으로 취급 금지**"(CLAUDE.md 발송 규율)는 그대로다 —
   창 **밖**에서 온 명단은 `predicted` 로 남는다. 바꾸는 것은 "창 안에서 온
   11명을 예상이라고 부르던 것"뿐이다.
"""
from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.collectors import lineups as L

KICK = datetime(2026, 9, 20, 18, 0, tzinfo=timezone.utc)


# ── 규칙이 한 곳이다 ────────────────────────────────────────────────

def test_공식_판정_함수가_있다():
    """🔴 적재기와 ⑤가 **같은 함수**를 본다 — 두 벌이면 어긋난다."""
    assert hasattr(L, "xi_status_of")


def test_창_안_11명은_공식이다():
    """🔴 실측 그대로 — 122행이 -48 ~ -3분, 전부 11명."""
    for mins in (-48, -15, -3):
        got = L.xi_status_of(source="flashscore", n_players=11,
                             captured_at=KICK + timedelta(minutes=mins),
                             kickoff=KICK)
        assert got == L.STATUS_CONFIRMED, f"{mins}분: {got}"


def test_창_밖은_예상이다():
    """🔴 "예상을 확정으로 취급 금지" — 창 밖 명단은 그대로 predicted."""
    got = L.xi_status_of(source="flashscore", n_players=11,
                         captured_at=KICK - timedelta(hours=5), kickoff=KICK)
    assert got == L.STATUS_PREDICTED


def test_인원이_안_맞으면_예상이다():
    """⚠️ 11명이 아니면 확정 XI 가 아니다 — 부분 수신일 수 있다."""
    for n in (0, 7, 10, 12):
        got = L.xi_status_of(source="flashscore", n_players=n,
                             captured_at=KICK - timedelta(minutes=10),
                             kickoff=KICK)
        assert got == L.STATUS_PREDICTED, n


def test_킥오프를_모르면_예상이다():
    """🔴 **모르면 낮은 쪽이다.** 확정이라고 올려 부르면 확신이 부풀고,
    그것이 이 저장소가 가장 경계하는 방향이다."""
    assert L.xi_status_of(source="flashscore", n_players=11,
                          captured_at=KICK, kickoff=None) == L.STATUS_PREDICTED
    assert L.xi_status_of(source="flashscore", n_players=11,
                          captured_at=None, kickoff=KICK) == L.STATUS_PREDICTED


def test_창의_원본이_설정이다():
    """🔴 숫자를 코드에 박지 않는다(사본 금지)."""
    from app.engine import rules as R

    assert R.get("lineups.official_window_min") is not None
    src = inspect.getsource(L.xi_status_of)
    assert "official_window_min" in src


# ── 적재기가 그 함수를 쓴다 ─────────────────────────────────────────

def test_적재기가_상태를_손으로_박지_않는다():
    """🔴 이것이 결함의 자리다 — `"predicted"` 리터럴이 INSERT 인자였다.

    ⚠️ 주석·독스트링을 뗀 **코드 본문**만 본다(D46, 이 저장소 10회).
    """
    from app.collectors import satellite_soccer as SS

    tree = ast.parse(inspect.getsource(SS))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if body and isinstance(body, list):
            first = body[0]
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                body.pop(0)
    code = ast.unparse(tree)
    assert "xi_status_of" in code, "적재기가 공식 판정 함수를 안 쓴다"
    assert "'predicted', 'flashscore'" not in code, "상태를 손으로 박았다"


# ── ⑤가 표를 읽는다 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_n05_가_lineups_에서_확정XI를_읽는다():
    """🔴 배선의 끝. 종전에는 위성 추출 상자(`out`)만 봤고, LLM 을 0 으로
    만든 뒤로는 그 상자가 비어 있어 **영원히 미상**이었다."""
    from app.flow.ctx import Ctx
    from app.flow.nodes import n05_evidence as N5
    from app.flow.state import State

    xi = [f"P{i}" for i in range(11)]

    class _P:
        async def fetch(self, sql, *a):
            if "lineups" not in sql:
                return []
            return [{"side": "home", "status": L.STATUS_CONFIRMED,
                     "source": "flashscore", "starter": "4-3-3",
                     "batting_order": xi, "scratches": [],
                     "captured_at": KICK - timedelta(minutes=15)}]

    st = State.new({"id": "1", "sport": "soccer", "league": "EPL",
                    "home": "A", "away": "B",
                    "starts_at": KICK.isoformat()})
    st.sport = "soccer"
    st.pick_side = "home"
    st.n04_hyp = [{"id": "H", "vars": [{"var": "xi_confirmed", "is_core": True}]}]
    out = await N5.run(st, Ctx(pool=_P()))
    rows = [e for e in (out.n05_evidence or []) if e["var"] == "xi_confirmed"]
    assert rows, "확정 XI 가 있는데 증거가 비었다"
    assert rows[0]["value"], rows[0]
    assert "lineups" in rows[0]["source"], rows[0]["source"]


@pytest.mark.asyncio
async def test_예상만_있으면_확정으로_치지_않는다():
    """🔴 "예상을 확정으로 취급 금지". ⑥의 `_judge` 는 None → `unknown` 이다 —
    **`refuted`(봤는데 없다)가 아니다.** 공식 XI 는 아직 나오지 않았을 뿐이고,
    없다고 단정하면 핵심 변수가 반증으로 잡혀 픽이 철회된다."""
    from app.flow.ctx import Ctx
    from app.flow.nodes import n05_evidence as N5
    from app.flow.state import State

    class _P:
        async def fetch(self, sql, *a):
            if "lineups" not in sql:
                return []
            return [{"side": "home", "status": L.STATUS_PREDICTED,
                     "source": "flashscore", "starter": "4-3-3",
                     "batting_order": [f"P{i}" for i in range(11)],
                     "scratches": [],
                     "captured_at": KICK - timedelta(hours=6)}]

    st = State.new({"id": "1", "sport": "soccer", "league": "EPL",
                    "home": "A", "away": "B", "starts_at": KICK.isoformat()})
    st.sport = "soccer"
    st.pick_side = "home"
    st.n04_hyp = [{"id": "H", "vars": [{"var": "xi_confirmed", "is_core": True}]}]
    out = await N5.run(st, Ctx(pool=_P()))
    rows = [e for e in (out.n05_evidence or []) if e["var"] == "xi_confirmed"]
    assert not rows, f"예상 XI 를 증거로 실었다: {rows}"


def test_야구는_건드리지_않았다():
    """⚠️ 반대 위험 — MLB 는 statsapi 가 `confirmed` 를 직접 준다."""
    assert L.STATUS_CONFIRMED == "confirmed"
    assert L.STATUS_PREDICTED == "predicted"
    src = inspect.getsource(L.refresh_mlb_lineup)
    assert "xi_status_of" not in src, "야구 경로에 축구 규칙이 새어 들어갔다"
