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

#: 🔴 미실행 상태의 원본은 `flow.labels.UNRUN` 하나다(사본 금지).
try:
    from app.flow.labels import UNKNOWN as UNKNOWN_LABEL
    from app.flow.labels import UNRUN as UNRUN_LABEL
except Exception:                                    # pragma: no cover
    UNRUN_LABEL, UNKNOWN_LABEL = "미실행", "unknown"

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
    # 🔴 [VIS-1 2026-09-23] 종전에는 `채점: confirmed 1 · unknown 1.` 이었다 —
    #    읽는 사람이 알 수 없다. 변수의 **사람 이름**으로 적는다.
    #    ⚠️ 이름·상태의 원본은 config(`flow.var_names`)와 `labels` 다(사본 금지).
    ok = [_var_ko(k) for k, v in per.items() if v == "confirmed"]
    no = [_var_ko(k) for k, v in per.items() if v == UNKNOWN_LABEL]
    un = [_var_ko(k) for k, v in per.items() if v == UNRUN_LABEL]
    parts = []
    if ok:
        parts.append("확인 " + " · ".join(ok))
    if no:
        parts.append("아직 모름 " + " · ".join(no))
    if un:
        parts.append("잴 방법 없음 " + " · ".join(un))
    return "채점: " + " / ".join(parts) + "." if parts else None


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


def _var_ko(var: str) -> str:
    """변수의 **사람 이름**. 🔴 원본은 `config/rules.yaml` 의 `flow.var_names`
    하나다 — 여기에 표를 만들지 않는다(사본 금지)."""
    try:
        from app.flow import rules as R

        return str((R.get("var_names") or {}).get(var) or var)
    except Exception:
        return var


def _team_of(state, side: str) -> str:
    return str(getattr(state, side, "") or side)


def _pct(x) -> str:
    try:
        return f"{float(x) * 100:.1f}%"
    except (TypeError, ValueError):
        return "?"


def story_flow(state) -> list:
    """흐름 ⑫ 서술 — **사용자가 읽는 글**. `n12_text` 가 기대하는 문장 목록.

    🔴 [VIS-1 2026-09-23 사용자 지시] **"코드로 예측결과를 내면 사용자가 알기
       쉽게 표현되어야 한다"**. 종전 글은 내부 용어 그대로였다:
```
찾은 것: bullpen_3d · starter_recent3.
채점: 미실행 3 · confirmed 2 · unknown 1.
찾으려 한 것: 우리 픽(home)을 무너뜨릴 근거.
```
       읽는 사람이 `bullpen_3d`·`confirmed`·`home` 을 알 수 없다.

    🔴 **고치는 것은 표현이지 판정이 아니다.** 확률·조정·등급은 코드가 낸 값
       그대로 쓴다 — 숫자를 바꾸거나 없는 말을 붙이지 않는다(계약이 잠근다).

    🔴 순서: **결론 → 시장과의 차이 → 무엇을 봤나 → 못 본 것 → 잴 수 없는 것
       → 확률을 움직인 것 → 걸 만한가.** 결론을 앞에 두는 것은 사용자가 가장
       먼저 알고 싶은 것이기 때문이고, 근거를 바로 뒤에 붙여 "결론만 있고
       근거가 없다"가 되지 않게 한다.
    ⚠️ 값이 없으면 그 줄을 **뺀다**(절대 규칙 6). 전부 없으면 빈 목록이다.
    """
    out: list = []
    side = getattr(state, "pick_side", None) or "home"
    us = _team_of(state, side)
    p8 = getattr(state, "n08_pcode", None) or {}
    p_pick = p8.get("p_code_pick")
    if p_pick is not None and side == "away":
        try:
            p_pick = round(1.0 - float(p_pick), 4)
        except (TypeError, ValueError):
            p_pick = None
    grade = (getattr(state, "n09_conf", None) or {}).get("grade")

    # ① 결론
    if p_pick is not None:
        head = f"코드 판단: {us} {_pct(p_pick)}"
        if grade:
            head += f" · 확신 {grade}"
        out.append(head)

    # ② 시장과의 차이
    mk = (getattr(state, "n02_market", None) or {}).get("p") or {}
    pm = mk.get(side)
    if pm is not None:
        gap = None
        if p_pick is not None:
            gap = (float(p_pick) - float(pm)) * 100
        line = f"시장은 같은 쪽을 {_pct(pm)} 로 봅니다"
        if gap is not None:
            line += (f" — 우리가 {abs(gap):.1f}%p "
                     + ("높게" if gap > 0 else "낮게") + " 봅니다")
        out.append(line + ".")

    # ③ 무엇을 봤나 — 원문 그대로
    ev = getattr(state, "n05_evidence", None) or []
    seen = [e for e in ev if e.get("value") and not e.get("status")]
    for e in seen[:3]:
        # ⚠️ 원문이 없으면 값이라도 쓴다. **둘 다 없으면 줄을 뺀다** —
        #    "결장 — " 처럼 뒤가 빈 줄이 나가던 자리다(계약이 잡았다).
        body = str(e.get("raw_excerpt") or "").strip()
        if not body:
            v = e.get("value")
            body = (" · ".join(map(str, v))[:90] if isinstance(v, (list, tuple))
                    else str(v).strip())
        if not body:
            continue
        out.append(f"· {_var_ko(e.get('var'))} — {body[:90]}")

    # ④ 못 본 것 / ⑤ 잴 수 없는 것 — **둘을 가른다**(HYC-3)
    per = (getattr(state, "n06_verdict", None) or {}).get("per_var") or {}
    unknown = [_var_ko(k) for k, v in per.items() if v == UNKNOWN_LABEL]
    unrun = [_var_ko(k) for k, v in per.items() if v == UNRUN_LABEL]
    if unknown:
        out.append("아직 못 본 것: " + " · ".join(unknown) + ".")
    if unrun:
        out.append("잴 방법이 없는 것: " + " · ".join(unrun)
                   + " (수집 경로가 없습니다).")

    # ⑥ 확률을 움직인 것
    adj = getattr(state, "n07_adjust", None)
    if adj is not None:
        moved = []
        for a in adj:
            if not isinstance(a, dict):
                continue
            try:
                pp = float(a.get("pp") or 0)
            except (TypeError, ValueError):
                continue
            if abs(pp) < 0.01:
                continue
            moved.append(f"{_var_ko(a.get('var'))} {pp:+.1f}%p")
        out.append("확률을 움직인 것: " + " · ".join(moved) + "."
                   if moved else
                   "확률을 움직일 근거는 나오지 않았습니다 — 시장값 그대로입니다.")

    # ⑦ 걸 만한가
    v11 = getattr(state, "n11_value", None) or {}
    why = v11.get("reject_reason")
    st = v11.get("structure") or {}
    if why:
        out.append(f"걸 만한가: 아니오 — {why}.")
    elif st.get("market"):
        out.append(f"걸 만한가: 예 — {st.get('market')} {st.get('line')} "
                   f"@{st.get('odds')} (기대 이득 {st.get('edge_pp')}%p).")
    return out
