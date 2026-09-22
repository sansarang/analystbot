"""[CODE-V] **LLM 판정이 실패해도 코드 판정까지는 간다.**

사용자 2026-09-22: "코드가 예측값을 내고 LLM 은 서술만 하는 거 아니냐?"

🔴 맞다. CLAUDE.md:
> "승자·확률·확신은 **코드**가 정한다(`matchup.apply_code_verdict` ·
>  `confidence.by_code`). LLM 이 하는 일은 **추출과 서술** 둘뿐이다."

그런데 배선이 그 말을 안 따르고 있었다:
```python
if await judge_matchup(...):        # ← LLM 판정
    await _attach_market_spine(...)  #   시장 뼈대
    apply_code_verdict(jg)           #   코드 승자   ← 둘 다 이 안에 있었다
```
LLM 이 빈손이면 **시장 뼈대도 안 붙고 코드 판정도 안 돌았다.**

🔴 실측 2026-09-22: 무료 사슬 전부 소진(gemini 402 · groq 429 · anthropic
   잔액 0)으로 KBO·NPB **전 경기 판정 0건**. 같은 시각 코드 경로만 따로
   돌리자 **9경기 승자가 전부 나왔다** — `p_code` 는 멀쩡했는데 그 자리에 갈
   기회가 없었다.
```
[matchup_prelim] 🔴 무료 사슬 전부 실패 — 이 건은 재료 없이 간다
[verdict] 승자 없음 Doosan Bears@Kiwoom Heroes · **0자**
[v3] Doosan Bears@Kiwoom Heroes 탈락 — 판정 실패
```
"""
from __future__ import annotations

import ast
import inspect

import app.pipeline as P


#: 🔴 **코드 줄만 본다.** 원문을 `index()` 로 찾으면 "`if _llm_ok:` 안에
#  있어서" 같은 **내 주석**이 먼저 잡힌다 — 이 저장소가 그 거짓 실패를 겪은
#  것이 지금 여섯 번째다(D46). 주석·문자열을 떼고 줄 단위로 찾는다.
def _code_lines() -> list[str]:
    out = []
    for ln in inspect.getsource(P).splitlines():
        body = ln.split("#", 1)[0].rstrip()
        out.append(body)
    return out


def _at(lines, needle: str) -> int:
    """그 문장이 **코드로** 있는 줄 번호. 없으면 -1."""
    for i, ln in enumerate(lines):
        if ln.strip() == needle:
            return i
    return -1


def test_코드_판정이_LLM_성공_게이트_밖에_있다():
    """🔴 이것이 결함의 핵심이었다."""
    L = _code_lines()
    i_llm = next(i for i, ln in enumerate(L)
                 if "_llm_ok = await judge_matchup(" in ln)
    i_spine = next(i for i, ln in enumerate(L)
                   if i > i_llm and "_attach_market_spine(pool, jg)" in ln)
    i_code = next(i for i, ln in enumerate(L)
                  if i > i_llm and "_code_ok = apply_code_verdict(jg)" in ln)
    i_gate = _at(L, "if _llm_ok:")
    assert i_gate > 0, "게이트 줄을 못 찾았다"
    assert i_llm < i_spine < i_code < i_gate, (
        f"시장 뼈대·코드 판정이 아직 게이트 안이다: "
        f"llm={i_llm} spine={i_spine} code={i_code} gate={i_gate}")


def test_LLM_이_실패해도_판정_건수에_센다():
    """⚠️ 코드가 승자를 냈는데 '판정 0건'으로 보고하면 카드가 거짓말을 한다."""
    assert _at(_code_lines(), "if _llm_ok or _code_ok:") > 0


def test_나머지_블록은_여전히_LLM_안에_있다():
    """🔴 **범위를 넓히지 않았다.** 서술·감사·분기점 조사는 LLM 산출물을
    전제로 한다 — 여기서 푼 것은 **승자**뿐이다."""
    L = _code_lines()
    gate = _at(L, "if _llm_ok:")
    tail = "\n".join(L[gate:gate + 90])
    for must in ("branch_resolve", "_spawn_fact_audit"):
        assert must in tail, f"{must} 가 게이트 밖으로 새어 나왔다"


def test_p_code_가_없으면_승자를_지어내지_않는다():
    """🔴 `apply_code_verdict` 의 종전 규약을 안 건드렸다 —
    시장 뼈대가 없으면 승자 None · 확신 하 · 보드."""
    from app.engine.matchup import apply_code_verdict
    from app.engine.verdict import LEVELS

    jg = {"game_id": 1, "sport": "kbo", "home": "H", "away": "A",
          "matchup": {"승자": "H", "확신": "상"}}
    assert apply_code_verdict(jg) is False
    assert jg["winner"] is None
    assert jg["board_only"] is True
    assert (jg["matchup"] or {})["확신"] == LEVELS[-1]
    # LLM 값은 버리지 않고 대피시킨다
    assert (jg.get("llm_verdict") or {}).get("승자") == "H"


def test_p_code_가_있으면_LLM_없이_승자가_나온다():
    """🔴 이것이 오늘 실측으로 확인된 것이다 — LLM 0회로 9경기 승자 산출."""
    from app.engine.matchup import apply_code_verdict

    jg = {"game_id": 2, "sport": "kbo", "home": "Samsung Lions",
          "away": "NC Dinos", "p_code": 0.6522, "matchup": {}}
    assert apply_code_verdict(jg) is True
    assert jg["winner"] == "Samsung Lions", jg.get("winner")

    jg2 = {"game_id": 3, "sport": "kbo", "home": "Kiwoom Heroes",
           "away": "Doosan Bears", "p_code": 0.3294, "matchup": {}}
    assert apply_code_verdict(jg2) is True
    assert jg2["winner"] == "Doosan Bears"


def test_게이트를_푼_코드가_문법적으로_한_덩어리다():
    """⚠️ 들여쓰기 사고 방지 — 블록을 옮기다 다른 문장이 딸려 들어가면
    조용히 동작이 바뀐다."""
    ast.parse(inspect.getsource(P))
