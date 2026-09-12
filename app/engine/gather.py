"""[ORD-10 · 1단계] **질문 없이 경기 것만 긁는다.**

사용자 지시 2026-09-12: "갈림길 변수등을 서치로 지정하지 않고 경기에 대한
것만 서치해 온다...그후 ai에게 정보를 준다.ai가 거른다"

🔴 왜 순서를 또 바꾸나 — 질문에 매인 수집이 세 가지로 새고 있었다(실측 09-12):
     · 퍼플렉시티 경기당 최대 4콜 → **429 발생**
     · X 는 질답을 강요당해 같은 프롬프트 5회에 답 `[0,0,1,0,1]`
       (자유 서술로 물으면 클레빈저 영입·선발 예고를 한 번에 냈다)
     · `xsearch.fetch_for_game` — 질문 없는 속보 수집기가 **놀고 있었다**

⚠️ **이 단계는 잡음을 줄이지 않는다.** 거르는 일은 전부 ②(선별)가 한다.
   그러니 합격 기준은 "적게 가져오기"가 아니라 **"빠뜨리지 않고, 출처와
   시각을 붙여 가져오기"**다.
   🔴 그 대가를 기억해 둔다 — DSM-1 실측이 조준 없는 수집의 결과였다:
      위성 76건 중 조사 인용 **0건**. ②가 못 거르면 그 상태로 돌아간다.

⚠️ 행 모양은 기존 `deepsearch.reinforce` 의 `자료` 와 **같게** 맞춘다
   (질문·답·소스·소스유형·시점·계정·url). 새 계약을 만들지 않는다.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

#: 위성 참고 상한. 원본 규약은 `deepsearch.MAX_SAT`(ORD-3) 이다 — 여기서
#  숫자를 새로 정하지 않는다.
from app.engine.deepsearch import MAX_SAT  # noqa: E402

#: 퍼플렉시티 프리뷰 1콜. **질문 목록이 아니다** — 경기에 걸린 것을 훑어 온다.
#  🔴 성적을 금지하는 이유는 ORD-5 실측 그대로다: 조사요청 38문 중 28문(74%)이
#     성적 조회였고, 그건 어느 날에나 같은 값이라 오늘을 설명하지 못한다.
PREVIEW_ASK = """오늘({today}) {league} 경기 "{away} @ {home}" 에 **오늘 걸린 사실**을
찾아라. 질문 목록은 없다 — 이 경기와 닿는 것을 훑어 온다.

찾을 것 — **오늘/이번 주에 바뀐 것**:
  · 부상·통증 — IL 등재/복귀, 타구 맞음, 검진 결과
  · 등록 — KBO 1군 등록·말소, MLB IL·옵션·콜업, 트레이드
  · 선발 — 예고와 변경, 등판 간격, 투구수 제한
  · 불펜 — 연투, 마무리 가용 여부, 소진 보도
  · 라인업 — 주전 결장·휴식 예고
  · 환경 — 돔 지붕 개폐, 바람·비, 구장 변경
  · 팀 사정 — 감독 코멘트, 순위 경쟁, 특별 경기

🔴 **성적을 가져오지 마라.** 시즌 성적·평균자책점·팀 타율·OPS·게임로그·
   통산 전적은 어느 날에나 같은 값이고 오늘을 설명하지 않는다.
🔴 **경기 전 것만.** 끝난 경기의 결과·하이라이트·팬 반응은 빼라.
🔴 **없으면 없는 대로 적게 가져와라.** 채우려고 일반론을 쓰지 마라.
🔴 `시점` 은 그 일이 있었던 날이다. 모르면 빈 칸으로 두되 사실은 남겨라.

[출력] 아래 JSON만 출력한다. 다른 텍스트, 마크다운 백틱 금지. 최대 10건.
{{"답": [{{"답": "사실 1문장", "시점": "YYYY-MM-DD", "소스유형": "공식|기록|뉴스",
        "url": "..."}}]}}
찾은 것이 없으면 `{{"답": []}}` 을 출력하라."""


def _row(answer: str, *, src: str, kind: str = "", when: str = "",
         account: str = "", url: str = "") -> dict:
    """수집 행 하나. 모양의 원본은 `deepsearch._rows` 다."""
    return {"질문": "", "답": answer, "소스": src, "소스유형": kind,
            "시점": when, "계정": account, "url": url}


async def _satellite(jg: dict, redis) -> list[dict]:
    """위성 캐시. 최신순으로 잘라 온다(ORD-3 에서 정한 규약)."""
    from app.collectors.satellite import read_cache

    items = await read_cache(redis, (jg.get("sport") or "").lower(),
                             jg.get("game_id"))
    items = sorted(items or [],
                   key=lambda a: (a.get("age_h") is None,
                                  float(a.get("age_h") or 0.0)))
    out = []
    for a in items[:MAX_SAT]:
        title = (a.get("title") or "").strip()
        body = (a.get("body") or "").strip()
        text = title if (not body or body.startswith(title[:40])) \
            else (f"{title} — {body[:300]}" if title else body[:300])
        if text:
            out.append(_row(text, src="satellite",
                            kind=str(a.get("source") or ""),
                            url=str(a.get("url") or "")))
            out[-1]["age_h"] = a.get("age_h")
    return out


async def _x_news(jg: dict, date: str, redis) -> list[dict]:
    """X 속보. **`xsearch` 가 원본이다** — 프롬프트·URL 검증·캡을 다시 만들지 않는다.

    🔴 ORD-8 에서 내가 여기에 질답 틀을 씌운 것이 잘못이었다. 실측: 같은
       질답 프롬프트 5회에 답 `[0,0,1,0,1]`. 자유 서술로 물으면 한 번에 답했다.
    ⚠️ 경기당 1콜·일일 캡은 `xsearch` 안에 있다. 우회하지 않는다.
    """
    from app.collectors.xsearch import fetch_for_game, load_cache

    sport = (jg.get("sport") or "").lower()
    gid = jg.get("game_id")
    # 🔴 **먼저 캐시를 읽는다.** `xsearch` 는 경기당 1콜이라, 스케줄러가 낮에
    #    소진했으면 여기서 다시 쏴도 빈손이다(실측 2026-09-12: KBO·NPB 전부 0건).
    #    먼저 쏜 쪽이 채우고 나머지는 읽는다. 캡을 우회하지 않는다.
    items = await load_cache(redis, sport, gid, date)
    if not items:
        items = await fetch_for_game(jg, date, redis)
    # 🔴 **키를 손으로 적지 마라.** `parse_items` 는 `headline` 을 받아
    #    `title` 로 **바꿔서** 돌려준다(xsearch.py:150). 실측 2026-09-12:
    #    `headline` 으로 읽어 NPB 4건·2건이 통째로 버려졌고, 로그에는
    #    "적재 4건"이라 찍혀 있었다 — 수집기는 성공했는데 우리가 못 읽었다.
    return [_row(str(it.get("title") or "").strip(), src="x", kind="뉴스",
                 when=str(it.get("at") or "")[:10],
                 account=str(it.get("account") or ""),
                 url=str(it.get("url") or ""))
            for it in (items or []) if (it.get("title") or "").strip()]


async def _preview(jg: dict) -> list[dict]:
    """퍼플렉시티 프리뷰 **1콜**. 질문 목록이 아니다."""
    from app.config import get_settings
    from app.engine.deepsearch import _pplx_findings, _today_kst

    s = get_settings()
    if not getattr(s, "deepsearch_pplx_enabled", False):
        return []
    prompt = PREVIEW_ASK.format(
        today=_today_kst(),
        league=jg.get("league") or (jg.get("sport") or "").upper(),
        away=jg.get("away"), home=jg.get("home"))
    data = await _pplx_findings(prompt, max_tokens=1600)
    items = (data or {}).get("답") if isinstance(data, dict) else None
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        fact = str(it.get("답") or it.get("사실") or "").strip()
        if fact:
            out.append(_row(fact, src="pplx",
                            kind=str(it.get("소스유형") or "").strip(),
                            when=str(it.get("시점") or "").strip(),
                            url=str(it.get("url") or "").strip()))
    return out


async def _lineup(jg: dict, redis, date: str) -> list[dict]:
    """[ORD-14] 크롤러가 긁어 둔 **오늘 선발 예고·타순·변화 이력**.

    사용자 지적 2026-09-12: "go언어가 네이버 야후 mlb는 다른곳에서 크롤링을
    한다…경기시작 전에 라인업 선발을 가지고 온다…그거 역시도 수집에 들어가야 한다"

    🔴 **이건 DB 수치가 아니라 오늘의 사실이다.** 타순·선발 예고·"18:05 에
       4번 타자가 빠졌다"는 성적이 아니라 오늘 바뀐 것이고, 그래서 4단계
       (참조용 DB)가 아니라 **1단계(수집)** 에 들어간다.
    🔴 근거: 3단계 실측 2026-09-12 — 네 경기 전부 `없는것` 이
       ['선발 최근 등판', '오늘 타순'] 이었고 확신이 4/4 `하` 로 깔렸다.
       그런데 오늘 타순·선발 예고는 **우리가 이미 10분마다 긁고 있었다.**
    ⚠️ 외부 호출 0. 값의 원본은 `crawler_feed` 와 `matchup.lineups_payload` 다.
    """
    from app.collectors import crawler_feed as CF
    from app.engine.matchup import lineups_payload

    sport = (jg.get("sport") or "").lower()
    out: list[dict] = []
    try:
        snap = await CF.load_snapshot(redis, sport, date)
        row = CF.snapshot_for_game(snap, jg)
    except Exception as exc:
        logger.warning("[gather] 크롤러 스냅샷 실패: %s", exc)
        row = {}

    lp = lineups_payload(jg) or {}
    state = jg.get("lineup_status") or "none"
    for side, label in (("away", "원정"), ("home", "홈")):
        blk = lp.get(side) or {}
        name = blk.get("선발투수") or row.get(f"{side}_pitcher") or "미정"
        out.append(_row(f"{label} 선발 예고 — {name}", src="라인업",
                        kind="공시"))
        order = blk.get("타순") or []
        if order:
            names = " · ".join(
                f"{o.get('순번', i + 1)}{o.get('이름') or o}"
                if isinstance(o, dict) else str(o)
                for i, o in enumerate(order))
            out.append(_row(f"{label} 오늘 타순 — {names}", src="라인업",
                            kind="공시"))
    if state != "confirmed":
        # 🔴 "타순 미확정"도 사실이다 — 잠정 카드가 왜 잠정인지를 ②가 알아야 한다.
        out.append(_row(f"오늘 타순 상태 — {state} (확정 전)", src="라인업",
                        kind="공시"))

    try:
        changes = await CF.load_changes(redis, sport, date)
        tl = CF.lineup_timeline(changes, jg)
    except Exception as exc:
        logger.warning("[gather] 크롤러 변화 이력 실패: %s", exc)
        tl = {}
    when = tl.get("lineup_announced_at")
    if when:
        out.append(_row(f"라인업 발표 시각 — {when}", src="라인업", kind="공시"))
    for line in (tl.get("lineup_changes") or []) + (tl.get("starter_changes") or []):
        out.append(_row(str(line), src="라인업", kind="공시"))
    return [r for r in out if len(r["답"]) < 400]


async def _bullpen(pool, jg: dict) -> list[dict]:
    """우리 기록. **질문을 기다리지 않는다** — 불펜은 매 경기 걸리는 축이다."""
    from app.collectors import bullpen_usage as BU

    sport = (jg.get("sport") or "").lower()
    out = []
    for side in ("away", "home"):
        team = jg.get(side) or ""
        if not team:
            continue
        text = BU.to_answer(team, await BU.recent(pool, sport, team))
        if text:
            out.append(_row(text, src="크롤러", kind="기록"))
    return out


async def enrich(jg: dict, redis, date: str) -> list[str]:
    """[ORD-16] 크롤러가 아는 **선발 이름**으로 `jg` 의 빈 칸을 메운다.

    🔴 왜. 실측 2026-09-12 13:14 운영 — 크롤러는 정상이었다(심장박동 13:14 ·
       KBO 4경기 · NPB 6경기, 선발 이름까지 전부 있음). 그런데 `games` 테이블은
       **선발 -/- 전부 NULL** 이었다. `games.home_pitcher` 를 쓰는 코드가
       KBO·NPB 에 없다(MLB 만 채운다). 크롤러 값은 `merge_into_research` 로
       research 에만 흘러가고, 그건 **프리페치가 돌아야** 찬다.
       그래서 `matchup.game_brief` 가 KBO/NPB 에서 늘 "미정" 을 냈다.

    ⚠️ **비어 있을 때만 채운다.** MLB 는 `games` 컬럼이 statsapi 예고 선발로
       이미 차 있다 — 크롤러로 덮으면 더 나쁜 값이 될 수 있다.
    ⚠️ 호출 순서가 계약이다: `collect` → `game_brief`. 반대로 부르면 종전처럼
       "미정" 이 나간다.
    """
    from app.collectors import crawler_feed as CF

    try:
        snap = await CF.load_snapshot(redis, (jg.get("sport") or "").lower(), date)
        row = CF.snapshot_for_game(snap, jg)
    except Exception as exc:
        logger.warning("[gather] 크롤러 스냅샷 실패 — 메우지 않는다: %s", exc)
        return []
    filled = []
    for side in ("home", "away"):
        if str(jg.get(f"{side}_pitcher") or "").strip():
            continue
        name = str(row.get(f"{side}_pitcher") or "").strip()
        if name:
            jg[f"{side}_pitcher"] = name
            filled.append(f"{side}={name}")
    if filled:
        # 🔴 어디서 온 값인지 안 남기면 "왜 선발이 바뀌었나"를 못 푼다.
        logger.info("[gather] 크롤러로 선발을 메웠다 %s@%s · %s",
                    jg.get("away"), jg.get("home"), " ".join(filled))
    return filled


async def collect(jg: dict, redis=None, date: str = "", *, pool=None) -> dict:
    """① 수집. 반환 `{"자료": [...], "출처": {...}}`.

    🔴 **0건이면 0건이라고 돌려준다.** 빈손을 숨기면 ②가 아는 척 거른다.
    ⚠️ 채널 하나가 터져도 나머지는 산다. 채널별 건수를 로그에 남긴다 —
       ORD-8 에서 배운 것이다(중간 수치가 없으면 "왜 0건인가"를 다시 물어야 한다).
    """
    # 🔴 [ORD-16] **먼저 메운다.** 이 뒤에 `game_brief` 를 부르면 선발이 보인다.
    await enrich(jg, redis, date)
    jobs = {"satellite": _satellite(jg, redis),
            "x": _x_news(jg, date, redis),
            "pplx": _preview(jg),
            # [ORD-14] 크롤러가 긁어 둔 오늘 선발·타순. 외부 호출 0.
            "라인업": _lineup(jg, redis, date),
            "크롤러": _bullpen(pool, jg)}
    got = await asyncio.gather(*jobs.values(), return_exceptions=True)
    rows: list[dict] = []
    src: dict = {}
    for name, g in zip(jobs, got):
        if isinstance(g, list):
            rows.extend(g)
            if g:
                src[name] = len(g)
        else:
            logger.warning("[gather] %s 실패 — 나머지로 계속한다: %s", name, g)
    logger.info("[gather] %s@%s 수집 %d건 %s",
                jg.get("away"), jg.get("home"), len(rows), src)
    return {"자료": rows, "출처": src}
