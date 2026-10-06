"""단계 4 계약 — **모든 종목이 같은 깊이를 내는가.**

사용자 지시 2026-10-01:

> 이 경기는 한 예를 설명한 거다 .. **모든 경기를** 사용자가 경기분석 해줘 했을 때
> 내가 보여준 결과치대로 나와야 한다고 .. **거짓없이**

🔴 축구만 깊은 것은 *"모든 경기"* 가 아니다. 이 계약은 **종목마다** 같은 접미사를
   내는지 본다 — 접미사가 갈리면 카드·측정이 종목별로 갈린다.

| 종목 | 어디서 | 깊이 |
|---|---|---|
| 축구 | `fotmob` 경기 페이지(JSON) | 기준 XI·맞대결·폼·통계·선수·순위 |
| 야구 | `statsapi.mlb.com` **공식** | 타순·선수·팀통계 → 따라가서 폼·맞대결 |
| 하키 | `api-web.nhle.com` **공식** | 구장·상태(+경기후 선수) → 따라가서 폼·맞대결·선수·순위 |

⚠️ **하키에는 경기 전 라인업이 없다** — 있는 척하지 않는다(어댑터 머리글이 그렇게
   적어 뒀다). K리그·해외축구는 `sources_context` 가 **없다**; 그것도 사실대로다.
"""
from __future__ import annotations

import inspect

import pytest

from app.cells import SUB_QUESTIONS, Q_LINEUP, Source
from app.collect import fdorg, fotmob, kleague, mlb, nhl
from tests._helpers import strip_docs

#: 🔴 깊이를 가진 어댑터. ⚠️ 목록을 늘리면 아래 계약이 그 종목도 검사한다.
WITH_DEPTH = {"MLB": mlb, "NHL": nhl}
#: 아직 깊이가 없는 어댑터 — **이름으로 남긴다**(조용한 0 금지)
WITHOUT_DEPTH = {"K리그": kleague, "해외축구": fdorg}


def test_깊이가_있는_어댑터는_공식_주소를_쓴다():
    """🔴 키 없음·카드 없음·공식 — §11-7 의 "유료 API 0건" 안이다."""
    assert "statsapi.mlb.com" in mlb.BASE
    assert "api-web.nhle.com" in nhl.API


#: 🔴🔴 **깊이 소스를 몇 개까지 두나 — 그 까닭을 함께 적는다**(2026-10-04).
#
#  종전 계약은 *"요청 하나로 시작한다"* 였다. 그 규율은 맞다 — 공식 API 는 한 번
#  열면 팀 id·약칭을 주고 §19-c 따라가기가 나머지를 연다(예산).
#
#  ⚠️ 그런데 **MLB 는 둘이 필요하다**(실측 2026-10-04 · 사용자 지시 ①):
#
#    ① 박스스코어 → 팀 id → (따라가기) 일정·맞대결·폼
#    ② 🔴 **예고 선발** — `schedule?gamePk=…&hydrate=probablePitcher`
#       → (따라가기) `people/{id}/stats` 로 **방어율**
#
#  🔴 ②를 ①의 따라가기에 넣을 수 없다: 투수 id 는 ②의 **응답**에서 나오고,
#     `cells._follow` 는 **한 겹**만 따라간다(재귀하지 않는다). 즉 2단 사슬이고,
#     이 저장소에서 2단을 쓰는 길은 **소스를 하나 더 두는 것**뿐이다.
#  ⚠️ 박스스코어에는 예고 선발이 없다(끝난 경기의 기록이다) — 한 주소로는 못 얻는다.
#  🔴 그래서 **수를 선언으로 둔다.** 늘리려면 여기 까닭을 적어야 한다.
DEPTH_SOURCES = {
    "MLB": 2,       # 박스스코어 + 예고 선발(2단 사슬 · 위 주석)
    "NHL": 1,
}


@pytest.mark.parametrize("league", sorted(WITH_DEPTH))
def test_깊이_소스는_선언한_수만큼이고_전부_따라가기를_들었다(league):
    """🔴 **요청을 미리 여러 개 열지 않는다**(예산) — 수는 `DEPTH_SOURCES` 선언이다.

    ⚠️ 소스를 늘리면 이 계약이 빨개진다. 그때 **까닭을 위 주석에 적고** 수를 고친다
       — 조용히 늘면 예산이 조용히 는다.
    """
    mod = WITH_DEPTH[league]
    ext = "849848" if league == "MLB" else "nhl-2026020021"
    srcs = mod.sources_context(ext)
    want = DEPTH_SOURCES[league]
    assert len(srcs) == want, (
        f"{league}: 깊이 소스가 {len(srcs)}개다(선언 {want}개) — "
        f"늘렸다면 `DEPTH_SOURCES` 와 그 까닭을 함께 고쳐라: "
        f"{[x.name for x in srcs]}")
    for s in srcs:
        assert isinstance(s, Source) and s.kind == "url" and s.url, s
        assert callable(s.parse), f"{league}:{s.name} 파서가 없다"
        assert callable(s.follow) and callable(s.parse_follow), \
            f"{league}:{s.name} §19-c 따라가기가 없다"
        # 🔴 공식 소스는 기사 검증기의 대상이 아니다(§12-c-5 1층)
        assert s.verify is False and s.tier == 1, s.name


@pytest.mark.parametrize("league", sorted(WITH_DEPTH))
def test_꼴이_아닌_ext_id_에_소스를_만들지_않는다(league):
    """🔴 지어내지 않는다 — 번호가 아니면 빈 목록이다."""
    mod = WITH_DEPTH[league]
    for bad in ("", "  ", "abc", "nhl-xyz", None):
        assert mod.sources_context(bad) == [], f"{league}: {bad!r} 에 소스를 만들었다"


def test_하키는_경기_전_라인업을_만들지_않는다():
    """⚠️ 하키에는 예고 선발·경기 전 라인업이 없다. 골리도 직전에 나온다.

    🔴 어댑터 머리글이 그렇게 적어 뒀고, 코드가 그것을 지켜야 한다 —
       `:baseline` 을 만드는 곳이 **없어야** 한다.

    ⚠️ **D46** — 독스트링·주석을 뺀 **코드만** 본다. 문서가 *"`:baseline` 을 만들지
       않는다"* 고 **설명하는** 것과 코드가 그것을 **만드는** 것은 다르다.
       (첫 판이 바로 그 주석에 걸려 빨개졌다.)
    """
    code = strip_docs(inspect.getsource(nhl))
    assert ":baseline" not in code, "하키가 기준 XI 를 만든다 — 자료가 없다"


def test_접미사가_종목마다_같다():
    """★ 🔴 접미사가 갈리면 카드·측정이 **종목별로 갈린다.**

    원본은 `app/cells.SUB_QUESTIONS` 다. 세 어댑터가 쓰는 접미사를 소스에서 긁어
    그 목록과 대조한다 — 손으로 적지 않는다.
    """
    import re
    used = set()
    for mod in (fotmob, mlb, nhl):
        # 🔴 **숫자를 빼먹지 않는다** — `h2h` 에 `2` 가 있다(첫 판이 이것을 놓쳤다)
        for m in re.finditer(r'f"\{q\.id\}:([a-z0-9_]+)"',
                             strip_docs(inspect.getsource(mod))):
            used.add(m.group(1))
    assert used, "접미사를 하나도 못 찾았다 — 정규식을 보라"
    unknown = sorted(used - set(SUB_QUESTIONS))
    assert unknown == [], f"`SUB_QUESTIONS` 에 없는 접미사: {unknown}"
    # 🔴 세 종목이 **공통으로** 내는 것이 있어야 "같은 깊이"다
    for must in ("h2h", "form", "player"):
        assert must in used, f"어느 어댑터도 `{must}` 를 안 낸다"


def test_깊이가_없는_종목은_있는_척하지_않는다():
    """🔴 K리그·해외축구는 아직 깊이가 없다. **그 사실이 코드에 그대로 있어야** 한다 —
    빈 `sources_context` 를 넣어 "있는데 0건"으로 보이게 하지 않는다.
    """
    for league, mod in WITHOUT_DEPTH.items():
        assert not hasattr(mod, "sources_context"), (
            f"{league}: 깊이가 생겼으면 `WITH_DEPTH` 로 옮기고 계약을 늘려라")




# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **따라가기는 공짜가 아니다** — 실측 2026-10-04
# ══════════════════════════════════════════════════════════════════
#
#  깊이 세포 예산이 `len(depth) + 1` 이었다. 그러면 따라가기가 **공짜**로 셈되고,
#  먼저 온 소스의 따라가기가 예산을 다 쓴다.
#
#  🔴 실측(밀워키 vs 샌디에이고): 예산 **3** · 박스스코어 1 + 따라가기 **3** →
#     새로 붙인 `MLB 예고 선발` 이 **`예산소진`** 으로 **한 번도 안 돌았다.**
#     즉 ①(예고 선발 배선)이 **예산에 막혀** 값을 못 냈다 — 배선만으로는 부족했다.


def test_따라가기_몫을_소스가_선언한다():
    """🔴 몫을 안 적으면 그 소스는 남의 예산으로 돈다(또는 못 돈다)."""
    for league, mod in sorted(WITH_DEPTH.items()):
        ext = "849848" if league == "MLB" else "nhl-2026020021"
        for s in mod.sources_context(ext):
            if callable(s.follow):
                assert int(getattr(s, "follow_max", 0) or 0) > 0, (
                    f"{league}:{s.name} 이 따라가기를 하는데 `follow_max` 를 "
                    f"선언하지 않았다 — 예산이 조용히 샌다")




def test_따라가기가_제_몫보다_많이_안_연다():
    """🔴 한 소스가 남의 몫을 먹지 못한다 — `_follow` 가 자른다."""
    import asyncio

    from app.cells import Blackboard, Budget, Cell, Question, Source

    class _Net:
        def __init__(self):
            self.got = []

        async def get(self, url, **kw):
            self.got.append(url)

            class _F:
                ok = True
                dead = False
                reason = ""
                text = "{}"
                published_at = None
            f = _F()
            f.url = url
            return f

    net = _Net()
    src = Source("몫 둘", "url", url="https://x/0", tier=1,
                 parse=lambda got, q: [],
                 follow=lambda got, q: [f"https://x/{i}" for i in range(1, 6)],
                 parse_follow=lambda got, q: [], follow_max=2)
    cell = Cell(Question("lineup", "x", team="A", league="X"), [src],
                budget=Budget(searches=0, fetches=50))
    got = asyncio.run(cell._follow(src, _Net(), net))
    assert got == []
    # 🔴 **둘만** 열었다(다섯이 아니다)
    assert len(net.got) == 2, net.got
    assert any("선언한 몫이다" in t for t in cell.tried), cell.tried
