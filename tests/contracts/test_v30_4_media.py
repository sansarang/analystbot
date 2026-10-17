"""🔴🔴 **리그별 현지 매체 표** — 사용자 지시 2026-10-17.

> 매체 표 구현하고 … **우선 일본 매체표만** 해봐라

🔴 왜 — 실측 2026-10-17(세 경기): 질의 68개·검색 결과 **1,913건**으로 기사 변수
   **2개**였고, 가장 큰 손실이 ④ **신원**(가시마 **749건**)이었다. 검문이 센 것이
   아니라 **엔진이 그 경기 글을 못 찾는다**. 그 와중에
   `site:soccer-king.jp セレッソ大阪 日程` 은 **28건**을 줬다.

🔴 잠금 넷(`app/core/media.py` 머리말):
  ① 표는 `config/media.yaml` **하나**다(코드에 매체를 박지 않는다)
  ② 호스트는 **robots 확인 뒤에만** 쓴다(#4)
  ③ 표에 없는 리그는 **빈 목록 + 사유**(없는 매체로 좁혀 0건을 만들지 않는다)
  ④ 대회 열쇠를 **다시 만들지 않는다**(`s5_verify.comp_kind` 하나)
"""
from __future__ import annotations

import inspect
import pathlib

from app.core import media

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_md1_표는_설정에_있고_일본이_들어있다() -> None:
    """🔴 ① 값은 `config/` 에 두고 **사용자만** 바꾼다(§13-7)."""
    import yaml
    said = (ROOT / media.CONF).read_text(encoding="utf-8")
    box = yaml.safe_load(said)
    assert set(box) == {"max_hosts", "by_league"}, box
    rows = dict(box["by_league"])
    # 🔴 **일본 먼저**(사용자 지시) — J1·J2 둘 다
    for key in ("league:J1", "league:J2"):
        assert rows.get(key), f"🔴 `{key}` 가 표에 없다"
    # 🔴 **호스트만** 적는다(주소·경로 금지 — `hosts` 검사가 그것을 버린다)
    for key, hosts in rows.items():
        for one in hosts:
            assert "://" not in one and "/" not in one, (key, one)
    # ⚠️ 표가 **왜 생겼는지**를 파일이 말한다(다음 사람이 수를 안 믿게)
    assert "749" in said and "28건" in said


def test_md2_표에_없는_리그는_좁히지_않는다() -> None:
    """🔴 ③ 없는 매체로 좁혀 **0건을 만들지 않는다** — 사유를 남긴다(#3)."""
    got, why = media.hosts_of("league:J1")
    assert got and len(got) <= media.cap(), (got, media.cap())
    none, why2 = media.hosts_of("league:없는리그")
    assert none == [] and "매체 표에 없다" in why2, why2
    # 🔴 대회 열쇠가 없으면 그 사실을 적는다
    assert media.hosts_of("")[0] == [] and "열쇠가 없다" in media.hosts_of("")[1]


def test_md3_상한이_있다() -> None:
    """🔴 robots 를 그만큼만 받는다(한 호스트에 한 번 통신)."""
    assert 1 <= media.cap() <= 8, media.cap()
    import yaml
    rows = dict(yaml.safe_load(
        (ROOT / media.CONF).read_text(encoding="utf-8"))["by_league"])
    long = max(rows.values(), key=len)
    got, why = media.hosts_of(
        next(k for k, v in rows.items() if v is long))
    assert len(got) <= media.cap()
    if len(long) > media.cap():
        assert "잘랐다" in why, why


def test_md4_대회_열쇠를_다시_만들지_않는다() -> None:
    """🔴 ④ 만드는 곳은 `s5_verify.comp_kind` 하나다(사본 금지)."""
    src = inspect.getsource(media.key_of)
    assert "comp_kind" in src, src
    # 🔴 못 알아보면 **빈 글자**다(지어내지 않는다)
    assert media.key_of(None, None) == ""


def test_md5_딥서치가_표를_먼저_쓰고_robots_를_확인한다() -> None:
    """🔴🔴 ② 표 매체도 **robots 확인 뒤에만** 쓴다 · 그리고 모델 제안보다
    **앞에** 둔다(상한에 걸리면 표가 먼저 산다)."""
    said = (ROOT / "app/core/stages/s3_docs.py").read_text(encoding="utf-8")
    i = said.index("from app.core import media as _md")
    j = said.index("_qw.check_hosts(", i)
    k = said.index("_qw.site_queries(", i)
    assert i < j < k, "🔴 robots 확인 전에 `site:` 를 만든다(#4)"
    # 🔴 표 매체가 **모델 제안보다 앞**이다
    assert "want = [*said_tbl," in said, "🔴 표를 뒤에 둔다"
    # 🔴 `site:` 질의가 **보통 질의보다 앞**이다(상한에서 먼저 산다)
    assert "said = [*_qw.site_queries(ok, rows), *rows]" in said
    # ⚠️ 표가 비면 그 사실을 **수첩에** 적는다(#3)
    assert 'state.note(f"②③ 매체 표 — {why_tbl}")' in said


def test_md6_배선이_facts_를_넘긴다() -> None:
    """🔴🔴 **실사고 2026-10-17(우라와 실행)** — 표가 **한 곳도 안 붙었다**.

    ``_llm_queries`` 가 ``media.key_of(ref, None)`` 로 불렀고, ``comp_kind`` 는
    ``facts.match_format`` 을 읽으므로 **AttributeError → except → 빈 글자**가
    됐다. 그래서 *"⬜ 대회 열쇠가 없다"* 로 조용히 떨어졌다 — 운영이 내는 열쇠는
    **`league:J1`** 이었다(같은 실행 로그 8회).

    🔴 그래서 **글자가 아니라 꼴을 검사한다**: 그 함수는 ``facts`` 를 받고,
       ``key_of`` 에 **그 이름**을 넘긴다. ⚠️ 상태값(통과)이 아니라 **인자**다.
    """
    import ast
    from app.core.stages import s3_docs

    src = pathlib.Path(s3_docs.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)

    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.AsyncFunctionDef) and n.name == "_llm_queries"),
              None)
    assert fn is not None, "🔴 `_llm_queries` 가 없다 — 배선이 사라졌다"

    #  ① 그 함수가 `facts` 를 **받는다**
    names = [a.arg for a in (*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs)]
    assert "facts" in names, f"🔴 `facts` 를 안 받는다 — {names}"

    #  ② `key_of` 에 **그 이름**을 넘긴다(`None`·상수 금지)
    calls = [n for n in ast.walk(fn)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "key_of"]
    assert calls, "🔴 `key_of` 를 안 부른다 — 표를 안 본다"
    for one in calls:
        got = [a for a in one.args if isinstance(a, ast.Name) and a.id == "facts"]
        assert got, ("🔴 `key_of` 에 `facts` 를 안 넘긴다 — 열쇠가 빈 글자가 되고 "
                     "표가 조용히 안 붙는다(실사고 2026-10-17)")

    #  ③ 부르는 쪽도 `facts` 를 **넘긴다**(시그니처만 고치면 TypeError 다)
    outer = next((n for n in ast.walk(tree)
                  if isinstance(n, ast.AsyncFunctionDef) and n.name == "run"), None)
    assert outer is not None, "🔴 `run` 이 없다"
    use = [n for n in ast.walk(outer)
           if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
           and n.func.id == "_llm_queries"]
    assert use, "🔴 `run` 이 `_llm_queries` 를 안 부른다 — 안 이은 코드다(#2)"
    for one in use:
        got = [a for a in one.args if isinstance(a, ast.Name) and a.id == "facts"]
        assert got, "🔴 `run` 이 `facts` 를 안 넘긴다"


def test_md7_운영_열쇠가_표의_열쇠와_같은_꼴이다() -> None:
    """🔴 표의 열쇠는 **`comp_kind` 가 만드는 꼴**이어야 한다(④ 사본 금지).

    ⚠️ 실측 2026-10-17 우라와 실행: 운영 로그에 **`league:J1`** 이 8회 찍혔다.
       표가 `J1`·`jpn.1` 처럼 다른 꼴을 쓰면 **영구히 안 맞는다**(조용한 0).
    🔴 그래서 표의 모든 열쇠가 `competition.kind_of` 가 **실제로 낼 수 있는 값**
       인지 본다 — 리그 열쇠는 `config/competitions.yaml` 의 키다.
    """
    import yaml
    box = yaml.safe_load((ROOT / media.CONF).read_text(encoding="utf-8"))
    comps = yaml.safe_load(
        (ROOT / "config/competitions.yaml").read_text(encoding="utf-8")) or {}
    known = set(dict(comps.get("keys") or {}).keys())
    assert known, "🔴 대회 표를 못 읽었다 — 검사가 빈 통과가 된다"
    for key in dict(box["by_league"]):
        assert key.startswith("league:"), f"🔴 `{key}` — 리그 열쇠 꼴이 아니다"
        assert key in known, (
            f"🔴 `{key}` 가 `config/competitions.yaml` 의 `keys` 에 없다 — "
            f"`comp_kind` 가 이 열쇠를 낼 수 없어 표가 영구히 안 붙는다")


def test_md8_문지기가_site_질의를_버리지_않는다() -> None:
    """🔴🔴 **실사고 2026-10-17(우라와 두 번째)** — 표가 붙고 robots 까지 확인
    했는데 **`site:` 질의가 한 건도 안 던져졌다**.

    §12-b(`llm.query_ok`)가 *"사이트 연산자 금지"* 라서 ②③ 문지기가 **전부**
    버렸다. 🔴 그런데 ⑤-b3 2단은 **같은 꼴을 던지고 있었다** — 거기서는 문지기를
    **먼저** 통과시키고 `site:` 를 **그 뒤에** 붙인다. 즉 순서가 달랐다.

    🔴 그래서 ②③ 문지기는 접두를 떼고 **알맹이**를 §12-b 로 잰다.
    ⚠️ 규칙은 걷지 않는다 — **연도·따옴표·낱말 수는 그대로 걸려야 한다**.
    """
    from app.core.stages.s3_docs import gate_ok

    #  ① 좁힌 질의는 **통과한다**(이것이 안 되면 매체 표가 죽은 코드다 · #2)
    for q in ("site:soccer-king.jp 浦和レッズ 先発予想",
              "site:soccer-king.jp Mito Hollyhock predicted lineup"):
        ok, why = gate_ok(q)
        assert ok, f"🔴 문지기가 좁힌 질의를 막는다 — {q!r} · {why}"
        assert "site:" in why, f"🔴 좁힌 사실을 사유에 안 적었다(#3) — {why}"

    #  ② §12-b 는 **알맹이에 그대로** 걸린다(연도·낱말 수)
    for q, mark in (("site:soccer-king.jp 浦和 2026 先発", "연도"),
                    ("site:soccer-king.jp " + " ".join(["語"] * 9), "낱말 수")):
        ok, _why = gate_ok(q)
        assert not ok, f"🔴 {mark} 규칙이 `site:` 뒤에서 풀렸다 — {q!r}"

    #  ③ **알맹이가 없으면** 통과하지 않는다(호스트만 던지면 포털 첫 화면이다)
    ok, _why = gate_ok("site:soccer-king.jp")
    assert not ok, "🔴 호스트만 있는 질의가 통과한다 — 그 경기 글이 아니다"


def test_md9_좁힌_질의는_확인된_매체에서만_나온다() -> None:
    """🔴 ② `site:` 를 붙이는 곳은 **robots 를 확인한 목록**뿐이어야 한다(#4).

    ⚠️ 문지기가 접두를 받아 주므로, 만드는 쪽이 느슨해지면 **지어낸 매체로
       좁힌 0건**이 된다. 🔴 그래서 `_llm_queries` 안에서 `site_queries` 의 첫
       인자가 `check_hosts` 의 반환값인지 **꼴로** 본다.
    """
    import ast
    from app.core.stages import s3_docs

    tree = ast.parse(pathlib.Path(s3_docs.__file__).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "_llm_queries")

    #  `ok, _ = await check_hosts(...)` 로 받은 **그 이름**을 쓴다
    got = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
           and isinstance(n.func, ast.Attribute) and n.func.attr == "check_hosts"]
    assert got, "🔴 `check_hosts` 를 안 부른다 — robots 확인 없이 좁힌다(#4)"

    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "site_queries"]
    assert calls, "🔴 `site_queries` 를 안 부른다 — 표가 질의에 닿지 않는다(#2)"
    for one in calls:
        first = one.args[0] if one.args else None
        assert isinstance(first, ast.Name) and first.id == "ok", (
            "🔴 `site_queries` 의 첫 인자가 `check_hosts` 가 돌려준 `ok` 가 아니다 "
            "— 확인 안 된 매체로 좁힐 수 있다")
