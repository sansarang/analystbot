"""MDL-1 계약 — v3 판정이 **어느 모델이 냈는지** 원장까지 나른다.

🔴 실측 2026-09-17 운영 원장: 09-17 20건 **전건 `model` NULL** (같은 날
   `model_src` 20/20 · `llm_winner` 20/20 — v3 가 다른 칸은 다 채운다).
🔴 저장소가 이미 경고해 둔 자리다 — matchup.py:1621
   "폴백이 일어나면 어느 모델이 그 판정을 했는지가 사라지고, 그러면
    **모델별 성적을 영영 못 가른다**". 그 보정은 v2 경로에만 있었다.
⚠️ `model_src`(확률 모델)·`analyze_model`(S11 분석 LLM)은 **다른 호출**이라
   판정 LLM 을 대체하지 못한다.
"""
import inspect

import pytest

from app.engine import matchup as M
from app.engine import team_form as TF
from app.llm.judge_route import JUDGE_ROLES, PRELIM_ROLE

REAL = "gemini/gemini-3.5-flash-lite"


@pytest.fixture
def usage():
    """`LAST_USAGE` 를 세우고 되돌린다 — 다른 테스트에 새면 안 된다."""
    keep = dict(TF.LAST_USAGE)
    TF.LAST_USAGE.clear()
    yield TF.LAST_USAGE
    TF.LAST_USAGE.clear()
    TF.LAST_USAGE.update(keep)


# ── v3 가 모델을 싣는다

def test_v3가_apply_winner에_model을_넘긴다():
    call = inspect.getsource(M._judge_v3).split("apply_winner(jg,", 1)[1][:200]
    assert '"model"' in call


def test_실제_응답_모델이다_설정값이_아니다(usage):
    """🔴 무료 사슬은 폴백한다 — 실측 2026-09-05: provider=nvidia 인데 로그는
    claude-sonnet-5 였다. 설정값을 적으면 **모델별 성적이 거짓말이 된다.**"""
    usage.update({"role": PRELIM_ROLE, "model": REAL})
    assert M._real_model("설정값") == REAL


def test_다른_역할이_끼면_설정값으로_떨어진다(usage):
    """🔴 반대 위험 — 폼 모델을 판정 모델로 적으면 안 된다."""
    usage.update({"role": "form", "model": "폼모델"})
    assert M._real_model("설정값") == "설정값"


def test_모르면_빈_문자열이_아니라_None이다():
    """🔴 `''` 를 쓰면 '모름'과 '빈 이름'이 같아진다."""
    src = inspect.getsource(M._judge_v3)
    assert "_real_model(get_settings().matchup_model) or None" in src


# ── 값이 끝까지 간다

def test_model이_matchup에_남는다(usage):
    usage.update({"role": PRELIM_ROLE, "model": REAL})
    jg = {"home": "H", "away": "A", "game_id": 1}
    assert M.apply_winner(jg, {"승자": "H", "확신": "중", "서술": "",
                               "model": M._real_model("x")})
    assert jg["matchup"]["model"] == REAL


def test_코드_덮어쓰기가_model을_나른다():
    """🔴 P0-1 이 승자를 코드값으로 덮는데, 그때 model 을 떨어뜨리면 도로아미다."""
    src = inspect.getsource(M.apply_code_verdict)
    assert 'model=(jg.get("matchup") or {}).get("model")' in src


def test_원장이_그_칸을_읽는다():
    import pathlib

    led = pathlib.Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    assert '"model": jg.get("model") or matchup.get("model")' in led


# ── 🔴 반대 위험

def test_승자와_확신을_안_바꾼다(usage):
    usage.update({"role": PRELIM_ROLE, "model": REAL})
    jg = {"home": "H", "away": "A", "game_id": 1}
    M.apply_winner(jg, {"승자": "A", "확신": "하", "서술": "", "model": REAL})
    assert jg["matchup"]["승자"] == "A" and jg["winner"] == "A"


def test_v2_경로를_안_건드렸다():
    """🔴 거기는 이미 `_real_model` 보정이 있다 — 두 번 고치면 사본이 된다."""
    src = inspect.getsource(M)
    assert src.count('jg["model"] = _actual') == 1
    assert "JUDGE_ROLES" in inspect.getsource(M._real_model)
    assert PRELIM_ROLE in JUDGE_ROLES
