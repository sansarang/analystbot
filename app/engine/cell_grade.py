"""[#63] 칸별 사후 채점 — 2단 해석봇의 ▲▼가 실제로 맞았는지 센다.

**왜 이게 필요한가.** 2단은 지금 다섯 칸에 전부 부호를 매기지만, 그중 어느 칸이
실제로 승패를 가리키는지는 아무도 모른다. 불펜 칸이 신호인지, 최근 3경기 칸이
신호인지, 아니면 전부 잡음인지 — **결과와 대조하기 전까지는 추측이다.**

이 모듈이 하는 일은 두 가지뿐이다.
  ① 판정 시점에 (경기 × 팀 × 칸 × 부호)를 그대로 적재한다.
  ② 경기가 끝나면 `cell_ledger` 뷰로 칸별 적중률을 집계한다.

⚠️ **여기서 임계값을 만들지 마라.** 이 표는 임계값을 *실측으로* 정하기 위한
   재료다. 표본이 얇을 때 "불펜 칸이 낫다" 같은 결론을 내면 #77과 같은 실수를
   반복한다. 칸당 최소 표본은 `MIN_SAMPLE`이고, 그 아래는 집계에서 판단하지
   않는다("표본 부족"으로 표시).
"""
from __future__ import annotations

import logging

from app.engine.card import SCORING_LEVELS

logger = logging.getLogger(__name__)

# 칸별로 이만큼 채점되기 전에는 우열을 말하지 않는다.
# 근거: 적중률 50% 가정에서 표본 30이면 표준오차 ≈ 9%p — 55%와 45%를 구분하지
#       못한다. 이 값은 **판단 유보선**이지 성능 기준이 아니다.
MIN_SAMPLE = 30

_UPSERT = """
    INSERT INTO cell_verdicts (game_id, side, team, cell, symbol, reason,
                               fact_count, model, ref_total, created_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
    ON CONFLICT (game_id, side, cell) DO UPDATE
       SET symbol = EXCLUDED.symbol, reason = EXCLUDED.reason,
           team = EXCLUDED.team, fact_count = EXCLUDED.fact_count,
           model = EXCLUDED.model, ref_total = EXCLUDED.ref_total,
           created_at = now()
"""

# 득점 환경은 경기 단위라 side를 쓰지 않는다 — 고정값으로 유일 제약을 만족시킨다.
SCORING_SIDE = "game"


async def record_verdicts(pool, game_id: int, side: str, team: str | None,
                          verdicts: dict, card_side: dict | None = None) -> int:
    """`interpret_side` 결과를 그대로 적재한다. 돌려주는 값은 기록된 칸 수.

    폐기된 칸(인용 없음·방향 오독)은 애초에 `verdicts`에 없으므로 기록되지 않는다
    — **판정하지 않은 칸을 채점하면 안 된다.** 그 칸의 적중률은 정의되지 않는다.
    """
    if not pool or not verdicts or side not in ("home", "away"):
        return 0
    rows = []
    for cell, v in verdicts.items():
        sym = (v or {}).get("symbol")
        if sym not in ("▲", "▼", "="):
            continue
        facts = ((card_side or {}).get(cell) or {}).get("facts") or []
        rows.append((int(game_id), side, team, cell, sym,
                     (v.get("reason") or "")[:1000], len(facts),
                     v.get("provider"), None))
    if not rows:
        return 0
    async with pool.acquire() as con:
        await con.executemany(_UPSERT, rows)
    return len(rows)


async def cell_ledger(pool, days: int = 30) -> list[dict]:
    """칸별 적중률. 표본이 얇으면 `verdict='표본 부족'`으로 판단을 유보한다."""
    if not pool:
        return []
    rows = await pool.fetch("""
        SELECT cell, sport, decided, hits, pushes, neutrals, hit_rate
        FROM cell_ledger ORDER BY sport, decided DESC
    """)
    out = []
    for r in rows:
        d = dict(r)
        d["verdict"] = ("표본 부족" if (d["decided"] or 0) < MIN_SAMPLE
                        else "판단 가능")
        out.append(d)
    return out


def format_ledger(rows: list[dict]) -> str:
    """운영용 한 줄 요약. 표본 부족이면 적중률을 **아예 쓰지 않는다** —
    얇은 표본의 숫자를 보여주면 그 숫자가 근거로 쓰인다."""
    if not rows:
        return "칸별 채점 기록 없음"
    lines = []
    for r in rows:
        if r["verdict"] == "표본 부족":
            lines.append(f"{r['sport']}/{r['cell']}: {r['decided']}건 — 표본 부족"
                         f"(최소 {MIN_SAMPLE})")
        else:
            lines.append(f"{r['sport']}/{r['cell']}: {r['hits']}/{r['decided']} "
                         f"= {float(r['hit_rate']) * 100:.1f}%")
    return " · ".join(lines)


# ───────────────────────────────────────────── 재시도 큐 (전 provider 실패 대응)

RETRY_QUEUE_KEY = "cell_retry_queue"     # 2단이 전멸한 경기 — 다음 사이클 재처리


async def queue_retry(redis, sport: str, date: str, game_id) -> None:
    """전 provider가 죽어 판정 0건인 경기를 적어둔다.

    ⚠️ **재시도 큐는 실패를 감추는 장치가 아니다.** 이번 응답은 "판정 미수행"으로
       정직하게 나가고, 큐는 다음 사이클에 조용히 메우는 용도다. 큐에 넣었다고
       사용자에게 판정된 것처럼 보이면 안 된다.
    """
    if redis is None or not game_id:
        return
    import json

    try:
        await redis.sadd(RETRY_QUEUE_KEY, json.dumps(
            {"sport": sport, "date": date, "game_id": game_id}, ensure_ascii=False))
        await redis.expire(RETRY_QUEUE_KEY, 2 * 24 * 3600)
    except Exception as exc:
        logger.debug("[2단] 재시도 큐 적재 실패: %s", exc)


async def drain_retry_queue(redis, limit: int = 20) -> list[dict]:
    """큐를 비우고 재처리 대상을 돌려준다. 꺼낸 것은 큐에서 뺀다 —
    실패하면 호출자가 다시 넣는다(무한 적체를 만들지 않는다)."""
    if redis is None:
        return []
    import json

    out = []
    try:
        for raw in list(await redis.srandmember(RETRY_QUEUE_KEY, limit) or []):
            await redis.srem(RETRY_QUEUE_KEY, raw)
            try:
                out.append(json.loads(raw))
            except Exception:
                continue
    except Exception as exc:
        logger.debug("[2단] 재시도 큐 조회 실패: %s", exc)
    return out


async def record_scoring(pool, game_id, level: str, reason: str,
                        ref_total: float | None, facts: list | None = None,
                        provider: str | None = None) -> bool:
    """[§9-6번째 칸] 득점 환경 판정을 적재한다.

    ⚠️ **기준 총득점(ref_total)을 함께 적는다.** 없으면 "다득점 예상이 맞았나"를
       판정할 수 없다 — 무엇보다 많았어야 하는지가 정의되지 않는다.
       기준이 없으면 기록은 하되 채점 대상에서 빠진다(뷰가 NULL을 거른다).
    """
    if not pool or not game_id or level not in SCORING_LEVELS:
        return False
    async with pool.acquire() as con:
        await con.execute(_UPSERT, int(game_id), SCORING_SIDE, None, "scoring",
                          level, (reason or "")[:1000], len(facts or []),
                          provider, ref_total)
    return True


async def scoring_ledger(pool) -> list[dict]:
    """득점 환경 적중률. 승패 칸과 **따로** 센다 — 다른 질문이기 때문이다."""
    if not pool:
        return []
    rows = await pool.fetch("""
        SELECT sport, level, decided, hits, pushes, ungradable,
               avg_actual, avg_ref, hit_rate
        FROM scoring_ledger ORDER BY sport, decided DESC
    """)
    out = []
    for r in rows:
        d = dict(r)
        d["verdict"] = "표본 부족" if (d["decided"] or 0) < MIN_SAMPLE else "판단 가능"
        out.append(d)
    return out


def format_scoring_ledger(rows: list[dict]) -> str:
    """표본 부족이면 적중률 숫자를 쓰지 않는다 — 얇은 표본은 근거가 못 된다."""
    if not rows:
        return "득점 환경 채점 기록 없음"
    parts = []
    for r in rows:
        head = f"{r['sport']}/{r['level']}"
        if r["verdict"] == "표본 부족":
            parts.append(f"{head}: {r['decided']}건 — 표본 부족(최소 {MIN_SAMPLE})")
        else:
            parts.append(f"{head}: {r['hits']}/{r['decided']} "
                         f"= {float(r['hit_rate']) * 100:.1f}% "
                         f"(실제 평균 {r['avg_actual']} vs 기준 {r['avg_ref']})")
        if r.get("ungradable"):
            parts[-1] += f" · 기준 없어 미채점 {r['ungradable']}건"
    return " · ".join(parts)
