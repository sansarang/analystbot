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


def test_v5_8_1_옛_꼴을_이름으로_센다():
    """🔴 #3 조용한 0 금지 — 이관이 끝났는지 **숫자로** 봐야 한다."""
    from app.matchkey import is_canonical
    assert is_canonical("fotmob:5181853")
    assert not is_canonical("fotmob-5181780")
    assert not is_canonical("849825")
    assert not is_canonical("")


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


def test_v5_8_1_팀_이름을_인자로_받는_함수가_늘지_않는다():
    """🔴🔴 §8-1 — *"어떤 함수도 팀 이름 문자열을 인자로 받지 않는다(AST 계약)."*

    ══════════════════════════════════════════════════════════════════
    ⚠️ **한 번에 다 못 고친다 — 그래서 수를 잠근다**
    ══════════════════════════════════════════════════════════════════

    지금 `team: str` 을 받는 함수가 수십 개다. 🔴 그 전부를 열쇠로 바꾸는 것은
    이 조항 하나의 일이 아니다(검색어·귀속은 **이름을 써야 한다** — 기사에 ID 가
    없다 · 1~3단계의 "신원 vs 귀속" 구분).
    🔴 그래서 **지금 수를 못 박는다.** 늘면 빨개지고, 줄이면 그 수를 내려 적는다 —
       그것이 이 저장소가 쓰는 줄어드는 허용 목록이다.
    """
    hits = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for a in list(node.args.args) + list(node.args.kwonlyargs):
                if a.arg not in ("team", "opponent", "home", "away"):
                    continue
                ann = ast.unparse(a.annotation) if a.annotation else ""
                if "str" in ann:
                    hits.append(f"{p.relative_to(ROOT)}:{node.name}:{a.arg}")
    #: 🔴 **2026-10-04 실측 수.** ⚠️ 늘리지 않는다 — 줄이면 이 수를 내려 적는다.
    #   ⚠️ 내 첫 어림(104)이 틀렸고 **되감기 계약이 그 자리에서 알렸다** —
    #      목록이 거짓이 되기 전에 기계가 먼저 말했다.
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **81 → 83** — 지시서 §2 오픈월드 ⑥ 단 (2026-10-05)
    # ══════════════════════════════════════════════════════════════════
    #
    #  늘어난 둘: `resolve._by_openworld(team=, opponent=)`
    #
    #  ⚠️ §8-1 이 막는 것은 *"이름을 신원으로 쓰는 것"* 이다 — 함수마다 이름을
    #     받으면 그 함수가 **또 하나의 해석 지점**이 된다.
    #  🔴 그런데 ⑥ 단은 **해석 입구 자신**이다(`resolve.py`): 이름표가 그 이름을
    #     **못 풀었을 때만** 돌고, 받은 이름을 공개 페이지로 확인해 **열쇠를
    #     발급한다**(⑥-4). 열쇠가 아직 **없는** 자리이므로 이름 말고 넘길 것이
    #     없다.
    #  ⚠️ 그래서 올린다 — **까닭을 적고** 올린다(조용히 올리면 이 계약이 뜻을
    #     잃는다). 🔴 ⑥ 밖의 새 코드는 여전히 **열쇠**를 받아야 한다.
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **83 → 84** — 딥서치 재구축 §2 (지시서 2026-10-05)
    # ══════════════════════════════════════════════════════════════════
    #
    #  그 문서가 이 예외를 **명시로** 적었다:
    #
    #  > `{팀}` 은 별칭표의 **영어 짧은 표기**(열쇠 아님 — **질의는 글자**,
    #  > 출력 `team` 칸은 **열쇠 M48 그대로**). 대표팀은 CLDR 영어명.
    #
    #  ⚠️ 늘어난 자리는 `app/research/subtasks.py:_seed_of` 다 — 씨앗 **질의
    #     문자열**을 만든다. 🔴 검색 엔진에 열쇠(`team:000081`)를 던질 수는
    #     없다. 그래서 이 자리는 **글자를 받는 것이 설계**다.
    #  🔴 출력 쪽은 그대로 열쇠다: `Subtask.team_key` 가 `team:` 접두를 들고,
    #     §2 계약(`test_r2_하위마다_팀과_자리가_있다`)이 그것을 잠근다.
    BASELINE = 84
    assert len(hits) <= BASELINE, (
        f"🔴 팀 이름을 인자로 받는 자리가 **늘었다** {len(hits)} > {BASELINE}"
        f"(§8-1) — 새 코드는 **열쇠**를 받아라:\n  "
        + "\n  ".join(sorted(hits)[-12:]))
    if len(hits) < BASELINE:
        raise AssertionError(
            f"✅ {BASELINE} → {len(hits)} 로 **줄었다** — `BASELINE` 을 "
            f"{len(hits)} 로 내려 적어라(목록이 거짓이 되기 전에)")
