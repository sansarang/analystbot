"""CONF-1 — 확신 등급을 코드가 정한다 (1차 결정 3 · 2차 결정 C).

🔴 종전: `verdict.level()` 은 **라벨 정규화뿐**이고 등급은 LLM 자기신고였다.
   AUC 0.5122 짜리 판정에 AI가 스스로 붙인 등급을 그대로 실어 보냈다.

규칙(사용자 결정 1차-3):
  상  라인업/타순 확정 · 필수 축 전부 DB있음 · p_code ≥ 0.63 ·
      |p_code − p_market| ≤ 4%p · adj_pp 항목 ≥ 2
  중  p_code ≥ 0.58 · |괴리| ≤ 4%p · 필수 축 2/3 이상
  하  그 외. p_market NULL · 라인업 잠정 · 필수 축 결측이면 무조건 하

⚠️ `DB본것`(자기보고)·채택 자료 수·뉴스 건수는 **입력에서 제외**한다.
⚠️ [2차 결정 C] `divergence_pp = p_code − p_market = Σadj` 로 정의를 고정한다
   (LLM 확률과 시장의 차이가 아니다).
⚠️ 조정이 붙기 전에는 `adj_pp` 항목이 0~1 이라 **상이 드문 것이 정상**이다.
"""
import pytest

from app.engine import confidence as C


def _jg(**kw):
    base = {"sport": "mlb", "lineup_status": "confirmed",
            "p_code": 0.65, "p_market_spine": 0.63,
            "adj_pp": '{"주전결장": -3.0, "필승조연투": -1.0}'}
    base.update(kw)
    return base


_HAVE_BB = ["선발 최근 등판", "불펜 최근 폼과 가용성"]


def test_필수축을_손으로_적지_않는다():
    """⚠️ 이름의 원본은 `dbref.ITEMS` 다."""
    from app.engine.dbref import ITEMS

    names = {n for n, _ in ITEMS}
    for axis in C.REQUIRED_AXES["mlb"] + C.REQUIRED_AXES["soccer"]:
        assert axis in names, axis


def test_상은_조건_전부를_만족해야_한다():
    assert C.by_code(_jg(), _HAVE_BB) == "상"


@pytest.mark.parametrize("patch", [
    {"lineup_status": "predicted"},        # 잠정
    {"p_code": 0.60},                      # 0.63 미만
    {"p_market_spine": 0.55},              # 괴리 10%p
    {"adj_pp": '{"주전결장": -3.0}'},        # 항목 1개
])
def test_하나라도_어긋나면_상이_아니다(patch):
    assert C.by_code(_jg(**patch), _HAVE_BB) != "상"


def test_중은_058과_괴리4퍼센트포인트다():
    jg = _jg(p_code=0.59, p_market_spine=0.57, adj_pp='{"주전결장": -3.0}')
    assert C.by_code(jg, _HAVE_BB) == "중"


def test_시장이_없으면_무조건_하():
    """🔴 뼈대가 없으면 등급을 붙이지 않는다."""
    assert C.by_code(_jg(p_market_spine=None, p_code=None), _HAVE_BB) == "하"


def test_라인업이_잠정이면_무조건_하():
    assert C.by_code(_jg(lineup_status="predicted"), _HAVE_BB) == "하"


def test_필수축이_결측이면_하():
    assert C.by_code(_jg(), []) == "하"


def test_자기보고를_입력으로_쓰지_않는다():
    """🔴 `DB본것`·채택 수·뉴스 건수는 등급에 영향이 없어야 한다."""
    a = C.by_code(_jg(), _HAVE_BB)
    b = C.by_code(_jg(order_v3={"DB본것": [], "자료": []}, news_count=0), _HAVE_BB)
    assert a == b == "상"


def test_괴리는_조정의_합이다():
    """⚠️ [결정 C] divergence_pp = p_code − p_market = Σadj."""
    assert C.divergence_pp(0.55, 0.58) == pytest.approx(-3.0, abs=1e-9)
    assert C.divergence_pp(None, 0.58) is None
    assert C.divergence_pp(0.55, None) is None


# ── verdict.level() 교체

def test_level은_입력값_복사_검증이다():
    """🔴 LLM 등급은 코드 등급과 **글자 단위로 같아야** 한다. 다르면 반려."""
    from app.engine import verdict as V

    assert V.level("상", expected="상") == "상"
    assert V.level("중", expected="상") is None      # 불일치 → 반려
    assert V.level("없는등급", expected="하") is None


def test_level은_기대값을_반드시_받는다():
    """🔴 [P0-1 2026-09-15] 종전 이 테스트는 **결함을 잠그고 있었다.**

    "호출부가 아직 기대값을 못 주는 경로가 있다"며 `level(raw)` 를 허용했고,
    `verdict.decide()` 가 바로 그 모양으로 불러 LLM 자기신고를 통과시켰다
    (7432 "파르마 승 · 확신 상"). 이제 기대값은 필수다 — 정규화만 필요하면
    `shadow_level` 이고, 그 값은 **카드에 실리지 않는다.**
    """
    import pytest as _pt

    from app.engine import verdict as V

    with _pt.raises(TypeError):
        V.level("중")
    assert V.level("중", "중") == "중"
    assert V.level("상", "중") is None
    assert V.shadow_level("중") == "중"
    assert V.shadow_level("없는등급") == "하"


def test_파이프라인이_코드등급을_세운다():
    """🔴 배선이 없으면 위 규칙이 다 맞아도 원장은 LLM 등급을 쓴다."""
    import inspect

    from app import pipeline as PL

    src = inspect.getsource(PL._attach_market_spine)
    assert "by_code" in src and "code_confidence" in src, src[-500:]
    # 자기보고가 아니라 `있음` 을 쓴다
    assert '["있음"]' in src, src[-500:]


def test_원장이_코드등급을_우선한다():
    import inspect

    from app.engine import pick_ledger as L

    src = inspect.getsource(L._row_from_game)
    i = src.index('"confidence"')
    assert "code_confidence" in src[i:i + 200], src[i:i + 200]


def test_괴리_정의가_고정됐다():
    """⚠️ [결정 C] divergence_pp = p_code − p_market = Σadj."""
    import inspect

    from app import pipeline as PL

    src = inspect.getsource(PL._attach_market_spine)
    assert "divergence_pp" in src and "_conf.divergence_pp" in src
