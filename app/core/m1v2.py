"""🔴🔴 **후보 판 M1v2**(수정·검증 지시 2026-10-14e) — 기본은 **전부 꺼짐**.

🔴 여기 있는 것은 **순수 함수**다 — 백필 판정기(`tools/judge_candidates.py`)가
   플래그와 **무관하게** 같은 식을 부를 수 있어야 한다(사본 금지 · #1).
🔴 운영 경로는 플래그가 꺼져 있으면 **글자 하나도 달라지지 않는다**(§0).
⚠️ 계수는 백필로만 고른다 — 이 파일에 값을 손으로 적지 않는다(`config/m1v2.yaml`).
"""
from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONF = "config/m1v2.yaml"

#: 🔴🔴 **효과 이름 → 그 팀에 유리한가**(①a 의 재료)
#:
#:  ⚠️ `form_defense_credit` 는 코드 자신의 말로 *"수비를 실제보다 나쁘게 봤을 수
#:     있다"* 는 **보정**이라 **유리**(+1)로 뒀다. 지시서는 T12 를 불리로 적었는데,
#:     T12 는 `_goals._t12` 에서 **둘로 갈려** 발동한다 —
#:     `form_attack_discount`(운 요소 **득점** → 공격 할인 · 불리)와
#:     `form_defense_credit`(운 요소 **실점** → 수비 보정 · 유리). 그래서 지시서의
#:     첫 규칙(*"효과 부호를 읽어"*)대로 **효과별로** 부호를 매겼다.
FAVOUR = {
    "lambda_own": +1,
    "lambda_own_late": +1,
    "lambda_opp": -1,            # 🔴 값이 음수(상대 λ 를 깎는다) → 그 팀에 유리
    "own_win_logodds": +1,
    "form_defense_credit": +1,
    "form_attack_discount": -1,
    "luck_goals": 0,             # 🔴 수량이지 방향이 아니다
    "draw_logodds": 0,           # 🔴 무 쪽 — 어느 팀의 우위도 아니다
}


#: 🔴🔴 **그림자 계산용 끄기**(§4) — 이 값이 참이면 `on`·`which` 가 **전부 꺼짐**을
#:   돌려준다. ⚠️ 운영 확률을 계산한 뒤 **옛 판**을 한 번 더 세는 자리에만 쓴다.
_FORCE_OFF = False


class off:                                                  # noqa: N801
    """🔴 `with m1v2.off():` — 그 블록 안에서는 후보가 **전부 꺼진다**(옛 판)."""

    def __enter__(self):
        global _FORCE_OFF
        self._was = _FORCE_OFF
        _FORCE_OFF = True
        return self

    def __exit__(self, *exc):
        global _FORCE_OFF
        _FORCE_OFF = self._was
        return False


def any_on() -> bool:
    """🔴 후보가 **하나라도** 켜져 있나(그림자를 붙일지 가른다)."""
    if _FORCE_OFF:
        return False
    box = dict(table().get("flags") or {})
    return any(v is True for v in box.values()) or bool(box.get("home_mul"))


def table() -> dict:
    import yaml
    path = ROOT / CONF
    if not path.is_file():
        return {}
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def on(name: str) -> bool:
    """🔴 그 후보가 **켜져 있나**(기본 꺼짐 · `off()` 안에서는 늘 거짓)."""
    if _FORCE_OFF:
        return False
    return bool(dict(table().get("flags") or {}).get(str(name)) is True)


def which(name: str) -> str:
    """🔴 값으로 고르는 후보(③ `home_mul`) — 꺼짐이면 빈 글자."""
    if _FORCE_OFF:
        return ""
    return str(dict(table().get("flags") or {}).get(str(name)) or "")


# ══════════════════════════════════════════════════════════════════
# ① 축3 부호
# ══════════════════════════════════════════════════════════════════

def rule_sign(effect: dict) -> int:
    """🔴🔴 ①a — 그 규칙이 **그 팀에 유리하면 +1 · 불리하면 −1 · 모르면 0**.

    🔴 효과 **이름과 값의 부호**를 함께 본다(`lambda_opp: -0.06` 은 상대 λ 를
       깎으니 그 팀에 유리하다). 여러 칸이 있으면 **합의 부호**다.
    """
    got = 0.0
    for key, val in dict(effect or {}).items():
        base = FAVOUR.get(str(key))
        if not base:
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            continue
        if num == 0.0:
            continue
        got += base * (1.0 if num > 0 else -1.0)
    return 0 if abs(got) < 1e-9 else (1 if got > 0 else -1)


# ══════════════════════════════════════════════════════════════════
# ② 결측 축 가중 재배분
# ══════════════════════════════════════════════════════════════════

def weights_of(base: dict, present: list[str]) -> tuple[dict, str]:
    """🔴🔴 ②a — 있는 축의 가중을 **합 1 로 다시 나눈다**. `(가중, 사유)`.

    🔴 ⬜ 축이 **둘 이상**이면 재배분하지 않는다(남은 축 하나를 과대 반영한다).
    """
    rows = {k: float(base.get(k) or 0.0) for k in present}
    miss = [k for k in base if k not in rows]
    cap = int(table().get("renorm_max_missing") or 1)
    if not miss:
        return rows, "재배분 없다(네 축 다 있다)"
    if len(miss) > cap:
        return rows, (f"🟡 **축 부족** — ⬜ {len(miss)}개({', '.join(miss)}) → "
                      f"재배분하지 않는다(한 축을 과대 반영한다)")
    total = sum(rows.values())
    if total <= 0:
        return rows, "🔴 남은 가중이 0 이다 — 재배분 못 한다"
    out = {k: round(v / total, 4) for k, v in rows.items()}
    return out, (f"**재배분됨** — ⬜ {', '.join(miss)} · "
                 + " · ".join(f"{k} {base[k]:g}→{out[k]:g}" for k in out))


# ══════════════════════════════════════════════════════════════════
# ③ 팀별 홈 배율 후보
# ══════════════════════════════════════════════════════════════════

def team_home(variant: str, games: list[dict], *, league: float,
              prior: float | None = None) -> tuple[float, str]:
    """🔴🔴 ③ — 후보별 **팀** 홈 배율. `(배율, 사유)`.

    ⚠️ 이름이 `team_home` 인 까닭 — `probmodel.home_mul`(리그 쪽 배율)과 **글자가
       겹치면** 계약 `test_v7_홈_배율이_리그_평균과_같은_열쇠를_본다` 가 빨개진다
       (그 계약은 `probmodel` 안의 `home_mul(` 호출을 **전부** 센다 · 실측
       2026-10-14). 🔴 그 계약은 제 일을 한 것이므로 **이름을 바꿨다**.

    · `a` 끄기(리그값) · `b` 대칭식(공격·수비 둘 다) · `c` 수축 강화(K·상한)
    · `d` 이월(지난 시즌 사전값) · 그 밖(빈 글자)이면 **지금 식**은 호출부가 쓴다.
    🔴 표본이 없거나 0 나눗셈이면 **리그값**이다(지어내지 않는다 · #4).
    """
    said = str(variant or "")
    if said == "a":
        return float(league), f"③a 팀별 효과 끄기 — 리그 ×{float(league):.3f}"
    rows = [dict(g) for g in (games or [])]
    at_h = [g for g in rows if str(g.get("side") or "") == "home"]
    at_a = [g for g in rows if str(g.get("side") or "") == "away"]
    n = min(len(at_h), len(at_a))
    box = dict(table().get("home_mul_c") or {})
    k = float(box.get("k") or 16)
    cap = float(box.get("cap") or 1.30)
    if not n:
        base = float(prior) if (said == "d" and prior) else float(league)
        return base, (f"표본 0 쌍 → "
                      + (f"③d 사전값 ×{base:.3f}" if said == "d"
                         else f"리그 ×{base:.3f}"))
    gf_h = sum(float(g.get("gf") or 0.0) for g in at_h) / len(at_h)
    gf_a = sum(float(g.get("gf") or 0.0) for g in at_a) / len(at_a)
    ga_h = sum(float(g.get("ga") or 0.0) for g in at_h) / len(at_h)
    ga_a = sum(float(g.get("ga") or 0.0) for g in at_a) / len(at_a)
    if said == "b":
        # 🔴 ③b 대칭식 — 공격(홈 득점/원정 득점)과 수비(원정 실점/홈 실점)의 기하평균
        if gf_a <= 0 or ga_h <= 0:
            return float(league), (f"리그 ×{float(league):.3f} — 0 나눗셈"
                                   f"(원정 득점 {gf_a:.2f} · 홈 실점 {ga_h:.2f})")
        raw = math.sqrt((gf_h / gf_a) * (ga_a / ga_h))
        raw = max(0.80, min(1.40, raw))
        w = min(n, 8) / 8.0
        got = (1 - w) * float(league) + w * raw
        return round(got, 4), (f"③b 대칭식 ×{raw:.3f}(공격 {gf_h/gf_a:.3f} · 수비 "
                               f"{ga_a/max(ga_h,1e-9):.3f}) · 쌍 {n} · 가중 "
                               f"{w:.0%} · 리그 ×{float(league):.3f} → ×{got:.3f}")
    if gf_a <= 0:
        return float(league), f"리그 ×{float(league):.3f} — 원정 득점이 0 이다"
    raw = gf_h / gf_a
    if said == "c":
        raw = max(1.0 / cap, min(cap, raw))
        w = n / (n + k)
        got = (1 - w) * float(league) + w * raw
        return round(got, 4), (f"③c 수축 강화 ×{raw:.3f} · 쌍 {n} · K {k:g} · "
                               f"가중 {w:.0%} · 상한 {cap:g} → ×{got:.3f}")
    if said == "d":
        raw = max(0.80, min(1.40, raw))
        base = float(prior) if prior else float(league)
        w = n / (n + 8.0)
        got = (1 - w) * base + w * raw
        return round(got, 4), (f"③d 이월 — 사전값 ×{base:.3f} · 이번 시즌 "
                               f"×{raw:.3f}(쌍 {n} · 가중 {w:.0%}) → ×{got:.3f}")
    return float(league), f"후보 `{said}` 를 모른다 — 리그값"


# ══════════════════════════════════════════════════════════════════
# ④ 축0 척도 정규화
# ══════════════════════════════════════════════════════════════════

SCALE_BOX = "data/axis_scale"


def axis_sd(league: str, axis: str = "axis0") -> tuple[float | None, str]:
    """🔴🔴 ④a — 그 리그의 **축 차 표준편차**(이전 시즌까지로 적합한 판).

    🔴 판은 `data/axis_scale/<리그>.yaml` 이고 `tools/fit_axis_scale.py` 가 만든다
       (누설 금지 — 채점 시즌을 넣지 않는다).
    """
    import yaml
    path = ROOT / SCALE_BOX / f"{str(league or '').replace(':', '_')}.yaml"
    if not path.is_file():
        return None, f"⬜ 축 척도 판이 없다(`{path.name}`)"
    got = dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    val = (got.get(axis) or {}).get("sd")
    if not val:
        return None, f"⬜ `{axis}` 표준편차가 판에 없다"
    return float(val), (f"판 `{path.stem}`({axis} sd {float(val):.3f} · "
                        f"표본 {(got.get(axis) or {}).get('n')}경기 · 시즌 "
                        f"{(got.get(axis) or {}).get('seasons')})")
