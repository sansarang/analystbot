"""🔴🔴 **후보 판 넷**(수정·검증 지시 2026-10-14e · CA1~CA8).

> 0 운영 판(M1 · K0 고정)은 판정 통과 전까지 그대로다. 고친 것은 전부 **후보
>   판(설정 플래그)** 으로 만들고, 운영 카드에는 그림자 열로만 붙인다.
> ① 축3 부호 · ② 결측 가중 재배분 · ③ 팀별 홈 배율 · ④ 축0 척도 정규화.

🔴 그래서 계약이 지키는 것은 둘이다 —
   ① **기본이 꺼짐**이고 꺼져 있으면 운영 수가 **한 글자도 안 바뀐다**
   ② 켰을 때 지시서가 적은 수(0.429/0.286/0.286 · T11 감소 …)가 **그대로** 나온다
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

W4 = {"axis0": 0.3, "axis1": 0.3, "axis2": 0.2, "axis3": 0.2}


def _fired(rule: str, side: str, effect: dict, *, watch: bool = False):
    from app.core.goals import Fired
    return Fired(rule=rule, side=side, effect=dict(effect), watch_only=watch)


def _box(fired: list):
    return {"profile": {"home": object(), "away": object()}, "fired": fired}


# ══════════════════════════════════════════════════════════════════
# CA1 — **기본은 꺼짐**이다
# ══════════════════════════════════════════════════════════════════

def test_ca1_켠_것은_판정_통과분뿐이고_전환일이_적혀_있다() -> None:
    """🔴🔴 §4 — **통과한 것만** 켠다 · 켰으면 **전환일**이 있어야 한다.

    🔴 채택(2026-10-14) — ①a 축3 부호(판정 통과 + 버그 수정) · ②a 가중 재배분
       (중립 → 버그 수정으로 채택) · ③a 팀 배율 끄기(`③now` 가 유의하게 해롭다).
    🔴 탈락 — ①b(중립 · ①a 가 대신한다) · ③b·③c·③d(끄기보다 나쁘다) ·
       ④a(전 표본 로그 손실 +0.0017 · 방향 −0.64%p).
    """
    from app.core import m1v2
    box = dict(m1v2.table().get("flags") or {})
    assert box, "플래그 표가 없다"
    assert m1v2.on("axis3_sign") is True
    assert m1v2.on("weight_renorm") is True
    assert m1v2.which("home_mul") == "a", box.get("home_mul")
    # 🔴 탈락분은 **꺼져 있다**
    assert m1v2.on("axis3_off") is False
    assert m1v2.on("axis0_scale") is False
    # 🔴 켠 판에는 **전환일**이 있다(카드 수가 그날부터 바뀐다)
    assert str(m1v2.table().get("switched_at") or ""), "전환일이 비었다"
    # 🔴 판정표 경로가 저장소에 남아 있다(카드 각주가 가리킨다)
    assert (ROOT / "var/accept/judge_stage1.log").exists()


def test_ca1b_끄기_문맥은_전부_꺼진다() -> None:
    """🔴 `m1v2.off()` — 그림자(옛 M1)를 세는 자리가 쓰는 문맥."""
    from app.core import m1v2
    assert m1v2.any_on() is True
    with m1v2.off():
        assert m1v2.any_on() is False
        assert m1v2.on("axis3_sign") is False
        assert m1v2.which("home_mul") == ""
    assert m1v2.on("axis3_sign") is True


def test_ca2_옛_판은_발동_수였다() -> None:
    """🔴 옛 판(후보 꺼짐) — 불리한 규칙(T11)도 그 팀을 **올렸다**(그게 버그였다).

    🔴 그 식이 **아직 코드에 있다**(그림자 비교가 그것을 쓴다 · §4 탈락분 보존).
    """
    from app.core import m1v2, matchup as mu
    with m1v2.off():
        got = mu.axis3(_box([_fired("T11", "home",
                                    {"draw_logodds": 0.12,
                                     "own_win_logodds": -0.08})]), None, r={})
    assert got.gap is not None and got.gap > 0, got.why


# ══════════════════════════════════════════════════════════════════
# CA3 — ①a 규칙 부호
# ══════════════════════════════════════════════════════════════════

def test_ca3_규칙_부호표() -> None:
    from app.core import m1v2
    assert m1v2.rule_sign({"lambda_own": 0.08}) == +1
    assert m1v2.rule_sign({"lambda_own_late": 0.12}) == +1
    assert m1v2.rule_sign({"lambda_opp": -0.06}) == +1       # 상대 λ 를 깎는다
    assert m1v2.rule_sign({"draw_logodds": 0.12,
                           "own_win_logodds": -0.08}) == -1  # T11
    assert m1v2.rule_sign({"form_attack_discount": 0.5,
                           "luck_goals": 3}) == -1           # T12 공격
    assert m1v2.rule_sign({"form_defense_credit": 0.5}) == +1  # T12 수비
    assert m1v2.rule_sign({}) == 0


def test_ca4_축3_부호판은_불리한_규칙을_내린다() -> None:
    """🔴 ①a — T11(효과 −0.08)이 발동한 쪽 축3 이 **내려간다**(운영 전환분)."""
    from app.core import matchup as mu
    bad = mu.axis3(_box([_fired("T11", "home",
                                {"draw_logodds": 0.12,
                                 "own_win_logodds": -0.08})]), None, r={})
    assert bad.gap is not None and bad.gap < 0, bad.why
    good = mu.axis3(_box([_fired("T9", "home", {"lambda_own": 0.08})]),
                    None, r={})
    assert good.gap is not None and good.gap > 0, good.why
    none = mu.axis3(_box([]), None, r={})
    assert none.gap == 0.0, none.why
    # 🔴 부호표가 카드 사유에 남는다(무엇이 왜 깎였는지 보인다)
    assert "부호판 ①a" in bad.why


# ══════════════════════════════════════════════════════════════════
# CA5 — ②a 가중 재배분
# ══════════════════════════════════════════════════════════════════

def test_ca5_가중_재배분_수가_지시서와_같다() -> None:
    from app.core import m1v2
    got, why = m1v2.weights_of(W4, ["axis0", "axis2", "axis3"])
    assert got == {"axis0": 0.4286, "axis2": 0.2857, "axis3": 0.2857}, got
    assert "재배분됨" in why
    # 🔴 둘 이상 ⬜ → 재배분하지 않는다
    got2, why2 = m1v2.weights_of(W4, ["axis0", "axis2"])
    assert got2 == {"axis0": 0.3, "axis2": 0.2}, got2
    assert "축 부족" in why2


def test_ca6_켜면_종합이_재배분을_쓴다(monkeypatch) -> None:
    from app.core import m1v2, matchup as mu
    axes = {"axis0": mu.Axis(name="axis0", home=1.0, away=0.0),
            "axis1": mu.Axis(name="axis1"),
            "axis2": mu.Axis(name="axis2", home=0.0, away=0.0),
            "axis3": mu.Axis(name="axis3", home=0.0, away=0.0)}
    for one in axes.values():
        one.gap = None if one.name == "axis1" else (one.home - one.away)
    with m1v2.off():
        off = mu.combine(axes)
    monkeypatch.setattr(m1v2, "on", lambda name: name == "weight_renorm")
    on = mu.combine(axes)
    assert abs(off["score"] - 0.3) < 1e-6, off
    assert abs(on["score"] - 0.4286) < 1e-3, on       # 0.3/0.7
    assert "재배분됨" in on["why"]


# ══════════════════════════════════════════════════════════════════
# CA7 — ③ 팀 홈 배율 후보
# ══════════════════════════════════════════════════════════════════

def test_ca7_홈_배율_후보들() -> None:
    from app.core import m1v2
    games = [{"side": "home", "gf": 2, "ga": 1}, {"side": "home", "gf": 1,
                                                  "ga": 0},
             {"side": "away", "gf": 1, "ga": 2}, {"side": "away", "gf": 0,
                                                  "ga": 3}]
    a, why_a = m1v2.team_home("a", games, league=1.12)
    assert a == 1.12 and "끄기" in why_a
    b, why_b = m1v2.team_home("b", games, league=1.12)
    assert 0.80 <= b <= 1.40 and "대칭식" in why_b
    c, why_c = m1v2.team_home("c", games, league=1.12)
    assert 0.80 <= c <= 1.40 and "수축 강화" in why_c
    # 🔴 0 나눗셈 — 원정 득점이 0 이면 리그값
    zero = [{"side": "home", "gf": 2, "ga": 0}, {"side": "away", "gf": 0,
                                                 "ga": 2}]
    got, why = m1v2.team_home("c", zero, league=1.12)
    assert got == 1.12 and "0" in why
    # 🔴 표본 0 쌍 → 리그값(③d 는 사전값)
    got2, _w = m1v2.team_home("c", [], league=1.12)
    assert got2 == 1.12
    got3, why3 = m1v2.team_home("d", [], league=1.12, prior=1.05)
    assert got3 == 1.05 and "사전값" in why3


def test_ca8_운영_경로는_후보를_하나로_들어간다() -> None:
    """🔴 ③ 은 `probmodel.team_home_mul` **한 자리**에서 갈린다(사본 금지)."""
    import inspect

    from app.core import probmodel as pm
    said = inspect.getsource(pm.team_home_mul)
    assert 'which("home_mul")' in said and "_c.team_home(" in said


# ══════════════════════════════════════════════════════════════════
# CA9 — ④a 척도 · 백필 재료
# ══════════════════════════════════════════════════════════════════

def test_ca9_축_척도_판을_읽는다() -> None:
    from app.core import m1v2
    sd, why = m1v2.axis_sd("league:ELC", "axis0")
    assert sd and sd > 0, why
    none, why2 = m1v2.axis_sd("league:없는리그", "axis0")
    assert none is None and "⬜" in why2


def test_ca10_백필이_축3_부호_재료를_적는다() -> None:
    """🔴 판정기가 ①a 를 **같은 표본**에서 재려면 백필이 그 칸을 적어야 한다.

    🔴 그리고 그 칸은 **가중표에 없다** — 그래서 지금 판의 종합을 안 바꾼다.
    """
    said = (ROOT / "app/core/backfill.py").read_text(encoding="utf-8")
    assert 'gaps["axis3_sign"]' in said
    from app.core import matchup as mu
    assert "axis3_sign" not in dict(mu.table().get("weights") or {})
