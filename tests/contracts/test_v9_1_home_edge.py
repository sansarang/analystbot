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


def test_v9_구조_결장은_기사_수와_무관하게_hard다():
    """🔴🔴 **⑤**(사용자 지시 2026-10-11) — fotmob **결장 명단(구조 사실)** 에 있는
    결장은 **기사 출처 수와 상관없이 hard·근거 가능**.

    ⚠️ 실사고(LAFC): 뮐러 결장이 명단에 있는데도 기사가 1곳이라
       `soft · 🔴 근거 불가(맥락)` 로 내려갔다 — 구조 사실을 기사 수로 깎았다.
    """
    import inspect

    from app.core.stages import s5_verify as _s5
    said = inspect.getsource(_s5)
    assert "_in_missing" in said, "🔴 구조 결장 명단을 안 본다"
    i = said.index("def _in_missing")
    assert "missing" in said[i:i + 500]
    # 🔴 **그 자리에서 level 2·usable** 로 올린다
    j = said.index("구조 결장 명단에 있다")
    win = said[max(0, j - 400):j]
    assert "level, usable = 2, True" in win, win[-200:]


def test_v9_구조_결장_대조가_이름_규칙을_지킨다():
    """🔴 이름 대조는 `_in` 하나다 — 한 낱말 이름은 **성으로만** 맞춘다."""
    from app.core.stages import s5_verify as _s5

    class _M:
        def __init__(self, nm):
            self.name = nm

    class _F:
        missing = {"team:000001": [_M("Thomas Müller"), _M("Rafael")]}

    assert _s5._in_missing("Thomas Müller", "team:000001", _F()) is True
    assert _s5._in_missing("Müller", "team:000001", _F()) is True
    # 🔴 `Rafael`(한 낱말)이 `Rafael Tolói` 같은 **다른 사람**을 끌어오지 않는다
    assert _s5._in_missing("Rafael Tolói", "team:000001", _F()) is False


def test_v9_자동_등록_리그도_자체_Elo_표에_있다():
    """🔴🔴 **⑥**(사용자 지시 2026-10-11) — 자동 등록 리그는 fotmob 결과로 자체
    Elo 를 굴린다(V1 검증용).

    ⚠️ 실사고(LAFC): **MLS 가 그 표에 없어서** 카드의 기준 열이 통째로 비었다
       (`기준 없음 — Elo 를 못 받았다`) → 축1 의 상대 전력 보정도 **안 돌았다**.
    🔴 id·slug 는 받아서 확인한 값이다(`/leagues/130/matches/mls` · 414경기).
    """
    from app.collect import leagueelo as _le
    box = dict((_le.fotmob_table().get("competitions") or {}))
    assert "MLS" in box, f"🔴 MLS 가 fotmob Elo 표에 없다 — {sorted(box)}"
    said = dict(box["MLS"])
    assert int(said.get("id") or 0) == 130 and said.get("slug") == "mls", said
    # 🔴 K리그1·J1 도 그대로 있다(지우지 않았다)
    assert {"KL1", "J1"} <= set(box)


def test_v9_작성_입력을_상위_근거로_줄인다():
    """🔴🔴 **⑦**(사용자 지시 2026-10-11) — 작성 입력을 **변수 상위 8**로 줄인다.

    ⚠️ 실사고: LAFC·스포팅KC·상파울루가 **전부** `llm_truncated` 로 템플릿에 떨어졌다.
    🔴 **지우는 것이 아니라 줄인다** — 몇 개를 뺐는지 `empty` 에 적는다(#3).
    """
    from app.core import saybundle as _sb

    got = _sb.Bundle()
    for i in range(20):
        got.items[f"L{i}"] = object()
    for key in ("P1", "M0", "H1"):
        got.items[key] = object()
    _sb.trim(got)
    rows = [k for k in got.items if k.startswith("L")]
    assert len(rows) == _sb.TOP_VARS, rows
    # 🔴 확률·상성·가설은 **늘 남는다**
    assert {"P1", "M0", "H1"} <= set(got.items)
    assert any("줄이기" in x for x in got.empty), got.empty


def test_v9_잘리면_템플릿이_아니라_축약판이다():
    """🔴 *"잘리면 템플릿 대신 **'잘림 — 핵심 3줄만'** 축약판"*(⑦).

    ⚠️ 돌연변이: 잘림을 템플릿으로 되돌리면 빨개진다.
    """
    import inspect

    from app.core.stages import s9_say as _say
    said = inspect.getsource(_say.run)
    assert "잘림 — 핵심 3줄만" in said, "🔴 축약판이 없다"
    assert "last_llm_reason" in said, "🔴 **왜 실패했는지**를 안 본다"
    i = said.index('"audit": "잘림 — 핵심 3줄만"')
    assert "key_points" in said[i:i + 300], "🔴 핵심 3줄로 안 줄인다"
    assert "[:3]" in said[i:i + 300], said[i:i + 200]
    # 🔴 그 사유 칸이 `RunState` 에 있다
    from app.core.state import RunState
    assert hasattr(RunState(), "last_llm_reason")
