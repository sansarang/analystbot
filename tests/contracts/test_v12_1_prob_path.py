"""🔴🔴 **확률 경로 재구성** — 사용자 지시 2026-10-12(적중률 1번).

> 1. 확률 경로 재구성: ③ **Elo → 바닥 λ/승무패**. ⑪ **축0·축1만**(Elo 대비 잔차).
> **축2·축3·⑩ 전략 판정은 확률 경로 밖**(표시·검증). **C1 개정**, 계약·흐름도 갱신.

🔴 왜 — 444경기 백필(2026-10-12): 축2 개선 **−0.0038** · 축3 **−0.0039**(음수 =
   손실을 만든다). 축0 +0.0007 · 축1 +0.0001 만 남는다. 그리고 봇은 `Elo만` 을
   **이기지 못했다**(−0.0052 · 95% −0.0119~+0.0015 → 0 을 품는다).
🔴 **C1 개정**: 옛 C1 은 *"S3 입력에 Elo 가 없다"* 였다. 이제 **Elo 가 바닥**이고
   상성(축0·축1)은 **그 위의 잔차**다. ⚠️ 동기·일정·감독 발언·맞대결·시장·LLM 은
   그대로 **금지**다(그 금지는 안 걷힌다).
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════
# 바닥 = Elo
# ══════════════════════════════════════════════════════════════════

def test_floor_comes_from_elo() -> None:
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_floor_comes_from_elo)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
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


def test_floor_is_none_without_elo() -> None:
    """🔴🔴 **Elo 바닥 경로를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_floor_is_none_without_elo)이 지키던 것은 `probfloor` 의 **Elo 바닥** 묶음이다 —
       `floor_of`(Elo → 승무패) · `lambdas`(바닥을 λ 로) · `compute`(바닥 +
       잔차) · `load_coef`(적합 계수).
    🔴 확률은 이미 그 수를 안 봤다(승무패 = `flat_prob`). 그리고 오늘 지은
       계약 `test_bl1` 이 `compute` 가 **지워진 `base.triple_of` 를 부르는**
       것을 잡았다 — 라이브에서 카드가 죽는 자리였다.
    🔴 그래서 지웠고, 이 시험은 *"되살아나지 않는다"* 를 지킨다.
    """
    from app.core import probfloor as _pf
    for one in ("floor_of", "lambdas", "compute", "load_coef"):
        assert not hasattr(_pf, one), f"🔴 `probfloor.{one}`(Elo 바닥)이 되살아났다"
    #  🔴 **남아야 하는 것** — 격자에서 마켓을 세는 둘(Elo 를 안 쓴다)
    for one in ("score_grid", "markets_of"):
        assert hasattr(_pf, one), f"🔴 `probfloor.{one}` 이 같이 지워졌다"


def test_residual_uses_axis0_and_axis1_only() -> None:
    """🔴 ⑪ — 잔차는 **축0·축1만**이다(축2·축3 은 안 본다)."""
    from app.core import probfloor as pf
    assert tuple(pf.RESIDUAL_AXES) == ("axis0", "axis1")


# ⚠️ **옮긴 자리 2026-10-12**: 손값 β 로 바닥을 기울이던 `probfloor.blend` 는
#    엔진 교체 지시서 §3(*"손값 β 삭제"*)으로 `app/` 에서 걷혔고, **비교 기준**
#    으로만 쓰이므로 채점기(`tools/backfill_score.legacy_blend`)로 갔다.
#    🔴 지키는 것은 그대로다 — 잔차는 **축0·축1만**이고 축2·축3 은 확률을 못 민다.

def _blend():
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from backfill_score import legacy_blend
    return legacy_blend


def test_residual_moves_the_floor() -> None:
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_residual_moves_the_floor)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
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


def test_axis2_axis3_cannot_move_the_probability() -> None:
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_axis2_axis3_cannot_move_the_probability)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
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


def test_strategy_is_out_of_the_probability_path() -> None:
    """🔴 ⑩ 전략 판정이 확률 경로에 **없다**(표시·검증으로만)."""
    # ⚠️ D46 — **독스트링을 뺀 코드만** 본다(문서가 금지어를 설명하는 것과
    #    코드가 그것을 부르는 것은 다르다)
    tree = ast.parse(_src("app/core/probfloor.py"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    said = ast.unparse(tree)
    for bad in ("strategy", "plan", "전략"):
        assert bad not in said, bad


def test_c1_amended_in_the_docs() -> None:
    """🔴 C1 개정이 **문서에 적혀 있다**(Elo 는 바닥 · 나머지 금지는 유지)."""
    said = _src("docs/코드흐름도.md")
    assert "C1 개정" in said
    assert "Elo" in said and "바닥" in said


def test_survival_source_is_only_the_distribution() -> None:
    """🔴🔴 **보드 생존의 출처는 시뮬 분포 하나다**(사용자 지시 2026-10-12).

    > 퇴로는 끊는다 … 생존·등급 **"보류 — 확률 없음(사유)"**.
    🔴 시나리오 무게(`hit / mass`)가 생존·등급에 닿으면 **실패**다.
    """
    said = inspect.getsource(
        __import__("app.core.stages.s7_judge", fromlist=["x"])._one)
    assert "survive.from_dist" in said
    # 🔴 시나리오 무게로 생존을 세는 자리가 **없어야** 한다
    assert "hit / mass" not in said.replace(" ", "")
    assert "hit/mass" not in said.replace(" ", "")
    # 🔴 분포가 없으면 **보류**다
    i = said.index("if not dist:")
    assert '"보류"' in said[i:i + 500]


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **운영 ⑯ 배선**(사용자 결정 2026-10-12 (a)) — 새 구조가 판정이다
# ══════════════════════════════════════════════════════════════════

def test_lambda_is_solved_to_match_the_floor() -> None:
    """🔴🔴 **지운 경로를 계약하던 시험이다** — 사용자 지시 2026-10-17.

    > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**

    ⚠️ 이 시험이 지키던 것(test_lambda_is_solved_to_match_the_floor)은 **상성 축 · λ(기대 득점) · 몬테카를로
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


def test_solver_says_when_it_cannot() -> None:
    """🔴🔴 **지운 경로를 계약하던 시험이다** — 사용자 지시 2026-10-17.

    > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**

    ⚠️ 이 시험이 지키던 것(test_solver_says_when_it_cannot)은 **상성 축 · λ(기대 득점) · 몬테카를로
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


def test_probmodel_takes_the_floor() -> None:
    """🔴 ⑯ 이 **바닥을 인자로 받는다**(Elo 가 그 바닥이다)."""
    import inspect

    from app.core import probmodel as pm
    assert "floor" in inspect.signature(pm.run).parameters


def test_pipeline_passes_the_elo_floor() -> None:
    """🔴 배선 — 파이프라인이 `base_p`(Elo)를 ⑯ 에 넘긴다."""
    said = _src("app/core/pipeline.py")
    i = said.index("prob = _pm.run(")
    assert "floor=" in said[i:i + 300], said[i:i + 200]


def test_shadow_field_and_card_line_exist() -> None:
    """🔴 그림자 확률 칸과 카드 줄이 있다.

    ⚠️ **방향이 뒤집혔다**(사용자 결정 2026-10-12 운영 교체): 이제 운영 ⑯ 은
       **M1(얼린 옛 경로)** 이고 **M3(새 경로)가 그림자**다. 🔴 근거는 460경기
       비교 시험 — M3 가 **어느 지표에서도 M1 을 앞서지 못했다**.
       (규칙 해석은 `M3 유지` 였고 그 기록은 그대로 남는다 ·
        `docs/fable/stages/2026-10-12_compare_paths.md`)
    """
    from app.core import probmodel as pm
    assert "shadow" in pm.ProbOut.__dataclass_fields__
    said = _src("app/core/render.py")
    assert "그림자" in said and "M3" in said
