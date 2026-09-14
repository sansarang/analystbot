"""[PRI-1] 사전값 — 티어 표 + 올해 성적. **검색 전에** 확정한다.

지시문 Phase 2 (2026-09-13). 공식은 거기 적힌 그대로다.

🔴 **사전값은 검색 전에 확정한다.** 검색 후 적으면 뉴스 어조에 끌린다.
🔴 **`p_prior` 는 `p_code` 에 더하지 않는다**(지시문 금지 사항 · 3차 결정 G).
   쓰이는 곳은 Phase 3 괴리 게이트와 카드 서술 **둘뿐**이다.
⚠️ 순수 함수 모듈이다 — DB·HTTP 를 부르지 않는다. 성적은 호출부가 넘긴다.
"""
from __future__ import annotations

import functools
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

#: 티어 → 기준 레이팅. 지시문 2-2 그대로. **여기 한 곳에만 적는다.**
TIER_ELO = {1: 1700, 2: 1620, 3: 1560, 4: 1510, 5: 1460}

#: 티어가 비어 있을 때 쓰는 자리. 리그 중앙이다.
TIER_DEFAULT = 3

#: 티어 가중치가 바닥에 닿는 경기 수. 그 뒤로는 올해 성적이 0.7 을 쥔다.
W_TIER_FULL_GP = 12
W_TIER_FLOOR = 0.3

#: 올해 성적 → 레이팅. 승점률 0 이면 1400, 1 이면 1900.
ELO_BASE, ELO_SPAN = 1400.0, 500.0

#: 홈 이점(레이팅 점수). 축구가 야구보다 크다.
HFA_SOCCER, HFA_BASEBALL = 60.0, 25.0

#: 무승부 곡선. 격차가 벌어질수록 무승부가 줄어든다.
DRAW_BASE, DRAW_SLOPE = 0.27, 0.00035
DRAW_MIN, DRAW_MAX = 0.10, 0.34

#: 최근 5경기가 **극단일 때만** 주는 보정(%p).
FORM_PP = 4.0

TIER_DIR = Path("config/tiers")


def w_tier(games_played: int) -> float:
    """티어 가중치. 경기가 쌓일수록 내려가고 `W_TIER_FLOOR` 에서 멈춘다."""
    gp = max(0, int(games_played or 0))
    return max(W_TIER_FLOOR, 1.0 - gp / W_TIER_FULL_GP)


def team_elo(tier: int | None, *, w: int, d: int, lose: int) -> tuple[float, str]:
    """티어 + 올해 성적 → 레이팅. 반환 `(elo, prior_src)`.

    🔴 티어가 비면 **중앙(3)** 으로 계산하고 그 사실을 `prior_src` 에 남긴다.
       조용히 메우면 채웠는지 안 채웠는지를 영영 모른다.
    """
    src = "tier"
    if tier is None:
        tier, src = TIER_DEFAULT, "tier:미기입"
    base = float(TIER_ELO.get(int(tier), TIER_ELO[TIER_DEFAULT]))
    gp = int(w or 0) + int(d or 0) + int(lose or 0)
    if gp <= 0:
        return base, src
    pts_rate = (3 * int(w) + int(d)) / (3.0 * gp)
    elo_this = ELO_BASE + ELO_SPAN * pts_rate
    k = w_tier(gp)
    return k * base + (1.0 - k) * elo_this, src


def _logistic(diff: float) -> float:
    return 1.0 / (1.0 + 10 ** (-diff / 400.0))


def soccer_prior(elo_home: float, elo_away: float) -> tuple[float, float, float]:
    """축구 3-way. 반환 `(홈, 무, 원정)` — 합은 1 이다."""
    d = float(elo_home) - float(elo_away) + HFA_SOCCER
    raw = _logistic(d)
    draw = min(DRAW_MAX, max(DRAW_MIN, DRAW_BASE - DRAW_SLOPE * abs(d)))
    home = raw * (1 - draw)
    away = (1 - raw) * (1 - draw)
    # ⚠️ 반올림으로 합이 1 에서 어긋나지 않게 마지막 칸을 잔차로 채운다
    #    (`market_edge.implied_probs` 와 같은 처리).
    h, dr = round(home, 4), round(draw, 4)
    return h, dr, round(1.0 - h - dr, 4)


def baseball_prior(elo_home: float, elo_away: float, settings=None) -> float:
    """야구 2-way 홈 승 확률. ⚠️ 절사는 `scoring.cap_probability` 가 원본이다."""
    from app.engine.scoring import cap_probability

    d = float(elo_home) - float(elo_away) + HFA_BASEBALL
    capped, _ = cap_probability(_logistic(d), "mlb", settings)
    return round(float(capped), 4)


def form_pp(last5: str) -> float:
    """최근 5경기 → 보정(%p). **극단일 때만** 준다.

    전승·무패(패 0) → +4 · 전패·무승(승 0) → −4 · 그 외 0.
    ⚠️ 5경기가 안 되면 0 이다 — 얇은 표본에 보정을 붙이지 않는다.
    """
    s = (last5 or "").upper()
    if len(s) != 5 or set(s) - set("WDL"):
        return 0.0
    if "L" not in s:
        return FORM_PP
    if "W" not in s:
        return -FORM_PP
    return 0.0


@functools.lru_cache(maxsize=32)
def load_season(league: str) -> str:
    """그 리그 티어 파일의 `season` 문자열. 없으면 빈 문자열."""
    import yaml

    p = TIER_DIR / f"{league}.yaml"
    if not p.exists():
        return ""
    try:
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("[prior] 시즌 읽기 실패 %s: %s", p, exc)
        return ""
    return str(doc.get("season") or "")


def season_start(league: str):
    """올해 성적을 세기 시작하는 날. **티어 파일의 `season` 이 원본이다.**

    🔴 달력 규칙을 새로 만들지 않는다 — `"2026-27"`(가을~봄 리그)은 그해
       7월 1일, `"2026"`(봄~가을 리그·야구)은 그해 1월 1일이다. 형식이
       그것을 이미 말하고 있다.
    ⚠️ 모르면 `None` — 호출부가 "성적 없음"으로 읽는다. 지어내지 않는다.
    """
    from datetime import date as _date

    raw = (load_season(league) or "").strip()
    if not raw:
        return None
    head = raw.split("-")[0]
    if not head.isdigit() or len(head) != 4:
        return None
    y = int(head)
    return _date(y, 7, 1) if "-" in raw else _date(y, 1, 1)


@functools.lru_cache(maxsize=32)
def load_tiers(league: str) -> dict:
    """`config/tiers/{league}.yaml` → `{팀: 티어|None}`. 없으면 빈 dict."""
    import yaml

    p = TIER_DIR / f"{league}.yaml"
    if not p.exists():
        logger.info("[prior] 티어 표 없음: %s", p)
        return {}
    try:
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("[prior] 티어 표 읽기 실패 %s: %s", p, exc)
        return {}
    return dict(doc.get("tiers") or {})
