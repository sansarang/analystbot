"""1b 선수 식별 — §7-3. **player_id 는 봇이 발급한다.**

사용자 결정 2026-09-27:
  *"player_id는 봇이 발급(자연키 = 리그+팀+등번호+이름, 생년월일 있으면 추가),
  외부 id(MLB statsapi id, npb.jp 선수 id, FotMob id)는 player_alias 테이블에
  붙인다. 동명이인은 팀+등번호로 갈리고, 이적 시 alias가 따라간다.
  이름만 있는 기사 추출은 팀이 확정된 경우에만 매칭하고, 팀 불명이면 미상."*

🔴 **거짓 매칭보다 미상이 낫다.** 동명이인이 실재한다(박건우 NC/롯데 ·
   김민석 두산/KT). 이름만으로 맞추면 결장이 상대 팀에 붙는다.
"""
from __future__ import annotations

import re
import unicodedata

MATCH_HARD = "hard"       # 외부 id 또는 팀+등번호로 확정
MATCH_LIKELY = "likely"   # 팀 확정 + 이름 유일
MATCH_NONE = "미상"       # 🔴 값으로 남긴다. 조용히 버리지 않는다


_WS = re.compile(r"\s+")
_DROP = re.compile(r"[·.\-'’]")


def name_key(name: str) -> str:
    """대조용 정규화 키.

    🔴 **비라틴 문자를 지우지 않는다.** 실사고 2026-09-21: `NFKD → ascii
       ignore` 를 쓰는 정규화가 한글을 통째로 지워(`'박건우' → ''`) 한국 선수
       이름이 **전부 서로 일치**했다. 그래서 라틴 문자만 발음부호를 벗기고,
       비라틴은 그대로 둔다.
    """
    s = _WS.sub(" ", str(name or "")).strip().lower()
    if not s:
        return ""
    out = []
    for ch in unicodedata.normalize("NFD", s):
        if unicodedata.combining(ch):
            continue          # 라틴 발음부호만 떨어진다
        out.append(ch)
    return _DROP.sub("", _WS.sub("", unicodedata.normalize("NFC", "".join(out))))


_UPSERT = """
INSERT INTO players (league, team, jersey, name, name_key, birth_date, role)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT ON CONSTRAINT %s DO UPDATE
   SET team = EXCLUDED.team,
       name = EXCLUDED.name,
       role = COALESCE(EXCLUDED.role, players.role),
       last_seen = now()
RETURNING player_id
"""


async def upsert_player(conn, *, league: str, team: str, name: str,
                        jersey: str | None = None, birth_date=None,
                        role: str | None = None) -> int:
    """명단 한 줄 → `player_id`.

    🔴 **이적 시 새 행을 만들지 않는다** — `team` 을 갱신하고 `last_seen` 을
       올린다. alias 는 그대로 남으므로 자동으로 따라간다(§7-3).
    ⚠️ 등번호가 있는 쪽과 없는 쪽은 유일 인덱스가 다르다(스키마의 부분 인덱스).
    """
    key = name_key(name)
    if not key:
        raise ValueError("이름이 비었다")
    if jersey is not None:
        jersey = str(jersey).strip() or None      # 🔴 '00' 을 살린다

    # 부분 유일 인덱스는 ON CONFLICT 로 이름을 못 대므로 먼저 찾아본다
    if jersey is not None:
        row = await conn.fetchrow(
            "SELECT player_id FROM players WHERE league=$1 AND team=$2 "
            "AND jersey=$3 AND name_key=$4", league, team, jersey, key)
    else:
        row = await conn.fetchrow(
            "SELECT player_id FROM players WHERE league=$1 AND team=$2 "
            "AND name_key=$3 AND birth_date IS NOT DISTINCT FROM $4",
            league, team, key, birth_date)
    if row:
        await conn.execute(
            "UPDATE players SET name=$2, role=COALESCE($3, role), "
            "last_seen=now() WHERE player_id=$1", row["player_id"], name, role)
        return int(row["player_id"])

    # 다른 팀에 같은 (등번호, 이름) 이 있으면 이적이다 — 옮긴다
    if jersey is not None:
        moved = await conn.fetchrow(
            "SELECT player_id FROM players WHERE league=$1 AND jersey=$2 "
            "AND name_key=$3 AND team<>$4", league, jersey, key, team)
        if moved:
            await conn.execute(
                "UPDATE players SET team=$2, last_seen=now() WHERE player_id=$1",
                moved["player_id"], team)
            return int(moved["player_id"])

    row = await conn.fetchrow(
        "INSERT INTO players (league, team, jersey, name, name_key, "
        "birth_date, role) VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING player_id",
        league, team, jersey, name, key, birth_date, role)
    return int(row["player_id"])


async def link_alias(conn, player_id: int, source: str, external_id: str
                     ) -> None:
    """외부 id 를 붙인다. 🔴 같은 외부 id 가 두 선수에 붙으면 유일키가 막는다."""
    await conn.execute(
        "INSERT INTO player_alias (player_id, source, external_id) "
        "VALUES ($1,$2,$3) ON CONFLICT (source, external_id) DO UPDATE "
        "SET player_id = EXCLUDED.player_id, linked_at = now()",
        player_id, source, str(external_id))


async def resolve_by_alias(conn, source: str, external_id: str) -> int | None:
    """🔴 **1순위.** id 가 있으면 이름을 보지 않는다."""
    row = await conn.fetchrow(
        "SELECT player_id FROM player_alias WHERE source=$1 AND external_id=$2",
        source, str(external_id))
    return int(row["player_id"]) if row else None


async def resolve_by_name(conn, *, league: str, team: str | None, name: str,
                          jersey: str | None = None
                          ) -> tuple[int | None, str]:
    """🔴 **팀이 확정된 경우에만 매칭한다.** 팀 불명이면 즉시 미상.

    반환은 셋이다: `(id, "hard")` · `(id, "likely")` · `(None, "미상")`.
    같은 팀에 동명이인이 둘이면 등번호 없이는 갈 수 없다 → 미상.
    """
    if not team:
        return None, MATCH_NONE
    key = name_key(name)
    if not key:
        return None, MATCH_NONE

    if jersey is not None:
        row = await conn.fetchrow(
            "SELECT player_id FROM players WHERE league=$1 AND team=$2 "
            "AND jersey=$3 AND name_key=$4", league, team, str(jersey), key)
        if row:
            return int(row["player_id"]), MATCH_HARD

    rows = await conn.fetch(
        "SELECT player_id FROM players WHERE league=$1 AND team=$2 "
        "AND name_key=$3", league, team, key)
    if len(rows) == 1:
        return int(rows[0]["player_id"]), MATCH_LIKELY
    return None, MATCH_NONE      # 0건이거나 동명이인 — 둘 다 미상


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **스쿼드 명단 대조** — "손흥민이 나오면 버린다" (사용자 설계 2026-10-02)
#
# ⚠️ **`app/verify.py` 가 아니라 여기 있다.** 계약(`test_검증기가_수집기보다_먼저_있다`)이
#    검증기를 **의존 없는 모듈**로 잠근다 — `verify` 는 `re`·`dataclasses`·`datetime`
#    만 쓴다. 명단 대조는 `name_key` 를 쓰므로 **선수 신원의 집**인 이 파일이 맞다.
# ══════════════════════════════════════════════════════════════════
#
# > ④ 엉뚱한 걸 버린다 — 손흥민이 나오면 남자팀이라 버림 → **fotmob 스쿼드 명단과
# > 기사 속 선수명 대조, 명단 밖 선수뿐이면 폐기**
#
# 🔴 실측 2026-10-02 이 왜 이것이 필요한지 보여 줬다: 여자 아시안게임을 물었는데
#    **남자 대표팀**(손흥민·김민재) 경기 페이지가 들어왔다. 날짜도 같고 팀 이름도
#    글자까지 같아서 `same_squad_kind` 외에는 막을 길이 없었다 — 그러나 **이름이
#    모호한 경우**(`South Korea` 하나로 남녀가 다 돈다)에는 그것도 못 막는다.
#    🔴 **명단은 모호하지 않다.** 손흥민은 여자 대표팀 명단에 없다.
#
# ⚠️ **명단을 모르면 검사하지 않는다 — 통과시키지도 않는다.** `None` 을 돌려
#    호출부가 *"검사 못 했다"* 를 남기고 hardness 를 내리게 한다(§12-c-1 과 같은 규율).


def roster_keys(names) -> frozenset[str]:
    """명단 → 대조 키 집합. 🔴 `name_key` 를 쓴다(한글을 지우지 않는 정규화)."""
    return frozenset(k for k in (name_key(n) for n in (names or [])) if k)


def in_roster(name: str, roster) -> bool | None:
    """이 선수가 명단에 있나. 🔴 **명단을 모르면 `None`** — 참도 거짓도 아니다.

    ⚠️ `None` 을 `True` 로 때우면 명단 검사가 **아무것도 막지 않는다.** 실측
       2026-10-02 의 손흥민이 그 구멍으로 들어왔다.
    """
    keys = roster if isinstance(roster, frozenset) else roster_keys(roster)
    if not keys:
        return None
    key = name_key(name)
    if not key:
        return None
    if key in keys:
        return True
    # 🔴 **성만 적힌 기사가 많다** — `Son` 이 `Heung-Min Son` 과 맞아야 한다.
    #    ⚠️ 두 글자 미만은 보지 않는다(`Li` 가 수십 명과 맞는다).
    if len(key) >= 3:
        for k in keys:
            if key in k or k in key:
                return True
    return False


def squad_check(name: str, roster):
    """§17-g-3 · M14 — **남의 선수면 버린다.** 돌려주는 것은 `verify.Verdict` 다.

    🔴 돌려주는 것: 통과(`ok`) · 거부(`ok=False`) · **모름**(`unknown=True`).
    ⚠️ 모름은 `soft` 로 내린다 — 명단 없이 받은 사실을 hard 로 두면 안 된다.
    """
    from app import verify
    got = in_roster(name, roster)
    if got is None:
        return verify.Verdict(True, "명단을 몰라 대조하지 못했다", unknown=True,
                       hardness="soft")
    if got:
        return verify.Verdict(True, "", hardness="hard")
    return verify.Verdict(False, f"`{name}` 이 우리 명단에 없다 — 남의 팀 자료다",
                   hardness="soft")
