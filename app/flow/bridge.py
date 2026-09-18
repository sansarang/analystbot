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

import json
import logging

logger = logging.getLogger(__name__)


def _sport_of(row: dict) -> str:
    """리그 코드 → `analysis_state.sport`(baseball|soccer) 규약."""
    sp = (row.get("sport") or "").lower()
    return "soccer" if sp == "soccer" else "baseball"


#: 우리 득점 분포 확률. 🔴 **원본은 `scoring.game_distribution`** 이고
#  `pipeline.py:4030` 이 원장에 싣는다 — 여기서는 **읽기만** 한다(재계산 금지).
#  ⚠️ 실측 2026-09-19: 이 칸이 **전건 NULL** 이다. 판정이 실패하면 그 뒤의 λ
#     산출 블록 자체가 안 돌기 때문이다(`lambda_missing` 도 None 이었다).
#     즉 LLM 사슬이 살아야 이 값이 찬다 — 배선은 그때를 위해 먼저 해 둔다.
_MODEL_SQL = """
    SELECT game_id, model_probs
      FROM pick_ledger
     WHERE is_final AND model_probs IS NOT NULL
       AND game_id = ANY($1::bigint[])
"""


#: 오늘 슬레이트. 🔴 **위성과 같은 조건**이다(`satellite._DUE_SQL`) — 그쪽이
#  원본이고 여기서는 같은 규칙을 쓴다: 예정 · 앞으로 N시간 안에 시작.
_SLATE_SQL = """
    SELECT id, sport, league, home, away, starts_at
      FROM games
     WHERE status = 'scheduled'
       AND starts_at BETWEEN now() AND now() + make_interval(hours => $1)
     ORDER BY starts_at
"""


async def run_today(pool, redis, *, lookahead_h: int = 24, settings=None) -> dict:
    """오늘 슬레이트 전체를 섀도로 돌린다.

    🔴 **창(window)에 매이지 않는다.** 실사고 2026-09-19: `run_slate` 을
       `mlb_pregame_poll` 안에 넣었더니 그 함수가 폴링 창 밖에서 조기 반환해
       **한 번도 돌지 않았다**. 관측은 창과 무관해야 한다.
    """
    if pool is None:
        return {"games": 0, "stopped": {}, "sent": 0, "why": "풀 없음"}
    try:
        rows = [dict(r) for r in await pool.fetch(_SLATE_SQL, int(lookahead_h))]
    except Exception as exc:
        logger.warning("[flow] 슬레이트 조회 실패: %s", exc)
        return {"games": 0, "stopped": {}, "sent": 0, "why": "조회 실패"}
    return await run_slate(pool, redis, rows, settings=settings)


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

    # 🔴 [2026-09-19] **파생 확률을 슬레이트 단위로 한 번 읽는다.**
    #    없으면 ⑪의 구조 후보가 0 이고, `동의` 라벨이 만든 파생 가설이 쓰일
    #    자리가 없다. 경기마다 조회하면 질의가 N배가 되므로 한 번에 읽는다.
    model_by_game: dict = {}
    if pool is not None:
        try:
            ids = [int(r["id"]) for r in rows if str(r.get("id") or "").isdigit()]
            if ids:
                for m in await pool.fetch(_MODEL_SQL, ids):
                    raw = m["model_probs"]
                    model_by_game[int(m["game_id"])] = (
                        json.loads(raw) if isinstance(raw, str) else raw)
        except Exception as exc:
            logger.warning("[flow] 파생 확률 조회 실패: %s", exc)
    if rows and not model_by_game:
        # 🔴 조용한 0 금지 — "모델이 없다"와 "안 읽었다"는 다르다.
        logger.info("[flow] 파생 확률 0건 — 구조 픽 후보가 서지 않는다 "
                    "(판정이 실패하면 λ 산출 블록이 안 돈다)")

    out: dict = {"games": 0, "stopped": {}, "sent": 0}
    for r in rows:
        game = {"game_id": r.get("id") or r.get("game_id"),
                "sport": _sport_of(r), "league": r.get("league") or "",
                "home": r.get("home") or "", "away": r.get("away") or "",
                "kickoff_utc": r.get("starts_at")}
        # 🔴 경기마다 주입을 갈아끼운다. 예산(`ctx.budget`)은 **슬레이트 단위로
        #    유지**된다 — 그래서 `inject` 만 바꾸고 ctx 를 새로 만들지 않는다.
        gid = game["game_id"]
        ctx.inject = {"model_probs": model_by_game.get(
            int(gid) if str(gid).isdigit() else -1)}
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
