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
from datetime import UTC, date

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


#: [ELO-1] 사전값 레이팅을 만들 수 있는 종목. 🔴 축구는 뺐다 —
#  `team_elo.refresh` 는 `WHERE sport = $1` 로 긁는데 축구 캐시 키는 **리그
#  코드**라 종목으로 긁으면 리그 간 비교가 된다. `team_elo` 머리말이 금지한
#  것이다("리그 안에서만 의미가 있다"). 축구는 표본부터 재야 하고 별건이다.
ELO_SPORTS = ("mlb", "kbo", "npb")


async def ensure_elo(pool, redis, sport: str, date: str, *, refresh=None) -> bool:
    """그 (종목, 날짜) 레이팅이 캐시에 있게 한다. 반환: 쓸 수 있나.

    🔴 **슬레이트 앞에서 한 번** 부른다. 경기마다 부르면 재계산이 36배다.
    🔴 `team_elo` 에는 전용 갱신 잡이 없다 — 쓰는 곳이 옛 파이프라인의 게으른
       폴백 하나뿐인데(`app/pipeline.py:2915`) `PIPELINE_V14` 가 그 경로를
       지나친다. 그래서 새 경로가 같은 일을 해야 한다.
    ⚠️ `elo_refresh_weekly` 는 다른 물건이다 — 축구 `soccer_elo`(CSV 재피팅)다.
    """
    if redis is None:
        return False
    try:
        from app.models import team_elo as TE

        if await TE.load(redis, sport, date):
            return True
        if pool is None:
            return False
        fn = refresh or TE.refresh
        got = await fn(pool, redis, sport, date)
        return bool(got)
    except Exception as exc:
        logger.warning("[flow] elo 보장 실패 %s %s: %s", sport, date, exc)
        return False


#: 선발 교체 메모의 표지. 🔴 `lineups.py` 가 `f"{side} 선발 변경: A → B"` 로
#  만든다 — 그 문구가 원본이고 여기서 새로 짓지 않는다.
STARTER_CHANGE_MARK = "선발 변경"


def rejudge_signals_of(cg: dict | None) -> dict:
    """판정 캐시 한 경기 → ⑩이 읽는 신호.

    🔴 `pipeline.starter_changed` 를 **쓰지 않는다.** 그 칸의 정의는
       `lineup_status == "conflict"` 이고 그건 *소스 불일치*이지 선발 교체가
       아니다. ⑩ 머리말은 트리거가 "`starter_change_notes` 가 낸 줄"이라고
       적고 있으므로 그 줄을 본다.
       ⚠️ 저 칸은 `deep.needs_refresh` 가 쓰고 있어 건드리지 않는다.
    ⚠️ `lineup_just_confirmed` 는 `lineup_confirmed_at` 에 의존한다 —
       LIN-1 전에는 KBO·NPB 가 그 칸을 안 적어 구조적으로 항상 False 였다.
    """
    cg = cg or {}
    notes = cg.get("lineup_notes") or []
    if isinstance(notes, str):
        notes = [notes]
    return {
        "lineup_confirmed": bool(cg.get("lineup_just_confirmed")),
        "starter_changed": any(STARTER_CHANGE_MARK in str(n) for n in notes),
    }


def model_probs_from_cache(jg: dict | None, *, lines: dict | None = None,
                           settings=None) -> dict | None:
    """판정 캐시의 `research` 로 λ 를 세우고 전 마켓 확률을 만든다.

    🔴 **왜 여기서 만드나.** 옛 파이프라인은 야구에서 λ 경로를 통째로 건너뛴다
       (`pipeline.py:3763` · SEND-1 결정 B-1 2026-09-13). 그래서
       `pick_ledger.model_probs` 가 1,382행 전건 NULL 이고 ⑪의 구조 후보가
       0 이었다. **그 결정을 되돌리지 않는다** — 옛 발송 경로의 확률이 바뀐다.
       v1.4 흐름은 별도 경로이므로 여기서 따로 계산한다.
    🔴 계수를 만지지 않는다 — 30건 채점 전 동결(지시문 3-4 교정 원칙).
    ⚠️ 재료가 없으면 **None** 이다. "모델이 없다"와 "안 불렀다"는 다르다.
    """
    if not jg:
        return None
    sport = (jg.get("sport") or "").lower()
    if sport not in ("mlb", "kbo", "npb"):
        return None
    try:
        from app.engine.scoring import mlb_lambdas, mlb_market_probs

        lam = mlb_lambdas(jg, jg.get("research") or {}, settings, sport=sport)
        if not lam.home or not lam.away:
            logger.info("[flow] λ 못 세움 game=%s missing=%s",
                        jg.get("game_id"), lam.missing)
            return None
        return mlb_market_probs(lam.home, lam.away, lines=lines, settings=settings)
    except Exception as exc:
        logger.warning("[flow] 파생 확률 계산 실패 game=%s: %s", jg.get("game_id"), exc)
        return None


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

    # 🔴 [ELO-1] **슬레이트 앞에서 사전값 재료를 보장한다.** 이게 없으면
    #    ①이 `p_home=None` 을 내고 ③이 전건 보드고정으로 읽는다
    #    (실측 2026-09-19: 36경기 전건).
    #    ⚠️ 키는 **킥오프 UTC 날짜**다 — `n01_prior._load_elo` 와 같은 기준을
    #       쓴다. 여기서 KST 를 쓰면 하루 어긋나 보장이 헛돈다.
    want: set = set()
    for r in rows:
        sp = (r.get("sport") or "").lower()
        if sp in ELO_SPORTS and r.get("starts_at") is not None:
            want.add((sp, r["starts_at"].astimezone(UTC).date().isoformat()))
    for sp, day in sorted(want):
        ok = await ensure_elo(pool, redis, sp, day)
        logger.info("[flow] elo 보장 %s %s — %s", sp, day, "있음" if ok else "없음")


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
    # 🔴 [MOD-1] 판정 캐시를 **슬레이트마다 한 번** 읽는다 — 경기마다 읽으면
    #    같은 문서를 N번 파싱한다. 파생 확률의 재료(`research`)가 여기 있다.
    cache_by_game: dict = {}
    if redis is not None:
        from datetime import timedelta as _td
        for sp, day in sorted(want):
            for d in (day, (date.fromisoformat(day) - _td(days=1)).isoformat()):
                try:
                    raw = await redis.get(f"analysis:{sp}:{d}")
                except Exception:
                    raw = None
                if not raw:
                    continue
                try:
                    doc = json.loads(raw)
                except ValueError:
                    continue
                for cg in doc.get("games") or []:
                    cache_by_game.setdefault(str(cg.get("game_id")), cg)
                break
        made = 0
        for gid, cg in cache_by_game.items():
            if gid in {str(k) for k in model_by_game}:
                continue          # 원장에 있으면 그것이 먼저다
            got = model_probs_from_cache(cg, settings=s)
            if got:
                model_by_game[int(gid)] = got
                made += 1
        logger.info("[flow] 파생 확률 — 원장 %d건 · 캐시에서 계산 %d건",
                    len(model_by_game) - made, made)

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
        # 🔴 [REJ-1] ⑩ 재판정 신호도 함께 준다. 종전에는 `model_probs` 하나만
        #    줘서 `rejudge_signals` 가 영원히 빈 dict 였고 `n10_rejudge` 행이
        #    0건이었다(Phase 0 D-7).
        ctx.inject = {"model_probs": model_by_game.get(
            int(gid) if str(gid).isdigit() else -1),
            "rejudge_signals": rejudge_signals_of(cache_by_game.get(str(gid)))}
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
