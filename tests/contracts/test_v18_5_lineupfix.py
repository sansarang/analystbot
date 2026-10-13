"""🔴🔴 **§4 후보 신호 · §5 경계 모듈**(라인업 지시서 2026-10-13).

> M1(legacy-4axis) 코드는 **K0 고정**. 라인업 보정은 M1 격자 계산 **직전 λ** 에
> 거는 경계 모듈 `app/core/lineupfix.py` 로만.
> `log λ홈 += Σ g_k·L_k` · `log λ원정 −= Σ g_k·L_k` → 팀 총골 기대 **±2% 정규화**
> → 격자 재계산. 계수 `g_k` 는 릿지·시즌 교차 · 판
> `data/lineupfix/<league>/<as_of>.yaml`. 상한 감시 `|g_k·sd(L_k)| > 0.15` → **판 무효**.

계약 **LF1** 직교화 안 한 신호 진입 실패 · **LF2** 상한 초과 판 운영 금지 ·
**LF3** `old_engine` 해시 변경 실패(K0) · **LF4** 판 없이 보정 실패.

🔴 신호는 **전부 차분값**이다(§4) — 수준값(축0 로그 가치 합)은 **이미 M1 안에**
   있으므로 쓰지 않는다. 계약이 그 이름을 센다.
"""
from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc


def _plate(**g) -> dict:
    """🔴 판 한 장 — 채택 신호의 `g`·`sd`·직교화 계수를 함께 든다."""
    return {"adopted": sorted(g),
            "g": {k: v for k, v in g.items()},
            "sd": {k: 0.1 for k in g},
            "ortho": {k: {"a": 0.0, "b": 0.0} for k in g}}


# ══════════════════════════════════════════════════════════════════
# §4 — 신호는 전부 **차분값**이다
# ══════════════════════════════════════════════════════════════════

def test_signals_are_all_differences() -> None:
    from app.core import lineupfix as lf
    # ⚠️ **재료 교체**(사용자 결정 2026-10-13 저녁)로 L6·L7·L8 이 더해졌다 —
    #    §4 의 다섯은 그대로 있어야 한다(지운 것이 아니다).
    assert tuple(lf.SIGNALS)[:5] == ("L1", "L2", "L3", "L4", "L5")
    side = {"xi": ["p1", "p2"], "usual": ["p1", "p3"], "bench": ["p4"]}
    got, why = lf.raw_of(
        home=side, away={"xi": ["q1", "q2"], "usual": ["q1", "q2"],
                         "bench": ["q3"]},
        value={"p1": 0.3, "p2": 0.1, "p3": 0.5, "p4": 0.0,
               "q1": 0.0, "q2": 0.0, "q3": 0.0})
    assert set(got) == {"L1", "L2", "L3", "L4", "L5"}, got
    # 🔴 홈이 평소 주전 하나(p3 · 0.5)를 빼고 p2(0.1)를 넣었다 → L2 는 **양수**
    assert got["L2"] > 0, (got, why)
    # 🔴 L3 — 홈 2/2 중 1명만 평소 XI → 0.5, 원정은 1.0 → 차는 **음수**
    assert got["L3"] < 0, got
    # 🔴 수준값이 아니다 — 두 팀을 똑같이 올리면 **신호가 안 바뀐다**
    up = {k: v + 1.0 for k, v in {"p1": 0.3, "p2": 0.1, "p3": 0.5, "p4": 0.0,
                                  "q1": 0.0, "q2": 0.0, "q3": 0.0}.items()}
    got2, _w = lf.raw_of(home=side,
                         away={"xi": ["q1", "q2"], "usual": ["q1", "q2"],
                               "bench": ["q3"]}, value=up)
    assert abs(got2["L1"] - got["L1"]) < 1e-9, (got, got2)


# ══════════════════════════════════════════════════════════════════
# 🔴 LF1 — **직교화 안 한 신호는 못 들어온다**
# ══════════════════════════════════════════════════════════════════

def test_lf1_raw_signal_cannot_enter() -> None:
    from app.core import lineupfix as lf
    plate = _plate(L1=0.5)
    del plate["ortho"]["L1"]              # 🔴 직교화 계수가 **없다**
    got, why = lf.apply({"home": 1.4, "away": 1.1}, raw={"L1": 0.2},
                        plate=plate)
    assert got == {"home": 1.4, "away": 1.1}, got     # 🔴 λ 를 **안 건드린다**
    assert "직교" in why and "🔴" in why, why


def test_ortho_removes_the_axis0_part() -> None:
    """🔴 직교화 — 축0 차로 설명되는 몫을 **뺀다**(판의 a·b 로)."""
    from app.core import lineupfix as lf
    got, why = lf.ortho({"L1": 0.5}, axis0=1.0,
                        plate={"ortho": {"L1": {"a": 0.1, "b": 0.3}}})
    assert abs(got["L1"] - 0.1) < 1e-9, (got, why)


# ══════════════════════════════════════════════════════════════════
# 🔴 LF2 — **상한 초과 판은 운영 금지**
# ══════════════════════════════════════════════════════════════════

def test_lf2_blown_coefficient_invalidates_the_plate() -> None:
    from app.core import lineupfix as lf
    plate = _plate(L1=2.0)                # |2.0 × 0.1| = 0.2 > 0.15
    got, why = lf.apply({"home": 1.4, "away": 1.1}, raw={"L1": 0.2},
                        plate=plate)
    assert got == {"home": 1.4, "away": 1.1}, got
    assert "상한" in why and "무효" in why, why


# ══════════════════════════════════════════════════════════════════
# 🔴 LF4 — **판 없이 보정 없음**
# ══════════════════════════════════════════════════════════════════

def test_lf4_no_plate_no_correction() -> None:
    from app.core import lineupfix as lf
    got, why = lf.apply({"home": 1.4, "away": 1.1}, raw={"L1": 0.2}, plate={})
    assert got == {"home": 1.4, "away": 1.1}, got
    assert "판" in why and "🔴" in why, why
    # 🔴 판 고르기는 `versions` 하나다(L3 · 엄격히 이전)
    said, why2 = lf.plate_of(league="league:J1",
                             as_of=datetime(2000, 1, 1, tzinfo=UTC))
    assert said == {} and "🔴" in why2, why2


# ══════════════════════════════════════════════════════════════════
# 보정이 **실제로** λ 를 움직인다 · 총골은 ±2% 안이다
# ══════════════════════════════════════════════════════════════════

def test_correction_moves_lambda_and_keeps_the_total() -> None:
    from app.core import lineupfix as lf
    lam = {"home": 1.4, "away": 1.1}
    got, why = lf.apply(lam, raw={"L1": 0.2}, plate=_plate(L1=0.5))
    assert got["home"] > lam["home"] and got["away"] < lam["away"], (got, why)
    was, now = sum(lam.values()), sum(got.values())
    assert abs(now / was - 1.0) <= 0.02 + 1e-9, (was, now, why)
    assert "라인업 보정" in why, why


# ══════════════════════════════════════════════════════════════════
# 🔴 LF3 — **얼린 M1 을 건드리지 않는다**(K0)
# ══════════════════════════════════════════════════════════════════

def test_lf3_frozen_engine_is_untouched() -> None:
    import ast
    import hashlib
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    said = (root / "app/core/legacy/old_engine.py").read_bytes()
    got = hashlib.sha256(said).hexdigest()
    # 🔴 K0 — 해시는 `test_v16_0_legacy.py` 가 든다(사본 금지: 여기서 그 값을
    #    다시 적지 않고 **그 계약이 있는지**와 **경계가 얼린 코드를 안 고치는지**만 센다)
    pin = (root / "tests/contracts/test_v16_0_legacy.py").read_text(
        encoding="utf-8")
    assert got in pin, "🔴 얼린 경로가 바뀌었다 — K0 계약을 먼저 본다"
    tree = ast.parse((root / "app/core/lineupfix.py").read_text(
        encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    code = ast.unparse(tree)
    assert "old_engine" not in code, "🔴 경계가 얼린 코드를 부른다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **판정 규칙은 실행 전에 못 박는다**(§6 · 지시서 2026-10-13)
# ══════════════════════════════════════════════════════════════════
#
#  > (a) 로그 손실 점추정 < B · 구간 하한 < 0
#  > (b) 방향이 B 보다 **낮지 않음**(맥니마 **B 우세** p<0.05 탈락)
#  > (c) 상위 30/20/10% 평균 **≥ B**
#  ⚠️ 앞선 `v2` 의 (b)는 *"도전이 유의하게 낫다"* 였다 — **더 엄격**했다.
#     🔴 그래서 이름을 가른다(`rule="lineup"`) — 옛 시험의 판정은 그대로 둔다.

def test_lineup_rule_is_committed_before_the_trial() -> None:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    import judge_models as jm
    base = {0.30: 0.50, 0.20: 0.50, 0.10: 0.50}
    # 🔴 (a) 통과 · (b) B 가 낫지만 **유의하지 않다** · (c) 같다 → 통과
    ok, box, why = jm.passes(diff={"mean": -0.01, "lo": -0.02, "hi": 0.001},
                             dir_rate=0.49, base_dir=0.50, p_value=0.40,
                             bands=base, base_bands=base, rule="lineup")
    assert ok and box == {"a": True, "b": True, "c": True}, why
    # 🔴 B 가 **유의하게** 낫다 → (b) 탈락
    bad, box2, why2 = jm.passes(diff={"mean": -0.01, "lo": -0.02, "hi": 0.0},
                                dir_rate=0.44, base_dir=0.52, p_value=0.01,
                                bands=base, base_bands=base, rule="lineup")
    assert not bad and box2["b"] is False, why2
    # 🔴 구간 하한이 0 을 못 넘으면 (a) 탈락
    bad2, box3, _w = jm.passes(diff={"mean": -0.001, "lo": 0.002, "hi": 0.01},
                               dir_rate=0.55, base_dir=0.50, p_value=0.9,
                               bands=base, base_bands=base, rule="lineup")
    assert not bad2 and box3["a"] is False


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **(d) 조건** — 사용자 결정 2026-10-13(저녁) · 다음 시험부터
# ══════════════════════════════════════════════════════════════════
#
#  > 채택에 (d) 추가 — 평소→확정 XI 확률 변화 **평균 ≥ 1.0%p** 이고,
#  > 변화 **≥ 3%p 경기의 방향 적중률 ≥ B**.
#  🔴 왜 — `B+L1` 은 (a)(b)(c)를 통과했는데 폭이 **0.12%p** · ≥3%p 경기 **0건**
#     이었다. 규칙을 통과해도 **라인업이 반영된 것이 아니다**.

def test_rule_d_requires_real_movement() -> None:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    import judge_models as jm
    base = {0.30: 0.50, 0.20: 0.50, 0.10: 0.50}
    good = {"diff": {"mean": -0.01, "lo": -0.02, "hi": 0.001},
            "dir_rate": 0.50, "base_dir": 0.50, "p_value": 0.9,
            "bands": base, "base_bands": base, "rule": "lineup2"}
    # 🔴 (a)(b)(c) 통과 + 폭 1.2%p · ≥3%p 20경기에서 방향이 B 보다 높다 → 채택
    ok, box, why = jm.passes(**good, move={"mean": 0.012, "wide_n": 20,
                                           "wide_hit": 0.55,
                                           "base_wide_hit": 0.50})
    assert ok and box["d"] is True, why
    # 🔴 폭이 0.12%p 면 **탈락**(지난 시험의 `B+L1` 이 이 자리다)
    bad, box2, why2 = jm.passes(**good, move={"mean": 0.0012, "wide_n": 0,
                                              "wide_hit": 0.0,
                                              "base_wide_hit": 0.0})
    assert not bad and box2["d"] is False and "잴 것이 없다" in why2, why2
    # 🔴 폭은 넓지만 넓게 움직인 경기에서 **방향이 더 낮으면** 탈락
    bad2, box3, _w = jm.passes(**good, move={"mean": 0.02, "wide_n": 19,
                                             "wide_hit": 0.368,
                                             "base_wide_hit": 0.421})
    assert not bad2 and box3["d"] is False
