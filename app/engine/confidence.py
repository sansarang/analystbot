"""[확신도 후보] 확신도를 무엇으로 정할지 **아직 정하지 않았다. 재기만 한다.**

🔴 이 모듈은 게이트에 닿지 않는다. `gate_result_of` 는 지금도 앞으로도
   `judge_confidence`(LLM 자기신고)만 읽는다. 여기 값은 원장의
   `confidence_probe` 칸에만 쌓인다.

## 왜 후보를 재기만 하는가 — 실측 2026-09-07

교체를 승인받았지만 **배포 전 관문에서 떨어졌다.** 처음 설계한 재료-결측
방식은 57경기 **전부 `상`** 이 나와 변별력이 0이었고, 그대로 넣으면 거부권이
11건 → 0건으로 사라진다.

변별력이 있는 축은 시장뿐이었다 (채점 100경기, 경기당 1행):

    현행 자기신고   상 50.0%(2)  · 중 52.9%(87) · 하 45.5%(11)   거부권 11%
    A 괴리>15pp=하  상 53.8%(39) · 중 56.6%(53) · 하 12.5%(8)    거부권  8%
    B 방향충돌=하   상 54.3%(35) · 중 57.1%(35) · 하 43.3%(30)   거부권 30%
    C 충돌&>10pp=하 상 54.3%(35) · 중 58.3%(48) · 하 29.4%(17)   거부권 17%

**그런데 이 숫자를 그대로 믿으면 안 된다. 셋 다 문제가 있다.**

① 검증한 값이 게이트가 보는 값이 아니다. 위 `divergence_pp` 는 백필로 넣은
   **CLOSE(마감 근사)** 다. 게이트는 카드 시점의 **SEND** 를 본다. SEND 괴리는
   오늘(`cff9a93`)까지 한 번도 기록된 적이 없어 잴 수가 없었다.
   → 그래서 지금부터 **SEND 로 쌓는다.** 그게 이 모듈의 존재 이유다.

② 자기신고가 나쁘다는 근거도 확정되지 않았다. 절단을 바꾸면 방향이 뒤집힌다 —
     134경기 전체    하 58.8%(17) > 중 53.9%(115)
     100경기(시장O)  하 45.5%(11) < 중 52.9%( 87)
   표본 11~17건으로는 방향조차 안 정해진다. **"역정보"라고 단정했던 것을
   여기 바로잡아 둔다.**

③ 오늘 하루에 시장 적재·변수 해결·grok 대체가 다 들어갔다. 게이트까지
   얹으면 내일부터의 변화를 어느 것에도 귀속시킬 수 없다.

→ **2주 뒤 SEND 데이터 50~100경기로 결정한다.** 그때까지 이 모듈은
   후보들을 나란히 새기기만 한다.

⚠️ **재료 목록을 손으로 적지 않는다.** 판정 조립이 쓰는 payload 함수를
   그대로 불러서 센다 — 자료가 하나 늘 때 여기가 안 따라가면 그 순간
   이 기록은 거짓말이 된다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

HIGH, MID, LOW = "상", "중", "하"
_ORDER = (HIGH, MID, LOW)

#: 재료식 경계. `comparator.confidence_from` 의 칸 셈과 같은 발상이다.
#: ⚠️ 실측상 이 축은 변별력이 없었다(57경기 전부 `상`). 남겨 두는 것은
#:    "안 되더라"를 계속 확인하기 위해서다 — 지우면 그 사실도 사라진다.
GAP_HIGH_MAX = 1
GAP_MID_MAX = 3

#: 시장식 경계 (%p). A·C 가 공유한다.
DIV_WIDE = 15.0        # A: 이만큼 벌어지면 하
DIV_CONFLICT = 10.0    # C: 방향이 갈리고 이만큼 벌어지면 하
DIV_TIGHT = 5.0        # 이 안이면 상


def _down(level: str, steps: int = 1) -> str:
    return _ORDER[min(_ORDER.index(level) + steps, len(_ORDER) - 1)]


def material_gaps(jg: dict) -> list[str]:
    """빠진 재료 이름. **판정 조립이 쓰는 함수를 그대로 부른다.**

    ⚠️ 여기서 "자료N 이 있다"의 정의를 다시 쓰지 않는다. 사본은 원본이
       바뀔 때 따라가지 않고, 그 순간 이 기록이 거짓말이 된다.
    """
    from app.engine.matchup import (boxscore_payload, bullpen_payload,
                                    lineups_payload)

    gaps: list[str] = []
    try:
        if not boxscore_payload(jg):
            gaps.append("자료1 박스스코어")
        lp = lineups_payload(jg)
        slots = (min(len(((lp.get(s) or {}).get("타순") or []))
                     for s in ("home", "away")) if lp else 0)
        if slots < 9:
            gaps.append("자료3 오늘 타순")
        if not bullpen_payload(jg):
            gaps.append("자료9 불펜")
    except Exception as exc:                  # 계측이 판정을 죽이지 않는다
        logger.warning("[confidence] 재료 셈 실패 game=%s: %s",
                       jg.get("game_id"), exc)
    for key, name in (("material10_status", "자료10 변수참조"),
                      ("material11_status", "자료11 맥락")):
        if (jg.get(key) or "") in ("결측", "실패", "없음"):
            gaps.append(name)
    if not (jg.get("elo") or {}):
        gaps.append("자료12 실력 레이팅")
    return gaps


def branch_unresolved(jg: dict) -> bool:
    """분기점을 지목했는데 **하나도 못 풀었나.**

    분기점 자체가 없으면 False 다 — 안 물어본 것과 묻고 못 푼 것은 다르다.
    """
    from app.engine.matchup import branch_payload

    try:
        items = (branch_payload(jg) or {}).get("항목") or []
    except Exception:
        return False
    return bool(items) and not any(it.get("답") for it in items)


def by_materials(gaps_n: int, unresolved: bool) -> str:
    """후보 M — 재료 결측 + 분기점 미해결. **실측 변별력 없음.**"""
    level = (HIGH if gaps_n <= GAP_HIGH_MAX
             else MID if gaps_n <= GAP_MID_MAX else LOW)
    return _down(level) if unresolved else level


def by_market(div_pp: float | None, same_side: bool | None,
              *, rule: str) -> str | None:
    """후보 A·B·C — 시장 괴리. 시장이 없으면 **None**.

    🔴 수집 실패가 거부권이 되면 안 된다. 실측 2026-09-07: 시장 미수집
       34경기는 오히려 **61.8%** 로 가장 잘 맞았다. `None` 을 `하` 로
       읽는 호출자는 그 34경기를 통째로 버리게 된다.
    """
    if div_pp is None or same_side is None:
        return None
    d = abs(float(div_pp))
    if rule == "A":
        return LOW if d > DIV_WIDE else MID if d > DIV_TIGHT else HIGH
    if rule == "B":
        if not same_side:
            return LOW
        return HIGH if d <= DIV_TIGHT else MID
    if rule == "C":
        if not same_side:
            return LOW if d > DIV_CONFLICT else MID
        return HIGH if d <= DIV_TIGHT else MID
    raise ValueError(f"모르는 규칙: {rule}")


def probe(jg: dict, *, market_prob=None, divergence_pp=None) -> dict:
    """확신도 후보 전부를 한 번에 낸다. **기록 전용 — 게이트로 가지 않는다.**

    ⚠️ 실패해도 예외를 밖으로 내지 않는다. 계측이 판정 기록을 죽이면 안 된다.
    """
    try:
        gaps = material_gaps(jg)
        unresolved = branch_unresolved(jg)
        our = jg.get("p_claude")
        same = None
        if market_prob is not None and our is not None:
            same = (float(market_prob) > 0.5) == (float(our) >= 0.5)
        div = (float(divergence_pp) if divergence_pp is not None else None)
        return {
            "자기신고": (jg.get("matchup") or {}).get("확신도"),
            "결측": gaps, "결측수": len(gaps), "분기점_미해결": unresolved,
            "M": by_materials(len(gaps), unresolved),
            "A": by_market(div, same, rule="A"),
            "B": by_market(div, same, rule="B"),
            "C": by_market(div, same, rule="C"),
            "시장괴리pp": div, "시장동의": same,
            "기준": "send",     # 🔴 CLOSE 백필과 섞이지 않게 출처를 새긴다
        }
    except Exception as exc:
        # ⚠️ 로그 줄에서 다시 `jg.get` 을 부르지 않는다 — jg 가 None 이면
        #    예외 처리기가 예외를 내고, 계측이 본체를 죽인다는 바로 그 사고다.
        logger.warning("[confidence] 후보 계산 실패: %s", exc)
        return {}


# ══════════ [CONF-1 2026-09-13] 확신 등급을 **코드가** 정한다 ══════════
#
# 사용자 결정(1차 결정 3): 종전 `verdict.level()` 은 라벨 정규화뿐이었고 등급은
# LLM 자기신고였다 — AUC 0.5122 짜리 판정에 AI 가 스스로 붙인 등급을 실어 보냈다.
#
# ⚠️ `DB본것`·채택 자료 수·뉴스 건수는 **입력에서 뺀다**(자기보고).
# ⚠️ [2차 결정 C] `divergence_pp = p_code − p_market = Σadj` 로 정의를 고정한다.

#: 종목별 필수 축. 🔴 이름의 원본은 `dbref.ITEMS` 다 — 손으로 적지 않는다.
REQUIRED_AXES: dict[str, tuple[str, ...]] = {
    "mlb": ("선발 최근 등판", "불펜 최근 폼과 가용성"),
    "kbo": ("선발 최근 등판", "불펜 최근 폼과 가용성"),
    "npb": ("선발 최근 등판", "불펜 최근 폼과 가용성"),
    "soccer": ("축구 선발 라인업", "축구 부상·결장자"),
}

#: 등급 문턱. 지시문 표 그대로.
CODE_HIGH_P = 0.63
CODE_MID_P = 0.58
CODE_DIV_MAX = 4.0      # |p_code − p_market| %p
CODE_HIGH_ADJ_N = 2     # 상은 조정 항목 2개 이상


def divergence_pp(p_code, p_market) -> float | None:
    """우리 − 시장 (%p). 🔴 [결정 C] 이것이 **Σadj** 다 —
    LLM 확률과 시장의 차이가 아니다."""
    if p_code is None or p_market is None:
        return None
    return round((float(p_code) - float(p_market)) * 100, 2)


def _adj_count(jg: dict) -> int:
    import json as _json

    raw = jg.get("adj_pp")
    if isinstance(raw, dict):
        return len(raw)
    try:
        return len(_json.loads(raw or "{}"))
    except (TypeError, ValueError):
        return 0


def by_code(jg: dict, have: list | tuple | set | None) -> str:
    """규칙표대로 등급을 정한다. 반환은 `verdict.LEVELS` 의 값.

    `have` — 이 경기에서 값이 있는 DB 항목 이름들(`dbref.bundle`의 `있음`).
    🔴 자기보고(`DB본것`)가 아니라 **있음**을 쓴다.
    """
    from app.collectors.lineups import STATUS_CONFIRMED

    sport = (jg.get("sport") or "").lower()
    axes = REQUIRED_AXES.get(sport, ())
    got = {a for a in axes if a in set(have or ())}
    p_code, p_mkt = jg.get("p_code"), jg.get("p_market_spine")
    # 🔴 뼈대가 없으면 등급을 붙이지 않는다
    if p_code is None or p_mkt is None:
        return LOW
    if (jg.get("lineup_status") or "") != STATUS_CONFIRMED:
        return LOW
    if not axes or not got:
        return LOW
    div = abs(divergence_pp(p_code, p_mkt) or 0.0)
    if div > CODE_DIV_MAX:
        return LOW
    p = float(p_code)
    # ⚠️ 2종에서 "2/3 이상"은 1.33 → **올림하여 전부**로 읽는다(보수적).
    need_mid = -(-2 * len(axes) // 3)
    if (p >= CODE_HIGH_P and len(got) == len(axes)
            and _adj_count(jg) >= CODE_HIGH_ADJ_N):
        return HIGH
    if p >= CODE_MID_P and len(got) >= need_mid:
        return MID
    return LOW
