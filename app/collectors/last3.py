"""최근 3경기 패킷 공통. 시즌 ERA·xwOBA는 넣지 않는다.

허용: 각 상대의 **현재** 순위·승률 1줄 (상대 수준 맥락).
"""
from __future__ import annotations

BANNED_KEYS = ("era", "era_season", "xwoba", "woba", "ops", "obp", "siera", "xfip")


def attach_opponent_context(row: dict, standings: dict | None) -> dict:
    """상대 수준 맥락 1줄. 시즌 ERA가 아니다. 없는 칸은 만들지 않는다."""
    opp = row.get("opponent")
    st = (standings or {}).get(opp) or {}
    if st.get("rank") is not None:
        row["opponent_rank"] = st["rank"]
    wp = st.get("win_pct")
    if wp is None:
        w, l = st.get("w"), st.get("l")
        try:
            w_i, l_i = int(w), int(l)
        except (TypeError, ValueError):
            w_i = l_i = None
        if w_i is not None and l_i is not None and (w_i + l_i) > 0:
            wp = round(w_i / (w_i + l_i), 3)
    if wp is not None:
        row["opponent_win_pct"] = wp
    return row


def strip_banned(obj: dict) -> dict:
    return {k: v for k, v in obj.items() if k not in BANNED_KEYS}
