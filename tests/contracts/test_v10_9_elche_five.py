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


def test_2_맞대결_검열은_맞대결_문장만_본다() -> None:
    from app.core.stages import s9_audit as au
    assert "맞대결" in au.H2H_TOPIC_WORDS
    got = _src("app/core/stages/s9_audit.py")
    assert "H2H_TOPIC_WORDS" in got.split("H2H_EVEN_WORDS if x in said_line")[0]


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
    from app.core.lineupgate import XI_N
    from app.core.stages.s2e_matchup import usual_xi
    # 🔴 `games_of` 가 받는 꼴로 준다(사본 금지 — 그 함수가 목록을 만든다)
    rows = [{"home_name": "A", "away_name": "B", "mine_home": True,
             "utc": f"2026-10-0{i + 1}T00:00:00Z", "goals": [], "stats": {},
             "starters": [f"p{j}" for j in range(14)]} for i in range(5)]
    assert len(usual_xi(rows)) == XI_N


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
    got = _src("app/collect/leagueelo.py")
    tree = ast.parse(got)
    fn = next(x for x in ast.walk(tree)
              if isinstance(x, ast.FunctionDef) and x.name == "rating_of")
    assert "same_any" in ast.unparse(fn), "🔴 느슨한 대조 칸이 없다"
