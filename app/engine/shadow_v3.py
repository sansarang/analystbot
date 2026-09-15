"""[U14 2026-09-15] 섀도 판정 — v3 로 전환해도 되는가.

🔴 **이 모듈은 스위치를 켜지 않는다.** 기준을 재서 "된다/안 된다"를 말할
   뿐이다. 전환 시각은 **사용자가 정한다**(지시문 3대 확인 지점 중 셋째).
🔴 **하나라도 미달이면 전환 불가**다. 넷 중 셋이 좋아도 아니다 — 자기모순이
   하나라도 있으면 그 카드가 나간다는 뜻이고, 그건 수치로 상쇄되지 않는다.
⚠️ 순수 함수다. 표본이 없으면 "표본 없음"이고 통과가 아니다.

기준(1차 결정 2):
  · 카드 생성률 ≥ 98% 이고 **T-30 이전**
  · 자기모순 0
  · 브라이어 ≤ 종전 + 0.005
  · 토큰 ≤ 종전의 2배
"""
from __future__ import annotations

CARD_RATE_MIN = 0.98
BRIER_SLACK = 0.005
TOKEN_MULT_MAX = 2.0
SHADOW_DAYS = 7


def criteria() -> dict:
    """기준 원문. 🔴 이 숫자는 여기에만 있다 — 보고서가 베끼지 않는다."""
    return {
        "카드생성률": f"≥ {CARD_RATE_MIN:.0%} · T-30 이전",
        "자기모순": "0건",
        "브라이어": f"≤ 종전 + {BRIER_SLACK}",
        "토큰": f"≤ 종전 × {TOKEN_MULT_MAX:g}",
        "기간": f"{SHADOW_DAYS}일",
    }


def _rate(n, d):
    return (n / d) if d else None


def evaluate(rows: list | None, *, baseline: dict | None = None) -> dict:
    """섀도 행 목록 → 항목별 판정 + 전환 가부.

    행 모양: `{"day": "2026-09-15", "card": bool, "before_t30": bool,
               "self_contra": bool, "p": float, "hit": 0|1, "tokens": int}`
    `baseline` = `{"brier": float, "tokens": int}` (종전 경로 값).
    """
    rows = list(rows or [])
    n = len(rows)
    days = sorted({r.get("day") for r in rows if r.get("day")})
    b = baseline or {}

    cards = sum(1 for r in rows if r.get("card"))
    t30 = sum(1 for r in rows if r.get("card") and r.get("before_t30"))
    contra = sum(1 for r in rows if r.get("self_contra"))
    scored = [(float(r["p"]), int(r["hit"])) for r in rows
              if r.get("p") is not None and r.get("hit") is not None]
    brier = (sum((p - h) ** 2 for p, h in scored) / len(scored)
             if scored else None)
    tokens = sum(int(r.get("tokens") or 0) for r in rows) or None

    base_brier, base_tokens = b.get("brier"), b.get("tokens")
    items = {
        "카드생성률": {
            "값": _rate(t30, n),
            "기준": CARD_RATE_MIN,
            "통과": (n > 0 and _rate(t30, n) is not None
                     and _rate(t30, n) >= CARD_RATE_MIN),
        },
        "자기모순": {"값": contra, "기준": 0, "통과": n > 0 and contra == 0},
        "브라이어": {
            "값": brier, "기준": (None if base_brier is None
                                  else base_brier + BRIER_SLACK),
            "통과": (brier is not None and base_brier is not None
                     and brier <= base_brier + BRIER_SLACK),
        },
        "토큰": {
            "값": tokens, "기준": (None if base_tokens is None
                                   else base_tokens * TOKEN_MULT_MAX),
            "통과": (tokens is not None and base_tokens is not None
                     and tokens <= base_tokens * TOKEN_MULT_MAX),
        },
    }
    enough = len(days) >= SHADOW_DAYS
    fails = [k for k, v in items.items() if not v["통과"]]
    return {
        "n": n, "일수": len(days), "기간충족": enough,
        "항목": items, "미달": fails,
        # 🔴 기간이 안 찼으면 통과라고 쓰지 않는다. 표본 없음은 통과가 아니다.
        "전환가능": bool(enough and not fails),
        "사유": ("모든 기준 통과" if enough and not fails
                 else (f"{SHADOW_DAYS}일 미충족(현재 {len(days)}일)"
                       if not enough else "미달: " + ", ".join(fails))),
    }
