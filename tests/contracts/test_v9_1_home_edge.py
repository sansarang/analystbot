"""🔴🔴 **① 홈 이점은 그 리그 결과로 실측한다**(사용자 지시 2026-10-11).

> 리그 홈 이점은 그 리그 경기 결과로 실측한다(자동 등록 리그 포함, fotmob 결과).
> 이번 시즌 30경기 미만이면 직전 시즌까지.
> **"실측 없음 → 1.0" 경로 삭제.** lambda_const 자리 변수(S03)와 λ에 쓴 값이 다르면
> **계약 실패**.
"""
from __future__ import annotations

import inspect


def test_v9_실측_없음이면_1_0_으로_가지_않는다():
    """🔴 **조용한 1.0 금지** — 못 쟀으면 `None` 과 사유다(#3).

    ⚠️ 돌연변이: `home_mul_default` 로 돌아가면 빨개진다.
    """
    from app.core import probmodel as _pm
    said = inspect.getsource(_pm.home_mul)
    code = "\n".join(x for x in said.splitlines()
                     if not x.strip().startswith("#"))
    assert "home_mul_default" not in code, (
        "🔴 실측이 없을 때 **1.0** 으로 간다 — 그 경로는 삭제다")
    # 🔴 못 쟀으면 **`None`** 을 준다(호출부가 크게 실패한다)
    class _Facts:
        standings = {}
        match_format = ""
    got, why = _pm.home_mul(_Facts(), None, ref=None)
    assert got is None, f"🔴 못 쟀는데 수를 냈다 — {got} · {why}"
    assert "실측" in why


def test_v9_MLS_홈_이점이_표에_있다():
    """🔴 자동 등록 리그(MLS)도 **표에 실측이 있다**(fotmob 결과 414경기)."""
    from app import rules
    box = dict(rules.goal_baseline("league:MLS") or {})
    assert box.get("home_share"), f"🔴 MLS 홈 몫이 없다 — {box}"
    assert int(box.get("n") or 0) >= 30, box
    assert "fotmob" in str(box.get("source") or ""), box


def test_v9_S03_변수_값과_λ_값이_같다():
    """🔴🔴 **계약** — `lambda_const` 자리 변수(S03)와 λ 에 쓴 값이 **같아야** 한다.

    ⚠️ 종전에는 S03 이 *"홈 **승률** 표가 없다"* 라고 적고 λ 는 **득점 실측**을 썼다 —
       한 카드가 두 수를 말했다. 🔴 두 자리가 **같은 함수**를 보게 한다.
    """
    from app.core import probmodel as _pm
    from app.core.stages import s5_verify as _s5
    said = inspect.getsource(_s5)
    # 🔴 S03 글을 만드는 자리가 **득점 실측**(`goal_baseline`)을 읽는다
    assert "goal_baseline" in said, "🔴 S03 이 λ 와 다른 표를 본다"
    # 🔴 λ 쪽도 같은 함수다
    assert "goal_baseline" in inspect.getsource(_pm.home_mul)


def test_v9_fotmob_리그_결과_파서가_선다():
    """🔴 그 실측의 재료 — `fotmob.league_results`(끝난 경기만·점수를 읽은 줄만)."""
    from app.collect import fotmob as _fm
    j = {"props": {"pageProps": {"fixtures": {"allMatches": [
        {"home": {"name": "A"}, "away": {"name": "B"},
         "status": {"finished": True, "scoreStr": "2 - 0", "utcTime": "x"}},
        {"home": {"name": "C"}, "away": {"name": "D"},
         "status": {"finished": False, "scoreStr": "", "utcTime": "y"}},
        {"home": {"name": "E"}, "away": {"name": "F"},
         "status": {"finished": True, "scoreStr": "", "utcTime": "z"}}]}}}}
    got = _fm.league_results(j)
    assert len(got) == 1, got          # 🔴 안 끝난 줄·점수 못 읽은 줄은 **버린다**
    assert got[0]["gh"] == 2 and got[0]["ga"] == 0


def test_v9_축1이_창과_산술을_적는다():
    """🔴🔴 **② 축1 감사**(사용자 지시 2026-10-11) — 축1 사유가 **경기 수·원본
    득실·운 할인**을 적는다.

    ⚠️ 실사고: 카드의 **폼 블록은 최근 5경기**, 축1 은 **최근 10경기**였다 —
       두 수가 **다른 창**인데 카드가 그 말을 안 했다(사용자가 그래서 물었다).
    """
    import inspect

    from app.core import matchup as _mu
    said = inspect.getsource(_mu.axis1)
    for want in ("최근", "운 할인", "원본 득실"):
        assert want in said, f"🔴 축1 이 `{want}` 를 안 적는다"


def test_v9_원본_득실이_뒤집히면_경고_줄이_붙는다():
    """🔴 고정물 — *"원본 득실이 더 나쁜 팀이 축1에서 크게 앞서면 경고 줄"*.

    🔴 실물로 센다 — 원본은 home 이 좋은데 보정 지수는 away 가 앞서게 만든다.
    """
    from app.core import form as _form
    from app.core import matchup as _mu

    def _mk(gf, ga, n, idx):
        one = _form.TeamForm(team="t", n=n, gf=gf, ga=ga,
                             adj_gf=gf, adj_ga=ga)
        # 🔴 운 할인으로 **지수만** 낮춘다(원본 득실은 그대로다)
        one.gf_after_luck = idx * n + ga
        return one

    box = {"form": {"home": _mk(20, 10, 10, -0.2),   # 원본 +1.0 · 지수 -0.2
                    "away": _mk(10, 12, 10, 0.4)}}   # 원본 -0.2 · 지수 +0.4
    got = _mu.axis1(box, None, r={})
    assert "⚠️" in got.why and "원본 득실" in got.why, got.why
    assert "away" in got.why


def test_v9_꺼진_무기가_상수가_아니다():
    """🔴🔴 **③ 축2 감사**(사용자 지시 2026-10-11) — 꺼진 무기는 **비중**으로 센다.

    ⚠️ 실사고: `off_weapons` 가 **상수**(`forward`·`box_entry`·`direct`)를 돌려줘
       LAFC·밴쿠버가 **둘 다 3/3**, 김천–안양도 3/3 이었다 — 양 팀이 늘 같으면
       축2 의 차는 **언제나 0** 이다(실제로 그랬다).
    🔴 고정물 — **결장 0명 팀은 꺼진 무기 0.**
    """
    from app.core import style as _style

    class _Read:
        def __init__(self, state, table):
            self.key_state, self.att_table = state, table

    table = {"A": 10.0, "B": 5.0, "C": 5.0}       # 팀 합 20
    # 🔴 빠진 선수가 **없다** → 꺼진 무기 0
    assert _style.off_weapons(_Read({"A": "선발"}, table), None) == []
    # 🔴 비중 50% → 공격 축 셋
    big = _style.off_weapons(_Read({"A": "명단 제외"}, table), None)
    assert set(big) == {"forward", "box_entry", "direct"}, big
    # 🔴 비중 25% → **하나만**(상수가 아니다)
    mid = _style.off_weapons(_Read({"B": "벤치"}, table), None)
    assert mid == ["forward"], mid
    # 🔴 표가 비면 **끄지 않는다**(없는 약화를 지어내지 않는다)
    assert _style.off_weapons(_Read({"A": "명단 제외"}, {}), None) == []


def test_v9_손흥민이_선발인데_수비_위주면_버린다():
    """🔴🔴 **④ 전략 판정**(사용자 지시 2026-10-11) — 포메이션 글자로 공격/수비를
    판정하지 않는다. **선수별 주 역할·시즌 공격 기여**로 센다.

    🔴 고정물 — *"손흥민·부앙가가 선발인 LAFC 가 `수비 위주` 로 나오면 실패"*.
    ⚠️ 돌연변이: 그 검사를 지우면 포메이션만 보고 다시 `수비 위주` 가 나온다.
    """
    from app.core.stages import s2d_strategy as _s2d

    class _Read:
        def __init__(self, on):
            self.key_state = on
            self.da = -10.0          # 🔴 ΔA 는 **통과**하는 값이다(그래서 샜다)
            self.back_now = self.back_usual = 4
            self.changed = 3

        def ids(self):
            return ["L1", "L2", "L5"]

    class _Line:
        side, strategy = "home", "수비 위주"
        fact_refs = ["L1", "L2"]

    on = {"Heung-Min Son": "선발", "Denis Bouanga": "선발"}
    bad = _s2d.check([_Line()], {"home": _Read(on)})
    assert any("핵심 공격 선수" in x for x in bad), bad
    # 🔴 핵심 공격 선수가 **벤치/제외**면 그 말을 하지 않는다
    off = {"Heung-Min Son": "명단 제외", "Denis Bouanga": "벤치"}
    assert not [x for x in _s2d.check([_Line()], {"home": _Read(off)})
                if "핵심 공격 선수" in x]
