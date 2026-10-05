"""🔴🔴 **§3 — 리드**(지시서 2026-10-05 딥서치 재구축). **리드는 코드다.**

> `lead.py` 가 하는 일은 **넷뿐**이고, 그 밖의 일을 하면 계약 위반이다.
>  1. **병합** — 하위 8개의 `variables[]` 조각을 합친다. 같은 주장(MinHash 0.8)
>     은 한 묶음으로 세어 **독립 출처 수를 올리고**, 유형·방향은 건드리지
>     않는다(방향은 검증층이 재계산). 하위가 담당 밖 유형을 적어 왔으면
>     **그대로 받는다** — 폐기는 검증층 몫이다.
>  2. **장부 갱신** — 유형군 × 팀 칸마다 `searched`/`found`/`empty`/`not_tried`
>     + 사유. 🔴 **`found` 배선이 이번에 완성돼야 한다** — 지금은 `searched`
>     만 적힌다.
>  3. **2차 보충(최대 1회)** — `not_tried`·`empty` 유형군만, 남은 예산 안에서
>     한 번 다시 돌린다(턴 6). 2차 뒤에도 비면 `gaps` 로 보고 — **3차는 없다**(M64).
>  4. **깔때기 집계** — 하위별 한 줄 + 합계.
>
> **리드가 하지 않는 것**(M60): LLM 호출로 변수·가설·시나리오를 만들지 않는다.
> 변수 내용을 고치지 않는다. 하위 결과를 버리지 않는다.
"""
from __future__ import annotations

import ast
import inspect


def _var(vid: str, kind: str = "absence_def", url: str = "https://a.com/1",
         claim: str = "선수 하나가 결장한다") -> dict:
    return {"id": vid, "type": kind, "team": "team:000081",
            "subject": "team:000081", "claim": claim, "quote": "out injured",
            "source_url": url, "lang": "en", "direction_hint": "away",
            "confidence": "high", "checked": True}


# ══════════════════════════════════════════════════════════════════
# M60 — 리드는 **변수를 만들지 않는다**
# ══════════════════════════════════════════════════════════════════
def test_M60_병합_출력의_모든_변수가_하위에_원형이_있다():
    from app.research import lead
    parts = [{"name": "A-홈", "variables": [_var("v1"), _var("v2")]},
             {"name": "B-홈", "variables": [_var("v3")]}]
    got = lead.merge(parts)
    ids = {str(v.get("id")) for v in got["variables"]}
    seen = {str(v["id"]) for p in parts for v in p["variables"]}
    assert ids <= seen, (
        f"🔴 리드가 **없던 변수를 만들었다**: {sorted(ids - seen)}")
    assert ids == seen, f"🔴 하위 변수를 버렸다: {sorted(seen - ids)}"


def test_M60_리드_코드에_LLM_호출이_없다():
    from app.research import lead
    src = inspect.getsource(lead)
    tree = ast.parse(src)
    bad = {n.func.attr for n in ast.walk(tree)
           if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
           and n.func.attr in ("chat", "ask", "complete", "run")}
    assert not bad, (
        f"🔴 리드가 LLM 을 부른다{sorted(bad)} — 가설·시나리오는 DeepSeek "
        f"단계 3 그대로다(M60)")
    # 🔴 `solar` 는 **예산 설정 읽기**로만 쓴다 — 그것만 허용한다.
    #    ⚠️ 이름이 보이는지로 보면 안 된다(`from app import solar` 가 걸린다) —
    #       **무엇을 부르는지**를 본다.
    on_solar = {n.func.attr for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "solar"}
    # 🔴 `solar_concurrency` 도 **예산 설정 읽기**다 — 429 를 받은 뒤의 동시
    #    호출 수를 그 한 곳이 정한다(사용자 지시 2026-10-06 ④ · 사본 금지).
    #    ⚠️ 목록을 늘릴 때는 **그것이 LLM 호출이 아님**을 확인하고 늘린다.
    assert on_solar <= {"budget_cfg", "solar_concurrency"}, (
        f"🔴 리드가 `solar` 로 예산 설정 밖의 일을 한다{sorted(on_solar)}")


def test_M60_같은_주장은_독립_출처_수를_올린다():
    """🔴 유형·방향은 **건드리지 않는다** — 방향은 검증층이 재계산한다."""
    from app.research import lead
    same = "호날두가 명단에서 빠졌다"
    parts = [{"name": "A-홈",
              "variables": [_var("v1", url="https://a.com/1", claim=same)]},
             {"name": "A-원정",
              "variables": [_var("v2", url="https://b.com/2", claim=same)]}]
    got = lead.merge(parts)
    rows = got["variables"]
    assert len(rows) == 2, f"🔴 하위 결과를 **버렸다**: {len(rows)}개"
    outlets = [int(v.get("outlets") or 1) for v in rows]
    assert max(outlets) >= 2, (
        f"🔴 같은 주장이 두 출처에서 왔는데 **독립 출처 수가 안 올랐다**: "
        f"{outlets}")
    for v in rows:
        assert v.get("direction") is None, (
            "🔴 리드가 **방향을 적었다** — 그것은 검증층 몫이다(M60)")


def test_M60_담당_밖_유형도_그대로_받는다():
    """🔴 폐기는 **검증층 몫**이다(지시서 §3-1)."""
    from app.research import lead
    parts = [{"name": "A-홈", "kinds": ("absence_def",),
              "variables": [_var("v1", kind="venue_weather")]}]
    got = lead.merge(parts)
    assert len(got["variables"]) == 1, (
        "🔴 담당 밖 유형을 리드가 버렸다 — 폐기는 검증층이 한다")


# ══════════════════════════════════════════════════════════════════
# 장부 — `found` 배선이 **이번에 완성돼야 한다**
# ══════════════════════════════════════════════════════════════════
def test_r3_장부가_네_상태를_실제로_적는다():
    from app import ledgerbook
    from app.research import lead
    book = ledgerbook.Book()
    parts = [
        # 🔴 검증 통과 변수가 생겼다 → `found`
        {"name": "A-홈", "group": "A", "team_key": "team:000081",
         "searched": 3, "variables": [_var("v1")], "verified": 1},
        # 🔴 검색은 했는데 후보 0 → `empty`
        {"name": "B-홈", "group": "B", "team_key": "team:000081",
         "searched": 3, "variables": [], "verified": 0},
        # 🔴 검색만 했고 검증 통과는 아직 → `searched`
        {"name": "C-홈", "group": "C", "team_key": "team:000081",
         "searched": 2, "variables": [_var("v9")], "verified": 0},
    ]
    lead.write_book(book, parts)
    assert book.state("A", "team:000081") == "found", book.state("A", "team:000081")
    assert book.state("B", "team:000081") == "empty"
    assert book.state("C", "team:000081") == "searched"


def test_r3_실패_하위는_사유와_함께_not_tried():
    from app import ledgerbook
    from app.research import lead
    book = ledgerbook.Book()
    lead.write_book(book, [{"name": "D-홈", "group": "D",
                            "team_key": "team:000021", "failed": "타임아웃"}])
    assert book.state("D", "team:000021") == "not_tried"
    said = book.why("D", "team:000021")
    assert said and "타임아웃" in said, (
        f"🔴 실패 사유가 장부에 없다(#3): {said!r}")


# ══════════════════════════════════════════════════════════════════
# M64 — 2차 보충은 **최대 1회** · `not_tried`·`empty` 칸만
# ══════════════════════════════════════════════════════════════════
def test_M64_2차는_빈_칸만_고른다():
    from app import ledgerbook
    from app.research import lead
    book = ledgerbook.Book()
    book.mark("A", "team:000081", "found")
    book.mark("B", "team:000081", "empty")
    book.mark("C", "team:000081", "searched")
    got = lead.second_round(book, ["A", "B", "C", "D"], ["team:000081"])
    keys = sorted({g for g, _ in got})
    assert keys == ["B", "D"], (
        f"🔴 2차 대상이 틀렸다({keys}) — `empty`·`not_tried` 만이다")


def test_M64_2차는_한_번뿐이다():
    """🔴 **3차는 없다** — 루프가 아니다."""
    from app.research import lead
    import textwrap
    tree = ast.parse(textwrap.dedent(inspect.getsource(lead.second_round)))
    loops = [n for n in ast.walk(tree) if isinstance(n, ast.While)]
    assert not loops, (
        "🔴 2차에 `while` 이 있다 — 최대 1회여야 한다(M64)")
    assert hasattr(lead, "SECOND_ROUNDS") and lead.SECOND_ROUNDS == 1, (
        "🔴 `SECOND_ROUNDS = 1` 이 이름으로 없다")


def test_M64_남은_예산_안에서만_돈다():
    from app.research import lead
    assert hasattr(lead, "second_budget"), (
        "🔴 `lead.second_budget(쓴 것들)` 이 없다 — 2차가 상한을 넘을 수 있다")
    left = lead.second_budget([{"searched": 3, "fetched": 2, "out": 4000}] * 8)
    assert left["search"] == 0 and left["fetch"] == 0, left
    some = lead.second_budget([{"searched": 1, "fetched": 0, "out": 500}] * 8)
    assert some["search"] == 16 and some["fetch"] == 16, some
    assert some["out"] > 0


# ══════════════════════════════════════════════════════════════════
# 깔때기 집계 — 하위별 한 줄 + 합계
# ══════════════════════════════════════════════════════════════════
def test_r3_하위별_한_줄과_합계를_낸다():
    from app.research import lead
    said = lead.funnel_lines([
        {"name": "A-홈", "searched": 3, "passed": 2, "rejected": 1,
         "fetched": 2, "cands": 4, "verified": 3, "out": 4100, "secs": 38.0},
        {"name": "B-홈", "searched": 2, "passed": 2, "rejected": 0,
         "fetched": 1, "cands": 2, "verified": 1, "out": 2000, "secs": 21.0},
    ])
    joined = "\n".join(said)
    assert "A-홈" in joined and "q3" in joined and "통과2" in joined, joined
    assert "4.1k" in joined, f"🔴 토큰을 k 로 안 적는다: {joined}"
    assert "합계" in joined, "🔴 합계 줄이 없다"


def test_r3_하위별_표가_로그로_간다():
    """🔴 §3-4: *"하위별 한 줄과 합계를 **기존 깔때기 로그에** 쓴다."*

    ⚠️ 실사고 2026-10-05: 표가 `agent_note` 로만 갔고 카드가 **471자에서
       잘랐다** — `tools/research_report.py` 가 읽을 것이 없었다(표 없이
       "됐다"는 보고가 된다).
    """
    from app import analyze
    tree = ast.parse(inspect.getsource(analyze))
    # 🔴 `funnel_lines` 결과가 `logger` 로 가는 자리가 있어야 한다
    logged = False
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr in ("info", "warning")
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "logger"):
            if "하위" in ast.dump(n) or "funnel_lines" in ast.dump(n):
                logged = True
    assert logged, (
        "🔴 하위별 표를 **로그로 안 찍는다** — 카드는 자르고, 보고 도구는 "
        "읽을 것이 없다(§3-4)")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **병합은 실제 꼴을 받는다** — 실사고 2026-10-05 (인도네시아–태국)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 봇이 **죽었다**: `lead.merge → dict(v) → TypeError: 'Classified' object
#     is not iterable`. 🔴 `_run_agent` 는 **판정층 변수**(`classify.Classified`)
#     를 돌려주는데 내 계약은 **dict 로만** 시험했다 — 실제 경로의 꼴을 안 봤다.
#  🔴 ①번(`done.variables` 가 문자열)과 **같은 병**이다. 꼴을 **들어오는
#     자리에서** 맞춘다(§8-3).
def test_병합이_Classified_객체도_받는다():
    from app import classify
    from app.research import lead
    rows = [classify.Classified(
        type="absence", team="team:000081", direction="home",
        hardness="soft", text="선수 하나가 결장한다",
        source_url="https://a.com/1", why="규칙 사유")]
    got = lead.merge([{"name": "A-홈", "variables": rows}])
    assert len(got["variables"]) == 1, got
    said = got["variables"][0]
    # 🔴 **원본 객체를 잃지 않는다** — 검증층이 그 객체를 쓴다
    assert said is rows[0] or getattr(said, "text", None) == rows[0].text, (
        "🔴 `Classified` 를 dict 로 바꿔 **원본을 잃었다** — 검증층이 못 쓴다")
    # 🔴 독립 출처 수는 **객체에도** 붙는다
    assert getattr(said, "outlets", None) is not None or isinstance(said, dict)


def test_병합이_두_꼴을_섞어_받는다():
    """🔴 옛 경로(dict)와 새 경로(`Classified`)가 함께 올 수 있다."""
    from app import classify
    from app.research import lead
    obj = classify.Classified(
        type="absence", team="team:000081", direction="home", hardness="soft",
        text="같은 주장이다", source_url="https://a.com/1", why="w")
    got = lead.merge([{"name": "A-홈", "variables": [obj]},
                      {"name": "A-원정",
                       "variables": [_var("v2", claim="같은 주장이다",
                                          url="https://b.com/2")]}])
    assert len(got["variables"]) == 2, got
