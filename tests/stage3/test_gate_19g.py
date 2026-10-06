"""단계 3 **게이트** — §19-g 세포망 재현 픽스처 7건 + 카오스.

§19-g 원문(09-27 실측):

1. 다음스포츠 K리그 일정(지난주) → 검증기 거부 → 연합 순연 기사에서 "강원-인천
   1경기" 도출.
2. 소프트뱅크 라인업: 스포츠나비 JS 실패 → 西スポ 스니펫에서 나카무라 아키라
   6번·이마미야·오쓰 추출.
3. 히로시마 라인업: 安芸の者 한 페이지에서 양 팀 9명 + 고조노 부재 도출.
4. 카라스코 최근 등판: 2회 변형 검색 후 unknown, 사유 기록, 방아쇠 생성.
5. 휴스턴 선발: unknown → 반증 세포 → RotoWire hit → 웨스네스키 3.50/1.15 사실
   → 판정 상향.
6. 김건희 동명이인: 인천 DF(A대표 소집)와 강원 FW를 다른 player_id 로 분리,
   결장은 인천 쪽에만.
7. 텍사스-미네소타 라이브 스코어 세포가 휴스턴 동기 등급을 유지.

🔴 **이 파일은 무엇이 증명되고 무엇이 안 되는지를 갈라 적는다.** 2026-09-27 의
   페이지는 다시 녹음할 수 없고, 저장소에 남은 실측 응답은 **3건**(西スポ 질의·
   安芸の者 질의·Astros 질의)뿐이다. 나머지 4건의 원본 응답은 없다.
   → 없는 것을 있는 척하지 않는다(§11-3). 각 항목에 **무엇으로 무엇을 증명하나**를
     적고, 원본 응답이 없는 항목은 **기계 부분만** 검사한다고 밝힌다.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

from app import cassette, queries, searchcells, verify
from app.blackboard import Blackboard, Fact
from app.cells import (Q_LINEUP, Q_STARTER_RECENT, Budget, Cell, Question,
                       Source, SourceScores)
from app.collect import kleague
from app.net import Net
from app.search import SearxSearch

DAY = date(2026, 9, 27)
KST = timezone(timedelta(hours=9))
#: 🔴 09-27 경기 시각 — 시간축이 세포를 닫지 않게 **그날 T-30분**에 선다.
STARTS = datetime(2026, 9, 27, 14, 0, tzinfo=KST)


@pytest.fixture
def replay(monkeypatch):
    """🔴 `replay` — 네트워크에 가지 않는다. 가면 터진다."""
    monkeypatch.setenv(cassette.MODE_ENV, cassette.REPLAY)
    monkeypatch.setenv(cassette.DAY_ENV, str(DAY))
    monkeypatch.delenv(cassette.DIR_ENV, raising=False)

    async def _explode(*a, **k):
        raise AssertionError("🔴 게이트가 네트워크에 갔다 — §19-g 는 "
                             "'실제 네트워크 없이' 를 요구한다")

    monkeypatch.setattr("httpx.AsyncClient.get", _explode)
    return SearxSearch()




# ══════════════════════════════════════════════════════════════════
# ② 소프트뱅크 라인업 — 🔴 원본 응답 있음 (카세트 정확)
# ══════════════════════════════════════════════════════════════════













def test_19g_2_오쓰_예고선발이_그날_응답에_있다(replay):
    """§19-g-2 의 *"오쓰"* — 🔴 그것은 **라인업이 아니라 예고 선발**이다.

    그날 응답의 daily.co.jp 스니펫이 `２７日の予告先発 / ソフトバンク・大津` 이다.
    ⚠️ 라인업 파서가 그것을 타순으로 읽으면 안 된다 — 예고 선발은 `starters` 다.
       그래서 여기서는 **응답에 있다**는 것만 확인하고, 그 사실을 어느 표에 넣는지는
       §13-c(양 팀 9명 검사)가 정한다.
    """
    hits = asyncio.run(replay.query("ソフトバンク スタメン 9月27日", lang="ja"))
    assert hits, "카세트가 안 읽혔다"
    blob = " ".join(f"{h.title} {h.snippet}" for h in hits)
    assert "大津" in blob, "그날 응답에 오쓰가 없다"
    assert "予告先発" in blob




def test_재현_시각이_카세트_날짜로_고정된다(replay):
    """🔴 **재현에는 시계가 필요하다.**

    §12-c-1 은 *"발행이 오늘 또는 어제"* 를 요구한다. 2026-09-27 카세트를 며칠
    뒤에 재생하면 그날 기사가 전부 *"N일 지난 기사"* 로 거부된다 — 그것은 코드
    결함이 아니라 **시계를 안 고정한 결함**이다(실측 2026-09-30: 게이트가 그것으로
    터졌다).

    ⚠️ 절제 2026-09-30: `reference_now()` 가 늘 실제 시각을 내도록 되돌렸더니
       계약이 **통과해 버렸다** — 시계를 검사하는 계약이 없었다.
    🔴 운영(`off`)에서는 **진짜 지금**이어야 한다. 과거 시각으로 도는 일은 없다.
    """
    now = cassette.reference_now()
    assert now.date() == DAY, f"재현 시각이 카세트 날짜가 아니다: {now}"

    # 🔴 그 시각 기준으로 **그날 기사가 통과한다**
    art = {"title": "スタメン発表", "published_at": datetime(
        2026, 9, 27, 12, 0, tzinfo=KST), "tier": verify.TIER_PRIMARY}
    assert verify.check_article(art, now).ok, "그날 기사가 거부됐다"
    # 🔴 며칠 전 기사는 여전히 거부된다 — 시계를 늦췄다고 검증기가 느슨해지지 않는다
    old = dict(art, published_at=datetime(2026, 9, 20, 12, 0, tzinfo=KST))
    assert not verify.check_article(old, now).ok, "오래된 기사가 통과했다"


def test_운영에서는_진짜_시각이다(monkeypatch):
    """🔴 `off`·`record` 는 **실제 지금**이다 — 카세트 날짜가 운영을 오염시키지 않는다."""
    monkeypatch.setenv(cassette.MODE_ENV, cassette.OFF)
    monkeypatch.setenv(cassette.DAY_ENV, "2026-09-27")
    now = cassette.reference_now()
    assert now.date() == datetime.now(KST).date(), (
        f"운영 시각이 카세트 날짜로 고정됐다: {now}")


# ══════════════════════════════════════════════════════════════════
# ③ 히로시마 라인업 — 🔴 원본 응답 있음 (카세트 정확)
# ══════════════════════════════════════════════════════════════════





# ══════════════════════════════════════════════════════════════════
# ⑤ 휴스턴 선발 — ⚠️ 카세트 근사 (질의가 다르다)
# ══════════════════════════════════════════════════════════════════



def test_19g_5_카세트가_근사임을_스스로_밝힌다(replay):
    """🔴 **근사를 숨기지 않는다.** 카세트 파일이 `approx` 로 그것을 적고 있어야
    한다 — 안 적으면 다음 세션이 이 게이트를 "검색어까지 증명됐다"고 읽는다.
    """
    from app.search import SEARXNG_URL, _lang
    params = {"q": "Houston Astros probable pitcher Sep 27",
              "format": "json", "language": _lang("en")}
    got = cassette.load("search", f"{SEARXNG_URL}/search",
                        cassette.query_string(params), when=DAY)
    assert "approx" in got, "근사 카세트가 그 사실을 안 적었다"
    assert got["approx"]["그날 던진 질의"] == \
        "Astros probable pitcher September 27"

    # 🔴 반대로 **정확한** 카세트에는 그 칸이 없어야 한다
    p2 = {"q": "ソフトバンク スタメン 9月27日", "format": "json",
          "language": _lang("ja")}
    exact = cassette.load("search", f"{SEARXNG_URL}/search",
                          cassette.query_string(p2), when=DAY)
    assert "approx" not in exact, "정확한 카세트에 근사 표시가 붙었다"






# ══════════════════════════════════════════════════════════════════
# ① K리그 일정 — 🔴 원본 응답 없음 · 기계 부분만
# ══════════════════════════════════════════════════════════════════







# ══════════════════════════════════════════════════════════════════
# ④ 카라스코 — 🔴 원본 응답 없음 · 기계 부분만
# ══════════════════════════════════════════════════════════════════



def test_19g_4_검색_0건은_없음이_아니다():
    """🔴 §7-5e — *"검색 0건은 '없음'이 아니라 unknown 이다."*"""
    slot = Blackboard().unknown("starter_recent:x", "변형 2회 후 0건")
    assert slot.state == "unknown" and slot.value is None
    assert slot.reason == "변형 2회 후 0건"


# ══════════════════════════════════════════════════════════════════
# ⑥ 동명이인 — 🔴 DB 가 필요하다 · 규칙만 검사
# ══════════════════════════════════════════════════════════════════

def test_19g_6_팀_불명이면_미상이다():
    """§19-g-6 — *"인천 김건희(DF)와 강원 김건희(FW)를 다른 player_id 로 분리."*

    🔴 **증명되는 것**: 팀이 확정되지 않으면 `resolve_by_name` 이 **즉시 미상**이고,
       같은 팀에 동명이인이 둘이면 등번호 없이는 **미상**이다. 거짓 매칭보다 미상이
       낫다(§7-3) — 이름만으로 맞추면 결장이 **상대 팀에** 붙는다.

    ⚠️ 실제 두 선수를 넣고 갈라지는지는 DB 가 있어야 본다. 그 실측은 주 세션이
       psql 로 했고 보고서에 원문이 있다 — 여기서는 규칙을 검사한다.
    """
    from app import ids

    class _Conn:
        def __init__(self, rows):
            self.rows = rows

        async def fetchrow(self, *a):
            return self.rows[0] if self.rows else None

        async def fetch(self, *a):
            return self.rows

    # 팀 불명 → 🔴 즉시 미상 (DB 를 보지도 않는다)
    got = asyncio.run(ids.resolve_by_name(_Conn([]), league="K리그1",
                                          team=None, name="김건희"))
    assert got == (None, ids.MATCH_NONE)

    # 같은 팀에 동명이인 둘 → 🔴 미상
    got = asyncio.run(ids.resolve_by_name(
        _Conn([{"player_id": 1}, {"player_id": 2}]),
        league="K리그1", team="인천", name="김건희"))
    assert got == (None, ids.MATCH_NONE), got

    # 팀 확정 + 유일 → likely
    got = asyncio.run(ids.resolve_by_name(
        _Conn([{"player_id": 7}]), league="K리그1", team="인천", name="김건희"))
    assert got == (7, ids.MATCH_LIKELY), got


def test_19g_6_귀속불명_결장은_원장에_안_들어간다():
    """🔴 `absences.team` 은 NOT NULL 이다 — 아무 팀에 붙이면 **상대 팀**에 붙는다.

    §17-g-3 · M14: *"두 팀 언급 기사는 귀속 불명이면 어느 팀에도 안 붙임."*
    """
    import inspect

    from tests._helpers import strip_docs

    from app.collect import ingest
    src = strip_docs(inspect.getsource(ingest._absences))
    assert "if not f.team:" in src, "귀속 불명을 걸러내지 않는다"
    assert "귀속불명" in inspect.getsource(ingest._absences)


def test_19g_6_이름_정규화가_한글을_지우지_않는다():
    """⚠️ 실사고 2026-09-21: `NFKD → ascii ignore` 가 `'박건우' → ''` 로 만들어
    **한국 선수 이름이 전부 서로 일치**했다. 그러면 동명이인 분리가 무의미하다.
    """
    from app import ids
    assert ids.name_key("김건희") != ""
    assert ids.name_key("김건희") != ids.name_key("김민석")
    # 라틴 발음부호는 벗긴다
    assert ids.name_key("Muñoz") == ids.name_key("Munoz")


# ══════════════════════════════════════════════════════════════════
# ⑦ 라이브 스코어 — 🔴 원본 응답 있음(npb 픽스처) · 세포 경계만
# ══════════════════════════════════════════════════════════════════

def test_19g_7_라이브_세포는_경기_시작_후에도_깬다():
    """§19-g-7 — *"텍사스-미네소타 라이브 스코어 세포가 휴스턴 동기 등급을 유지."*

    🔴 **증명되는 것**: §19-d 가 *"경기 시작이면 그 경기의 모든 세포는 종료"* 라고
       했지만 **라이브만 예외**다. 타 구장 결과는 경기 중에 봐야 쓸모가 있다.

    🔴 **원문 뒷부분은 재현 대상이 아니다.** *"휴스턴 **동기 등급**을 유지"* 의
       "동기 등급"은 **v4 §8 이 폐기한 어휘**다(v3 §3 의 동기 4등급). v4 는 승자를
       고르지 않으므로 등급을 유지할 대상이 없다 — 라이브 스코어가 낳는 것은
       **사실**이고, 그 사실이 뒤 단계에서 시나리오 생존에 들어간다(단계 7).
       ⚠️ 그것을 *"단계 7 에서 재현한다"* 고 적으면 폐기된 개념이 돌아온다.
    """
    from app import cells as C
    starts = datetime(2026, 9, 27, 14, 0, tzinfo=KST)
    during = starts + timedelta(minutes=30)
    assert C.awake(C.Q_LIVE, starts, during), "라이브가 경기 중에 잠들었다"
    for q in (C.Q_LINEUP, C.Q_INTENT, C.Q_STARTER_RECENT, C.Q_ABSENCE):
        assert not C.awake(q, starts, during), f"{q} 가 경기 중에 깨어 있다"


def test_19g_7_라이브_사실이_경기별로_갈린다():
    """🔴 한 소스가 여러 경기를 내면 **질문도 여러 개**여야 한다.

    ⚠️ 실측 2026-09-27: 파서가 질문 id 를 안 정해서 라이브 5경기가 **한 질문에
       몰려 모순으로 판정**됐다. 계약이 값 하나짜리 대역이라 못 잡았다.
    """
    bb = Blackboard()
    for gid, score in (("tex-min", "6-1"), ("hou-ath", "0-0")):
        bb.write(Fact(question_id=f"live_score:{gid}",
                      value={"score": score}, hardness="hard"))
    assert len(bb.slots) == 2, bb.slots
    assert bb.contradictions() == [], bb.contradictions()


# ══════════════════════════════════════════════════════════════════
# 🔴 카오스 — §19-g 마지막 문단
# ══════════════════════════════════════════════════════════════════





def test_카오스_엔진이_죽으면_그_엔진만_dead다():
    """🔴 §19-b-4 · §19-i-2 — *"업스트림 엔진이 막히면 **그 엔진만** dead 처리."*

    ⚠️ SearXNG 자체를 죽은 것으로 보면 그날 검색이 통째로 멈춘다.
    """
    s = SearxSearch(engine_ttl=600.0)
    hits = s._hits({"results": [{"title": "t", "url": "https://u",
                                 "content": "c"}],
                    "unresponsive_engines": [["brave", "Suspended"]]}, "q")
    assert len(hits) == 1, "엔진 하나가 죽었다고 결과를 버렸다"
    assert s.dead_engines == {"brave"}
    assert s.alive is not False, "SearXNG 전체를 죽은 것으로 봤다"










