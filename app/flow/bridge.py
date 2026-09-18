"""[v1.4 STEP 13] 운영 경로 다리 — **스케줄러가 새 파이프라인을 부르는 자리.**

🔴 STEP 13 을 처음 붙일 때 기존 발송에 **배타 가드만** 걸고 `run_game` 호출을
   잇지 않았다. 그러면 `PIPELINE_V14=true` 가 "새 경로를 켠다"가 아니라
   "카드를 끈다"가 된다 — 관측할 것이 없다. 이 파일이 그 구멍을 메운다.

🔴 **기존 판정을 건드리지 않는다.** 새 경로는 같은 슬레이트를 **따로** 돌고
   자기 상태(`analysis_runs`)만 남긴다. 발송은 `PIPELINE_V14_SEND` 가 가른다.
⚠️ 한 경기 실패가 나머지를 막지 않는다 — 경기별 try 로 감싼다.
⚠️ 예산은 슬레이트 단위로 **한 번** 만들어 경기마다 차감한다(§3 상한).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _sport_of(row: dict) -> str:
    """리그 코드 → `analysis_state.sport`(baseball|soccer) 규약."""
    sp = (row.get("sport") or "").lower()
    return "soccer" if sp == "soccer" else "baseball"


async def run_slate(pool, redis, rows: list, *, settings=None) -> dict:
    """슬레이트 1회. 반환 `{"games", "stopped": {사유: 수}, "sent"}`.

    🔴 **조용한 0 금지** — 어디서 몇 건이 멈췄는지 사유별로 센다. 그 분포가
       24h 섀도 관측의 보고 대상이다(지시문 §7).
    """
    from app.config import get_settings
    from app.flow.ctx import Ctx
    from app.flow.rules import get as rget
    from app.flow.run import run_game

    s = settings or get_settings()
    if not getattr(s, "pipeline_v14", False):
        return {"games": 0, "stopped": {}, "sent": 0, "why": "스위치 꺼짐"}

    # §3 예산 — 슬레이트 30% · 경기당 상한은 ⑤가 따로 본다.
    ratio = float(rget("deepsearch_cap.slate_ratio", 0.30) or 0.30)
    per_game = int(rget("deepsearch_cap.per_game", 5) or 5)
    cap = max(per_game, int(round(len(rows) * ratio)) * per_game)
    ctx = Ctx(pool=pool, redis=redis, settings=s,
              budget={"searches": 0, "slate_cap": cap})

    out: dict = {"games": 0, "stopped": {}, "sent": 0}
    for r in rows:
        game = {"game_id": r.get("id") or r.get("game_id"),
                "sport": _sport_of(r), "league": r.get("league") or "",
                "home": r.get("home") or "", "away": r.get("away") or "",
                "kickoff_utc": r.get("starts_at")}
        try:
            st = await run_game(game, ctx)
        except Exception as exc:
            logger.warning("[flow] game=%s 실행 실패: %s", game["game_id"], exc)
            out["stopped"]["error"] = out["stopped"].get("error", 0) + 1
            continue
        out["games"] += 1
        key = st.stop_reason or "완주"
        out["stopped"][key] = out["stopped"].get(key, 0) + 1
        if (st.n13_send or {}).get("sent"):
            out["sent"] += 1
    logger.info("[flow] 슬레이트 %d경기 · 멈춤 %s · 발송 %d (예산 %d/%d)",
                out["games"], out["stopped"], out["sent"],
                ctx.budget["searches"], cap)
    return out
