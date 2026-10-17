"""🔴🔴 **딥서치 삭제** — 사용자 지시 2026-10-17.

> 딥서치 삭제!!!!

🔴 **왜 — 실측 2026-10-17(우라와 두 실행 · 같은 경기·같은 날)**
코드가 만든 질의 24~30개가 검색 결과 **734건**을 긁어 기사 변수 **2개**였다.
⚠️ `site:jleague.jp` 가 준 "15건"의 실체는 **2014~2022년 글과 굿즈 페이지**였고,
   묵은 글 본문을 받는 데 **63초**를 썼다(URL 에 날짜가 없어 못 걸렀다).
🔴 세 경기 누적으로는 질의 68개 · 결과 1,913건 → 기사 변수 **2개**였다.

## 🔴 지운 선과 남긴 몸통
```
지웠다 ── run(코드 질의 다발 수확) · queries_for · _table_queries ·
          _llm_queries · regather · s4_extract._narrow ·
          querywriter.ask·said_of · subtasks.narrow_words·narrow_query·local_name
남겼다 ── _candidates · _fetch(던지고 받는 몸통) · 검문 전부 · gap_docs(입구)
```
⚠️ 몸통까지 지우면 **LLM 서치도 던질 길이 없다** — 둘은 몸통을 같이 쓴다.

이 파일이 지키는 것은 하나다: **지운 길이 조용히 되살아나지 않는다.**
"""
from __future__ import annotations

import ast
import inspect
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _code(path: pathlib.Path) -> str:
    """🔴 **D46** — 독스트링·주석을 뺀 **코드만**.

    지운 까닭을 글로 남기는 것과 그것을 **부르는** 것은 다르다.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                          ast.ClassDef)) and ast.get_docstring(n):
            n.body = n.body[1:]
    return ast.unparse(tree)


def test_ds1_코드_질의_다발이_없다() -> None:
    """🔴 질의를 만드는 곳은 **LLM 하나**다(`s4b_gapsearch.ask`)."""
    said = _code(ROOT / "app/core/stages/s3_docs.py")
    for one in ("queries_for", "_table_queries", "_llm_queries", "regather",
                "_RefShim"):
        assert one not in said, f"🔴 `{one}`(딥서치)가 되살아났다"
    # 🔴 몸통과 입구는 **남아야** 한다 — 지우면 LLM 서치도 못 던진다
    from app.core.stages import s3_docs
    for one in ("_candidates", "_fetch", "gap_docs", "tally_to",
                "grade_ok", "identity_ok", "sport_ok", "gate_ok", "names_of"):
        assert hasattr(s3_docs, one), f"🔴 `s3_docs.{one}`(몸통·검문)이 지워졌다"
    assert not hasattr(s3_docs, "run"), "🔴 `s3_docs.run`(딥서치)이 되살아났다"
    assert getattr(s3_docs, "STAGES", None) == ("gap_docs",), (
        "🔴 입구를 글자로 안 적었다 — 단계 계약이 `run` 을 찾는다")


def test_ds2_몸통이_질의를_반드시_받는다() -> None:
    """🔴🔴 `_candidates` 에 **기본값이 없어야** 한다.

    ⚠️ 종전에는 `queries` 를 비우면 `queries_for`(코드 질의)로 떨어졌다 —
       기본값을 두면 지운 길이 **조용히** 되살아난다.
    """
    from app.core.stages import s3_docs
    sig = inspect.signature(s3_docs._candidates)
    p = sig.parameters["queries"]
    assert p.default is inspect.Parameter.empty, (
        "🔴 `queries` 에 기본값이 있다 — 코드 질의로 떨어질 수 있다")


def test_ds3_운영이_수확을_직접_받는다() -> None:
    """🔴🔴 **`docs` 는 수확 결과 그 자체**여야 한다.

    ⚠️ 절제 실험: `docs = ([], "") or await harvest(...)` 로 바꾸면 운영은
       문서 0건이 되는데 글자 검사는 통과했다 — 그래서 **꼴**로 본다.
    """
    tree = ast.parse((ROOT / "app/core/pipeline.py").read_text(encoding="utf-8"))
    got = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Assign):
            continue
        names = {t.id for t in ast.walk(n.targets[0]) if isinstance(t, ast.Name)}
        if "docs" not in names:
            continue
        # `docs, _why = await _gs.harvest(...)` — 오른쪽이 **바로** await 다
        if isinstance(n.value, ast.Await) and isinstance(n.value.value, ast.Call):
            f = n.value.value.func
            if isinstance(f, ast.Attribute) and f.attr == "harvest":
                got.append(n)
    assert got, ("🔴 운영이 `docs` 를 **수확에서 바로** 받지 않는다 — "
                 "감싸거나 가로채면 문서가 조용히 0건이 된다")


def test_ds4_수확이_센_칸을_두_길에서_적는다() -> None:
    """🔴 **재생·라이브 둘 다** 깔때기를 적는다(#3 조용한 0 금지).

    ⚠️ 절제 실험: 라이브 쪽 `tally_to` 만 끊었는데 계약이 초록이었다 —
       재생 쪽 한 줄이 글자 검사를 통과시켰다. 그래서 **둘을 센다**.
    """
    from app.core.stages import s4b_gapsearch as gs
    src = inspect.getsource(gs.harvest)
    assert src.count("tally_to") >= 2, (
        f"🔴 `tally_to` 가 {src.count('tally_to')}번뿐이다 — 재생·라이브 둘 다 "
        "적어야 한다(카드가 *질의 못 쟀다* 로 남는다)")


def test_ds5_쓴_질의는_전부_던진다() -> None:
    """🔴🔴 하위 상한이 **받은 질의 수**다 — #3 조용한 0 금지.

    ⚠️ 설정값(`search`·`fetch` = 3)은 하위가 **여덟**일 때의 값이다. 하위가
       둘이 되자 총량이 ¼ 이 됐고, 고정물에서 녹음 질의 20개 중 **6개만**
       나가 문서가 5 → 1건이 됐다. 🔴 옛 비율은 **질의 1개당 받기 1건**이다.
    """
    from app.core.stages import s4b_gapsearch as gs
    src = inspect.getsource(gs._side_queries)
    #  ① **질의는 쓴 것을 전부 던진다** — 상한이 질의 수다
    assert "search_cap=max(1, len(mine))" in src, "🔴 질의가 상한에 버려진다"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **받기는 질의 수에서 떼어 놨다** — 사용자 지시 2026-10-17 *"둘다 해라"*
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전엔 `fetch_cap=len(mine)`(질의 1개당 1건)이었다. 실측
    #     2026-10-17(울산 HD vs 부천 4차): 질의 3개 → 결과 49 → **날짜 통과
    #     42건**인데 **4건만** 열어 문서 0건이었다.
    #  🔴 그래서 수는 **표가 든다**(`config/llm.yaml` 의 `budget.harvest`) —
    #     질의 상한 12 · 쪽마다 받기 12(옛 딥서치 총량 24를 쪽 둘로 나눈 수).
    assert "fetch_cap=max(1, fetch_per_side())" in src, (
        "🔴 받기가 다시 질의 수에 묶였다 — 날짜 통과한 것을 못 열고 버린다")
    #  ② 두 수는 **코드에 박지 않는다**(§13-7 사용자가 고친다)
    import yaml
    box = dict((yaml.safe_load(
        (ROOT / "config/llm.yaml").read_text(encoding="utf-8")) or {})
        .get("budget") or {}).get("harvest") or {}
    for key in ("queries", "fetch_per_side"):
        assert int(box.get(key) or 0) > 0, f"🔴 `budget.harvest.{key}` 가 없다"
    assert gs.max_q() == int(box["queries"]), "🔴 질의 상한이 표를 안 읽는다"
    assert gs.fetch_per_side() == int(box["fetch_per_side"]), (
        "🔴 받기 상한이 표를 안 읽는다")
    from app.core.stages import s3_docs
    got = inspect.getsource(s3_docs.gap_docs)
    assert "fetch_per_side" in got, (
        "🔴 상위 N 이 표를 안 본다 — 질의 수에 묶이면 42건 중 4건만 연다")


def test_ds6_표적_하위가_유형_전부를_받는다() -> None:
    """🔴🔴 `F-*` 하위는 **빈 칸 전체**를 겨냥하므로 유형도 전부다.

    ⚠️ 실측: 문서 9건이 왔는데 추출이 `F` 묶음 유형만 물어 **기사 변수 0개**
       였다(결장 기사가 와도 `복귀·명단` 만 물었다).
    🔴 목록은 묶음 표에서 **모은다** — 손으로 적지 않는다(#1).
    """
    from app.core.stages.s4_extract import group_kinds
    from app.core.stages.s4b_gapsearch import harvest_kinds
    got = harvest_kinds()
    assert len(got) >= 10, f"🔴 묶음 표에서 유형을 못 모았다 — {got}"
    for sid in ("F-home", "F-away"):
        assert set(group_kinds(sid)) == set(got), (
            f"🔴 `{sid}` 가 유형 전부를 안 받는다 — {group_kinds(sid)}")
    # ⚠️ 다른 묶음은 **그대로**다(자기 유형만)
    assert set(group_kinds("A-home")) != set(got), (
        "🔴 다른 묶음까지 전부를 받으면 추출이 엉뚱한 유형을 묻는다")


def test_ds7_좁히기_2차와_그_부품이_없다() -> None:
    """🔴 1차 제목에서 낱말을 뽑아 **코드가 질의를 다시 짜던** 길이다."""
    said = _code(ROOT / "app/core/stages/s4_extract.py")
    assert "_narrow" not in said, "🔴 좁히기 2차가 되살아났다"
    from app.research import subtasks
    for one in ("narrow_words", "narrow_query", "local_name"):
        assert not hasattr(subtasks, one), f"🔴 `subtasks.{one}` 가 되살아났다"
    from app.core import querywriter as qw
    for one in ("ask", "said_of"):
        assert not hasattr(qw, one), f"🔴 `querywriter.{one}`(딥서치)가 되살아났다"


def test_ds8_질의는_두_팀을_다_담으라고_말한다() -> None:
    """🔴🔴 **질의 꼴이 전부였다** — 사용자 지시 2026-10-17 *"질의하는게 문제"*.

    🔴 실측(봇의 `identity_ok`·`datehint.too_old` 로 센 수 · 울산 HD vs 부천):

        | 질의 꼴                         | 결과 | 신원 | 날짜 |
        | `울산 HD 예상 선발 라인업`(한 팀) |  9 | **0** | **0** |
        | `울산 부천 예상 선발`(두 팀)      | 13 |  12 |   9 |
        | `Ulsan Bucheon starting lineup`| 35 |  31 |  30 |

    ⚠️ 한 팀 질의는 **그 경기 글이 0건**이다 — 팀 일반 기사가 와서 신원 검문이
       전부 버린다. 질의 16개·결과 287건을 긁고도 **문서 0건**이던 뿌리다.
    🔴 그래서 프롬프트가 **두 팀을 다 넣으라고** 말해야 한다(그 수와 함께).
    """
    import inspect

    from app.core.stages import s4b_gapsearch as gs
    src = inspect.getsource(gs.ask)
    assert "두 팀 표기를 다 넣는다" in src, (
        "🔴 한 팀만 넣으라고 말하면 신원 통과가 0이 된다(실측 2026-10-17)")
    #  ⚠️ **수를 함께 적는다** — 다음 사람이 그 말을 안 믿고 되돌리지 않게
    assert "0건" in src and "12건" in src, "🔴 실측 수를 안 적었다(#3)"


def test_ds9_두_팀_질의가_쪽_둘에_나뉜다() -> None:
    """🔴 두 팀을 다 담으면 **모든 질의가 양쪽에 걸린다** — 한쪽이 상한을 다 쓴다.

    ⚠️ 받기 상한은 하위마다 따로다(`fetch_cap`) — 몰리면 다른 쪽이 굶는다.
    🔴 그래서 양쪽에 걸린 질의는 **번갈아** 준다. 한쪽 팀만 든 질의는 그대로다.
    """
    from app.core.schema import MatchRef
    from app.core.stages.s4b_gapsearch import _side_queries
    ref = MatchRef(id="m", sport="soccer", home="team:000318", away="team:000320",
                   home_name="Ulsan HD FC", away_name="Bucheon FC 1995",
                   competition="K-League 1", competition_short="KL1",
                   kickoff_utc="2026-10-17T07:30:00+00:00")
    pairs = [("울산 부천 예상 선발", "ko"), ("울산 부천 서명관 부상", "ko"),
             ("울산 부천 순위 승점", "ko"), ("울산 부천 휴식 일정", "ko")]
    got = {s: [q for q, _ in _side_queries(ref, pairs, s)[0]]
           for s in ("home", "away")}
    for side, rows in got.items():
        assert rows, f"🔴 `{side}` 가 빈손이다 — 한쪽이 상한을 다 쓴다"
    #  🔴 같은 질의를 **둘이 같이** 들지 않는다(예산 낭비)
    assert not (set(got["home"]) & set(got["away"])), got
    #  🔴 하나도 잃지 않는다
    assert len(got["home"]) + len(got["away"]) == len(pairs), got
