"""🔴🔴 **v5 §8-4 — 명단 소스 신뢰.** TheSportsDB 는 명단·리그 판정에 안 쓴다. [#7]

§8-4 원문:

> TheSportsDB 는 **명단·리그 판정에 쓰지 않는다**(잘림·거짓 명단).
> 팀 검색(`searchteams.php?t=`)**만 별칭 보조.**
> 명단은 MLB statsapi·NHL·football-data·공식 사이트·54팀 YAML. [#7]

══════════════════════════════════════════════════════════════════
🔴 왜 — 실측 2026-10-03 이 **거짓 명단**을 받았다
══════════════════════════════════════════════════════════════════

```
search_all_teams.php?l=Japanese J1 League  → **10팀**(J1 은 20팀이다)
all_leagues.php                            → **10리그**
lookup_all_teams.php?id=4633(J1)·4830(KBO)·4424(MLB)
   → 🔴 **셋 다 똑같은 영국 2부 24팀** (`Wigan Athletic`·`Blackpool`…)
```
⚠️ 24팀이 **돌아온다**는 사실만 보고 썼다면 봇이 **거짓 명단**으로 리그를
   판정했을 것이다. 상태값(200 OK·건수)은 증거가 아니다(CLAUDE.md #4).
"""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _code_only(path: pathlib.Path) -> str:
    """🔴 D46 — 독스트링·주석을 뺀 **코드만**."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(
                    first.value, ast.Constant) and isinstance(
                    first.value.value, str):
                node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_v5_8_4_명단을_tsdb에서_받지_않는다():
    """🔴🔴 §8-4 — `search_all_teams` 가 **코드에 0건**이어야 한다."""
    import re as _re
    bad = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        code = _code_only(p)
        for pat in ("search_all_teams", "all_leagues.php",
                    "lookup_all_teams"):
            # 🔴🔴 **D46** — 금지어를 *설명하는* 것과 **주소로 부르는** 것은 다르다.
            #    ⚠️ 독스트링은 이미 걷었지만 **사유 문장**(사용자에게 보이는
            #       f-string)에도 그 이름이 나온다 — *"`lookup_all_teams` 는 id 를
            #       무시한다"* 는 그 설명이고 호출이 아니다.
            #    🔴 그래서 **주소 꼴**(`thesportsdb…/<그 파일>`)만 본다.
            near = _re.escape(pat)
            if _re.search("thesportsdb[^\n]{0,80}" + near, code):
                bad.append(f"{p.relative_to(ROOT)} — `{pat}` 주소")
    assert not bad, (
        "🔴 tsdb **명단** 주소가 코드에 남아 있다(§8-4 · #7) — 잘리고 거짓 명단을 "
        "준다:\n  " + "\n  ".join(bad))


def test_v5_8_4_리그_명부가_tsdb를_명단_출처로_안_쓴다():
    """🔴 `teams_from: tsdb:…` 가 **한 줄도 없어야** 한다."""
    from app import rules
    bad = []
    for lg in (rules._load("config/leagues.yaml").get("leagues") or []):
        for src in (lg.get("teams_from") or []):
            if str(src).startswith("tsdb:"):
                bad.append(f"{lg.get('key')} — {src}")
    assert not bad, (
        "🔴 리그 명부가 명단을 tsdb 에서 받는다(§8-4):\n  " + "\n  ".join(bad))


def test_v5_8_4_팀_검색은_별칭_보조로만_남는다():
    """🔴 §8-4 — *"팀 검색(`searchteams.php?t=`)**만** 별칭 보조."*

    ⚠️ 그 길은 **남는다**(현지 표기를 준다 · `strTeamAlternate` → `柏レイソル`).
       🔴 그런데 **리그를 정하지 않는다** — 그것이 §8-4 가 막는 것이다.
    """
    from app import resolve
    assert "searchteams.php" in resolve.ASK_TEAM
    code = _code_only(ROOT / "app" / "resolve.py")
    # 🔴 ④단이 `_fill`(리그 확정)을 부르면 안 된다
    tree = ast.parse(code)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "_by_ask")
    called = {ast.unparse(x.func) for x in ast.walk(fn)
              if isinstance(x, ast.Call)}
    assert "_fill" not in called, (
        "🔴 ④단(팀 직접 조회)이 **리그를 확정한다**(`_fill`) — §8-4 가 그것을 "
        "막는다. 현지 표기만 받고 리그는 ②·③에 맡겨라")


def test_v5_8_4_팀_조회가_리그를_안_정한다():
    """🔴 값으로 확인한다 — 구조 계약만으로는 못 잡는다."""
    import asyncio

    from app.resolve import Resolved, _by_ask

    class _Net:
        async def get(self, url, **kw):
            class _F:
                ok = True
                dead = False
                reason = ""
                #: 🔴 실측 응답 꼴(2026-10-03) — 리그와 현지 표기를 함께 준다
                text = ('{"teams":[{"strTeam":"Kashiwa Reysol",'
                        '"strLeague":"Japanese J1 League",'
                        '"strTeamAlternate":"\\u67cf\\u30ec\\u30a4\\u30bd\\u30eb"}]}')
            f = _F()
            f.url = url
            return f

    got = Resolved()
    done = asyncio.run(_by_ask("Kashiwa Reysol", got, net=_Net()))
    # 🔴 **리그를 정하지 않았다** — 사다리가 멈추지 않는다
    assert done is False, "🔴 ④단이 리그를 확정했다(§8-4 위반)"
    assert got.league == "", got.league
    # ✅ 그런데 **현지 표기는 받았다**(별칭 보조는 남는다)
    #    🔴 `local` 이 아니라 `ask_local` 이다 — `local` 은 **리그·언어를 안 뒤에**
    #       `_local` 이 채운다. ⚠️ 리그를 모르면 어느 언어가 현지어인지도 모르고,
    #       그때 표기를 붙이면 `Croatia` 에 포르투갈어가 달라붙는다(실측 2026-10-03).
    assert got.ask_local == "柏レイソル", got.ask_local
    assert got.local == "", "🔴 리그를 모르는데 현지 표기를 **썼다**"
    assert any("§8-4" in x or "별칭" in x or "현지 표기" in x
               for x in got.steps), got.steps


def test_v5_8_4_명단_출처가_선언에_적혀_있다():
    """🔴 §8-4 가 이름 댄 것만 명단 출처다 — 그 목록이 코드에 있어야 한다."""
    from app.league_index import ROSTER_SOURCES
    assert "adapter" in ROSTER_SOURCES and "url" in ROSTER_SOURCES
    assert "fdorg" in ROSTER_SOURCES
    assert "tsdb" not in ROSTER_SOURCES, (
        "🔴 tsdb 가 명단 출처 목록에 있다(§8-4)")


def test_v5_8_4_거부도_오타도_사유를_남긴다():
    """#3 조용한 0 금지 — **거부**와 **오타**를 가르고 둘 다 이름으로 남긴다.

    ⚠️ 첫 판은 `tsdb:` **하나만** 쳤다. 그래서 *"모르는 꼴에 사유를 안 남긴다"*
       돌연변이가 **초록이었다** — 그 가지를 밟지 않았다.
    """
    import asyncio

    from app import league_index as LI
    # ── ① 거부(§8-4)
    got, why = asyncio.run(LI.roster_from("tsdb:Japanese J1 League", net=None))
    assert got == [], got
    assert "§8-4" in why, why
    # ── ② 🔴 **오타 꼴** — 조용히 0 이 되면 그 리그가 명단 없이 도는 것을 모른다
    got2, why2 = asyncio.run(LI.roster_from("tsbd:오타", net=None))
    assert got2 == [], got2
    assert str(why2 or "").strip(), "🔴 모르는 꼴에 사유가 없다"
    assert "모르는" in why2 and "tsbd" in why2, why2
    # ── ③ 빈 꼴도 터지지 않고 사유를 남긴다
    got3, why3 = asyncio.run(LI.roster_from("", net=None))
    assert got3 == [] and str(why3 or "").strip(), (got3, why3)
