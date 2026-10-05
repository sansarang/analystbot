"""🔴🔴 **robots 규율** — v5 §4-7. [#9]

> robots.txt 거부 경로는 dead. **우회·UA 위장·프록시 금지.** **301 은 끝까지
> 따라가 최종 호스트의 robots 를 읽는다.** robots **404 는 허용**으로 본다
> (npb.jp 와 kleague.com 을 같은 규칙으로).

══════════════════════════════════════════════════════════════════
🔴 왜 — 실측 2026-10-04 에 두 번 틀렸다
══════════════════════════════════════════════════════════════════

```
kleague.com  → **301**. 우리는 *"못 읽었다"* 로 적었다.
             🔴 그것은 *"따라가지 않았다"* 였다 — 사용자가 지적했다.
npb.jp       → robots **404**. 그것을 *"허용"* 으로 봤다 — 맞다.
             ⚠️ 그런데 같은 규칙을 kleague 에 **안 썼다.**
```
🔴 두 호스트에 **같은 규칙**을 쓴다 — 그것이 §4-7 의 요구다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 🔴 §4-7 — *"301 은 **끝까지** 따라간다."* ⚠️ 무한 고리를 막으려 수를 둔다.
FOLLOW_REDIRECTS = 5

#: 🔴 robots 상태 → 판정. ⚠️ 5xx 는 **모르는 것**이다 — 허용으로 보지 않는다.
_BY_STATUS = {
    200: "read",      # 🔴 읽어서 규칙을 적용한다
    404: "allow",     # 🔴 §4-7 — **없으면 허용**이다
    410: "allow",
    403: "deny",      # ⚠️ robots 자체를 막는다면 그 뜻으로 받는다
    401: "deny",
}


def verdict_for_status(status: int) -> str:
    """🔴 그 상태 코드의 뜻. `read` · `allow` · `deny` · `unknown`.

    ⚠️ **`unknown` 은 허용이 아니다**(fail-closed) — 5xx 는 서버가 흔들리는
       것이고, 그때 긁으면 더 흔든다.
    """
    got = _BY_STATUS.get(int(status or 0))
    if got:
        return got
    if 500 <= int(status or 0) < 600:
        return "unknown"
    return "unknown"


def same_rule_note(host: str, status: int) -> str:
    """🔴 §4-7 — **두 호스트에 같은 규칙**을 썼다는 사실을 글로 남긴다.

    ⚠️ 실측 2026-10-04: `npb.jp`(404 → 허용)와 `kleague.com`(301 → 안 따라감)에
       **다른 규칙**을 썼다. 그 차이가 조용했다.
    """
    got = verdict_for_status(status)
    return (f"robots {status} → `{got}` — §4-7 은 모든 호스트에 **같은 규칙**을 "
            f"쓴다(`{host}`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다"
            f"(최대 {FOLLOW_REDIRECTS}번)")
