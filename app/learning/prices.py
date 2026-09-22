"""[LE-1a] 가격 조회 — **종가 규칙의 단일 원본.**

🔴 "종가"는 **킥오프 이전 마지막 스냅샷**이다(W4 규칙 · 지시문 LE-1-1):

```sql
captured_at <= LEAST(<기준시각>, g.starts_at)  ORDER BY captured_at DESC  LIMIT 1
```

이 규칙은 `pick_ledger._CLV_SNAP` 에 먼저 있었다. 여기서 **다시 짓지 않고
같은 문장을 쓴다** — 계약 `test_close_rule_matches_clv_snap` 이 두 곳의 WHERE
절이 같은지 잠근다. 한쪽이 바뀌면 계약이 깨진다(사본 금지).

🔴 **devig 을 새로 짜지 않는다.** 원본은 `app/flow/odds_math.devig_2way` ·
   `devig_3way` 다. 이 저장소에는 devig 구현이 이미 넷 있다 — 다섯째를
   만들지 않는다.

⚠️ 확률은 **우리가 고른 쪽 기준**으로 돌려준다. 홈 기준 확률을 원정 픽에
   그대로 쓰면 CLV 의 부호가 뒤집힌다(CLV-3 이 겪은 실패).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 🔴 종가 조건. `pick_ledger._CLV_SNAP` 과 **같은 문장**이어야 한다.
CLOSE_WHERE = "o.captured_at <= LEAST($2::timestamptz, g.starts_at)"

#: 한 경기 한 마켓의 **킥오프 이전 마지막** 가격을 쪽별로. 뷰가 팀명을
#  `side_norm` 으로 이미 풀어 놓았다(`db/schema.sql` 의 `market_prices`).
_LAST_SQL = f"""
    SELECT DISTINCT ON (p.side_norm) p.side_norm, p.odds, p.captured_at, p.book
      FROM market_prices p
      JOIN games g ON g.id = p.game_id
     WHERE p.game_id = $1 AND p.market = $3
       AND p.side_norm IS NOT NULL
       AND ($4::numeric IS NULL OR p.line = $4)
       AND {CLOSE_WHERE.replace('o.', 'p.')}
     ORDER BY p.side_norm, p.captured_at DESC
"""


async def last_prices(conn, *, game_id: int, market: str = "h2h",
                      at=None, line=None) -> dict:
    """쪽별 마지막 가격 `{side_norm: odds}`. 🔴 **없으면 빈 dict** — 0 으로
    채우지 않는다(`record_clv` 와 같은 규약)."""
    from datetime import datetime, timezone

    when = at or datetime.now(timezone.utc)
    try:
        rows = await conn.fetch(_LAST_SQL, game_id, when, market, line)
    except Exception as exc:
        logger.warning("[learning] 가격 조회 실패 game=%s: %s", game_id, exc)
        return {}
    return {r["side_norm"]: float(r["odds"]) for r in rows
            if r["odds"] is not None}


def devig(prices: dict) -> dict:
    """쪽별 배당 → 쪽별 확률. 🔴 **기존 devig 을 쓴다.**

    ⚠️ 2-way 와 3-way 를 쪽 수로 가른다. 한쪽만 있으면 **빈 dict** 다 —
       마진을 못 걷어낸 1/배당을 확률이라고 부르지 않는다.
    """
    from app.flow.odds_math import devig_2way, devig_3way

    if not isinstance(prices, dict):
        return {}
    h, d, a = prices.get("home"), prices.get("draw"), prices.get("away")
    o, u = prices.get("over"), prices.get("under")
    try:
        if h and d and a:
            ph, pd, pa = devig_3way(h, d, a)
            return {"home": round(ph, 4), "draw": round(pd, 4),
                    "away": round(pa, 4)}
        if h and a:
            ph, pa = devig_2way(h, a)
            return {"home": round(ph, 4), "away": round(pa, 4)}
        if o and u:
            po, pu = devig_2way(o, u)
            return {"over": round(po, 4), "under": round(pu, 4)}
    except Exception as exc:
        logger.info("[learning] devig 실패 %r: %s", prices, exc)
    return {}


async def close_p(conn, *, game_id: int, side: str,
                  market: str = "h2h", line=None) -> float | None:
    """**우리가 고른 쪽**의 종가 확률. 못 구하면 None.

    ⚠️ 킥오프 이후 스냅샷은 들어오지 않는다(`CLOSE_WHERE`). 그래서 이 값은
       "경기 후 정보"가 아니다 — LE-2 의 누설 검사를 통과한다.
    """
    from datetime import datetime, timezone

    # 기준시각을 **먼 미래**로 두면 `LEAST(…, starts_at)` 가 킥오프로 잘린다.
    far = datetime(2100, 1, 1, tzinfo=timezone.utc)
    pr = devig(await last_prices(conn, game_id=game_id, market=market,
                                 at=far, line=line))
    v = pr.get(side)
    return None if v is None else float(v)
