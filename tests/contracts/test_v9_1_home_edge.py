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
         "status": {"finished": True, "scoreStr": "2 - 0", "utcTime": "2026-09-01T12:00:00Z"}},
        {"home": {"name": "C"}, "away": {"name": "D"},
         "status": {"finished": False, "scoreStr": "", "utcTime": "2026-09-08T12:00:00Z"}},
        {"home": {"name": "E"}, "away": {"name": "F"},
         "status": {"finished": True, "scoreStr": "", "utcTime": "2026-09-15T12:00:00Z"}}]}}}}
    # 🔴 `as_of` 필수(사용자 지시 2026-10-12 ⓐ · 누설 금지 L1) — 기준선 측정이
    #    **그날 끝난 경기**까지 먹으면 그 수로 그날 카드를 매긴다.
    #    ⚠️ 이 계약은 파서 모양만 보므로 **먼 미래**를 준다(전부 통과).
    #    🔴 고정물의 `utcTime` 도 **실물 꼴**로 고쳤다 — 시각을 못 읽는 줄은
    #       `before_as_of` 가 떨어뜨린다(언제인지 모르는 경기를 기준선에 넣지 않는다).
    from datetime import UTC as _UTC
    from datetime import datetime as _dt
    got = _fm.league_results(j, as_of=_dt(2030, 1, 1, tzinfo=_UTC))
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


def test_v9_꺼진_무기가_상수가_아니다() -> None:
    """🔴🔴 **지운 경로를 계약하던 시험이다** — 사용자 지시 2026-10-17.

    > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**

    ⚠️ 이 시험이 지키던 것(test_v9_꺼진_무기가_상수가_아니다)은 **상성 축 · λ(기대 득점) · 몬테카를로
       시뮬** 경로다. 그 경로의 결과가 **전부 버려지고 있었다** —
       `probmodel.run` 마지막 세 줄이 승무패를 `flat_prob`(1/3 균등 + 변수)로
       덮고 `lam`·`over`·`scores` 를 비웠기 때문이다.
    🔴 그래서 **지웠고**, 이 시험은 *"되살아나지 않는다"* 를 지키는 쪽으로
       바꾼다(지우면 되살아나도 아무도 안 본다).
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    def _code(rel: str) -> str:
        """🔴 D46 — 독스트링·주석을 뺀 **코드만** 본다."""
        t = _ast.parse((root / rel).read_text(encoding="utf-8"))
        for n in _ast.walk(t):
            if isinstance(n, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef,
                              _ast.ClassDef)) and _ast.get_docstring(n):
                n.body = n.body[1:]
        return _ast.unparse(t)

    #  ① 상성 단계가 **안 돈다**
    assert "_s2e.run(" not in _code("app/core/pipeline.py"), (
        "🔴 상성 단계가 되살아났다")
    from app.core.stages import s2e_matchup as _s2e
    assert not hasattr(_s2e, "run"), "🔴 `s2e_matchup.run`(상성)이 되살아났다"
    #  ② 확률 경로가 **시뮬을 안 부른다**
    said = _code("app/core/probmodel.py")
    assert "_sim.run(" not in said, "🔴 확률 경로가 몬테카를로를 다시 부른다"
    assert "flat_prob(varset" in said, "🔴 승무패가 `flat_prob` 에서 안 나온다"
    #  ③ λ 재료 함수들이 **없다**
    from app.core import probmodel as _pm
    for one in ("league_mean", "away_mul", "_share", "league_base"):
        assert not hasattr(_pm, one), f"🔴 `probmodel.{one}`(λ 재료)가 되살아났다"


# ⚠️ **걷은 시험** — `s2d_strategy.check`(LLM 전략 판정의 검열)가 §1 처분
#    (2026-10-12 셋째)으로 지워졌다: ⑩ 은 **늘 코드 판정**이라 버릴 LLM 줄이
#    없다(계약 X2).
#    걷은 시험: `test_v9_손흥민이_선발인데_수비_위주면_버린다`

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


def test_v9_자동_등록_리그도_자체_Elo_표에_있다() -> None:
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_v9_자동_등록_리그도_자체_Elo_표에_있다)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
    🔴 **확률은 이미 그 수를 안 보고 있었다** — 승무패는 `flat_prob`
       (1/3 균등 + 변수)이 내고 `probmodel.run` 은 `floor` 를 안 읽는다.
       쓰이던 곳은 카드의 **기준 열**과 **방향 판정**뿐이었고 둘 다 표시인데,
       `eloratings.net/World.tsv` 를 **매 실행** 받고 있었다.
    🔴 그래서 지웠고, 이 시험은 *"되살아나지 않는다"* 를 지킨다.
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    #  ① Elo 모듈 넷이 **없다**
    for rel in ("app/collect/elo.py", "app/collect/leagueelo.py",
                "app/core/domesticelo.py"):
        assert not (root / rel).exists(), f"🔴 `{rel}`(Elo)가 되살아났다"
    #  ② 기준 확률 함수가 **없다**
    from app.core import base as _b
    for one in ("we", "triple_of", "triple_from", "base_prob"):
        assert not hasattr(_b, one), f"🔴 `core.base.{one}`(Elo)가 되살아났다"
    from app.core.stages import s2b_base as _s2b
    for one in ("_base", "continental_elo", "league_level"):
        assert not hasattr(_s2b, one), f"🔴 `s2b_base.{one}`(Elo)가 되살아났다"
    #  ③ ② 는 **남아 있다** — 오늘 XI 가 평소보다 약/강한가는 Elo 를 안 쓴다
    for one in ("strength_of", "fill_values", "adjust"):
        assert hasattr(_b, one), f"🔴 `core.base.{one}`(선수 전력)이 같이 지워졌다"
    #  ④ 기준은 **늘 비어 있고 사유가 붙는다**(#3 조용한 0 금지)
    said = (root / "app/core/stages/s2b_base.py").read_text(encoding="utf-8")
    assert "BaseProb(probs=None" in said, "🔴 기준을 빈 값으로 안 낸다"
    assert "기준(Elo)은 지웠다" in said, "🔴 그 사실을 사유에 안 적는다"


# ⚠️ **걷은 시험** — `saybundle`(최종 평 LLM 프롬프트 묶음)이 지시서
#    2026-10-12(셋째) §1 처분으로 **지워졌다**(㉔ LLM 서술 삭제).
#    걷은 시험: `test_v9_작성_입력을_상위_근거로_줄인다`
