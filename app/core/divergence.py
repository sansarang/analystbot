"""🔴🔴 **시장 괴리 진단**(P5 · 예측 지시 2026-10-13 23:10 KST) — **표시 전용**.

> 보드가 있으면 **마진 제거 확률**을 우리 확률과 나란히. 결론·등급은 우리 확률로만.
> 차이 **≥ 10%p** 줄은 🔴 **시장 괴리** + 그 경기에서 **⬜ 인 입력 목록**(리그
> 오프셋·대회 이력·축1~3·Elo·XI 판 등)을 자동으로 붙인다.
> ⬜ 입력이 **하나라도** 걸린 괴리 줄은 **결론 상한 "접는다"**. ⬜ 없이 생긴
> 괴리만 조건부까지 허용.

🔴 **마진 제거는 `core/devig` 하나다**(사본 금지) · 시장 확률은 **등급 계산에
   들어가지 않는다**(네 층 §7) — 이 모듈은 **글자와 상한**만 만든다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 🔴 이보다 벌어지면 **괴리**다(지시의 10%p)
CUT = 0.10

#: 🔴 ⬜ 로 셀 입력들 — 카드가 그 이름으로 적는다(사본 금지: 사유 글에서 읽는다)
GAP_NAMES: tuple[tuple[str, str], ...] = (
    ("Elo 기준", "base"), ("리그 오프셋", "league_gap"),
    ("대회 이력", "comp_history"), ("축1~3", "axes"), ("XI 판", "xi"))


def market_triple(prices: list[float]) -> tuple[list[float], str]:
    """🔴 배당 셋 → **마진 제거 확률**(`devig.shin`). 못 하면 `([], 사유)`."""
    rows = [float(x) for x in (prices or []) if x]
    if len(rows) != 3 or min(rows) <= 1.0:
        return [], f"🔴 배당 셋이 아니다({prices!r})"
    from app.core import devig
    got = devig.shin(rows)
    if not got or abs(sum(got) - 1.0) > 1e-6:
        return [], "🔴 마진 제거가 안 됐다"
    return [float(x) for x in got], (
        "마진 제거(Shin) — 원 배당 "
        + " / ".join(f"{x:g}" for x in rows)
        + f" · 마진 {100 * (sum(1 / x for x in rows) - 1):.1f}%")


def rows_of(ours: list[float], market: list[float]) -> list[dict]:
    """🔴 줄마다 `{이름, 우리, 시장, 차이, 괴리}`(홈·무·원정)."""
    out: list[dict] = []
    for i, name in enumerate(("홈", "무", "원정")):
        a = float(ours[i]) if i < len(ours) else None
        b = float(market[i]) if i < len(market) else None
        if a is None or b is None:
            continue
        out.append({"name": name, "ours": a, "market": b, "diff": b - a,
                    "wide": abs(b - a) >= CUT})
    return out


def said_of(ours: list[float], prices: list[float], *,
            gaps: list[str]) -> tuple[str, bool]:
    """🔴🔴 카드 줄 + **상한 여부**. `(글자, 접는다)`.

    🔴 괴리 줄이 있고 **⬜ 입력이 하나라도** 있으면 `접는다` 다(우리가 모르는
       정보로 생긴 차이일 수 있다). ⬜ 가 없으면 **조건부까지** 허용한다.
    """
    said, why = market_triple(prices)
    if not said:
        return f"⬜ **시장 괴리 미산출** — {why}", False
    rows = rows_of(ours, said)
    body = " · ".join(
        f"{r['name']} 우리 {r['ours']:.1%} ↔ 시장 {r['market']:.1%}"
        f"({r['diff']:+.1%}{' 🔴 **괴리**' if r['wide'] else ''})"
        for r in rows)
    wide = [r for r in rows if r["wide"]]
    if not wide:
        return (f"{why} · {body} · ✅ **10%p 이상 벌어진 줄 없다**"
                f" · ⚠️ 등급·결론은 **우리 확률만** 쓴다"), False
    tail = (f" · 🔴 **시장 괴리 {len(wide)}줄**"
            + (f" · ⬜ 입력 — {' · '.join(gaps)}" if gaps
               else " · ⬜ 입력 **없다**"))
    fold = bool(gaps)
    return (f"{why} · {body}{tail}"
            + (" → 🔻 **결론 상한 접는다**(우리가 모르는 정보일 수 있다)"
               if fold else " → 🟡 **조건부까지 허용**(⬜ 없이 생긴 괴리다)")
            + " · ⚠️ 등급·결론은 **우리 확률만** 쓴다", fold)
