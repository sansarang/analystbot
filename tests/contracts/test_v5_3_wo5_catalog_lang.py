"""🔴🔴 **⑤ 카탈로그 템플릿** — 사용자 지시 2026-10-06.

> 카탈로그 템플릿: **모든 유형에 영어 템플릿 필수**, 현지어는 **추가분**.
> **경기 언어에 없다고 건너뛰는 경로 제거.**

══════════════════════════════════════════════════════════════════
🔴 왜 (실측 2026-10-06 · 북아일랜드–조지아)
══════════════════════════════════════════════════════════════════

경기 언어가 `['en','ka']` 라 `ko`·`ja`·`zh` 템플릿이 **전부** `건너뜀` 으로
찍혔다. 카드 블록 1 이 그 줄로 덮여 *"카탈로그가 통째로 안 돌았다"* 로 읽혔다:

```
세포 카탈로그:Georgia:def_absence: 건너뜀 — 템플릿 언어 `ko` 가
      이 경기 언어 ['en', 'ka'] 에 없다
```
"""
from __future__ import annotations

import ast
import inspect

from app import queries, rules


def _typed() -> dict[str, list[tuple[str, str]]]:
    return {t: rules.type_templates_tagged(t)
            for t in sorted(rules.variable_types())}


def test_wo5_템플릿이_있는_유형은_영어를_가진다():
    """🔴 영어가 있으면 유형이 **언어 때문에** 0 이 될 수 없다.

    ⚠️ 템플릿이 **하나도 없는** 유형은 여기 대상이 아니다 — 그것은
       `variable_types.yaml` 이 *"구조 자료에서만 온다"* 고 선언한 것이고
       (실측 13종), 거기에 질의를 **지어 넣지 않는다**(#4 추측 금지).
    """
    bad = []
    for t, tp in _typed().items():
        if not tp:
            continue
        if not any((lang or "") in ("", "en") for _q, lang in tp):
            bad.append((t, sorted({lang for _q, lang in tp})))
    assert not bad, (
        f"🔴 영어 템플릿이 없는 유형: {bad} — 경기 언어가 그 언어를 안 쓰면 "
        f"그 유형이 **구조적으로 0건**이 된다(사용자 지시 2026-10-06 ⑤)")
    # 🔴 **전제가 비어 있지 않다** — 템플릿을 다 지워도 초록이 되면 안 된다
    assert sum(1 for tp in _typed().values() if tp) >= 5, _typed()


