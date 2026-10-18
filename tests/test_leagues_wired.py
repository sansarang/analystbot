"""🔴🔴 **설정이 말한 리그는 코드가 실제로 할 수 있어야 한다** (CLAUDE.md #2 배선).

══════════════════════════════════════════════════════════════════
🔴 왜 이 계약이 생겼나 — 설정이 **거짓말을 하고 있었다**
══════════════════════════════════════════════════════════════════

실측 2026-10-03(사용자가 *"오늘 기아와 LG 야구 경기"* 를 물었을 때):

```
config.LEAGUES_AUTO      ('KBO', 'NPB', 'MLB', '해외축구', 'NHL')
ingest.ADAPTERS          ['K리그1', 'MLB', 'NHL', 'NPB', '해외축구']
→ 설정에 있는데 어댑터가 없는 리그: ['KBO']
```

⚠️ 즉 설정은 *"KBO 를 매일 모은다"* 고 적어 두고 코드는 **아무것도 안 했다.**
   조용히 아무 일도 일어나지 않는 것이 이 저장소가 반복해 다친 자리다.
🔴 **손 목록을 두지 않는다** — 계약이 두 원본(`config`·`ingest`)을 **대조**한다.
   리그를 하나 더 적으면 어댑터 없이는 빨개진다.
"""
from __future__ import annotations

from app import queries
from app.bot import aliases
from app.collect.ingest import ADAPTERS
from app.config import LEAGUES_AUTO


def test_자동_수집_리그는_전부_어댑터가_있다():
    missing = [lg for lg in LEAGUES_AUTO if lg not in ADAPTERS]
    assert not missing, (
        f"🔴 `LEAGUES_AUTO` 가 모은다고 적었는데 `ADAPTERS` 에 없다: {missing} — "
        f"설정이 거짓말을 한다(CLAUDE.md #2)")


def test_어댑터는_규약을_지킨다():
    """🔴 이름만 등록하고 함수가 없으면 **부르는 순간** 터진다 — 미리 본다."""
    for lg, mod in ADAPTERS.items():
        for fn in ("sources_slate",):
            assert callable(getattr(mod, fn, None)), (lg, fn)
        # 🔴 종목을 **밖에서 읽을 수 있어야** 한다(사용자 지시 2026-10-01 다섯 종목)
        assert str(getattr(mod, "SPORT", "")), lg


def test_자동_수집_리그는_검색_언어가_선언돼_있다():
    """🔴 언어가 없으면 그 리그 검색이 **영어로만** 돈다 — 현지 기사를 못 집는다."""
    for lg in LEAGUES_AUTO:
        got = queries.langs_for(lg) if hasattr(queries, "langs_for") else None
        if got is None:
            continue
        assert got, lg


