"""🔴🔴 **순위표(H1) 계약** — 지시 2026-10-14 *"순위 및 승률을 가지고 와서 의심
단계를 만들어봐라"*.

지키는 것:
  ST1 원천이 **하나**다 — `standings` 는 `domesticelo.load` 를 쓴다(사본 금지)
  ST2 **누설 금지** — `table_at(day)` 는 그 날짜 **앞** 경기만 쌓는다
  ST3 유효 목록은 **설정**에서 온다 — 코드에 `H1`·`J1` 을 박지 않는다
  ST4 두 팀은 **한 표**에서 온다 — 다른 대회 표를 섞어 견주지 않는다
  ST5 **묶음을 실제로 센다** — `_doubt_of` 가 `bad=[]` 로 박혀 있지 않다
  ST6 못 쟨 것은 **이름으로** 남긴다(#3 조용한 0 금지)
  ST7 적합과 운영이 **같은 깃발**을 세운다(표본 대조)
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _code_only(rel: str) -> str:
    """🔴 D46 — 독스트링·주석을 뺀 **코드만** 본다."""
    tree = ast.parse(_src(rel))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if isinstance(node, (ast.Str, ast.Constant)):
            continue
        out.append(type(node).__name__)
    return _strip_docs(_src(rel))


def _strip_docs(said: str) -> str:
    tree = ast.parse(said)
    drop: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = list(getattr(node, "body", []) or [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                one = body[0]
                for ln in range(one.lineno, (one.end_lineno or one.lineno) + 1):
                    drop.add(ln)
    rows = said.splitlines()
    return "\n".join(x for i, x in enumerate(rows, 1)
                     if i not in drop and not x.strip().startswith("#"))


def test_st1_one_source() -> None:
    """ST1 — 덤프를 **직접** 열지 않는다. `domesticelo` 를 통한다."""
    code = _strip_docs(_src("app/core/standings.py"))
    assert "domesticelo" in code, "ST1 — 원천이 `domesticelo` 여야 한다"
    assert "replay_" not in code, (
        "ST1 🔴 `standings` 가 덤프 파일 이름을 **직접** 들었다 — 원천이 둘이 된다. "
        "`domesticelo.load()` 를 쓴다(사본 금지)")
    assert "json.loads" not in code and "glob(" not in code, (
        "ST1 🔴 `standings` 가 파일을 직접 읽는다 — `domesticelo` 를 통한다")


def test_st2_no_leak() -> None:
    """ST2 — 그 날짜 **앞**만. `>=` 로 잘라야 그 경기 자신이 안 들어간다."""
    code = _strip_docs(_src("app/core/standings.py"))
    assert 'd >= str(day)' in code, (
        "ST2 🔴🔴 누설 — `table_at` 이 `day` **이상**을 빼는 줄이 없다. "
        "그 경기 결과가 그 경기의 순위표에 들어가면 미래를 보는 것이다(C11)")


def test_st2b_leak_measured() -> None:
    """ST2b — **실제로** 잘리는지 돌려 본다(글자만 믿지 않는다)."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core import standings
    early, _w1 = standings.table_at("2025-01-01")
    late, _w2 = standings.table_at("2026-10-14")
    n_e = sum(v.n for v in early.values())
    n_l = sum(v.n for v in late.values())
    assert n_e < n_l, (
        f"ST2b 🔴 날짜를 앞으로 당겼는데 경기 수가 안 줄었다({n_e} ↔ {n_l}) — "
        "자르는 줄이 안 듣는다")


def test_st3_valid_from_config() -> None:
    """ST3 — 유효 목록은 `config/doubt_vars.yaml` 에서 온다."""
    code = _strip_docs(_src("app/core/doubt.py"))
    assert "doubt_vars.yaml" in code, (
        "ST3 🔴 `doubt.valid()` 가 설정을 안 읽는다")
    pipe = _strip_docs(_src("app/core/pipeline.py"))
    i = pipe.find("def _bad_doubts")
    j = pipe.find("def _j1_of")
    body = pipe[i:j] if i >= 0 and j > i else ""
    assert body, "ST3 🔴 `_bad_doubts` 가 없다"
    assert "_db2.valid()" in body, (
        "ST3 🔴 `_bad_doubts` 가 유효 목록을 **설정에서** 안 받는다")


def test_st4_one_table() -> None:
    """ST4 — 섞어 견주지 않는다. 짝으로 찾는 함수가 있어야 한다."""
    code = _strip_docs(_src("app/core/standings.py"))
    assert "def pair_of(" in code, (
        "ST4 🔴 두 팀을 **한 표**에서 찾는 `pair_of` 가 없다 — 팀별로 따로 찾으면 "
        "ACLE 표 1.92 ↔ KL1 표 1.42 처럼 **다른 대회 자**를 견준다(실측 10-14)")
    assert "def h1_of(" in code and "pair_of(" in code.split("def h1_of(")[1], (
        "ST4 🔴 `h1_of` 가 `pair_of` 를 안 쓴다")


def test_st5_bucket_is_counted() -> None:
    """ST5 — `bad=[]` 로 박혀 있으면 묶음 0 만 읽는다(10-14 사고)."""
    pipe = _strip_depth = _strip_docs(_src("app/core/pipeline.py"))
    i = pipe.find("def _doubt_of")
    j = pipe.find("def _bad_doubts")
    body = pipe[i:j] if i >= 0 and j > i else ""
    assert body, "ST5 🔴 `_doubt_of` 가 없다"
    assert "bad=[]" not in body.replace(" ", ""), (
        "ST5 🔴🔴 `_doubt_of` 가 `bad=[]` 를 넘긴다 — 의심 단계가 **빈손으로** "
        "돈다. 10-14 슬레이트 10경기가 전부 `유효 불리 의심 없다` 로 지나갔다")
    assert "_bad_doubts(" in body, "ST5 🔴 묶음을 세는 곳을 안 부른다"


def test_st6_unmeasured_is_named() -> None:
    """ST6 — 못 쟨 것은 이름으로. J1 은 보드가 없으면 ⬜ 로 적는다."""
    pipe = _src("app/core/pipeline.py")
    i = pipe.find("def _bad_doubts")
    j = pipe.find("def _j1_of")
    body = pipe[i:j] if i >= 0 and j > i else ""
    assert "셀 수 없다" in body and "걸리지 않은 것이 아니다" in body, (
        "ST6 🔴 J1 을 못 쟀을 때 *'걸리지 않았다'* 와 *'셀 수 없었다'* 를 "
        "가르지 않는다(#3 조용한 0 금지)")


def test_st7_fit_and_runtime_agree() -> None:
    """ST7 — 적합과 운영이 **같은 깃발**. 표본 60건을 대조한다."""
    import random
    import sys
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tools"))
    import replays
    from app.core import standings

    rows, _w = replays.load()
    rows = [r for r in rows if r.get("ours") and r.get("hit") is not None
            and r.get("hg") is not None]
    rows.sort(key=lambda r: str(r.get("day")))
    pts: dict = {}
    fit: dict = {}
    for r in rows:
        lg, se = str(r["league"]), str(r["season"])
        h, a = str(r["home"]), str(r["away"])
        ours = [float(x) for x in r["ours"]]
        pick = max(range(3), key=lambda i: ours[i])
        side = "home" if pick == 0 else ("away" if pick == 2 else "")
        A = pts.get((lg, se, h)) or {"p": 0, "n": 0}
        B = pts.get((lg, se, a)) or {"p": 0, "n": 0}
        if side and A["n"] >= standings.MIN_GAMES and B["n"] >= standings.MIN_GAMES:
            ppg = {"home": A["p"] / A["n"], "away": B["p"] / B["n"]}
            other = "away" if side == "home" else "home"
            fit[(lg, str(r["day"]), h, a, side)] = ppg[side] < ppg[other]
        hg, ag = int(r["hg"]), int(r["ag"])
        for team, ish in ((h, True), (a, False)):
            p = 3 if ((hg > ag) == ish and hg != ag) else (1 if hg == ag else 0)
            one = pts.setdefault((lg, se, team), {"p": 0, "n": 0})
            one["p"] += p
            one["n"] += 1
    assert len(fit) > 500, f"ST7 🔴 적합 깃발이 {len(fit)}개뿐이다 — 덤프를 확인하라"
    random.seed(11)
    keys = random.sample(sorted(fit), 60)
    bad: list = []
    for lg, day, h, a, side in keys:
        got = standings.h1_of(home=h, away=a, pick=side, day=day, league=lg)
        if got.state and got.bad() != fit[(lg, day, h, a, side)]:
            bad.append((lg, day, h, a, fit[(lg, day, h, a, side)], got.bad()))
    assert not bad, (
        f"ST7 🔴🔴 적합과 운영의 H1 깃발이 **{len(bad)}건** 다르다 — 같은 팀 같은 "
        f"날짜면 같은 값이어야 한다. 보기 {bad[:3]}")
