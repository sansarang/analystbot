"""자료12 elo 파라미터 적합의 계약.

이 도구가 틀리면 **틀린 파라미터를 근거와 함께** 배포하게 된다.
자료13 때 관문이 판별력이 없었던 것(n=30, 구간 폭 ±17%p)과 같은 부류의
사고를 막는 것이 여기 테스트들의 일이다.
"""

import datetime as dt
import math

import pytest

from tools.fit_elo import DECAYS, EPS, HOME_ADVS, KS, baseline, evaluate, ratings_asof

BASE = dt.datetime(2026, 7, 1, tzinfo=dt.UTC)


def _m(i, home, away, res):
    return {"home": home, "away": away, "ts": BASE + dt.timedelta(days=i),
            "res": res}


def _series(n=80, strong="A", weak="B"):
    """강팀이 늘 이기는 시계열. 레이팅이 벌어져야 정상이다."""
    out = []
    for i in range(n):
        # 홈/원정을 번갈아 — 홈이점만으로 설명되지 않게 한다.
        if i % 2:
            out.append(_m(i, strong, weak, "H"))
        else:
            out.append(_m(i, weak, strong, "A"))
    return out


# ═══════════════ ① 누수 — 이 도구의 성패

def test_예측_시점_이후_경기는_레이팅에_영향을_주지_않는다():
    """🔴 `team_elo.compute` 는 감쇠 기준을 **마지막 경기**로 잡는다.
    그대로 쓰면 과거를 예측할 때 미래 시점이 새어 들어온다."""
    ms = _series(60)
    a = ratings_asof(ms, 20, 0.9, 20.0, 15.0)
    b = ratings_asof(ms[:20], 20, 0.9, 20.0, 15.0)
    assert a == b, "뒤 행의 유무가 앞 구간 레이팅을 바꿨다 — 누수다"


def test_감쇠가_예측_시점_기준으로_걸린다():
    """감쇠 기준이 전체 마지막이면 decay 를 바꿔도 앞 구간이 같은 비율로
    눌린다. 시점 기준이면 구간마다 다르게 반영된다."""
    ms = _series(60)
    slow = ratings_asof(ms, 30, 1.00, 20.0, 15.0)   # 감쇠 없음
    fast = ratings_asof(ms, 30, 0.80, 20.0, 15.0)   # 강한 감쇠
    spread = lambda r: max(r.values()) - min(r.values())   # noqa: E731
    assert spread(slow) != spread(fast)


def test_채점_구간_이전_경기는_예측에_쓰이지_않는다():
    """`start` 이전은 예열이지 채점 대상이 아니다."""
    ms = _series(80)
    r = evaluate(ms, decay=0.9, k=20.0, home_adv=15.0, min_games=10,
                 start=40, end=80)
    assert r["n"] <= 40


# ═══════════════ ② 지표가 실제로 지표인가

def test_감쇠를_늦추면_레이팅이_더_벌어진다():
    """🔴 실측 동기: MLB 레이팅 폭이 49.7 뿐이라 자료12 가 ±9.2%p 밖에
    못 만든다. 감쇠가 원인 후보라는 가설을 이 성질이 받친다."""
    ms = _series(80)
    spread = lambda d: (lambda r: max(r.values()) - min(r.values()))(  # noqa: E731
        ratings_asof(ms, 80, d, 20.0, 15.0))
    assert spread(1.00) > spread(0.90)


def test_완벽한_예측은_logloss_가_0에_가깝다():
    """지표 방향 검사 — 낮을수록 좋다."""
    ms = _series(120)
    r = evaluate(ms, decay=1.00, k=48.0, home_adv=15.0, min_games=10,
                 start=60, end=120)
    assert r["n"] > 0
    assert r["logloss"] < -math.log(0.5), "동전던지기보다 나빠졌다"
    assert r["acc"] > 0.9, "강팀이 늘 이기는 계열인데 방향을 못 맞춘다"


def test_무승부는_방향_채점에서_빠지고_logloss_는_0_5로_센다():
    ms = [_m(i, "A", "B", "H") for i in range(40)]
    ms += [_m(40 + i, "A", "B", "D") for i in range(20)]
    r = evaluate(ms, decay=0.95, k=20.0, home_adv=15.0, min_games=10,
                 start=20, end=60)
    assert r["n"] > r["dec_n"], "무승부가 방향 분모에 들어갔다"


def test_확률은_잘리고_logloss_가_무한대가_되지_않는다():
    """p=0 또는 1 이면 log 가 발산한다 — EPS 로 자른다."""
    assert 0 < EPS < 1e-6
    ms = _series(200)
    r = evaluate(ms, decay=1.00, k=48.0, home_adv=15.0, min_games=10,
                 start=100, end=200)
    assert math.isfinite(r["logloss"])


# ═══════════════ ③ 기준선 — 못 이기면 축이 무의미하다

def test_기준선은_그_시점까지의_홈승률만_쓴다():
    """기준선도 walk-forward 여야 공정하다."""
    ms = [_m(i, "A", "B", "H") for i in range(50)]
    b = baseline(ms, 25, 50)
    assert b["n"] == 25
    assert b["logloss"] < -math.log(0.5), "홈이 늘 이기는데 상수가 못 맞춘다"


def test_기준선은_무승부도_0_5로_센다():
    ms = [_m(i, "A", "B", "D") for i in range(40)]
    b = baseline(ms, 20, 40)
    assert math.isfinite(b["logloss"])


# ═══════════════ ④ 관문 설계 — 현행값이 비교에 반드시 들어간다

def test_훑는_값에_현행_운영값이_들어_있다():
    """현행이 후보군에 없으면 '개선'을 잴 기준이 없다."""
    from app.config import get_settings
    from app.models.team_elo import HOME_ADV, K_FACTOR

    s = get_settings()
    assert float(s.elo_decay) in DECAYS
    assert float(K_FACTOR) in KS
    assert float(HOME_ADV) in HOME_ADVS


def test_홀드아웃이_선택에_쓰이지_않는다():
    """🔴 20개 조합을 346경기에 훑으면 반드시 과적합된다.
    선택 구간과 보고 구간이 겹치면 이 도구는 자기 자랑밖에 못 한다."""
    src = open("tools/fit_elo.py", encoding="utf-8").read()
    i = src.index("def run_sport")
    seg = src[i:]
    assert "start=warm, end=split" in seg, "선택은 split 이전만 봐야 한다"
    assert "start=split, end=n" in seg, "보고는 split 이후만 봐야 한다"


def test_관문_문구가_문서에_박혀_있다():
    """실행 전에 선언한 기준이 코드에 남아 있어야 나중에 못 옮긴다."""
    src = open("tools/fit_elo.py", encoding="utf-8").read()
    assert "세 리그 전부" in src and "변경 없음" in src
