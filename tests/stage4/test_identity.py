"""④ **신원·날짜 필터** 계약 (사용자 설계 2026-10-02).

> ④ 엉뚱한 걸 버린다 — 손흥민이 나오면 남자팀이라 버림 → **fotmob 스쿼드 명단과 기사
> 속 선수명 대조, 명단 밖 선수뿐이면 폐기**. 발행 시각이 킥오프 후면 폐기

🔴 **0건보다 틀린 자료가 나쁘다.** 0건은 "자료 부족"으로 멈추지만 틀린 자료는 카드를
   만든다 — 오늘 여자 아시안게임에서 남자 대표팀 자료가 들어온 것이 그 사고였다.
"""
from __future__ import annotations

import asyncio
import importlib.util
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import cells, ids, verify
from app.blackboard import Blackboard, Fact
from app.net import Fetched, Net
from tests._helpers import strip_docs

ROOT = Path(__file__).resolve().parents[2]
WOMEN = ("지소연", "장슬기", "조소현", "추효주")
# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **실제 시계 기준이다** — 고정 날짜는 지뢰다 (2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 종전은 `datetime(2026, 10, 2, 6, …)` **고정**이었다. 🔴 `verify.recent_enough`
#     가 *"2일 넘으면 거부"* 이고 `now` 는 **진짜 지금**이라, 날짜가 이틀 지나자
#     이 파일이 통째로 빨개졌다(실측 2026-10-04: `검증거부(date: 2일 지난 기사다)`).
#  ⚠️ 그 실패는 **코드 결함이 아니다** — 시험이 시계에 매여 있던 것이다.
#  🔴 그래서 **지금 기준**으로 잡는다. 시험이 어느 날 돌아도 같은 뜻이 된다.
#  🔴 **킥오프는 가깝게**(+2시간) 잡는다. ⚠️ 멀리 잡으면 *"기사는 킥오프 3시간
#     전"* 이 **미래 발행**이 되어 다른 검증기에 걸린다(실측 2026-10-04:
#     `검증거부(date: 발행이 미래다)`). 두 검증기가 양쪽에서 조인다:
#       `recent_enough`  기사가 **2일보다 오래되면** 거부
#       같은 함수        기사가 **2시간 넘게 미래면** 거부
#     → 킥오프 +2시간이면 "킥오프 3시간 전" 기사가 **1시간 전**이 된다. 둘 다 통과.
KICK = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=2)


def test_명단_밖_선수는_버린다():
    """🔴 **손흥민은 여자 대표팀 명단에 없다.** 이름이 모호해도 명단은 모호하지 않다."""
    assert ids.squad_check("장슬기", WOMEN).ok is True
    bad = ids.squad_check("손흥민", WOMEN)
    assert bad.ok is False and "명단에 없다" in bad.reason
    assert ids.squad_check("Heung-Min Son", WOMEN).ok is False
    # 🔴 **성만 적힌 기사**도 맞춘다 — `Son` ↔ `Heung-Min Son`
    assert ids.in_roster("Son", ("Heung-Min Son", "Min-Jae Kim")) is True
    # ⚠️ 두 글자 미만은 보지 않는다 — `Li` 가 수십 명과 맞는다
    assert ids.in_roster("Li", ("Heung-Min Son",)) is False


def test_명단을_모르면_막지_않고_내린다():
    """🔴 `None` 을 `True` 로 때우면 명단 검사가 **아무것도 막지 않는다.**

    ⚠️ 실측 2026-10-02 의 손흥민이 그 구멍으로 들어왔다.
    """
    assert ids.in_roster("아무개", ()) is None
    got = ids.squad_check("아무개", [])
    assert got.ok is True and got.unknown is True and got.hardness == "soft"


def test_명단_대조가_검증기_밖에_있다():
    """🔴 `verify` 는 **의존 없는 모듈**이다(계약이 잠근다) — 그래서 `ids` 에 있다.

    ⚠️ 처음에 `verify` 에 넣었다가 그 계약이 **그 자리에서** 빨개졌다.
    """
    src = strip_docs(inspect.getsource(verify))
    assert "name_key" not in src, "검증기가 선수 신원에 기대고 있다"
    assert hasattr(ids, "squad_check") and hasattr(ids, "roster_keys")


def test_세포가_명단으로_사실을_가른다():
    """🔴 함수가 있는 것과 **세포가 그것을 쓰는 것**은 다르다 — 실제로 돌려 본다."""

    def _parse(payload, q):
        return [Fact(question_id=f"{q.id}:player",
                     value={"player_name": "손흥민", "basis": "suspension"},
                     hardness="hard", published_at=KICK - timedelta(hours=3),
                     article_title="t", article_body="손흥민 결장",
                     source="https://ok.example/x")]

    def _make(roster):
        cell = cells.Cell(
            cells.Question(cells.Q_LINEUP, "AG:한국:2026-10-02", team="한국",
                           league="Asian Games", deadline=KICK),
            # ⚠️ `tier=3`(프리뷰)은 이 질문 타입에서 **기존 규칙이 거부한다**
            #    (*"프리뷰 사이트는 선발·라인업 확인용만"*) — 명단 검사를 보려면
            #    그 앞에서 안 걸려야 하므로 공식 층을 쓴다
            [cells.Source("기사", "url", url="https://ok.example/x", tier=1,
                          parse=_parse, verify=True)],
            budget=cells.Budget(searches=0, fetches=1))
        cell.roster = roster
        net = Net()

        async def _get(url, **k):
            return Fetched(url, True, 200, "<html>손흥민 결장</html>")

        net.get = _get                              # type: ignore[assignment]
        bb = Blackboard()
        state = asyncio.run(cell.run(net, bb, search=None, scores=None))
        return state, cell

    # 🔴 여자 명단 → **버린다**
    state, cell = _make(WOMEN)
    assert state != "found", state
    assert any("명단에 없다" in t for t in cell.tried), cell.tried

    # 🔴 그 선수가 든 명단 → 받는다
    state2, _ = _make(("손흥민", "김민재"))
    assert state2 == "found", state2

    # ⚠️ 명단이 비면 **막지 않고 soft 로 내린다** — 통과가 아니라 "못 쟀다"다.
    #    🔴 세포 상태(`found`/`unknown`)로 단정하지 않는다 — 그 뒤 층 검사가 soft 를
    #       어떻게 보는지는 **다른 규칙**이고 여기서 그것을 또 정하지 않는다.
    #       묻는 것은 하나다: **버리지 않았고, 사유를 남겼나.**
    _state3, cell3 = _make(())
    assert any("명단을 몰라" in t for t in cell3.tried), cell3.tried
    assert not any("명단에 없다" in t for t in cell3.tried), cell3.tried






# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **거짓 변수를 막는다** — 실측 2026-10-03 (콜롬비아 vs 파라과이)
# ══════════════════════════════════════════════════════════════════
#
# 파라과이 수비 결장을 물었더니 좁은 질문이 `yes` 를 내고 인용이 이것이었다:
#
#   "Toluca have confirmed **Alexis Vega** has suffered an injury that will keep
#    him out of **Mexico's** upcoming **November** international friendlies"
#
# 🔴 멕시코 선수 · 11월 경기다. 인용이 본문에 실재해서 `hard` 로 통과했고 변수
#    `def_absence·home·hard` 가 **거짓으로** 섰다. 원인 셋을 전부 못 박는다.

_VEGA = ("Toluca have confirmed Alexis Vega has suffered an injury that will "
         "keep him out of Mexico's upcoming November international friendlies.")




def test_남의_팀_선수_결장은_명단_대조가_막는다():
    """🔴 Vega 는 **26명 스쿼드 밖**이다 — 명단이 그 자리를 막는다."""
    from app import ids
    squad = ("Gastón Olveira", "Juan Cáceres", "Gustavo Gómez",
             "Omar Alderete", "Miguel Almirón", "Julio Enciso")
    got = ids.squad_check("Alexis Vega", squad)
    assert not got.ok and "명단에 없다" in got.reason, got
    # 🔴 우리 선수는 통과한다
    assert ids.squad_check("Miguel Almirón", squad).ok


def test_스쿼드는_교체까지_센다():
    """🔴 명단이 **선발 11명**뿐이면 교체 명단 선수가 기사에 나올 때 멀쩡한 사실을
    *"남의 팀"* 으로 버린다(실측 2026-10-03: 명단이 11명이었다)."""
    from app.collect import fotmob
    side = {"starters": [{"name": f"S{i}"} for i in range(11)],
            "subs": [{"name": f"B{i}"} for i in range(15)]}
    got = fotmob.squad_names(side)
    assert len(got) == 26, len(got)
    assert "B0" in got and "S0" in got


def test_주체도_팀도_없는_추출_사실은_거부한다():
    """🔴 붙일 근거가 **0** 이면 우리 경기 이야기가 아니다.

    ⚠️ 주체(선수)가 **있을 때는 여기서 막지 않는다** — 명단 대조가 더 정확히 한다
       (명단을 모르면 `soft` 로 내리는 규율까지 포함).
    """
    from app import cells as C
    from app.blackboard import Fact
    f = Fact(question_id="counter:x", value={"ask": "event_match",
                                             "answer": "yes"},
             hardness="hard", article_title="Mexico friendlies",
             article_body=_VEGA, extracted_by="ASK:event_match:qwen3:8b")
    assert C._from_extractor(f)
    # 🔴 규칙 파서 사실은 이 문을 지나지 않는다
    g = Fact(question_id="x", value={}, hardness="hard",
             extracted_by="rule:npb_standings")
    assert not C._from_extractor(g)
    # ⚠️ `extracted_by` 가 비어 있어도 추출기가 아니다(시험 고정물·단순 파서)
    h = Fact(question_id="x", value={}, hardness="hard")
    assert not C._from_extractor(h)


def test_감독_교체는_부임_시점이_없으면_변수가_아니다():
    """🔴🔴 봇이 이것을 **변수 둘**로 냈다(`splits_direction` 이라 두 배로 센다):

        `coach_change=True · left=None · since=None · arrived='named'`

    두 감독 다 유임이었다. §4 는 *"감독 교체 · **부임 시점** · 첫 경기 여부"* 를
    함께 요구한다 — 시점이 없으면 **미결정**이다.
    """
    from app import classify
    g = classify.Game(home="Colombia", away="Paraguay", sport="soccer",
                      league="Friendlies")
    bare = {"team": "Colombia", "coach_change": True, "left": None,
            "arrived": "named", "since": None}
    side, why, bad = classify._dir_coach_change(bare, g)
    assert side is None and "부임 시점" in bad, (side, why, bad)
    # 🔴 시점이 있으면 선다
    ok = {**bare, "since": "2026-07-01"}
    side2, why2, bad2 = classify._dir_coach_change(ok, g)
    assert side2 == "home" and not bad2, (side2, why2, bad2)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **기술 5 — 신원·날짜·출처 등급 필터** (사용자 기술 지시 2026-10-03)
# ══════════════════════════════════════════════════════════════════
#
# > 내가 엉뚱한 기사를 버리는 기준을 코드로 옮기면 넷이다 … `both_teams_named` ·
# > `roster_overlap >= 2` · 경기 전 7일 · 표식 불일치. 그리고 **출처 등급**:
# > 협회·구단 공식 > 전국지 > 현지지 > … > **베팅 팁 사이트**(단독으로는 안 쓴다).


def test_출처_등급을_호스트가_정한다():
    """🔴 층 상수는 전부터 있었는데 **소스가 선언한 층**을 그대로 썼다 — 검색으로
    나온 기사가 전부 같은 층이어서 **인도네시아 팁 사이트와 전국지가 구분되지
    않았다**(실측 2026-10-03)."""
    from app import rules, verify
    off, _ = rules.tier_of_host("https://npb.jp/bis/x", verify.TIER_PRIMARY)
    pri, _ = rules.tier_of_host("https://www.abc.com.py/x", verify.TIER_PREVIEW)
    pre, _ = rules.tier_of_host("https://www.fotmob.com/x", verify.TIER_PRIMARY)
    tip, why = rules.tier_of_host("https://forebet.com/x", verify.TIER_PRIMARY)
    assert off == verify.TIER_OFFICIAL and pri == verify.TIER_PRIMARY
    assert pre == verify.TIER_PREVIEW
    # 🔴 **팁 사이트는 최하** — 판정 입력 금지 층이다
    assert tip == verify.TIER_FORECAST and "forecast" in why
    assert not verify.admissible(tip, purpose="judgement").ok
    # 🔴 표에 없으면 **그 소스가 선언한 층** — 모르는 것을 최하로 떨어뜨리지 않는다
    unk, why2 = rules.tier_of_host("https://unknown.example/x",
                                   verify.TIER_PRIMARY)
    assert unk == verify.TIER_PRIMARY and "없다" in why2


def test_명단_겹침을_센다():
    """🔴 `1` 로 두면 이름이 한 번 스친 기사가 통과한다 — 사용자 예시가 `>= 2` 다."""
    from app import cells
    squad = ("Miguel Almirón", "Julio Enciso", "Gustavo Gómez")
    # 🔴 기사는 **성만** 쓴다
    assert cells._roster_overlap("Almirón y Enciso entrenaron", squad) == 2
    assert cells._roster_overlap("Almirón entrenó solo", squad) == 1
    assert cells._roster_overlap("nada que ver", squad) == 0
    # ⚠️ 명단을 모르면 0 이고 **검사하지 않는다**(호출부가 사유를 남긴다)
    assert cells._roster_overlap("Almirón", ()) == 0
    assert cells.ROSTER_OVERLAP_MIN == 2


def test_두_팀_검사와_명단_겹침이_추출기에_걸렸다():
    """🔴 종전에는 **우리 팀 하나**만 봤다 — *"파라과이"* 가 스쳐 나오는 다른 경기
    기사가 통과했다. ⚠️ D46 — 독스트링·주석을 뺀 코드만 본다."""
    import inspect

    from app import cells
    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(cells.Cell._verified))
    assert "_roster_overlap(" in src, "명단 겹침 검사가 없다"
    assert "opponent" in src, "두 팀 검사가 없다"
    # 🔴 출처 층을 호스트가 정한다
    assert "tier_of_host(" in src


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **기술 6 — 중복 제거 후 독립 출처 세기** (사용자 기술 지시 2026-10-03)
# ══════════════════════════════════════════════════════════════════
#
# > 같은 보도자료가 8개 매체에 복사되면 출처 **8개가 아니라 1개**다. 문장 유사도로
# > 묶은 뒤 센다. 두 출처가 서로 다르면 **미상**, 시간 순으로 더 새 상태가 명시돼
# > 있으면("의심" → "결장 확정") **새 쪽**을 쓴다.


def _f(quote, *, tier=2, value=None, when=None):
    from app.blackboard import Fact
    return Fact(question_id="x", value=value or {"p": "A"}, hardness="soft",
                quote=quote, tier=tier, published_at=when)


def test_표기만_다른_같은_보도를_하나로_센다():
    """🔴 종전 중복 제거는 **완전 일치**였다 — 구두점 하나만 달라도 별건이 되어
    같은 보도가 변수 여럿으로 세어졌고 방향 묶음 strength 가 부풀었다."""
    from app import blackboard as B
    a = "Toluca have confirmed Alexis Vega has suffered an injury"
    assert B.similar(a, a + ".") >= B.DUP_SIMILARITY
    assert B.similar(a, "앙굴로가 발목 부상으로 결장한다") < B.DUP_SIMILARITY
    n, groups = B.independent_sources([_f(a), _f(a + "."), _f("다른 이야기다")])
    assert n == 2 and sorted(len(g) for g in groups) == [1, 2], groups


def test_복사된_보도자료는_단독_출처다():
    """🔴 여덟 매체에 복사돼도 **출처는 하나**다 — 확정이 아니다."""
    from app import blackboard as B
    a = "구단이 결장을 확인했다"
    st, why = B.claim_state([_f(a), _f(a + " "), _f(a + ".")])
    assert st == B.FOUND and "단독" in why, (st, why)
    # 🔴 서로 다른 글 둘이면 **독립 둘**이다
    st2, why2 = B.claim_state([_f(a), _f("다른 매체가 다른 문장으로 썼다")])
    assert st2 == B.FOUND and "독립 출처 2곳" in why2, why2
    # 🔴 **공식(1층)은 단독이라도 확정**이다
    st3, why3 = B.claim_state([_f(a, tier=1)])
    assert st3 == B.FOUND and "공식" in why3


def test_값이_엇갈리면_미상이고_새_쪽이_있으면_새_쪽이다():
    """🔴 *"두 출처가 서로 다르면 미상, 시간 순으로 더 새 상태가 명시돼 있으면
    새 쪽을 쓴다"* — 사용자 규칙 그대로."""
    from datetime import datetime, timezone

    from app import blackboard as B
    old = _f("의심", value={"state": "의심"})
    new = _f("결장 확정", value={"state": "확정"})
    # 🔴 날짜가 없으면 **미상**이다 — 어느 쪽이 새 것인지 모른다
    st, why = B.claim_state([old, new])
    assert st == B.CONTRADICTED and "서로 다른 값" in why, (st, why)
    # 🔴 날짜가 있으면 **새 쪽**을 쓴다
    t0 = datetime(2026, 10, 2, 9, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 2, 18, tzinfo=timezone.utc)
    st2, why2 = B.claim_state([_f("의심", value={"state": "의심"}, when=t0),
                               _f("결장 확정", value={"state": "확정"}, when=t1)])
    assert st2 == B.FOUND and "더 새 쪽" in why2, why2


def test_슬롯이_독립_출처_수를_들고_있다():
    """🔴 `reconcile` 은 **하나를 고르는** 일이고 이것은 **몇 곳이 말하나**다 —
    둘은 다른 질문이라 둘 다 필요하다."""
    from app import blackboard as B
    bb = B.Blackboard()
    a = "구단이 결장을 확인했다"
    for q in (a, a + ".", a + " "):
        bb.write(_f(q))
    slot = bb.get("x")
    assert slot.sources == 1, (slot.sources, slot.source_note)
    assert "단독" in slot.source_note
