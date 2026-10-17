"""🔴🔴 **운영 확정 — M1 + ρ 보정 · 그림자 M3**(사용자 결정 2026-10-12).

> ⑯ 운영 확률 = `legacy/old_engine.run`(K0 해시 고정) → `drawfix`(ρ 판) 순서.
> 판 없으면 **보정 없이 + 🔴**. 그림자 = M3(probfloor) · 바닥 = Elo.
> 생존·역배·보호 줄 = **M1 보정 후 격자** 합(소수 넷째 자리).
> 축 기여 분해는 **보정 전** 수를 설명함을 카드에 표시.
> 계약 **M1-1**: 운영 확률이 `old_engine` 외 경로에서 나오면 실패.
> 계약 **M1-2**: `drawfix` 판 없이 보정 수가 나오면 실패.
> 계약 **M1-3**: 그림자·바닥 확률이 **등급·생존에 닿으면** 실패.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _code(rel: str) -> str:
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_m1_1_operation_number_comes_from_old_engine() -> None:
    """🔴🔴 **M1-1** — 운영 승무패의 출처는 **하나**다.

    ⚠️ **그 하나가 바뀌었다** — 종전엔 `old_engine`(얼린 M1)이었고, 사용자
       지시 2026-10-15 가 *"초기 확률 **33.3 프로로 동등**"* 으로 덮었고,
       2026-10-17 이 *"**기대득점 지워라**"* 로 옛 엔진 호출을 걷었다.
    🔴 그래서 세는 것은 *"승무패를 덮는 자리가 **`flat_prob` 하나뿐**인가"* 다.
    """
    said = _code("app/core/probmodel.py")
    assert "_oe.run(" not in said, "🔴 운영이 옛 엔진을 다시 부른다"
    i = said.index("said_flat, why_flat = flat_prob(varset, ref=ref)")
    # ⚠️ `_code()` 는 `ast.unparse` 라 **따옴표가 작은 것**이다(D46) — 글자를
    #    그대로 비교하지 말고 **칸 이름**으로 센다.
    assert "got.home = round(float(said_flat[" in said[i:i + 400]
    # 🔴 **승무패 셋을 한꺼번에 덮는 자리**는 ρ 보정 하나뿐이다(M1 대입은 없다)
    assert "got.home, got.draw, got.away = (said_m1.home" not in said, (
        "🔴 옛 M1 이 운영 수를 덮는다")
    assert said.count("got.home, got.draw, got.away") == 1, (
        f"🔴 승무패를 한꺼번에 덮는 자리가 "
        f"{said.count('got.home, got.draw, got.away')}곳이다 — 하나여야 한다")


# 🔴 **`test_m1_2_no_correction_without_a_version_file` 을 지웠다** — `core/drawfix`(ρ 보정)를 지웠다 — 격자를 걷자 굽힐 대상이 없어졌고 ρ 는 폐기 유지였다(사용자 지시 2026-10-17 · CLAUDE.md).

def test_m1_2_correction_needs_the_plate_in_code() -> None:
    """🔴🔴 **무승부 보정(ρ)은 운영 경로에 없다** — 사용자 지시 2026-10-17.

    ⚠️ 이 시험은 *"코드가 판을 읽고 나서만 보정한다"*(2026-10-12)를 세고
       있었다. 🔴 그 보정은 **격자를 굽히는 것**이고, 격자는 두 번 걷혔다:
         · 2026-10-15(3번) *"기대득점 빼면…"* → λ·오버·스코어를 비운다
         · 2026-10-17 *"기대득점 지워라"* → 옛 엔진을 **안 부른다**
       그래서 굽힐 격자가 없고, 보정한 승무패도 `flat_prob` 가 덮었다
       (효과 **0** 이었다 · 실측으로 세고 180줄을 걷었다).
    🔴 그리고 ρ 는 **폐기 유지**다(2026-10-13 `draw_care` · CLAUDE.md).
    🔴 그래서 세는 것을 뒤집는다 — 운영이 **보정을 부르지 않는다**.
    ⚠️ `core/drawfix` 모듈은 **안 지웠다**(백필·비교가 읽는다 · 아래에서 그
       함수들이 **제 일을 하는지**는 그대로 센다).
    """
    said = _code("app/core/probmodel.py")
    assert "_dfx.load(" not in said and "_dfx.bend(" not in said, (
        "🔴 운영이 무승부 보정을 다시 부른다 — ρ 는 폐기 유지다")
    assert "drawfix" not in said, "🔴 운영이 `drawfix` 를 들여온다"


def test_m1_3_shadow_and_floor_never_touch_grade_or_survival() -> None:
    """🔴🔴 **M1-3** — 그림자·바닥은 **등급·생존**에 닿지 않는다."""
    said = _code("app/core/pipeline.py")
    # 🔴 생존에 넘기는 분포는 `edge["sim"]["scores"]`(= M1 보정 후 격자)다
    i = said.index("s7_judge.run(")
    assert "dist=" in said[i:i + 400]
    assert "shadow" not in said[i:i + 400] and "floor" not in said[i:i + 400]
    # 🔴 판정 쪽 코드에 그림자·바닥이 **없다**
    judge = _code("app/core/stages/s7_judge.py")
    for bad in ("shadow", "floor"):
        assert bad not in judge, bad


def test_survival_and_underdog_use_the_corrected_grid() -> None:
    """🔴 생존·역배·보호 줄이 **같은(보정 후) 격자**를 쓴다."""
    said = _code("app/core/render.py")
    i = said.index("_underdog_line")
    # 🔴 λ 로 격자를 **다시 만들지 않는다** — 저장된 격자를 쓴다
    block = said[said.index("def _underdog_line"):][:1800]
    assert "scores" in block, "🔴 역배 줄이 저장된 격자를 안 쓴다"


def test_card_says_decomposition_is_pre_correction() -> None:
    """🔴 축 기여 분해가 **보정 전** 수를 설명한다고 카드가 적는다."""
    said = (ROOT / "app/core/render.py").read_text(encoding="utf-8")
    assert "보정 전" in said


def test_card_shows_the_confidence_band() -> None:
    """🔴 §2 — 문턱은 보류하고 **구간(30/20/10%)만** 카드에 적는다."""
    said = (ROOT / "app/core/render.py").read_text(encoding="utf-8")
    assert "확신 구간" in said
    from app.core import bands
    assert bands.of(0.62) == "상위 10%" or bands.of(0.62) == "상위 20%"
    assert bands.of(0.30) == ""


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **0-0 경기가 빠지지 않는다** — 실사고 2026-10-12(코모 0-0 로마)
# ══════════════════════════════════════════════════════════════════
#
#  🔴 종전 `backfill.score_of` 는 **골 목록**으로만 스코어를 셌다 → 0-0 은 골이
#     없어 `None` 이 되고 **백필·재생·채점에서 통째로 빠졌다**. 무승부가 구조적
#     으로 덜 세졌다. ⚠️ 그 표본으로 잰 무승부율·보정 판은 **다시 재야 한다**.


def test_zero_zero_is_read_from_the_header() -> None:
    """🔴 0-0 도 **스코어로 읽힌다**(골 목록이 비어도)."""
    from app.core import backfill as bf
    said = {"props": {"pageProps": {"header": {
        "status": {"finished": True, "scoreStr": "0 - 0"}}}}}
    assert bf.score_of(said) == (0, 0)


def test_unfinished_match_is_still_none() -> None:
    """⚠️ 끝나지 않은 경기는 **여전히 `None`** 이다(지어내지 않는다)."""
    from app.core import backfill as bf
    said = {"props": {"pageProps": {"header": {
        "status": {"finished": False, "scoreStr": "1 - 0"}}}}}
    assert bf.score_of(said) is None


def test_header_wins_over_the_goal_list() -> None:
    """🔴 헤더가 **1순위**다 — 골 목록은 그것이 없을 때만 본다."""
    from app.core import backfill as bf
    said = (ROOT / "app/core/backfill.py").read_text(encoding="utf-8")
    i = said.index("def score_of")
    j = said.index("fm.goals_of(j)", i)
    assert said.index("scoreStr", i) < j, "🔴 골 목록을 먼저 본다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **폼 창의 대회 기준은 "이 경기의 대회"다** — 실사고 2026-10-13
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 종전에는 **지난 경기 목록 첫 줄**의 대회 이름을 기준으로 삼았다. 토리노의
#     첫 줄이 `Coppa Italia` 라 기준이 컵이 되고 **세리에A 경기 3건이 전부 빠졌다**
#     → 축1 폼이 **친선(13-0 포함)과 컵**만 봤다. 🔴 그 수가 운영 확률(57%)을 만들었다.


def test_form_level_reference_is_this_match() -> None:
    """🔴 폼 창의 대회 기준은 `ref.competition` 이다(목록 첫 줄이 아니다)."""
    said = _code("app/core/stages/s2e_matchup.py")
    i = said.index("_level.keep(")
    head = said[max(0, i - 900):i]
    assert "getattr(ref, 'competition'" in head.replace('"', "'"), head[-300:]
    # 🔴 **목록 첫 줄에서 집는 길이 없다**
    assert "for one in rows['home'] + rows['away']" not in head.replace(
        '"', "'")


def test_level_keep_drops_friendlies_and_keeps_the_league() -> None:
    """🔴 그 리그 경기는 **남고**, 친선·하위 리그 컵은 **빠진다**."""
    from app.core import level
    rows = [{"league": "Serie A", "opp": "Milan", "gf": 1, "ga": 1},
            {"league": "Club Friendlies", "opp": "Pinzolo", "gf": 13,
             "ga": 0},
            {"league": "Coppa Italia", "opp": "Carrarese", "gf": 2, "ga": 0}]
    got, why = level.keep(rows, league="Serie A",
                          elo={"Milan": 1500.0, "Monza": 1400.0})
    kept = [r["opp"] for r in got]
    assert "Milan" in kept, (kept, why)
    assert "Pinzolo" not in kept, (kept, why)
    assert "Carrarese" not in kept, (kept, why)   # 컵 · 상대가 표에 없다
