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

#: elo 캐시 키의 종목 코드. 🔴 `state.sport`(baseball|soccer)가 아니라
#  **리그 코드**다 — `app/models/team_elo.CACHE_KEY` 가 그렇게 쓴다.
_LEAGUE_CODE = {"KBO": "kbo", "NPB": "npb", "MLB": "mlb"}


def _code(state) -> str:
    lg = (state.league or "").strip()
    return _LEAGUE_CODE.get(lg.upper(), lg.lower())


def _elo_win(elo_home: float, elo_away: float, hfa: float) -> float:
    """ELO 승률식. 400점 차 = 10배."""
    return 1.0 / (1.0 + 10 ** ((float(elo_away) - float(elo_home) - float(hfa)) / 400.0))


async def _load_elo(state, ctx) -> dict:
    """`{팀: 레이팅}`. 주입값이 있으면 그것, 없으면 Redis 캐시.

    🔴 **없으면 빈 dict** 다. 리그 평균으로 메우지 않는다 — 채운 팀과 안 채운
       팀이 같은 근거를 가진 것처럼 보이면 게이트가 오분류한다(U3 리즈 사례).
    """
    if "elo" in (ctx.inject or {}):
        return dict(ctx.inject["elo"] or {})
    if ctx.redis is None:
        return {}
    try:
        from app.models import team_elo as TE

        date = (state.kickoff_utc or "")[:10]
        raw = await TE.load(ctx.redis, _code(state), date)
        return dict(raw or {})
    except Exception as exc:
        logger.warning("[flow:n01] elo 로드 실패 game=%s: %s", state.game_id, exc)
        return {}


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
    elo = await _load_elo(state, ctx)
    eh, ea = _rating(elo.get(state.home)), _rating(elo.get(state.away))
    if eh is None or ea is None:
        miss = [n for n, v in ((state.home, eh), (state.away, ea)) if v is None]
        logger.info("[flow:n01] game=%s elo 미기입 %s — 사전값 없음",
                    state.game_id, miss)
        state.n01_prior = {"p_home": None, "p_draw": None, "p_away": None,
                           "source": "team_elo", "missing": miss}
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
                       "source": "team_elo",
                       "elo": {"home": eh, "away": ea}}
    state.pick_side = "home" if ph >= (pa or 0) else "away"
    logger.info("[flow:n01] game=%s elo %.1f/%.1f → p_home %.3f · pick %s",
                state.game_id, eh, ea, ph, state.pick_side)
    return state
