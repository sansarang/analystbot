"""[v1.4 STEP 2] ① 사전값 — **시장을 보기 전에 우리 판단을 적는다.**

🔴 CLAUDE.md "페이블처럼 분석한다": 순서가 이 봇의 정체다. 이 노드는 배당을
   **읽지 않는다** — 읽으면 앵커링이고, 그러면 "우리가 시장과 다르다"를 잴 수 없다.
🔴 자료12 team_elo(팀당 1값)만 쓴다. **시즌 누적표(타율·ERA·승률)는 금지**
   (CLAUDE.md 대원칙 · v1.4 동결 규칙 6).
⚠️ elo 를 못 구하면 **지어내지 않는다** — `p_home=None` 이고, ③ 게이트가
   그것을 보드 고정으로 읽는다.
"""
from __future__ import annotations

import logging
import math

from app.flow import rules as R

logger = logging.getLogger(__name__)

NODE = "n01_prior"

def _code(state) -> str:
    """elo 캐시 키의 코드. 🔴 규칙의 원본은 `team_elo.code_for` **한 곳**이다.

    ⚠️ 종전에는 이 파일이 규칙을 따로 갖고 있어 쓰는 쪽과 어긋났다
       (`elo:EPL:…` 로 쓰고 `elo:epl:…` 로 읽었다 — SELO-1c).
    """
    from app.models.team_elo import code_for

    return code_for(state.league, state.sport)


def _elo_win(elo_home: float, elo_away: float, hfa: float) -> float:
    """ELO 승률식. 400점 차 = 10배."""
    return 1.0 / (1.0 + 10 ** ((float(elo_away) - float(elo_home) - float(hfa)) / 400.0))


#: 뒤로 걸어가는 날 수. 🔴 갱신을 한 번 놓쳤다고 슬레이트 전체가 보드고정이
#  되면 안 된다. 내보내기가 이미 같은 규약을 쓴다(`for_fable.resolve` 3일).
#  ⚠️ 무한정 걸어가지 않는다 — 오래된 레이팅은 실력이 아니라 기억이다.
ELO_LOOKBACK_DAYS = 3


async def _load_elo(state, ctx) -> tuple[dict, str | None]:
    """`({팀: 레이팅}, asof)`. 주입값이 있으면 그것, 없으면 Redis 캐시.

    🔴 **없으면 빈 dict** 다. 리그 평균으로 메우지 않는다 — 채운 팀과 안 채운
       팀이 같은 근거를 가진 것처럼 보이면 게이트가 오분류한다(U3 리즈 사례).
    🔴 [ELO-1] 오늘 키가 없으면 **최대 3일 뒤로 걸어간다.** `team_elo` 에는
       전용 갱신 잡이 없고 옛 파이프라인의 게으른 폴백 하나뿐인데,
       `PIPELINE_V14` 가 그 경로를 지나쳐 새 키가 안 생긴다(실측 2026-09-19:
       운영 Redis 에 `elo:*` 가 09-18 세 개뿐, 36경기 전건 보드고정).
    🔴 **어느 날짜 값을 썼는지 돌려준다.** 없으면 "오래된 레이팅으로 판정했다"를
       영영 못 잡는다.
    """
    if "elo" in (ctx.inject or {}):
        return dict(ctx.inject["elo"] or {}), "inject"
    if ctx.redis is None:
        return {}, None
    try:
        from datetime import date as _date
        from datetime import timedelta as _td

        from app.models import team_elo as TE

        base = _date.fromisoformat((state.kickoff_utc or "")[:10])
        for back in range(0, ELO_LOOKBACK_DAYS + 1):
            day = (base - _td(days=back)).isoformat()
            raw = await TE.load(ctx.redis, _code(state), day)
            if raw:
                if back:
                    logger.info("[flow:n01] game=%s elo %s 값을 쓴다 (%d일 전)",
                                state.game_id, day, back)
                return dict(raw), day
        return {}, None
    except Exception as exc:
        logger.warning("[flow:n01] elo 로드 실패 game=%s: %s", state.game_id, exc)
        return {}, None


def _rating(box) -> float | None:
    """`{'레이팅': 1515.1, …}` 또는 숫자. 모르면 None."""
    if isinstance(box, dict):
        v = box.get("레이팅", box.get("rating"))
        return float(v) if v is not None else None
    try:
        return float(box)
    except (TypeError, ValueError):
        return None


async def run(state, ctx):
    """① 사전값. `p_home`·`p_draw`·`p_away` 와 `pick_side` 를 정한다."""
    elo, asof = await _load_elo(state, ctx)
    eh, ea = _rating(elo.get(state.home)), _rating(elo.get(state.away))
    if eh is None or ea is None:
        miss = [n for n, v in ((state.home, eh), (state.away, ea)) if v is None]
        logger.info("[flow:n01] game=%s elo 미기입 %s — 사전값 없음",
                    state.game_id, miss)
        state.n01_prior = {"p_home": None, "p_draw": None, "p_away": None,
                           "source": "team_elo", "asof": asof, "missing": miss}
        return state

    sport = (state.sport or "").lower()
    if sport == "soccer":
        # 🔴 3-way. `1 - p_home` 은 원정 확률이 아니다 — 무승부 질량을 먼저 뺀다.
        raw = _elo_win(eh, ea, float(R.get("hfa_elo.soccer", 0) or 0))
        pd = float(R.get("draw_prior", 0.26))
        ph, pa = raw * (1 - pd), (1 - raw) * (1 - pd)
    else:
        hfa = float(R.get(f"hfa_elo.{_code(state)}", 0) or 0)
        ph = _elo_win(eh, ea, hfa)
        pd, pa = None, 1.0 - ph

    state.n01_prior = {"p_home": round(ph, 4),
                       "p_draw": None if pd is None else round(pd, 4),
                       "p_away": round(pa, 4),
                       "source": "team_elo", "asof": asof,
                       "elo": {"home": eh, "away": ea}}
    state.pick_side = "home" if ph >= (pa or 0) else "away"
    logger.info("[flow:n01] game=%s elo %.1f/%.1f → p_home %.3f · pick %s",
                state.game_id, eh, ea, ph, state.pick_side)
    return state
