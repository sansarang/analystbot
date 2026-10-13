"""🔴🔴 **§6-1 원천 표 · §6-2 질의 생성**(지시서 2026-10-13 밤 셋째).

> 6-1 계약 **SR1**: 원천 표에 **없는 도메인은 C등급**으로 처리 ·
>      **SR2**: S·A 없이 **C등급만으로 hard 사실**을 만들면 실패.
> 6-2 계약 **QY1**: 질의 언어에 **현지어가 없으면 실패** ·
>      **QY2**: 질의 로그(경기별 질의 목록·결과 수) **미기록 실패**.

🔴 왜 여기부터인가 — §6-7 기준선(재현율 **16.3%**)과 §6-4 감사(**잘못 버림 1%**)를
   함께 읽으면 잃는 자리는 **신원이 아니라 "무엇으로 찾나·어디서 찾나"** 다.
🔴 낱말·원천은 **설정표에만** 있다(`config/search_terms/*.yaml` ·
   `config/sources/*.yaml`) — 코드에 낱말을 적지 않는다(사본 금지).
"""
from __future__ import annotations


def test_sr1_unknown_domain_is_grade_c() -> None:
    from app.core.search import sources as sr
    got, why = sr.grade_of("nikkansports.com", league="league:J1")
    assert got == "A", (got, why)
    said, why2 = sr.grade_of("data.j-league.or.jp", league="league:J1")
    assert said == "S", (said, why2)
    none, why3 = sr.grade_of("example-blog.tistory.com", league="league:J1")
    assert none == "C" and "표에 없다" in why3


def test_sr2_hard_fact_needs_s_or_a() -> None:
    """🔴🔴 **SR2** — C등급만으로는 **hard 사실**을 못 만든다."""
    from app.core.search import sources as sr
    ok, why = sr.hard_ok(["C", "C"], league="league:J1")
    assert not ok and "C등급" in why
    said, why2 = sr.hard_ok(["C", "A"], league="league:J1")
    assert said and "A" in why2


def test_sources_table_is_read_not_hardcoded() -> None:
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "app/core/search/sources.py").read_text(
        encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    code = ast.unparse(tree)
    for bad in ("nikkansports", "yna.co.kr", "fotmob.com"):
        assert bad not in code, bad


def test_qy1_queries_must_include_the_local_language() -> None:
    from app.core.search import query as qy
    got, why = qy.build(league="league:J1", home="Kawasaki Frontale",
                        away="Nagoya Grampus", players=["Leandro Damiao"],
                        coach="Shigetoshi Hasebe", kinds=("absence",), cap=0)
    langs = {q["lang"] for q in got}
    assert "ja" in langs and "en" in langs, (langs, why)
    # 🔴 현지어 낱말 표가 없는 리그는 **질의를 만들지 않는다**(QY1)
    bad, why2 = qy.build(league="league:없는리그", home="A", away="B",
                         players=[], coach="", kinds=("absence",))
    assert bad == [] and "🔴" in why2


def test_queries_use_aliases_not_only_english() -> None:
    """🔴 별칭(현지 표기·약칭)을 쓴다 — 영어 표기 하나로만 찾지 않는다."""
    from app.core.search import query as qy
    got, _why = qy.build(league="league:KL1", home="Ulsan HD FC",
                         away="Gwangju FC", players=[], coach="",
                         kinds=("absence",))
    said = " ".join(q["q"] for q in got)
    assert "울산" in said or "ì" in said or "Ulsan" in said
    assert any(q["lang"] == "ko" for q in got)


def test_qy2_query_log_is_written() -> None:
    """🔴🔴 **QY2** — 질의 목록·결과 수를 **기록**한다(없으면 실패)."""
    from app.core.search import query as qy
    box = qy.Log()
    got, _why = qy.build(league="league:J1", home="FC Tokyo",
                         away="Kashima Antlers", players=[], coach="",
                         kinds=("absence", "expected_xi"), log=box)
    box.note(got[0]["q"], hits=3)
    said = box.rows()
    assert said and said[0]["hits"] == 3
    assert box.summary().startswith("질의")
    assert "미기록" in qy.Log().summary()


def test_site_queries_come_first() -> None:
    """🔴 S·A 원천 지정(`site:`) 질의가 **앞**이다(일반 질의는 그다음)."""
    from app.core.search import query as qy
    got, _why = qy.build(league="league:J1", home="FC Tokyo",
                         away="Kashima Antlers", players=[], coach="",
                         kinds=("absence",), cap=0)
    sites = [i for i, q in enumerate(got) if "site:" in q["q"]]
    plain = [i for i, q in enumerate(got) if "site:" not in q["q"]]
    assert sites and plain and max(sites) < min(plain), (sites[:3], plain[:3])


def test_cost_cap_keeps_s_a_and_still_english() -> None:
    """🔴🔴 **§6-9 비용 상한** — 넘으면 **S·A 만** 남기되 **영어는 지킨다**.

    ⚠️ 두 요구가 부딪힌다(*"영어 필수"* vs *"상한 초과 시 S·A 만"*) — 상한
       때문에 **영어가 사라지는 쪽**이 더 나쁜 손실이므로 영어 몇 개를 남긴다.
    """
    from app.core.search import query as qy
    from app.core.search import sources as sr
    cap = int(sr.table("league:J1").get("per_match_query_cap") or 0)
    assert cap > 0, "🔴 원천 표에 `per_match_query_cap` 이 없다"
    got, why = qy.build(league="league:J1", home="Kawasaki Frontale",
                        away="Nagoya Grampus",
                        players=["A", "B", "C", "D", "E"], coach="C 감독",
                        kinds=qy.KINDS)
    assert len(got) <= cap, (len(got), cap)
    assert any(q["lang"] == "en" for q in got), got[:3]
    assert sum(1 for q in got if q["grade"] in ("S", "A")) >= cap // 2
    assert "상한" in why


def test_players_are_not_asked_about_the_manager() -> None:
    """🔴 대상·종류 짝 — 선수에게 *"새 감독"* 을 묻지 않는다(실측에서 나왔다)."""
    from app.core.search import query as qy
    got, _why = qy.build(league="league:KL1", home="Ulsan HD FC",
                         away="Gwangju FC", players=["손흥민"], coach="김감독",
                         kinds=("coach",))
    bad = [q for q in got if q["target"].startswith("player:")]
    assert not bad, bad
