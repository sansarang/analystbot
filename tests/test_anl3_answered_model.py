"""ANL-3 계약 — 원장이 **실제로 답한 모델**을 적는다.

🔴 실측 2026-09-17: 원장에 `analyze_model='claude-opus-5'` 인데 **Opus 는
   불리지도 않았다.** 로그가 말한다 —
     [matchup_prelim] gemini/gemini-3.5-flash-lite 응답이 JSON 이 아니다
     [matchup_prelim] 🔴 무료 사슬 전부 실패 — 유료로 내려가지 않는다
   `to_ledger(model=s.matchup_model)` 가 **설정값**을 적고 있었다.
🔴 오늘 MDL-1 에서 고친 것과 **똑같은 병의 두 번째 자리**다.
   matchup.py:1621 — "폴백이 일어나면 … 모델별 성적을 영영 못 가른다".
"""
import inspect

import pytest

from app.engine import analyze as AN
from app.engine import team_form as TF
from app.llm.judge_route import JUDGE_ROLES, PRELIM_ROLE

REAL = "gemini/gemini-3.5-flash-lite"


@pytest.fixture
def usage():
    keep = dict(TF.LAST_USAGE)
    TF.LAST_USAGE.clear()
    yield TF.LAST_USAGE
    TF.LAST_USAGE.clear()
    TF.LAST_USAGE.update(keep)


def test_실제_응답_모델을_읽는다(usage):
    usage.update({"role": PRELIM_ROLE, "model": REAL})
    assert AN.answered_model("claude-opus-5") == REAL


def test_다른_역할이_끼면_설정값이다(usage):
    """🔴 `LAST_USAGE` 는 직전 호출이다 — 폼 모델을 분석 모델로 적으면 안 된다."""
    usage.update({"role": "form", "model": "폼모델"})
    assert AN.answered_model("claude-opus-5") == "claude-opus-5"


def test_아무것도_없으면_None이다(usage):
    """🔴 `''` 를 쓰면 '모름'과 '빈 이름'이 같아진다."""
    assert AN.answered_model(None) is None
    assert AN.answered_model("") is None


def test_원장_저장이_실제_모델을_쓴다():
    src = inspect.getsource(AN.run)
    for seg in src.split("to_ledger(")[1:]:
        head = seg.split(")", 1)[0]
        assert "answered_model" in head or "model=None" in head, head


def test_호출_실패는_None_그대로다():
    """🔴 반대 위험 — 응답이 없으면 모델도 없다. 설정값으로 채우면
    '안 불렸다'와 '불렸다'가 같아진다."""
    src = inspect.getsource(AN.run)
    fail = src.split("out[\"skipped\"] = f\"호출 실패", 1)[1][:200]
    assert "model=None" in fail


def test_to_ledger는_안_바뀌었다():
    """받은 값을 적을 뿐이다 — 모델을 고르는 일은 호출부가 한다."""
    src = inspect.getsource(AN.to_ledger)
    assert "LAST_USAGE" not in src and "matchup_model" not in src


# ── 🔴 반대 위험 · 사본 금지

def test_matchup의_같은_함수를_안_건드렸다():
    """🔴 `_real_model` 은 v2 판정 경로가 쓴다. 합치는 것은 **다른 일**이다."""
    from app.engine import matchup as M

    assert hasattr(M, "_real_model")
    assert "LAST_USAGE" in inspect.getsource(M._real_model)


def test_같은_원본을_본다():
    """🔴 두 함수가 각자 지어내지 않고 **같은 원본**(LAST_USAGE·JUDGE_ROLES)을 본다."""
    src = inspect.getsource(AN.answered_model)
    assert "LAST_USAGE" in src and "JUDGE_ROLES" in src
    assert PRELIM_ROLE in JUDGE_ROLES
