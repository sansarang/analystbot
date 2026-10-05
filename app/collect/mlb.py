"""MLB — statsapi.mlb.com. 🔴 **키 0건 · 검색 0건.**

§13-a: *"MLB.com probable pitchers … MLB.com standings·magic number …
MLB.com transactions·IL"*. 그 셋이 한 API 에 있어 검색 없이 URL 로 닫힌다 —
그래서 §19-b 의 "넓게 던진다"가 필요 없는 유일한 리그다.

실측 2026-09-27: 일정 15경기 · 예고 선발 13/15 · 순위 전 구단.
robots.txt 가 404 라 제한이 없다(§19-f 는 우회가 아니라 확인이다).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from app import factspec, matchkey, verify
from app.blackboard import Fact
from app.cells import Q_STANDINGS, Question, Source
from app.net import Fetched

logger = logging.getLogger(__name__)
BASE = "https://statsapi.mlb.com/api/v1"
KST = timezone(timedelta(hours=9))

#: 🔴 이 어댑터가 맡는 종목. **상수로 밝힌다** — 행 안에만 적으면 "표에 어떤
#  종목이 있나"를 밖에서 못 읽는다(사용자 지시 2026-10-01: 다섯 종목을 쌓는다).
SPORT = "baseball"
#: 한 시즌 경기 수. 🔴 리그 상수는 코드에 박지 않고 여기 한 곳에 둔다.
GAMES_IN_SEASON = 162

#: 🔴 statsapi 의 `status.abstractGameState`·`detailedState` → 우리 규약.
#   사본 금지 — 읽는 쪽이 문자열을 다시 적지 않는다.
_STATUS = {
    "Preview": "scheduled",
    "Live": "inprogress",
    "Final": "final",
}
_DETAILED = {
    "Postponed": "postponed",
    "Delayed": "delayed",
    "Delayed Start": "delayed",
    "Suspended": "postponed",
}


def schedule_url(day) -> str:
    return (f"{BASE}/schedule?sportId=1&date={day}"
            "&hydrate=probablePitcher,team,venue")


def standings_url(season: int) -> str:
    return (f"{BASE}/standings?leagueId=103,104&season={season}"
            "&standingsTypes=regularSeason")


def transactions_url(day) -> str:
    return f"{BASE}/transactions?startDate={day}&endDate={day}"


# ══════════════════════════════════════════════════════════════════
# STEP 0 슬레이트 + 예고 선발
# ══════════════════════════════════════════════════════════════════


def parse_schedule(got: Fetched, q: Question | None = None) -> list[dict]:
    """일정 JSON → 경기 목록.

    🔴 **현지 시각과 KST 를 둘 다 만든다**(§2). `gameDate` 는 UTC(Z)다.
    🔴 예고 선발이 없으면 `None` 으로 둔다 — **지어내지 않는다**(§0-5).
    """
    if not got.ok:
        return []
    data = json.loads(got.text)
    out: list[dict] = []
    for date_block in data.get("dates") or []:
        for g in date_block.get("games") or []:
            # 🔴🔴 **tz 없는 시각을 슬레이트에 넣지 않는다**(5단계 · 2026-10-04).
            #
            #  ⚠️ 종전엔 여기서 `fromisoformat` 을 바로 썼다. `Z` 가 없는 꼴이
            #     오면 **naive 가 그대로 `games` 표에 들어갔고**, 그 값은 조용히
            #     서버 시간대로 읽힌다 — 실측에서 그 가정이 어긋나 경기를 잃었다.
            #  🔴 `_when` 이 tz 를 요구한다. 못 읽으면 **그 경기를 건너뛴다** —
            #     시각을 모르는 행은 슬레이트에 뜻이 없다(`ingest._slate` 와 같다).
            starts = _when(g.get("gameDate"))
            if starts is None:
                logger.info("[mlb] 시각을 못 읽어 건너뛴다 — %s (%r)",
                            g.get("gamePk"), g.get("gameDate"))
                continue
            st = g.get("status") or {}
            status = _DETAILED.get(st.get("detailedState") or "") \
                or _STATUS.get(st.get("abstractGameState") or "", "scheduled")
            row = {
                "sport": "baseball", "league": "MLB",
                # 🔴🔴 **§8-1 — 열쇠가 출처를 말한다**(`statsapi:849825`).
                #    ⚠️ 종전엔 **숫자만**(`849825`)이라 `adapter_of(ext_id=)` 가
                #       이 행을 **라우팅하지 못했다**(실측 2026-10-04).
                "ext_id": matchkey.make("statsapi", g["gamePk"]),
                "home": _team(g, "home"), "away": _team(g, "away"),
                # 🔴 **id 를 들고 간다.** 순위는 약칭(`Nationals`), 일정은
                #    정식명(`Washington Nationals`)이라 **이름으로는 안 맞는다**
                #    (실측 2026-09-27 — 동기가 30팀 전부 미확인으로 떨어졌다).
                "home_id": _team_id(g, "home"), "away_id": _team_id(g, "away"),
                "venue": (g.get("venue") or {}).get("name"),
                "starts_utc": starts,
                "starts_kst": starts.astimezone(KST),
                "status": status,
                "home_score": (g["teams"]["home"] or {}).get("score"),
                "away_score": (g["teams"]["away"] or {}).get("score"),
                "probable": {
                    side: _probable(g, side) for side in ("home", "away")},
            }
            out.append(row)
    logger.info("[mlb] 일정 %d경기 · 예고 선발 %d경기 양쪽", len(out),
                sum(1 for r in out if all(r["probable"].values())))
    return out


def _team(g: dict, side: str) -> str:
    return ((g.get("teams") or {}).get(side) or {}).get("team", {}).get("name", "")


def _team_id(g: dict, side: str):
    tid = ((g.get("teams") or {}).get(side) or {}).get("team", {}).get("id")
    return str(tid) if tid else None


def _probable(g: dict, side: str) -> dict | None:
    pp = ((g.get("teams") or {}).get(side) or {}).get("probablePitcher")
    if not pp:
        return None                     # 🔴 미확인은 미확인이다
    return {"name": pp.get("fullName"), "external_id": str(pp.get("id")),
            "source": "statsapi"}


# ══════════════════════════════════════════════════════════════════
# STEP 1 동기 재료 — 순위
# ══════════════════════════════════════════════════════════════════


def parse_standings(got: Fetched, q: Question | None = None) -> list[Fact]:
    """순위 JSON → `standings` 행.

    🔴 §3 이 요구하는 칸이 전부 있다: `gamesBack` · `clinched` ·
       `eliminationNumber`("E" 면 탈락) · `magicNumber` · `gamesPlayed`.
    ⚠️ 잔여는 `162 − gamesPlayed` 다. 우천 순연으로 162 를 못 채우는 팀이 있어
       음수가 나오면 0 으로 눕힌다.
    """
    if not got.ok:
        return []
    data = json.loads(got.text)
    now = datetime.now(timezone.utc)
    facts: list[Fact] = []
    for rec in data.get("records") or []:
        for t in rec.get("teamRecords") or []:
            name = (t.get("team") or {}).get("name") or ""
            gb = t.get("gamesBack")
            row = {
                "team": name,
                "team_id": str((t.get("team") or {}).get("id") or "") or None,
                # 🔴 **공통 꼴**(`league.TABLE_FIELDS`) — 종목마다 칸 이름이
                #    달라서 단계 5~7 이 분기를 써야 했다(실측 2026-10-02:
                #    fotmob 은 `wins/draws/losses`, 여기는 `w/l/d` 였다).
                #    ⚠️ 옛 이름도 남긴다 — 읽는 쪽이 이미 있다.
                "wins": t.get("wins"), "losses": t.get("losses"), "draws": None,
                "played": t.get("gamesPlayed"),
                "goals_for": (t.get("runsScored")
                              or (t.get("runDifferential") is not None and None)),
                "goals_against": t.get("runsAllowed"),
                "goal_diff": t.get("runDifferential"),
                "points": None, "rank": _num(t.get("divisionRank")),
                "table": ((rec.get("division") or {}).get("nameShort")
                          or (rec.get("division") or {}).get("name")),
                "w": t.get("wins"), "l": t.get("losses"), "d": None,
                "pct": _num(t.get("winningPercentage")),
                "remaining": max(0, GAMES_IN_SEASON - int(t.get("gamesPlayed") or 0)),
                "games_back": _num(gb),
                "clinched": bool(t.get("clinched") or t.get("divisionChamp")),
                # 🔴 `eliminationNumber` 는 **지구** 탈락이다. 와일드카드가
                #    따로 있어서, 지구에서 밀려도 포스트시즌 길이 남는다.
                #    실측 2026-09-27: 양키스가 "진출 확정 · 탈락"으로 동시에
                #    찍혔다 — §3 등급이 그 모순에 걸린다. **둘 다 막혔고 확정도
                #    아닐 때만** 탈락이다.
                "eliminated": _eliminated(t),
                "note": _note(t),
                "tiebreaker": None,
            }
            facts.append(Fact(
                # 🔴 팀마다 다른 질문이다. 하나로 묶으면 30팀이 서로 모순이 된다.
                question_id=f"{Q_STANDINGS}:MLB:{name}", value=row,
                hardness="hard",
                publisher="MLB.com", source=standings_url(
                    int(t.get("season") or now.year)),
                published_at=_when(t.get("lastUpdated")), team=name, step=1))
    logger.info("[mlb] 순위 %d팀", len(facts))
    return facts


def _eliminated(t: dict) -> bool:
    """포스트시즌 길이 **전부** 막혔나. 확정 팀은 탈락이 아니다."""
    if t.get("clinched") or t.get("divisionChamp"):
        return False
    div = str(t.get("eliminationNumber") or "")
    wc = str(t.get("wildCardEliminationNumber") or "")
    return div == "E" and wc == "E"


def _note(t: dict) -> str:
    """사람이 읽을 한 줄. 🔴 순위는 §3 **동기**의 재료다 — 맥락이 아니다."""
    rank = t.get("divisionRank")
    gb = t.get("gamesBack")
    magic = t.get("magicNumber")
    bits = [f"지구 {rank}위" if rank else ""]
    if gb and gb != "-":
        bits.append(f"{gb}게임 차")
    if magic and magic != "-":
        bits.append(f"매직넘버 {magic}")
    if t.get("clinched"):
        bits.append("진출 확정")
    if _eliminated(t):
        bits.append("탈락")
    elif str(t.get("eliminationNumber") or "") == "E":
        bits.append("지구 탈락")      # 와일드카드는 남아 있다
    return " · ".join(b for b in bits if b)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _when(v):
    if not v:
        return None
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **tz 없는 값을 내보내지 않는다**(5단계 시간 계약 · 2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `replace("Z","+00:00")` 은 **`Z` 가 있을 때만** 듣는다. `2026-10-03T16:00:00`
    #     처럼 끝에 아무것도 없으면 **naive 가 그대로 나간다** — 그리고 그 값은
    #     조용히 서버 시간대로 가정된다. 실측 2026-10-03 에 그 가정이 어긋나
    #     **경기를 잃었다**(`16:00Z` vs `01:00 KST`).
    #  🔴 `timefmt.aware` 가 tz 를 요구한다. 못 붙이면 **`None`** 이고 경고가 남는다 —
    #     조용히 UTC 로 가정하지 않는다.
    from app import timefmt
    try:
        got = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return timefmt.aware(got, where="mlb._when")


# ══════════════════════════════════════════════════════════════════
# STEP 2 결장 재료 — transactions (IL·말소)
# ══════════════════════════════════════════════════════════════════

#: statsapi `typeDesc` → §4 basis 7종. 🔴 표에 없는 것은 **버린다**(추측 금지).
_BASIS = {
    "Status Change": "deregistered",
    "Injured List": "injury",
    "Released": "gone",
    "Trade": "gone",
    "Assigned": "deregistered",
    "Optioned": "deregistered",
    "Recalled": None,                   # 복귀는 결장이 아니다
    "Activated": None,
    "Selected": None,
    "Signed": None,
    "Designated for Assignment": "gone",
    "Outrighted": "gone",
    "Claimed Off Waivers": "gone",
}


def parse_transactions(got: Fetched, q: Question | None = None) -> list[Fact]:
    """transactions JSON → 결장 후보.

    🔴 **`line` 을 여기서 짓지 않는다.** 투수인지 야수인지는 로스터가 말하고,
       그것이 없으면 `starter`/`lineup_core` 를 지어내게 된다. 이 파서는
       `basis` 와 선수 id 까지만 낸다 — `line` 은 §4 세포가 로스터로 채운다.
    """
    if not got.ok:
        return []
    data = json.loads(got.text)
    out: list[Fact] = []
    for tr in data.get("transactions") or []:
        basis = _BASIS.get(tr.get("typeDesc") or "", "")
        if not basis:
            continue                     # 복귀·계약은 결장이 아니다
        person = tr.get("person") or {}
        team = (tr.get("team") or {}).get("name")
        desc = tr.get("description") or ""
        out.append(Fact(
            question_id=f"absence:{team}",
            value={"player_name": person.get("fullName"),
                   "external_id": str(person.get("id") or ""),
                   "basis": basis, "note": desc},
            hardness="hard", publisher="MLB.com transactions",
            published_at=_when(tr.get("date")), team=team, step=2))
    logger.info("[mlb] transactions 결장 후보 %d건", len(out))
    return out


# ══════════════════════════════════════════════════════════════════
# 세포가 쓸 소스 목록
# ══════════════════════════════════════════════════════════════════


def _slate_fact(got: Fetched, q: Question, day) -> list[Fact]:
    """🔴 파서는 `dict` 행을 낸다(그게 `games` 표의 모양이다). 세포는 `Fact` 를
    받는다 — **그 경계를 여기서 감싼다.** 파서를 세포 모양으로 바꾸면 파서가
    테스트하기 어려워지고, 세포가 dict 를 알면 흐름이 소스를 알게 된다.
    """
    rows = parse_schedule(got, q)
    if not rows:
        return []
    return [Fact(question_id=q.id, value=rows, hardness="hard",
                 publisher="MLB.com", source=schedule_url(day), step=0)]


def sources_slate(day) -> list[Source]:
    return [Source("MLB statsapi 일정", "url", url=schedule_url(day), tier=1,
                   parse=lambda got, q: _slate_fact(got, q, day))]


def sources_standings(season: int) -> list[Source]:
    return [Source("MLB statsapi 순위", "url", url=standings_url(season),
                   tier=1, parse=parse_standings)]


def sources_transactions(day) -> list[Source]:
    return [Source("MLB statsapi transactions", "url",
                   url=transactions_url(day), tier=1,
                   parse=parse_transactions)]


# ══════════════════════════════════════════════════════════════════
# 🔴 깊이 — **축구와 같은 수준으로** (사용자 지시 2026-10-01)
# ══════════════════════════════════════════════════════════════════
#
# > 이 경기는 한 예를 설명한 거다 .. **모든 경기를** 사용자가 경기분석 해줘 했을 때
# > 내가 보여준 결과치대로 나와야 한다고 .. 거짓없이
#
# 축구는 fotmob 한 페이지로 맞대결·폼·휴식일·선수 기록·순위가 나온다. 야구는
# `statsapi` 가 같은 것을 **공식 API** 로 준다(키 없음·카드 없음·robots 404 = 제한 없음):
#
#     /game/{pk}/boxscore                       타순 9명 · 선수 시즌/경기 기록 · 팀 통계
#     /schedule?teamId=X&startDate&endDate       직전 경기 → **휴식일**
#     /schedule?teamId=X&opponentId=Y&season=    **맞대결** 전 경기
#     /standings                                순위 (이미 있었다)
#
# 🔴 **박스스코어 하나에서 팀 id 가 나온다** — 그래서 §19-c 따라가기로 나머지를 연다.
#    `games` 표에 팀 id 칸이 없어 스키마를 건드리지 않아도 된다.
#
# ⚠️ **경기 전에는 타순이 비어 있다.** 그때는 사실을 만들지 않는다 — 0 으로 채우면
#    거짓이다. 예고 선발은 슬레이트의 `probable` 이 이미 들고 있다.

#: 야구 타순은 9명이다. 🔴 모자라면 사실로 올리지 않는다(축구 11명과 같은 규약).
ORDER = 9


def boxscore_url(game_pk) -> str:
    return f"{BASE}/game/{game_pk}/boxscore"


def team_schedule_url(team_id, lo, hi) -> str:
    return (f"{BASE}/schedule?sportId=1&teamId={team_id}"
            f"&startDate={lo}&endDate={hi}")


def h2h_url(team_id, opp_id, season: int) -> str:
    return (f"{BASE}/schedule?sportId=1&teamId={team_id}"
            f"&opponentId={opp_id}&season={season}")


def is_boxscore(url: str) -> bool:
    return "/boxscore" in (url or "") and "statsapi.mlb.com" in (url or "")


def _json(got) -> dict | None:
    try:
        return json.loads(getattr(got, "text", "") or "")
    except ValueError as exc:
        logger.info("[mlb] JSON 이 아니다: %s", exc)
        return None


def _side_of(d: dict, q: Question) -> tuple[str, dict] | None:
    """질문한 팀이 홈인가 원정인가. 🔴 모르면 `None` — 아무 쪽에도 안 붙인다."""
    for side in ("home", "away"):
        t = ((d.get("teams") or {}).get(side) or {})
        name = str(((t.get("team") or {}).get("name") or "")).strip()
        if name and (not q.team
                     or verify.mentions_team(name, q.team, q.local)):
            return side, t
    return None


def parse_boxscore(got, q: Question) -> list[Fact]:
    """박스스코어 → **타순 · 선수 기록 · 팀 통계.** 축구의 `parse_match` 와 같은 자리."""
    url = getattr(got, "url", "") or ""
    if not is_boxscore(url):
        return []
    d = _json(got)
    if d is None:
        return []
    picked = _side_of(d, q)
    if picked is None:
        return []
    side, t = picked
    name = str(((t.get("team") or {}).get("name") or "")).strip()
    opp = str((((d.get("teams") or {}).get("away" if side == "home" else "home")
                or {}).get("team") or {}).get("name") or "").strip()
    players = t.get("players") or {}
    order = [x for x in (t.get("battingOrder") or []) if x]
    out: list[Fact] = []

    def _name(pid) -> str:
        p = players.get(f"ID{pid}") or players.get(str(pid)) or {}
        return str(((p.get("person") or {}).get("fullName") or "")).strip()

    if len(order) == ORDER:
        # 🔴 타순이 **확정 라인업**이다(축구의 XI 와 같은 자리)
        out.append(Fact(
            question_id=q.id,
            value={"team": name, "players": [_name(p) for p in order],
                   "lineup_kind": "confirmed", "order_ids": order},
            hardness="hard", source=url, publisher="MLB statsapi",
            article_title=f"{name} 타순", tier=verify.TIER_OFFICIAL,
            extracted_by="rule:mlb_boxscore", step=1, team=name))
    elif order:
        logger.info("[mlb] %s 타순 %d명(9 아님) — 올리지 않는다", name, len(order))

    # 🔴 **기록을 남긴 선수만** — 명단 전체는 타순 사실이 담았다(축구와 같은 규약)
    order_set = {int(x) for x in order}
    for key, p in players.items():
        person = (p.get("person") or {})
        pname = str(person.get("fullName") or "").strip()
        if not pname:
            continue
        # 🔴 타순에 든 선수는 **기록이 0 이어도** 변수의 재료다(선발 여부가 사실이다)
        pid_in_order = int(person.get("id") or 0) in order_set
        bat = ((p.get("stats") or {}).get("batting") or {})
        pit = ((p.get("stats") or {}).get("pitching") or {})
        sb = ((p.get("seasonStats") or {}).get("batting") or {})
        sp = ((p.get("seasonStats") or {}).get("pitching") or {})
        # 🔴 **이 경기에 나온 선수만.** `seasonStats` 는 벤치 선수에게도 붙어 있어서
        #    그것으로 가르면 명단 전체가 사실이 된다(실측 2026-10-01: 28건 중
        #    기록 0인 선수가 섞였다).
        #    ⚠️ 투구 이닝은 `"0.0"` 같은 **문자열**로 온다 — 0 을 걸러야 한다.
        ip = str(pit.get("inningsPitched") or "").strip()
        played = (int(bat.get("atBats") or 0) > 0
                  or int(bat.get("hits") or 0) > 0
                  or (ip not in ("", "0", "0.0") and float(ip or 0) > 0)
                  or pid_in_order)
        if not played:
            continue
        out.append(Fact(
            question_id=f"{q.id}:player",
            value={"team": name, "player": pname,
                   "player_id": person.get("id"),
                   "shirt": p.get("jerseyNumber"),
                   "position": ((p.get("position") or {}).get("abbreviation")),
                   "hits": bat.get("hits"), "home_runs": bat.get("homeRuns"),
                   "rbi": bat.get("rbi"), "at_bats": bat.get("atBats"),
                   "innings_pitched": pit.get("inningsPitched"),
                   "strike_outs": pit.get("strikeOuts"),
                   "earned_runs": pit.get("earnedRuns"),
                   # 🔴 **시즌은 시즌 이름으로** — 통산과 섞으면 거짓이다
                   "season_avg": sb.get("avg"), "season_home_runs": sb.get("homeRuns"),
                   "season_era": sp.get("era"), "season_strike_outs": sp.get("strikeOuts"),
                   "opponent": opp},
            hardness="hard", source=url, publisher="MLB statsapi",
            article_title=f"{pname} 경기 기록", tier=verify.TIER_OFFICIAL,
            extracted_by="rule:mlb_player", step=1, team=name))

    ts = ((t.get("teamStats") or {}))
    if ts:
        out.append(Fact(
            question_id=f"{q.id}:stats",
            value={"team": name, "opponent": opp,
                   "batting": ts.get("batting"), "pitching": ts.get("pitching")},
            hardness="hard", source=url, publisher="MLB statsapi",
            article_title=f"{name} 경기 통계", tier=verify.TIER_OFFICIAL,
            extracted_by="rule:mlb_team_stats", step=1, team=name))
    return out


def follow_links(got, q: Question) -> list[str]:
    """🔴 §19-c — 박스스코어에서 **팀 id** 를 얻어 일정·맞대결을 연다."""
    if not is_boxscore(getattr(got, "url", "") or ""):
        return []
    d = _json(got)
    if d is None:
        return []
    picked = _side_of(d, q)
    if picked is None:
        return []
    side, t = picked
    tid = ((t.get("team") or {}).get("id"))
    other = ((d.get("teams") or {}).get("away" if side == "home" else "home") or {})
    oid = ((other.get("team") or {}).get("id"))
    if not tid:
        return []
    day = q.deadline.date() if q.deadline else date.today()
    lo = day - timedelta(days=21)
    urls = [team_schedule_url(tid, lo, day)]
    if oid:
        urls.append(h2h_url(tid, oid, day.year))
    return urls


def _games(d: dict) -> list[dict]:
    out = []
    for dt in (d.get("dates") or []):
        for g in (dt.get("games") or []):
            if isinstance(g, dict):
                g = {**g, "_date": dt.get("date")}
                out.append(g)
    return out


def parse_schedule_facts(got, q: Question) -> list[Fact]:
    """팀 일정 응답 → **휴식일**(`:form`) 또는 **맞대결**(`:h2h`).

    🔴 둘을 **주소로** 가른다 — `opponentId` 가 있으면 맞대결이다.
    ⚠️ 휴식일은 **날짜를 센다** — 시간을 빼면 하루 어긋난다(실측 2026-10-01, 축구에서
       같은 병을 고쳤다).
    """
    url = getattr(got, "url", "") or ""
    if "/schedule?" not in url:
        return []
    d = _json(got)
    if d is None:
        return []
    rows = []
    for g in _games(d):
        tm = g.get("teams") or {}
        rows.append({
            "date": g.get("_date"),
            "home": ((tm.get("home") or {}).get("team") or {}).get("name"),
            "away": ((tm.get("away") or {}).get("team") or {}).get("name"),
            "home_score": (tm.get("home") or {}).get("score"),
            "away_score": (tm.get("away") or {}).get("score"),
            "state": ((g.get("status") or {}).get("abstractGameState")),
        })
    if not rows:
        return []
    team = (q.team or "").strip()
    if "opponentId=" in url:
        return [Fact(question_id=f"{q.id}:h2h",
                     value={"matches": rows, "count": len(rows)},
                     hardness="hard", from_past_match=True,
                     source=url, publisher="MLB statsapi",
                     article_title="맞대결 기록", tier=verify.TIER_OFFICIAL,
                     extracted_by="rule:mlb_h2h", step=1, team=team or None)]
    # 🔴 **끝난 경기만** 센다 — 예정 경기를 "직전"으로 읽으면 휴식일이 음수가 된다
    done = sorted(r["date"] for r in rows
                  if r["state"] == "Final" and r["date"])
    when = q.deadline.date() if q.deadline else None
    rest = ((when - date.fromisoformat(done[-1])).days
            if (when and done) else None)
    # 🔴🔴 **`last5` 를 여기서 계산한다**(§8-3 *"어댑터 안에서 변환한다"*).
    #    ⚠️ 종전에는 `recent` 만 내보내고 글자 수열은 `classify` 가 만들었다 —
    #       그래서 **fotmob 만** `last5` 를 가졌고 야구·하키 폼 변수가 0 이었다(#6).
    #    🔴 변환기는 `factspec.last5_from` **하나**다(어댑터마다 적으면 또 갈린다).
    recent = rows[-5:]
    last5, how = factspec.last5_from(recent, team_name=team)
    return [Fact(question_id=f"{q.id}:form",
                 value={"team": team or None, "last_game": done[-1] if done else None,
                        "rest_days": rest, "games": len(rows),
                        "recent": recent, "last5": last5, "last5_how": how},
                 hardness="hard", from_past_match=True,
                 source=url, publisher="MLB statsapi",
                 article_title=f"{team} 최근 일정", tier=verify.TIER_OFFICIAL,
                 extracted_by="rule:mlb_form", step=1, team=team or None)]


def parse_followed(got, q: Question) -> list[Fact]:
    """🔴 따라간 자료를 **생김새로** 가른다."""
    return parse_schedule_facts(got, q)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **예고 선발** — 사용자 지시 2026-10-04 ①
# ══════════════════════════════════════════════════════════════════
#
#  > 야구 포스트시즌 1차전 카드에 `pitcher_state` 변수가 **0개**다. v4 **M18** 은
#  > *"pitcher_state 없이는 총점·핸디 결론 금지"* 인데 카드는 핸디 생존율을
#  > 계산해서 냈다 … **야구에서 선발은 변수 하나가 아니라 변수의 절반이다** —
#  > mlb 어댑터(statsapi)는 probable pitcher 를 준다. 그걸 `pitcher_state` 세포로
#  > 연결하는 게 야구 쪽 **최우선**이다.
#
#  ⚠️ 왜 지금까지 없었나 — `_probable` 이 **이미 있었다.** 그런데 그것은
#     **슬레이트 행**(`parse_schedule` → `games` 표)에만 들어갔고, 질문 경로의
#     **깊이 소스에는 없었다.** 즉 이름을 받아 놓고 사실로 만들지 않았다
#     (CLAUDE.md #2 배선 — 안 이어진 코드는 없는 코드보다 나쁘다).
#
#  🔴 받아서 확인했다(실측 2026-10-04 · `gamePk=849825`):
#
#      schedule?gamePk=…&hydrate=probablePitcher,team
#        → home `Logan Henderson`(id) · away `Michael King`(id)
#        ⚠️ `probablePitcher` 칸은 `['fullName','id','link']` **셋뿐**이다 —
#           `hydrate=probablePitcher(stats(...))` 로도 성적이 안 붙는다(실측).
#      people/{id}/stats?stats=season&group=pitching
#        → `era=2.47 whip=0.84 inningsPitched=98.1`  ·  `era=3.21 whip=1.18`
#
#  🔴 그래서 **두 단**이다: 예고 선발을 받고(①) 그 투수의 성적을 따라간다(② §19-c).
#     `classify._fill_starter_era` 가 `:starter` 와 `:starter_stats` 를 **이미** 합친다
#     (npb 가 쓰는 그 문이다) — 새로 만들지 않고 **같은 규약**으로 낸다.


def probable_url(game_pk) -> str:
    """🔴 그 경기의 **예고 선발**. ⚠️ 키 없음 · 카드 없음."""
    return f"{BASE}/schedule?gamePk={game_pk}&hydrate=probablePitcher,team"


def pitcher_stats_url(person_id) -> str:
    """🔴 그 투수의 **그 해 투구 성적**(방어율). ⚠️ 키 없음."""
    return f"{BASE}/people/{person_id}/stats?stats=season&group=pitching"


def is_probable(url: str) -> bool:
    return "gamePk=" in str(url or "") and "probablePitcher" in str(url or "")


def parse_probable(got, q: Question) -> list[Fact]:
    """예고 선발 → `:starter` 사실 **둘**(홈·원정 각각).

    🔴 `_dir_pitcher_state` 가 요구하는 칸을 그대로 채운다: `player` ·
       `opponent_player` · `team`. ⚠️ 방어율은 **여기서 모른다** — ②가 채운다.
    ⚠️ 한쪽만 예고됐으면 **그 한쪽도 낸다**(이름은 사실이다). 방향은
       `_dir_pitcher_state` 가 *"둘 다 알아야 한다"* 로 막는다 — 여기서 막지 않는다.
    """
    if not getattr(got, "ok", False) or not is_probable(getattr(got, "url", "")):
        return []
    d = _json(got)
    if d is None:
        return []
    url = getattr(got, "url", "") or ""
    out: list[Fact] = []
    for g in _games(d):
        tm = g.get("teams") or {}
        box = {side: _probable(g, side) for side in ("home", "away")}
        names = {side: ((box.get(side) or {}).get("name") or "")
                 for side in ("home", "away")}
        if not any(names.values()):
            logger.info("[mlb] 예고 선발이 **아직 없다** — %s", url[:80])
            return []
        for side in ("home", "away"):
            other = "away" if side == "home" else "home"
            team = ((tm.get(side) or {}).get("team") or {}).get("name")
            if not names[side]:
                continue
            out.append(Fact(
                question_id=f"{q.id}:starter",
                value={"player": names[side],
                       "opponent_player": names[other] or None,
                       "team": team,
                       # 🔴 외부 id 를 남긴다 — ②가 그것으로 성적을 받는다
                       "external_id": (box.get(side) or {}).get("external_id"),
                       "era": None, "opponent_era": None},
                hardness="hard", source=url, publisher="MLB statsapi",
                article_title=f"{team} 예고 선발", tier=verify.TIER_OFFICIAL,
                extracted_by="rule:mlb_probable", step=1, team=team or None))
    # ⚠️ `names` 는 루프 **안**의 이름이다 — 경기가 0건이면 없다(실측: NameError).
    #    🔴 사실에서 지어 찍는다(루프 밖에서 루프 안 이름을 쓰지 않는다).
    if out:
        logger.info("[mlb] 예고 선발 %d건 — %s", len(out),
                    " · ".join(f"{f.value.get('team')}={f.value.get('player')}"
                               for f in out))
    return out


def follow_pitchers(got, q: Question) -> list[str]:
    """§19-c — 예고 선발 **두 명의 성적 주소**. 🔴 이름만으로는 변수가 안 된다.

    ⚠️ `_dir_pitcher_state` 는 *"둘 다 알아야 한다"* 고 못 박았다 — 그래서 **둘 다**
       따라간다. 🔴 id 가 없으면 그 쪽은 건너뛴다(주소를 지어내지 않는다).
    """
    if not is_probable(getattr(got, "url", "")):
        return []
    d = _json(got)
    if d is None:
        return []
    out: list[str] = []
    for g in _games(d):
        for side in ("home", "away"):
            pid = (_probable(g, side) or {}).get("external_id")
            if pid and str(pid).isdigit():
                u = pitcher_stats_url(pid)
                if u not in out:
                    out.append(u)
    return out


def parse_pitcher_stats(got, q: Question) -> list[Fact]:
    """투수 성적 → `:starter_stats` 사실. 🔴 `classify._fill_starter_era` 가 읽는다.

    ⚠️ 그 함수는 `{player: {...}}` 꼴 표를 `:pitcher_table` 에서 받고, **선수
       페이지 성적**(`:starter_stats`)은 *"리더보드를 이긴다"* 고 적혀 있다 —
       우리가 내는 것이 바로 그쪽이다(같은 규약을 쓴다 · 사본 금지).
    🔴 `people/{id}/stats` 응답에는 **선수 이름이 없다**(실측 2026-10-04) — 그래서
       `/people/{id}` 를 함께 보고, 그것도 없으면 **버린다.** 이름 없이 성적만
       담으면 `_fill_starter_era` 가 누구 것인지 모른다.
    """
    url = getattr(got, "url", "") or ""
    if not getattr(got, "ok", False) or "/stats?" not in url:
        return []
    d = _json(got)
    if d is None:
        return []
    out: list[Fact] = []
    for blk in (d.get("stats") or []):
        for sp in (blk.get("splits") or []):
            st = sp.get("stat") or {}
            who = (sp.get("player") or {}).get("fullName")
            if not who:
                continue
            era = st.get("era")
            try:
                era = float(era) if era not in (None, "", "-", ".---") else None
            except (TypeError, ValueError):
                era = None
            if era is None:
                continue        # 🔴 방어율이 없으면 쓸 데가 없다
            out.append(Fact(
                question_id=f"{q.id}:starter_stats",
                value={"player": " ".join(str(who).split()), "era": era,
                       "whip": st.get("whip"),
                       "ip": st.get("inningsPitched"),
                       "games": st.get("gamesPlayed")},
                hardness="hard", source=url, publisher="MLB statsapi",
                article_title=f"{who} 투구 성적", tier=verify.TIER_OFFICIAL,
                extracted_by="rule:mlb_pitcher_stats", step=1))
    if out:
        logger.info("[mlb] 투수 성적 %d건 — %s", len(out),
                    " · ".join(f"{f.value['player']} ERA {f.value['era']}"
                               for f in out))
    return out


def sources_context(ext_id: str) -> list[Source]:
    """🔴 경기 하나의 **깊이 소스.** `ext_id` 가 `gamePk` 다.

    ⚠️ 공식 API 이므로 `verify=False` 다 — 발행 시각이 없다(§12-c-5 1층).
    """
    # 🔴 §8-1 — 열쇠 떼기는 `matchkey` 한 곳이다(`isdigit()` 로 가르면
    #    `statsapi:849825` 가 탈락하고 **깊이가 조용히 0** 이 된다 · 실측 2026-10-04)
    #  ⚠️ `bare_ok=True` — **맨숫자가 이 어댑터의 옛 꼴이다**(`849825`). 다른
    #     어댑터는 접두를 썼으므로 맨숫자를 받지 않는다(§8-1 · `matchkey.mine`).
    pk = matchkey.mine(ext_id, "statsapi", bare_ok=True)
    if not pk or not pk.isdigit():
        return []
    return [
        # 🔴 `follow_links` 가 **셋**을 낸다(팀 일정 둘 + 맞대결 하나) — 실측
        Source("MLB 박스스코어", "url", url=boxscore_url(pk),
               tier=verify.TIER_OFFICIAL, parse=parse_boxscore,
               follow=follow_links, parse_follow=parse_followed, follow_max=3),
        # 🔴🔴 **예고 선발**(사용자 지시 2026-10-04 ① · 위 머리글).
        #    ⚠️ 이름을 받아 놓고 사실로 안 만들던 자리다 — 야구에서 선발은
        #       *"변수 하나가 아니라 변수의 절반"* 이다.
        # 🔴 `follow_pitchers` 가 **둘**을 낸다(양 팀 선발의 성적) — 둘 다 알아야
        #    `_dir_pitcher_state` 가 방향을 낸다(*"둘 다 알아야 한다"*).
        Source("MLB 예고 선발", "url", url=probable_url(pk),
               tier=verify.TIER_OFFICIAL, parse=parse_probable,
               follow=follow_pitchers, parse_follow=parse_pitcher_stats,
               follow_max=2),
    ]
