"""🔴🔴 **v5 §8-1 — 쌓인 열쇠를 이관한다**(`849825` → `statsapi:849825`).

══════════════════════════════════════════════════════════════════
🔴 왜 이 계약이 생겼나 — **카드가 스스로 적었다**(실측 2026-10-04)
══════════════════════════════════════════════════════════════════

MLB 밀워키 vs 샌디에이고 카드:

```
· 세포 열쇠: ⚠️ 경기 열쇠가 **옛 꼴**이다(`849825`) — §8-1 은 `출처:경기ID` 를
  요구한다. 출처 `미상` · id `849825`  🔴 **출처를 못 읽어 깊이 소스를 고를 수 없다**
```

어댑터 **여덟 개 전부**가 이제 `matchkey.make` 를 쓴다. 그런데 `games` 46행이
**46/46 비표준**이었다 — 그 행들은 바뀌기 **전에** 쌓였다.

🔴 그래서 둘을 함께 막는다:
   ① 어댑터가 내는 행은 **반드시** 표준 꼴이다(`test_…어댑터가_표준_열쇠를_쓴다`)
   ② 쌓인 행은 **이관된다** — 리그 표에서 출처를 **계산한다**(손으로 적지 않는다)

⚠️ `UNIQUE(sport, ext_id)` 가 있다 — 이관이 **충돌을 만들면 그 행은 건너뛰고
   그 사실을 센다**(#3 조용한 0 금지). 조용히 지우지 않는다.
"""
from __future__ import annotations

def test_v5_8_1_출처를_리그에서_계산한다():
    """🔴 `리그 → 출처` 를 **손으로 적지 않는다** — 두 표를 겹쳐 얻는다.

    ⚠️ `ingest.ADAPTERS`(리그→모듈)와 `SOURCE_ADAPTERS`(출처→모듈)가 이미
       원본이다. 세 번째 표를 적으면 그것이 **사본**이고, 어댑터가 늘 때 한 발
       늦는다(CLAUDE.md #1).
    """
    from app import keymigrate
    from app.collect import ingest
    src = keymigrate.source_for(league="MLB", ext_id="849825")
    assert src == "statsapi", src
    # 🔴 **표에서 자란다** — 리그를 지우면 이 수가 줄어든다
    got = {lg: keymigrate.source_for(league=lg, ext_id="") for lg in ingest.ADAPTERS}
    assert all(got.values()), [k for k, v in got.items() if not v]


def test_v5_8_1_옛_접두도_읽는다():
    """`fotmob-5181780` 은 출처를 **이미 말하고 있다** — 그대로 쓴다."""
    from app import keymigrate
    assert keymigrate.source_for(league="", ext_id="fotmob-5181780") == "fotmob"


def test_v5_8_1_이관이_표준_꼴을_만든다():
    """🔴 이관 결과가 `matchkey.is_canonical` 을 **통과해야** 한다."""
    from app import keymigrate, matchkey
    new = keymigrate.canonical_for(league="NHL", ext_id="2026020123")
    assert new == "nhl:2026020123"
    assert matchkey.is_canonical(new)


def test_v5_8_1_출처를_모르면_건드리지_않는다():
    """🔴 **추측으로 접두를 붙이지 않는다**(#4) — 모르면 `""` 다.

    ⚠️ 리그가 `Friendlies` 처럼 표에 없고 열쇠도 맨숫자면 출처를 알 길이 없다.
       그때 아무 출처나 붙이면 라우팅이 **엉뚱한 어댑터**로 간다 — 0 보다 나쁘다.
    """
    from app import keymigrate
    assert keymigrate.canonical_for(league="대회명 미상", ext_id="12345") == ""
    assert keymigrate.source_for(league="Friendlies", ext_id="12345") == ""


def test_v5_8_1_이미_표준이면_그대로():
    from app import keymigrate
    assert keymigrate.canonical_for(league="MLB", ext_id="statsapi:849825") == ""


def test_v5_8_1_어댑터가_표준_열쇠를_쓴다():
    """🔴🔴 **쓰는 쪽**을 막는다 — 이관은 한 번이고, 다음 행은 안 틀려야 한다.

    ⚠️ 이 검사는 **어댑터 파일에서 자란다**(목록을 손으로 안 적는다):
       `app/collect/*.py` 안의 `"ext_id":` 줄은 **반드시** `matchkey.make(` 나
       이미 표준인 문자열이어야 한다.
    🔴 종전에 MLB 가 `g["gamePk"]` 를 **맨숫자로** 넣었고(실측 2026-10-04) 그
       한 줄이 깊이 라우팅을 통째로 막았다.
    """
    import pathlib
    import re
    bad = []
    for p in sorted(pathlib.Path("app/collect").glob("*.py")):
        for i, line in enumerate(p.read_text().splitlines(), 1):
            s = line.strip()
            if s.startswith("#") or '"ext_id":' not in s:
                continue
            val = s.split('"ext_id":', 1)[1]
            # 🔴 `matchkey.make(…)` 이거나 **출처 접두를 글자로 가진** 것만 통과
            if "matchkey.make(" in val or re.search(r'"[a-z]+:"', val):
                continue
            # ⚠️ **넘기는 곳은 짓는 곳이 아니다** — 실측 2026-10-04:
            #    `ingest.py:587` 이 `r["ext_id"]` 를 그대로 전달한다. 그 값은
            #    이 검사를 **이미 통과한** 열쇠다. 🔴 짓는 곳만 본다.
            if '["ext_id"]' in val or '.get("ext_id")' in val:
                continue
            bad.append(f"{p}:{i}  {s[:80]}")
    assert not bad, (
        "🔴 §8-1 — 어댑터가 **맨숫자 열쇠**를 쓴다(그러면 출처를 못 읽어 깊이 "
        f"소스가 통째로 안 돈다):\n  " + "\n  ".join(bad))


def test_v5_8_1_이관이_충돌을_세고_건너뛴다():
    """⚠️ `UNIQUE(sport, ext_id)` — 표준 꼴이 **이미 있으면** 그 행은 못 바꾼다.

    🔴 그때 **조용히 지우지 않는다** — 건너뛰고 수를 돌려준다(#3).
    """
    from app import keymigrate
    rows = [{"sport": "baseball", "league": "MLB", "ext_id": "849825"},
            {"sport": "baseball", "league": "MLB", "ext_id": "statsapi:849825"},
            {"sport": "soccer", "league": "Friendlies", "ext_id": "6280453"}]
    plan = keymigrate.plan(rows)
    assert plan.changes == []           # 🔴 충돌이라 **안 바꾼다**
    assert plan.clashes == 1
    assert plan.unknown == 1            # Friendlies — 출처를 모른다
    assert plan.already == 1
    assert "충돌 1" in plan.line() and "출처 미상 1" in plan.line()


def test_v5_8_1_이관이_바꿀_것을_센다():
    from app import keymigrate
    plan = keymigrate.plan([
        {"sport": "baseball", "league": "MLB", "ext_id": "849825"},
        {"sport": "hockey", "league": "NHL", "ext_id": "2026020123"}])
    assert plan.changes == [("baseball", "849825", "statsapi:849825"),
                            ("hockey", "2026020123", "nhl:2026020123")]
    assert plan.clashes == 0 and plan.unknown == 0


def test_v5_8_1_이관이_기동에_이어져_있다():
    """🔴🔴 **안 이어진 이관은 없는 이관이다**(CLAUDE.md #2).

    ⚠️ `scheduler.main` 이 스키마를 적용하는 그 자리에서 **한 번** 돈다.

    ══════════════════════════════════════════════════════════════════
    🔴 **첫 판이 돌연변이를 통과시켰다**(2026-10-04)
    ══════════════════════════════════════════════════════════════════

    `await keymigrate.run(pool)` → `keymigrate.plan([])` 로 바꿔도 **초록이었다** —
    내 계약이 `"keymigrate" in src` 라는 **낱말**만 봤고, 그 낱말은 남아 있었다.
    🔴 D46 — **호출 꼴**을 본다: `run` 을 `pool` 로 **await** 하나.
    ⚠️ 글자 비교가 아니라 AST 다 — 줄바꿈·공백에 안 깨진다.
    """
    import ast
    import inspect
    import textwrap

    from app import scheduler
    tree = ast.parse(textwrap.dedent(inspect.getsource(scheduler.main)))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "run"
             and isinstance(n.func.value, ast.Name)
             and n.func.value.id == "keymigrate"]
    assert calls, (
        "🔴 이관 함수를 만들어 두고 **부르는 곳이 없다** — 쌓인 46행이 그대로 "
        "남고 카드는 계속 '옛 꼴'을 적는다(CLAUDE.md #2)")
    # 🔴 **await** 해야 돈다 — 코루틴을 만들어 버리면 아무 일도 안 난다
    awaited = [n for n in ast.walk(tree)
               if isinstance(n, ast.Await) and n.value in calls]
    assert awaited, "🔴 `keymigrate.run` 을 **await 하지 않는다** — 안 돈다"
    # ⚠️ 그리고 **그 풀**을 줘야 한다(빈 목록을 주면 아무 행도 못 본다)
    assert [a for a in calls[0].args if isinstance(a, ast.Name)], (
        "🔴 `run()` 에 풀을 안 넘긴다 — 볼 행이 없다")


def test_v5_8_1_가리키는_표를_DB_에_묻는다():
    """🔴🔴 **목록을 손으로 적지 않는다** — 내가 적었다가 **틀렸다**.

    ══════════════════════════════════════════════════════════════════
    🔴 실측 2026-10-04 — 지어낸 세 줄이 트랜잭션을 죽였다
    ══════════════════════════════════════════════════════════════════

    `REFERRING = (("ledger","match_key"), ("sufficiency","match_key"),
    ("learned_names","match_key"))` 를 적어 두었다. 실물:

    ```
    ledger.match_key       🔴 없다 (`ledger` 는 `game_id` 정수 FK)
    learned_names          🔴 표 자체가 없다
    → InFailedSQLTransactionError: current transaction is aborted
    ```

    ⚠️ 트랜잭션 안에서는 `try/except` 가 못 구한다 — 실패 뒤 문장이 전부 무시된다.
    🔴 그래서 **DB 에 묻고**(information_schema) 있는 것만 고친다.
    """
    import asyncio
    import pathlib

    from app import keymigrate
    from tests._helpers import strip_docs
    # 🔴 손으로 적은 표가 **없어야** 한다.
    #    ⚠️ D46 — **독스트링·주석을 뺀 코드만** 본다. 위 독스트링이 틀린 목록을
    #       *설명하고* 있고, 그것은 코드가 그것을 *부르는* 것과 다르다.
    body = strip_docs(pathlib.Path("app/keymigrate.py").read_text())
    for name in ("ledger", "learned_names", "sufficiency"):
        assert name not in body, (
            f"🔴 표 이름(`{name}`)을 **코드에 박았다** — DB 가 원본이다"
            f"(`referring`). 내가 적었다가 틀렸고 트랜잭션이 죽었다.")

    seen = {}

    class _C:
        async def fetch(self, q, *a):
            seen["q"] = " ".join(q.split()); seen["a"] = a
            return [{"table_name": "games", "column_name": "ext_id"},
                    {"table_name": "ledger", "column_name": "match_key"}]

    got = asyncio.run(keymigrate.referring(_C()))
    assert "information_schema.columns" in seen["q"], seen["q"]
    # 🔴 열쇠 **이름 규약**을 질의가 들고 간다
    assert list(seen["a"][0]) == list(keymigrate.KEY_COLUMN_NAMES)
    # ⚠️ `games.ext_id` 는 **집**이다 — 가리키는 것이 아니다
    assert got == [("ledger", "match_key")], got


def test_v5_8_1_가리키는_칸이_실제로_없다():
    """🔴 **지금 빈 목록인 까닭을 기록한다** — 조용한 0 이 아니다(#3).

    ⚠️ 뒷날 누가 `ledger.match_key` 같은 **글자 열쇠 칸**을 더하면 이 계약이
       빨개지고, 그때 이관이 그 칸을 함께 바꿔야 한다는 것을 알려 준다.
    """
    import pathlib
    import re
    from app import keymigrate
    sql = pathlib.Path("db/schema.sql").read_text()
    found = set()
    for name in keymigrate.KEY_COLUMN_NAMES:
        for m in re.finditer(rf"\b{name}\s+(TEXT|VARCHAR)", sql, re.I):
            found.add(name)
    # 🔴 `games.ext_id` 하나다 — 나머지는 `game_id` 정수 FK 로 잇는다
    assert found == {"ext_id"}, (
        f"🔴 글자 열쇠 칸이 늘었다({sorted(found)}) — `keymigrate.referring` 이 "
        f"그것을 함께 바꾸는지 확인하라")


def test_v5_8_1_없는_표에_SQL_을_안_보낸다():
    """🔴🔴 **보내기 전에 고른다** — 트랜잭션이 죽으면 열쇠 절반만 바뀐다."""
    import asyncio

    from app import keymigrate

    class _C:
        def __init__(self): self.sql = []
        async def fetch(self, q, *a):
            if "information_schema" in q:
                return []                      # 🔴 가리키는 칸이 **없다**
            return [{"sport": "baseball", "league": "MLB", "ext_id": "849825"}]
        async def execute(self, q, *a): self.sql.append((" ".join(q.split()), a))
        def transaction(self): return self
        async def __aenter__(self): return self
        async def __aexit__(self, *e): return False

    class _P:
        def __init__(self): self.c = _C()
        def acquire(self): return self.c

    pool = _P()
    got = asyncio.run(keymigrate.run(pool))
    assert got.changes == [("baseball", "849825", "statsapi:849825")]
    assert got.referring == []
    # 🔴 `games` 하나만 고친다 — 없는 표에 던지지 않는다
    assert len(pool.c.sql) == 1, pool.c.sql
    q, a = pool.c.sql[0]
    assert "UPDATE games SET ext_id" in q
    assert a == ("statsapi:849825", "baseball", "849825"), a


def test_v5_8_1_있는_표는_함께_바꾼다():
    """⚠️ 있으면 **반드시** 함께다 — 안 하면 채점이 그 경기를 못 찾는다."""
    import asyncio

    from app import keymigrate

    class _C:
        def __init__(self): self.sql = []
        async def fetch(self, q, *a):
            if "information_schema" in q:
                return [{"table_name": "ledger", "column_name": "match_key"}]
            return [{"sport": "baseball", "league": "MLB", "ext_id": "849825"}]
        async def execute(self, q, *a): self.sql.append((" ".join(q.split()), a))
        def transaction(self): return self
        async def __aenter__(self): return self
        async def __aexit__(self, *e): return False

    class _P:
        def __init__(self): self.c = _C()
        def acquire(self): return self.c

    pool = _P()
    got = asyncio.run(keymigrate.run(pool))
    assert got.referring == [("ledger", "match_key")]
    assert any("UPDATE ledger SET match_key" in q for q, _ in pool.c.sql), pool.c.sql
    for q, a in pool.c.sql:
        assert "statsapi:849825" in a and "849825" in a, (q, a)


def test_v5_8_1_바꿀_것이_없으면_SQL_을_안_보낸다():
    """🔴 멱등이다 — 기동마다 도는데 쓸 일이 없으면 **한 줄도** 안 보낸다."""
    import asyncio

    from app import keymigrate

    class _C:
        def __init__(self): self.sql = []
        async def fetch(self, q, *a):
            if "information_schema" in q:
                return []
            return [{"sport": "baseball", "league": "MLB",
                     "ext_id": "statsapi:849825"}]
        async def execute(self, q, *a): self.sql.append(q)
        def transaction(self): return self
        async def __aenter__(self): return self
        async def __aexit__(self, *e): return False

    class _P:
        def __init__(self): self.c = _C()
        def acquire(self): return self.c

    pool = _P()
    got = asyncio.run(keymigrate.run(pool))
    assert got.changes == [] and got.already == 1
    assert pool.c.sql == []
