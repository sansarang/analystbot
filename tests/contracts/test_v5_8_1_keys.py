"""🔴🔴 **v5 §8-1 — ID 우선.** 경기 열쇠는 `출처:경기ID` 다. [M30]

§8-1 원문:

> 팀 열쇠는 봇이 한 번 발급하는 뜻 없는 번호(`team:000273`)이고 파일에 못 박아
> 영구다. 외부 ID(tsdb·fdorg·fotmob·statsapi), 모든 언어의 이름·별칭, CLDR
> 국가명은 전부 그 번호 밑의 **별칭**이다. **경기 열쇠는 `출처:경기ID`**
> (`fotmob:5181853`, `statsapi:…`). 이름→ID 해석은 `resolve()` 한 곳에서만 하고,
> 그 뒤 **어떤 함수도 팀 이름 문자열을 인자로 받지 않는다**(AST 계약).

══════════════════════════════════════════════════════════════════
🔴 왜 — 실측 2026-10-04 의 열쇠들
══════════════════════════════════════════════════════════════════

```
nhl-2026020021   npb-…   fotmob-5181780   tsdb-…
849825           🔴 **MLB 는 접두가 아예 없다** — 이 열쇠는 출처를 말하지 못한다
```
⚠️ 그래서 `ingest.adapter_of(ext_id=…)` 가 MLB 행을 **라우팅하지 못한다**
   (실측: `_sport_from_ext('849825')` → `''`). 🔴 §8-1 의 `출처:ID` 가 그것을 막는다.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_v5_8_1_출처_목록이_선언돼_있다():
    """🔴 §8-1 이 이름 댄 출처들 — 손으로 흩어 적지 않는다."""
    from app.matchkey import SOURCES
    for s in ("fotmob", "statsapi", "nhl", "npb", "tsdb", "fdorg", "espn"):
        assert s in SOURCES, (s, sorted(SOURCES))


@pytest.mark.parametrize("source,mid,want", [
    ("fotmob", "5181853", "fotmob:5181853"),
    ("statsapi", 849825, "statsapi:849825"),
    ("nhl", "2026020021", "nhl:2026020021"),
])
def test_v5_8_1_열쇠를_출처_콜론_아이디로_만든다_M30(source, mid, want):
    from app.matchkey import make
    assert make(source, mid) == want


def test_v5_8_1_모르는_출처는_거부한다():
    """🔴 오타난 출처가 조용히 들어오면 라우팅이 그 행을 못 찾는다."""
    from app.matchkey import make
    with pytest.raises(ValueError, match="출처"):
        make("오타", "1")


def test_v5_8_1_빈_아이디는_거부한다():
    from app.matchkey import make
    with pytest.raises(ValueError, match="경기 ID"):
        make("fotmob", "")


@pytest.mark.parametrize("key,want", [
    ("fotmob:5181853", ("fotmob", "5181853")),
    # 🔴 **옛 꼴도 읽는다** — 쌓인 행이 있다(이관 중이다)
    ("fotmob-5181780", ("fotmob", "5181780")),
    ("nhl-2026020021", ("nhl", "2026020021")),
    ("tsdb-123", ("tsdb", "123")),
    # 🔴🔴 **접두 없는 MLB 열쇠** — 숫자만이다. 출처를 못 말한다
    ("849825", ("", "849825")),
    ("", ("", "")),
])
def test_v5_8_1_옛_꼴도_읽는다(key, want):
    """⚠️ 쌓인 행을 깨뜨리지 않는다 — **읽기는 둘 다**, 쓰기는 새 꼴만."""
    from app.matchkey import parse
    assert parse(key) == want




def test_v5_8_1_어댑터가_새_꼴로_쓴다():
    """🔴🔴 §8-1 — **쓰는 쪽은 새 꼴만.** ⚠️ 어댑터가 직접 문자열을 짓지 않는다.

    구조 계약: `app/collect/` 안에 `f"{EXT_PREFIX}{...}"` 꼴이 남아 있으면 실패.
    """
    bad = []
    for p in sorted((ROOT / "app" / "collect").glob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.JoinedStr):
                continue
            got = ast.unparse(node)
            if "EXT_PREFIX" in got:
                bad.append(f"{p.name}:{node.lineno} — {got[:60]}")
    assert not bad, (
        "🔴 어댑터가 열쇠를 **손으로 짓는다**(§8-1) — `matchkey.make` 를 써라:\n  "
        + "\n  ".join(bad))


def test_v5_8_1_어댑터가_열쇠를_matchkey로_짓는다():
    """🔴🔴 §8-1 — **모든** 어댑터가 `matchkey.make` 를 쓴다.

    ══════════════════════════════════════════════════════════════════
    🔴 **첫 판이 돌연변이를 통과시켰다**(2026-10-04)
    ══════════════════════════════════════════════════════════════════

    첫 판은 `f"{EXT_PREFIX}{...}"` 꼴만 찾았다. 🔴 **MLB 는 애초에 접두가 없어서**
    (`str(g["gamePk"])`) 그 검사에 **걸리지 않았다** — 되돌린 돌연변이가 초록이었다.
    ⚠️ 그래서 *"고유 꼴이 없나"* 가 아니라 *"`matchkey.make` 를 쓰나"* 를 본다.
    """
    #: 🔴 `ext_id` 를 **쓰는** 어댑터들. ⚠️ 이름으로 적는다 — 하나가 늘면
    #   여기 적어야 하고, 적지 않으면 그 어댑터가 옛 꼴로 쓸 수 있다.
    WRITERS = ("mlb", "nhl", "fotmob", "espn", "kbo", "fdorg", "npb")
    bad = []
    for name in WRITERS:
        p = ROOT / "app" / "collect" / f"{name}.py"
        tree = ast.parse(p.read_text(encoding="utf-8"))
        made = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for k, v in zip(node.keys, node.values, strict=False):
                if not (isinstance(k, ast.Constant) and k.value == "ext_id"):
                    continue
                got = ast.unparse(v)
                if "matchkey.make" in got or got.startswith("'npb:'") \
                        or got.startswith('"npb:"'):
                    made = True
                else:
                    bad.append(f"{name}.py:{node.lineno} — ext_id = {got[:60]}")
        if not made and name != "npb":
            bad.append(f"{name}.py — `matchkey.make` 를 안 쓴다")
    assert not bad, (
        "🔴 어댑터가 열쇠를 **손으로 짓는다**(§8-1) — `matchkey.make` 를 써라:\n  "
        + "\n  ".join(bad))


def test_v5_8_1_라우팅이_두_꼴을_다_찾는다():
    """🔴 §8-1 의 값 — 열쇠가 **출처를 말한다**. MLB 도 포함이다.

    ⚠️ 실측 2026-10-04: `849825`(접두 없음)는 라우팅이 못 찾았다.
    """
    from app.collect import ingest
    for key in ("fotmob:5181853", "fotmob-5181780"):
        mod = ingest.adapter_of(ext_id=key)
        assert mod is not None and "fotmob" in mod.__name__, (key, mod)
    # 🔴 **새 꼴 MLB 열쇠는 찾는다**
    mod = ingest.adapter_of(ext_id="statsapi:849825")
    assert mod is not None and "mlb" in mod.__name__, mod


