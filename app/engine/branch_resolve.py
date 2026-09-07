"""[자료14] 판정이 지목한 **분기점**을 유형별로 갈라 답한다.

🔴 왜 (실측 2026-09-07, deepsearch 기록 6건 전수):
   판정이 `추가확인` 에 적은 것이 6건 모두 **미확인**으로 돌아왔다.
     "Wrobleski 오늘 예정 투구수 한도"   → 퍼플렉시티 → 미확인
     "허드슨 뒤 이닝 소화 계획"          → 퍼플렉시티 → 미확인
     "아리게티 투구 계획"                → 퍼플렉시티 → 미확인
     "금일 선발·라인업"                  → 퍼플렉시티 → 미확인
   전부 **기록으로 답할 질문을 뉴스 검색기에 보낸 것**이었다.
   `deepsearch` 는 `_free_articles`→`_fetch_body`→`_inject_articles` 구조라
   기사만 읽는다. "그 투수가 5이닝을 넘기는가"에 답하는 기사는 없다.

   같은 질문을 우리 DB 에 물었더니 즉시 답이 나왔다 (실측 Wrobleski):
     ① 본인      08-15 선발 6.0이닝(상대타자 24) · 09-02 구원 2.0이닝
     ② 소속팀    다저스 최근 30일 선발 22건 · **5이닝 이상 20/22 (91%)**
     ③ 같은 처지 리그 '직전 선발 1건뿐' 투수 232건 · **5이닝 이상 52%**
   표본 232건짜리 답이 있는데 판정에 가지 않았다.

⚠️ **새 크롤 소스를 만들지 않는다.** 전부 `pitcher_appearances`·`games` 재사용이다.
⚠️ **%p 를 만들지 않는다.** 여기서 만드는 것은 사실이다 — 그 사실을 확률로
   옮기는 것은 판정의 일이다(평의회와 같은 규약).
⚠️ 답이 없으면 **없다고 적는다.** 빈 칸을 만들지 않고, 지어내지 않는다.
   "모른다"는 것도 판정에 필요한 정보다 — 확신도를 낮출 근거가 된다.
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

RECORD, NEWS, LIVE, UNKNOWN = "기록형", "뉴스형", "실시간형", "미분류"

#: 유형 분류 키워드. **순서가 곧 우선순위다** — 기록형을 먼저 본다.
#  실측 6건이 전부 기록형이었는데 뉴스 검색기로 갔다.
#  ⚠️ `투구수` 만 잡으면 실측 사례 "아리게티 **투구 계획**" 을 놓친다.
#     `투구`·`등판`·`계획` 을 함께 본다 — 실제로 온 문장으로 폭을 정한다.
_RECORD_PAT = (
    r"이닝|소화|투구|워크로드|롱릴리프|연투|등판|"
    r"오프너|벌크|피로|가용|타순|득점력|최근\s*폼|"
    # [2026-09-07] 변수에서 오는 타선 질문 — "배율 0.46이 일시적 침체인가"
    r"타선|득점|배율|침체|반등|부진|"
    # [2026-09-07 ②] 종전에는 `불펜\s*소모` 라서 "홈 불펜이 조기 가동되는가" 가
    #   **미분류**로 빠졌다. 실측상 불펜은 기록형 질문의 42.9% 로 최다다.
    #   `연전` 도 없었다 — `연투` 만 있어서 "연전 4일차 피로" 가 다른 낱말
    #   (피로) 덕에 우연히 걸리고 있었다.
    #   ⚠️ 반대 위험(뉴스형을 빼앗음)을 실변수 638건으로 측정했다 → 아래 주석
    r"불펜|구원|필승조|연전"
)
_NEWS_PAT = r"부상|결장|IL|로스터|트레이드|영입|방출|감독|징계|날씨|우천|비"
#  🔴 "구단 발표"·"제한 여부" 는 **기록형보다 먼저** 본다. 실측 2026-09-07:
#     opus 가 자료14 로 리그 표본을 받고도 `추가확인` 에 "투구수·이닝 제한
#     여부(구단 발표)" 를 다시 적었다. 기록형으로 잡으면 같은 답을 또 붙여
#     중복이 되고, 정작 물은 **오늘의 사실**은 끝내 안 간다.
_LIVE_PAT = (r"구단\s*발표|발표\s*여부|제한\s*여부|오늘\s*라인업|금일\s*라인업|"
             r"선발\s*발표|공시|당일\s*발표|가용\s*여부|출전\s*여부")


def classify(question: str) -> str:
    """분기점 질문 → 해결사 유형. 못 가리면 `미분류`.

    🔴 기록형을 **먼저** 본다. "오늘 예정 투구수 한도" 처럼 두 유형이 겹치는
       문장이 실측 6건의 다수였고, 그때 뉴스로 보내면 미확인이 된다.
       투구수는 기사에 없지만 등판 기록에는 있다.
    """
    q = (question or "").strip()
    if not q:
        return UNKNOWN
    if re.search(_LIVE_PAT, q):
        return LIVE
    if re.search(_RECORD_PAT, q):
        return RECORD
    if re.search(_NEWS_PAT, q):
        return NEWS
    return UNKNOWN


# ── 기록형 해결사 ①: 본인 등판
_OWN = """
    SELECT g.starts_at::date AS d, a.is_starter, a.innings, a.batters, a.r
      FROM pitcher_appearances a JOIN games g ON g.id = a.game_id
     WHERE g.sport = $1 AND a.pitcher = $2 AND g.status = 'final'
       AND g.starts_at < $3
     ORDER BY g.starts_at DESC LIMIT $4
"""

# ── 기록형 해결사 ②: 소속팀 선발이 요즘 몇 이닝 가는가
_TEAM = """
    SELECT count(*) AS n, avg(a.innings) AS ip, avg(a.batters) AS tbf,
           count(*) FILTER (WHERE a.innings >= $5) AS deep
      FROM pitcher_appearances a JOIN games g ON g.id = a.game_id
     WHERE g.sport = $1 AND a.is_starter AND a.team = $2
       AND g.status = 'final' AND a.innings > 0
       AND g.starts_at < $3
       AND g.starts_at >= $3 - make_interval(days => $4)
"""

# ── 기록형 해결사 ③: 리그에서 '같은 처지'(선발 표본이 얇은) 투수의 다음 등판
#    🔴 이것이 이 모듈의 값이다. 본인 표본이 2건이어도 리그가 232건을 준다.
_PEERS = """
    WITH s AS (
      SELECT a.pitcher, g.starts_at, a.innings,
             count(*) FILTER (WHERE a.is_starter) OVER (
               PARTITION BY a.pitcher ORDER BY g.starts_at
               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prev_starts
        FROM pitcher_appearances a JOIN games g ON g.id = a.game_id
       WHERE g.sport = $1 AND g.status = 'final' AND a.innings > 0
         AND g.starts_at < $2
    )
    SELECT count(*) AS n, avg(innings) AS ip,
           count(*) FILTER (WHERE innings >= $4) AS deep
      FROM s WHERE prev_starts = $3
"""


def _cfg():
    from app.config import get_settings

    return get_settings()


async def innings_outlook(pool, sport: str, pitcher: str, team: str,
                          before) -> dict:
    """"그 선발이 몇 이닝 가는가" 에 세 갈래로 답한다. 못 내면 빈 dict.

    ⚠️ 세 갈래를 **곱하지 않는다.** 자료13 이 무너진 자리가 그것이다
       (표본 1~3 짜리 비율의 곱 → 예측 sd 5.25 vs 실제 3.82).
       여기서는 나란히 놓고 판정이 읽게 한다.
    """
    if pool is None or not sport or not pitcher or before is None:
        return {}
    s = _cfg()
    deep = float(s.branch_deep_innings)
    out: dict = {"질문": f"{pitcher} 가 {deep:g}이닝을 넘기는가"}
    try:
        rows = await pool.fetch(_OWN, sport, pitcher, before,
                                int(s.var_ref_appearances))
    except Exception as exc:
        logger.warning("[branch] %s 본인 등판 조회 실패: %s", pitcher, exc)
        rows = []
    starts = [r for r in rows if r["is_starter"]]
    if rows:
        out["본인"] = {
            "등판": [{"날짜": str(r["d"]),
                      "역할": "선발" if r["is_starter"] else "구원",
                      "이닝": float(r["innings"] or 0),
                      "상대타자": r["batters"], "실점": r["r"]} for r in rows],
            "선발수": len(starts)}
    try:
        r = await pool.fetchrow(_TEAM, sport, team, before,
                                int(s.branch_team_days), deep)
    except Exception as exc:
        logger.warning("[branch] %s 팀 선발 조회 실패: %s", team, exc)
        r = None
    if r and int(r["n"] or 0) >= int(s.branch_min_n):
        n = int(r["n"])
        out["소속팀"] = {"창": f"최근 {s.branch_team_days}일", "표본": n,
                         "평균이닝": round(float(r["ip"] or 0), 2),
                         "평균상대타자": round(float(r["tbf"] or 0), 1),
                         f"{deep:g}이닝이상": f"{int(r['deep'])}/{n} "
                                              f"({int(r['deep']) / n * 100:.0f}%)"}
    # 🔴 같은 처지 — 본인 선발 표본 수를 그대로 조건으로 건다.
    try:
        r = await pool.fetchrow(_PEERS, sport, before, len(starts), deep)
    except Exception as exc:
        logger.warning("[branch] 리그 동류 조회 실패: %s", exc)
        r = None
    if r and int(r["n"] or 0) >= int(s.branch_min_n):
        n = int(r["n"])
        out["같은처지"] = {"조건": f"직전까지 선발 등판 {len(starts)}건인 투수",
                           "표본": n, "평균이닝": round(float(r["ip"] or 0), 2),
                           f"{deep:g}이닝이상": f"{int(r['deep'])}/{n} "
                                                f"({int(r['deep']) / n * 100:.0f}%)"}
    return out if len(out) > 1 else {}


_LINEUP = """
    SELECT lineup_status,
           round(extract(epoch FROM (starts_at - lineup_confirmed_at)) / 60) AS lead_min
      FROM games WHERE id = $1
"""

#: 결장 문구에서 투수 자원을 가려낸다. `absences` 는 문장 리스트다
#  (`app/collectors/absences.py` 가 만든다) — 형식을 여기 다시 쓰지 않는다.
_PITCHER_HINT = ("선발", "투수", "불펜")


async def live_status(pool, jg: dict, pitcher: str | None) -> dict:
    """**오늘의 사실**로 답한다 — 라인업 공시·IL 명단. 새 API 를 부르지 않는다.

    🔴 실측 2026-09-07 WSH@LAD: `research.absences` 에 다저스 **선발 자원
       5명 이상**(Casparius IL-60 · Díaz IL-15 · Klein IL-60 · Lauer IL-15 ·
       Sasaki)이 들어 있었다. Wrobleski 가 선발로 나오는 이유이자 불펜이
       피로한 이유인데, 판정에는 "결장자 목록"으로만 갔지 **분기점의 답**
       으로는 가지 않았다.

    ⚠️ 모르는 것은 `미확인` 에 적는다. 구단이 공개하지 않는 것(투구수 한도)은
       조회로 나오지 않는다 — "없다"를 "정상"으로 읽게 두지 않는다.
    """
    out: dict = {}
    gid = jg.get("game_id")
    if pool is not None and gid:
        try:
            r = await pool.fetchrow(_LINEUP, gid)
        except Exception as exc:
            logger.warning("[branch] 라인업 상태 조회 실패 game=%s: %s", gid, exc)
            r = None
        if r:
            st = r["lead_min"]
            out["라인업"] = {"상태": r["lineup_status"],
                             "확정_T마이너스분": int(st) if st is not None else None}
    res = jg.get("research") or {}
    lines = [x for x in (res.get("absences") or []) if isinstance(x, str)]
    if lines:
        out["결장_출처"] = res.get("absence_basis") or "미상"
        for side in ("home", "away"):
            team = jg.get(side) or ""
            mine = [x for x in lines if team and x.startswith(team)]
            if not mine:
                continue
            arms = [x for x in mine if any(h in x for h in _PITCHER_HINT)]
            out.setdefault("결장", {})[side] = {
                "총": len(mine), "투수자원": len(arms),
                "명단": mine[:6]}
    if pitcher:
        hit = [x for x in lines if pitcher in x]
        out["대상투수_결장명단"] = hit or "없음(IL 명단에 없다)"
    out["미확인"] = ["투구수 한도·이닝 제한은 구단이 공개하지 않는다 — "
                     "조회로 나오지 않는 값이다"]
    return out


# ── 기록형 해결사 ④: 최근 타선이 눌린 팀은 다음 경기에 어떻게 됐나
#    🔴 변수에서 오는 질문이다. 실측 2026-09-07 NYY@SD 변수2 —
#       "홈 타선 배율 0.46이 표본 3의 일시적 침체일 가능성 … 근거 없음".
#       아무도 조사하지 않아 판정이 "보수 반영" 으로 넘어갔다.
_OFFENSE_PEERS = """
    WITH g AS (
      SELECT id, starts_at, home AS team,
             home_score AS runs, away_score AS allowed FROM games
       WHERE sport = $1 AND status = 'final' AND home_score IS NOT NULL
         AND starts_at < $2
      UNION ALL
      SELECT id, starts_at, away, away_score, home_score FROM games
       WHERE sport = $1 AND status = 'final' AND home_score IS NOT NULL
         AND starts_at < $2
    ), w AS (
      SELECT team, starts_at, runs,
             avg(runs) OVER (PARTITION BY team ORDER BY starts_at
                             ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS prev3,
             count(*) OVER (PARTITION BY team ORDER BY starts_at
                            ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS n3
        FROM g
    )
    SELECT count(*) AS n, avg(runs) AS next_runs
      FROM w WHERE n3 = 3 AND prev3 <= $3
"""


async def offense_outlook(pool, sport: str, team: str, before,
                          recent_rpg: float | None) -> dict:
    """최근 3경기 득점이 눌린 팀의 **다음 경기** 득점. 못 내면 빈 dict.

    ⚠️ 배율이 아니라 **경기당 득점**으로 건다 — 배율은 상대 실점률까지
       엮여 있어 리그 표본을 만들 조건으로 쓰면 표본이 잘게 쪼개진다.
    ⚠️ 리그 평균과 **나란히** 낸다. 회귀 폭을 우리가 계산해 주지 않는다 —
       그건 판정의 일이다.
    """
    if pool is None or not sport or before is None or recent_rpg is None:
        return {}
    s = _cfg()
    try:
        peer = await pool.fetchrow(_OFFENSE_PEERS, sport, before,
                                   float(recent_rpg))
        base = await pool.fetchrow(
            """SELECT avg(v) AS rpg FROM (
                 SELECT home_score AS v FROM games
                  WHERE sport = $1 AND status='final' AND home_score IS NOT NULL
                    AND starts_at < $2
                 UNION ALL
                 SELECT away_score FROM games
                  WHERE sport = $1 AND status='final' AND home_score IS NOT NULL
                    AND starts_at < $2) t""", sport, before)
    except Exception as exc:
        logger.warning("[branch] %s 타선 회귀 조회 실패: %s", team, exc)
        return {}
    n = int((peer or {}).get("n") or 0)
    if n < int(s.branch_min_n) or not base:
        return {}
    return {"질문": f"{team} 최근 3경기 경기당 {recent_rpg:.2f}득점이 "
                    f"다음 경기에 반등하는가",
            "조건": f"직전 3경기 경기당 {recent_rpg:.2f}득점 이하였던 팀",
            "표본": n,
            "다음경기_평균득점": round(float(peer["next_runs"] or 0), 2),
            "리그_경기당득점": round(float(base["rpg"] or 0), 2)}


# ── 기록형 해결사 ④: 불펜이 얼마나 닳았나
#
# 🔴 실측 2026-09-07: 기록형 변수 501건 중 **불펜 274건(42.9%)** 이 최다인데
#    해결사가 없었다. "불펜 조기 가동", "불펜 소모로 체력 저하" 같은 질문이
#    전부 `사유: 대상 선발을 특정하지 못했다` 로 끝났다.
_BULLPEN_OWN = """
    SELECT g.starts_at::date AS d,
           count(*) FILTER (WHERE NOT a.is_starter)      AS arms,
           coalesce(sum(a.innings) FILTER (WHERE NOT a.is_starter), 0) AS ip
      FROM pitcher_appearances a JOIN games g ON g.id = a.game_id
     WHERE g.sport = $1 AND a.team = $2 AND g.status = 'final'
       AND g.starts_at < $3
     GROUP BY g.id, g.starts_at
     ORDER BY g.starts_at DESC LIMIT $4
"""
# 같은처지 = 직전 N경기 구원 이닝 합이 비슷했던 팀들의 **다음 경기** 구원 실점.
_BULLPEN_PEERS = """
    WITH per AS (
      SELECT g.id, g.starts_at, a.team,
             coalesce(sum(a.innings) FILTER (WHERE NOT a.is_starter), 0) AS ip,
             coalesce(sum(a.r)       FILTER (WHERE NOT a.is_starter), 0) AS r
        FROM pitcher_appearances a JOIN games g ON g.id = a.game_id
       WHERE g.sport = $1 AND g.status = 'final' AND g.starts_at < $2
       GROUP BY g.id, g.starts_at, a.team
    ), w AS (
      SELECT team, starts_at, r, ip,
             sum(ip) OVER (PARTITION BY team ORDER BY starts_at
                           ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS prev_ip,
             count(*) OVER (PARTITION BY team ORDER BY starts_at
                            ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS n3
        FROM per
    )
    SELECT count(*) AS n, avg(r) AS next_r, avg(ip) AS next_ip
      FROM w WHERE n3 = 3 AND prev_ip >= $3
"""


async def bullpen_outlook(pool, sport: str, team: str, before) -> dict:
    """최근 3경기 불펜 소모 → 같은처지 팀의 다음 경기 구원 실점. 못 내면 `{}`.

    ⚠️ "지쳤다/괜찮다"를 우리가 판단하지 않는다. 소모량과 같은처지 실적을
       **나란히** 낼 뿐이다 — 판단은 판정의 일이다.
    """
    if pool is None or not sport or not team or before is None:
        return {}
    s = _cfg()
    try:
        own = await pool.fetch(_BULLPEN_OWN, sport, team, before, 3)
        if not own:
            return {}
        used_ip = sum(float(r["ip"] or 0) for r in own)
        peer = await pool.fetchrow(_BULLPEN_PEERS, sport, before, used_ip)
    except Exception as exc:
        logger.warning("[branch] %s 불펜 소모 조회 실패: %s", team, exc)
        return {}
    n = int((peer or {}).get("n") or 0)
    if n < int(s.branch_min_n):
        return {}
    return {"질문": f"{team} 불펜이 최근 3경기 소모로 흔들리는가",
            "최근3경기": [{"날짜": str(r["d"]), "투입": int(r["arms"] or 0),
                          "이닝": round(float(r["ip"] or 0), 1)} for r in own],
            "소모_구원이닝": round(used_ip, 1),
            "같은처지": {"조건": f"직전 3경기 구원 {used_ip:.1f}이닝 이상 던진 팀",
                        "표본": n,
                        "다음경기_구원실점": round(float(peer["next_r"] or 0), 2),
                        "다음경기_구원이닝": round(float(peer["next_ip"] or 0), 1)}}


# ── 기록형 해결사 ⑤: 연전 몇 일차인가, 그때 어떻게 됐나
#
# 🔴 실측 2026-09-07: 연전 68건(10.7%). "연전 4일차 away 피로" 가 `기록형` 으로
#    분류되고도 답이 **빈 dict** 로 나갔다 — 분류는 맞는데 풀 사람이 없었다.
_SERIES_DAYS = """
    SELECT g.starts_at::date AS d FROM games g
     WHERE g.sport = $1 AND ($2 = g.home OR $2 = g.away)
       AND g.status = 'final' AND g.starts_at < $3
     ORDER BY g.starts_at DESC LIMIT 12
"""
_SERIES_PEERS = """
    WITH g AS (
      SELECT id, starts_at, home AS team, home_score AS runs,
             away_score AS allowed FROM games
       WHERE sport = $1 AND status='final' AND home_score IS NOT NULL
         AND starts_at < $2
      UNION ALL
      SELECT id, starts_at, away, away_score, home_score FROM games
       WHERE sport = $1 AND status='final' AND home_score IS NOT NULL
         AND starts_at < $2
    ), w AS (
      SELECT team, starts_at::date AS d, runs, allowed,
             lag(starts_at::date, $3) OVER (PARTITION BY team
                                            ORDER BY starts_at) AS back
        FROM g
    )
    SELECT count(*) AS n, avg(runs) AS runs, avg(allowed) AS allowed
      FROM w WHERE back IS NOT NULL AND d - back = $3
"""


def consecutive_days(dates: list, today) -> int:
    """오늘이 연전 몇 일차인가. 오늘 포함, 하루라도 비면 끊긴다.

    ⚠️ 날짜만 본다 — 더블헤더로 같은 날 두 경기면 하루로 센다.
    """
    from datetime import timedelta

    seen = sorted({d for d in dates if d is not None}, reverse=True)
    day, n = today, 1
    for d in seen:
        if d == day:
            continue
        if d == day - timedelta(days=1):
            n += 1
            day = d
            continue
        break
    return n


async def series_outlook(pool, sport: str, team: str, before) -> dict:
    """연전 N일차 판별 + 리그가 그 N일차에 어땠는가. 못 내면 `{}`."""
    if pool is None or not sport or not team or before is None:
        return {}
    s = _cfg()
    try:
        rows = await pool.fetch(_SERIES_DAYS, sport, team, before)
        if not rows:
            return {}
        nth = consecutive_days([r["d"] for r in rows], before.date())
        if nth < 2:
            return {"질문": f"{team} 이 연전 피로 구간인가", "연전일차": nth,
                    "사유": "연전이 아니다 — 직전 경기가 어제가 아니다"}
        peer = await pool.fetchrow(_SERIES_PEERS, sport, before, nth - 1)
    except Exception as exc:
        logger.warning("[branch] %s 연전 조회 실패: %s", team, exc)
        return {}
    n = int((peer or {}).get("n") or 0)
    if n < int(s.branch_min_n):
        return {"질문": f"{team} 이 연전 {nth}일차 피로 구간인가",
                "연전일차": nth, "사유": f"리그 표본 {n}건 — 하한 미만"}
    return {"질문": f"{team} 이 연전 {nth}일차에서 처지는가",
            "연전일차": nth,
            "같은처지": {"조건": f"연전 {nth}일차 경기", "표본": n,
                        "평균득점": round(float(peer["runs"] or 0), 2),
                        "평균실점": round(float(peer["allowed"] or 0), 2)}}


async def resolve(pool, jg: dict, question: str) -> dict:
    """분기점 1건을 푼다. 반환 `{유형, 질문, 답 or 사유}`.

    답이 없으면 **`답` 을 비우고 `사유` 를 적는다** — 조용히 빠지지 않는다.
    """
    kind = classify(question)
    rec = {"유형": kind, "질문": question}
    from app.engine.starter_recent import _aware, pitcher_name

    if kind == LIVE:
        # 🔴 "알 수 없다"로 끝내지 않는다 — 오늘의 사실은 이미 우리 손에 있다.
        who = next((pitcher_name(jg, sd) for sd in ("home", "away")
                    if pitcher_name(jg, sd)
                    and pitcher_name(jg, sd).split()[-1] in question), None)
        rec["답"] = await live_status(pool, jg, who)
        return rec
    if kind != RECORD:
        rec["사유"] = {
            NEWS: "뉴스형 — 기사 조사(deepsearch) 소관",
            UNKNOWN: "유형을 가리지 못했다",
        }[kind]
        return rec

    before = _aware(jg.get("starts_at"))
    sport = (jg.get("sport") or "").lower()
    # ── [2026-09-07] 불펜·연전 해결사. **투수 이름보다 먼저 본다** —
    #    "홈 불펜이 조기 가동되는가" 에는 선발 이름이 없어서 종전에는
    #    `사유: 대상 선발을 특정하지 못했다` 로 끝났다. 실측상 불펜 42.9%·
    #    연전 10.7% 로 기록형의 절반이 여기 있었다.
    #    ⚠️ 질문이 한쪽을 가리키면 그쪽만, 아니면 양쪽 다 낸다.
    for pat, fn, tag in ((r"불펜|구원|필승조|롱릴리프", bullpen_outlook, "불펜"),
                         (r"연전|연투|휴식일|등판\s*간격", series_outlook, "연전")):
        if not re.search(pat, question):
            continue
        got = {}
        for side in ("home", "away"):
            other = {"home": "원정", "away": "홈"}[side]
            mine = {"home": "홈", "away": "원정"}[side]
            if other in question and mine not in question:
                continue
            blk = await fn(pool, sport, jg.get(side) or "", before)
            if blk:
                got[side] = blk
        if got:
            rec["답"] = got
            return rec
        rec["사유"] = f"{tag} 표본이 하한에 못 미친다"
        return rec
    # 타선 질문이면 타선 해결사로. 투수 이름이 없는 질문이 여기 온다.
    if re.search(r"타선|득점|배율|침체|반등|부진", question):
        res = jg.get("research") or {}
        off = {}
        for side in ("home", "away"):
            u = res.get(f"{side}_usage") or {}
            rpg = u.get("runs_per_game_l3")
            if rpg is None:
                continue
            # 질문이 한쪽만 가리키면 그쪽만 본다.
            hint = {"home": ("홈", jg.get("home") or ""),
                    "away": ("원정", jg.get("away") or "")}[side]
            other = {"home": "원정", "away": "홈"}[side]
            if other in question and hint[0] not in question:
                continue
            blk = await offense_outlook(pool, sport, jg.get(side) or "",
                                        before, float(rpg))
            if blk:
                off[side] = blk
        if off:
            rec["답"] = off
            return rec
        rec["사유"] = "타선 회귀 표본이 부족하다"
        return rec
    # 질문에 이름이 있으면 그 투수, 없으면 양쪽 선발을 다 본다.
    found = {}
    for side in ("home", "away"):
        nm = pitcher_name(jg, side)
        if not nm:
            continue
        if nm.split()[-1] not in question and nm not in question:
            continue
        team = jg.get(side) or ""
        blk = await innings_outlook(pool, sport, nm, team, before)
        if blk:
            found[side] = blk
    if not found:
        rec["사유"] = "질문에서 대상 선발을 특정하지 못했다"
        return rec
    rec["답"] = found
    return rec


async def attach(pool, jg: dict) -> bool:
    """`jg["branch"]` 를 채운다. 하나라도 풀면 True.

    대상은 판정이 낸 `전개.분기점` 과 `추가확인` 이다 — 분기점이 먼저다.
    ⚠️ I/O 는 여기서 끝낸다. 판정 경로는 채워진 값을 읽기만 한다
       (자료10·11 과 같은 규약).
    """
    m = jg.get("matchup") or {}
    qs: list[str] = []
    bp = ((m.get("전개") or {}).get("분기점") or "").strip()
    if bp:
        qs.append(bp)
    # 🔴 [2026-09-07] **변수도 질문이다.** 실측 NYY@SD 변수2 —
    #    "홈 타선 배율 0.46이 일시적 침체일 가능성 … 근거 없음 — 보수 반영".
    #    답이 우리 DB 에 있는데 아무도 묻지 않아 판정이 확률을 지어낼 뻔했다.
    #    리스크 서술만 떼어 보낸다(%p 는 판정의 몫이지 질문이 아니다).
    from app.engine.variable_parse import parse_all

    for row in parse_all(m):
        risk = (row.get("parsed") or {}).get("risk")
        if risk:
            qs.append(risk.strip())
    for q in (m.get("추가확인") or [])[:2]:
        if isinstance(q, str) and q.strip():
            qs.append(q.strip())
    if not qs:
        jg["branch"] = {}
        return False
    out, seen = [], set()
    for q in qs[:int(_cfg().branch_max_questions)]:
        try:
            r = await resolve(pool, jg, q)
        except Exception as exc:
            logger.warning("[branch] 해결 실패 game=%s: %s", jg.get("game_id"), exc)
            continue
        # 🔴 같은 답을 두 번 싣지 않는다. 실측 2026-09-07: 분기점과 추가확인이
        #    둘 다 Wrobleski 를 가리켜 같은 블록이 프롬프트에 두 번 들어갔다.
        #    ⚠️ 유형이 다르면 답이 겹쳐도 남긴다 — 기록형과 실시간형은 **다른
        #       질문에 답한다**(대리값 vs 오늘의 사실).
        sig = (r["유형"], json.dumps(r.get("답"), ensure_ascii=False, sort_keys=True,
                                     default=str))
        if r.get("답") and sig in seen:
            logger.info("[branch] 중복 답 생략 — %s", q[:40])
            continue
        seen.add(sig)
        out.append(r)

    # 🔴 **오늘의 사실은 분기점과 무관하게 항상 싣는다.**
    #    실측 2026-09-07: opus 가 두 회차 연속으로 `추가확인` 에 "구단 발표"·
    #    "가용 인원" 을 적었는데, 그 답(라인업 공시 시각·IL 명단)은 이미 우리
    #    손에 있었다. 분류 결과에 그것의 전달 여부를 맡기지 않는다 —
    #    분류는 틀릴 수 있고, 이 블록은 싸다(수백 자).
    try:
        today = await live_status(pool, jg, None)
    except Exception as exc:
        logger.warning("[branch] 오늘의 사실 조회 실패 game=%s: %s",
                       jg.get("game_id"), exc)
        today = {}
    jg["branch"] = {"항목": out}
    if today.get("결장") or today.get("라인업"):
        jg["branch"]["오늘의사실"] = today
    solved = sum(1 for x in out if x.get("답"))
    logger.info("[branch] game=%s 분기점 %d건 · 해결 %d건 · %s · 오늘의사실 %s",
                jg.get("game_id"), len(out), solved,
                " / ".join(f"{x['유형']}" for x in out) or "없음",
                "Y" if jg["branch"].get("오늘의사실") else "N")
    return bool(solved)


def payload(jg: dict) -> dict:
    """판정 프롬프트에 실을 자료14. **읽기만 한다.**"""
    return jg.get("branch") or {}
