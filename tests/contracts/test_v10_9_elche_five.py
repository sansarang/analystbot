"""🔴🔴 **엘체–셀타 다섯 고침** — 사용자 지시 2026-10-11(모니터링 보고 ①~⑤).

① ④ 근거 검열이 **S3 가 낸 우리 열**로 다시 센다(`ours=None` 대체가 방향을 뒤집었다)
② (m) 맞대결 검열은 **맞대결을 말하는 문장만** 본다(휴식 "비슷"에 걸렸다)
③ 복귀 문장을 `absence` 로 세지 않는다 → `returning`
④ 이름 없는 임시 열쇠를 **낱말 대조**로 합친다(`Celta Vigo` ↔ `RC Celta de Vigo`)
⑤ 평소 XI 는 **11명을 넘지 않는다** · 변수 경로의 꺼진 무기도 **비중 문을** 지난다 ·
   리그 Elo 조회가 **느슨한 대조**로 한 칸 더 본다
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_1_근거_검열을_S3_뒤에_다시_센다() -> None:
    got = _src("app/core/pipeline.py")
    assert "_cmp.market_reasons(" in got, "🔴 S3 뒤에 근거 줄을 다시 세지 않는다"
    head = got.split("_cmp.market_reasons(")[1][:200]
    assert 'ours=layers["ours"]' in head, "🔴 S3 가 낸 우리 열을 안 넘긴다"


# ⚠️ **걷은 시험** — `s9_audit`(최종 평 LLM **검열**)이 지시서
#    2026-10-12(셋째) §1 처분으로 지워졌다(그 평이 코드 템플릿이 되었다).
#    🔴 코드 계산이던 `top_scores`·`score_drivers`·`_names_in` 은 쓰는 곳
#    (`app/core/layer1.py`)으로 **옮겼다** — 사본이 아니다.
#    걷은 시험: `test_2_맞대결_검열은_맞대결_문장만_본다`

def test_3_복귀는_결장이_아니다() -> None:
    from app.core.stages.s5_verify import _retype
    kind, why = _retype("absence", "Sangare는 햄스트링 부상에서 회복하여 출전 가능하다")
    assert kind == "returning" and why
    # ⚠️ 결장 낱말이 함께 있으면 바꾸지 않는다
    assert _retype("absence", "복귀가 늦어져 이번 경기는 결장한다")[0] == "absence"
    assert _retype("absence", "무릎 부상으로 출전이 불투명하다")[0] == "absence"
    assert _retype("recent_pattern", "복귀했다")[0] == "recent_pattern"


def test_3_유형_바로잡기가_내용검사보다_먼저다() -> None:
    got = _src("app/core/stages/s5_verify.py")
    assert got.index("_retype(str(c.type)") < got.index("said_bad = _type_fits(")


def test_4_낱말_대조로_이름없는_열쇠를_합친다() -> None:
    got = _src("app/teamref.py")
    assert "same_any" in got, "🔴 대조 입구를 쓰지 않는다"


def test_5_평소_XI_는_열한명을_넘지_않는다() -> None:
    """🔴🔴 **지운 경로를 계약하던 시험이다** — 사용자 지시 2026-10-17.

    > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**

    ⚠️ 이 시험이 지키던 것(test_5_평소_XI_는_열한명을_넘지_않는다)은 **상성 축 · λ(기대 득점) · 몬테카를로
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


def test_5_변수_경로도_비중_문을_지난다() -> None:
    from app.core import style
    from app.core.matchup import SIX_DEF
    from app.core.stages.s2e_matchup import _gate_off
    axes = ["forward", "box_entry", "direct", "press"]
    out = _gate_off(axes, usual={"a"}, out_today={"a"}, share=0.0)
    assert set(out) == {x for x in axes if x in SIX_DEF}, "🔴 비중 0 인데 공격이 꺼졌다"
    big = _gate_off(axes, usual={"a"}, out_today={"a"},
                    share=float(style.OFF_SMALL))
    assert set(big) == set(axes), "🔴 비중이 문턱을 넘었는데 안 껐다"
    # ⚠️ 못 쟀으면 막지 않는다(#3)
    assert set(_gate_off(axes, usual={"a"}, out_today={"a"})) == set(axes)


def test_5_리그_Elo_조회가_느슨한_대조를_본다() -> None:
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_5_리그_Elo_조회가_느슨한_대조를_본다)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
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
