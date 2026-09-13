"""SEND-1 — 카드가 `p_code` 를 읽는다 (사용자 결정 B-1, 2026-09-13).

사용자 결정 둘:
  · **딥서치 이동을 `p_code` 에 더한다** — 호출 비용을 이미 썼으므로 버리지 않는다.
  · **소비 지점(카드·보드)에서 갈아끼운다** — 판정·딥서치 로직은 안 건드리고,
    원장에는 제미나이 확률·`p_code`·`p_model` 이 전부 남아 사후 대조가 된다.

🔴 **카드와 보드가 같은 값을 쓴다.** 실사고 2026-09-05: 게이트가 둘로 갈려
   한 카드가 두 말을 했다("우리 53% — 시장 동의" 와 "시장 이견 47% vs 54%").
"""
import pytest

from app.engine import prob as P


def _jg(**kw):
    base = {"sport": "mlb", "home": "H", "away": "A",
            "p_market_spine": 0.60, "p_claude": 0.52}
    base.update(kw)
    return base


# ── 계산

def test_시장과_조정과_딥서치를_더한다():
    jg = _jg(out_starters=2, deepsearch={"이동_pp": 1.2})
    # 시장 0.60 + 주전결장(−1.5×2 = −3.0 → 축소 −1.5%p) + 딥서치 +1.2%p
    assert P.p_send(jg) == pytest.approx(0.597, abs=1e-4)


def test_딥서치가_없으면_시장더하기조정이다():
    jg = _jg(out_starters=2)
    assert P.p_send(jg) == P.p_code(0.60, P.adjustments(jg), "mlb")


def test_시장이_없으면_None이다():
    """🔴 Elo·0.5 로 대체하지 않는다. 없으면 카드는 종전 값으로 폴백한다."""
    assert P.p_send(_jg(p_market_spine=None)) is None


def test_합계_상한을_넘지_않는다():
    """딥서치가 크게 움직여도 시장에서 멀어지는 폭은 표의 상한 안이다."""
    jg = _jg(deepsearch={"이동_pp": 40.0})
    assert abs(P.p_send(jg) - 0.60) <= P.ADJ_SUM_CAP / 100 + 1e-9


def test_승률_상한으로_절사된다():
    jg = _jg(p_market_spine=0.67, deepsearch={"이동_pp": 6.0})
    from app.config import get_settings

    assert P.p_send(jg) <= float(get_settings().max_win_prob_mlb) + 1e-9


# ── 카드

def test_카드가_p_send를_쓴다():
    from app.engine import form_card as F

    jg = _jg(p_send=0.64, matchup={"p_home": 0.52, "우세": "home"})
    side, p = F.favored_side_and_p(jg)
    assert (side, p) == ("home", 0.64)


def test_p_send가_없으면_종전대로다():
    from app.engine import form_card as F

    jg = _jg(matchup={"p_home": 0.52, "우세": "home"})
    assert F.favored_side_and_p(jg) == ("home", 0.52)


def test_원정_우세면_뒤집어_준다():
    from app.engine import form_card as F

    jg = _jg(p_send=0.40, matchup={"p_home": 0.52, "우세": "away"})
    side, p = F.favored_side_and_p(jg)
    assert side == "away" and p == pytest.approx(0.60)


def test_시장_동의_게이트도_같은_값을_본다():
    """🔴 카드 본문과 게이트가 다른 값을 보면 한 카드가 두 말을 한다."""
    import inspect

    from app.engine import form_card as F

    src = inspect.getsource(F)
    # `p_home": jg.get("p_claude")` 로 게이트에 넘기던 자리가 남아 있으면 안 된다
    assert '"p_home": jg.get("p_claude")' not in src, src


# ── 보드(자격 게이트)

def test_보드_확률도_p_send로_간다():
    """🔴 야구는 `_compute_picks` 안의 **BASEBALL_SPORTS 분기**를 탄다 —
       그 분기가 `continue` 로 λ 경로를 건너뛰므로 아래쪽만 고치면
       KBO·NPB·MLB 보드는 옛 값 그대로다(실측: 두 분기에 `build_board` 가 있다).
    """
    import inspect

    from app import pipeline as PL

    src = inspect.getsource(PL._compute_picks)
    # ⚠️ `continue` 로 분기를 가르지 않는다 — 앞쪽(status != scheduled)에도
    #    하나 있어 슬라이스가 엉뚱한 데서 잘린다(무딘 계약 전례).
    i = src.index("if sport in BASEBALL_SPORTS:")
    branch = src[i:src.index("build_board", i)]
    assert 'ph = jg.get("p_send") or jg.get("p_claude")' in branch, branch[-500:]
    assert src.count("p_send") >= 2, src.count("p_send")


# ── 원장

def test_원장은_LLM_확률을_그대로_남긴다():
    """🔴 사후 대조의 재료다 — 여기까지 갈아끼우면 비교할 것이 없어진다."""
    import inspect

    from app.engine import pick_ledger as L

    src = inspect.getsource(L._row_from_game)
    assert '"p_home": jg.get("p_claude")' in src, src


def test_원장의_p_code는_실제_나간_값이다():
    import inspect

    from app.engine import pick_ledger as L

    src = inspect.getsource(L._row_from_game)
    assert 'jg.get("p_send")' in src, src
