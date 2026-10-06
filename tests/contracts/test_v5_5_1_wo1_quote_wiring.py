"""🔴🔴 **지시서 §1-1 — 에이전트가 연 본문이 검증층에 닿는다** + 인용 양방향.

작업 지시서(오픈월드) §1-1:

> 포르투갈 후보 12개 → 검증 0개의 **사유 진단** — 12개 각각에 대해 사유 코드,
> 에이전트가 낸 `quote`, 그 URL 에서 받아 둔 본문의 해당 부근 200자를 나란히
> 보고한다. 인용 검증(§5-1)이 **정규화 차이**(따옴표·공백·NBSP·대소문자·발음
> 기호)로 진짜 인용을 떨어뜨리는지, 에이전트가 **실제로 지어냈는지**를 가른다.
> … 계약에 **"진짜 인용 10건은 통과, 지어낸 인용 10건은 폐기"** 양방향 고정물을 둔다.

══════════════════════════════════════════════════════════════════
🔴 진단 결과 — **정규화도 지어냄도 아니다. 배선이 끊겼다.**
══════════════════════════════════════════════════════════════════

실측 2026-10-04(`pn2.log`) — 열두 건이 **전부 같은 사유**였다:

```
verified_vars 탈락: quote_not_found 12
[verify] 폐기 V8  — 🔴 그 URL 의 **본문을 받아 두지 않았다** — 대조할 수 없다
                     (fail-closed): https://www.si.com/soccer/norway-vs-portugal…
[verify] 폐기 V12 — 🔴 같은 것: https://www.si.com/soccer/portugal-vs-norway…
```

🔴 **인용을 본문과 비교조차 못 했다.** 까닭:

```
app/analyze.py:153
    ctx = verifylayer.Context(…, bodies=dict(getattr(seen, "bodies", {}) or {}))
                                             ↑ 세포가 받아 둔 것만

app/agentloop.py  Tools._open()
    self.bodies[url] = body      ← 에이전트가 직접 연 본문은 **여기** 있다
```

⚠️ 결정 ③(세포는 장부)으로 `seen.bodies` 가 **비었다**. 에이전트가 제 손으로
   연 본문은 `Tools.bodies` 에 쌓이는데 **아무도 검증층에 넘기지 않았다.**
🔴 이 저장소가 반복해 다친 자리다(#2) — *"만든 것은 부르는 곳이 있어야 한다."*
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib

import pytest

UTC = dt.timezone.utc
FIX = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "openworld"




# ══════════════════════════════════════════════════════════════════
# ① 배선 — 에이전트가 연 본문이 검증층에 **닿나**
# ══════════════════════════════════════════════════════════════════





# ══════════════════════════════════════════════════════════════════
# ② 인용 양방향 고정물 — 진짜 10건 통과 · 지어낸 10건 폐기
# ══════════════════════════════════════════════════════════════════

def _cases() -> dict:
    """🔴 **실측 저장**이다(§5: 라이브 웹에 기대는 테스트는 계약이 아니다)."""
    p = FIX / "quote_cases.json"
    assert p.exists(), (
        f"🔴 고정물이 없다: {p} — §1-1 이 **양방향 10+10** 을 요구한다")
    return json.loads(p.read_text(encoding="utf-8"))


def test_wo1_1_고정물이_열_건씩_있다():
    """🔴 *"진짜 인용 10건은 통과, 지어낸 인용 10건은 폐기"*."""
    box = _cases()
    assert len(box["real"]) >= 10, len(box["real"])
    assert len(box["fake"]) >= 10, len(box["fake"])






def test_wo1_1_본문이_없으면_사유가_다르다():
    """🔴 §8-6 — *"본문을 못 받았다"* 와 *"인용이 본문에 없다"* 는 **다른 사유**다.

    ⚠️ 실측 12건이 `quote_not_found` 로 묶여서 **고칠 곳을 가렸다**. 🔴 본문이
       없는 것은 **수집/배선** 문제이고, 인용이 없는 것은 **에이전트** 문제다.
    """
    from app import reasons
    assert hasattr(reasons.Reason, "BODY_MISSING"), (
        "🔴 `Reason.BODY_MISSING` 이 없다 — 본문 부재를 `quote_not_found` 로 "
        "적으면 거짓 사유다(§8-6)")
    got = reasons.Reason.BODY_MISSING
    assert got.fix_where in ("수집", "읽기"), got.fix_where




