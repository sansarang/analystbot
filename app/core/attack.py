"""🔴🔴 **공격형 검증 엔진**(지시 2026-10-14f) — 결론을 변수로 공격해 좁힌다.

🔴 원칙(§0) —
   · 공격 결과는 **버팀 / 깨짐 / 반격** 셋이다.
   · **[확정]**(`judge: true`) 변수만 깨짐·반격에 쓴다. [관찰]은 **표시만**.
   · 깨진 변수는 **기여 0** 으로 두고 **같은 시뮬 함수**로 다시 센다(§3).
🔴 등급표는 `config/attack_vars.yaml` 하나다(사본 금지) — 등급을 코드에 적지 않는다.
⚠️ 확률 경로를 **새로 만들지 않는다** — λ 를 다시 세우는 식은 운영과 같다
   (바닥 × 홈 배율 × e^{β·Σ}). 공격은 **Σ 와 배율의 입력만** 바꾼다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONF = "config/attack_vars.yaml"

BETA = 0.25
W = {"axis0": 0.3, "axis1": 0.3, "axis2": 0.2, "axis3": 0.2}

#: 🔴 공격이 **그 변수에서 걷어내는 축**(깨지면 그 축 기여를 0 으로)
AXIS_OF = {"A2": "axis0", "B1": "axis1", "B3": "axis1", "F1": "axis3",
           "F2": "axis3"}

#: 🔴🔴 **C2 깨짐 문턱** — 백필 분위 보정표에서 **상위 20%**(배율 ≥1.38)의 홈 승률이
#:   기준(43.4%)보다 낮았다(40.7% · 시즌 초 38.8%). 그 분위는 근거로 못 쓴다.
C2_CUT = 1.38
#: 🔴 J1 — 시장과 ≥10%p 벌어진 줄(이미 `core/divergence.CUT` 과 같은 수)
J1_CUT = 0.10


def table() -> dict:
    import yaml
    path = ROOT / CONF
    if not path.is_file():
        return {}
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def grade(key: str) -> str:
    return str((dict(table().get("vars") or {}).get(str(key))
                or {}).get("grade") or "⬜")


def judges() -> list[str]:
    """🔴 **판정에 쓰는 변수**(등급표가 `judge: true` 라고 적은 것만)."""
    return sorted(k for k, v in dict(table().get("vars") or {}).items()
                  if (v or {}).get("judge") is True)


@dataclass
class Shot:
    """🔴 공격 한 발 — 변수 하나에 대한 판정."""

    key: str = ""
    verdict: str = "버팀"          # 버팀 · 깨짐 · 반격 · 보류 · 표시만
    why: str = ""
    moved: float = 0.0             # 🔴 그 변수가 Σ 에서 걷힌 몫(기여 %p 는 카드가)

    def said(self) -> str:
        mark = {"버팀": "✅", "깨짐": "🔴", "반격": "🔁", "보류": "⏸",
                "표시만": "📋"}.get(self.verdict, "·")
        return (f"{mark} **{self.key}**({grade(self.key)}) {self.verdict}"
                + (f" — {self.why}" if self.why else ""))


@dataclass
class Out:
    """🔴 공격 결과 — 살아남은 Σ·배율과 발자국."""

    shots: list = field(default_factory=list)
    sigma: float = 0.0
    sigma0: float = 0.0
    mul: float = 1.0
    mul0: float = 1.0
    gaps: dict = field(default_factory=dict)
    draw_add: float = 0.0          # 🔴 K1 — 무 쪽에 더할 몫(표시·재판정용)
    hold: bool = True

    def broken(self) -> list:
        return [s for s in self.shots if s.verdict == "깨짐"]

    def counters(self) -> list:
        return [s for s in self.shots if s.verdict == "반격"]

    def verdict(self) -> str:
        """🔴 판정 — 살아남음 · 약해짐 · 무너짐(§3)."""
        if not self.broken():
            return "살아남음"
        gone = abs(self.sigma0 - self.sigma) + abs(self.mul0 - self.mul)
        flip = (self.sigma0 * self.sigma) < 0
        if flip or any(s.key in ("J1", "C2", "E1") for s in self.broken()):
            return "무너짐" if flip else "약해짐"
        return "약해짐" if gone > 0 else "살아남음"


def of(box: dict) -> Out:
    """🔴🔴 **공격 한 경기** — `box` 는 그 경기의 재료다(새 통신 0건).

    `box` 열쇠 —
      `pick`(0 홈·1 무·2 원정) · `gaps`(축 차) · `mul`·`league_mul`(홈 배율) ·
      `axis_why`(축별 사유) · `xi_state`(확정·예상) · `absence`(결장 줄) ·
      `elo`(기준 승무패 또는 None) · `market`(마진 제거 삼원 또는 None) ·
      `ours`(봇 삼원) · `gaps_missing`(⬜ 입력 이름) · `band`(무 구간 편차) ·
      `neutral`(중립인가) · `t12`(결론 쪽 T12 발동) · `form_games`(축1 표본)
    """
    gaps = {k: (None if v is None else float(v))
            for k, v in dict(box.get("gaps") or {}).items()}
    sigma0 = sum(W.get(k, 0.0) * (v or 0.0) for k, v in gaps.items())
    got = Out(sigma=sigma0, sigma0=sigma0, gaps=dict(gaps),
              mul=float(box.get("mul") or 1.0),
              mul0=float(box.get("mul") or 1.0))
    pick = box.get("pick")
    side = "home" if pick == 0 else ("away" if pick == 2 else "")
    want = judges()

    def fire(key: str, verdict: str, why: str) -> None:
        got.shots.append(Shot(key=key, verdict=verdict, why=why))
        if verdict == "깨짐" and AXIS_OF.get(key):
            axis = AXIS_OF[key]
            if gaps.get(axis) is not None:
                got.gaps[axis] = 0.0
                got.sigma = sum(W.get(k, 0.0) * (v or 0.0)
                                for k, v in got.gaps.items())

    # ── A1 체급(Elo·오프셋) ────────────────────────────────────────
    if "A1" in want:
        elo = box.get("elo")
        if not elo:
            fire("A1", "깨짐", "⬜ 기준(Elo·리그 오프셋)이 없다 — 체급 근거 0")
        else:
            same = (max(range(3), key=lambda i: float(elo[i])) == pick)
            fire("A1", "버팀" if same else "반격",
                 f"기준 {100*float(elo[0]):.0f}/{100*float(elo[1]):.0f}/"
                 f"{100*float(elo[2]):.0f}% — 결론과 "
                 + ("같은 쪽" if same else "**반대쪽**"))

    # ── A2 축0 ───────────────────────────────────────────────────
    if "A2" in want and gaps.get("axis0") is not None:
        why = str(box.get("axis_why", {}).get("axis0") or "")
        sd = box.get("axis0_sd")
        flip = False
        if sd:
            alt = dict(got.gaps)
            alt["axis0"] = float(gaps["axis0"]) / float(sd)
            s_alt = sum(W.get(k, 0.0) * (v or 0.0) for k, v in alt.items())
            flip = (s_alt * sigma0) < 0
        if flip:
            fire("A2", "깨짐", f"리그 표준화(÷{float(sd):.3f})로 재계산하면 "
                              f"종합 부호가 **뒤집힌다**")
        elif "대체값" in why:
            fire("A2", "표시만", "가치를 **메운 선수**가 있다 — " + why[:60])
        else:
            fire("A2", "버팀", f"축0 차 {gaps['axis0']:+.3f}(확정 XI 기준)")

    # ── B1 폼 표본 ───────────────────────────────────────────────
    if "B1" in want:
        n = box.get("form_games")
        if gaps.get("axis1") is None:
            fire("B1", "깨짐", "⬜ 보정 폼을 못 셌다 — 축1 기여 0")
        elif n is not None and int(n) < 5:
            fire("B1", "깨짐", f"표본 {int(n)}경기(<5) — 시즌 초 수축으로도 모자라다")
        else:
            fire("B1", "버팀", f"축1 차 {gaps['axis1']:+.3f}"
                               + (f" · 표본 {int(n)}경기" if n else ""))

    # ── B3 운 요소 골(T12) ───────────────────────────────────────
    if "B3" in want:
        t12 = str(box.get("t12") or "")
        if t12 and side and side in t12:
            fire("B3", "깨짐", f"결론 쪽에 **운 요소 골** — {t12[:60]}")
        elif t12:
            fire("B3", "반격", f"상대 쪽 운 요소 골 — {t12[:60]}")
        else:
            fire("B3", "버팀", "운 요소 골 발동 없다")

    # ── C1·C2·C4 장소 ────────────────────────────────────────────
    if "C4" in want and box.get("neutral"):
        got.mul = 1.0
        fire("C4", "깨짐", "중립 경기 — 홈 이점 0(CC3)")
    if "C1" in want:
        lg = float(box.get("league_mul") or 0.0)
        real = box.get("league_real")
        if lg and real:
            gap = abs(lg / float(box.get("away_mul") or 0.88) - float(real))
            fire("C1", "버팀" if gap < 0.15 else "표시만",
                 f"엔진 비율 {lg / float(box.get('away_mul') or 0.88):.3f} ↔ "
                 f"실측 {float(real):.3f}")
    if "C2" in want:
        mul = float(box.get("team_mul") or 0.0)
        if not mul:
            fire("C2", "버팀", "팀별 홈 효과를 **쓰지 않는다**(③a 반영판)")
        elif mul >= C2_CUT:
            got.mul = float(box.get("league_mul") or got.mul)
            fire("C2", "깨짐", f"팀 배율 ×{mul:.3f} 는 상위 20% 분위 — 그 분위 "
                              f"홈 승률 40.7% < 기준 43.4%")
        else:
            fire("C2", "버팀", f"팀 배율 ×{mul:.3f}(상위 분위 아님)")

    # ── E1·E2·E4 라인업 ─────────────────────────────────────────
    if "E4" in want and str(box.get("xi_state") or "") != "확정":
        fire("E4", "보류", f"XI `{box.get('xi_state')}` — E1~E3 판정 보류")
    elif "E1" in want:
        miss = list(box.get("key_missing") or [])
        if miss and side:
            fire("E1", "깨짐", f"결론 쪽 핵심 빠짐 {miss[:3]}")
        else:
            fire("E1", "버팀", "축0 상위 3 중 빠짐 없다")
    if "E2" in want:
        src = str(box.get("absence_src") or "")
        fire("E2", "표시만" if src and src not in ("S", "A") else "버팀",
             f"결장 원천 `{src or '⬜'}`"
             + (" — B·C 단독은 판정 안 한다" if src not in ("S", "A") else ""))

    # ── G3 출장정지 ──────────────────────────────────────────────
    if "G3" in want:
        src = box.get("discipline")
        fire("G3", "버팀" if src else "표시만",
             "연맹 공시 확인" if src else "⬜ 공시 통로가 없다(추측 안 한다)")

    # ── J1 시장 괴리 ────────────────────────────────────────────
    if "J1" in want:
        mk, ours = box.get("market"), box.get("ours")
        if mk and ours and pick is not None:
            gap = float(mk[pick]) - float(ours[pick])
            miss = list(box.get("gaps_missing") or [])
            if gap <= -J1_CUT and miss:
                fire("J1", "깨짐", f"결론 쪽을 시장이 **{100*gap:+.1f}%p** 낮게 "
                                  f"본다 · ⬜ 입력 {miss[:3]}")
            elif gap <= -J1_CUT:
                fire("J1", "표시만", f"시장이 {100*gap:+.1f}%p 낮다(⬜ 없다)")
            else:
                fire("J1", "버팀", f"시장과 {100*gap:+.1f}%p")
        else:
            fire("J1", "표시만", "⬜ 시장 수가 없다")

    # ── K1 무 과소 ──────────────────────────────────────────────
    if "K1" in want and pick != 1:
        dev = box.get("band_dev")
        if dev:
            got.draw_add = abs(float(dev))
            fire("K1", "깨짐" if abs(float(dev)) >= 0.025 else "표시만",
                 f"무 구간 편차 {100*float(dev):+.1f}%p — 결론이 "
                 f"**무가 아니다** 쪽이다")
        else:
            fire("K1", "표시만", "⬜ 그 구간 백필 편차가 없다")

    got.hold = not got.broken()
    return got


def lam_of(box: dict, out: Out) -> list[float]:
    """🔴 살아남은 λ — **운영과 같은 식**(바닥 × 배율 × e^{β·Σ})."""
    import math
    base = [float(x) for x in (box.get("base") or [1.0, 1.0])]
    away = float(box.get("away_mul") or 0.88)
    m = BETA * out.sigma
    return [base[0] * out.mul * math.exp(m), base[1] * away * math.exp(-m)]
