"""🔴🔴 **쌓아 둔 경기에서 찾기** — 이름표 사다리 ②단이 쓴다(`app/resolve.py`).

══════════════════════════════════════════════════════════════════
🔴 **슬레이트 명령·렌더러는 지웠다** — 사용자 지시 2026-10-06 ⑧
══════════════════════════════════════════════════════════════════

> 삭제: 스케줄러·채점·슬레이트 코드 삭제 → `analyze.py` 삭제.

⚠️ 그런데 이 파일에는 **두 가지**가 섞여 있었다: ① `/slate` 명령이 쓰던 렌더러
   (`render`·`SPORT_KO`)와 ② **경기 조회**(`find`·`by_key`·`window`). 🔴 ②는
   v6 의 입구(s1 → `resolve.match_of`)가 쓴다 — 지우면 *"쌓인 경기에 있나"* 단이
   사라진다. 그래서 **①만 지우고 ②를 남겼다.**
🔴 남은 것은 **DB 조회**뿐이고 사람이 읽는 꼴을 만들지 않는다(그것은 `render.py`).
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from app import timefmt
logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))
#: 🔴 사유 문장이 쓰는 종목 이름 — ⚠️ 이것은 **렌더러가 아니다**(사유를 사람이 읽게
#   적는 자리다 · 조용한 0 금지). `/slate` 명령의 꼴은 지웠다.
SPORT_KO = {"baseball": "야구", "soccer": "축구", "hockey": "하키",
            "basketball": "농구", "volleyball": "배구"}


@dataclass
class Found:
    """조회 결과. 🔴 **못 찾은 이유까지** 들고 온다."""

    games: list[dict] = field(default_factory=list)
    #: 🔴 왜 비었나 — `"아직 안 쌓였다"` 와 `"그 날짜에 경기가 없다"` 는 다르다
    #  ⚠️ 이것은 **곁들이는 설명**이다. 무엇이 막았나는 아래 `reason` 이 정한다.
    why: str = ""
    #: 🔴🔴 **실패한 조건이 직접 넣는다**(4단계). 사람이 고르지 않는다.
    reason: object = None
    #: 🔴 어느 날짜·종목까지 **쌓여 있나**(창 밖 질문을 구분하려면 이것이 필요하다)
    stored_days: list[str] = field(default_factory=list)
    stored_sports: list[str] = field(default_factory=list)
_WHERE_DAYS = (f" WHERE {timefmt.sql_kst_day()} >= $1::date\n"
               f"   AND {timefmt.sql_kst_day()}"
               f"       < $1::date + ($2 || ' days')::interval\n")
_BASE = """
SELECT id, sport, league, home, away, venue, starts_kst, status,
       -- 🔴 `ext_id` 가 **공식 API 깊이의 열쇠다**(`sources_context`). 빠뜨리면
       --    질문 경로가 검색 운에만 매달린다(실측 2026-10-02 라이브 2회: 변수 0건).
       ext_id,
       home_score, away_score, round_note
  FROM games
""" + _WHERE_DAYS
async def window(pool, *, day: date | None = None, days: int = 2) -> Found:
    """쌓인 창 전체. 🔴 **무엇이 쌓였는지**를 먼저 답한다."""
    day = day or datetime.now(KST).date()
    rows = await pool.fetch(_BASE + " ORDER BY starts_kst, league, home",
                            day, str(days))
    got = Found(games=[dict(r) for r in rows])
    got.stored_days = sorted({str(r["starts_kst"].astimezone(KST).date())
                              for r in rows})
    got.stored_sports = sorted({r["sport"] for r in rows})
    if not rows:
        from app.matchref import Reason as _R
        got.reason = _R.NOT_COLLECTED
        got.why = (f"{day} 부터 {days}일치가 **아직 안 쌓였다** — 스케줄러가 한 "
                   f"번도 안 돌았거나 수집이 실패했다")
    return got
async def by_key(pool, key: str) -> Found:
    """🔴🔴 **열쇠로 바로 찾는다**(3단계 · 사용자 설계 2026-10-03).

    > `slate.find(match_key)` … 함수 인자에 팀 이름 문자열이 없다.

    ⚠️ 이름으로 찾으면 **저장한 언어와 조회 언어가 갈릴 수 있다** — 실측
       2026-10-03: 봇이 `Croatia` 로 적어 놓고 `크로아티아` 로 되찾아 실패했고,
       그 사유를 *"창 밖"* 이라고 **거짓으로** 적었다.
    🔴 `games.ext_id` 는 **언어가 없다.** 그래서 그 병이 구조적으로 불가능하다.
    ⚠️ 날짜 창도 **안 본다** — 열쇠는 그 경기 하나를 가리키므로 거를 것이 없다.
    """
    got = Found()
    if not str(key or "").strip():
        from app.matchref import Reason as _R
        got.reason = _R.NO_QUERY
        got.why = "열쇠가 비었다"
        return got
    # 🔴 **날짜 조건만 열쇠 조건으로 갈아 끼운다** — 🔴 갈아 끼울 글자를 손으로
    #    적지 않는다(`_WHERE_DAYS` 가 그 글자의 원본이다). ⚠️ 적어 두면 조각이
    #    바뀔 때 `replace` 가 **조용히 아무것도 안 바꾸고** 날짜 창이 살아남는다.
    rows = await pool.fetch(
        _BASE.replace(_WHERE_DAYS, " WHERE ext_id = $1\n")
        + " ORDER BY starts_utc", key)
    got.games = [dict(r) for r in rows]
    if not got.games:
        from app.matchref import Reason as _R
        got.reason = _R.MATCH_NOT_FOUND
        got.why = f"`{key}` 로 적힌 경기가 표에 없다"
    return got
async def find(pool, *, team: str | None = None, sport: str | None = None,
               league: str | None = None, day: date | None = None,
               days: int = 2, opponent: str | None = None) -> Found:
    """팀·종목·리그로 찾는다. 🔴 **팀 이름은 부분 일치**로 본다.

    ⚠️ 🔴 **열쇠를 알면 `by_key` 를 쓴다**(3단계) — 이름 조회는 *"사용자가 처음
       물었을 때"* 만이다. 한 번 찾은 뒤에는 열쇠로 다닌다.

    ⚠️ 기사는 약칭을 쓰고 표에는 정식명이 들어 있다(`Colorado Avalanche` ↔
       `콜로라도`). 정확히 맞추라고 하면 사용자가 못 찾는다 — 그래서 부분 일치다.
    🔴 그러나 **여러 경기가 맞으면 전부 돌려준다** — 하나를 골라 주지 않는다.
       고르는 것은 사용자 몫이고, 잘못 고르면 남의 경기를 분석한다(§17-g-3 · M14).
    """
    day = day or datetime.now(KST).date()
    sql = _BASE
    args: list = [day, str(days)]
    if team:
        args.append(f"%{team.strip()}%")
        sql += f" AND (home ILIKE ${len(args)} OR away ILIKE ${len(args)})"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **상대도 조건이다** (실측 2026-10-02)
    # ══════════════════════════════════════════════════════════════════
    #
    #  사용자가 *"중국 vs 팔레스타인"* 을 물었는데 봇이 **아시안게임 `China W`**
    #  경기(한국 vs 중국 여자)를 분석했다. `China` 부분 일치가 그것을 잡았고,
    #  한 건이 맞았으니 *"찾았다"* 로 끝났다 — 🔴 **남의 경기다**(§17-g-3 · M14:
    #  남의 경기를 분석하면 그 카드는 통째로 거짓이다).
    #
    #  🔴 상대를 알면 **양 팀이 다 들어야** 그 경기다. 상대를 모르면 종전대로 돈다.
    if opponent and str(opponent).strip():
        args.append(f"%{str(opponent).strip()}%")
        sql += f" AND (home ILIKE ${len(args)} OR away ILIKE ${len(args)})"
    if sport:
        args.append(sport)
        sql += f" AND sport = ${len(args)}"
    if league:
        args.append(f"%{league.strip()}%")
        sql += f" AND league ILIKE ${len(args)}"
    rows = await pool.fetch(sql + " ORDER BY starts_kst, league, home", *args)

    got = Found(games=[dict(r) for r in rows])
    if rows:
        return got

    # 🔴 **왜 비었나를 가른다** — 창이 비었나, 질문이 안 맞았나
    whole = await window(pool, day=day, days=days)
    got.stored_days, got.stored_sports = whole.stored_days, whole.stored_sports
    if not whole.games:
        # 🔴 **분류도 함께 넘긴다**(4단계). 문장만 넘기면 *"아직 안 쌓였다"* 가
        #    여기서 **그냥 못 찾았다**로 바뀌어, 처방이 뒤집힌다(스케줄러를
        #    돌려야 하는데 사용자에게 다시 물으라고 하게 된다).
        got.why, got.reason = whole.why, whole.reason
        return got
    bits = []
    if team:
        bits.append(f"`{team}` 이 든 경기")
    if opponent:
        bits.append(f"상대 `{opponent}`")
    if sport:
        bits.append(f"종목 {SPORT_KO.get(sport, sport)}")
    if league:
        bits.append(f"리그 `{league}`")
    from app.matchref import Reason as _R2
    got.reason = _R2.MATCH_NOT_FOUND
    got.why = (f"창에는 {len(whole.games)}경기가 쌓여 있는데 "
               f"{' · '.join(bits) or '조건'}에 맞는 것이 없다 "
               f"(쌓인 종목: {', '.join(SPORT_KO.get(s, s) for s in whole.stored_sports)})")
    return got
