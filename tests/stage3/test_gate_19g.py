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


def _run(cell: Cell, search, *, net: Net | None = None, bb=None):
    bb = bb if bb is not None else Blackboard()
    net = net or Net()
    state = asyncio.run(cell.run(net, bb, search=search,
                                 scores=SourceScores()))
    return state, bb


# ══════════════════════════════════════════════════════════════════
# ② 소프트뱅크 라인업 — 🔴 원본 응답 있음 (카세트 정확)
# ══════════════════════════════════════════════════════════════════

def _sb_cell(now_offset_min: int = 30):
    return searchcells.lineup_cell(
        team="福岡ソフトバンクホークス", league="NPB", day=DAY, game_id=None,
        starts=STARTS, local="ソフトバンク",
        opponent="オリックス・バファローズ", opponent_local="オリックス",
        now=STARTS - timedelta(minutes=now_offset_min))


def test_19g_2_소프트뱅크_라인업(replay):
    """§19-g-2 — *"西スポ 스니펫에서 나카무라 아키라 6번·이마미야·오쓰 추출."*

    🔴 **증명되는 것 — 원문이 지목한 사실이 그대로 나온다**
      · 코드의 1번 검색어가 그날 던진 질의와 **글자까지 같다**(`ソフトバンク
        スタメン 9月27日`) — §13-b 표에서 나왔고 사람이 맞춘 것이 아니다.
      · 그날의 실제 응답이 **네트워크 없이** 재생된다(네트워크에 가면 터진다).
      · `中村晃` **6번**(원문의 "나카무라 아키라 6번")
      · `今宮健太` **7번**(원문의 "이마미야")

    ⚠️ **증명되지 않는 것 — 하나도 감추지 않는다**
      · 원문이 지목한 `西スポ` 는 그날 응답의 1위가 아니다. 1위는 §13-a 가 라인업
        소스로 **금지한** baseball-data 였고, 타순을 들고 있던 것은 팀 페이지·
        SANSPO 계열 스니펫이다. 원문의 "西スポ" 는 페이블이 손으로 고른 결과다.
      · 🔴 그 표는 **귀속 불명**(`team=None`)이다 — `vs オリックス` 페이지라
        상대 이름만 나오고 우리 팀 표기가 없다. §17-g-3 이 그때 팀을 붙이지
        말라고 한다(M14). 붙이려면 URL·발행사로 귀속을 정해야 하고 그것은
        단계 4 의 소스 지도 확정에서 한다.
    """
    cell, dropped = _sb_cell()
    assert dropped == [], dropped
    assert cell.sources[0].query == "ソフトバンク スタメン 9月27日"

    hits = asyncio.run(replay.query(cell.sources[0].query, lang="ja"))
    assert hits, "카세트가 안 읽혔다 — 네트워크 없이 재생이 안 됐다"
    facts = searchcells.parse_lineup(hits, cell.question)
    assert facts, "그날 응답에서 타순을 하나도 못 뽑았다"

    # 🔴 원문의 두 사실이 **한 표 안에** 같이 있어야 한다
    want = [f for f in facts if isinstance(f.value, list)
            and {6: "中村晃", 7: "今宮健太"}.items() <= {
                v["order"]: v["name"] for v in f.value}.items()]
    assert want, (
        "中村晃 6번 + 今宮健太 7번 을 한 표에서 못 뽑았다: "
        f"{[[(v['order'], v['name']) for v in f.value] for f in facts if isinstance(f.value, list)]}")
    table = want[0]
    assert table.extracted_by == "rule:JP_COMPACT"
    # 🔴 스니펫 근거는 soft 다(§19-b-3)
    assert table.hardness == "soft"
    # 🔴 귀속 불명 — 우리 팀 표기가 없는 `vs オリックス` 페이지다(§17-g-3)
    assert table.team is None, (
        f"귀속을 {table.team!r} 로 붙였다 — 그 스니펫은 우리 팀을 말하지 않는다")


def test_19g_2_남의_팀_선수를_우리_라인업에_붙이지_않는다(replay):
    """🔴 **M14 재발 방지** — 실측이 잡은 자리다.

    그날 응답에 `ルーカス 4번 三塁` 가 있었다(다른 경기 기사). 귀속 규칙이 없을 때
    코드는 그것을 **소프트뱅크로 저장했고**, 날짜까지 있어서 검증기를 통과해
    `found` 가 됐다 — 즉 **엉뚱한 선수 한 명이 그날 소프트뱅크 라인업이 됐다.**

    §17-g-3: 우리 팀이 언급되지 않은 자료에는 귀속을 붙이지 않는다.
    """
    hits = asyncio.run(replay.query("ソフトバンク スタメン 9月27日", lang="ja"))
    facts = searchcells.parse_lineup(hits, _sb_cell()[0].question)
    for f in facts:
        vals = f.value if isinstance(f.value, list) else [f.value]
        for v in vals:
            if isinstance(v, dict) and "ルーカス" in (v.get("name") or ""):
                assert f.team is None, (
                    "다른 경기 선수(ルーカス)를 소프트뱅크에 붙였다 — M14")


def test_19g_2_다른_날_타순이_걸러진다(replay):
    """🔴 §13-c ① 이 **낡은 타순을 걸러 낸다** — 그것이 이 검사의 값어치다.

    ⚠️ 이 계약은 두 번 고쳐졌고 그 이력이 곧 설명이다:
      · 1판: `contradicted` 를 기대했다 — 틀렸다. §19-c 는 hardness 가 같으면
        **발행 시각이 최신인 쪽**을 택하므로 `found` 가 맞다.
      · 2판: *"날짜 있는 사실이 앞에 온다"* 를 걸었다. 그때 그날 응답에는 **9/23
        타순**(날짜 있음)과 09-27 타순(날짜 없음)이 섞여 있었고, **낡은 것이
        이겼다.** 그것을 위험으로 적어 뒀다.
      · 3판(지금): §13-c ① 을 조이자(**월+일**이 기사에 있어야 한다) 9/23 타순이
        **애초에 사실이 되지 않는다.** 위험이 사라졌다 — 낡은 것을 이기게 두는
        것보다 **들어오지 못하게 막는 것**이 옳다.

    🔴 그래서 지금 검사하는 것: 남은 타순이 **그 경기 날짜를 말하는 기사**에서
       왔는가.
    """
    hits = asyncio.run(replay.query("ソフトバンク スタメン 9月27日", lang="ja"))
    q = _sb_cell()[0].question
    bb = Blackboard()
    for f in searchcells.parse_lineup(hits, q):
        bb.write(f)
    slot = bb.get(q.id)
    assert slot and slot.facts, "타순을 하나도 못 뽑았다"

    # 🔴 남은 사실은 전부 **그 경기 날짜를 말하는 기사**에서 왔다
    for f in slot.facts:
        blob = f"{f.article_title} {f.article_body}"
        assert ("9月27日" in blob or "9/27" in blob or "2026.9.27" in blob), (
            f"그 경기를 말하지 않는 기사가 남았다: {f.source}\n{blob[:160]}")

    # 🔴 §19-g-2 의 사실이 그 안에 있다
    names = {v.get("name") for f in slot.facts
             if isinstance(f.value, list) for v in f.value}
    assert any("中村晃" in (n or "") for n in names), names


def test_19g_2_발행시각_없는_사실은_soft로만_남는다(replay):
    """🔴 **§12-c-1 을 글자대로 지킨다** — *"soft 로만 남긴다."*

    타순을 들고 있는 스니펫에는 **발행 시각이 없다**(그날 응답 44건 중 날짜 있는
    것 14건이고 타순을 가진 것은 거기 없다). 경기 데이터 페이지는 기사가 아니라
    발행 시각을 안 적는다.

    §12-c-1 원문(사용자 결정 2026-09-27): *"날짜를 못 읽는 자료는 통과가 아니라
    거부(fail-closed). 일정·라인업 용도로는 쓰지 못하고 **soft 로만 남긴다**."*

    🔴 **"버린다"가 아니다.** 종전 판은 버렸고, 그래서 §9 필수 8건 ①④ 의 자료를
       찾아 놓고 전부 떨어뜨렸다(실측 2026-09-30, 단계 4).
    🔴 버리지 않는 **조건**은 하나다: 파서가 **§13-c ①**(기사에 그 경기 날짜가
       있는가)로 *"그 경기 것인가"* 를 이미 답했을 때. 그것이 §12-c-1 의 목적을
       다른 수단으로 채운다.
    ⚠️ 그래도 **hard 로 올라가지 않는다** — soft 다. 그것이 원문이다.
    """
    cell, _ = _sb_cell()
    state, bb = _run(cell, replay)
    joined = " / ".join(cell.tried)

    # 🔴 사유가 남는다 — 무엇을 왜 soft 로 뒀는지
    assert "발행 시각 없음" in joined, joined
    assert "soft" in joined and "§12-c-1" in joined, joined

    slot = bb.get(cell.question.id)
    if slot and slot.facts:
        # 🔴 발행 시각 없는 사실은 **soft 를 넘지 않는다**
        for f in slot.facts:
            if f.published_at is None:
                assert f.hardness == "soft", (f.hardness, f.source)


def test_19g_2_그_경기를_말하지_않으면_그래도_버린다(replay):
    """⚠️ `dateless_ok` 가 검증을 **느슨하게** 만든 것이 아니다.

    🔴 §13-c ① 을 통과하지 못한 자료는 파서가 애초에 사실을 내지 않는다 —
       즉 "발행 시각이 없어도 soft 로 남긴다"는 **그 경기 것임이 확인된 자료에만**
       적용된다. 그 둘을 함께 두지 않으면 M13(다른 경기 자료를 오늘 것으로 읽음)이
       돌아온다.
    """
    q = Question(Q_LINEUP, "NPB:西武:2026-09-29", team="埼玉西武ライオンズ",
                 local="西武", league="NPB",
                 deadline=datetime(2026, 9, 29, 21, 0, tzinfo=KST))

    class _H:
        title = ""
        # 🔴 날짜가 **다른 경기**다
        snippet = "西武 9月20日 スタメン 1右 カナリオ2左 平沢3捕 小島4一 ネビン5三 渡部"
        url = "https://x"
        publisher = "x"
        published_at = None

    assert searchcells.parse_lineup([_H()], q) == [], (
        "다른 경기 자료가 통과했다 — §13-c 가 `dateless_ok` 의 전제다")


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


def test_압축_타순은_몇_칸_이상일_때만_타순이다():
    """🔴 `MIN_SLOTS` 가 **정밀도를 지킨다.**

    압축 꼴(`1右 正木智也`)은 번호+한자+이름이라 **스코어·순위 표기와 구별되지
    않는다**(`3 - 5 試合終了`, `2 二塁打`). 타순은 9칸이므로 절반 이상 보일 때만
    타순으로 본다.

    ⚠️ 절제 2026-09-30: `MIN_SLOTS = 1` 로 낮췄더니 계약이 **통과해 버렸다** —
       문턱을 검사하는 계약이 없었다. 그러면 스코어 한 줄이 라인업이 된다.
    """
    q = Question(Q_LINEUP, "x", team="阪神タイガース", local="阪神")

    class _H:
        def __init__(self, body):
            self.title, self.snippet = "", body
            self.url, self.publisher = "https://x", "x"
            self.published_at = None

    # 🔴 한두 칸짜리 잡음은 타순이 아니다
    noise = _H("阪神 3 - 5 試合終了 2 二塁打 記録")
    for f in searchcells.parse_lineup([noise], q):
        assert f.extracted_by != "rule:JP_COMPACT", (
            f"잡음 두 칸을 타순으로 읽었다: {f.value}")

    # 🔴 문턱 이상이면 타순이다 — 검증기가 아무것도 통과 안 시키면 무용하다
    real = _H("阪神 1右 近本光司2中 中野拓夢3三 佐藤輝明4一 大山悠輔5左 前川右京")
    got = [f for f in searchcells.parse_lineup([real], q)
           if f.extracted_by == "rule:JP_COMPACT"]
    assert got, "진짜 타순 5칸을 못 읽었다"
    assert len(got[0].value) >= searchcells.MIN_SLOTS


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

def test_19g_3_히로시마_양팀_한표_귀속불명(replay):
    """§19-g-3 — *"安芸の者 한 페이지에서 양 팀 9명 + 고조노 부재 도출."*

    🔴 **증명되는 것**
      · 코드의 1번 검색어가 그날 질의와 글자까지 같다(`広島 スタメン 9月27日 横浜`) —
        §13-b 가 요구한 `{球場}` 를 `games.venue` 로 채운 결과다.
      · 한 스니펫에서 **타순 9칸 이상**을 뽑는다.
      · 🔴 그 표가 **양 팀 것**이므로 **어느 팀에도 붙이지 않는다**(§17-g-3 · M14).

    ⚠️ 실측: 양 팀 타순을 들고 있던 것은 安芸の者 가 아니라 **DeNA 구단 페이지**이고,
       그 스니펫은 `中. 中村 奨成. 1. 左. 度会 隆輝 ; …` 처럼 **두 팀이 교대로** 들어
       있었다. 🔴 그것을 한 팀으로 읽으면 상대 9명이 우리 라인업에 섞인다 — M14 가
       돈으로 배운 자리다.
    """
    cell, _ = searchcells.lineup_cell(
        team="広島東洋カープ", league="NPB", day=DAY, game_id=None,
        starts=STARTS, local="広島", opponent="横浜DeNAベイスターズ",
        venue="横浜", now=STARTS - timedelta(minutes=30))
    assert cell.sources[0].query == "広島 スタメン 9月27日 横浜"

    hits = asyncio.run(replay.query(cell.sources[0].query, lang="ja"))
    facts = searchcells.parse_lineup(hits, cell.question)
    assert facts, "타순을 하나도 못 뽑았다"

    table = max(facts, key=lambda f: len(f.value))
    # ⚠️ 원문은 *"양 팀 9명"* 이라고 했지만 그날 스니펫은 **잘려 있다** — 히로시마
    #    4명·DeNA 4명까지만 보인다. 없는 칸을 있는 척하지 않는다(§11-3).
    #    🔴 검사하는 것은 **한 스니펫에서 여러 칸을 뽑고 귀속을 안 붙인다**는 것이다.
    assert len(table.value) >= 4, f"양 팀 표에서 {len(table.value)}칸만 뽑았다"
    # 🔴 **귀속 불명** — 양 팀이 한 표에 있으면 팀을 붙이지 않는다
    assert table.team is None, (
        f"양 팀 교대 표를 {table.team!r} 에 붙였다 — M14 재발 경로")
    names = {v["name"] for v in table.value}
    # 🔴 **상대 팀 선수가 같은 표에 있다** — 그래서 귀속을 못 붙인다
    assert any("度会" in n or "筒香" in n for n in names), names
    assert table.extracted_by in ("rule:JP_SLOT", "rule:JP_COMPACT")


def test_19g_3_고조노_부재는_아직_도출할_수_없다(replay):
    """§19-g-3 의 *"고조노 부재 도출"* — 🔴 **아직 못 한다. 왜 못 하는지 적는다.**

    ⚠️ 나는 처음에 *"고조노가 응답에 없다"* 고 계약을 썼고 **틀렸다** — 小園海斗 는
       그날 응답에 있다(구단 선수 목록 스니펫). 없는 것은 그 이름이 아니라 **부재
       진술**이다. 응답 어디에도 "小園이 빠졌다"고 적힌 문장은 없다.

    🔴 그것을 도출하려면 **타순 9명 ↔ 등록 명단**을 견줘야 한다("명단에 있는데
       타순에 없다"). 그 비교는 v4 STEP 2(결장)이고 §9 는 그것을 **단계 5** 에
       배정했다 — 단계 3 에서 쓰면 §13-2 위반이고 기계가 막는다.

    그래서 이 계약은 **지금 무엇이 있고 무엇이 없는지**를 못 박는다. 단계 5 가
    오면 이 계약을 지우고 결장 세포로 옮긴다.
    """
    hits = asyncio.run(replay.query("広島 スタメン 9月27日 横浜", lang="ja"))
    blob = " ".join(f"{h.title} {h.snippet}" for h in hits)
    # 🔴 이름은 **있다** — 내가 틀렸던 자리다
    assert "小園" in blob, "小園 이 응답에서 사라졌다 — 카세트가 바뀌었나"
    # 🔴 **부재 진술은 없다** — 그래서 지금 도출하면 그것은 추측이다
    for mark in ("小園は欠場", "小園を外", "小園 欠場", "小園が離脱"):
        assert mark not in blob, f"부재 진술이 나타났다({mark}) — 이제 도출할 수 있다"

    # 🔴 그리고 그 비교(타순 ↔ 명단)를 **단계 3 에서 하지 않는다**
    import inspect

    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(searchcells))
    assert "roster" not in src, (
        "라인업 세포가 명단을 읽는다 — 그 비교는 STEP 2(단계 5)다(§13-2)")


# ══════════════════════════════════════════════════════════════════
# ⑤ 휴스턴 선발 — ⚠️ 카세트 근사 (질의가 다르다)
# ══════════════════════════════════════════════════════════════════

def test_19g_5_휴스턴_선발_웨스네스키(replay):
    """§19-g-5 — *"unknown → 반증 세포 → RotoWire hit → 웨스네스키 3.50/1.15."*

    🔴 **증명되는 것**: 파서가 그날 응답에서 **H. Wesneski** 를 뽑는다.

    ⚠️ **증명되지 않는 것 셋** — 하나도 감추지 않는다:
      · **카세트가 근사다.** 그날 던진 질의는 `Astros probable pitcher September 27`
        이고 지금 코드는 `Houston Astros probable pitcher Sep 27` 을 던진다. 같은
        날의 응답을 다른 질의의 답으로 저장했다(`tools/build_cassettes_0927.py` 가
        `approx` 칸에 적는다). → **검색어는 증명되지 않는다.**
      · 원문의 `RotoWire` 는 그날 응답에 **없다** — 이름을 들고 있던 것은
        `fantasypros` 다.
      · `3.50/1.15`(ERA·WHIP)는 **스니펫에 없다.** §19-b-2 가 *"숫자는 본문을
        연다"* 고 한 이유가 이것이고, 본문 카세트는 없다.
    """
    srcs, _ = searchcells.search_sources(
        Q_STARTER_RECENT, team="Houston Astros", league="MLB", day=DAY,
        parse=searchcells.parse_starter_recent)
    assert srcs[0].query == "Houston Astros probable pitcher Sep 27"
    # 🔴 §13-b(라인업 표) 검색어가 선발 질문에 끼지 않는다
    assert not any("lineup" in (s_.query or "") for s_ in srcs), \
        [s_.query for s_ in srcs]

    q = Question(Q_STARTER_RECENT, "MLB:Houston Astros:2026-09-27",
                 team="Houston Astros", league="MLB")
    hits = asyncio.run(replay.query(srcs[0].query, lang="en"))
    facts = searchcells.parse_starter_recent(hits, q)
    assert facts, "그날 응답에서 선발 이름을 못 뽑았다"

    names = [n for f in facts for n in (f.value.get("names") or [])]
    assert any("Wesneski" in n for n in names), names
    # 🔴 수치는 스니펫에 없다 — 있는 척하지 않는다(못 잰 칸으로 남는다)
    nums = [n for f in facts for n in (f.value.get("numbers") or [])]
    assert "3.50" not in nums and "1.15" not in nums, (
        f"ERA·WHIP 가 스니펫에서 나왔다 — §19-b-2 본문 열기 없이 수치를 얻는다는 "
        f"뜻이므로 이 계약을 고쳐라: {nums}")


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


def test_19g_5_반증_세포가_unknown에서_태어난다():
    """§19-g-5 의 기계 부분 — 🔴 *"사실이 사실을 낳는다"*(§19-c).

    ⚠️ 원본 응답이 없는 부분(RotoWire 히트)은 검사하지 않는다. 검사하는 것은
       **unknown 이 반증 세포를 만들고, 그 세포가 그 unknown 을 의존으로 가진다**는
       구조다 — 그것이 §19-c 의 요지다.
    """
    dep = "starter_recent:MLB:Houston Astros:2026-09-27"
    cell = searchcells.counter_cell(
        subject="Houston Astros", condition="휴스턴 선발이 확정됐는가",
        league="MLB", day=DAY, game_id=None,
        variants=[queries.Variant("astros starting pitcher", "en", "L5",
                                  source="L5")],
        deps=[dep])
    assert cell.deps == [dep], "반증 세포가 자기를 낳은 unknown 을 모른다"
    assert "반증 조건" in cell.reason

    # 🔴 의존이 아직 없으면 **돌지 않는다**(§19-a `deps`)
    bb = Blackboard()
    state = asyncio.run(cell.run(Net(), bb, search=None,
                                 scores=SourceScores()))
    assert state == "pending", state
    assert "의존 미해결" in cell.reason

    # unknown 도 **닫힌 것**이다 — 멈추지 않는다(§1)
    bb.unknown(dep, "선발 미정")
    state = asyncio.run(cell.run(Net(), bb, search=None,
                                 scores=SourceScores()))
    assert state == "unknown", state
    assert "검색 수단" in cell.reason, cell.reason


def test_19g_5_세포는_판정하지_않는다():
    """🔴 §19-f — *"lean·확신·등급은 judge.py 다."* 원문의 "판정 상향"은 세포 밖이다."""
    import inspect

    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(searchcells))
    for bad in ("verdict", "survival", "confidence ="):
        assert bad not in src, f"세포가 판정에 손댄다: {bad}"


# ══════════════════════════════════════════════════════════════════
# ① K리그 일정 — 🔴 원본 응답 없음 · 기계 부분만
# ══════════════════════════════════════════════════════════════════

def test_19g_1_연도없는_일정페이지는_거부된다():
    """§19-g-1 — *"다음스포츠 K리그 일정(지난주) → 검증기 거부."*

    🔴 **증명되는 것**: 연도 없는 날짜 표기(`09.27 일`)만 있는 일정 페이지는
       `verify.slate_date_ok` 가 **fail-closed 로 거부**하고, 파서가 사실 0건을 낸다.
       그것이 M13(지난주 일정을 오늘 것으로 읽음)의 재발을 막는 자리다.

    ⚠️ 그날의 다음스포츠 응답은 저장돼 있지 않다. 그래서 **그 페이지의 모양**을
       가진 입력으로 검사한다 — 라이브 실측(2026-09-30)에서 실제로
       `kleague.com/schedule.do`·`flashscore` 가 같은 사유로 거부됐고 그 로그가
       `logs/stage3/live_2026-09-30.log` 에 있다.
    """
    from app.net import Fetched
    q = Question("slate", "K리그1:2026-09-27", league="K리그1",
                 deadline=datetime(2026, 9, 27, tzinfo=KST))

    # 연도 없는 표기만 있는 페이지 — 🔴 거부되어야 한다
    page = Fetched("https://sports.daum.net/schedule", True, 200,
                   "<td>09.27 일</td><td>강원 - 인천</td>"
                   "<td>09.20 일</td><td>포항 - 서울</td>")
    assert kleague.parse_schedule_page(page, q) == [], \
        "🔴 연도 없는 일정 페이지가 통과했다 — M13 재발 경로"
    # 사유가 무엇인지도 확인한다 — "날짜를 못 찾았다"와 다르다
    v = verify.slate_date_ok(kleague.page_dates(page.text), DAY)
    assert not v.ok and "연도 없는" in v.reason, v.reason

    # 연도가 있고 오늘이면 통과한다 — 검증기가 **아무것도 통과 안 시키면** 무용하다
    ok = Fetched("https://x", True, 200,
                 "<td>2026.09.27</td><td>강원 - 인천</td>")
    got = kleague.parse_schedule_page(ok, q)
    assert got and got[0].value == [{"a": "강원", "b": "인천"}], got


def test_19g_1_순연기사에서_경기를_도출한다():
    """§19-g-1 뒷부분 — *"연합 순연 기사에서 '강원-인천 1경기' 도출."*"""
    class _Hit:
        title = "프로축구 K리그1 강원-인천전 우천 순연"
        snippet = "27일 열릴 예정이었던 강원 - 인천 경기가 순연됐다"
        url = "https://www.yna.co.kr/view/x"
        publisher = "www.yna.co.kr"
        published_at = datetime(2026, 9, 27, 10, 0, tzinfo=KST)

    q = Question("slate", "K리그1:2026-09-27", league="K리그1")
    got = kleague.parse_postponed([_Hit()], q)
    assert got, "순연 기사에서 아무것도 못 뽑았다"
    assert {"a": "강원", "b": "인천"} in got[0].value, got[0].value
    # 🔴 스니펫 근거다 — soft(§19-b-3)
    assert got[0].hardness == "soft"


def test_19g_1_순연이_아닌_기사는_쓰지_않는다():
    """⚠️ 아무 기사에서나 팀 짝을 뽑으면 **지난주 경기**가 오늘 슬레이트가 된다."""
    class _Hit:
        title = "강원 - 인천 지난 맞대결 돌아보기"
        snippet = "작년 강원 - 인천 경기는"
        url = "https://x"
        publisher = "x"
        published_at = None

    q = Question("slate", "K리그1:2026-09-27", league="K리그1")
    assert kleague.parse_postponed([_Hit()], q) == []


# ══════════════════════════════════════════════════════════════════
# ④ 카라스코 — 🔴 원본 응답 없음 · 기계 부분만
# ══════════════════════════════════════════════════════════════════

def test_19g_4_변형을_다_쓰면_unknown이고_사유가_남는다(replay):
    """§19-g-4 — *"2회 변형 검색 후 unknown, **사유 기록**, 방아쇠 생성."*

    🔴 **증명되는 것**: 변형을 전부 쓰고도 못 찾으면 상태가 `unknown` 이고, 사유에
       **어느 변형까지 썼는지**가 남는다(§19-b-6). 그리고 예산을 넘겨 쓰지 않는다.

    ⚠️ 카라스코 그날 응답은 없다. 그래서 **카세트가 없는 상태**로 돌린다 — 그것이
       "못 찾았다"의 가장 정직한 대역이다(카세트 없음 → `SearchUnavailable`).
    """
    # 🔴 **v5 §4-1 문지기**(2026-10-04): 질의가 **세 요소 이상**이어야 던져진다.
    #    ⚠️ 실제 호출부(`analyze.gather`)는 `sport` 를 넘긴다 — 시험이 안 넘기면
    #       `starter_recent`(상대를 안 싣는 질문)의 요소가 둘이라 **막힌다.**
    #    🔴 실물과 같게 넘긴다.
    srcs, _ = searchcells.search_sources(
        Q_STARTER_RECENT, team="롯데", league="KBO", day=DAY,
        sport="baseball", parse=searchcells.parse_starter_recent)
    assert len(srcs) >= 2, "변형이 2개 미만이다 — §19-g-4 는 2회 변형을 말한다"
    cell = Cell(Question(Q_STARTER_RECENT, "KBO:롯데:2026-09-27",
                         team="롯데", league="KBO"),
                srcs, budget=Budget(searches=2, fetches=0))

    state, bb = _run(cell, replay)
    assert state == "unknown", state
    # 🔴 사유에 예산과 시도가 **이름으로** 남는다
    assert "검색 2/2" in cell.reason, cell.reason
    assert "카세트 없음" in cell.reason, cell.reason
    # 🔴 **어느 변형까지 썼는지**가 남는다(§19-b-6)
    assert cell.reason.count("검색:") >= 2, cell.reason
    # 🔴 예산을 넘겨 쓰지 않는다(§12-d)
    assert cell.budget.used_searches == 2
    # 🔴 블랙보드에도 사유가 남는다 — 조용한 0 금지
    assert bb.unknowns(), "블랙보드가 조용히 비었다"
    assert cell.question.id in dict(bb.unknowns())


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

def test_카오스_1차소스가_죽으면_대체로_간다(replay):
    """§19-g 원문: *"라이브 실측에서 소스가 죽어 있으면 **대체 소스로 같은 사실을
    내는지**가 검사 항목이다(카오스 테스트: 1차 소스를 강제로 dead 처리)."*

    🔴 여기서는 **URL 소스**로 카오스를 건다: 1차(공식 페이지)를 강제로 dead 로
       두면 2차 소스가 같은 사실을 내야 한다. 그리고 **사유가 남아야** 한다 —
       어느 소스가 죽어서 대체로 갔는지가 `source_state` 에 들어갈 값이다.
    """
    from app.net import Fetched

    def _parse(got, q):
        return [Fact(question_id=q.id, value={"lineup": ["A", "B"]},
                     hardness="hard")]

    cell = Cell(
        Question(Q_LINEUP, "NPB:팀:2026-09-27", team="팀", league="NPB"),
        [Source("1차 공식", "url", url="https://primary.example/x", tier=1,
                parse=_parse),
         Source("2차 대체", "url", url="https://backup.example/x", tier=2,
                parse=_parse)],
        budget=Budget(searches=0, fetches=2))

    net = Net()
    # 🔴 **강제로 dead 처리** — 사유 없이 죽이는 문은 없다
    net.mark_dead("primary.example", "카오스 테스트: 1차 소스 강제 dead")

    calls: list[str] = []

    async def _get(url, **k):
        calls.append(url)
        ok, why = await Net.allowed(net, url)
        if not ok:
            return Fetched(url, False, reason=why)
        return Fetched(url, True, 200, "<html></html>")

    net.get = _get                                    # type: ignore[assignment]
    state, bb = _run(cell, replay, net=net)

    assert state == "found", f"{state} — 대체 소스로 못 갔다: {cell.tried}"
    # 🔴 **어느 소스가 죽었는지 사유가 남는다**
    assert any("카오스" in t for t in cell.tried), cell.tried
    assert any("primary.example" in c for c in calls)
    assert any("backup.example" in c for c in calls), "2차를 아예 안 불렀다"


def test_카오스_전부_죽으면_지어내지_않는다(replay):
    """🔴 대체가 없으면 **unknown 이고 사유가 남는다.** 값을 만들지 않는다(§11-3)."""
    from app.net import Fetched

    cell = Cell(
        Question(Q_LINEUP, "NPB:팀:2026-09-27", team="팀", league="NPB"),
        [Source("1차", "url", url="https://a.example/x", tier=1,
                parse=lambda g, q: []),
         Source("2차", "url", url="https://b.example/x", tier=2,
                parse=lambda g, q: [])],
        budget=Budget(searches=0, fetches=2))
    net = Net()
    net.mark_dead("a.example", "카오스: 강제 dead")
    net.mark_dead("b.example", "카오스: 강제 dead")

    async def _get(url, **k):
        ok, why = await Net.allowed(net, url)
        return Fetched(url, ok, reason=why)

    net.get = _get                                    # type: ignore[assignment]
    state, bb = _run(cell, replay, net=net)
    assert state == "unknown", state
    assert "카오스" in cell.reason, cell.reason
    assert bb.get(cell.question.id).value is None, "값을 지어냈다"


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


def test_kleague는_games_표에_적지_않는다():
    """🔴 `app/collect/kleague.py` 머리글이 그렇게 적었고, **기전으로만** 참이었다.

    ⚠️ 리뷰 2026-09-30: pairs 에 `starts_utc` 키가 없어서 `ingest._slate` 가
       건너뛰는 것뿐이다. 다음 세션이 pairs 에 시각을 붙이면 **조용히 중복 행이
       쌓인다** — K리그 `ext_id` 규약이 없어서다(단계 4 가 정한다).
    🔴 그래서 여기서 잠근다: K리그 사실에는 `ext_id`·`starts_utc` 가 **없어야** 한다.
    """
    q = Question("slate", "K리그1:2026-09-27", league="K리그1",
                 deadline=datetime(2026, 9, 27, tzinfo=KST))

    class _Hit:
        title = "K리그1 강원-인천전 우천 순연"
        snippet = "27일 강원 - 인천 경기가 순연됐다"
        url = "https://www.yna.co.kr/view/x"
        publisher = "www.yna.co.kr"
        published_at = datetime(2026, 9, 27, 10, 0, tzinfo=KST)

    got = kleague.parse_postponed([_Hit()], q)
    assert got, "순연 기사에서 아무것도 못 뽑았다"
    for row in got[0].value:
        assert "starts_utc" not in row, (
            "K리그 사실에 시각이 붙었다 — `ingest._slate` 가 `games` 에 적기 "
            "시작하고, ext_id 규약이 없어 중복 행이 쌓인다(단계 4 가 정한다)")
        assert "ext_id" not in row, row

    # 🔴 그리고 어댑터가 `games` 를 **직접** 쓰지 않는다
    import inspect

    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(kleague))
    for bad in ("INSERT INTO games", "UPDATE games", "pool.execute"):
        assert bad not in src, f"kleague 가 DB 에 직접 쓴다: {bad}"


def test_13c_다른_경기_라인업을_오늘_것으로_읽지_않는다():
    """🔴 **§13-c ①** — *"기사에 오늘 날짜·구장이 있는가 … 어긋나면 unknown."*

    ⚠️ 실측 2026-09-30(단계 4 측정): §19-b-5 의 `시점:전날` 축이 09-28 팬블로그
       기사를 가져왔고 그것은 **09-28 경기의 라인업**이었다. 발행일(09-28)은
       §12-c-1 을 통과했다 — 최신 기사이기 때문이다. 🔴 그런데 **다른 경기**다.
       겐다가 그 라인업에도 없어서 "겐다 벤치" 채점이 **우연히 통과**했다.

    🔴 발행일 검증으로는 이것을 못 가른다 — 전날 기사가 오늘 경기를 예고할 수도
       있고, 그것이 `시점:전날` 축의 목적이다. 그래서 §13-c 가 **기사 본문에 그
       경기 날짜가 있는지**를 따로 요구한다. M13 과 같은 결의 오류다.
    """
    q = Question(Q_LINEUP, "NPB:西武:2026-09-29", team="埼玉西武ライオンズ",
                 local="西武", league="NPB",
                 deadline=datetime(2026, 9, 29, 21, 0, tzinfo=KST))

    class _H:
        def __init__(self, body):
            self.title, self.snippet = "", body
            self.url = "https://yamisokulions.com/x"
            self.publisher = "yamisokulions.com"
            self.published_at = datetime(2026, 9, 28, 17, 23, tzinfo=KST)

    lineup = "1右 カナリオ2左 平沢3捕 小島4一 ネビン5三 渡部6二 石井7中 長谷川"

    # 🔴 **전날 경기 라인업** — 기사에 09-29 가 없다 → 버린다
    wrong = _H(f"西武 9月28日 オリックス戦 スタメン {lineup}")
    assert searchcells.parse_lineup([wrong], q) == [], (
        "다른 경기(09-28) 라인업을 09-29 것으로 읽었다 — §13-c 위반")

    # 🔴 **오늘 경기를 예고하는 전날 기사** — 기사에 09-29 가 있다 → 쓴다
    right = _H(f"西武 9月29日 オリックス戦 予告スタメン {lineup}")
    got = searchcells.parse_lineup([right], q)
    assert got, "오늘 경기를 말하는 전날 기사를 버렸다 — 그것이 시점:전날 축이다"
    assert len(got[0].value) >= 5


def test_13c_마감을_모르면_날짜_검사의_대상이_아니다():
    """⚠️ 마감(경기 시각)이 없는 질문에 이 검사를 걸면 **전부 버린다.**

    🔴 검증기가 아무것도 통과시키지 않으면 그것은 검증기가 아니다.
    """
    q = Question(Q_LINEUP, "x", team="埼玉西武ライオンズ", local="西武")
    assert q.deadline is None

    class _H:
        title = ""
        snippet = "西武 スタメン 1右 カナリオ2左 平沢3捕 小島4一 ネビン5三 渡部"
        url = "https://x"
        publisher = "x"
        published_at = None

    assert searchcells.parse_lineup([_H()], q), "마감 없는 질문을 통째로 버렸다"


def test_세포가_금지_라인업_소스를_열지_않는다(replay):
    """🔴 §13-a — **표에 안 넣는 것만으로는 안 막힌다.** 그 셋은 검색 1순위로 나온다.

    ⚠️ 실측 2026-09-30(단계 4): 세이부 라인업 세포가
       `baseball-data.com/lineup/l.html` 을 **실제로 열었다.** 그 표는 §13-a 가
       못 박은 대로 **하루 지연**이라 겐다가 선발로 들어 있었고 — §19-g-5 의
       사실(겐다 **벤치**)과 반대다. M13 과 같은 결의 함정이다.

    🔴 예산을 쓰기 **전에** 가른다 — 열고 나서 버리면 열기 예산이 그만큼 준다.
    """
    from app.net import Fetched

    opened: list[str] = []

    class _H:
        def __init__(self, url):
            self.url = url
            self.title = "西武 スタメン 9月29日"
            self.snippet = "9月29日 スタメン"
            self.publisher = ""
            self.published_at = None

    cell, _ = searchcells.lineup_cell(
        team="埼玉西武ライオンズ", league="NPB", day=date(2026, 9, 29),
        game_id=None, starts=datetime(2026, 9, 29, 21, 0, tzinfo=KST),
        local="西武", opponent="オリックス・バファローズ",
        opponent_local="オリックス",
        now=datetime(2026, 9, 29, 20, 30, tzinfo=KST))
    src = cell.sources[0]
    assert callable(src.deny), "라인업 소스에 금지 판정이 안 붙었다"

    net = Net()

    async def _get(url, **k):
        opened.append(url)
        return Fetched(url, True, 200, "<html></html>")

    net.get = _get                                    # type: ignore[assignment]
    hits = [_H("https://baseball-data.com/lineup/l.html"),
            _H("https://news.yahoo.co.jp/articles/x"),
            _H("https://baseball.yahoo.co.jp/npb/game/y"),
            _H("https://lions-matome.com/archives/z.html")]

    asyncio.run(cell._open_hits(src, hits, net))

    for bad in ("baseball-data.com", "news.yahoo.co.jp", "baseball.yahoo.co.jp"):
        assert not any(bad in u for u in opened), f"§13-a 금지 소스를 열었다: {bad}"
    assert any("lions-matome" in u for u in opened), "허용 소스를 안 열었다"
    # 🔴 **건너뛴 사유가 남는다**(조용한 0 금지)
    joined = " / ".join(cell.tried)
    assert "§13-a" in joined, joined
    # 🔴 예산을 **쓰기 전에** 가렸다 — 금지 3건에 열기 예산이 안 들었다
    assert cell.budget.used_fetches == 1, cell.budget.spent


def test_13c_일만_맞는_기사를_통과시키지_않는다():
    """🔴 **세 번째 거짓 통과가 나온 자리다**(실사고 2026-09-30, 단계 4).

    §19-b-5 의 `표기:일자` 변형은 `西武 スタメン 29日` 을 던진다 — 그것이 검색어로는
    맞다(넓게 던진다). 🔴 그런데 **받은 것을 `29日` 만으로 믿으면** 어느 달·어느
    해 기사든 통과한다.

    실제로 `nikkansports.com/…/202403280001840.html`
    (`【一覧】西武の予想開幕スタメン…`, **2024년 3월** 개막 예상)이 통과했고,
    겐다가 그 2024년 명단에 없으니 "겐다 벤치"가 **통과로 찍혔다.**

    ⚠️ §12-c-7 이 *"연도 없는 표기는 못 읽는 것으로 본다 — fail-closed"* 라고 막은
       병과 같다. **월+일이 최소 조건이다.**
    """
    q = Question(Q_LINEUP, "NPB:西武:2026-09-29", team="埼玉西武ライオンズ",
                 local="西武", league="NPB",
                 deadline=datetime(2026, 9, 29, 21, 0, tzinfo=KST))
    lineup = "1中 金子侑2右 若林3二 外崎4一 アギラー5指 中村剛6左 コルデロ"

    class _H:
        def __init__(self, title, body):
            self.title, self.snippet = title, body
            self.url, self.publisher = "https://x", "x"
            self.published_at = None

    # 🔴 **일만 맞는 다른 달 기사** — 버려야 한다
    wrong = _H("【一覧】西武の予想開幕スタメンと先発ローテーション",
               f"2024年3月29日 開幕 {lineup}")
    assert searchcells.parse_lineup([wrong], q) == [], (
        "일(日)만 맞는 다른 달 기사가 통과했다 — §12-c-7 과 같은 병이다")

    # 🔴 월+일이 맞으면 통과한다 — 전부 막으면 검증기가 아니다
    right = _H("西武スタメン", f"9月29日 オリックス戦 {lineup}")
    assert searchcells.parse_lineup([right], q), "맞는 기사를 버렸다"
