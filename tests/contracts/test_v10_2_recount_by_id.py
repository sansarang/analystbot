"""🔴🔴 **id 기준 재계산 · 검열 카탈로그 · 과거 라인업** — 2026-10-11 ④⑤⑥.

> 4. 재계산: 위를 고친 뒤 squad_turnover·r 가중·명단 대조·무기 꺼짐을 **id 기준**
>    으로 다시 센다. 고정물: 가와사키–나고야 캡처 → 4명 전원 id 확정, 양 팀 "없는
>    선수" 각 3명(문턱 5 미만 → **깃발 꺼짐**), 이즈미 결장·무기 꺼짐 **없음**,
>    가와사키 GK 1명.
> 5. 검열 카탈로그: 평소 XI 에서 빠진 선수를 **`DROP:id`** 로 넣는다(쇼난 가세·
>    도하나). **코드가 계산한 사람은 모델이 써도 위반이 아니다.**
> 6. 과거 라인업 백필: 등록 리그(J2 포함) 팀마다 최근 리그 **10경기** 선발 XI 를
>    fotmob 경기 페이지에서 쌓는다(킥오프 전 자료만). 명단 대조 표본 5경기 미만이
>    안 나오게.
"""
from __future__ import annotations

import ast
import inspect


def _src(fn) -> str:
    tree = ast.parse(inspect.getsource(fn))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Module)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


# ══════════════════════════════════════════════════════════════════
# ④ id 기준 재계산 — 같은 사람을 두 번 세지 않는다
# ══════════════════════════════════════════════════════════════════

def test_off_matchday_counts_by_id() -> None:
    """🔴🔴 ④ — 한글 캡처 XI 와 로마자 명단을 **같은 사람으로** 센다.

    ⚠️ 실사고: 캡처가 `브로더센`·`와키자카` 로 오고 과거 선발이 `Svend Brodersen`·
       `Yasuto Wakizaka` 라, 글자로 세니 **둘 다 "없는 선수"** 가 됐다.
    """
    from app.core import turnover
    src = _src(turnover.off_matchday)
    assert "playerid" in src, "id 로 안 센다(이름 문자열 비교가 남아 있다)"


def test_roster_gap_counts_by_id() -> None:
    """🔴 ④ — **명단 대조**(결장 사다리 칸 2)도 id 로 센다."""
    from app.core import absence
    src = _src(absence.roster_gap)
    assert "playerid" in src or "_pid" in src


def test_off_weapons_counts_by_id() -> None:
    """🔴🔴 **지운 경로를 계약하던 시험이다** — 사용자 지시 2026-10-17.

    > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**

    ⚠️ 이 시험이 지키던 것(test_off_weapons_counts_by_id)은 **상성 축 · λ(기대 득점) · 몬테카를로
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


# ══════════════════════════════════════════════════════════════════
# ⑤ 검열 카탈로그 — `DROP:id`
# ══════════════════════════════════════════════════════════════════

def test_catalog_has_dropped_players() -> None:
    """🔴🔴 ⑤ — **평소 XI 에서 빠진 선수**가 `DROP:` 로 카탈로그에 든다.

    ⚠️ 실사고 2026-10-11(쇼난): 코드가 고른 주장이 `Naoki Kase`·`Kazuki Dohana`
       를 말하는데, 검열 (l) 이 *"XI·결장 명단·변수 대상에 없다"* 로 그 글을 버렸다
       — **코드가 계산한 사람**을 모델이 쓰면 위반이 되는 모순이었다.
    """
    from app.core import layer1
    src = _src(layer1.facts_catalog)
    assert "DROP:" in src, "빠진 선수를 카탈로그에 안 넣는다"


# ⚠️ **걷은 시험** — `s9_audit`(최종 평 LLM **검열**)이 지시서
#    2026-10-12(셋째) §1 처분으로 지워졌다(그 평이 코드 템플릿이 되었다).
#    🔴 코드 계산이던 `top_scores`·`score_drivers`·`_names_in` 은 쓰는 곳
#    (`app/core/layer1.py`)으로 **옮겼다** — 사본이 아니다.
#    걷은 시험: `test_dropped_player_is_not_a_violation`

def test_roster_gap_uses_ten_match_starters() -> None:
    """🔴🔴 ⑥ — 명단 대조가 **경기 목록의 선발**(10경기)을 쓴다.

    ⚠️ 실측 2026-10-11(쇼난): `과거 XI 4경기(<5)` 로 칸이 0 이었다 — 그 자료는
       `facts.past_xi`(≤5)였다. 🔴 `_history` 는 **10경기 선발**을 이미 들고 온다.
    """
    from app.core import absence
    src = _src(absence.starts_of)
    assert "games" in src and "starters" in src, "10경기 목록을 안 본다"
    #: 🔴 명단 없는 경기는 **분모에서 뺀다**(그 사실이 코드에 있다)
    assert "continue" in src
