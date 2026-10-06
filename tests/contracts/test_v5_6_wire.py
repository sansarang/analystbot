"""🔴🔴 **§6 — 날짜 3층 마감 + 골격 배선**(지시서 2026-10-05 딥서치 재구축).

> 이미 실측·일부 구현된 것을 이 재구축 안에서 **끝까지 배선한다.**
>  1. ①층 — `time_range=week` 기본. **결과가 2건 이하면** 그 질의 한정으로
>     `time_range` 없이 **1회 재시도**(fetch 전 ②③층이 거르니 안전).
>  2. ②층 — `app/datehint.py` 를 **하위 에이전트의 검색 결과 경로에 배선** —
>     `self.snippets` 가 실제로 채워지는지 **배선 계약으로** 확인한다.
>  3. ③층 — `htmldate` 가 `published_at` 의 **원본**.
>  4. GDELT `seendate` · Bing RSS `pubDate` 유지. Google News 는 **dead**.

🔴 그리고 §1~§5 의 골격을 **실제 경로**(`analyze._run_agent`)에 잇는다 —
   안 이은 코드는 없는 코드보다 나쁘다(규율 #2).
"""
from __future__ import annotations

import ast
import inspect


# ══════════════════════════════════════════════════════════════════
# ①층 — **2건 이하면** 창 없이 1회 재시도
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 종전엔 **0건**일 때만 벗겼다. 🔴 지시서가 수를 바꿨다: *"결과가 2건
#     이하면 그 질의 한정으로 `time_range` 없이 1회 재시도."*
def test_r6_두건_이하면_창을_벗기고_다시():
    import asyncio

    from app import search
    assert hasattr(search, "SEARX_THIN_AT"), (
        "🔴 `search.SEARX_THIN_AT` 가 없다 — 몇 건을 '얄팍하다'로 보나")
    assert search.SEARX_THIN_AT == 2, search.SEARX_THIN_AT
    seen: list = []

    class Fake(search.SearxSearch):
        async def _one(self, text, *, lang="ko", engines=None, time_range=""):
            seen.append(time_range)
            # 🔴 창을 걸면 **2건**(얄팍하다) · 벗기면 다섯
            return ([search.Hit(title="t", url=f"https://a{i}.com/x")
                     for i in range(2 if time_range else 5)])

    got = asyncio.run(Fake().query("아무 질의"))
    assert seen == ["week", ""], (
        f"🔴 2건인데 다시 안 던졌다(던진 창: {seen})")
    assert len(got) == 5, f"🔴 벗긴 결과를 안 썼다: {len(got)}"


def test_r6_세건이면_다시_안_던진다():
    """🔴 상한을 넘으면 **그대로 쓴다** — 쓸데없는 호출을 늘리지 않는다."""
    import asyncio

    from app import search
    seen: list = []

    class Fake(search.SearxSearch):
        async def _one(self, text, *, lang="ko", engines=None, time_range=""):
            seen.append(time_range)
            return [search.Hit(title="t", url=f"https://a{i}.com/x")
                    for i in range(3)]

    asyncio.run(Fake().query("아무 질의"))
    assert seen == ["week"], f"🔴 3건인데 또 던졌다: {seen}"


# ══════════════════════════════════════════════════════════════════
# ②층 — 하위 에이전트의 **검색 결과 경로**에 배선
# ══════════════════════════════════════════════════════════════════






# ══════════════════════════════════════════════════════════════════
# 골격 배선 — 실제 경로가 §2~§5 를 **쓴다**
# ══════════════════════════════════════════════════════════════════








# ══════════════════════════════════════════════════════════════════
# 남은 배선 셋 — **2차 보충 · 1단 재정렬 · 좁히기**
# ══════════════════════════════════════════════════════════════════




