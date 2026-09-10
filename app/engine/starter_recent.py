"""오늘 선발의 최근 등판 + **표본 보정용 시즌 라인**.

🔴 실사고 2026-09-01 (NYY @ LAA, 1:7 패):
     Rodríguez 표본 1경기(6이닝 3실점) → 판정 "안정적" → NYY 66% 추천
     실제 시즌: 6선발 26.2이닝 ERA 5.40 **BB 16개(BB/9 5.4)** — 제구 붕괴 신인
     오늘: 3.2이닝 3볼넷 4실점 (시즌 평균 그대로)
     Ureña  표본 3경기가 그의 부진 구간 → 판정 "이닝 소화력 불안"
     실제 시즌: 23선발 123.1이닝 ERA 2.85 — 정상급
     오늘: 7이닝 1실점 0볼넷 8K
   3경기 창은 **선발에게 너무 좁다.** 로테이션상 15~21일이라 한 번의 호투가
   시즌 성향을 통째로 가린다. 타선은 매일 뛰니 3경기가 의미 있지만 선발은 다르다.
   그리고 표본이 1경기여도 3경기와 동등하게 취급됐다 — 하한이 없었다.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

#: [B] 선발 최근 등판 창. 3 → 5 (2026-09-01 사용자 지시).
#   3등판이면 15~21일이라 한 번의 호투가 시즌 성향을 가린다.
RECENT_STARTS = 5

#: [A] 이 수 이하면 "표본 부족" — 확신도 강등 + 추천 자동 탈락.
#   판정이 "표본 1경기뿐"이라고 두 번 말해놓고 확률은 66%로 냈다(실사고).
#   위험을 말하는 것과 가격에 반영하는 것은 다르다.
MIN_STARTS = 1

_FETCH = """
    SELECT a.opponent, a.innings, a.r, a.hits, a.k, a.bb,
           g.starts_at,
           -- [v1.1 1단계] 그 등판에서 **팀이 낸 득점**. W-L 액면에 속지 않기 위한 값이다.
           --   실측 사례: 바즈 4승14패 — 실질은 ERA 4.04에 타선 지원 부족.
           --   신규 크롤 없음. team/home/away 일치율은 3종목 100% 실측(2026-08-31).
           CASE WHEN a.team = g.home THEN g.home_score
                WHEN a.team = g.away THEN g.away_score END AS run_support
      FROM pitcher_appearances a
      JOIN games g ON g.id = a.game_id
     WHERE g.sport = $1 AND a.pitcher = $2 AND a.is_starter
       AND g.starts_at < $3 AND g.status = 'final'
     ORDER BY g.starts_at DESC
     LIMIT $4
"""


#: 구원 등판 조회. **선발과 섞지 않는다** — 1이닝 구원과 6이닝 선발은 다른 일이다.
#   🔴 실측 2026-09-01: `_FETCH` 가 `AND a.is_starter` 로 걸러 구원 기록을
#      하나도 보지 않았다. 저장은 되어 있다 — mlb 구원 1,730행 · npb 609 · kbo 839.
#      실사고의 Will Dion 은 **총 등판 19회 중 선발 1회**였다. 우리는 n=0 으로
#      읽었지만 18번의 구원 기록이 있었다.
#      회수율 실측(최근 7일, 표본≤1 선발): MLB 15건 중 7건(46.7%)이 구원 2건 이상.
_FETCH_RELIEF = """
    SELECT a.opponent, a.innings, a.r, a.hits, a.k, a.bb, g.starts_at
      FROM pitcher_appearances a
      JOIN games g ON g.id = a.game_id
     WHERE g.sport = $1 AND a.pitcher = $2 AND NOT a.is_starter
       AND g.starts_at < $3 AND g.status = 'final'
     ORDER BY g.starts_at DESC
     LIMIT $4
"""
#: 구원 표본 상한. 선발 창(5)보다 짧게 둔다 — 참고 자료이지 주 근거가 아니다.
RECENT_RELIEF = 4


def _aware(v) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=UTC)
    try:
        s = str(v).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def slim_start(row) -> dict:
    """등판 한 줄. ERA 키는 만들지 않는다.

    `run_support`(그 등판에서 팀이 낸 득점)를 함께 싣는다 — 승패는 타선 지원에
    좌우되므로, 이 값이 없으면 판정이 W-L 액면에 속는다.
    """
    def _get(k):
        if isinstance(row, dict):
            return row.get(k)
        try:
            return row[k]
        except (KeyError, IndexError, TypeError):
            return None

    out: dict = {}
    for k in ("opponent", "innings", "r", "hits", "k", "bb", "run_support"):
        v = _get(k)
        if v is not None:
            out[k] = v
    dt = _aware(_get("starts_at"))
    if dt is not None:
        out["date"] = dt.date().isoformat()
    return out


def pitcher_name(jg: dict, side: str) -> str:
    """research.{side}_pitcher.name 우선. 없으면 games.{side}_pitcher.

    research 키가 없는 경기를 `or {}`로 받으면 빈 dict가 이름이 있는 것처럼
    처리되어 MLB 예고 선발(games 컬럼)이 전부 빈다 (실측 2026-08-29).
    """
    r = jg.get("research") or {}
    p = r.get(f"{side}_pitcher")
    if isinstance(p, dict):
        name = (p.get("name") or "").strip()
        if name:
            return name
    elif p:
        return str(p).strip()
    return str(jg.get(f"{side}_pitcher") or "").strip()


async def attach_starter_recent(jg: dict, pool) -> None:
    """research.{home,away}_starter_recent 을 채운다. pool 없으면 빈 목록."""
    research = jg.setdefault("research", {})
    sport = jg.get("sport") or ""
    before = _aware(jg.get("starts_at")) or datetime.now(UTC)
    for side in ("home", "away"):
        name = pitcher_name(jg, side)
        key = f"{side}_starter_recent"
        if not pool or not name or not sport:
            research.setdefault(key, [])
            continue
        try:
            rows = await pool.fetch(_FETCH, sport, name, before, RECENT_STARTS)
        except Exception as exc:
            logger.warning("[starter_recent] %s %s 조회 실패: %s", sport, name, exc)
            research.setdefault(key, [])
            continue
        research[key] = [slim_start(r) for r in rows]
        # 선발 표본이 얇을 때만 구원 기록을 붙인다 — 충분하면 잡음이다.
        rkey = f"{side}_starter_relief"
        research.setdefault(rkey, [])
        if len(research[key]) <= MIN_STARTS:
            try:
                rrows = await pool.fetch(_FETCH_RELIEF, sport, name, before,
                                         RECENT_RELIEF)
                research[rkey] = [slim_start(r) for r in rrows]
                if research[rkey]:
                    logger.info("[starter_recent] %s 선발 %d건 → 구원 %d건 보강",
                                name, len(research[key]), len(research[rkey]))
            except Exception as exc:
                logger.warning("[starter_recent] %s 구원 조회 실패: %s", name, exc)
    mark_low_sample(jg)


#: [SR-1 2026-09-10] **얇은 표본** 기준. `MIN_STARTS`(=1, 추천 자동 탈락)와
#  **다른 규칙**이다 — 이쪽은 확률을 0.50 쪽으로 당기고 확신도를 낮춘다.
#  `app/engine/CLAUDE.md` 대원칙에 이미 있던 문장을 코드로 옮긴 것이다:
#    "최근 등판이 2경기 이하면 시즌으로 메우지 말고 0.50 쪽으로 당기고
#     확신도를 낮춘다. 표본이 적다는 사실 자체가 정보다."
THIN_STARTS = 2

#: 얇을 때 남길 확신의 비율. `|p-0.50|` 에 곱한다.
#  🔴 실측(운영 195경기, 선발 30일 등판 수로 재구성):
#       ≤2경기 36/78 = 46.2% · 브라이어 0.2644  ← 0.25 보다 나쁘다
#       ≥3경기 61/110 = 55.5% · 브라이어 0.2487
#       평균 |p-0.5| 는 7.7 vs 7.6%p — **얇을 때도 같은 확신으로 찍고 있었다**
#     λ 를 훑으면 얇음 브라이어 최소는 λ=0(0.2500)이다. 그래도 0.5 로 잡았다 —
#     재구성이 DB 보유 기간에 좌우되고("0경기" 군이 53.1%로 나온 건 진짜
#     신인이 아니라 이력이 없는 경우가 섞인 탓), 두 군 차이도 유의하지 않다
#     (z≈1.26 · p≈0.21). 최적값을 그대로 쓰지 않고 보수적으로 절반만 깎는다.
#  ⚠️ 1.0 으로 두면 축소가 항등이 되어 종전 동작으로 돌아간다.
THIN_SHRINK = 0.5


def thin_sample_sides(jg: dict) -> list[str]:
    """[SR-1] 자료4 등판이 `THIN_STARTS` 이하인 쪽. 빈 목록이면 정상."""
    r = jg.get("research") or {}
    out = []
    for side in ("home", "away"):
        if not pitcher_name(jg, side):
            continue
        if len(r.get(f"{side}_starter_recent") or []) <= THIN_STARTS:
            out.append(side)
    return out


def low_sample_sides(jg: dict) -> list[str]:
    """[A] 최근 등판 표본이 하한 이하인 쪽. 빈 목록이면 정상."""
    r = jg.get("research") or {}
    out = []
    for side in ("home", "away"):
        if not pitcher_name(jg, side):
            continue
        if len(r.get(f"{side}_starter_recent") or []) <= MIN_STARTS:
            out.append(side)
    return out


def mark_low_sample(jg: dict) -> list[str]:
    """표본 부족을 경기에 새긴다. 게이트와 확신도가 이 값을 읽는다."""
    sides = low_sample_sides(jg)
    jg["starter_low_sample"] = sides
    if sides:
        logger.info("[starter_recent] 표본 부족 game=%s sides=%s — 추천 자격 없음",
                    jg.get("game_id"), ",".join(sides))
    return sides
