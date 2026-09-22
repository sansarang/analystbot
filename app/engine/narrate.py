"""[NOLLM] 템플릿 서술 — **LLM 을 부르지 않는다.**

사용자 2026-09-22: "판정은 원래 코드에서 낸다… **서술도 템플릿으로 바꿔라**"

🔴 **순수 함수다.** LLM·HTTP·DB 호출이 0건이다(`hypothesis.py` 와 같은 규약).
   계약이 그것을 잠근다.

🔴 **지어내지 않는다.** 있는 값만 문장으로 옮긴다. 값이 없으면 그 줄을 **빼고**,
   없는 것을 "없다"고 단정하지 않는다 — 절대 규칙 6(재료 없으면 분석 생성 금지).

⚠️ 이 글은 LLM 이 쓰던 `🧠 분석` 블록을 대신한다. 종전 글은 문장이 유려했지만
   **근거가 자료와 어긋나는 일이 있었다**(SRCH-6 전례: 제미니 분석글 4/4 가
   0자로 카드에 닿았고, ORD-15 는 DB 참조가 승자를 바꿨는데 서술은 옛 팀을
   설명하고 있었다). 템플릿은 그 어긋남이 구조적으로 불가능하다 — **쓰는 값이
   곧 보여주는 값**이다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 확률을 사람 말로. 🔴 숫자를 그대로 쓰지 않는다 — `p_code` 는 시장 뼈대라
#  "우리가 계산했다"로 읽히면 안 된다(실측: p_code == p_market 이 80%).
_BANDS = ((0.62, "뚜렷하게"), (0.56, "다소"), (0.0, "근소하게"))


def _band(p: float) -> str:
    for lo, word in _BANDS:
        if p >= lo:
            return word
    return "근소하게"


def _team(jg: dict, side: str) -> str:
    """표시용 팀 이름. 한국어 표기가 있으면 그것."""
    return str(jg.get(f"{side}_kr") or jg.get(side) or "").strip()


def _pick_side(jg: dict) -> str | None:
    w = jg.get("winner") or (jg.get("matchup") or {}).get("승자")
    if not w:
        return None
    if w == jg.get("home"):
        return "home"
    if w == jg.get("away"):
        return "away"
    return None


def market_line(jg: dict) -> str | None:
    """시장이 어느 쪽인지. 🔴 **우리 판단이 아니라 시장이라고 적는다.**"""
    p = jg.get("p_code")
    side = _pick_side(jg)
    if p is None or side is None:
        return None
    try:
        pf = float(p)
    except (TypeError, ValueError):
        return None
    mine = pf if side == "home" else 1.0 - pf
    name = _team(jg, side)
    if not name:
        return None
    return f"시장은 {name} 쪽을 {_band(mine)} 봅니다."


def adjust_line(jg: dict) -> str | None:
    """우리 조정이 붙었는지. ⚠️ 0 이면 **0이라고 적는다** — 조용히 비우면
    "분석했다"로 읽힌다."""
    adj = jg.get("adj_pp")
    if isinstance(adj, str):
        import json

        try:
            adj = json.loads(adj)
        except Exception:
            adj = None
    if not isinstance(adj, dict) or not adj:
        return "우리 기록에서 조정할 근거는 나오지 않았습니다 — 시장값 그대로입니다."
    parts = []
    for k, v in adj.items():
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if abs(f) < 0.01:
            continue
        parts.append(f"{k} {f:+.1f}%p")
    if not parts:
        return "우리 기록에서 조정할 근거는 나오지 않았습니다 — 시장값 그대로입니다."
    return "우리 기록이 움직인 것: " + " · ".join(parts) + "."


def fork_lines(jg: dict, limit: int = 3) -> list[str]:
    """갈림길 — **코드가 세운 가설**이다(`hypothesis.py`, LLM 0건)."""
    ov = jg.get("order_v3") or jg.get("order_v2") or {}
    forks = [str(x).strip() for x in (ov.get("갈림길목록") or []) if str(x).strip()]
    return forks[:limit]


def evidence_lines(jg: dict, limit: int = 4) -> list[str]:
    """조사 결과 중 **사람이 읽을 수 있는 줄만**.

    ⚠️ JSON 원문 줄은 뺀다 — 카드에 `{"home": {"팀": …` 이 그대로 찍히던
       자리다(실측 2026-09-22 card:kbo). 사람이 읽는 칸이 아니다.
    """
    ov = jg.get("order_v3") or jg.get("order_v2") or {}
    out = []
    for row in (ov.get("자료") or []):
        if not isinstance(row, dict):
            continue
        name = str(row.get("이름") or row.get("name") or "").strip()
        val = str(row.get("값") or row.get("value") or "").strip()
        if not name or not val:
            continue
        if val.startswith("{") or val.startswith("["):
            continue          # JSON 원문은 서술에 안 싣는다
        out.append(f"{name} — {val[:90]}")
        if len(out) >= limit:
            break
    return out


def missing_line(jg: dict) -> str | None:
    """못 본 것. 🔴 **조용한 0 금지** — 무엇이 없었는지 적는다."""
    ov = jg.get("order_v3") or jg.get("order_v2") or {}
    miss = [str(x).strip() for x in (ov.get("없는것") or ov.get("DB없음") or [])
            if str(x).strip()]
    if not miss:
        return None
    return "못 본 것: " + " · ".join(miss[:4]) + "."


def confidence_line(jg: dict) -> str | None:
    """확신이 왜 그 등급인지. ⚠️ 등급 자체는 `confidence.by_code` 가 정한다 —
    여기서 다시 계산하지 않는다(사본 금지)."""
    from app.collectors.lineups import STATUS_CONFIRMED

    if (jg.get("lineup_status") or "") != STATUS_CONFIRMED:
        return "타순이 아직 확정 전이라 확신을 낮게 둡니다."
    return None


def story(jg: dict) -> str:
    """카드의 `🧠 분석` 블록. **없으면 빈 문자열**(빈 줄을 만들지 않는다).

    🔴 순서: 시장이 어디를 보는가 → 우리가 무엇을 움직였나 → 무엇을 봤나
       → 무엇을 못 봤나 → 확신 이유. **결론보다 근거가 앞**이다(SRCH-6 규약).
    """
    parts: list[str] = []
    for fn in (market_line, adjust_line):
        v = fn(jg)
        if v:
            parts.append(v)
    ev = evidence_lines(jg)
    if ev:
        parts.append("본 것: " + " · ".join(ev) + ".")
    for fn in (missing_line, confidence_line):
        v = fn(jg)
        if v:
            parts.append(v)
    return "\n".join(parts)


# ═══════════ [SWAP-3T 2026-09-22] 흐름(v1.4) 상태용 템플릿 ═══════════
#
# 🔴 사용자 지시("서술도 템플릿으로 바꿔라")는 **흐름에도** 적용된다.
#    구경로에만 붙여 두면 경로를 갈아끼울 때 다시 LLM 서술로 돌아간다.
# ⚠️ 위 `story()` 는 구경로 `jg` 모양을, 아래 `story_flow()` 는 흐름 `state`
#    모양을 읽는다. **규칙은 같다** — 있는 값만 옮기고 없으면 줄을 뺀다.


def _flow_team(state, side: str) -> str:
    return str(getattr(state, side, "") or "").strip()


def flow_market_line(state) -> str | None:
    """시장이 어느 쪽인지. 🔴 우리 판단이 아니라 **시장**이라고 적는다."""
    p = (getattr(state, "n08_pcode", None) or {}).get("p_code_pick")
    side = getattr(state, "pick_side", None)
    if p is None or side not in ("home", "away"):
        return None
    try:
        pf = float(p)
    except (TypeError, ValueError):
        return None
    mine = pf if side == "home" else 1.0 - pf
    name = _flow_team(state, side)
    return f"시장은 {name} 쪽을 {_band(mine)} 봅니다." if name else None


def flow_hypothesis_line(state) -> str | None:
    """🔴 **갈림길** — 코드가 세운 가설이다(`n04_hyp`, LLM 0건)."""
    hyp = getattr(state, "n04_hyp", None) or []
    texts = [str(h.get("text") or "").strip()
             for h in hyp if isinstance(h, dict)]
    texts = [t for t in texts if t]
    return ("찾으려 한 것: " + " · ".join(texts[:2]) + ".") if texts else None


def flow_evidence_line(state) -> str | None:
    """⑤가 실제로 찾은 것. ⚠️ **출처가 있는 것만** 센다."""
    ev = getattr(state, "n05_evidence", None) or []
    got = [str(e.get("var") or "") for e in ev
           if isinstance(e, dict) and e.get("value") not in (None, "", [])]
    if not got:
        return None
    return "찾은 것: " + " · ".join(sorted(set(got))[:5]) + "."


def flow_verdict_line(state) -> str | None:
    """확인/반증/모름. 🔴 **미상을 숨기지 않는다** — 그게 이 봇의 값어치다."""
    v = getattr(state, "n06_verdict", None) or {}
    per = v.get("per_var") or {}
    if not per:
        return None
    from collections import Counter

    c = Counter(per.values())
    parts = [f"{k} {n}" for k, n in c.most_common()]
    return "채점: " + " · ".join(parts) + "."


def flow_adjust_line(state) -> str | None:
    """조정. ⚠️ 0 이면 **0이라고 적는다** — 조용히 비우면 "분석했다"로 읽힌다.

    🔴 **빈 목록과 없음은 다르다.** `[]` 는 "⑦이 돌았는데 붙일 게 없었다"이고
       `None`(칸 자체가 없음)은 "⑦까지 못 갔다"이다. 후자에 "조정할 근거가
       없었다"고 적으면 **돌지도 않은 단계를 돌았다고 말하는 것**이다.
       이 저장소가 반복해 강조하는 구분이다(`_need_of`·`record_move` 규약).
    """
    adj = getattr(state, "n07_adjust", None)
    if adj is None:
        return None
    parts = []
    for a in adj:
        if not isinstance(a, dict):
            continue
        try:
            pp = float(a.get("pp") or 0)
        except (TypeError, ValueError):
            continue
        if abs(pp) < 0.01:
            continue
        parts.append(f"{a.get('var') or '?'} {pp:+.1f}%p")
    if not parts:
        return "조정할 근거는 나오지 않았습니다 — 시장값 그대로입니다."
    return "확률을 움직인 것: " + " · ".join(parts) + "."


def story_flow(state) -> list:
    """흐름 ⑫ 서술 — **문장 목록**. `n12_text` 가 기대하는 모양이다.

    🔴 순서: 시장 → 무엇을 찾으려 했나(갈림길) → 찾았나 → 채점 → 조정.
       **근거가 결론보다 앞**이다(SRCH-6 규약).
    ⚠️ 값이 없으면 그 줄을 **뺀다**(절대 규칙 6). 전부 없으면 빈 목록이다.
    """
    out = []
    for fn in (flow_market_line, flow_hypothesis_line, flow_evidence_line,
               flow_verdict_line, flow_adjust_line):
        try:
            v = fn(state)
        except Exception as exc:                            # pragma: no cover
            logger.info("[narrate] 흐름 서술 줄 실패 %s: %s", fn.__name__, exc)
            v = None
        if v:
            out.append(v)
    return out
