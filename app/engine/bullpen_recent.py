"""[C1] 불펜 — **최근 3경기 실점 + 최근 3일 가용성.** 시즌 누적 없음.

🔴 대원칙(2026-09-04 사용자 확정): 판정에 들어가는 모든 데이터는 최근
   3~5경기(불펜은 최근 3일)만 쓴다. **시즌 누적·통산·상대전적 금지.**
   그래서 종전 자료9 의 `team_era`(시즌 방어율)를 걷어내고 이 모듈로 바꾼다.

⚠️ **투구수가 DB 에 없다.** `pitcher_appearances` 는 `batters`(TBF) 만 갖고
   있어 이를 소모 대리값으로 쓴다(타자당 ~4구). 임계는 config 가 원본이고
   환산 근거를 프롬프트에도 적는다 — 대리값을 실측처럼 보이게 하지 않는다.

⚠️ 주력 5인 **선정**은 최근 14일을 본다. 판정에 들어가는 **수치**는 최근
   3일이다 — "누가 주력인가"는 명단 문제이지 폼 판정이 아니므로 대원칙과
   충돌하지 않는다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

AVAILABLE, TIRED, SPENT = "가용", "피로", "소진"


def _cfg():
    from app.config import get_settings

    return get_settings()


_RECENT_RUNS = """
    WITH g AS (
        SELECT id, starts_at FROM games
         WHERE sport = $1 AND status = 'final' AND starts_at < $3
           AND ($2 = home OR $2 = away)
         ORDER BY starts_at DESC LIMIT $4
    )
    SELECT coalesce(sum(a.r), 0) AS runs,
           coalesce(sum(a.innings), 0) AS ip,
           count(*) AS appearances,
           count(DISTINCT a.game_id) AS games
      FROM pitcher_appearances a JOIN g ON g.id = a.game_id
     WHERE a.team = $2 AND NOT a.is_starter
"""

_CORE = """
    SELECT a.pitcher, count(*) AS n
      FROM pitcher_appearances a JOIN games g ON g.id = a.game_id
     WHERE g.sport = $1 AND a.team = $2 AND NOT a.is_starter
       AND g.status = 'final' AND g.starts_at < $3
       AND g.starts_at >= $3 - make_interval(days => $4)
     GROUP BY a.pitcher ORDER BY n DESC, a.pitcher LIMIT $5
"""

_LAST3D = """
    SELECT a.pitcher, count(*) AS apps,
           coalesce(sum(a.batters), 0) AS tbf,
           max(g.starts_at) AS last_at
      FROM pitcher_appearances a JOIN games g ON g.id = a.game_id
     WHERE g.sport = $1 AND a.team = $2 AND NOT a.is_starter
       AND g.status = 'final' AND g.starts_at < $3
       AND g.starts_at >= $3 - interval '3 days'
       AND a.pitcher = ANY($4::text[])
     GROUP BY a.pitcher
"""


def label_of(apps: int, tbf: int) -> str:
    """3값 라벨. 임계는 config 가 원본 — 코드에 숫자를 적지 않는다."""
    s = _cfg()
    if apps >= int(s.bullpen_spent_apps) or tbf >= int(s.bullpen_spent_tbf):
        return SPENT
    if apps >= int(s.bullpen_fatigue_apps) or tbf >= int(s.bullpen_fatigue_tbf):
        return TIRED
    return AVAILABLE


async def team_block(pool, sport: str, team: str, before) -> dict:
    """한 팀의 자료9 블록. 못 만들면 빈 dict — 없는 값을 만들지 않는다."""
    if pool is None or not sport or not team or before is None:
        return {}
    s = _cfg()
    out: dict = {}
    try:
        row = await pool.fetchrow(_RECENT_RUNS, sport, team, before,
                                  int(s.bullpen_recent_games))
    except Exception as exc:
        logger.warning("[bullpen] %s %s 최근 실점 조회 실패: %s", sport, team, exc)
        row = None
    if row and int(row["games"]):
        ip = float(row["ip"] or 0)
        out["최근3경기"] = {
            "실점": int(row["runs"]), "이닝": round(ip, 1),
            "등판": int(row["appearances"]), "경기": int(row["games"]),
            "경기당실점": round(int(row["runs"]) / int(row["games"]), 2),
        }
    try:
        core = await pool.fetch(_CORE, sport, team, before,
                                int(s.bullpen_core_days), int(s.bullpen_core_size))
    except Exception as exc:
        logger.warning("[bullpen] %s %s 주력 조회 실패: %s", sport, team, exc)
        return out
    names = [r["pitcher"] for r in core]
    if not names:
        logger.info("[bullpen] %s %s 주력 불펜 0명 — 가용성 없음", sport, team)
        return out
    try:
        rows = await pool.fetch(_LAST3D, sport, team, before, names)
    except Exception as exc:
        logger.warning("[bullpen] %s %s 최근 3일 조회 실패: %s", sport, team, exc)
        return out
    by = {r["pitcher"]: r for r in rows}
    people, worst = [], AVAILABLE
    order = {AVAILABLE: 0, TIRED: 1, SPENT: 2}
    for name in names:
        r = by.get(name)
        apps = int(r["apps"]) if r else 0
        tbf = int(r["tbf"] or 0) if r else 0
        lab = label_of(apps, tbf)
        if order[lab] > order[worst]:
            worst = lab
        people.append({"이름": name, "최근3일등판": apps, "상대타자": tbf,
                       "라벨": lab})
    out["가용성"] = {
        "종합": worst, "주력": people, "인원": len(names),
        "기준": (f"등판 {s.bullpen_fatigue_apps}회↑ 또는 상대타자 "
                 f"{s.bullpen_fatigue_tbf}↑=피로 · {s.bullpen_spent_apps}연투 또는 "
                 f"{s.bullpen_spent_tbf}↑=소진 (투구수 미보유 → 상대타자 대리)"),
    }
    if len(names) < int(s.bullpen_core_size):
        out["가용성"]["주의"] = f"주력 표본 부족, n={len(names)}"
    logger.info("[bullpen] %s %s 최근3경기 실점=%s · 가용성=%s (주력 %d명)",
                sport, team, (out.get("최근3경기") or {}).get("실점"),
                worst, len(names))
    return out


async def attach(pool, jg: dict) -> int:
    """`research.{side}_bullpen` 을 **최근 폼 값으로 교체**한다. 반환 채운 쪽 수.

    🔴 시즌 값(`era`·`whip`·`k9`·`bb9`)을 **지운다.** 남겨 두면 프롬프트에
       계속 실려 대원칙이 깨진다.
    """
    from app.engine.starter_recent import _aware

    if pool is None:
        return 0
    sport = (jg.get("sport") or "").lower()
    before = _aware(jg.get("starts_at"))
    if before is None:
        from datetime import UTC, datetime

        before = datetime.now(UTC)
    research = jg.setdefault("research", {})
    n = 0
    for side in ("home", "away"):
        blk = await team_block(pool, sport, jg.get(side) or "", before)
        dst = research.setdefault(f"{side}_bullpen", {})
        for stale in ("era", "whip", "k9", "bb9"):
            dst.pop(stale, None)
        if blk:
            dst.update(blk)
            n += 1
    return n
