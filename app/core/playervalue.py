"""🔴🔴 **선수 가치 — 없는 값을 0 으로 더하지 않는다**(사용자 지시 2026-10-12 1번).

> 대체값 = **같은 리그·같은 포지션 선발 선수 가치 중앙값**, 카드에
> **"대체값 — 누구" 🔴**.

🔴 왜 — ⓓ 감사(2026-10-12): 가와사키 선발 11명 중 `Pedro Romano` 가 가치 없음이라
   **0 으로 합산**됐다. 영입 직후 선수·하위 리그 출신은 **늘 0** 이 되고, 그러면
   그 팀 축0 이 **조용히 깎인다**(#3 조용한 0 금지).
⚠️ "같은 리그" 는 **그 경기 선발들**이다 — 두 팀 다 그 리그이고 as-of 정합이다
   (선수단 페이지의 현재 누계를 끌어오지 않는다 · L2).
"""
from __future__ import annotations

import logging
from statistics import median

logger = logging.getLogger(__name__)


def _num(said: object) -> float | None:
    """🔴 `0` 도 **없음**으로 본다 — 0 을 더하면 그 팀이 깎인다."""
    if isinstance(said, (int, float)) and float(said) > 0.0:
        return float(said)
    return None


def fill(rows: list[dict], *, pool: list[dict] | None = None
         ) -> tuple[list[dict], str]:
    """🔴🔴 1번 — 빈 가치를 **중앙값으로 채운다**. `(채운 줄, 사유)`.

    `rows` 한 줄: `{"name", "pos", "value"}`(`fotmob.players_of` 가 주는 꼴).
    `pool` 을 주면 **그 목록에서** 중앙값을 찾는다(같은 리그의 다른 경기 선발).
    ⚠️ 빌릴 값이 아예 없으면 **채우지 않는다**(`None` 그대로 · 지어내지 않는다).
    """
    said_rows = [dict(x) for x in (rows or [])]
    box = [dict(x) for x in (pool if pool is not None else said_rows)]
    by_pos: dict[str, list[float]] = {}
    whole: list[float] = []
    for one in box:
        got = _num(one.get("value"))
        if got is None:
            continue
        whole.append(got)
        by_pos.setdefault(str(one.get("pos") or ""), []).append(got)
    filled: list[str] = []
    no_pos: list[str] = []
    out: list[dict] = []
    for one in said_rows:
        got = _num(one.get("value"))
        if got is not None:
            out.append({**one, "value": got, "filled": False})
            continue
        pos = str(one.get("pos") or "")
        said_pool = by_pos.get(pos) or []
        if said_pool:
            out.append({**one, "value": round(median(said_pool), 2),
                        "filled": True})
            filled.append(str(one.get("name") or "?"))
        elif whole:
            out.append({**one, "value": round(median(whole), 2),
                        "filled": True})
            filled.append(str(one.get("name") or "?"))
            no_pos.append(str(one.get("name") or "?"))
        else:
            out.append({**one, "value": None, "filled": False})
    bits: list[str] = []
    if filled:
        bits.append(f"🔴 **대체값 — {', '.join(filled[:4])}**"
                    f"({len(filled)}명 · 같은 리그 선발 **중앙값**)")
    if no_pos:
        bits.append(f"⚠️ 같은 **포지션**이 없어 선발 전체 중앙값으로: "
                    + ", ".join(no_pos[:3]))
    if not whole and any(_num(x.get("value")) is None for x in said_rows):
        bits.append("🔴 가치를 **못 채웠다** — 빌릴 값이 하나도 없다")
    return out, " · ".join(bits)


def log_sum(rows: list[dict]) -> tuple[float | None, int]:
    """🔴 축0 이 쓰는 **로그 합**과 **센 선수 수**. ⚠️ `None` 은 안 센다."""
    import math
    got = [float(x["value"]) for x in (rows or [])
           if _num(x.get("value")) is not None]
    if not got:
        return None, 0
    return round(math.log1p(sum(got)), 4), len(got)
