"""LLMS-1 — LLM 판정 출력을 버리지 않고 무료 섀도로 기록한다 (2차 결정 D).

(a) 구조에서 승자는 `p_code` 가 정한다. 그래도 LLM 의 `승자`·`확신` 은 계속
받아 `pick_ledger.llm_winner`·`llm_level` 에 남긴다 — **카드·발송에는 쓰지 않는다.**

🔴 300건 시점에 `llm_winner` 의 AUC 를 `p_code` 와 나란히 본다. LLM 이 나은
   변수 조합이 있다면 그것이 조정 변수 후보다.
⚠️ `dbref.recheck` 의 "승자 변경"은 **승자를 바꾸지 않는다.** 코드 승자와
   다르면 서술에 반대 근거를 쓰게 요구할 뿐이다.
⚠️ `market_agree_required` 의 정의를 `|Σadj| ≤ 4%p` 로 바꾼다 — 뼈대가
   시장이므로 "우리 확률 vs 시장"은 항상 0 이다.
"""
import inspect

import pytest


def test_원장에_두_칸이_있다():
    src = open("db/schema.sql", encoding="utf-8").read()
    for col in ("llm_winner", "llm_level"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in src, col


def test_원장_행이_LLM_출력을_싣는다():
    from app.engine import pick_ledger as L

    src = inspect.getsource(L._row_from_game)
    assert "llm_winner" in src and "llm_level" in src, src[-600:]


def test_카드가_LLM_등급을_쓰지_않는다():
    """🔴 발송에는 코드 등급만 쓴다."""
    from app.engine import pick_ledger as L

    src = inspect.getsource(L._row_from_game)
    i = src.index('"confidence"')
    assert "code_confidence" in src[i:i + 200]
    assert "llm_level" not in src[i:i + 200]


# ── recheck: 승자를 바꾸지 않는다

def test_recheck가_승자를_바꾸지_않는다():
    """🔴 [결정 D] 코드 승자가 최종이다. LLM 이 달라도 서술로만 남긴다."""
    from app.engine import dbref

    src = inspect.getsource(dbref.recheck)
    assert '"승자변경"' in src
    assert "반대" in src or "서술" in src, "반대 근거 요구가 없다"


@pytest.mark.asyncio
async def test_다른_승자는_반대근거로_남는다(monkeypatch):
    from app.engine import dbref

    async def _fake(prompt, **kw):
        return '{"본것": [], "확신": "중", "승자": "B팀", "사유": "불펜 소모"}'

    monkeypatch.setattr("app.engine.team_form.complete_json", _fake)
    monkeypatch.setattr(dbref, "bundle",
                        lambda jg: {"줄": [("오늘 타순", "x")], "있음": ["오늘 타순"],
                                    "없음": []})
    jg = {"away": "A팀", "home": "B팀", "sport": "mlb"}
    out = await dbref.recheck(jg, {}, {"승자": "A팀", "확신": "중"})
    # 승자는 그대로다
    assert out["승자"] == "A팀", out
    assert out["승자변경"] is False, out
    # 다른 의견은 사유로 남는다
    assert out.get("반대근거"), out


# ── market_agree_required 재정의

def test_시장동의는_조정의_크기로_본다():
    """⚠️ 뼈대가 시장이라 '우리 vs 시장'은 항상 0 이다 — 정의를 바꾼다."""
    from app.engine import scoring as S

    assert hasattr(S, "ADJ_AGREE_MAX_PP")
    assert S.ADJ_AGREE_MAX_PP == 4.0


@pytest.mark.parametrize("div,expect", [(0.0, None), (3.9, None), (4.0, None),
                                        (4.1, "market_disagree"), (-6.0, "market_disagree")])
def test_조정이_4퍼센트포인트를_넘으면_이견(div, expect):
    from app.engine import scoring as S

    got = S.market_disagree_by_adj(div)
    assert (got or None) == (expect or None)
