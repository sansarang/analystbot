"""[UND-1] ⑤가 **상대 선발만** 봐서 언더 방향이 구조적으로 불가능했다.

사용자 2026-09-23: "삭제하고 2 진행해라" — ②는 갈림길 **(가) 양 팀 선발 수집**
(제가 추천한 쪽. (나) "조건 완화"는 한 팀만 보고 언더를 걸게 되어 안 골랐다).

🔴 실측 (최근 14일, `n05_evidence` 전수):
```
starter_recent3 방향   양쪽 다 +   0건   ← 언더 조건은 이것만 성립한다
                      한쪽만 +  329건
⑤가 수집하는 쪽        sides=('away',) 758 · ('home',) 448 · 둘 다  0
```
⑪의 언더 조건은 "양 팀 선발 **모두** 호재"인데 ⑤가 한 팀만 수집하니
`all(v > 0 for v in [0, 1])` 이 영원히 거짓이다 — 14일간 언더 픽 0건.

⚠️ 오버는 정상이었다(`starter_recent3 −1` 403회). 앞서 "오버도 불가능"이라고
   적었던 것은 **틀렸고** 측정이 바로잡았다.

🔴 **⑦의 부호 규약은 그대로다.** `_direction_of` 는 `pick − other` 라 양쪽을
   실으면 **더 정확**해진다 — 둘 다 호재면 상쇄(0)이고, 그때 조정이 없는 것이
   맞다. 종전에는 우리 선발이 아무리 좋아도 상대만 보고 불리로 읽었다.
"""
from __future__ import annotations

import inspect

import pytest

from app.flow.nodes import n05_evidence as N5

#: 리그 기준 4.2 대비 — 좋은 등판(자책 1) · 나쁜 등판(자책 8)
GOOD = [{"innings": 7.0, "er": 1, "k": 6, "opponent": "X",
         "d": __import__("datetime").date(2026, 9, 17)} for _ in range(2)]
BAD = [{"innings": 5.0, "er": 8, "k": 2, "opponent": "Y",
        "d": __import__("datetime").date(2026, 9, 17)} for _ in range(2)]


def test_양쪽_선발을_다_조회한다():
    """🔴 이 단위의 전부 — 종전에는 `opp_starter_of` 하나만 봤다."""
    src = inspect.getsource(N5._starter_recent3)
    assert "home" in src and "away" in src
    assert "_both" in src or "for side in" in src, "여전히 한 쪽만 본다"


@pytest.mark.asyncio
async def test_양쪽_모두_호재면_방향이_상쇄된다():
    """🔴 이것이 언더가 서는 자리다(⑪ `total_direction`)."""
    import app.flow.direction as DIR

    d = DIR.merge(DIR.starter_direction(GOOD, league_era=4.2, team="home"),
                  DIR.starter_direction(GOOD, league_era=4.2, team="away"))
    assert d.get("home") == 1 and d.get("away") == 1, d
    from app.flow.nodes.n07_adjust import _direction_of

    assert _direction_of(d, "home") == 0.0, "양쪽 호재인데 한쪽 편을 든다"


def test_언더가_실제로_선다():
    """🔴 ⑪ `total_direction` 이 언더를 내는지 **불러서** 본다."""
    from app.flow.nodes.n11_value import total_direction

    class _S:
        n05_evidence = [{"var": "starter_recent3",
                         "direction": {"home": 1, "away": 1, "dev": -0.5}},
                        {"var": "bullpen_3d", "direction": {"home": 0, "away": 0}}]

    got = total_direction(_S())
    assert got["side"] == "under", got


def test_오버는_그대로_선다():
    """⚠️ 반대 위험 — 오버는 종전에도 동작했다(403회). 깨면 안 된다."""
    from app.flow.nodes.n11_value import total_direction

    class _S:
        n05_evidence = [{"var": "starter_recent3",
                         "direction": {"home": -1, "away": 0}},
                        {"var": "bullpen_3d", "direction": {"home": 0, "away": 0}}]

    assert total_direction(_S())["side"] == "over"


def test_한쪽만_호재면_언더가_아니다():
    """🔴 **(나)를 고르지 않았다는 잠금.** 한 팀만 보고 언더를 걸면 안 된다."""
    from app.flow.nodes.n11_value import total_direction

    class _S:
        n05_evidence = [{"var": "starter_recent3",
                         "direction": {"home": 1, "away": 0}},
                        {"var": "bullpen_3d", "direction": {"home": 0, "away": 0}}]

    assert total_direction(_S())["side"] is None


@pytest.mark.asyncio
async def test_한쪽_선발만_알면_그쪽만_싣는다():
    """⚠️ 예고 전이면 한쪽만 안다 — 지어내지 않는다."""
    import app.flow.direction as DIR

    d = DIR.merge(DIR.starter_direction(BAD, league_era=4.2, team="away"))
    assert d.get("away") == -1 and not d.get("home"), d


def test_원문에_양쪽_선발이_다_나온다():
    """⚠️ 서술이 근거를 말해야 한다 — 어느 선발을 봤는지."""
    src = inspect.getsource(N5)
    assert "_starter_recent3" in src
