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


def test_KBO_팀을_한국어로_부르면_KBO_로_간다():
    """🔴🔴 **조용한 오답을 막는다** — 실측 2026-10-03.

    사용자가 *"KBO · LG 트윈스 · 기아 타이거즈"* 라고 물었을 때 봇이 이랬다:

    ```
    LG 트윈스     → ('mlb', 'Minnesota Twins')       🔴
    롯데 자이언츠  → ('mlb', 'San Francisco Giants')  🔴
    기아 타이거즈  → None
    ```
    ⚠️ 조각(`트윈스`·`자이언츠`)이 MLB 별칭과 겹쳐 잡혔다. 그러면 봇이 **다른
       리그의 다른 경기**를 분석하고 그럴듯한 카드를 낸다 — 0건보다 나쁘다.
    """
    from app.collect import kbo
    want = {
        "LG 트윈스": "LG Twins", "기아 타이거즈": "Kia Tigers",
        "KIA 타이거즈": "Kia Tigers", "두산 베어스": "Doosan Bears",
        "한화 이글스": "Hanwha Eagles", "삼성 라이온즈": "Samsung Lions",
        "롯데 자이언츠": "Lotte Giants", "SSG 랜더스": "SSG Landers",
        "NC 다이노스": "NC Dinos", "키움 히어로즈": "Kiwoom Heroes",
        "KT 위즈": "KT Wiz",
    }
    for ko, en in want.items():
        got = aliases.find_team(ko)
        assert got == ("kbo", en), f"{ko} → {got} (원하는 것 ('kbo', {en!r}))"
    # 🔴 **어댑터가 아는 이름이어야** 한다 — 별칭이 가리키는 팀을 수집이 못 찾으면
    #    그 별칭은 죽은 선언이다(사본 금지: 표는 어댑터가 원본이다)
    for ko, en in want.items():
        assert en in kbo.TEAM_IDS, f"{ko} → `{en}` 이 KBO 어댑터 표에 없다"


def test_MLB_질문은_그대로_돈다():
    """⚠️ KBO 를 넣다가 MLB 를 깨뜨리지 않았는지 — 가르는 것은 **길이**다."""
    assert aliases.find_team("트윈스") == ("mlb", "Minnesota Twins")
    assert aliases.find_team("자이언츠") == ("mlb", "San Francisco Giants")
    assert aliases.find_team("타이거스") == ("mlb", "Detroit Tigers")


def test_갈리는_이름은_혼자_오면_고르지_않는다():
    """🔴 `롯데` 는 KBO(자이언츠)·NPB(지바 롯데)에 **둘 다** 있다.

    ⚠️ 하나를 고르면 그것이 추측이다 — 사용자가 어느 쪽인지 말해야 한다.
    """
    assert aliases.find_team("롯데") is None
