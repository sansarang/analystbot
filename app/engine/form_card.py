"""야구 텔레그램 카드 — 매치업 JSON만 매핑. 없는 칸을 만들지 않는다."""
from __future__ import annotations

from app.config import get_settings


def _team(name: str) -> str:
    from app.bot.aliases import kr_team

    return kr_team(name or "?")


def _park(jg: dict) -> str:
    r = jg.get("research") or {}
    for v in (jg.get("stadium"), jg.get("venue"), r.get("park"), r.get("stadium")):
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict) and (v.get("name") or v.get("park")):
            return str(v.get("name") or v.get("park")).strip()
    return ""


def favored_side_and_p(jg: dict) -> tuple[str | None, float | None]:
    """우세 사이드와 그 승률. p_home 기반. 없으면 (None, None)."""
    m = jg.get("matchup") or {}
    p = m.get("p_home")
    if p is None:
        p = jg.get("p_claude")
    try:
        p = float(p)
    except (TypeError, ValueError):
        return None, None
    side = m.get("우세")
    if side == "away":
        return "away", 1.0 - p
    if side == "home":
        return "home", p
    if side == "박빙":
        return "home" if p >= 0.5 else "away", p if p >= 0.5 else 1.0 - p
    if p >= 0.5:
        return "home", p
    return "away", 1.0 - p


def traffic_light(p: float | None, settings=None) -> str:
    """표시 전용. 추천 게이트가 아니다."""
    s = settings or get_settings()
    if p is None:
        return "⚪"
    if p >= s.signal_green_prob:
        return "🟢"
    if p >= s.min_win_prob:
        return "🟡"
    return "🔴"


def rec_label(jg: dict, settings=None) -> str:
    s = settings or get_settings()
    sport = jg.get("sport") or ""
    if sport == "npb" and not s.npb_last3_verified:
        return "NPB: 참고용"
    if jg.get("form_unavailable") or jg.get("judgement_void"):
        return "보드만"
    from app.collectors.lineups import pick_state as _ps

    state = jg.get("pick_state")
    if state is None:
        state = _ps(jg.get("lineup_status"))[0]
    if state != "final":
        return "보드만"
    if jg.get("judge_confidence") == "low" or jg.get("judge_pass"):
        return "보드만"
    side, p = favored_side_and_p(jg)
    if p is None:
        return "보드만"
    need = s.min_win_prob
    if side == "away":
        need += s.away_prob_penalty
    return "추천" if p >= need else "보드만"


def render_form_card(jg: dict, sport: str | None = None, *,
                     revision: bool = False) -> str:
    """판정 JSON → 카드 본문. 언더오버·런라인·F5 없음."""
    sport = sport or jg.get("sport") or ""
    home, away = _team(jg.get("home") or "?"), _team(jg.get("away") or "?")
    league = jg.get("league") or sport.upper()
    when = jg.get("starts_at_kst") or ""
    park = _park(jg)
    m = jg.get("matchup") or {}
    side, p = favored_side_and_p(jg)
    fav_name = home if side == "home" else away if side == "away" else None

    lines = [f"{league}  {away} @ {home}"]
    info = " ".join(x for x in (when, park) if x)
    if info:
        lines.append(info)
    if fav_name is not None and p is not None:
        lines.append(f"우세 {fav_name} {p * 100:.1f}%")
        lines.append(f"신호등 {traffic_light(p)}")
    reasons = [str(x).strip() for x in (m.get("근거") or []) if str(x).strip()]
    for i, r in enumerate(reasons[:3], 1):
        lines.append(f"근거{i} {r}")
    variables = [str(x).strip() for x in (m.get("변수") or []) if str(x).strip()]
    for v in variables[:2]:
        lines.append(f"변수 {v}")
    news = m.get("뉴스반영") or {}
    if isinstance(news, dict) and news.get("적용"):
        adj = news.get("조정폭") or ""
        why = news.get("사유") or ""
        bit = " ".join(str(x) for x in (adj, why) if x).strip()
        if bit:
            lines.append(f"뉴스반영 {bit}")
    lines.append(rec_label(jg))
    if revision:
        lines.append("라인업 변경 재판정")
    return "\n".join(lines)
