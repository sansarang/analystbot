"""수집 → DB. 🔴 **세포가 낸 사실을 표로 옮기는 것까지가 수집기다.**

여기가 없으면 세포는 블랙보드에만 쓰고 흐름은 빈 DB 를 읽는다 — 안 이어진
코드는 없는 코드보다 나쁘다(§배선).

🔴 판정하지 않는다(§19-f). `standings`·`games`·`starters`·`absences`·`players`
   에 적을 뿐이고, 동기 등급은 `sources.DbSources.motivation` 이 §3 함수로 낸다.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from app import ids, queries, searchcells, timefmt
from app.blackboard import Blackboard
from app.cells import (Q_ABSENCE, Q_COUNTER, Q_INTENT, Q_LINEUP, Q_LIVE,
                       Q_SLATE, Q_STANDINGS, Q_STARTER_RECENT, Cell, Question,
                       SourceScores, awake)
from app.collect import espn, fdorg, fotmob, kbo, kleague, mlb, nhl, npb
from app.llm import Budget as LLMBudget
from app.net import Net
from app.search import SearchChain, build_chain

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

#: 어느 리그를 어느 어댑터가 맡나. 🔴 **분기 말고 표다** — 리그가 늘면 행이 는다.
ADAPTERS = {
    "MLB": mlb,
    "NPB": npb,
    # 🔴 **KBO** — `config.LEAGUES_AUTO` 에 처음부터 있었는데 여기 **없었다**.
    #    즉 설정이 *"KBO 를 모은다"* 고 적어 두고 코드는 아무것도 안 했다
    #    (CLAUDE.md #2 배선). 실측 2026-10-03 에 사용자 질문으로 드러났다.
    #    ⚠️ 공식 사이트(`koreabaseball.com`)는 **robots 전면 금지**라 못 간다 —
    #       소스를 고른 경위는 `app/collect/kbo.py` 머리글에 전부 적혀 있다.
    kbo.LEAGUE: kbo,
    # 🔴 §19-g-1 의 리그다 — 일정 날짜 검증(`verify.slate_date_ok`)이 여기서 돈다.
    #    ⚠️ K리그는 `games` 표에 적지 않는다(ext_id 규약 미정 — `kleague` 머리글).
    kleague.LEAGUE: kleague,
    # ── 사용자 지시 2026-10-01: "야구 축구 하키 농구 배구" 를 당일·내일로 저장한다
    #    ⚠️ **v4 §9 에 없는 확장이다** — §9 단계 9 가 이름을 댄 것은
    #       `KBO·NPB·MLB·K리그·해외축구`(야구·축구)뿐이다.
    #       → `docs/fable/questions/2026-10-01_five_sports.md`
    #    🔴 농구·배구는 **여기 없다.** 무료 일정 소스를 못 찾았다(실측) —
    #       있는 척하지 않는다. 그 사유는 위 문서에 적혀 있다.
    fdorg.LEAGUE: fdorg,      # 해외축구 13개 대회 (키만·카드 없음)
    nhl.LEAGUE: nhl,          # 하키 (키 없음)
}

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **깊이는 리그가 아니라 `ext_id` 가 가리킬 수도 있다** (실측 2026-10-02)
# ══════════════════════════════════════════════════════════════════
#
# `ADAPTERS` 는 **슬레이트를 쌓는** 어댑터 표다. 그런데 봇이 스스로 찾아 적은 경기
# (`app/findgame.py`)는 리그 이름이 `Friendlies`·`대회명 미상` 처럼 **표에 없는 이름**
# 이고, 그러면 `analyze.depth_sources` 가 깊이를 0 으로 둔다.
#
# 라이브(중국 vs 팔레스타인 친선): 사실 6건 · 변수 **0건** · §7 R5 자료 부족.
# 🔴 그런데 그 경기의 **자료 주소는 `ext_id` 에 적혀 있었다**(`fotmob-6280453`).
#
# ⚠️ 리그 표를 먼저 본다 — 리그가 공식 API 를 가지면 그것이 더 깊다(NPB 순위표 등).
#    접두 표는 **리그에 어댑터가 없을 때의 대체**다(§19-b-4 와 같은 결).
#: 🔴🔴 **§8-1 — 출처 → 어댑터.** `matchkey.SOURCES` 의 이름을 쓴다.
#
#  ⚠️ 종전 `DEPTH_BY_EXT` 는 **접두 글자**(`fotmob-`)를 열쇠로 썼다. 그래서
#     접두가 없는 MLB 열쇠(`849825`)를 못 찾았다(실측 2026-10-04).
#  🔴 이제 출처 이름으로 고른다 — 열쇠 꼴이 바뀌어도 이 표는 그대로다.
SOURCE_ADAPTERS = {
    "fotmob": fotmob,
    "espn": espn,
    # 🔴 **MLB** — 종전에 이 줄이 **없었다**(접두가 없어 라우팅 자체가 불가)
    "statsapi": mlb,
    "nhl": nhl,
    "npb": npb,
    "tsdb": kbo,          # ⚠️ KBO 어댑터가 tsdb 를 **일정 소스로만** 쓴다
    "fdorg": fdorg,
    "kleague": kleague,
}

DEPTH_BY_EXT = {
    fotmob.EXT_PREFIX: fotmob,
    # 🔴 사용자 지시 2026-10-03 — ESPN 을 소스로 쓴다. ⚠️ 깊이는 **얕다**
    #    (구장·관중뿐) — 그 사실을 어댑터 독스트링이 적어 둔다.
    espn.EXT_PREFIX: espn,
}


def adapter_of(league: str = "", ext_id: str = ""):
    """🔴 **이 경기의 자료를 아는 어댑터.** 리그 표 → 없으면 `ext_id` 접두.

    ⚠️ 고르는 규칙을 **한 곳에만** 둔다. 종전에 `analyze` 가 같은 규칙을 다시
       적고 있었고, 그러면 한쪽이 늘 때 다른 쪽이 한 발 늦는다(#1 사본 금지).
    🔴 리그를 **먼저** 본다 — 공식 API 가 있으면 그것이 더 깊다(NPB 순위표 등).
    """
    mod = ADAPTERS.get(str(league or ""))
    if mod is not None:
        return mod
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§8-1 — 열쇠가 출처를 말한다**(`statsapi:849825`)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전에는 `startswith(prefix)` 로 **접두 글자**를 봤다. 그래서 접두가
    #     없는 MLB 열쇠(`849825`)는 **영영 못 찾았다**(실측 2026-10-04).
    #  🔴 이제 `matchkey.parse` 가 출처를 떼어 준다 — 옛 꼴(`fotmob-…`)도 읽는다.
    from app import matchkey
    src = matchkey.source_of(ext_id)
    if src:
        got = SOURCE_ADAPTERS.get(src)
        if got is not None:
            return got
    return None


def context_of(league: str = "", ext_id: str = ""):
    """🔴 그 어댑터의 **깊이 소스** 함수(없으면 `None`)."""
    return getattr(adapter_of(league, ext_id), "sources_context", None)






# ══════════════════════════════════════════════════════════════════
# STEP 0 — 일정 + 예고 선발
# ══════════════════════════════════════════════════════════════════

_UPSERT_GAME = """
INSERT INTO games (sport, league, ext_id, home, away, venue, starts_utc,
                   starts_kst, starts_local, status, round_note,
                   home_score, away_score)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
ON CONFLICT (sport, ext_id) DO UPDATE
   SET status = EXCLUDED.status,
       venue = COALESCE(EXCLUDED.venue, games.venue),
       home_score = EXCLUDED.home_score,
       away_score = EXCLUDED.away_score,
       round_note = COALESCE(EXCLUDED.round_note, games.round_note),
       updated_at = now()
RETURNING id
"""


def slate_rows(bb, league: str) -> list[dict]:
    """🔴 칠판에서 **그 리그의 일정 행 전부**. 원본은 이 함수 하나다(사본 금지).

    ══════════════════════════════════════════════════════════════════
    🔴 왜 `bb.value()` 로는 안 되나 (실측 2026-10-03)
    ══════════════════════════════════════════════════════════════════

    `bb.value()` 는 **칸이 `FOUND` 일 때 첫 사실 하나**를 준다. 소스가 하나면 맞다.
    ⚠️ 그런데 `collect_all` 어댑터(`kbo`)는 소스가 **열한 개**이고 각자 다른 목록을
       올린다 — `reconcile` 이 그것을 **`contradicted`** 로 보고 `value()` 가
       `None` 을 돌려줬다. 🔴 실측에서 **0경기**가 나왔다.
    🔴 그래서 **사실을 전부 펼쳐** 모으고 `ext_id` 로 중복을 지운다.
       ⚠️ 같은 경기가 두 팀 질의에서 한 번씩 오므로 중복은 **정상**이다.
    """
    slot = bb.slots.get(f"{Q_SLATE}:{league}")
    out: list[dict] = []
    seen: set[str] = set()
    for f in (slot.facts if slot else []):
        v = f.value if isinstance(f.value, list) else []
        for r in v:
            if not isinstance(r, dict):
                continue
            key = str(r.get("ext_id") or "")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            out.append(r)
    return out


async def _slate(pool, bb, net, scores, search, mod, league: str, day: date) -> int:
    # 🔴 어댑터가 *"전부 모아라"* 라고 선언하면 그대로 한다 — 일정이 **한 주소에
    #    다 있지 않은** 리그가 있다(`kbo`: 팀마다 따로 물어야 한다).
    cell = Cell(Question(Q_SLATE, league, league=league),
                mod.sources_slate(day),
                collect_all=bool(getattr(mod, "SLATE_COLLECT_ALL", False)))
    await cell.run(net, bb, search=search, scores=scores)
    rows = slate_rows(bb, league)
    n = 0
    for r in rows:
        if not r.get("starts_utc"):
            continue                    # 🔴 시각을 모르면 슬레이트에 넣지 않는다
        gid = await pool.fetchval(
            _UPSERT_GAME, r["sport"], r["league"], r["ext_id"], r["home"],
            r["away"], r.get("venue"), r["starts_utc"], r["starts_kst"],
            r.get("starts_local"), r["status"], r.get("round_note"),
            r.get("home_score"), r.get("away_score"))
        n += 1
        await _starters(pool, gid, r, league)
    return n


async def _starters(pool, game_id: int, row: dict, league: str) -> None:
    """예고 선발. 🔴 없으면 **행을 만들지 않는다** — 빈 행은 "모른다"를 숨긴다."""
    for side, pp in (row.get("probable") or {}).items():
        if not pp or not pp.get("name"):
            continue
        pid = None
        if pp.get("external_id"):
            pid = await ids.resolve_by_alias(pool, pp["source"],
                                             pp["external_id"])
            if pid is None:
                team = row["home"] if side == "home" else row["away"]
                pid = await ids.upsert_player(
                    pool, league=league, team=team, name=pp["name"],
                    role="pitcher")
                await ids.link_alias(pool, pid, pp["source"],
                                     pp["external_id"])
        await pool.execute(
            "INSERT INTO starters (game_id, side, player_id, name, status, "
            "source_url) VALUES ($1,$2,$3,$4,'probable',$5) "
            "ON CONFLICT (game_id, side) DO UPDATE "
            "SET name = EXCLUDED.name, player_id = EXCLUDED.player_id",
            game_id, side, pid, pp["name"], pp.get("source"))


# ══════════════════════════════════════════════════════════════════
# STEP 1 — 순위 (동기 재료)
# ══════════════════════════════════════════════════════════════════


async def _standings(pool, bb, net, scores, search, mod, league: str,
                     day: date) -> int:
    if not hasattr(mod, "sources_standings"):
        bb.unknown(f"{Q_STANDINGS}:{league}", f"{league} 순위 소스 미구현")
        return 0
    cell = Cell(Question(Q_STANDINGS, league, league=league),
                mod.sources_standings(day.year))
    await cell.run(net, bb, search=search, scores=scores)

    # 🔴 **id → 정식명.** 순위의 팀 이름은 약칭이라 `games` 와 안 맞는다.
    #    오늘 일정에서 id 를 읽어 이름을 맞춘다 — 이름끼리 맞추지 않는다.
    by_id: dict[str, str] = {}
    for r in bb.value(f"{Q_SLATE}:{league}") or []:
        for side in ("home", "away"):
            tid = r.get(f"{side}_id")
            if tid:
                by_id[str(tid)] = r[side]
    n = 0
    for qid, slot in bb.slots.items():
        if not qid.startswith(f"{Q_STANDINGS}:{league}:") or not slot.facts:
            continue
        r = slot.value
        if not r:
            continue
        f = slot.facts[0]
        # 오늘 안 뛰는 팀은 약칭 그대로 남는다 — 아무것도 그 행에 안 붙으므로 무해하다
        team = by_id.get(str(r.get("team_id") or ""), r["team"])
        await pool.execute(
            "INSERT INTO standings (league, team, as_of, w, l, d, pct, "
            "remaining, games_back, clinched, eliminated, tiebreaker, note, "
            "source_url, published_at) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15) "
            "ON CONFLICT (league, team, as_of) DO UPDATE "
            "SET w=EXCLUDED.w, l=EXCLUDED.l, remaining=EXCLUDED.remaining, "
            "    games_back=EXCLUDED.games_back, clinched=EXCLUDED.clinched, "
            "    eliminated=EXCLUDED.eliminated, note=EXCLUDED.note",
            league, team, day, r["w"], r["l"], r["d"], r["pct"],
            r["remaining"], r["games_back"], r["clinched"], r["eliminated"],
            r["tiebreaker"], r["note"], f.source, f.published_at)
        n += 1
    return n


# ══════════════════════════════════════════════════════════════════
# 라이브 — 중지·순연·진행중 (§2) · 타 구장 결과 (§9 방아쇠)
# ══════════════════════════════════════════════════════════════════


async def _live(pool, bb, net, scores, search, mod, league: str, day: date) -> int:
    if not hasattr(mod, "sources_live"):
        return 0
    cell = Cell(Question(Q_LIVE, league, league=league),
                mod.sources_live(day))
    await cell.run(net, bb, search=search, scores=scores)
    n = 0
    for qid, slot in bb.slots.items():
        if not qid.startswith(f"{Q_LIVE}:") or not slot.value:
            continue
        v = slot.value
        if not isinstance(v, dict):
            continue
        # 🔴 팀 이름으로 잇는다 — ext_id 규약이 소스마다 달라서다.
        #    ⚠️ 못 찾으면 **아무것도 안 고친다.** 잘못된 경기의 상태를 바꾸는
        #       것보다 모르는 채 두는 것이 낫다.
        done = await pool.execute(
            "UPDATE games SET status=$1, home_score=$2, away_score=$3, "
            "updated_at=now() "
            f" WHERE league=$4 AND {timefmt.sql_kst_day()}=$5 "
            f"   AND home=$6 AND away=$7",
            v["status"], *_score(v.get("score")), league, day,
            v.get("home"), v.get("away"))
        if done and done.endswith("1"):
            n += 1
    return n


def _score(s: str | None) -> tuple[int | None, int | None]:
    """`"8-0"` → `(8, 0)`. 🔴 홈-원정 순서는 소스가 정한다 — 여기서 뒤집지 않는다."""
    if not s or "-" not in s:
        return None, None
    a, _, b = s.partition("-")
    try:
        return int(a), int(b)
    except ValueError:
        return None, None


# ══════════════════════════════════════════════════════════════════
# 1b — 로스터 (등번호·역할)
# ══════════════════════════════════════════════════════════════════




# ══════════════════════════════════════════════════════════════════
# STEP 2 — 결장 (§4 원장)
# ══════════════════════════════════════════════════════════════════

#: 🔴 `line`·`confidence` 는 **NOT NULL 이고 지어낼 수 없다.**
#
#  §4 의 `line` 은 `starter|bullpen|lineup_core|defense|midfield` 다. MLB
#  transactions 파서가 이미 못 박았다: *"`line` 을 여기서 짓지 않는다. 투수인지
#  야수인지는 로스터가 말하고, 그것이 없으면 `starter`/`lineup_core` 를 지어내게
#  된다."* 🔴 그래서 **알 때만 적는다** — 모르면 원장에 넣지 않고 unknown 을
#  이름으로 남긴다(M15: 오래된 지식으로 사실을 썼다 / §11-3 추측 금지).
#
#  ⚠️ `confidence` 는 사실의 `hardness` 다 — 새로 짓는 값이 아니다.
_UPSERT_ABSENCE = """
INSERT INTO absences (league, team, player_name, player_id, basis, line,
                      confidence, source_url, published_at, extracted_by)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
ON CONFLICT (league, team, player_name, basis) WHERE resolved_at IS NULL
DO UPDATE SET player_id = COALESCE(EXCLUDED.player_id, absences.player_id),
              line = EXCLUDED.line,
              confidence = EXCLUDED.confidence,
              source_url = COALESCE(EXCLUDED.source_url, absences.source_url)
"""


async def _line_of(pool, league: str, team: str | None, name: str,
                   player_id: int | None) -> str | None:
    """§4 `line` — 🔴 **알 때만 돌려준다. 모르면 `None`.**

    지금 알 수 있는 것은 하나다: 그 선수가 **오늘 예고 선발**이면 `starter` 다
    (`starters` 표가 그것을 안다). 그 밖은 로스터의 `role` 만으로는 못 가른다 —
    투수라고 `bullpen` 으로 적으면 예고되지 않은 선발 투수가 불펜으로 기록되고,
    그것이 `pitcher_state` 판정을 오염시킨다(M18 과 같은 결의 오류).
    """
    row = await pool.fetchrow(
        "SELECT 1 FROM starters s JOIN games g ON g.id = s.game_id "
        " WHERE g.league = $1 AND ($2::text IS NULL OR $2 IN (g.home, g.away)) "
        "   AND (s.player_id = $3 OR s.name = $4) "
        f"   AND {timefmt.sql_kst_day('g.starts_kst')} = {timefmt.SQL_TODAY_KST} "
        " LIMIT 1", league, team, player_id, name)
    return "starter" if row else None


async def _absences(pool, bb, net, scores, search, mod, league: str,
                    day: date) -> int:
    """§4 결장 원장. 🔴 **어댑터가 결장 소스를 주는 리그만** 돈다.

    MLB 는 `transactions`(공식), NPB 는 로스터 페이지의 `公示以降の動き`(전출).
    ⚠️ 소스가 없으면 **unknown 을 이름으로** 남긴다 — 조용히 0 이 되면 "결장자가
       없다"로 읽히고, 그것은 M11(명단 없이 완전체로 씀)의 재발 경로다.
    """
    cells: list[Cell] = []
    if hasattr(mod, "sources_transactions"):
        cells.append(Cell(Question(Q_ABSENCE, f"{league}:{day}", league=league),
                          mod.sources_transactions(day)))
    if hasattr(mod, "sources_absence"):
        # NPB — 오늘 뛰는 팀만. 🔴 12팀을 다 열면 예산을 통째로 먹는다(§12-d)
        for team in sorted(_teams_today(bb, league)):
            srcs = mod.sources_absence(day.year, team)
            if not srcs:
                bb.unknown(f"{Q_ABSENCE}:{league}:{team}",
                           f"{team} 결장 소스 URL 없음 — 지어내지 않는다")
                continue
            cells.append(Cell(Question(Q_ABSENCE, f"{league}:{team}:{day}",
                                       team=team, league=league), srcs))
    if not cells:
        bb.unknown(f"{Q_ABSENCE}:{league}", f"{league} 결장 소스 미구현(§13)")
        return 0

    n = 0
    seen: set[int] = set()
    for cell in cells:
        await cell.run(net, bb, search=search, scores=scores)
        # 🔴 **이 세포가 올린 사실만** 본다(리뷰 2026-09-30). 종전에는 블랙보드의
        #    `absence:` 전체를 매 세포마다 다시 긁어서, 팀이 여러 개면 같은 사실에
        #    `attach_player_ids`·적재가 반복되고 반환 `n` 이 부풀었다(보고 수치가
        #    실제 행 수와 어긋난다). 🔴 그리고 문자열 `"absence:"` 를 박지 않는다 —
        #    질문 id 는 `Question.id` 가 정한다.
        facts = [f for qid, slot in bb.slots.items()
                 if qid.startswith(f"{Q_ABSENCE}:") for f in slot.facts
                 if id(f) not in seen]
        seen.update(id(f) for f in facts)
        # 🔴 §19-g-6 — 동명이인은 `player_id` 로 갈린다. 팀 불명이면 미상이다
        unresolved = await searchcells.attach_player_ids(
            pool, facts, league=league, team=cell.question.team)
        for why in unresolved:
            bb.unknown(f"{Q_ABSENCE}:{league}:미상:{why[:40]}", why)
        for f in facts:
            v = f.value if isinstance(f.value, dict) else {}
            name = v.get("player_name")
            if not name:
                continue
            # 🔴 `team` 은 NOT NULL 이다. 귀속이 불명이면 **원장에 넣지 않는다** —
            #    아무 팀에 붙이면 결장이 상대 팀에 붙는다(§17-g-3 · M14).
            if not f.team:
                bb.unknown(f"{Q_ABSENCE}:{league}:귀속불명:{name}",
                           f"{name} 결장 — 어느 팀인지 모른다(원장에 넣지 않았다)")
                continue
            line = await _line_of(pool, league, f.team, name, f.player_id)
            if line is None:
                # 🔴 지어내지 않는다. **이름으로** 남긴다(조용한 0 금지)
                bb.unknown(f"{Q_ABSENCE}:{league}:{f.team}:{name}:line",
                           f"{name} 결장은 잡혔는데 §4 line 을 모른다 — "
                           f"로스터·예고 선발이 아직 없다(원장에 넣지 않았다)")
                continue
            await pool.execute(
                _UPSERT_ABSENCE, league, f.team, name, f.player_id,
                v["basis"], line, f.hardness, f.source, f.published_at,
                f.extracted_by)
            n += 1
    return n


def _teams_today(bb, league: str) -> set[str]:
    """오늘 뛰는 팀. 🔴 **슬레이트 세포가 이미 답한 것을 읽는다**(§19-c 블랙보드).

    ⚠️ DB 를 다시 읽지 않는다 — 같은 사실을 두 곳에서 가져오면 한쪽이 낡는다.
    """
    out: set[str] = set()
    for r in bb.value(f"{Q_SLATE}:{league}") or []:
        for side in ("home", "away"):
            if r.get(side):
                out.add(r[side])
    return out


# ══════════════════════════════════════════════════════════════════
# §19-d — 경기별 세포 (라인업·의도·선발 최근 창)
# ══════════════════════════════════════════════════════════════════


async def _slate_rows(pool, bb, league: str, day: date) -> list[dict]:
    """오늘 경기들. 🔴 **블랙보드가 먼저, DB 가 다음이다.**

    같은 사이클 안에서는 슬레이트 세포가 이미 답했으므로 블랙보드가 원본이다
    (§19-c). 라인업 주기(`only=`)는 슬레이트 세포를 돌리지 않으므로 DB 를 읽는다.

    ⚠️ **같은 모양으로 돌려준다** — 호출부가 두 경로를 구분하면 한쪽이 낡는다.
    """
    rows = bb.value(f"{Q_SLATE}:{league}") or []
    if rows:
        return rows
    got = await pool.fetch(
        # 🔴 `sport` 를 함께 읽는다 — 종목에 **없는 질문**을 걸러야 한다
        #    (`queries.asks`). 블랙보드 경로는 어댑터가 이미 `sport` 를 싣는다.
        "SELECT id, sport, ext_id, home, away, venue, starts_utc FROM games "
        f" WHERE league = $1 AND {timefmt.sql_kst_day()} = $2::date "
        " ORDER BY starts_utc",
        league, day)
    return [{"game_id": int(r["id"]), "sport": r["sport"],
             # 🔴 깊이 소스가 `ext_id` 로 공식 API 를 부른다(`sources_context`)
             "ext_id": r["ext_id"], "home": r["home"],
             "away": r["away"], "venue": r["venue"],
             "starts_utc": r["starts_utc"]} for r in got]


async def _game_cells(pool, bb, net, scores, search, league: str, day: date, *,
                      now: datetime, only: tuple[str, ...] | None = None
                      ) -> dict:
    """🔴 **시간축이 여기서 집행된다**(§19-d). `awake()` 가 아니면 안 돈다.

    §19-d: 라인업은 T-70분부터, 의도는 T-3h·T-1h, 선발 최근 창은 T-6h.
    ⚠️ **안 돈 세포를 이름으로 남긴다** — 조용히 건너뛰면 "자료가 없다"와
       "아직 시간이 아니다"가 구분되지 않는다(CLAUDE.md §조용한 0 금지).
    """
    rows = await _slate_rows(pool, bb, league, day)
    out = {"lineup": 0, "intent": 0, "starter_recent": 0, "asleep": 0}
    dropped: list[str] = []
    short = getattr(npb, "TEAMS", {}) if league == "NPB" else {}
    local_of = {full: s for s, full in short.items()}

    for r in rows:
        starts = r.get("starts_utc")
        if not starts:
            continue
        gid = r.get("game_id")
        for side, other in (("home", "away"), ("away", "home")):
            team = r.get(side)
            if not team:
                continue
            local = local_of.get(team, "")
            # 🔴 감독 **교체**는 감독 **의도**와 다른 질문이다(§19-a) — 세포도
            #    따로다. 실측 2026-09-30: 한 세포에 넣었더니 인용 하나를 얻고
            #    멈춰서 교체 자료에 영영 못 갔다.
            for qtype, make in ((Q_LINEUP, searchcells.lineup_cell),
                                (Q_INTENT, searchcells.intent_cell),
                                (Q_INTENT, searchcells.coach_cell),
                                (Q_STARTER_RECENT,
                                 searchcells.starter_recent_cell)):
                if only and qtype not in only:
                    continue
                # 🔴 **이 종목에 없는 질문은 묻지 않는다.** 물으면 엉뚱한 것을
                #    묻는다 — 실측 2026-10-01: 축구 경기에 `starter_recent` 를
                #    돌려 검색어가 `Las Vegas Lights 선발 등판 1일`(야구 용어)이
                #    됐다. 어댑터가 이미 *"축구에는 예고 선발이 없다"* 고 적었다.
                #    ⚠️ 건너뛴 것을 **이름으로** 남긴다(조용한 0 금지).
                asked, why = queries.asks(r.get("sport") or "", qtype)
                if not asked:
                    out["skipped_by_sport"] = out.get("skipped_by_sport", 0) + 1
                    bb.unknown(f"{qtype}:{league}:{team}:{day}", why)
                    continue
                if not awake(qtype, starts, now):
                    out["asleep"] += 1
                    # 🔴 왜 안 돌았는지 남긴다 — "자료 없음"이 아니다
                    # 🔴 **"아직"과 "이미"를 가른다**(실측 2026-10-02): 경기가
                    #    끝난 뒤에도 *"아직 안 깬다"* 로 적혀 있었다. 둘은 처방이
                    #    정반대다 — 전자는 기다리면 되고, 후자는 **이 경기는 영영
                    #    안 돈다**(§19-d: 킥오프면 세포 종료).
                    when = "이미 시작했다 — 이 세포는 더 안 돈다" \
                        if now >= starts else "아직 안 깬다"
                    bb.unknown(f"{qtype}:{league}:{team}:{day}",
                               f"§19-d 시간축 — {when} "
                               f"(경기 {starts:%m/%d %H:%M}Z, 지금 "
                               f"{now:%m/%d %H:%M}Z)")
                    continue
                # 🔴 **공식 API 깊이**(맞대결·폼·선수·순위)를 라인업 세포에 얹는다.
                #    사용자 지시 2026-10-01: *"모든 경기를 … 내가 보여준 결과치대로"*.
                #    ⚠️ 어댑터가 `sources_context` 를 갖고 있을 때만이다 — 없는
                #       종목에 있는 척하지 않는다(K리그·해외축구는 아직 없다).
                extra: list = []
                if qtype == Q_LINEUP and r.get("ext_id"):
                    ctx = getattr(ADAPTERS.get(league), "sources_context", None)
                    if callable(ctx):
                        extra = ctx(str(r["ext_id"]))
                cell, drop = make(team=team, league=league, day=day,
                                  game_id=gid, starts=starts, local=local,
                                  **({"extra": extra} if qtype == Q_LINEUP else {}),
                                  **({"opponent": r.get(other) or "",
                                      "opponent_local": local_of.get(
                                          r.get(other) or "", ""),
                                      "venue": r.get("venue") or "",
                                      "now": now}
                                     if qtype == Q_LINEUP else {}))
                dropped.extend(drop)
                await cell.run(net, bb, search=search, scores=scores)
                slot = bb.get(cell.question.id)
                if slot and slot.state == "found":
                    out[qtype if qtype != Q_STARTER_RECENT
                        else "starter_recent"] += 1
    if dropped:
        # 🔴 §12-b 로 버린 검색어를 이름으로 남긴다(§19-b-6)
        bb.unknown(f"검색어버림:{league}:{day}",
                   f"§12-b 로 버린 변형 {len(dropped)}건: {dropped[:5]}")
        out["dropped_queries"] = len(dropped)
    return out


# ══════════════════════════════════════════════════════════════════
# §19-g-5 — 반증 세포: unknown 이 질문을 낳는다
# ══════════════════════════════════════════════════════════════════


async def _counters(pool, bb, net, scores, search, league: str,
                    day: date) -> int:
    """🔴 *"사실이 사실을 낳는다"*(§19-c). unknown 하나가 **반증 세포**를 만든다.

    §19-g-5 실측: *"휴스턴 선발: unknown → 반증 세포 → RotoWire hit → 웨스네스키
    3.50/1.15 사실 → 판정 상향."* 🔴 검색어는 **L5(LLM)가 만들고 §12-b 로
    걸러진** 것들이다(§19-b-5) — 규칙 변형이 이미 다 떨어진 자리이기 때문이다.

    🔴 세포는 판정하지 않는다 — 상향은 `judge.py` 몫이다(§19-f).
    """
    # 🔴 선발을 못 잰 질문만 고른다. 예산이 있으니 전부에 반증을 붙이지 않는다
    open_qs = [(qid, slot.reason) for qid, slot in bb.slots.items()
               if slot.state != "found"
               and qid.startswith(f"{Q_STARTER_RECENT}:{league}:")]
    if not open_qs:
        return 0
    llm_budget = LLMBudget()
    n = 0
    for qid, reason in open_qs[:3]:          # §12-d 경기별 예산 고정
        subject = qid.split(":")[-2] if qid.count(":") >= 2 else qid
        condition = f"{subject} 선발 투수가 확정됐는가 ({reason[:60]})"
        variants, drops = await queries.from_llm(condition, league=league,
                                                pool=pool, budget=llm_budget)
        if not variants:
            bb.unknown(f"{Q_COUNTER}:{league}:{subject}:{day}",
                       f"반증 검색어를 못 만들었다 — {drops[:3] or 'L5 출력 0건'}")
            continue
        cell = searchcells.counter_cell(
            subject=subject, condition=condition, league=league, day=day,
            game_id=None, variants=variants, deps=[qid])
        await cell.run(net, bb, search=search, scores=scores)
        n += 1
    return n


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **`analyze.py` 에서 옮겨 왔다** — §8 5단계 삭제(2026-10-06)
# ══════════════════════════════════════════════════════════════════
#
#  이름표 사다리 ⑤단(*"봇이 직접 찾았다"*)이 이 함수를 쓴다(`app/resolve.py`).
#  🔴 적는 SQL 이 **이 파일**에 있으므로 여기가 제자리다 — 옛 조율자가 들고 있던
#     것이 사본이었다.
async def fill_slate(pool, league: str, day) -> str:
    """🔴 그 리그의 **일정을 받아 표에 적는다**(옛 `analyze._fill_slate`). 돌려주는 것은 사람이 읽을 사유.

    ⚠️ 수집 전체(`ingest.collect`)를 부르지 않는다 — 그것은 순위·명단·라인업까지
       도는 **아침 작업**이고, 질문 하나가 그것을 끌고 오면 사람이 기다린다.
       🔴 필요한 것은 **슬레이트 한 조각**이다. 적는 SQL 은 `ingest` 것을 쓴다.
    """
    from app.cells import Q_SLATE, Cell, Question
    mod = ADAPTERS[league]
    bb = Blackboard()
    # 🔴 어댑터가 *"전부 모아라"* 라고 선언하면 그대로 한다(`kbo.SLATE_COLLECT_ALL`)
    cell = Cell(Question(Q_SLATE, league, league=league), mod.sources_slate(day),
                collect_all=bool(getattr(mod, "SLATE_COLLECT_ALL", False)))
    why = await cell.run(Net(), bb, search=None)
    # 🔴 사실을 전부 펼쳐 모은다 — `bb.value()` 는 `collect_all` 에서 비어 온다
    #    (그 까닭은 `ingest.slate_rows` 독스트링에 있다)
    rows = slate_rows(bb, league)
    n = 0
    for r in rows:
        if not r.get("starts_utc"):
            continue            # 🔴 시각을 모르면 표에 넣지 않는다(`ingest` 와 같다)
        await pool.fetchval(
            _UPSERT_GAME, r["sport"], r["league"], r["ext_id"], r["home"],
            r["away"], r.get("venue"), r["starts_utc"], r["starts_kst"],
            r.get("starts_local"), r["status"], r.get("round_note"),
            r.get("home_score"), r.get("away_score"))
        n += 1
    return f"`{league}` 어댑터로 {n}경기를 표에 적었다" + (f" — {why}" if not n else "")


#: 🔴 `games.status` 중 **예정이 아닌 것**. 원본은 `db/schema.sql` 의 주석이다
#   (`scheduled | delayed | postponed | inprogress | final`).
#   ⚠️ `delayed`·`postponed` 는 **시작 안 한 것**이다 — 예측이 아직 뜻이 있다.
PLAYED_STATUS = ("inprogress", "final")
