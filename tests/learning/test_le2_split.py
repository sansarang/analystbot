"""[LE-2] 누설 방지·시간순 검증 — **엔진보다 먼저 잠근다.**

지시문 §1:
> "학습·검증은 시간순(walk-forward)만. 무작위 분할·미래 정보 누설(종가·결과·
>  경기 후 기사)이 학습 입력에 들어가면 **그 결과는 무효다.** 누설 방지는
>  계약 테스트로 잠근다."

🔴 **검사가 아니라 구조로 막았다.** 피처는 `(value, available_at)` 쌍으로만
   만들어진다 — `available_at` 없이는 생성자가 거부한다. 검사 함수에 의존하면
   그것을 안 부르는 경로가 생긴다(이 저장소의 D48·D52·WIR-3 가 그 전례다).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.learning import baselines as B
from app.learning import split as S

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _rows(n=200, key="ts"):
    return [{key: T0 + timedelta(days=i), "league": "E0"} for i in range(n)]


# ── 누설 ────────────────────────────────────────────────────────────

def test_no_future_feature():
    """🔴 지시문 원문 계약 — 결정 시각 이후 피처가 하나라도 있으면 **실패**."""
    f_ok = S.Feature("elo", 1500, T0 - timedelta(days=1))
    f_bad = S.Feature("close_odds", 1.8, T0 + timedelta(hours=2))

    assert S.usable([f_ok], T0) == [f_ok]
    with pytest.raises(S.LeakError) as e:
        S.usable([f_ok, f_bad], T0)
    assert "close_odds" in str(e.value)


def test_available_at_없이는_피처를_만들_수_없다():
    """🔴 **구조로 막는다.** 검사를 안 부르는 경로가 생기지 않게."""
    with pytest.raises(S.LeakError):
        S.Feature("x", 1, None)
    with pytest.raises(S.LeakError):
        S.Feature("x", 1, "2026-01-01")      # 문자열도 안 된다


def test_같은_시각은_통과한다():
    """⚠️ 반대 위험 — 결정 **시점**에 이미 있던 값까지 버리면 굶는다."""
    f = S.Feature("lineup", "확정", T0)
    assert S.usable([f], T0) == [f]


def test_naive_datetime_도_막는다():
    """⚠️ tz 없는 값을 UTC 로 읽는다 — 섞여도 비교가 성립해야 한다."""
    naive = datetime(2026, 1, 2)             # tz 없음 = UTC 로 본다
    with pytest.raises(S.LeakError):
        S.usable([S.Feature("x", 1, naive)], T0)


#: 🔴 무작위 분할의 표지. 지시문 §1: "무작위 분할을 쓰지 않는다."
_RANDOM_NAMES = ("train_test_split", "KFold", "StratifiedKFold",
                 "ShuffleSplit", "shuffle", "sample", "seed")
_RANDOM_KWARGS = ("shuffle", "random_state")


def test_random_split_forbidden():
    """🔴 지시문 원문 계약 — **분할기 외 경로로 학습하면 실패.**

    ⚠️ **코드 본문만 본다.** 원문을 grep 하면 "무작위 분할을 쓰지 않는다"는
       **주석 자체**가 걸린다. 이 저장소가 그 거짓 실패를 겪은 것이 지금
       다섯 번째다(D46). `ast` 로 호출 이름과 키워드 인자만 꺼내 본다.
    """
    import ast
    import pathlib

    hits = []
    for f in sorted(pathlib.Path("app/learning").rglob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = (fn.id if isinstance(fn, ast.Name)
                    else getattr(fn, "attr", ""))
            if name in _RANDOM_NAMES:
                hits.append(f"{f.name}:{name}()")
            for kw in node.keywords or []:
                if kw.arg in _RANDOM_KWARGS:
                    hits.append(f"{f.name}:{kw.arg}=")
    assert hits == [], f"무작위 분할을 쓴다: {hits}"


def test_이_계약이_실제로_잡는가():
    """🔴 **계약이 아무것도 안 잡으면 거짓 통과다.** 일부러 넣어 확인한다."""
    import ast

    bad = ast.parse("from sklearn.model_selection import train_test_split\n"
                    "a, b = train_test_split(rows, shuffle=True)\n")
    found = []
    for node in ast.walk(bad):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            if name in _RANDOM_NAMES:
                found.append(name)
            for kw in node.keywords or []:
                if kw.arg in _RANDOM_KWARGS:
                    found.append(kw.arg)
    assert "train_test_split" in found and "shuffle" in found


# ── walk-forward ────────────────────────────────────────────────────

def test_창이_시간을_넘지_않는다():
    """🔴 학습 창이 검증 창보다 **항상 앞**이다."""
    rows = _rows()
    ws = S.walk_forward(rows, train_weeks=12, valid_weeks=1)
    assert ws, "창이 하나도 안 나왔다"
    for w in ws:
        assert w.train_start < w.train_end <= w.valid_end
        tr, va = w.split(rows)
        assert tr and va
        assert max(r["ts"] for r in tr) < min(r["ts"] for r in va), (
            "학습에 검증 이후 행이 들어갔다")


def test_학습과_검증이_겹치지_않는다():
    """⚠️ 경계가 배타여야 한 경기가 두 번 세어지지 않는다."""
    rows = _rows()
    for w in S.walk_forward(rows, train_weeks=12, valid_weeks=1):
        tr, va = w.split(rows)
        ids = {id(r) for r in tr} & {id(r) for r in va}
        assert not ids, "같은 행이 학습과 검증에 둘 다 있다"


def test_창이_앞으로만_간다():
    """🔴 walk-forward 다 — 뒤로 가면 미래로 배운다."""
    ws = S.walk_forward(_rows(), train_weeks=12, valid_weeks=1)
    ends = [w.train_end for w in ws]
    assert ends == sorted(ends) and len(set(ends)) == len(ends)


def test_표본이_없으면_빈_목록이다():
    assert S.walk_forward([]) == []
    assert S.walk_forward([{"ts": None}]) == []


def test_리그별로_독립이다():
    """🔴 지시문 LE-2-1 — 리그를 섞으면 한 리그의 가격 습관이 다른 리그로 샌다."""
    rows = _rows(20) + [{"ts": T0, "league": "SP1"}]
    g = S.by_league(rows)
    assert set(g) == {"E0", "SP1"}
    assert len(g["SP1"]) == 1


def test_보정은_검증창_앞에서_맞춘다():
    """🔴 지시문 LE-2-3 — 앞에서 맞추고 뒤에서 잰다. 같은 자리에서 하면
    그건 학습 성적이다."""
    rows = _rows(10)
    a, b = S.calibration_halves(rows)
    assert len(a) == 5 and len(b) == 5
    assert max(r["ts"] for r in a) < min(r["ts"] for r in b)
    # 두 건 미만이면 쪼갤 수 없다 — 억지로 쪼개지 않는다
    assert S.calibration_halves([rows[0]]) == ([rows[0]], [])


# ── 기준선 3개 ──────────────────────────────────────────────────────

def _brows(n=60, elo=True):
    out = []
    for i in range(n):
        r = {"p_market": 0.45 + 0.01 * (i % 20),
             "result": "win" if i % 2 else "loss",
             "p_market_at_decision": 0.55, "p_close": 0.56,
             "price_at_decision": 1.9}
        if elo:
            r["p_elo"] = 0.5
        out.append(r)
    return out


def test_기준선_셋을_같은_표본에서_잰다():
    """🔴 표본이 다르면 "누가 낫다"가 성립하지 않는다."""
    s = B.score(_brows())
    assert s["_names"] == ("market", "fifty", "elo")
    for n in s["_names"]:
        assert s[n]["n"] == s["_sample"], f"{n} 의 표본이 다르다"


def test_오십퍼센트_기준선은_정확히_0_25():
    """🔴 50% 고정의 Brier 는 **항상 0.25** 다. 이것이 척도의 영점이다."""
    s = B.score(_brows())
    assert s["fifty"]["brier"] == 0.25
    assert abs(s["fifty"]["log_loss"] - 0.6931) < 0.001


def test_Elo_가_없으면_미가용으로_빠진다():
    """⚠️ 0.5 로 채우면 (ii) 와 구별이 안 돼 기준선이 하나 준다."""
    s = B.score(_brows(elo=False))
    assert s["_names"] == ("market", "fifty")
    assert "elo" not in s
    assert B.elo_p({"p_elo": None}) is None
    assert B.elo_p({}) is None


def test_Elo_를_다시_짜지_않았다():
    """🔴 원본은 `app/models/soccer_elo` 다(사본 금지)."""
    import inspect

    src = inspect.getsource(B)
    for banned in ("K_FACTOR", "def replay", "elo_core"):
        assert banned not in src, f"Elo 계산을 여기서 한다: {banned}"


def test_기준선을_못_이기면_후보를_안_낸다():
    """🔴 지시문 LE-2-4 원문 — Brier·CLV **둘 다**에서 이겨야 한다."""
    base = B.score(_brows())
    mk = base["market"]
    # 같은 값이면 못 이긴 것이다
    assert B.beats_market(dict(mk), base) is False
    # 한쪽만 이기면 안 된다
    better_brier = dict(mk, brier=(mk["brier"] or 1) - 0.01)
    assert B.beats_market(better_brier, base) is False
    both = dict(mk, brier=(mk["brier"] or 1) - 0.01,
                clv_mean=(mk["clv_mean"] or 0) + 0.01)
    assert B.beats_market(both, base) is True
    # 못 재면 None — 모르면 후보를 내지 않는 쪽이 맞다
    assert B.beats_market({"insufficient": True}, base) is None
    assert B.beats_market(dict(mk, clv_mean=None), base) is None


# ── 보정 ────────────────────────────────────────────────────────────

def test_표본이_얇으면_보정하지_않는다():
    """⚠️ isotonic 은 얇은 표본에서 계단을 과적합한다 — 원값이 낫다."""
    from app.learning.calibrate import Calibrator

    c = Calibrator().fit([0.5] * 5, [1, 0, 1, 0, 1])
    assert c.fitted is False and "표본 부족" in (c.reason or "")
    assert c.apply([0.42]) == [0.42], "못 맞췄는데 값을 바꿨다"


def test_결과가_한쪽뿐이면_보정하지_않는다():
    """🔴 그러면 보정이 상수 함수가 된다 — 그건 보정이 아니다."""
    from app.learning.calibrate import Calibrator

    c = Calibrator().fit([0.3 + 0.01 * i for i in range(40)], [1] * 40)
    assert c.fitted is False and c.reason == "결과가 한쪽뿐"


def test_보정이_확률_범위를_지킨다():
    from app.learning.calibrate import Calibrator

    ps = [i / 100 for i in range(40, 80)]
    ys = [1 if p > 0.6 else 0 for p in ps]
    c = Calibrator().fit(ps, ys)
    assert c.fitted
    for q in c.apply([0.0, 0.5, 1.0]):
        assert 0.0 <= q <= 1.0
    assert c.apply([None]) == [None]
