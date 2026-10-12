"""🔴🔴 **§10 이변 경고 — 확률로 못 간 신호만** — 지시서 2026-10-12(둘째) §10.

> 대상: §9 **미채택** 신호 + 확률로 넣을 수 없는 신호
>   F6 약한 강팀(강팀 승 < 50%) · F8 정보 공백(InfoQ ≤ 2) · F9 고분산 · 미채택 항
> 등급: 🟡 `S ≥ 상위 30% 분위` · 🔴 `S ≥ 상위 10% 분위`.
> 🔴 의 실제 강팀 승률이 예측보다 **구간상 낮을 때만** 운영 🔴 켬.

🔴 왜 경고인가 — *"확인되지 않은 것은 확률에 넣지 않는다"*(§0). 그런데 *"모르면
   아무 말도 안 한다"* 도 틀렸다 — 실사고 둘은 **읽는 사람이 강팀을 확신한** 일이다.
   🔴 그래서 **확률은 그대로 두고 등급만** 내린다(계약 U3).
🔴 **S2** — λ 식이 **채택한 신호**는 경고 점수에서 **뺀다**. 같은 신호를 두 곳에서
   세면 그 효과를 두 번 세는 것이다.
🔴 **U5** — 검증표(`fit_upset`)를 통과하지 않은 등급은 **운영에서 안 켜진다**.
⚠️ 계수·분위는 **판 파일**(`data/upset_model/<리그>/<날>.yaml`)이 든다(손값 금지).
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: 🔴🔴 신호 이름표 — ⚠️ 여기 **확률로 간 항은 없다**(λ 항 이름은 `probfloor.TERMS`)
SIGNALS: dict[str, str] = {
    "weak_fav": "F6 약한 강팀(강팀 승 < 50%)",
    "thin_info": "F8 정보 공백(InfoQ ≤ 2)",
    "high_var": "F9 고분산(λ 합이 상위 분위)",
}

#: 🔴 강팀 승을 "약하다"고 보는 문턱(§10 F6 이 그 수를 적었다)
WEAK_FAV = 0.50

#: 🔴 등급 글자 — 카드·판정이 같은 글자를 쓴다
YELLOW, RED = "🟡", "🔴"


@dataclass
class Score:
    """🔴 경고 한 묶음 — **센 신호와 뺀 신호를 이름으로** 든다."""

    score: float = 0.0
    grade: str = ""
    used: dict = field(default_factory=dict)
    skipped: list = field(default_factory=list)
    why: str = ""


def score_of(signals: dict, *, model: dict, adopted=None) -> Score:
    """🔴🔴 §10 — `S = Σ 채택 계수 × 신호값`. `(S, 등급, 사유)`.

    🔴 **S2** — `adopted`(λ 식이 채택한 항)에 든 신호는 **뺀다**.
    🔴 **U5** — `model["checked"]` 가 그 등급을 통과시키지 않았으면 **내린다**.
    ⚠️ 계수 없는 신호는 *"검증 안 됨"* 으로 **빼고 이름을 남긴다**(#3).
    """
    said = dict(signals or {})
    coef = dict(dict(model or {}).get("coef") or {})
    take = set(adopted or ())
    got = Score()
    notes: list[str] = []
    for name, val in said.items():
        if name in take:
            got.skipped.append(str(name))
            notes.append(f"`{name}` 는 **확률이 이미 담았다**(λ 식 채택 항)")
            continue
        w = coef.get(str(name))
        if w is None:
            got.skipped.append(str(name))
            notes.append(f"`{name}` 계수가 없다 — **검증 안 됨**(세지 않는다)")
            continue
        got.used[str(name)] = float(w) * float(val or 0.0)
        got.score += float(w) * float(val or 0.0)
    q30 = float(dict(model or {}).get("q30") or 0.0)
    q10 = float(dict(model or {}).get("q10") or 0.0)
    checked = dict(dict(model or {}).get("checked") or {})
    grade = ""
    if q10 and got.score >= q10:
        grade = RED
    elif q30 and got.score >= q30:
        grade = YELLOW
    if grade == RED and not checked.get("red"):
        grade = YELLOW
        notes.append("🔴 등급은 **검증 안 됨** — 참고(🟡)로 내린다(U5)")
    if grade == YELLOW and not checked.get("yellow"):
        grade = ""
        notes.append("🟡 등급도 **검증 안 됨** — 경고를 켜지 않는다(U5)")
    got.grade = grade
    parts = [f"이변 경고 S **{got.score:+.3f}**"
             + (f" → {grade}" if grade else " → 등급 없음")]
    if got.used:
        parts.append("센 신호 " + " · ".join(
            f"{k} {v:+.3f}" for k, v in got.used.items()))
    parts += notes
    got.why = " — ".join(parts)
    return got


def step_of(grade: str) -> int:
    """🔴 §14 — 🟡 는 강팀 줄 **한 단계↓**. 🔴 는 내리는 게 아니라 **접는다**."""
    return 1 if str(grade) == YELLOW else 0


def folds(market: str, *, grade: str, fav_name: str, fav_side: str,
          home: str, away: str) -> bool:
    """🔴🔴 **U4** — 🔴 면 **강팀 승·강팀 핸디** 줄은 등급을 안 받는다(접는다).

    🔴 약팀 보호 줄(+핸디·더블찬스·DNB)과 무승부는 **판정 대상으로 남는다**.
    ⚠️ 줄 이름은 `s7_judge._lines` 가 만든 글자다(`win home`·`handicap <팀> -1.5`).
    """
    if str(grade) != RED:
        return False
    said = str(market or "").strip().lower()
    fav_home = str(fav_side) == "home"
    if said.startswith("win "):
        return said.endswith("home") if fav_home else said.endswith("away")
    if said.startswith("handicap"):
        # 🔴 **강팀에게 걸린 음수 핸디**가 강팀 줄이다(약팀 +핸디는 보호 줄이다)
        low = str(fav_name or "").strip().lower()
        if low and low in said:
            return "-" in said.split(low, 1)[1]
        other = (away if fav_home else home)
        return False if str(other).strip().lower() in said else False
    return False
