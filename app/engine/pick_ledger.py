"""[v1.1 0단계] 픽 레저 — 판정 전건을 기록하고, 결과가 들어오면 채점한다.

목적은 하나다: **규율(임계 58/63·확신도 거부권·뉴스 상한)이 맞는지를 시스템이
스스로 데이터로 답하게 하는 것.** 지금까지는 판정을 내고 발송하면 끝이라
"58%가 옳은 문턱인가"를 영원히 알 수 없었다.

⚠️ 이 모듈은 **측정 전용이다. 어떤 판정 경로도 이 표를 읽지 않는다.**
   CLAUDE.md 판정 철학("채점 성적표는 판정에 쓰지 않는다")은 그대로 유지된다 —
   바뀐 것은 "기록조차 남기지 않는다"뿐이고, 그것은 사용자 지시(v1.1 0단계)다.
   임계값 재검토는 표본이 쌓인 뒤 **별도 지시로만** 한다.

⚠️ 발송 여부와 무관하게 기록한다. 보드만·거부권 탈락 경기가 캘리브레이션
   데이터의 절반이고, 그 경기들의 원판정이 맞았는지를 봐야 거부권이 옳은지 안다.
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# gate_result 값 집합. 엣지·가치 계열은 4·5단계에서 채워진다 —
# 지금 쓰이는 것은 추천·보드만·거부권탈락 셋뿐이다.
GATE_RECOMMENDED = "추천"
GATE_BOARD_ONLY = "보드만"
GATE_VETOED = "거부권탈락"
GATE_EDGE = "엣지"            # 4단계
GATE_VALUE_WARN = "가치주의"   # 5단계
GATE_VALUE_FAIL = "가치탈락"   # 5단계
GATE_DISCRETION = "재량"       # 수동 분류용

GATE_RESULTS = (
    GATE_EDGE, GATE_RECOMMENDED, GATE_VALUE_WARN, GATE_BOARD_ONLY,
    GATE_VETOED, GATE_VALUE_FAIL, GATE_DISCRETION,
)

# 판정 내용이 같으면 새 이력 행을 만들지 않는다. 이 조합이 "같은 판정"의 정의다.
_SIG_FIELDS = ("p_home", "favored", "confidence", "lineup_status",
               "gate_result", "model")


def gate_result_of(jg: dict, pick: dict | None) -> str:
    """이 경기가 게이트에서 어떻게 분류됐는가.

    거부권을 추천/보드만보다 **먼저** 본다 — 확신도 '하'는 확률이 아무리 높아도
    탈락이고, 그 사실 자체가 캘리브레이션의 핵심 질문이기 때문이다
    ("거부권으로 버린 경기들의 원판정은 실제로 틀렸는가?").
    """
    if jg.get("judge_pass") or jg.get("judge_confidence") == "low":
        return GATE_VETOED
    if not (pick and pick.get("recommended")):
        return GATE_BOARD_ONLY
    # [v1.1 5단계] 확률 통과 위에 가치·엣지를 얹는다. 배당이 없으면
    #   passes_value 가 None 이라 추천 그대로다 — 수집 실패가 추천을 막지 않는다.
    from app.engine.value_gate import CLS_EDGE, CLS_VALUE_WARN, classify

    cls = classify(probability_ok=True, vetoed=False,
                   p=pick.get("p"), odds=pick.get("odds"),
                   edge_status=jg.get("edge_status"))
    if cls == CLS_VALUE_WARN:
        return GATE_VALUE_WARN
    if cls == CLS_EDGE:
        return GATE_EDGE
    return GATE_RECOMMENDED


def _market_cols(jg: dict, pick: dict | None) -> dict:
    """시장 3칸. 값이 없으면 **NULL 로 남긴다** — 지어내지 않는다.

    `divergence_pp` 부호는 `market_baseline_ledger.divergence` 와 같은 방향
    (우리 − 시장, %p)이다. 두 표가 반대 부호를 쓰면 대조할 때마다 헷갈린다.
    """
    mkt = jg.get("p_market_send")
    our = jg.get("p_claude")
    div = None
    if mkt is not None and our is not None:
        div = round((float(our) - float(mkt)) * 100, 2)
    return {
        "odds": (pick or {}).get("odds"),
        "market_prob": float(mkt) if mkt is not None else None,
        "divergence_pp": div,
    }


async def _fill_market(conn, ledger_id: int, row: dict) -> None:
    """이미 있는 행의 시장 칸만 채운다. **판정 칸은 손대지 않는다.**

    ⚠️ `COALESCE(기존, 새값)` 이다 — 한 번 새긴 시장값을 나중 스냅샷으로
       덮어쓰지 않는다. 판정 시점의 시장이 우리가 재려는 것이고, 경기가
       가까워질수록 시장은 정답에 수렴하므로 덮어쓰면 사후확신이 된다.
    """
    if row.get("market_prob") is None and row.get("odds") is None:
        return
    try:
        await conn.execute(
            """UPDATE pick_ledger
                  SET odds          = COALESCE(odds, $2),
                      market_prob   = COALESCE(market_prob, $3),
                      divergence_pp = COALESCE(divergence_pp, $4)
                WHERE id = $1""",
            ledger_id, row.get("odds"), row.get("market_prob"),
            row.get("divergence_pp"))
    except Exception as exc:                       # 측정 장치가 본체를 죽이지 않는다
        logger.warning("[ledger] 시장 칸 기록 실패 id=%s: %s", ledger_id, exc)


def predicted_side(favored: str | None, p_home: float | None) -> str | None:
    """채점에 쓸 예측 방향.

    `우세`가 home/away면 그대로 쓴다. '박빙'이면 방향 선언이 없으므로
    p_home으로 환산한다 — 캘리브레이션은 확률 구간별 적중률을 보는 것이라
    방향이 없으면 그 표본이 통째로 빠진다. 환산 기준을 코드에 박아 두어
    나중에 "박빙은 어떻게 셌나"를 다시 묻지 않게 한다.
    """
    if favored in ("home", "away"):
        return favored
    if p_home is None:
        return None
    return "home" if p_home >= 0.5 else "away"


def _row_from_game(jg: dict, analysis: dict, picks_by_game: dict) -> dict | None:
    """판정된 경기 1건 → 레저 행. 판정이 없으면 None(기록하지 않는다)."""
    gid = jg.get("game_id")
    matchup = jg.get("matchup") or {}
    if gid is None or matchup.get("p_home") is None:
        return None                      # 판정 없음 — 레저는 판정의 원장이다
    pick = picks_by_game.get(gid)
    return {
        "game_id": int(gid),
        "sport": analysis.get("sport") or jg.get("sport") or "",
        "league": jg.get("league"),
        "date": analysis.get("date") or "",
        "p_home": jg.get("p_claude"),
        "favored": matchup.get("우세"),
        "confidence": matchup.get("확신도"),
        "lineup_status": jg.get("lineup_status") or "none",
        "gate_result": gate_result_of(jg, pick),
        "model": jg.get("model") or matchup.get("model"),
        # [시장 2026-09-07] 파이프라인이 판정 직후 이미 계산해 둔 값을 **버리고**
        #   있었다. 컬럼은 처음부터 있었고 INSERT 만 안 썼다.
        #   🔴 실측: 원장 621행 중 divergence_pp 0 · market_prob 0 — 시장 신호가
        #      캘리브레이션에 한 번도 닿은 적이 없다. 같은 56경기에서 시장
        #      60.7% · 우리 50.0% 였는데 그 격차를 볼 방법이 없었다.
        #   ⚠️ 배당 격리는 그대로다 — 이 값은 **판정이 끝난 뒤** 붙는 기록이고,
        #      판정 프롬프트로는 가지 않는다.
        **_market_cols(jg, pick),
    }


def _same_judgement(row: dict, existing) -> bool:
    for f in _SIG_FIELDS:
        a, b = row.get(f), existing[f]
        if f == "p_home":
            if (a is None) != (b is None):
                return False
            if a is not None and abs(float(a) - float(b)) > 1e-9:
                return False
        elif a != b:
            return False
    return True


async def record_analysis(pool, analysis: dict, *, trial: bool = False) -> dict:
    """분석 1슬레이트의 판정 전건을 레저에 반영. 반환: {inserted, rejudged, unchanged}.

    멱등이다 — 같은 분석을 여러 번 저장해도(캐시 재저장 등) 이력 행이 늘지 않는다.
    판정 내용이 실제로 달라졌을 때만 옛 행을 is_final=false로 내리고 새 행을 넣는다.

    `trial=True`는 시범 운영 등급(축구)이다 — 캘리브레이션에서 야구와 **분리
    집계**한다. 검증된 파이프라인과 시범 경로의 성적을 한 표에 섞으면 둘 다
    못 믿게 된다.

    ⚠️ 레저 실패가 발송을 막지 않는다. 측정 장치가 본체를 죽이면 안 된다.
    """
    stats = {"inserted": 0, "rejudged": 0, "unchanged": 0, "failed": 0}
    if pool is None or not analysis:
        return stats
    picks_by_game: dict = {}
    for p in analysis.get("picks") or []:
        # 승패(h2h) 픽이 그 경기의 대표다. 토탈·핸디로 게이트 결과를 정하면
        # 야구(승패만 평가)와 축구가 서로 다른 기준으로 기록된다.
        if p.get("market") == "h2h" and p.get("game_id") is not None:
            picks_by_game.setdefault(p["game_id"], p)

    for jg in analysis.get("games") or []:
        row = _row_from_game(jg, analysis, picks_by_game)
        if row is None:
            continue
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    existing = await conn.fetchrow(
                        "SELECT id, rejudge_count, "
                        + ", ".join(_SIG_FIELDS) +
                        " FROM pick_ledger"
                        " WHERE game_id = $1 AND date = $2 AND is_final"
                        " FOR UPDATE",
                        row["game_id"], row["date"])
                    if existing is not None and _same_judgement(row, existing):
                        # 🔴 판정은 그대로여도 **시장은 나중에 온다.** 여기서
                        #    그냥 넘기면 판정이 배당보다 먼저 끝난 경기는
                        #    시장 칸이 영영 NULL 로 남는다.
                        #    이력 행은 늘리지 않는다 — 시장은 판정이 아니다.
                        await _fill_market(conn, existing["id"], row)
                        stats["unchanged"] += 1
                        continue
                    n = 0
                    if existing is not None:
                        await conn.execute(
                            "UPDATE pick_ledger SET is_final = FALSE WHERE id = $1",
                            existing["id"])
                        n = int(existing["rejudge_count"]) + 1
                    await conn.execute(
                        """INSERT INTO pick_ledger
                             (game_id, sport, league, date, p_home, favored,
                              confidence, lineup_status, gate_result, model,
                              rejudge_count, is_final, trial,
                              odds, market_prob, divergence_pp)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,TRUE,$12,
                                   $13,$14,$15)""",
                        row["game_id"], row["sport"], row["league"], row["date"],
                        row["p_home"], row["favored"], row["confidence"],
                        row["lineup_status"], row["gate_result"], row["model"], n,
                        trial,
                        row["odds"], row["market_prob"], row["divergence_pp"])
                    stats["rejudged" if existing is not None else "inserted"] += 1
        except Exception as exc:
            # 한 경기 실패가 나머지를 막지 않는다. 다만 **조용히 넘기지 않는다** —
            # 레저가 판정의 유일한 영구 기록이 된 이상, 기록 실패는 그 판정이
            # 영원히 사라진다는 뜻이다. 호출자가 CRITICAL로 올릴 수 있게 센다.
            stats["failed"] += 1
            logger.warning("[ledger] 기록 실패 game=%s: %s", row.get("game_id"), exc)
    if stats["inserted"] or stats["rejudged"]:
        logger.info("[ledger] %s %s — 신규 %d · 재판정 %d · 변화없음 %d",
                    analysis.get("sport"), analysis.get("date"),
                    stats["inserted"], stats["rejudged"], stats["unchanged"])
    return stats


async def grade_pending(pool, sport: str | None = None) -> dict:
    """미채점 행에 결과를 붙인다. 반환: {graded, void}.

    우천취소·서스펜디드·노게임은 void=true로 닫는다 — 미채점으로 남겨 두면
    "채점 결손"과 구분되지 않아 무결손 판정을 못 한다.

    ⚠️ 진행 중(live) 경기는 건드리지 않는다. status가 final인 것만 채점한다.
    """
    out = {"graded": 0, "void": 0}
    if pool is None:
        return out
    # [C3] 변수 원장도 같은 잡에서 채점한다 — 따로 돌면 한쪽만 밀린다.
    #   ⚠️ 실패해도 픽 채점을 막지 않는다.
    #   ⚠️ **반환 dict 에 넣지 않는다.** `{graded, void}` 는 호출부·테스트가
    #      정확히 비교하는 계약이다. 결과는 로그와 `variable_ledger` 에 남고
    #      일일 요약은 원장을 직접 읽는다.
    try:
        from app.engine.variable_ledger import grade as _grade_vars

        v = await _grade_vars(pool, sport)
        if v.get("graded"):
            logger.info("[ledger] 변수 채점 동반 실행 %s", v)
    except Exception as exc:
        logger.warning("[ledger] 변수 채점 생략: %s", exc)
    # [시장 기준선] 같은 잡에서 채점한다 — **새 잡을 만들지 않는다**
    #   (타이밍 결합 회피: 따로 돌면 한쪽만 밀린다).
    #   ⚠️ 반환 계약 `{graded, void}` 는 건드리지 않는다.
    try:
        from app.engine.market_baseline import grade as _grade_market

        mb = await _grade_market(pool, sport)
        if mb.get("graded"):
            logger.info("[ledger] 시장 기준선 채점 동반 실행 %s", mb)
    except Exception as exc:
        logger.warning("[ledger] 시장 기준선 채점 생략: %s", exc)
    where_sport = " AND l.sport = $1" if sport else ""
    args = [sport] if sport else []
    rows = await pool.fetch(
        f"""SELECT l.id, l.game_id, l.sport, l.favored, l.p_home,
                  g.status, g.home_score, g.away_score
              FROM pick_ledger l JOIN games g ON g.id = l.game_id
             WHERE l.graded_at IS NULL
               AND g.status IN ('final', 'cancelled', 'suspended', 'postponed')
               {where_sport}""", *args)
    for r in rows:
        if r["status"] != "final" or r["home_score"] is None or r["away_score"] is None:
            await pool.execute(
                "UPDATE pick_ledger SET void = TRUE, graded_at = now() WHERE id = $1",
                r["id"])
            out["void"] += 1
            continue
        h, a = int(r["home_score"]), int(r["away_score"])
        winner = "home" if h > a else "away" if a > h else "draw"
        side = predicted_side(r["favored"], r["p_home"])
        # ⚠️ **무승부는 채점 분모에서 제외한다(void 아님).** hit=None 으로 두어
        #    캘리브레이션 집계가 건너뛰게 한다. 경기는 정상 성립했으므로
        #    void(우천취소·서스펜디드)와 구분해야 한다. KBO 는 연장 12회에도
        #    동점이면 무승부다. → docs/MODEL.md
        hit = None if (side is None or winner == "draw") else (side == winner)
        await pool.execute(
            """UPDATE pick_ledger
                  SET final_score = $2, winner = $3, hit = $4, graded_at = now()
                WHERE id = $1""",
            # 🔴 **"홈-원정" 순.** 종전 f"{a}-{h}" 는 원정-홈이라 카드·중계
            #    표기와 순서가 뒤집혀 있었다. 기존 행은 건드리지 않는다 —
            #    소급 수정하면 어느 순서로 적힌 행인지 구분할 수 없게 된다.
            r["id"], f"{h}-{a}", winner, hit)
        out["graded"] += 1
        # 건별로 남긴다 — "채점 N건"만으로는 무엇이 맞고 틀렸는지 볼 수 없고,
        # 운영 DB를 직접 조회할 수 없을 때 이 로그가 유일한 확인 경로다.
        # 🔴 `game=` 이었지만 실제 값은 `pick_ledger.id` 다 — 로그를 보고
        #    games.id 로 찾으면 엉뚱한 경기가 나온다. 둘 다 적는다.
        logger.info("[ledger] 채점 ledger_id=%s game_id=%s %s 예측=%s(p_home=%s) "
                    "결과=%s(%s 홈-원정) → %s",
                    r["id"], r.get("game_id"), r.get("sport") or "", side,
                    r["p_home"], winner, f"{h}-{a}",
                    "적중" if hit else ("무승부(분모 제외)" if hit is None else "빗나감"))
    if out["graded"] or out["void"]:
        logger.info("[ledger] 채점 %d건 · void %d건", out["graded"], out["void"])
    return out


# ---------------------------------------------------------------- 소급 백필 (1회성)
#
# ⚠️ **이 절은 1회성이다.** Redis에 남아 있던 판정을 레저로 옮겨 담기 위한 것이고,
#    백필이 끝났음을 확인한 뒤에는 다음 배포에서 통째로 지워도 된다
#    (호출부: scheduler.startup_backfill_job).
#    남겨 두어도 해롭지는 않다 — 멱등이고, 처리한 키는 건너뛴다.

SLATE_KEY_RE = re.compile(r"^analysis:(?P<sport>[a-z]+):(?P<date>\d{4}-\d{2}-\d{2})$")
BACKFILL_SEEN = "ledger_backfill_seen"      # 처리한 슬레이트 키 집합 (Redis SET)


async def backfill_from_redis(pool, redis, since: str, *, dry_run: bool = False,
                              skip_seen: bool = True) -> dict:
    """Redis 슬레이트 분석(`analysis:{sport}:{date}`)을 레저로 옮긴다.

    ⚠️ 읽기만 한다 — Redis 키를 지우거나 고치지 않는다.
    ⚠️ 슬레이트 키만 쓴다. 경기별 키(`analysis:{sport}:{game_id}:{date}`)에는
       게이트 결과·라인업 상태가 없어 레저의 절반이 빈다 — 반쪽 데이터로
       캘리브레이션을 오염시키지 않는다.

    멱등성은 두 겹이다: ① 처리한 키를 `ledger_backfill_seen`에 남겨 건너뛰고
    ② 건너뛰지 못해도 `record_analysis`가 같은 판정에 이력 행을 만들지 않는다.
    ①만으로는 부족하다 — Redis가 비워지면 ②가 받아낸다.
    """
    stats = {"slates": 0, "seen": 0, "inserted": 0, "rejudged": 0,
             "unchanged": 0, "failed": 0, "skipped": 0}
    if pool is None or redis is None:
        return stats
    keys = [k async for k in redis.scan_iter(match="analysis:*", count=500)]
    for key in sorted(keys):
        m = SLATE_KEY_RE.match(key)
        if not m or m.group("date") < since:
            continue
        if skip_seen and not dry_run:
            try:
                if await redis.sismember(BACKFILL_SEEN, key):
                    stats["seen"] += 1
                    continue
            except Exception:
                pass                     # 표식 조회 실패는 백필을 막지 않는다
        raw = await redis.get(key)
        if not raw:
            stats["skipped"] += 1
            continue
        try:
            analysis = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[ledger] 백필 건너뜀 — JSON 파싱 실패: %s", key)
            stats["skipped"] += 1
            continue
        analysis.setdefault("sport", m.group("sport"))
        analysis.setdefault("date", m.group("date"))
        stats["slates"] += 1
        if dry_run:
            continue
        st = await record_analysis(pool, analysis)
        for k2 in ("inserted", "rejudged", "unchanged", "failed"):
            stats[k2] += st[k2]
        try:
            await redis.sadd(BACKFILL_SEEN, key)
        except Exception:
            pass
    return stats
