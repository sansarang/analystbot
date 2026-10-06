"""🔴🔴 **§3 — 리드**(지시서 2026-10-05 딥서치 재구축). **리드는 코드다.**

> `lead.py` 가 하는 일은 **넷뿐**이고, 그 밖의 일을 하면 계약 위반이다.
>  1. **병합** — 하위 8개의 `variables[]` 조각을 합친다. 같은 주장(MinHash 0.8)
>     은 한 묶음으로 세어 **독립 출처 수를 올리고**, 유형·방향은 건드리지
>     않는다(방향은 검증층이 재계산). 하위가 담당 밖 유형을 적어 왔으면
>     **그대로 받는다** — 폐기는 검증층 몫이다.
>  2. **장부 갱신** — 유형군 × 팀 칸마다 `searched`/`found`/`empty`/`not_tried`
>     + 사유. 🔴 **`found` 배선이 이번에 완성돼야 한다** — 지금은 `searched`
>     만 적힌다.
>  3. **2차 보충(최대 1회)** — `not_tried`·`empty` 유형군만, 남은 예산 안에서
>     한 번 다시 돌린다(턴 6). 2차 뒤에도 비면 `gaps` 로 보고 — **3차는 없다**(M64).
>  4. **깔때기 집계** — 하위별 한 줄 + 합계.
>
> **리드가 하지 않는 것**(M60): LLM 호출로 변수·가설·시나리오를 만들지 않는다.
> 변수 내용을 고치지 않는다. 하위 결과를 버리지 않는다.
"""
from __future__ import annotations

import ast
import inspect


def _var(vid: str, kind: str = "absence_def", url: str = "https://a.com/1",
         claim: str = "선수 하나가 결장한다") -> dict:
    return {"id": vid, "type": kind, "team": "team:000081",
            "subject": "team:000081", "claim": claim, "quote": "out injured",
            "source_url": url, "lang": "en", "direction_hint": "away",
            "confidence": "high", "checked": True}


# ══════════════════════════════════════════════════════════════════
# M60 — 리드는 **변수를 만들지 않는다**
# ══════════════════════════════════════════════════════════════════


def test_M60_리드_코드에_LLM_호출이_없다():
    from app.research import lead
    src = inspect.getsource(lead)
    tree = ast.parse(src)
    bad = {n.func.attr for n in ast.walk(tree)
           if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
           and n.func.attr in ("chat", "ask", "complete", "run")}
    assert not bad, (
        f"🔴 리드가 LLM 을 부른다{sorted(bad)} — 가설·시나리오는 DeepSeek "
        f"단계 3 그대로다(M60)")
    # 🔴 `solar` 는 **예산 설정 읽기**로만 쓴다 — 그것만 허용한다.
    #    ⚠️ 이름이 보이는지로 보면 안 된다(`from app import solar` 가 걸린다) —
    #       **무엇을 부르는지**를 본다.
    on_solar = {n.func.attr for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "solar"}
    # 🔴 `solar_concurrency` 도 **예산 설정 읽기**다 — 429 를 받은 뒤의 동시
    #    호출 수를 그 한 곳이 정한다(사용자 지시 2026-10-06 ④ · 사본 금지).
    #    ⚠️ 목록을 늘릴 때는 **그것이 LLM 호출이 아님**을 확인하고 늘린다.
    assert on_solar <= {"budget_cfg", "solar_concurrency"}, (
        f"🔴 리드가 `solar` 로 예산 설정 밖의 일을 한다{sorted(on_solar)}")






# ══════════════════════════════════════════════════════════════════
# 장부 — `found` 배선이 **이번에 완성돼야 한다**
# ══════════════════════════════════════════════════════════════════




# ══════════════════════════════════════════════════════════════════
# M64 — 2차 보충은 **최대 1회** · `not_tried`·`empty` 칸만
# ══════════════════════════════════════════════════════════════════






# ══════════════════════════════════════════════════════════════════
# 깔때기 집계 — 하위별 한 줄 + 합계
# ══════════════════════════════════════════════════════════════════




# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **병합은 실제 꼴을 받는다** — 실사고 2026-10-05 (인도네시아–태국)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 봇이 **죽었다**: `lead.merge → dict(v) → TypeError: 'Classified' object
#     is not iterable`. 🔴 `_run_agent` 는 **판정층 변수**(`classify.Classified`)
#     를 돌려주는데 내 계약은 **dict 로만** 시험했다 — 실제 경로의 꼴을 안 봤다.
#  🔴 ①번(`done.variables` 가 문자열)과 **같은 병**이다. 꼴을 **들어오는
#     자리에서** 맞춘다(§8-3).


