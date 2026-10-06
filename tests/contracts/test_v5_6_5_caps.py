"""🔴🔴 **v5 §6-5 — 라인업 상태가 등급 상한을 정한다**(네 칸 + 야구 두 칸).

지시문 §6-5 원문:

> 상한(라인업 상태) — **양쪽 확정 1.0 / 한쪽 확정 0.9 / 양쪽 예상 0.85 / 한쪽이
> 라도 없음 0.8.** 야구는 선발 확정·타순 미공개 0.9, 선발 폼 자료 공백 0.85.
> 중립 구장 친선에서 실험 중인 팀의 무패 마켓 0.8. 행사 경기(은퇴·자선)는 승패
> 마켓 접기. **발표됐으나 미검증인 XI 는 "미공개"가 아니라 "미검증"으로 적고
> 한 단계 아래.** 등급 = min(생존 등급, 상한).

══════════════════════════════════════════════════════════════════
🔴 종전은 **세 칸**이었다 — v5 가 **네 칸**을 요구한다
══════════════════════════════════════════════════════════════════

    종전   확정 1.0 / 예상 0.85 / 없음 0.8
    v5     양쪽확정 1.0 / **한쪽확정 0.9** / 양쪽예상 0.85 / 없음 0.8

⚠️ 한쪽만 확정인 경기가 종전에 `예상`(0.85)으로 떨어졌다 — **한쪽을 확실히
   아는 것**과 **양쪽 다 추측인 것**은 모르는 양이 다르다.
🔴 그리고 야구에 **아예 안 걸렸다**(`sports: [soccer]`) — §6-5 가 야구 두 칸을
   이름으로 댔다.
"""
from __future__ import annotations


def _caps() -> dict:
    from app import rules
    return {str(k): float(v) for k, v in
            (rules.xi_state_cap().get("caps") or {}).items()}


def test_v5_6_5_네_칸이_선언돼_있다_M24():
    """🔴 지시문이 **이름으로 댄** 네 칸 전부. ⚠️ 값까지 본다."""
    caps = _caps()
    want = {"양쪽확정": 1.0, "한쪽확정": 0.9, "양쪽예상": 0.85, "없음": 0.8}
    for k, v in want.items():
        assert k in caps, f"🔴 §6-5 가 이름으로 댄 칸 `{k}` 이 yaml 에 없다"
        assert caps[k] == v, f"🔴 `{k}` 상한이 {caps[k]} 다 — §6-5 는 {v} 다"


def test_v5_6_5_야구_두_칸이_선언돼_있다():
    """🔴 *"야구는 선발 확정·타순 미공개 0.9, 선발 폼 자료 공백 0.85."*"""
    caps = _caps()
    assert caps.get("선발확정_타순미공개") == 0.9, caps
    assert caps.get("선발폼공백") == 0.85, caps


def test_v5_6_5_야구에도_상한을_건다():
    """🔴 종전 `sports: [soccer]` 가 **야구를 통째로 빼놨다.**"""
    from app import rules
    sports = [str(x) for x in (rules.xi_state_cap().get("sports") or [])]
    assert "baseball" in sports, (
        f"🔴 §6-5 가 야구 상한을 이름으로 댔는데 적용 종목에 없다: {sports}")


def test_v5_6_5_한_단계_아래가_사다리로_정해진다():
    """🔴🔴 *"미검증인 XI 는 … **한 단계 아래**"* — 사다리가 있어야 한다.

    ⚠️ `0.9 - 0.05` 같은 **산수로 짓지 않는다** — 칸이 1.0/0.9/0.85/0.8 이라
       간격이 고르지 않다(0.1·0.05·0.05). 🔴 **다음 칸**으로 내린다.
    """
    from app import survive
    assert survive.step_down(1.0) == 0.9
    assert survive.step_down(0.9) == 0.85
    assert survive.step_down(0.85) == 0.8
    # 🔴 바닥에서 더 못 내려간다 — 0 으로 떨어뜨리지 않는다
    assert survive.step_down(0.8) == 0.8
    # ⚠️ 사다리에 없는 수는 **그 아래 첫 칸**으로
    assert survive.step_down(0.95) == 0.9




def _game(sport: str = "soccer"):
    from app import classify
    return classify.Game(home="A", away="B", sport=sport, league="L")




def test_v5_6_5_미검증은_한_단계_아래를_받는다():
    """🔴 **끝까지 잇는다** — 상태 글자가 아니라 **상한 수**가 내려가야 한다."""
    from app import survive
    res = survive.Result()
    cap_ok = survive._xi_cap(res, _game(), "양쪽확정")
    cap_un = survive._xi_cap(res, _game(), "양쪽확정·미검증")
    # 🔴 확정은 상한이 없는 것과 같다(1.0) → `None`
    assert cap_ok is None
    assert cap_un == 0.9, cap_un
    assert any("미검증" in n for n in res.notes), res.notes


def test_v5_6_5_모르면_가장_센_상한():
    """⚠️ fail-closed — 모르는데 상한을 푸는 것은 우리에게 유리한 거짓말이다."""
    from app import survive
    res = survive.Result()
    assert survive._xi_cap(res, _game(), "알수없는칸") == 0.8
    assert any("못 쟀다" in n for n in res.notes), res.notes


def test_v5_6_5_야구_칸이_실제로_상한을_건다():
    """🔴 야구 두 칸이 **수로** 듣나 — 선언만 있고 안 걸리면 없는 것이다."""
    from app import survive
    res = survive.Result()
    g = _game("baseball")
    assert survive._xi_cap(res, g, "선발확정_타순미공개") == 0.9
    assert survive._xi_cap(res, g, "선발폼공백") == 0.85


def test_v5_6_5_근거_없는_칸이_없다():
    """🔴 §5-6 — 상한은 **수**다. 근거 없이 적으면 임의 상수다."""
    from app import rules
    cfg = rules.xi_state_cap()
    assert str(cfg.get("source") or "").strip(), "🔴 `source` 가 비었다"
    assert str(cfg.get("why") or "").strip(), "🔴 `why` 가 비었다"
    # ⚠️ 칸마다 **왜 그 수인가**가 있어야 한다
    basis = cfg.get("basis") or {}
    for k in _caps():
        assert str(basis.get(k) or "").strip(), (
            f"🔴 상한 `{k}` 에 근거가 없다 — §5-6 은 근거 없는 상수를 금지한다")
