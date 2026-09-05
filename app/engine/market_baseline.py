"""[시장 기준선] 우리 판정 vs 시장 — **사후 전용, 게이트 아님.**

🔴 배당은 판정 입력에 흐르지 않는다(CLAUDE.md 금지선). 이 모듈은 판정이
   확정된 **뒤에** 시장과 나란히 놓고, 나중에 누가 더 맞았는지 세기 위한 것이다.

⚠️ **이번 구현은 계산·표기·채점뿐이다.** "시장 동의 → 추천 강등"은 게이트
   변경이라 동결 대상이고, v1.4 승격 후보로만 예약한다. 추천/보드만 판정은
   기존 게이트 그대로다.
   → 50건 리포트 1번 항목: "시장 이견 경기의 적중률 vs 동의 경기의 적중률"

⚠️ 무승부 배당은 수집하지 않는다(수집 확장 금지). KBO·NPB 무승부는 채점에서
   `void` 로만 처리한다 — 2-way de-vig 에 무승부를 섞으면 확률이 부푼다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 기준 스냅샷 용도. 나이 규칙이 다르다.
SEND = "send"      # 카드 표기용 — 지금 시장이어야 한다
CLOSE = "close"    # 채점·CLV용 — 시작 직전 마지막 = 마감 근사

EVEN = "even"
#: 시장 우세가 없다고 보는 폭. `|p−0.5|` 가 이 미만이면 `even`.
EVEN_BAND = 0.01

#: de-vig 가드 — 배당이 이 이하면 값이 아니다(라이브 오염·결측 방어).
MIN_ODDS = 1.01


def _cfg():
    from app.config import get_settings

    return get_settings()


def devig_two_way(o_home, o_away) -> float | None:
    """2-way 마진 제거 → 홈 확률. 못 믿을 값이면 None.

    ⚠️ 1/배당을 그대로 쓰면 합이 1을 넘는다(북 마진). 반드시 정규화한다.
    """
    try:
        oh, oa = float(o_home), float(o_away)
    except (TypeError, ValueError):
        return None
    if oh <= MIN_ODDS or oa <= MIN_ODDS:
        return None
    ih, ia = 1.0 / oh, 1.0 / oa
    total = ih + ia
    if total <= 0:
        return None
    return round(ih / total, 4)


def favored_of(p_market: float | None) -> str | None:
    """시장의 우세. `EVEN_BAND` 안이면 `even` — 우세 없음이다."""
    if p_market is None:
        return None
    if abs(p_market - 0.5) < EVEN_BAND:
        return EVEN
    return "home" if p_market > 0.5 else "away"


def provider_for(sport: str) -> str | None:
    """그 리그 담당 활성 provider. **레지스트리가 원본이다.**

    ⚠️ 담당 밖 provider 행은 무시한다 — 우선순위를 손으로 적지 않는다.
    """
    from app.registry import active_providers

    for p in active_providers():
        if sport in p.sports:
            return p.name
    return None


_SNAP = """
    SELECT DISTINCT ON (side) side, odds, captured_at
      FROM odds_snapshots
     WHERE game_id = $1 AND market = 'h2h' AND provider = $2
       AND ($3::timestamptz IS NULL OR captured_at < $3)
     ORDER BY side, captured_at DESC
"""


async def p_market(pool, game: dict, *, purpose: str = SEND) -> dict:
    """기준 스냅샷 → {p, provider, age_min, reason}. 못 내면 `p=None` + 사유.

    `purpose=SEND`  : 지금 최신. 나이 > `market_snapshot_max_age_min` 이면 안 낸다.
    `purpose=CLOSE` : **시작 직전 마지막** 스냅샷. 나이 상한 없음(그게 마감이다).
    """
    out = {"p": None, "provider": None, "age_min": None, "reason": None}
    if pool is None or not game.get("id") and not game.get("game_id"):
        out["reason"] = "no_pool_or_game"
        return out
    gid = int(game.get("id") or game.get("game_id"))
    sport = (game.get("sport") or "").lower()
    prov = provider_for(sport)
    if not prov:
        out["reason"] = "no_active_provider"
        logger.info("[market] %s 담당 활성 provider 없음 — 시장 줄 생략", sport)
        return out
    out["provider"] = prov
    before = game.get("starts_at") if purpose == CLOSE else None
    try:
        rows = await pool.fetch(_SNAP, gid, prov, before)
    except Exception as exc:
        out["reason"] = "query_failed"
        logger.warning("[market] game=%s 스냅샷 조회 실패: %s", gid, exc)
        return out
    if len(rows) < 2:
        out["reason"] = "no_snapshot"
        logger.info("[market] game=%s %s 스냅샷 부족(%d) — 시장 줄 생략",
                    gid, purpose, len(rows))
        return out
    by_side = {r["side"]: r for r in rows}
    home, away = game.get("home") or "", game.get("away") or ""
    rh, ra = by_side.get(home), by_side.get(away)
    if rh is None or ra is None:
        out["reason"] = "side_unmatched"
        logger.info("[market] game=%s 팀명 미매칭 %s — 시장 줄 생략",
                    gid, sorted(by_side))
        return out
    p = devig_two_way(rh["odds"], ra["odds"])
    if p is None:
        out["reason"] = "bad_odds"
        logger.info("[market] game=%s 배당 이상(%s/%s) — 시장 줄 생략",
                    gid, rh["odds"], ra["odds"])
        return out
    from datetime import UTC, datetime

    newest = max(rh["captured_at"], ra["captured_at"])
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=UTC)
    age = (datetime.now(UTC) - newest).total_seconds() / 60
    out["age_min"] = round(age, 1)
    if purpose == SEND and age > int(_cfg().market_snapshot_max_age_min):
        out["reason"] = "stale"
        logger.info("[market] game=%s 스냅샷 %.0f분 전 — 상한 초과, 시장 줄 생략",
                    gid, age)
        return out
    out["p"] = p
    return out


# ─────────────────────────── 카드 표기 ───────────────────────────

def market_line(p_market_v: float | None, our_p: float | None) -> str | None:
    """카드 시장 줄. 둘 중 하나라도 없으면 **줄 자체를 안 낸다.**

    🔴 "미수집" 문구를 발명하지 않는다 — 기존 가치 줄이 이미 그 역할을 한다.
    ⚠️ 이견 **사유**는 만들지 않는다. 사유를 쓰려면 판정 프롬프트를 건드려야
       하고 그건 동결 위반이다. 수치·방향·라벨까지만.
    """
    if p_market_v is None or our_p is None:
        return None
    diff = (float(our_p) - float(p_market_v)) * 100
    thr = float(_cfg().market_divergence_pp)
    label = "시장 동의" if abs(diff) < thr else "시장 이견"
    return (f"시장 {float(p_market_v):.0%} vs 우리 {float(our_p):.0%} "
            f"({diff:+.1f}%p — {label})")


# ─────────────────────────── 원장 ───────────────────────────

async def record_send(pool, jg: dict, slate_date: str,
                      snap: dict | None = None) -> bool:
    """발송 시 1행 upsert. 반환 기록 여부.

    ⚠️ **발송된 경기만** 행이 생긴다 — 분모를 같게 하려는 것이다(스키마 주석).
    ⚠️ 실패해도 발송을 막지 않는다.
    """
    if pool is None:
        return False
    gid = jg.get("game_id") or jg.get("id")
    if gid is None:
        return False
    m = jg.get("matchup") or {}
    our_p = jg.get("p_claude")
    if our_p is None:
        our_p = m.get("p_home")
    s = snap if snap is not None else await p_market(pool, jg, purpose=SEND)
    try:
        await pool.execute(
            """INSERT INTO market_baseline_ledger
                   (game_id, sport, slate_date, provider, p_market_send,
                    market_favored, our_p, our_favored)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
               ON CONFLICT (game_id) DO UPDATE
                 SET p_market_send = COALESCE(
                         market_baseline_ledger.p_market_send,
                         EXCLUDED.p_market_send),
                     market_favored = COALESCE(
                         market_baseline_ledger.market_favored,
                         EXCLUDED.market_favored),
                     our_p = EXCLUDED.our_p,
                     our_favored = EXCLUDED.our_favored""",
            int(gid), jg.get("sport") or "", slate_date, s.get("provider"),
            s.get("p"), favored_of(s.get("p")),
            float(our_p) if our_p is not None else None,
            m.get("우세"))
    except Exception as exc:
        logger.warning("[market] 원장 기록 실패 game=%s: %s", gid, exc)
        return False
    logger.info("[market] 원장 send 기록 game=%s 시장=%s 우리=%s provider=%s",
                gid, s.get("p"), our_p, s.get("provider"))
    return True


_PENDING = """
    SELECT b.id, b.game_id, b.sport, g.home, g.away, g.starts_at,
           g.status, g.home_score, g.away_score
      FROM market_baseline_ledger b JOIN games g ON g.id = b.game_id
     WHERE b.graded_at IS NULL
       AND g.status IN ('final', 'cancelled', 'suspended', 'postponed')
       AND ($1::text IS NULL OR b.sport = $1)
"""

#: 🔴 우리 적중은 **`pick_ledger` 에서 복사한다.** 재계산하면 두 숫자가
#   어긋나고, 어긋나면 어느 쪽이 옳은지 알 수 없다(사본 드리프트).
_OUR_HIT = """
    SELECT hit FROM pick_ledger
     WHERE game_id = $1 AND is_final AND graded_at IS NOT NULL
     ORDER BY graded_at DESC LIMIT 1
"""


async def grade(pool, sport: str | None = None) -> dict:
    """종료 경기의 시장 기준선을 채점. 반환 {graded, void}."""
    out = {"graded": 0, "void": 0}
    if pool is None:
        return out
    try:
        rows = await pool.fetch(_PENDING, sport)
    except Exception as exc:
        logger.warning("[market] 채점 대상 조회 실패: %s", exc)
        return out
    for r in rows:
        game = {"id": r["game_id"], "sport": r["sport"], "home": r["home"],
                "away": r["away"], "starts_at": r["starts_at"]}
        close = await p_market(pool, game, purpose=CLOSE)
        p_close = close.get("p")
        fav = favored_of(p_close)
        # 취소·중단, 그리고 **무승부**는 void — 승패 비교가 성립하지 않는다.
        h, a = r["home_score"], r["away_score"]
        void = (r["status"] != "final" or h is None or a is None
                or int(h) == int(a))
        market_hit = None
        if not void and fav in ("home", "away"):
            winner = "home" if int(h) > int(a) else "away"
            market_hit = (fav == winner)
        try:
            our_hit = await pool.fetchval(_OUR_HIT, r["game_id"])
        except Exception as exc:
            logger.debug("[market] our_hit 복사 실패 game=%s: %s", r["game_id"], exc)
            our_hit = None
        try:
            # 🔴 [P1 2026-09-05] `$2` 를 **캐스팅한다.** 종전에는 같은 파라미터가
            #    `SET p_market_close = $2`(컬럼 타입)와 `our_p - $2`(산술) 두
            #    문맥에 쓰여 Postgres 가 타입을 통일하지 못했다:
            #      asyncpg.exceptions.AmbiguousParameterError:
            #      could not determine data type of parameter $2
            #    값과 무관하게 **항상** 실패한다(재현 완료: p_close 가 None 이든
            #    0.512 든 동일). 그래서 2026-09-04 이후 시장 채점이 **한 건도**
            #    기록되지 않았고, 13:00 잡이 매번 `채점 기록 실패 id=…` 만 남겼다.
            #    ⚠️ 파라미터 개수를 바꾸지 않는다 — 호출부 불변이 최소 침습이다.
            await pool.execute(
                """UPDATE market_baseline_ledger
                      SET p_market_close = $2::numeric,
                          market_favored = COALESCE($3, market_favored),
                          divergence = CASE
                              WHEN our_p IS NOT NULL AND $2::numeric IS NOT NULL
                              THEN our_p - $2::numeric END,
                          market_hit = $4, our_hit = $5, void = $6,
                          graded_at = now()
                    WHERE id = $1""",
                r["id"], p_close, fav, market_hit, our_hit, void)
        except Exception as exc:
            logger.warning("[market] 채점 기록 실패 id=%s: %s", r["id"], exc)
            continue
        out["graded"] += 1
        if void:
            out["void"] += 1
    if out["graded"]:
        logger.info("[market] 시장 기준선 채점 %d건 (void %d)",
                    out["graded"], out["void"])
    return out


async def summary(pool, sports: tuple[str, ...]) -> dict | None:
    """일일 요약용 집계. 확정분만. 재료 없으면 None."""
    if pool is None:
        return None
    try:
        row = await pool.fetchrow(
            """SELECT count(*) FILTER (WHERE market_hit) AS m_w,
                      count(*) FILTER (WHERE market_hit IS FALSE) AS m_l,
                      count(*) FILTER (WHERE our_hit) AS o_w,
                      count(*) FILTER (WHERE our_hit IS FALSE) AS o_l,
                      count(*) FILTER (WHERE abs(divergence) * 100 >= $2) AS diverged,
                      count(*) FILTER (WHERE abs(divergence) * 100 >= $2
                                         AND our_hit) AS diverged_hit
                 FROM market_baseline_ledger
                WHERE sport = ANY($1::text[]) AND NOT void
                  AND graded_at IS NOT NULL""",
            list(sports), float(_cfg().market_divergence_pp))
    except Exception as exc:
        logger.debug("[market] 집계 실패: %s", exc)
        return None
    if not row or not (row["m_w"] or row["m_l"] or row["o_w"] or row["o_l"]):
        return None
    return dict(row)
