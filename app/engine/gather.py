"""[ORD-10 · 1단계] **질문 없이 경기 것만 긁는다.**

사용자 지시 2026-09-12: "갈림길 변수등을 서치로 지정하지 않고 경기에 대한
것만 서치해 온다...그후 ai에게 정보를 준다.ai가 거른다"

🔴 왜 순서를 또 바꾸나 — 질문에 매인 수집이 세 가지로 새고 있었다(실측 09-12):
     · 퍼플렉시티 경기당 최대 4콜 → **429 발생**
     · X 는 질답을 강요당해 같은 프롬프트 5회에 답 `[0,0,1,0,1]`

🔴 [SRCH-1 2026-09-12] **X 채널을 지웠다**(사용자 지시 "x seach 삭제").
   실측: 호출당 $0.413 · 본문 수율 0. 그 자리는 Anthropic 웹 검색이 받는다.

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
        data = await BU.recent(pool, sport, team)
        # 🔴 [SRCH-8] **읽은 것을 버리지 않는다.** 종전에는 문장으로만 쓰고
        #    끝냈고, `bullpen_payload` 는 `research` 를 보므로 4단계 DB가
        #    영영 `없음` 이었다(실측 2026-09-12). 같은 사실이 두 갈래로
        #    갈라져 있던 것이다.
        #    ⚠️ `era` 는 스탯 수집기가 채운다 — `setdefault` 로 덮지 않는다.
        #    ⚠️ 기록이 없으면 칸을 만들지 않는다 — 빈 칸은 `bundle` 이
        #       "있음"으로 세고, 그러면 모르는 것이 아는 것이 된다.
        if data.get("투수"):
            blk = (jg.setdefault("research", {})
                     .setdefault(f"{side}_bullpen", {}))
            blk.setdefault("최근", data)
        text = BU.to_answer(team, data)
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
    # 🔴 [SRCH-8] **타순도 메운다.** `lineups_payload` 에는 이 칸을 읽는
    #    폴백이 **이미 있었다**(`jg["lineup_{side}"]`). 그런데 아무도 안 채워서
    #    영영 안 걸렸다 — 실측 2026-09-12: 4단계 DB가 `오늘 타순` 을 "있음"으로
    #    세면서도 `타순: null` 이었고, 수집 행에도 타순 줄이 없었다.
    #    크롤러는 그 값을 10분마다 긁고 있었다.
    #    ⚠️ 파싱은 `lineup_diff.parse_order` 가 원본이다 — 여기서 자르지 않는다.
    #    ⚠️ **비어 있을 때만.** 기존 값을 덮으면 그게 더 나쁘다(선발과 같은 규약).
    for side in ("home", "away"):
        key = f"lineup_{side}"
        if str(jg.get(key) or "").strip():
            continue
        raw = str(row.get(key) or "").strip()
        if raw:
            jg[key] = raw
            filled.append(f"{key}={raw[:18]}…")
    if filled:
        # 🔴 어디서 온 값인지 안 남기면 "왜 선발이 바뀌었나"를 못 푼다.
        logger.info("[gather] 크롤러로 메웠다 %s@%s · %s",
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
    # 🔴 [ORD-21 · SRCH-1] **여기서는 유료 검색을 하지 않는다.**
    #    "퍼플릭스와 x seach는 안트로픽 api키가 요청을 할때만 켜는걸로 하자."
    #    실측 2026-09-12: 위성·크롤러만으로도 갈림길이 나왔다
    #    ("문보경이 지명타자로 복귀해…"). 못 가리겠을 때만 검색한다.
    #    ⚠️ `_preview`(퍼플렉시티)는 지우지 않는다 — ②선별이 "없는 것"을
    #       지목했을 때 SRCH-3 이 부른다. X 는 지웠다(SRCH-1).
    jobs = {"satellite": _satellite(jg, redis),
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


async def _pplx_ask(jg: dict, asks: list[str], date: str) -> list[dict]:
    """[SRCH-4] 퍼플렉시티에 **같은 질문**을 던지고 **같은 문**을 지나게 한다.

    🔴 게이트를 새로 만들지 않는다 — `websearch.gate_rows` 를 부른다.
       두 벌이면 한쪽만 고쳐지고, 그게 이 저장소의 사본 드리프트다.
    ⚠️ 질문 프롬프트와 스위치는 `deepsearch._ask_pplx` 가 원본이다. 그쪽
       동작을 바꾸지 않는다 — 반환값에 게이트를 걸 뿐이다(ORDER_V2 의
       `reinforce` 도 같은 함수를 쓴다).
    ⚠️ `DEEPSEARCH_PPLX_ENABLED` 가 꺼져 있으면 `_ask_pplx` 가 빈손을
       돌려준다. 운영은 지금 **0** 이다 — 붙였다고 도는 것이 아니다.
    """
    from app.collectors.websearch import gate_rows
    from app.engine.deepsearch import _ask_pplx

    rows = await _ask_pplx(jg, asks)
    if not rows:
        return []
    kept, m = gate_rows(rows, date)
    if m["폐기"]:
        logger.info("[search] pplx 날짜 게이트 — 받음 %d · 채택 %d · 폐기 %d "
                    "(오래됨 %d · 날짜없음 %d · 미래 %d)",
                    m["받음"], m["채택"], m["폐기"], m["폐기_오래됨"],
                    m["폐기_날짜없음"], m["폐기_미래"])
    return kept


async def search(jg: dict, asks: list[str], date: str) -> dict:
    """[SRCH-3] **요청받은 질문만** 검색한다. 반환 `{"자료","출처"}`.

    사용자 지시 2026-09-12: "퍼플릭스와 안트로픽" ·
    "안트로픽 api키가 요청을 할때만 켜는걸로 하자" · "경기당 1회 질문 3개로 해라"

    🔴 **`collect` 와 다른 지갑이다.** 수집은 무료(위성·크롤러)이고 이쪽은
       유료다 — 경기당 약 $0.10 (실측 2026-09-12: $0.079~0.139).
       그래서 요청이 없으면 **한 채널도 부르지 않는다.**
    🔴 **채널 하나가 터져도 나머지는 산다.** 검색 실패로 판정을 멈추지 않는다.
    ⚠️ 스위치는 각 채널이 본다(`websearch._enabled`). 여기서 다시 보지 않는다 —
       두 곳에서 보면 그게 사본이고, 한쪽만 바뀐다.
    ⚠️ 퍼플렉시티는 SRCH-4 가 **같은 날짜 게이트를 붙여** 이 `jobs` 에 더한다.
       게이트 없이 붙이면 SRCH-2 가 막은 결함(5개월 전 기사)을 다시 연다.
    """
    from app.collectors import websearch

    qs = [str(q).strip() for q in (asks or []) if str(q).strip()]
    if not qs:
        return {"자료": [], "출처": {}}

    jobs = {websearch.SOURCE: websearch.ask(jg, qs, today=date),
            "pplx": _pplx_ask(jg, qs, date)}
    got = await asyncio.gather(*jobs.values(), return_exceptions=True)
    rows: list[dict] = []
    src: dict = {}
    for name, g in zip(jobs, got):
        if isinstance(g, list):
            rows.extend(g)
            if g:
                src[name] = len(g)
        else:
            logger.warning("[search] %s 실패 — 나머지로 계속한다: %s", name, g)
    logger.info("[search] %s@%s 질문 %d → %d건 %s",
                jg.get("away"), jg.get("home"), len(qs), len(rows), src)
    return {"자료": rows, "출처": src}
