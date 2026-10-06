"""검색으로 답하는 세포들 — §19-b 탐색 루프의 실제 질문들.

`app/collect/*.py` 는 **URL 로 닫히는** 질문(공식 API·공식 페이지)을 맡는다.
여기는 **검색으로만 닫히는** 질문이다: 확정 라인업 · 감독 의도 · 선발 최근 창 ·
반증(counter). §19-i 가 그 수단을 정했다(SearXNG 1순위).

🔴 **세포는 판정하지 않는다**(§19-f). 사실·hardness·unknown 사유만 낸다.
🔴 **스니펫만 근거면 soft 다**(§19-b-3). 숫자·인용은 본문을 연다(§19-b-2) —
   그래서 `Source.open_body` 가 있다.
🔴 **두 팀이 언급된 자료는 귀속이 불명이면 어느 팀에도 안 붙인다**(§17-g-3 · M14:
   마요르카 감독 기록을 알메리아 것과 바꿔 적었다).
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone

from app import ids, queries, rules, verify
from app.blackboard import Fact
from app.collect import fotmob
from app.cells import (SLATE, Budget, Cell, Q_ABSENCE, Q_COUNTER, Q_INTENT,
                       Q_LINEUP, Q_STANDINGS, Q_STARTER_RECENT, Question,
                       Source, budget_for)

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

#: 질문 타입 → 검색 핵심어. 🔴 리그의 **현지어**다(§12-b) — 번역 기사를 피한다.
#  ⚠️ 여기는 "무엇을 묻나"이고, **어느 매체에 묻나**는 §13-b(yaml)가 정한다.
WHAT: dict[tuple[str, str], str] = {
    (Q_LINEUP, "ja"): "スタメン",
    (Q_LINEUP, "en"): "lineup",
    (Q_LINEUP, "ko"): "선발 라인업",
    (Q_LINEUP, "zh"): "先發打序",
    (Q_STARTER_RECENT, "ja"): "先発 登板",
    (Q_STARTER_RECENT, "en"): "probable pitcher",
    (Q_STARTER_RECENT, "ko"): "선발 등판",
    (Q_INTENT, "ja"): "監督 コメント",
    (Q_INTENT, "en"): "manager said",
    (Q_INTENT, "ko"): "감독 인터뷰",
    # 🔴🔴 **순위표** — 세포가 없어 `stakes`·`home_field` 가 통째로 비어 있었다
    #    (실측 2026-10-03: KBO 는 어댑터 깊이가 0 이라 순위를 **어디서도** 못 받는다).
    #    ⚠️ 핵심어는 *"순위"* 가 아니라 **그 경기가 걸린 것**을 겨냥한다 —
    #       매직넘버·잔여경기가 §4 `stakes` 가 요구하는 사실이다.
    #    🔴 **짧게 쓴다** — §12-b 가 질의를 **6낱말**로 제한한다(`llm.query_ok`).
    #       실측 2026-10-03: `순위 매직넘버 잔여경기` 로 썼더니 팀명·날짜가 붙어
    #       7낱말이 되어 변형 여섯 중 **셋이 통째로 버려졌다**. 상한은 규칙이고
    #       (지난 시즌 기사가 섞이는 것을 막는다), 핵심어가 그 상한에 맞춰야 한다.
    (Q_STANDINGS, "ko"): "순위 매직넘버",
    (Q_STANDINGS, "en"): "standings magic number",
    (Q_STANDINGS, "ja"): "順位表 マジック",
    (Q_STANDINGS, "es"): "clasificación",
    (Q_STANDINGS, "zh"): "積分榜",
}


def what_of(qtype: str, lang: str) -> str:
    """🔴 없으면 **빈 문자열** — 핵심어를 지어내지 않는다(§11-3)."""
    return WHAT.get((qtype, lang), "")


# ══════════════════════════════════════════════════════════════════
# §19-b — 변형들을 소스 목록으로
# ══════════════════════════════════════════════════════════════════


def search_sources(qtype: str, *, team: str, league: str, day: date,
                   local: str = "", venue: str = "", parse=None,
                   parse_body=None, open_body: bool = False, prefer=None,
                   deny=None, dateless_ok: bool = False,
                   # 🔴 §19-c — 연 자료가 다른 자료를 가리킬 때 따라가는 길
                   follow=None, parse_follow=None,
                   # 🔴 §17-b L1~L3 — 규칙 파서가 0건을 낼 때의 **대체**(§19-b-5)
                   extract_tasks: tuple[str, ...] = (),
                   tier: int = verify.TIER_PRIMARY,
                   # 🔴 **엔진 지정** — 비면 `config/search_routing.yaml` 의 뉴스
                   #    엔진을 쓴다. 산문(기사)을 겨냥한 질문이 전부 그렇다.
                   engines: tuple[str, ...] | None = None,
                   # ══════════════════════════════════════════════════════════
                   # 🔴🔴 **신원을 질의에 싣는다** — 사용자 수정 ① (2026-10-04)
                   # ══════════════════════════════════════════════════════════
                   #
                   #  ⚠️ `Question` 은 `opponent` 를 **이미 들고 있었다**(§17-g-3
                   #     귀속 판단용). 그런데 **질의에는 안 실렸다** — 그래서
                   #     `Scotland lineup Oct 3` 가 나가고 드라마 출연진이 왔다.
                   #  🔴 같은 사실을 두 군데 쓰는 것이지 새로 만드는 것이 아니다.
                   opponent: str = "", opponent_local: str = "",
                   sport: str = "", langs: tuple[str, ...] = ()
                   ) -> tuple[list[Source], list[str]]:
    """§19-b-5 변형 → `Source` 목록. 반환은 `(소스들, 버린 사유)`.

    🔴 **순서가 곧 시도 순서**이고 §13-b 표의 검색어가 1번이다. 버린 변형은
       이름으로 올려 보낸다 — unknown 사유에 *"어떤 변형까지 썼는지"* 가 들어가야
       한다(§19-b-6).
    """
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **언어는 한 곳에서 정한다**(실측 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 여기서는 `LANGS.get(league)` 를 쓰고, 바로 아래 `queries.variants` 는
    #     `langs_for(league, team)` 를 쓰고 있었다 — **같은 경로에서 언어를 두 번
    #     따로 계산**한 것이다. 그래서 이런 질의가 나갔다:
    #
    #       [ja] Kashiwa Reysol **lineup** 10月3日
    #            ^^^^^^^^^^^^^^^^^^^^^^^^ 날짜는 일본어인데 핵심어는 영어
    #
    #     까닭: `LANGS` 에 `League Cup` 이 없어 여기 `langs` 가 `('en',)` 이었고,
    #     그래서 핵심어 표가 `{'en': 'lineup'}` 하나만 만들어졌다. `variants` 는
    #     `langs_for` 로 `('en','ja')` 를 얻었지만 **일본어 핵심어가 없었다.**
    #  🔴 `langs_for` 하나로 모은다 — 그것이 팀 선언·리그 명부·팀 되묻기를 전부 본다.
    # 🔴 호출부가 언어를 **이미 알면** 그것이 이긴다 — 대표팀은 리그가 없어
    #    `langs_for` 가 `('en',)` 로 떨어지지만 사다리 ②가 Babel 로 `mk` 를 안다.
    if langs:
        _why_lang = "호출부가 준 언어(사다리 ②)"
    else:
        langs, _why_lang = queries.langs_for(league, team)
    # 🔴🔴 **언어마다 핵심어를 따로** 넘긴다(실측 2026-10-03).
    #    ⚠️ 종전엔 하나를 골라 모든 변형에 붙여 `LG Twins 선발 라인업 Oct 3` 같은
    #       **반쯤 한국어인 영어 질의**가 나갔다. 영어 매체는 그 글자를 안 쓴다.
    what = {lg: what_of(qtype, lg) for lg in langs if what_of(qtype, lg)}
    if not what and what_of(qtype, "en"):
        what = {"en": what_of(qtype, "en")}
    if not what:
        return [], [f"{qtype} 의 검색 핵심어가 표에 없다 — 지어내지 않는다"]
    # 🔴 **§13-b 는 라인업 표다.** 선발 최근 창·감독 의도 질문에 그 검색어
    #    (`{team} lineup {date}`)를 1번으로 던지면 엉뚱한 것을 묻는다 —
    #    실측 2026-09-30: 종전에는 모든 질문 타입에 표를 붙였다.
    raw = queries.variants(team=team, league=league, day=day, what=what,
                           local=local, venue=venue,
                           use_table=(qtype == Q_LINEUP),
                           opponent=opponent, opponent_local=opponent_local,
                           sport=sport, langs=tuple(langs))
    kept, dropped = queries.admissible(raw)
    # 🔴 **기사를 겨냥한 질문은 뉴스 엔진으로 먼저 쏜다**(실측 2026-10-02).
    #    ⚠️ 0건이면 사슬이 지정 없이 한 번 더 던진다 — 좁혀도 경로가 죽지 않는다.
    eng = tuple(rules.news_engines()) if engines is None else tuple(engines)
    out = []
    for v in kept:
        out.append(Source(
            name=f"검색:{v.axis}", kind="search", query=v.text, lang=v.lang,
            # 🔴 §4-1 — 문지기가 짐작하지 않게 **조각을 싣는다**
            parts=getattr(v, "parts", None),
            tier=tier, parse=parse, verify=True,
            open_body=open_body, parse_body=parse_body,
            extract_tasks=tuple(extract_tasks), engines=eng,
            prefer=prefer, deny=deny, dateless_ok=dateless_ok,
            follow=follow, parse_follow=parse_follow))
    return out, dropped


# ══════════════════════════════════════════════════════════════════
# 라인업 (§13-b·§13-c)
# ══════════════════════════════════════════════════════════════════

#: 스니펫의 타순 표기. 실측 2026-09-27(baystars `game/result` 스니펫):
#:   `中. 中村 奨成. 1. 左. 度会 隆輝 ; 遊. 勝田 成. 2. 二. 牧 秀悟`
#: → `포지션 . 이름 . 번호` 가 **양 팀 교대로** 붙는다.
_JP_POS = "投捕一二三遊左中右指"
_JP_SLOT = re.compile(
    rf"([{_JP_POS}])\s*[.．]\s*([^\s.．;；]{{2,}}(?:\s+[^\s.．;；]{{1,}})?)\s*[.．]\s*(\d{{1,2}})")
#: `中村奨1番` · `勝田2番` — 기사 본문의 서술형 타순(실측: yahoo 기사 제목).
#: 🔴 **가장 약한 신호다.** 앞의 두 패턴이 다 실패했을 때만 쓰고, `extracted_by`
#:    에 이름을 남겨 단계 4 가 정확도를 따로 잴 수 있게 한다.
#: ⚠️ 이름 칸에 **히라가나를 허용하지 않는다.** 실측(09-27 카세트): `合の中村晃は`·
#:    `場合の…は` 처럼 조사(の·は)가 붙은 조각이 선수 이름으로 잡혔다. 일본 기사의
#:    선수명은 한자·가타카나이고 히라가나는 **문법**이다 — 그것으로 가른다.
_JP_ORDER_WORD = re.compile(
    r"([一-鿿ァ-ヿ][一-鿿ァ-ヿー]{1,5})\s*(\d{1,2})\s*番")
#: `「6番・一塁」で先発出場` 꼴 — 한 선수의 타순·포지션(실측: SANSPO 스니펫).
_JP_ONE_SLOT = re.compile(r"「\s*(\d{1,2})\s*番[・･]?\s*([^」]*)」")

#: 🔴 **압축 타순** — 실측 2026-09-27 카세트에 그날 라인업 **전체**가 이 꼴로 있었다:
#:    `1右 正木智也2中 柳町達3指 近藤健介4三 栗原陵矢5左 柳田悠岐6一 中村晃7遊 今宮健太8捕`
#:    (번호 + 포지션 한 자 + 이름, 구분자 없이 이어 붙는다)
#: ⚠️ 처음에는 이 꼴을 못 읽어서 §19-g-2 의 *"이마미야"* 를 *"응답에 없다"* 고
#:    단정했다 — **있었다.** 스니펫을 눈으로 보고서야 알았다(§11-4 추측 금지).
_JP_COMPACT = re.compile(
    r"(\d{1,2})\s*([一二三遊左中右指捕投])\s*([一-鿿ァ-ヿ][一-鿿ァ-ヿー]{1,5})")
#: `1(左) 柳町達 2(中) 周東佑京` — 괄호 꼴(같은 응답의 다른 스니펫).
_JP_PAREN = re.compile(
    r"(\d{1,2})\s*[（(]\s*([一二三遊左中右指捕投])\s*[）)]\s*"
    r"([一-鿿ァ-ヿ][一-鿿ァ-ヿー]{1,5})")

#: 🔴 **압축·괄호 꼴은 몇 칸 이상 연달아 나올 때만 타순으로 본다.**
#:    한두 칸은 스코어·순위 표기와 구별되지 않는다(`3 - 5 試合終了`). 타순은 9칸이
#:    므로 절반 이상 보이면 그것은 라인업이다 — 이 문턱이 정밀도를 지킨다.
MIN_SLOTS = 5


def deny_lineup_source(url: str) -> str | None:
    """§13-a 가 라인업 소스로 금지한 곳이면 **사유**를, 아니면 `None`.

    🔴 *"스포츠나비 경기 페이지(JS)·baseball-data 스타멘 표(하루 지연)·야후 뉴스
       본문(robots 거부)은 라인업 소스로 쓰지 않는다."*

    ⚠️ 실측 2026-09-30(단계 4): 세이부 라인업 세포가 `baseball-data.com/lineup/l.html`
       을 열었고 그 표는 **하루 지연**이라 겐다가 선발로 들어 있었다 —
       §19-g-5 가 말한 사실(겐다 **벤치**)의 **반대**다. 표에 안 넣는 것만으로는
       안 막힌다(그 셋은 검색 1순위로 나온다).
    🔴 이름 목록은 `config/lineup_sources.yaml` 이고 계약이 §13-a 문장과 대조한다.
    """
    low = (url or "").lower()
    for row in queries.banned_for_lineup():
        for host in row.get("hosts") or []:
            if host.lower() in low:
                return f"§13-a 금지 라인업 소스({row.get('origin')} · {host})"
    return None


def _mentions_game_day(text: str, q: Question) -> bool:
    """§13-c ① — 기사에 **그 경기 날짜**가 있나.

    🔴 **이것이 없으면 전날 경기 라인업을 오늘 것으로 읽는다.**
       실측 2026-09-30(단계 4 측정): §19-b-5 의 `시점:전날` 축이 09-28 팬블로그
       기사를 가져왔고, 그것은 **09-28 경기의 라인업**이었다. 겐다가 그 라인업에도
       없어서 "겐다 벤치" 채점이 **우연히 통과**했다 — 거짓 통과다.
       M13(지난주 일정을 오늘 것으로 읽음)과 같은 결의 오류이고, §13-c 가 그것을
       막으려고 이미 적혀 있었다.

    ⚠️ **발행 시각 검증(§12-c-1)과 다른 검사다.** 그쪽은 *"기사가 최신인가"* 이고
       이쪽은 *"기사가 **그 경기**를 말하는가"* 다. 전날 기사가 오늘 경기를 예고할
       수도 있으므로(그것이 `시점:전날` 축의 목적이다) 발행일로는 가를 수 없다.

    🔴 날짜를 못 찾으면 **거부**다(fail-closed). 지어내지 않는다.
    """
    if q.deadline is None:
        return True          # 마감을 모르면 이 검사의 대상이 아니다
    d = q.deadline.astimezone(KST).date()
    # 🔴 표기는 매체마다 다르다 — `9月29日`·`9/29`·`09.29`·`9월 29일`·`Sep 29`
    #
    # 🔴 **일(日)만 있는 표기는 쓰지 않는다.** `29日` 로 통과시키면 **어느 달·어느
    #    해 기사든** 통과한다. 실사고 2026-09-30(단계 4, 세 번째 거짓 통과):
    #    `표기:일자` 변형(`西武 スタメン 29日`)이 **2024년 3월 개막 예상 스타멘**
    #    기사를 물어왔고, 그 기사에 `29日` 이 있어서 §13-c 를 통과했다. 겐다가 그
    #    2024년 명단에 없으니 "겐다 벤치"가 **통과로 찍혔다.**
    #    ⚠️ §12-c-7 이 *"연도 없는 표기(`09.27 일`)는 못 읽는 것으로 본다 —
    #       fail-closed"* 라고 못 박은 병과 같은 것이다. **월+일은 최소 조건**이다.
    #    ⚠️ 검색어로 `29日` 을 던지는 것은 §19-b-5 가 요구하는 축이라 그대로 둔다 —
    #       **넓게 던지는 것과 받은 것을 믿는 것은 다르다.**
    forms = (f"{d.month}月{d.day}日", f"{d.month}/{d.day}",
             f"{d.month:02d}/{d.day:02d}", f"{d.month:02d}.{d.day:02d}",
             f"{d.month}.{d.day}", f"{d.month}월 {d.day}일",
             f"{d.month}월{d.day}일", f"{d.month}月{d.day}",
             f"{d:%Y-%m-%d}", f"{d:%Y.%m.%d}", f"{d:%Y/%m/%d}",
             f"{d:%b} {d.day}", f"{d:%b}. {d.day}", f"{d:%b} {d.day:02d}")
    return any(f in text for f in forms)


def parse_lineup(hits, q: Question) -> list[Fact]:
    """검색 결과 → 타순 사실. 🔴 **귀속이 불명이면 팀에 붙이지 않는다**(§17-g-3).

    ⚠️ 실측 2026-09-27: DeNA 구단 페이지 스니펫 하나에 **양 팀 타순이 교대로**
       들어 있었다(`中. 中村 奨成. 1. 左. 度会 隆輝 ; …`). 그것을 한 팀으로 읽으면
       상대 팀 9명이 우리 라인업에 섞인다 — M14 가 돈으로 배운 자리다.
       그래서 **두 팀이 언급된 자료는 `team=None`** 으로 남기고 사유를 적는다.

    🔴 스니펫 근거는 `soft` 다(§19-b-3). hard 로 올리려면 본문을 열어야 한다.
    """
    out: list[Fact] = []
    for h in _articles(hits):
        text = f"{h.get('title') or ''} {h.get('body') or ''}"
        # 🔴 §13-c ① — **그 경기 날짜를 말하지 않는 기사는 버린다.**
        #    발행일이 최신이어도 **다른 경기**의 라인업일 수 있다(실측: 전날
        #    경기 라인업이 오늘 것으로 들어왔다).
        if not _mentions_game_day(text, q):
            logger.info("[lineup] §13-c 거부 — 경기 날짜가 기사에 없다: %s",
                        h.get("url"))
            continue

        # 🔴 귀속을 **먼저** 정한다. `None` 은 "어느 팀에도 안 붙인다"이고
        #    **버리는 것이 아니다**(§17-g-3). 사실은 남고 팀 칸만 빈다.
        team = _attribute(text, q)

        # 🔴 **가장 센 신호 먼저** — 타순 전체가 한 줄에 있는 꼴.
        full = _full_order(text)
        if full:
            out.append(Fact(
                question_id=q.id, value=full, hardness="soft",
                source=h.get("url") or "",
                article_title=h.get("title") or "",
                article_body=h.get("body") or "", publisher=h.get("publisher") or "",
                published_at=h.get("published_at"),
                extracted_by="rule:JP_COMPACT", step=3, team=team))
            continue

        slots = _JP_SLOT.findall(text)
        if slots:
            rows = [{"order": int(n), "pos": p, "name": _tidy(nm)}
                    for p, nm, n in slots]
            out.append(Fact(
                question_id=q.id, value=rows, hardness="soft",
                source=h.get("url") or "",
                article_title=h.get("title") or "",
                article_body=h.get("body") or "", publisher=h.get("publisher") or "",
                published_at=h.get("published_at"), quote=None,
                extracted_by="rule:JP_SLOT", step=3,
                # 🔴 귀속 불명 — 두 팀이 한 표에 있으면 팀을 붙이지 않는다
                team=team))
            if team is None:
                logger.info("[lineup] 귀속 불명(양 팀 언급) — team 을 비웠다: %s",
                            h.get("url"))
            continue
        one = _JP_ONE_SLOT.search(text)
        # 🔴 **문장이 주인을 적었으면 그것을 따른다.** `阪神・ルーカスが「4番…」`
        #    은 한신 선수이고, 그 기사가 우리 팀을 상대로 언급했다는 이유로 우리
        #    라인업이 되어선 안 된다(실측 2026-09-27 · M14).
        subject_team, _ = _subject(text)
        one_team = team
        if one and subject_team:
            one_team = (team if _names_hit(subject_team, q.team or "", q.local)
                        else None)
        # 🔴 **이름이 없으면 사실이 아니다.** 실측 2026-09-27 카세트: `「7番・
        #    キャッチャー」` 만 있고 선수 이름이 문장에 없는 스니펫이 둘 있었고,
        #    파서가 `name=''` 인 사실을 냈다. 빈 이름은 블랙보드에서 **모순의
        #    재료**가 되고(같은 질문에 다른 빈 값), 카드에도 빈 칸으로 나간다.
        #    ⚠️ 지어내지 않는다 — 없으면 그 스니펫을 버린다(§11-3).
        if one and _subject_name(text):
            out.append(Fact(
                question_id=q.id,
                # ⚠️ `pos` 에 문장이 통째로 들어온 실측이 있다(`... 7 時間前 ...
                #    ソフトバンク・中村晃内野手が「6番・一塁`). 포지션은 짧은
                #    낱말이므로 길면 **모른다**로 둔다 — 긴 문장을 포지션으로
                #    저장하면 카드가 문장을 포지션 칸에 찍는다.
                value=[{"order": int(one.group(1)),
                        "pos": _pos_or_none(one.group(2)),
                        "name": _subject_name(text)}],
                hardness="soft", source=h.get("url") or "",
                article_title=h.get("title") or "",
                article_body=h.get("body") or "",
                publisher=h.get("publisher") or "",
                published_at=h.get("published_at"),
                extracted_by="rule:JP_ONE_SLOT", step=3, team=one_team))
            continue
        words = _JP_ORDER_WORD.findall(text)
        if words and team is not None:
            out.append(Fact(
                question_id=q.id,
                value=[{"order": int(n), "name": _tidy(nm), "pos": None}
                       for nm, n in words],
                hardness="soft", source=h.get("url") or "",
                article_title=h.get("title") or "",
                article_body=h.get("body") or "",
                publisher=h.get("publisher") or "",
                published_at=h.get("published_at"),
                extracted_by="rule:JP_ORDER_WORD", step=3, team=team))
    return out


def _full_order(text: str) -> list[dict]:
    """압축·괄호 꼴 타순. 🔴 `MIN_SLOTS` 칸 이상일 때만 돌려준다.

    ⚠️ **타순은 1..9 로 유일해야 한다.** 같은 번호가 두 번 나오면 두 팀이 섞인
       것이거나 스코어를 잘못 읽은 것이다 — 그때는 **앞에서부터 처음 본 번호만**
       남긴다(뒤엣것을 덮어쓰면 상대 팀 선수가 우리 타순에 앉는다).
    """
    for pat, how in ((_JP_PAREN, "paren"), (_JP_COMPACT, "compact")):
        rows: list[dict] = []
        seen: set[int] = set()
        for order, pos, name in pat.findall(text):
            n = int(order)
            if not 1 <= n <= 9 or n in seen:
                continue
            seen.add(n)
            rows.append({"order": n, "pos": pos, "name": _tidy(name)})
        if len(rows) >= MIN_SLOTS:
            rows.sort(key=lambda r: r["order"])
            logger.info("[lineup] %s 꼴에서 타순 %d칸", how, len(rows))
            return rows
    return []


#: `阪神・ルーカスが「4番・三塁」` — 🔴 **이 꼴은 팀을 스스로 적는다.**
#
#  실측 2026-09-27 카세트: 소프트뱅크 질의 결과에 **阪神 vs ソフトバンク 팜리그**
#  기사가 있었고, 거기서 `ルーカス`(한신 투수)가 `「4番・三塁」` 로 잡혔다. 그 기사는
#  `ソフトバンク` 를 언급하므로(상대로) 팀 이름만 보는 귀속 규칙은 그것을 **우리
#  라인업으로** 붙였다 — M14 와 같은 오류다.
#  🔴 그런데 그 문장은 `阪神・` 라고 **주인을 스스로 적는다.** 추측할 필요가 없다.
_JP_SUBJECT = re.compile(r"([^\s（(【、。]{2,10})[・･]([^\s・･（(]{2,8})が")


def _subject(text: str) -> tuple[str, str]:
    """`ソフトバンク・中村晃が「6番・一塁」` → `("ソフトバンク", "中村晃")`.

    🔴 못 읽으면 **빈 문자열 둘**이다 — 지어내지 않는다(§11-3).
    """
    m = _JP_SUBJECT.search(text)
    return (m.group(1), m.group(2)) if m else ("", "")


def _subject_name(text: str) -> str:
    """주어 선수 이름만. 🔴 못 읽으면 빈 문자열."""
    return _subject(text)[1]


def _pos_or_none(raw: str) -> str | None:
    """포지션 낱말. 🔴 **길면 모른다**(문장이 섞여 들어온 것이다)."""
    p = " ".join(str(raw or "").split())
    return p if p and len(p) <= 6 else None


#: 🔴 **사람 이름처럼 생긴 토큰.** 코드 기호(`(){}=;/"` 등)가 하나라도 있으면
#:    이름이 아니다. 라틴·한글·가나·한자와 공백·`.`·`-`·`\'` 만 받는다.
#:    ⚠️ 이 제약이 자바스크립트를 걸러 내는 자리다(실측 2026-09-30).
_NAME_CHARS = (r"[A-Za-zÀ-ÿ가-힣ぁ-ゟ゠-ヿ一-鿿]"
               r"[A-Za-zÀ-ÿ가-힣ぁ-ゟ゠-ヿ一-鿿 .\-']{1,28}")

_NAME_ONLY = re.compile(r"^" + _NAME_CHARS + r"$")
#: 🔴 한자·가나·한글 이름 — 2~6자. 라틴과 판정 규칙이 다르다.
_CJK_NAME = re.compile(r"^[가-힣ぁ-ゟ゠-ヿ一-鿿][가-힣ぁ-ゟ゠-ヿ一-鿿 ]{1,5}$")


def _looks_like_name(raw: str) -> bool:
    """사람 이름처럼 생겼나. 🔴 **코드는 이름이 아니다.**

    ⚠️ 실측 2026-09-30: 정규식만 조여도 부족했다 — 정규식이 놓친 조각이 남는다.
       뽑은 **각 토큰**을 한 번 더 본다(두 겹).
    """
    t = " ".join(str(raw or "").split())
    return bool(t) and _NAME_ONLY.match(t) is not None


def _looks_like_person(raw: str) -> bool:
    """**사람 이름**인가 — 낱말 모양만으로는 부족하다.

    🔴 실측 2026-09-30(단계 4): `_looks_like_name` 만으로는 fotmob 의 **통계 항목
       이름**이 선수 명단으로 들어왔다 — `Possession, shots, corners, big chances
       created, …`. 글자와 공백뿐이라 모양 검사를 통과한다.

    사람 이름의 구조적 성질로 가른다:
      · **한자·가나·한글** 2~6자 → 이름이다 (`源田壮亮`·`김건희`)
      · **라틴**이면 낱말이 둘 이상이고 **각 낱말이 대문자로 시작**한다
        (`Ognjen Cancarevic`) — `shots`·`big chances created` 는 떨어진다

    ⚠️ 완벽하지 않다(외자 이름·소문자 표기는 놓친다). 그래서 단계 4 가 **재현율을
       숫자로** 재고, 이 규칙이 얼마나 놓치는지 그 숫자가 말한다.
    """
    t = " ".join(str(raw or "").split())
    if not _looks_like_name(t):
        return False
    if _CJK_NAME.match(t):
        return True
    parts = t.replace(".", " ").replace("-", " ").split()
    return len(parts) >= 2 and all(w[:1].isupper() for w in parts if w)


def _tidy(name: str) -> str:
    return " ".join(str(name or "").split())


def _attribute(text: str, q: Question) -> str | None:
    """🔴 이 자료를 **어느 팀에 붙이나.** 모르면 `None`(= 귀속 불명).

    §17-g-3 원문: *"두 팀 언급 기사는 귀속 불명이면 **어느 팀에도 안 붙임**."*
    🔴 **"안 붙임"이지 "버림"이 아니다.** 사실은 남기고 팀 칸만 비운다 — 버리면
       진짜 라인업이 사라진다(실측 2026-09-30: 버리도록 짰다가 §19-g-2 의
       `中村晃`·`今宮健太` 표를 통째로 잃었다).

    귀속이 붙는 조건은 하나다: **우리 팀이 언급되고 상대는 언급되지 않을 때.**
      · 우리 팀을 안 말하는 자료 → 불명 (다른 경기 기사일 수 있다)
      · 둘 다 말하는 자료 → 불명 (한 표에 양 팀 타순이 든 경우다)

    ⚠️ 실측 2026-09-27 카세트: 소프트뱅크 질의 결과에 `ルーカス 4번 三塁`(다른 경기
       기사)가 있었고, 귀속 규칙이 없을 때 그것이 **소프트뱅크로 저장됐다** —
       M14(마요르카 기록을 알메리아 것과 바꿔 적음)와 같은 결의 오류다.
    """
    mine = (q.team or "").strip()
    if not mine:
        return None
    if not _names_hit(text, mine, q.local):
        return None
    if _names_hit(text, q.opponent or "", q.opponent_local):
        return None
    return mine


def _names_hit(text: str, formal: str, local: str | None) -> bool:
    """🔴 **판정은 `verify.mentions_team` 한 곳이다.** 여기 베끼지 않는다 —
    파서와 `cells` 의 열기 게이트가 갈리면 파서가 버릴 것을 열기가 열고 예산만 탄다.
    """
    return verify.mentions_team(text, formal, local)


# ══════════════════════════════════════════════════════════════════
# 선발 최근 창 · 감독 의도
# ══════════════════════════════════════════════════════════════════

#: `H. Wesneski (5-2) SP 91` · `ソフトバンク・大津` — 예고 선발 이름.
_EN_PITCHER = re.compile(r"\b([A-Z])\.\s*([A-Z][a-zA-Z\-']{2,})\b")
#: `3.50` · `1.15` 같은 수치. 🔴 **수치는 본문에서** 확인한다(§19-b-2).
_NUM = re.compile(r"\b\d+\.\d{2}\b")


def parse_starter_recent(hits, q: Question) -> list[Fact]:
    """예고 선발·최근 등판. 🔴 **수치가 스니펫에만 있으면 soft 다**(§19-b-2).

    §19-g-5 실측: `fantasypros` 스니펫이 `Astros … H. Wesneski (5-2) SP 91` 을
    주었다 — 이름은 잡히고 **ERA·WHIP 은 없다.** 그것을 "못 잰 칸"으로 남긴다.
    """
    out: list[Fact] = []
    for h in _articles(hits):
        text = f"{h.get('title') or ''} {h.get('body') or ''}"
        names = [f"{a}. {b}" for a, b in _EN_PITCHER.findall(text)]
        if not names:
            continue
        out.append(Fact(
            question_id=q.id,
            value={"names": names[:4], "numbers": _NUM.findall(text)[:6]},
            # 🔴 스니펫 근거 — 수치가 있어도 soft 다. 본문 대조가 hard 의 조건이다
            hardness="soft", source=h.get("url") or "",
                article_title=h.get("title") or "",
                article_body=h.get("body") or "",
            publisher=h.get("publisher") or "",
            published_at=h.get("published_at"),
            extracted_by="rule:EN_PITCHER", step=3))
    return out


def parse_intent(hits, q: Question) -> list[Fact]:
    """감독 인용. 🔴 **본문에 그 문장이 실재할 때만 `quote` 로 남긴다**(§12-c-6).

    ⚠️ 스니펫만으로는 대조할 본문이 없다 — 그래서 여기서는 `quote` 를 채우지 않고
       `open_body` 로 본문을 연 뒤 `parse_intent_body` 가 채운다. LLM 추출기는
       그럴듯한 인용을 **만들어낸다**(§17-g-2).
    """
    out: list[Fact] = []
    for h in _articles(hits):
        text = f"{h.get('title') or ''} {h.get('body') or ''}"
        if not _QUOTED.search(text):
            continue
        # 🔴 **그 팀 기사인지 먼저 본다** — M14 와 같은 귀속 결함이다.
        #    ⚠️ 실측 2026-10-01(USL 녹음): 이 검사가 없어서 `koreadaily.com` 의
        #       **영화 인터뷰**에서 `"자기 언어가 있는 영화에 손이 갈 것"` 을 뽑아
        #       감독 발언으로 블랙보드에 올렸다. 사실 0건보다 나쁘다 — 거짓 사실은
        #       그 위의 결론을 전부 틀리게 한다(§0).
        if not _names_hit(text, q.team or "", q.local):
            logger.info("[intent] 팀 언급 없음 — 인용을 버린다: %s",
                        (h.get("url") or "")[:90])
            continue
        out.append(Fact(
            question_id=q.id, value=_QUOTED.search(text).group(1)[:200],
            hardness="soft",            # 🔴 본문 대조 전에는 soft
            source=h.get("url") or "",
                article_title=h.get("title") or "",
                article_body=h.get("body") or "", publisher=h.get("publisher") or "",
            published_at=h.get("published_at"),
            extracted_by="rule:QUOTED", step=4))
    return out


_QUOTED = re.compile(r"[「\"“]([^」\"”]{6,200})[」\"”]")


def parse_lineup_body(got, q: Question) -> list[Fact]:
    """§19-b-2 — **라인업 본문을 연다.**

    🔴 실측 2026-09-30(단계 4): `lions-matome.com` 의
       `【試合実況】西武スタメン 先発:平良海馬（2026.9.29）` 가 검색에 잡혔고
       §13-c 날짜 검사도 통과했다. **그런데 타순은 본문에 있고 스니펫에는 없었다** —
       스니펫에는 제목과 광고 문구뿐이었다. 라인업 세포가 본문을 안 열어서
       그 표에 영영 닿지 못했다.

    §19-b-2 원문: *"스니펫에 답이 보여도 숫자·인용은 본문을 연다(web_fetch)."*
    타순은 **숫자**다 — 본문을 여는 것이 원문이 정한 길이다.

    ⚠️ 같은 파서를 쓴다(`parse_lineup`). 본문 전용 규칙을 따로 만들면 두 곳이
       갈리고, 갈리면 어느 쪽이 맞는지 아무도 모른다(사본 금지).
    """
    body = _strip_tags(getattr(got, "text", "") or "")
    if not body:
        return []

    class _AsHit:
        """본문을 `Hit` 모양으로 감싼다 — 파서가 한 길만 알게 한다."""

        title = ""
        snippet = body
        url = getattr(got, "url", "")
        publisher = ""
        published_at = getattr(got, "published_at", None)

    return parse_lineup([_AsHit()], q)


def parse_intent_body(got, q: Question) -> list[Fact]:
    """§19-b-2 — 본문을 열었다. 🔴 인용이 본문에 **실재하면** hard 다."""
    body = _strip_tags(getattr(got, "text", "") or "")
    # 🔴 본문에서도 **같은 귀속 검사**를 한다. 스니펫만 막으면 본문 경로로 들어온다
    #    (실측 2026-10-01: 영화 인터뷰가 들어온 경로가 본문이었다).
    if not _names_hit(body, q.team or "", q.local):
        logger.info("[intent] 본문에 팀 언급 없음 — 인용을 버린다 (%d자)", len(body))
        return []
    out: list[Fact] = []
    for m in _QUOTED.finditer(body):
        quote = m.group(1)
        v = verify.quote_grounded(quote, body)
        if not v.ok:
            continue
        out.append(Fact(question_id=q.id, value=quote[:200], quote=quote[:200],
                        hardness=v.hardness, source=getattr(got, "url", ""),
                        extracted_by="body:QUOTED", step=4))
        if len(out) >= 3:
            break
    return out


_TAG = re.compile(r"<[^>]+>")
#: 🔴 **`<script>`·`<style>` 은 내용까지 지운다.**
#
#  ⚠️ 실측 2026-09-30(단계 4): 종전 `_strip_tags` 는 **태그만** 걷고 코드 본문은
#     남겼다. 그래서 스포니치 기사 본문에서 뽑은 "선발 명단"이
#     `function(){q("i"` · `settings) { // GET` · `service_name: service_name`
#     같은 **자바스크립트**였다. 그리고 겐다가 그 목록에 없으니 "겐다 벤치"가
#     **통과로 찍혔다** — 두 번째 거짓 통과다.
#  🔴 `<noscript>` 도 지운다 — 광고·추적 코드가 거기 들어간다.
_SCRIPTISH = re.compile(
    r"<(script|style|noscript)\b[^>]*>.*?</\1\s*>", re.I | re.S)
#: 🔴 닫는 태그가 없는 깨진 문서도 있다 — 열린 `<script` 뒤를 통째로 버린다.
_SCRIPT_OPEN = re.compile(r"<(script|style)\b[^>]*>.*", re.I | re.S)


def _strip_tags(html: str) -> str:
    """HTML → 읽을 본문. 🔴 **코드는 본문이 아니다.**

    ⚠️ 이 함수가 본문 파싱 전부의 입구다(`parse_lineup_body`·`parse_intent_body`·
       `parse_football_xi_body`). 여기서 코드가 새면 **모든 추출이 오염된다.**
    """
    out = _SCRIPTISH.sub(" ", html or "")
    out = _SCRIPT_OPEN.sub(" ", out)
    return " ".join(_TAG.sub(" ", out).split())


# ══════════════════════════════════════════════════════════════════
# §19-b-3 — 검색 결과에 검증기를 건다 (④ 중복 제거를 여기서 쓴다)
# ══════════════════════════════════════════════════════════════════


def _articles(hits) -> list[dict]:
    """`Hit` 목록 → 검증기가 읽는 기사 dict. 🔴 **여기서 ④ 중복을 지운다.**

    §12-c-4: *"같은 보도자료 8건은 원문 1건이다."* 지우지 않으면 한 통신사 기사가
    8개 근거로 세어져 hardness 가 부풀고, 그것이 자료 충분성(STEP 4)을 속인다.

    ⚠️ 버린 것을 로그에 **개수와 함께** 남긴다 — 조용히 지우면 "왜 근거가 1건뿐
       인가"를 되짚을 수 없다.
    """
    arts = []
    for h in hits or []:
        arts.append({
            "title": getattr(h, "title", "") or "",
            "body": getattr(h, "snippet", "") or "",
            "url": getattr(h, "url", "") or "",
            "publisher": getattr(h, "publisher", "") or "",
            "published_at": getattr(h, "published_at", None),
        })
    kept, dups = verify.dedupe(arts)
    if dups:
        logger.info("[검증④] 중복 %d건 지웠다 (원문 %d건) — %s", len(dups),
                    len(kept), [d["url"] for d in dups[:3]])
    return kept


# ══════════════════════════════════════════════════════════════════
# §19-g-6 — 동명이인은 `player_id` 로 갈린다
# ══════════════════════════════════════════════════════════════════


async def attach_player_ids(pool, facts: list[Fact], *, league: str,
                            team: str | None) -> list[str]:
    """사실에 붙은 선수 이름 → `player_id`. 반환은 **미상 사유들**.

    🔴 §19-g-6: *"인천 김건희(DF, 23세) vs 강원 김건희(FW, 31세)처럼 동명이인은
       1b player_id 로 갈라서 애초에 같은 질문이 되지 않게 한다."*
    🔴 **팀이 불명이면 즉시 미상이다**(`ids.resolve_by_name`) — 거짓 매칭보다
       미상이 낫다. 이름만으로 맞추면 결장이 상대 팀에 붙는다.
    """
    unresolved: list[str] = []
    for f in facts:
        name = _name_of(f.value)
        if not name:
            continue
        pid, how = await ids.resolve_by_name(pool, league=league,
                                            team=f.team or team, name=name)
        if pid is None:
            unresolved.append(f"{name}: {how}"
                              + ("" if f.team or team else " (팀 불명)"))
            continue
        f.player_id = pid
    if unresolved:
        logger.info("[ids] 미상 %d건 — %s", len(unresolved), unresolved[:5])
    return unresolved


def _name_of(value) -> str:
    if isinstance(value, dict):
        return str(value.get("player_name") or value.get("name") or "")
    return ""


# ══════════════════════════════════════════════════════════════════
# §4 `coach_change` — 감독 교체 (단계 4b)
# ══════════════════════════════════════════════════════════════════

#: `현재 감독 Ramaz Svanadze 나이: 45 전략 선택 취임 일자: 2026년 9월 26일`
#: 🔴 실측 2026-09-30(단계 4): transfermarkt 가 이 꼴로 준다. 경기는 09-28 이므로
#:    취임 09-26 → **이틀 만에 첫 경기**이고, 그것이 §9 필수 8건 ① 의 사실이다
#:    (정본 §4 도 *"조지아 사뇰 사임·**이틀 만에 첫 경기**"* 라고 적었다).
_COACH_SINCE = re.compile(
    r"현재\s*감독\s*([^\d\n]{2,40}?)\s*나이[:：]\s*\d+"
    r"[^취]*?취임\s*일자[:：]\s*(20\d\d)[년.\-/]\s*(\d{1,2})[월.\-/]\s*(\d{1,2})")
#: 감독이 떠난 것을 말하는 낱말. 🔴 **원본은 여기 하나다** — 읽는 쪽이 다시 적지 않는다.
COACH_OUT_MARKS = ("사임", "해임", "물러", "경질", "떠난", "stepped down",
                   "resigned", "sacked", "departure")
#: 새로 온 것을 말하는 낱말.
COACH_IN_MARKS = ("부임", "선임", "취임", "새 감독", "신임", "appointed",
                  "takes charge", "named")


def parse_coach_change(hits, q: Question) -> list[Fact]:
    """§4 `coach_change` — 감독 교체·부임 시점·**첫 경기 여부**.

    🔴 정본 §4 가 요구하는 것은 셋이다: *"감독 교체·부임 시점·첫 경기 여부."*
       부임 시점을 알면 첫 경기 여부는 **경기 날짜와 견줘 계산**한다 — 기사가
       "첫 경기"라고 적어 주기를 기다리지 않는다.

    ⚠️ **귀속이 어렵다.** transfermarkt 스니펫에는 `현재 감독` 블록이 **둘**이다
       (양 팀). 순서가 홈-원정이라고 가정하지 않는다 — §17-g-3 대로 **둘 다 남기고
       팀을 비운다.** 어느 쪽이 우리 팀인지는 이름을 아는 뒤 단계 5 가 가른다.

    🔴 `days_since` 를 계산해 넣는다 — 그것이 §4 의 "첫 경기 여부"다. 날짜를 못
       읽으면 그 칸을 **비운다**(지어내지 않는다).
    """
    out: list[Fact] = []
    game_day = q.deadline.astimezone(KST).date() if q.deadline else None
    for h in _articles(hits):
        text = f"{h.get('title') or ''} {h.get('body') or ''}"
        # 🔴 §13-c ① — **그 경기를 말하는 자료만.** 이 검사가 `dateless_ok` 를
        #    정당하게 만든다(발행 시각 대신 이것이 "그 경기 것인가"를 답한다).
        if not _mentions_game_day(text, q):
            continue
        found = _COACH_SINCE.findall(text)
        if found:
            # 🔴 블록이 둘이면 양 팀 것이다 — 귀속하지 않는다(§17-g-3)
            team = _attribute(text, q) if len(found) == 1 else None
            for name, y, mo, d in found:
                since = date(int(y), int(mo), int(d))
                value = {"coach": _tidy(name), "since": str(since)}
                if game_day is not None:
                    value["days_before_game"] = (game_day - since).days
                    # 🔴 §4 "첫 경기 여부" — 취임 뒤 첫 경기인지
                    value["likely_first_game"] = 0 <= value["days_before_game"] <= 7
                out.append(Fact(
                    question_id=q.id, value=value, hardness="soft",
                    source=h.get("url") or "",
                article_title=h.get("title") or "",
                article_body=h.get("body") or "",
                    publisher=h.get("publisher") or "",
                    published_at=h.get("published_at"),
                    extracted_by="rule:COACH_SINCE", step=1, team=team))
            continue

        # 🔴 날짜가 없는 서술형 — `사임`·`부임` 낱말만 있는 기사
        out_mark = next((m for m in COACH_OUT_MARKS if m in text), None)
        in_mark = next((m for m in COACH_IN_MARKS if m in text), None)
        if not (out_mark or in_mark):
            continue
        out.append(Fact(
            question_id=q.id,
            value={"coach_change": True,
                   "left": out_mark, "arrived": in_mark,
                   # 🔴 **날짜를 모르면 비운다** — 서술만으로는 시점을 못 안다
                   "since": None},
            hardness="soft", source=h.get("url") or "",
                article_title=h.get("title") or "",
                article_body=h.get("body") or "",
            publisher=h.get("publisher") or "",
            published_at=h.get("published_at"),
            extracted_by="rule:COACH_MARK", step=1,
            team=_attribute(text, q)))
    return out


# ══════════════════════════════════════════════════════════════════
# 축구 선발 XI (단계 4b) — 야구 9명 파서와 **다른 꼴**이다
# ══════════════════════════════════════════════════════════════════

#: `Armenia : Ognjen Cancarevic, Erik Piloyan, Argishti Petrosyan, …`
#: 🔴 실측 2026-09-30: footboom1 이 이 꼴로 준다(팀명 · 콜론 · 쉼표 나열).
#:
#: ⚠️ **종전 판은 너무 느슨했다.** `A : b, c, d, …` 가 자바스크립트 객체 리터럴
#:    (`{ service_name: service_name, category: category, … }`)에 그대로 맞았고,
#:    그 "이름들"이 선발 명단으로 저장됐다(두 번째 거짓 통과).
#: 🔴 **이름처럼 생긴 것만** 받는다: 글자·공백·`.`·`-`·`'` 뿐이고 코드 기호가 없다.
_XI_LIST = re.compile(
    r"([A-Za-z가-힣][A-Za-z가-힣\s.\-]{1,28})\s*[:：]\s*"
    r"((?:" + _NAME_CHARS + r"\s*,\s*){5,}" + _NAME_CHARS + r")")
#: `先発 GK 21 市川暉記 DF 16 伊藤槙人 DF 30 山崎浩介 …`
#: 🔴 실측 2026-09-30: ゲキサカ 가 이 꼴로 준다(포지션 · 등번호 · 이름).
_XI_POS_NUM = re.compile(
    r"\b(GK|DF|MF|FW)\s*(\d{1,2})\s*([^\s0-9,;]{2,12})")

#: 🔴 축구는 **11명**이다(§13-c: *"양 팀 9명(축구 11명)이 다 있는가"*).
#:    절반 이상 보이면 라인업으로 본다 — 스니펫은 잘린다.
MIN_XI = 6


def parse_football_xi(hits, q: Question) -> list[Fact]:
    """축구 선발 XI. 🔴 야구 타순 파서와 **꼴이 다르다** — 등번호·포지션·쉼표 나열.

    ⚠️ 실측 2026-09-30(단계 4): §9 필수 8건 ②④(발베르데·아르메니아 센터백)가
       **이 파서가 없어서** 0점이었다. 검색은 명단을 가져왔다 —
       `Armenia : Ognjen Cancarevic, Erik Piloyan, …` (footboom1).

    🔴 §13-c ① 경기 날짜 검사는 `parse_lineup` 과 같이 적용한다 — 다른 경기의
       명단을 오늘 것으로 읽는 것이 가장 흔한 사고다(M13).
    """
    out: list[Fact] = []
    for h in _articles(hits):
        text = f"{h.get('title') or ''} {h.get('body') or ''}"
        if not _mentions_game_day(text, q):
            continue
        team = _attribute(text, q)

        # ① 포지션+등번호 꼴이 가장 세다 — 포지션을 알면 센터백 수를 셀 수 있다
        pos = _XI_POS_NUM.findall(text)
        if len(pos) >= MIN_XI:
            rows = [{"pos": p, "no": int(n), "name": _tidy(nm)}
                    for p, n, nm in pos]
            out.append(Fact(
                question_id=q.id, value=rows, hardness="soft",
                source=h.get("url") or "",
                article_title=h.get("title") or "",
                article_body=h.get("body") or "", publisher=h.get("publisher") or "",
                published_at=h.get("published_at"),
                extracted_by="rule:XI_POS_NUM", step=3, team=team))
            continue

        # ② `팀 : 이름, 이름, …` 꼴 — 포지션은 없다
        for who, names in _XI_LIST.findall(text):
            got = [_tidy(x) for x in names.split(",") if _looks_like_person(x)]
            if len(got) < MIN_XI:
                continue
            # 🔴 **그 줄이 우리 팀 것인지** 본다. 아니면 팀을 비운다(§17-g-3)
            mine = _names_hit(who, q.team or "", q.local)
            out.append(Fact(
                question_id=q.id,
                value=[{"name": n, "pos": None, "no": None} for n in got],
                hardness="soft", source=h.get("url") or "",
                article_title=h.get("title") or "",
                article_body=h.get("body") or "",
                publisher=h.get("publisher") or "",
                published_at=h.get("published_at"),
                extracted_by="rule:XI_LIST", step=3,
                team=(q.team if mine else None)))
    return out


def parse_lineup_any(hits, q: Question) -> list[Fact]:
    """야구 타순 **과** 축구 XI 를 함께 본다. 🔴 **꼴이 자료를 가른다.**

    ⚠️ 리그→종목 표를 손으로 만들지 않는다 — `국제대회` 는 축구일 수도 야구일 수도
       있고(WBC), 그 표는 언제나 한 발 늦는다(CLAUDE.md §사본 금지). 두 파서는
       **서로 겹치지 않는 꼴**을 본다(일본어 압축 타순 ↔ `GK/DF/MF/FW` 등번호),
       그래서 자료가 스스로 어느 쪽인지 말한다.
    """
    return parse_lineup(hits, q) + parse_football_xi(hits, q)


def parse_lineup_any_body(got, q: Question) -> list[Fact]:
    """§19-b-2 — 본문에서 **구조부터** 본다. 🔴 순서가 뜻을 가진다.

    ⚠️ 실측 2026-10-01: 봇이 fotmob 경기 페이지에 닿았는데 **사실 0건**이었다.
       그 페이지에는 선수 이름이 15/23명 있었고, 자료는 HTML 글자가 아니라
       `__NEXT_DATA__` **JSON** 에 있었다. 글자 파서는 그것을 못 읽는다.
    🔴 그래서 **구조가 있으면 구조를 먼저 읽는다.** 글자 훑기는 구조가 없을 때다 —
       구조는 포메이션·감독·교체 수까지 주고, 글자 훑기는 이름 몇 개에서 잘린다.
    """
    # 🔴 fotmob 경기 페이지는 JSON 으로 11명 전부를 준다(§13-c ② 가 요구하는 수)
    structured = fotmob.parse_match(got, q)
    if structured:
        # 🔴 **한 번 열었으니 다 읽는다.** 맞대결·폼·통계·구장이 같은 JSON 에 있고,
        #    열기 예산은 이미 썼다 — 측정 2026-10-01 이 도달 7/15 · 변환 0/15 로
        #    가리킨 자리다.
        return structured + fotmob.parse_context(got, q)
    return parse_lineup_body(got, q) + parse_football_xi_body(got, q)


def parse_football_xi_body(got, q: Question) -> list[Fact]:
    """§19-b-2 — 축구 XI 본문. 🔴 스니펫은 6~7명에서 잘린다(실측)."""
    body = _strip_tags(getattr(got, "text", "") or "")
    if not body:
        return []

    class _AsHit:
        title = ""
        snippet = body
        url = getattr(got, "url", "")
        publisher = ""
        published_at = getattr(got, "published_at", None)

    return parse_football_xi([_AsHit()], q)


# ══════════════════════════════════════════════════════════════════
# 세포 만들기
# ══════════════════════════════════════════════════════════════════


def lineup_cell(*, team: str, league: str, day: date, game_id: int | None,
                starts: datetime, local: str = "", opponent: str = "",
                opponent_local: str = "", venue: str = "",
                now: datetime | None = None,
                mode: str = SLATE,
                extra: list[Source] | None = None,
                # 🔴 사용자 수정 ① — 질의에 실을 상대·종목·언어
                opp_q: str = "", opp_q_local: str = "",
                sport: str = "", langs: tuple[str, ...] = ()
                ) -> tuple[Cell, list[str]]:
    """확정 라인업 세포. 🔴 마감은 **경기 시각**이다 — §19-e 지연을 그것으로 잰다.

    🔴 **"아직 공개 전 0건"과 "공개됐는데 0건"을 구분해 적는다.** §13-b 는 라인업이
       경기 1시간 전에 공개된다고 못 박았고, §19-d 는 T-70분부터 두드리라고 한다 —
       그 10분 동안의 0건은 **소스 결함이 아니다.** 구분하지 않으면 다음 사람이
       파서를 고치려 하고, 고칠 것은 없다(CLAUDE.md §"자료가 안 왔다"와 "왔는데
       못 뽑았다"를 구분해 적는다).
    """
    q = Question(Q_LINEUP, f"{league}:{team}:{day}", game_id=game_id,
                 team=team, league=league, deadline=starts, opponent=opponent,
                 sport=sport or None,
                 # 🔴 기사가 쓰는 표기를 질문에 싣는다 — 귀속 판단의 재료다
                 local=local or None, opponent_local=opponent_local or None)
    srcs, dropped = search_sources(
        Q_LINEUP, team=team, league=league, day=day, local=local, venue=venue,
        # 🔴 질의에 **신원**을 싣는다(사용자 수정 ① · 2026-10-04)
        opponent=opp_q, opponent_local=opp_q_local,
        sport=sport, langs=langs,

        # 🔴 야구 타순 **과** 축구 XI 를 함께 본다 — 꼴이 자료를 가른다
        parse=parse_lineup_any,
        # 🔴 §19-b-2 — 타순·명단은 **숫자**다. 스니펫에 없으면 본문을 연다
        #    (실측 2026-09-30: footboom1 의 아르메니아 XI 가 본문에 있었다).
        parse_body=parse_lineup_any_body, open_body=True,
        # 🔴🔴 §17-b **L1 결장** — 규칙 파서가 0건을 낸 본문을 읽는다.
        #    사용자 지시 2026-10-02: *"핵심은 '검색'이 아니라 '읽기'다"*.
        #    ⚠️ 실측(여자 아시안게임): 결장·휴식·감독 발언이 전부 산문에 있었는데
        #       가져온 것은 0건이었다. 규칙 파서는 **숫자 꼴**만 읽는다.
        extract_tasks=("L1",),
        # 🔴 **그 경기 날짜를 말하는 자료를 먼저 연다**(§13-c ①). 열기 예산이
        #    몇 건뿐이라 순서가 결과를 정한다 — 51건 중 맞는 것이 하나였다.
        prefer=lambda text: _mentions_game_day(text, q),
        # 🔴 §13-a 금지 소스는 **열지 않는다** — 검색 1순위로 나온다
        deny=deny_lineup_source,
        # 🔴 §12-c-1 *"soft 로만 남긴다"* — 라인업 파서가 §13-c ① 로 이미 그
        #    경기 것임을 확인한다(경기 데이터 페이지에는 발행 시각이 없다)
        dateless_ok=True,
        # 🔴 §19-c — 경기 페이지가 **직전 경기**를 가리킨다. 그것이 사용자가 손으로
        #    한 일이고(*"직전 경기 선발 XI를 기준 XI로"*), 결정 C 다.
        follow=fotmob.follow_links, parse_follow=fotmob.parse_followed)
    # 🔴 **공식 API 소스를 먼저 둔다**(`extra`). 순서가 곧 시도 순서다 —
    #    공식은 1층이고 결정적이다. 검색보다 뒤에 두면 검색 결과가 먼저 예산을 쓴다.
    #    ⚠️ 야구·하키의 깊이가 여기로 들어온다(`mlb.sources_context`·`nhl.…`).
    srcs = list(extra or []) + srcs
    # 🔴 열기 예산 3 — §19-b-2 가 본문을 열라고 하고, 검색 결과에 무관한 것이
    #    섞이므로(실측: 51건 중 1건) 두 번으로는 맞는 페이지에 닿지 못한다.
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **깊이 소스가 기사 열기 예산을 먹고 있었다**(실측 2026-10-02)
    # ══════════════════════════════════════════════════════════════════
    #
    #  `extra`(공식 API 깊이)는 `kind="url"` 이라 **열기 예산을 쓴다**. NPB 는 그것이
    #  둘(순위 두 장)이었으므로 열기 3 중 2 를 먹고 기사에 **1건**만 남았다.
    #  🔴 공식 깊이를 늘릴수록 기사를 못 읽게 되는 구조였다 — 이번에 깊이를 여섯으로
    #     늘렸으니 그대로 두면 기사를 **한 건도** 못 연다.
    #  ⚠️ 그래서 깊이 개수만큼 **더해 준다**. 늘린 것은 검색 결과를 여는 예산이
    #     아니라 *공식 주소를 여는 예산*이고, 그 둘은 다른 일이다.
    cell = Cell(q, srcs,
                budget=budget_for(len(srcs), fetches=3 + len(extra or []),
                                  mode=mode))
    opens = queries.lineup_opens_before_min()
    left = (starts - (now or datetime.now(timezone.utc))).total_seconds() / 60
    if left > opens:
        cell.tried.append(
            f"§13-b 공개 전(T-{int(left)}분 · 공개는 T-{opens}분)")
    return cell, dropped


def intent_cell(*, team: str, league: str, day: date, game_id: int | None,
                starts: datetime, local: str = "",
                mode: str = SLATE,
                opp_q: str = "", opp_q_local: str = "",
                sport: str = "", langs: tuple[str, ...] = ()
                ) -> tuple[Cell, list[str]]:
    """감독 의도 세포. 🔴 인용은 **본문을 열어** 대조한다(§19-b-2 · §12-c-6)."""
    q = Question(Q_INTENT, f"{league}:{team}:{day}", game_id=game_id,
                 team=team, league=league, deadline=starts, sport=sport or None)
    srcs, dropped = search_sources(Q_INTENT, team=team, league=league, day=day,
                                   local=local, parse=parse_intent,
                                   # 🔴 질의에 신원(사용자 수정 ① · 2026-10-04)
                                   opponent=opp_q, opponent_local=opp_q_local,
                                   sport=sport, langs=langs,
                                   parse_body=parse_intent_body,
                                   open_body=True,
                                   # 🔴🔴 §17-b **L2 인용·의도** — 감독 발언은
                                   #    규칙으로 못 읽는다(실측: 큰따옴표만 보면
                                   #    영화 인터뷰·cisa.gov 가 들어왔다).
                                   extract_tasks=("L2",),
                                   # 🔴 §12-c-1 — transfermarkt 경기 페이지에는
                                   #    발행 시각이 없다. `parse_coach_change` 가
                                   #    §13-c 로 그 경기 것임을 확인한다
                                   dateless_ok=True)
    return Cell(q, srcs,
                budget=budget_for(len(srcs), fetches=2, mode=mode)), dropped


def coach_cell(*, team: str, league: str, day: date, game_id: int | None,
               starts: datetime, local: str = "", opponent: str = "",
               mode: str = SLATE,
               opp_q: str = "", opp_q_local: str = "",
               sport: str = "", langs: tuple[str, ...] = ()
               ) -> tuple[Cell, list[str]]:
    """§4 `coach_change` 세포 — **감독 교체·부임 시점·첫 경기 여부.**

    🔴 **왜 감독 의도 세포와 따로인가**(§19-a: *"세포 하나 = 사실 질문 하나"*):
       실측 2026-09-30(단계 4) — 둘을 한 세포에 넣었더니 인용 하나(`이리 될 줄은..`)
       를 얻고 세포가 **멈췄고**, 감독 교체 자료(transfermarkt)에는 영영 못 갔다.
       §19-b 는 첫 성공에서 멈추는 것이 맞고, 그러면 **질문이 둘이면 세포도 둘**이다.

    ⚠️ 질문 타입은 `intent` 를 쓰되 `subject` 에 `:coach` 를 붙여 **질문 id 를
       가른다** — §19-a 의 타입 목록을 늘리지 않으면서 질문을 구분하는 길이다
       (`source_score.question_type` 제약이 그 목록을 강제한다).
    """
    q = Question(Q_INTENT, f"{league}:{team}:{day}:coach", game_id=game_id,
                 team=team, league=league, deadline=starts, sport=sport or None,
                 opponent=opponent or None, local=local or None)
    srcs, dropped = search_sources(
        Q_INTENT, team=team, league=league, day=day, local=local,
        parse=parse_coach_change,
        # 🔴 질의에 **신원**을 싣는다(사용자 수정 ① · 2026-10-04)
        opponent=opp_q, opponent_local=opp_q_local,
        sport=sport, langs=langs,

        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **본문을 열고 추출기를 건다**(사용자 기술 지시 2026-10-03 · ③)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 종전에는 **규칙 파서 하나**였다 — `parse_coach_change` 의 정규식이
        #     안 맞으면 그 세포는 **영영 0** 이었다. 실측 2026-10-03(KBO):
        #     문서 147건을 열었는데 사실이 **4건**이었고 그중 감독 것은 0건이다.
        #  🔴 §17-b 가 L1~L3 를 둔 까닭이 그것이다 — *"규칙 파서가 못 읽는 형식의
        #     **대체**"*. 규칙 파서가 먼저 돌고, 0건일 때만 추출기가 돈다.
        #  ⚠️ 추출기가 **판정하지 않는다** — 감독 교체의 *부임 시점*은 여전히
        #     `classify` 가 요구한다(낱말만으로는 변수가 아니다).
        open_body=True, extract_tasks=("L2",),
        # 🔴 §12-c-1 — transfermarkt 경기 페이지에는 발행 시각이 없다.
        #    `parse_coach_change` 가 §13-c 로 그 경기 것임을 확인한다.
        dateless_ok=True)
    return Cell(q, srcs,
                budget=budget_for(len(srcs), fetches=1, mode=mode)), dropped


def starter_recent_cell(*, team: str, league: str, day: date,
                        game_id: int | None, starts: datetime,
                        local: str = "",
                        mode: str = SLATE,
                        # ⚠️ `opp_q` 를 **안 받는다** — 지난 등판을 묻는 질문이라
                        #    오늘 상대를 넣으면 없는 기사를 찾는다(CELL_PLAN 주석)
                        sport: str = "", langs: tuple[str, ...] = ()
                        ) -> tuple[Cell, list[str]]:
    """선발 최근 창 세포. §19-d — T-6h 에 깬다."""
    q = Question(Q_STARTER_RECENT, f"{league}:{team}:{day}", game_id=game_id,
                 team=team, league=league, deadline=starts, sport=sport or None)
    srcs, dropped = search_sources(Q_STARTER_RECENT, team=team, league=league,
                                   day=day, local=local,
                                   parse=parse_starter_recent,
                                   # ⚠️ 상대는 **안 싣는다**(지난 등판 질문이다)
                                   sport=sport, langs=langs,
                                   # 🔴 **본문을 연다**(사용자 기술 지시 ③).
                                   #    ⚠️ 종전엔 규칙 파서뿐이라 예고 선발 기사를
                                   #       열지도 않았다 — 한국·일본 매체는 선발을
                                   #       산문으로 적는다(표가 아니다).
                                   open_body=True, extract_tasks=("L1",))
    return Cell(q, srcs,
                budget=budget_for(len(srcs), fetches=1, mode=mode)), dropped




def counter_cell(*, subject: str, condition: str, league: str, day: date,
                 game_id: int | None, variants: list[queries.Variant],
                 deps: list[str] | None = None,
                 mode: str = SLATE) -> Cell:
    """§19-g-5 **반증 세포** — unknown 이 낳은 질문이다.

    *"휴스턴 선발: unknown → 반증 세포 → RotoWire hit → 웨스네스키 사실 → 판정
    상향"*(09-27 실측). 🔴 검색어는 L5 가 만들고 §12-b 로 걸러진 것들이다.

    🔴 **세포는 판정하지 않는다** — 사실만 낸다. 상향은 `judge.py` 몫이다(§19-f).
    """
    q = Question(Q_COUNTER, f"{league}:{subject}:{day}", game_id=game_id,
                 team=None, league=league)
    srcs = [Source(name=f"반증:{v.axis}", kind="search", query=v.text,
                   lang=v.lang, tier=verify.TIER_PRIMARY, verify=True,
                   parse=parse_starter_recent)
            for v in variants]
    cell = Cell(q, srcs, deps=deps or [],
                budget=budget_for(len(srcs), fetches=1, mode=mode))
    cell.reason = f"반증 조건: {condition}"
    return cell


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **카탈로그 세포** — 경기마다 유형 전부를 돌린다 (사용자 설계 2026-10-02)
# ══════════════════════════════════════════════════════════════════
#
# > 봇이 경기마다 카탈로그 전 유형을 돌린다. 그러면 "무엇을 찾을지"를 모델이 정할
# > 필요가 없다. **8B 모델이 제일 못하는 게 바로 그 판단**이라 코드로 뺀다.
#
# 🔴 세포 하나 = **유형 하나**다(§19-a: *"세포 하나 = 사실 질문 하나"*). 그래서 유형이
#    늘면 세포가 늘고, 한 유형이 0건이어도 **다른 유형은 계속 돈다.**
#    ⚠️ 전에 한 세포에 질문 둘을 넣었다가 첫 성공에서 멈춰 둘째를 영영 못 얻었다
#       (실측 2026-09-30 감독 교체) — 그 실수를 되풀이하지 않는다.


