"""🔴🔴 **v5 §8-1 — 쌓인 경기 열쇠를 `출처:경기ID` 로 이관한다.**

══════════════════════════════════════════════════════════════════
🔴 왜 이 파일이 생겼나 — **카드가 스스로 말했다**(실측 2026-10-04)
══════════════════════════════════════════════════════════════════

MLB 밀워키 vs 샌디에이고 카드 한 줄:

```
· 세포 열쇠: ⚠️ 경기 열쇠가 **옛 꼴**이다(`849825`) — §8-1 은 `출처:경기ID` 를
  요구한다. 출처 `미상`  🔴 **출처를 못 읽어 깊이 소스를 고를 수 없다**
```

어댑터 여덟 개는 이미 `matchkey.make` 를 쓴다. 그런데 **`games` 46행이 46/46
비표준**이었다 — 그 행들은 어댑터가 바뀌기 **전에** 쌓였다. 🔴 쓰는 쪽만 고치면
쌓인 것은 영영 그 꼴로 남는다.

══════════════════════════════════════════════════════════════════
🔴 출처를 **계산한다** — 세 번째 표를 적지 않는다 (#1 사본 금지)
══════════════════════════════════════════════════════════════════

    ingest.ADAPTERS         리그 → 모듈      (원본)
    ingest.SOURCE_ADAPTERS  출처 → 모듈      (원본)
    ─────────────────────────────────────────────────
    여기                    리그 → 출처      (두 표를 **겹쳐** 얻는다)

⚠️ 손으로 `{"MLB": "statsapi"}` 를 적으면 어댑터가 늘 때 이 파일이 한 발 늦는다.
   2026-09-27 에 같은 병으로 여섯 번 놓쳤다.

🔴 **모르면 건드리지 않는다**(#4 추측 금지). 리그가 표에 없고(`Friendlies`) 열쇠도
   맨숫자면 출처를 알 길이 **없다** — 아무 접두나 붙이면 라우팅이 엉뚱한 어댑터로
   가고, 그것은 0 보다 나쁘다.
⚠️ `UNIQUE(sport, ext_id)` 가 있다 — 표준 꼴이 **이미 있으면** 그 행은 바꿀 수
   없다. 🔴 그때 **조용히 지우지 않는다**: 건너뛰고 그 수를 보고한다(#3).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app import matchkey

logger = logging.getLogger(__name__)


def _source_of_module() -> dict[object, str]:
    """모듈 → 출처. 🔴 `SOURCE_ADAPTERS` 를 **뒤집어** 얻는다.

    ⚠️ 한 모듈이 여러 출처에 걸리면(그런 일이 생기면) **먼저 선언된 것**을 쓴다 —
       선언 순서가 그 어댑터의 주 출처다.
    """
    from app.collect import ingest
    out: dict[object, str] = {}
    for src, mod in ingest.SOURCE_ADAPTERS.items():
        out.setdefault(mod, src)
    return out


def source_for(*, league: str = "", ext_id: str = "") -> str:
    """🔴 이 행의 **출처 이름**(모르면 `""`).

    순서가 `ingest.adapter_of` 와 같다 — **열쇠가 이미 말하면 그것**이 먼저이고,
    아니면 리그 표를 본다.
    ⚠️ `matchkey.source_of` 는 옛 접두(`fotmob-5181780`)도 읽는다.
    """
    said = matchkey.source_of(str(ext_id or ""))
    if said:
        return said
    from app.collect import ingest
    mod = ingest.ADAPTERS.get(str(league or ""))
    if mod is None:
        return ""
    return _source_of_module().get(mod, "")


def canonical_for(*, league: str = "", ext_id: str = "") -> str:
    """🔴 이 행이 **가져야 할** 열쇠. 바꿀 것이 없으면 `""`.

    ⚠️ 이미 표준이면 `""` 다 — *"바꿀 것 없음"*과 *"모름"*을 호출부가 수로 가린다
       (`plan` 이 `already` 와 `unknown` 을 따로 센다).
    """
    raw = str(ext_id or "")
    if matchkey.is_canonical(raw):
        return ""
    src = source_for(league=league, ext_id=raw)
    if not src:
        return ""
    return matchkey.make(src, matchkey.id_of(raw) or raw)


@dataclass
class Plan:
    """무엇을 바꾸고 **무엇을 못 바꿨나**. 🔴 못 한 것을 이름으로 남긴다(#3)."""

    changes: list[tuple[str, str, str]] = field(default_factory=list)
    clashes: int = 0        # 표준 꼴이 이미 있어 UNIQUE 가 막는다
    unknown: int = 0        # 🔴 출처를 알 길이 없다 — 건드리지 않는다
    already: int = 0        # 이미 표준이다
    clash_keys: list[str] = field(default_factory=list)
    unknown_keys: list[str] = field(default_factory=list)
    #: 🔴 함께 바꾼 표. ⚠️ 빈 목록이 **정상**이다 — 지금은 `game_id` 로 잇는다.
    referring: list[tuple[str, str]] = field(default_factory=list)

    def line(self) -> str:
        return (f"이관 {len(self.changes)}건 · 이미 표준 {self.already} · "
                f"충돌 {self.clashes} · 출처 미상 {self.unknown}")


def plan(rows) -> Plan:
    """행 목록 → 계획. 🔴 **DB 에 닿지 않는다**(시험할 수 있게).

    ⚠️ 충돌 판정은 *"같은 종목에 그 표준 꼴이 이미 있나"* 다 — `UNIQUE(sport,
       ext_id)` 가 종목까지 묶기 때문이다.
    """
    got = Plan()
    have = {(str(r.get("sport") or ""), str(r.get("ext_id") or "")) for r in rows}
    taken: set[tuple[str, str]] = set()
    for r in rows:
        sport = str(r.get("sport") or "")
        raw = str(r.get("ext_id") or "")
        if matchkey.is_canonical(raw):
            got.already += 1
            continue
        new = canonical_for(league=str(r.get("league") or ""), ext_id=raw)
        if not new:
            got.unknown += 1
            got.unknown_keys.append(raw)
            continue
        if (sport, new) in have or (sport, new) in taken:
            got.clashes += 1
            got.clash_keys.append(raw)
            continue
        taken.add((sport, new))
        got.changes.append((sport, raw, new))
    return got


#: 🔴 경기 열쇠가 **입을 수 있는 칸 이름**. ⚠️ 이것은 사실의 사본이 아니라
#  **이름 규약**이다 — 어느 표가 실제로 그 칸을 가졌나는 DB 가 말한다(`referring`).
KEY_COLUMN_NAMES = ("ext_id", "match_key", "game_key")

#: 🔴 열쇠의 집. 여기 것은 바꾸는 대상이고, 나머지는 **가리키는 것**이다.
HOME = ("games", "ext_id")


async def referring(conn) -> list[tuple[str, str]]:
    """🔴🔴 **누가 경기 열쇠를 글자로 들고 있나** — DB 에 묻는다.

    ══════════════════════════════════════════════════════════════════
    🔴 내가 이 목록을 **손으로 적었다가 틀렸다**(실측 2026-10-04)
    ══════════════════════════════════════════════════════════════════

    종전에 여기 `("ledger", "match_key")`·`("sufficiency", "match_key")`·
    `("learned_names", "match_key")` 를 **적어 두었다**. 실물에 물어 보니:

    ```
    ledger.match_key        🔴 없다      (`ledger` 는 `game_id` 정수 FK 다)
    sufficiency.match_key   🔴 없다      (같다)
    learned_names           🔴 표가 없다
    games.ext_id            ← 열쇠를 글자로 든 칸은 **이것 하나**다
    ```

    ⚠️ 그리고 그 틀린 `UPDATE` 가 **트랜잭션을 죽였다** —
       `InFailedSQLTransactionError: current transaction is aborted`. 🔴 안에서
       `try/except` 로 감싸도 소용없다(그 뒤 문장이 전부 무시된다). 그래서
       **보내기 전에** 있는 것만 고른다.
    🔴 CLAUDE.md #1·#4 가 막으려던 것이다 — 손으로 유지하는 목록은 한 발 늦고,
       여기서는 **처음부터 틀렸다.**
    """
    rows = await conn.fetch(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE column_name = ANY($1::text[]) AND data_type IN "
        "('text','character varying') ORDER BY table_name, column_name",
        list(KEY_COLUMN_NAMES))
    return [(r["table_name"], r["column_name"]) for r in rows
            if (r["table_name"], r["column_name"]) != HOME]


async def run(pool) -> Plan:
    """🔴 실제로 고친다. **기동 때 한 번**(`scheduler.main`).

    ⚠️ 한 트랜잭션이다 — 중간에 끊기면 열쇠 절반만 바뀌어 참조가 깨진다.
    """
    async with pool.acquire() as c:
        rows = await c.fetch("SELECT sport, league, ext_id FROM games")
        got = plan([dict(r) for r in rows])
        if not got.changes:
            logger.info("[keymigrate] %s", got.line())
            return got
        # 🔴 **보내기 전에** 누가 열쇠를 들었나 묻는다 — 없는 표에 `UPDATE` 를
        #    던지면 트랜잭션이 통째로 죽는다(실측 2026-10-04).
        also = await referring(c)
        async with c.transaction():
            for sport, old, new in got.changes:
                await c.execute(
                    "UPDATE games SET ext_id = $1 WHERE sport = $2 AND ext_id = $3",
                    new, sport, old)
                # 🔴 가리키는 표도 **함께** — 안 하면 채점이 그 경기를 못 찾고
                #    *"예측을 안 했다"* 로 센다(그것이 성적을 거짓으로 만든다).
                for table, col in also:
                    await c.execute(
                        f"UPDATE {table} SET {col} = $1 WHERE {col} = $2",  # noqa: S608
                        new, old)
        got.referring = list(also)
    logger.info("[keymigrate] %s", got.line())
    if got.clash_keys:
        logger.warning("[keymigrate] 🔴 충돌로 **남긴** 열쇠: %s",
                       ", ".join(got.clash_keys[:10]))
    if got.unknown_keys:
        logger.warning("[keymigrate] ⚠️ 출처 미상으로 **건드리지 않은** 열쇠: %s",
                       ", ".join(got.unknown_keys[:10]))
    return got
