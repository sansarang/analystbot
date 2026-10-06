"""🔴🔴 **v5 게이트 2 — §3-2 도구를 실제 통로에 꽂는다.**

카드가 스스로 적고 있던 줄:

```
⚠️ §3 에이전트 **도구 미배선** — 스키마·프롬프트·예산은 섰고
   `Tools.search`/`fetch` 가 실제 통로에 아직 안 꽂혔다(§3-2).
```

══════════════════════════════════════════════════════════════════
🔴 **무엇을 꽂나** — 새로 긁지 않는다
══════════════════════════════════════════════════════════════════

⚠️ 세포들이 이미 검색하고 본문을 받는다(깔때기 `queries` 23 · `fetched` 107 ·
   실측 2026-10-04). 🔴 에이전트가 **또 긁으면** 같은 페이지를 두 배로 두드리고
   예산이 두 배가 된다.

🔴 그래서 꽂는 것은 **세포가 이미 받아 둔 것**이다:

    search  →  그 경기에서 **본 검색 결과**(URL·제목·스니펫)
    fetch   →  그 URL 의 **이미 받아 둔 본문**

⚠️ 그래야 §4-4(*"검색 결과에 있던 URL 만"*)가 **자연히** 지켜진다 — 캐시에
   없는 URL 은 애초에 줄 것이 없다.
🔴 그리고 §5-1(인용 대조)이 **그 본문으로** 돈다 — 받아 두지 않은 본문에 대고
   인용을 검증할 수는 없다(그것이 `verifylayer` 의 fail-closed 다).
"""
from __future__ import annotations

import pytest


def test_v5_3_2_세포가_받은_것을_모은다():
    """🔴 깔때기처럼 **한 곳에 모은다** — 세포마다 흩어지면 줄 수가 없다."""
    from app.cells import Seen
    seen = Seen()
    assert seen.urls == [] and seen.bodies == {}
    seen.add_hit("https://a/1", title="제목", snippet="조각", query="q1")
    seen.add_body("https://a/1", "본문이다")
    assert seen.urls == ["https://a/1"]
    assert seen.bodies["https://a/1"] == "본문이다"
    # 🔴 같은 URL 을 두 번 넣어도 **한 건**이다
    seen.add_hit("https://a/1", title="다시", snippet="", query="q2")
    assert seen.urls == ["https://a/1"]
    # ⚠️ 빈 URL·빈 본문은 **안 넣는다**(없는 것을 있는 척하지 않는다)
    seen.add_hit("", title="x", snippet="")
    seen.add_body("https://b/2", "")
    assert seen.urls == ["https://a/1"] and "https://b/2" not in seen.bodies
















