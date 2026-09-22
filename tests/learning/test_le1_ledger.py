"""[LE-1a] T-LE1 계약 — 원장과 지표.

지시문 원문:
> T-LE1 `test_close_is_last_pre_kickoff` · `test_clv_sign_convention`
> (우리 쪽으로 종가가 움직이면 +) · `test_metrics_on_known_fixture`
> (손으로 계산한 10건과 일치) · `test_ledger_row_immutable_after_settle`

🔴 **`test_metrics_on_known_fixture` 는 손으로 계산한다.** 코드가 낸 값을 그대로
   기대값에 적으면 그 계약은 아무것도 검증하지 않는다(이 저장소의 '거짓 통과'
   목록에 같은 형태가 넷 있다).
"""
from __future__ import annotations

import math

import pytest

from app.learning import metrics as M

# ── 손으로 계산한 픽스처 10건 ────────────────────────────────────────
#   p_model · 결과 · 결정시점 확률 · 종가 확률 · 결정시점 배당
#   🔴 기대값은 **아래 주석의 산술**로 얻었다. 코드 출력을 베끼지 않았다.
FIX = [
    {"p_model": 0.60, "result": "win",  "p_market_at_decision": 0.55,
     "p_close": 0.60, "price_at_decision": 1.80},
    {"p_model": 0.55, "result": "loss", "p_market_at_decision": 0.50,
     "p_close": 0.45, "price_at_decision": 2.00},
    {"p_model": 0.70, "result": "win",  "p_market_at_decision": 0.65,
     "p_close": 0.70, "price_at_decision": 1.50},
    {"p_model": 0.40, "result": "loss", "p_market_at_decision": 0.42,
     "p_close": 0.38, "price_at_decision": 2.50},
    {"p_model": 0.50, "result": "win",  "p_market_at_decision": 0.50,
     "p_close": 0.50, "price_at_decision": 2.05},
    {"p_model": 0.80, "result": "win",  "p_market_at_decision": 0.75,
     "p_close": 0.82, "price_at_decision": 1.30},
    {"p_model": 0.30, "result": "loss", "p_market_at_decision": 0.33,
     "p_close": 0.28, "price_at_decision": 3.20},
    {"p_model": 0.65, "result": "loss", "p_market_at_decision": 0.60,
     "p_close": 0.55, "price_at_decision": 1.65},
    {"p_model": 0.45, "result": "win",  "p_market_at_decision": 0.48,
     "p_close": 0.52, "price_at_decision": 2.20},
    {"p_model": 0.52, "result": "win",  "p_market_at_decision": 0.50,
     "p_close": 0.54, "price_at_decision": 1.95},
]

#: 손 계산 — (p − y)²
#   0.16 · 0.3025 · 0.09 · 0.16 · 0.25 · 0.04 · 0.09 · 0.4225 · 0.3025 · 0.2304
_SQ = [(0.60 - 1) ** 2, (0.55 - 0) ** 2, (0.70 - 1) ** 2, (0.40 - 0) ** 2,
       (0.50 - 1) ** 2, (0.80 - 1) ** 2, (0.30 - 0) ** 2, (0.65 - 0) ** 2,
       (0.45 - 1) ** 2, (0.52 - 1) ** 2]


def test_metrics_on_known_fixture():
    """🔴 손으로 계산한 10건과 일치해야 한다."""
    want_brier = round(sum(_SQ) / 10, 4)
    assert M.brier(FIX) == want_brier, f"{M.brier(FIX)} != {want_brier}"

    # 로그손실도 손으로: -(y·ln p + (1-y)·ln(1-p))
    want_ll = round(sum(
        -(1 * math.log(r["p_model"]) if r["result"] == "win"
          else math.log(1 - r["p_model"])) for r in FIX) / 10, 4)
    assert M.log_loss(FIX) == want_ll, f"{M.log_loss(FIX)} != {want_ll}"

    # 적중 6/10
    assert sum(1 for r in FIX if r["result"] == "win") == 6
    # 🔴 0.25 = "항상 50%로 찍기". 이 픽스처는 그것보다 나아야 정상이다.
    assert want_brier < 0.25


def test_clv_sign_convention():
    """🔴 **우리 쪽으로 종가가 움직이면 +.**"""
    assert M.clv({"p_market_at_decision": 0.55, "p_close": 0.60}) == 0.05
    assert M.clv({"p_market_at_decision": 0.50, "p_close": 0.45}) == -0.05
    assert M.clv({"p_market_at_decision": 0.50, "p_close": 0.50}) == 0.0
    # 모르면 None — 0 으로 세면 CLV 평균이 좋아 보인다
    assert M.clv({"p_market_at_decision": None, "p_close": 0.6}) is None
    assert M.clv({"p_market_at_decision": 0.6, "p_close": None}) is None


def test_roi_는_단위_스테이크다():
    """⚠️ 금액이 아니다(R6). 이기면 배당−1 · 지면 −1 · push·void 는 0."""
    assert M.roi_unit({"result": "win", "price_at_decision": 1.80}) == 0.8
    assert M.roi_unit({"result": "loss", "price_at_decision": 1.80}) == -1.0
    # 🔴 [LE1-ROI 2026-09-22] push·void 도 **배당을 요구한다.** 종전 이 줄은
    #    `{"result": "push"} == 0.0` 이었다 — 가격 없는 결정을 분모에 넣어
    #    평균을 0 쪽으로 끌었다. 같은 뿌리의 결함이 ROI 를 −0.4656 으로
    #    보이게 만들었다(실측 2026-09-22).
    assert M.roi_unit({"result": "push", "price_at_decision": 1.90}) == 0.0
    assert M.roi_unit({"result": "void", "price_at_decision": 1.90}) == 0.0
    assert M.roi_unit({"result": "push"}) is None
    assert M.roi_unit({"result": None}) is None
    # 배당이 1.0 이하면 계산하지 않는다 — 그런 배당은 없다
    assert M.roi_unit({"result": "win", "price_at_decision": 1.0}) is None


def test_표본_부족이면_숫자를_내지_않는다():
    """🔴 지시문 §1 — 30건 미만에서 문턱을 확정하지 않는다."""
    s = M.summarize(FIX)          # 10건
    assert s["insufficient"] is True
    assert "brier" not in s, "표본이 얇은데 숫자를 냈다"
    assert s["n"] == 10 and s["min_samples"] >= 30

    big = FIX * 4                  # 40건
    s2 = M.summarize(big)
    assert s2["insufficient"] is False and s2["brier"] is not None


def test_push_와_void_는_분모에서_빠진다():
    """⚠️ 무승부를 손실로 세면 적중률과 ROI 가 동시에 거짓이 된다."""
    rows = FIX + [{"p_model": 0.5, "result": "push"},
                  {"p_model": 0.5, "result": "void"}]
    assert M.brier(rows) == M.brier(FIX)
    assert M.dropped(rows) == 2


def test_확률이_아니면_버린다():
    """🔴 클립하지 않는다 — 클립은 결함을 숨기고 Brier 를 좋아 보이게 한다."""
    rows = FIX + [{"p_model": 1.4, "result": "win"},
                  {"p_model": -0.2, "result": "loss"}]
    assert M.brier(rows) == M.brier(FIX)
    assert M.dropped(rows) == 2


def test_보정_곡선이_빈_분위를_지우지_않는다():
    """⚠️ 빈 분위가 빠지면 '단조'가 거짓으로 보인다."""
    c = M.calibration_curve(FIX, bins=10)
    assert len(c) == 10
    assert [x["bin"] for x in c] == list(range(1, 11))
    assert any(x["n"] == 0 for x in c)


def test_단조_판정은_얇은_분위를_무시한다():
    """⚠️ 2건짜리 분위로 '깨졌다'고 말하면 오탐이다."""
    curve = [{"n": 100, "freq": 0.4}, {"n": 2, "freq": 0.1},
             {"n": 100, "freq": 0.6}]
    assert M.is_monotone(curve, min_n=30) is True
    assert M.is_monotone(curve, min_n=1) is False
    # 판단할 분위가 2개 미만이면 None — 모른다고 말한다
    assert M.is_monotone([{"n": 100, "freq": 0.4}], min_n=30) is None


def test_엔진을_섞지_않는다():
    """🔴 지시문 LE-6-1 — 엔진별 CLV 가 따로 보여야 어느 것이 도는지 안다."""
    rows = ([dict(r, engine="a") for r in FIX * 4]
            + [dict(r, engine="b") for r in FIX * 4])
    g = M.group_by(rows, ("engine",))
    assert set(g) == {("a",), ("b",)}
    assert g[("a",)]["n"] == 40 and g[("b",)]["n"] == 40


def test_close_rule_matches_clv_snap():
    """🔴 **종가 규칙을 두 벌로 만들지 않았다.**

    원본은 `pick_ledger._CLV_SNAP` 이고 `prices.CLOSE_WHERE` 가 같은 문장을
    쓴다. 한쪽이 바뀌면 여기서 깨진다(사본 금지).
    """
    import re

    from app.engine.pick_ledger import _CLV_SNAP
    from app.learning.prices import CLOSE_WHERE

    def norm(s):
        return re.sub(r"\s+", " ", s).strip()

    assert norm(CLOSE_WHERE) in norm(_CLV_SNAP), (
        f"종가 조건이 갈라졌다:\n  prices: {norm(CLOSE_WHERE)}\n"
        f"  _CLV_SNAP: {norm(_CLV_SNAP)}")


def test_devig_을_새로_짓지_않았다():
    """🔴 이 저장소에 devig 구현이 이미 넷 있다 — 다섯째를 만들지 않는다."""
    import inspect

    from app.learning import prices as P

    src = inspect.getsource(P.devig)
    assert "odds_math" in src, "기존 devig 을 쓰지 않는다"
    # 한쪽만 있으면 확률이라고 부르지 않는다
    assert P.devig({"home": 1.8}) == {}
    assert P.devig({}) == {}
    # 2-way 는 합이 1
    d = P.devig({"home": 1.8, "away": 2.1})
    assert abs(sum(d.values()) - 1.0) < 0.001


def test_우리쪽_확률로_변환한다():
    """🔴 `pick_ledger` 의 확률은 **홈 기준**이다. 원정 픽에 그대로 쓰면
    CLV 의 부호가 뒤집힌다(CLV-3 이 겪은 실패)."""
    from app.learning.decisions import _our_side_p

    assert _our_side_p(0.62, "home") == 0.62
    assert _our_side_p(0.62, "away") == 0.38
    assert _our_side_p(None, "home") is None
    assert _our_side_p(0.62, None) is None
    assert _our_side_p(0.62, "draw") is None


def test_스키마에_확신등급_칸이_없다():
    """🔴 지시문 §1 — 보정 곡선이 단조가 될 때까지 확신 등급을 되살리지 않는다.

    실측 2026-09-22: 상 68.1%(n=47) · **하 57.7%(n=359)** · 중 53.2%(n=945).
    """
    import pathlib

    sql = (pathlib.Path(__file__).resolve().parents[2]
           / "db" / "schema.sql").read_text(encoding="utf-8")
    block = sql[sql.index("CREATE TABLE IF NOT EXISTS decision_ledger"):]
    block = block[: block.index(");")]
    for banned in ("confidence", "확신"):
        assert banned not in block, f"decision_ledger 에 {banned} 칸이 생겼다"


def test_켈리는_기록_전용이다():
    """🔴 절대 규칙 R6 — 금액·비중을 제안하지 않는다."""
    from app.learning import get as cfg

    assert cfg("learning.kelly.record_only") is True


def test_사용자_사이트_도메인은_기본값이_없다():
    """🔴 사용자 답 2026-09-22 — 접속은 사용자가 따로 지시할 때만.

    ⚠️ 도메인에 **기본값을 두면** 다음 세션이 그것을 긁으러 나간다.
    """
    from app.learning import get as cfg

    assert cfg("learning.slow_book.user_site_domain") is None
    assert cfg("learning.slow_book.user_site_book") == "user_site"


def test_상수의_원본이_learning_yaml_하나다():
    """🔴 사본 금지 — `rules.yaml` 에 같은 블록을 두지 않았다."""
    from app.engine import rules as R
    from app.learning import CONFIG_PATH, get as cfg

    assert CONFIG_PATH.name == "learning.yaml"
    assert R.get("learning") is None, (
        "config/rules.yaml 에 learning 블록이 생겼다 — 두 벌은 어긋난다")
    assert cfg("learning.min_samples") == 30


# ── [LE1-ROI] 내가 방금 만든 거짓 숫자 ────────────────────────────────

def test_배당이_없으면_ROI_를_세지_않는다():
    """🔴 **첫 표가 거짓 숫자를 냈다.** 실측 2026-09-22 (소급 적재 378행):

    ```
    result  행수   배당 있는 행
    win      208       69        ← 139건이 ROI 에서 빠졌다
    loss     158       42        ← 그런데 158건 **전부** −1 로 세어졌다
    → ROI −0.4656 (n=229)  = 승리 69 + 패배 158 + void 2
    ```

    승리는 배당이 없으면 버리고 패배는 배당 없이도 −1 로 셌다. 분모가
    승·패에서 다르면 ROI 는 **반드시 음수로 치우친다.** 숫자가 나빠 보이는
    쪽으로 틀렸다는 게 더 나쁘다 — "엔진이 안 된다"는 결론을 만든다.
    """
    from app.learning import metrics as M

    # 배당이 없으면 승·패 **둘 다** None 이어야 한다
    assert M.roi_unit({"result": "loss"}) is None, "배당 없는 패배가 -1 로 샜다"
    assert M.roi_unit({"result": "loss", "price_at_decision": None}) is None
    assert M.roi_unit({"result": "win"}) is None
    # 배당이 있으면 종전 그대로
    assert M.roi_unit({"result": "win", "price_at_decision": 1.8}) == 0.8
    assert M.roi_unit({"result": "loss", "price_at_decision": 1.8}) == -1.0


def test_ROI_분모가_승패에서_같다():
    """🔴 **반대 위험까지 잰다** — 한쪽만 고치면 이번엔 양수로 치우친다."""
    from app.learning import metrics as M

    rows = ([{"result": "win", "price_at_decision": 2.0}] * 3
            + [{"result": "win"}] * 5              # 배당 없음
            + [{"result": "loss", "price_at_decision": 2.0}] * 3
            + [{"result": "loss"}] * 5)            # 배당 없음
    vals = [M.roi_unit(r) for r in rows]
    counted = [v for v in vals if v is not None]
    assert len(counted) == 6, f"배당 있는 6건만 세야 한다: {counted}"
    assert sum(counted) == 0.0, "3승 3패 · 배당 2.0 이면 정확히 0 이다"


def test_push_와_void_도_배당을_요구한다():
    """⚠️ 가격이 없던 결정은 ROI 분모에 **아예 들어가지 않는다.**
    0 으로 세면 n 만 부풀고 평균이 0 쪽으로 끌린다."""
    from app.learning import metrics as M

    assert M.roi_unit({"result": "push"}) is None
    assert M.roi_unit({"result": "push", "price_at_decision": 1.9}) == 0.0
    assert M.roi_unit({"result": "void", "price_at_decision": 1.9}) == 0.0
