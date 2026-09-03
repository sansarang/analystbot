"""[C2] 변수 한 줄 파싱 — 정량 변수를 기계가 읽을 수 있게.

형식(프롬프트 §변수 형식과 **같은 문장**이어야 한다):
  "<리스크 서술> — 발생 시 <홈|원정> 방향 약 N%p · 현재 p에 M%p 기반영 · 근거 <자료 번호>"

🔴 **파싱 실패를 조용히 넘기지 않는다.** 실패는 `unverifiable` 로 남고 로그가
   찍힌다 — 그게 곧 형식 위반 감시다.
⚠️ **판정을 막지 않는다.** M 합이 범위를 넘어도 카드를 반려하지 않고 경고만
   남긴다. 섀도 정신이다 — 감시가 발송을 멈추면 안 된다.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

#: 방향 표기 → 내부 값.
_SIDE = {"홈": "home", "원정": "away"}

_PAT = re.compile(
    r"^(?P<risk>.+?)\s*[—-]\s*발생\s*시\s*(?P<side>홈|원정)\s*방향\s*약\s*"
    r"(?P<n>[-+]?\d+(?:\.\d+)?)\s*%p\s*[·,]\s*현재\s*p에\s*"
    r"(?P<m>[-+]?\d+(?:\.\d+)?)\s*%p\s*기반영\s*[·,]\s*근거\s*(?P<src>.+?)\s*$"
)


def parse_variable(text: str) -> dict | None:
    """한 줄 → {risk, side, n, m, source}. 형식 위반이면 None."""
    if not text:
        return None
    m = _PAT.match(str(text).strip())
    if not m:
        return None
    try:
        n = float(m.group("n"))
        mm = float(m.group("m"))
    except (TypeError, ValueError):
        return None
    return {"risk": m.group("risk").strip(), "side": _SIDE[m.group("side")],
            "n": n, "m": mm, "source": m.group("src").strip()}


def parse_all(verdict: dict) -> list[dict]:
    """판정의 변수 전건. 파싱 실패는 `parsed=None` 으로 **남긴다**(버리지 않는다)."""
    out = []
    for raw in (verdict.get("변수") or []):
        p = parse_variable(raw)
        if p is None:
            logger.info("[variable] 형식 위반 — 정량 파싱 불가: %r", str(raw)[:160])
        out.append({"raw": str(raw), "parsed": p})
    return out


def check_budget(verdict: dict, rows: list[dict] | None = None) -> dict:
    """규칙② — M 의 합이 |p_home − 0.50| 이내인가. **경고만 낸다.**

    반환 {"sum_m", "budget", "ok", "quantified", "total"}.
    """
    rows = rows if rows is not None else parse_all(verdict)
    parsed = [r["parsed"] for r in rows if r["parsed"]]
    sum_m = round(sum(abs(p["m"]) for p in parsed), 2)
    p_home = verdict.get("p_home")
    budget = None
    if p_home is not None:
        try:
            budget = round(abs(float(p_home) - 0.50) * 100, 2)
        except (TypeError, ValueError):
            budget = None
    ok = budget is None or sum_m <= budget + 1e-9
    if not ok:
        # ⚠️ 반려하지 않는다 — 판정을 막으면 그날 카드가 안 나간다.
        logger.warning("[variable] ⚠️ M 합 %.2f%%p > 예산 %.2f%%p — 규칙② 위반 "
                       "(카드는 그대로 나간다)", sum_m, budget)
    return {"sum_m": sum_m, "budget": budget, "ok": ok,
            "quantified": len(parsed), "total": len(rows)}
