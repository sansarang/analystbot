"""하키(NHL) 일정 — `api-web.nhle.com`. 🔴 **키 없음·카드 없음·무료**(§19-i-1).

⚠️ **v4 문서에 없는 종목이다.** §9 단계 9 가 이름을 댄 리그는 `KBO·NPB·MLB·K리그·
   해외축구` 뿐이다 — 야구와 축구만이다. 하키는 **사용자 지시 2026-10-01**
   *"야구 축구 하키 농구 배구 경기를 … 저장이 되어 있어야 한다"* 로 들어왔다.
   → `docs/fable/questions/2026-10-01_five_sports.md`

🔴 **이 소스의 값어치**: 한 번 부르면 **당일·내일·모레**가 함께 온다(`gameWeek`).
   사용자가 요구한 *"당일 및 그다음 날짜 터울은 하루"* 가 한 요청으로 채워진다.
   실측 2026-09-30: `2026-09-30 3경기 · 10-01 8경기 · 10-02 5경기`.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from app import factspec, league, matchkey, rules, verify, window
from app.blackboard import Fact
from app.cells import Question, Source
from app.net import Fetched

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))
LEAGUE = "NHL"
SPORT = "hockey"

#: 🔴 이 주소 하나가 원본이다 — 문서에 베끼지 않는다.
BASE = "https://api-web.nhle.com/v1/schedule"

#: NHL `gameState` → 우리 규약. 🔴 사본 금지 — 읽는 쪽이 다시 적지 않는다.
#: ⚠️ 표에 없는 값은 `scheduled` 로 때우지 않는다 — **이름으로 남긴다**(아래).
STATE = {
    "FUT": "scheduled", "PRE": "scheduled",
    "LIVE": "inprogress", "CRIT": "inprogress",
    "OFF": "final", "FINAL": "final",
    "PPD": "postponed", "SUSP": "postponed", "CNCL": "postponed",
}


def schedule_url(day: date) -> str:
    """🔴 **하루 앞에서 시작해 받는다.** 응답이 한 주를 주므로 그 안에 KST 기준
    그날 경기가 다 들어온다(북미 현지 날짜와 KST 가 하루 어긋나기 때문).
    """
    return f"{BASE}/{day - timedelta(days=1):%Y-%m-%d}"


def parse_schedule(got: Fetched, day: date | None = None) -> list[dict]:
    """NHL 주간 일정 → `games` 행. 🔴 **요청한 날짜만** 골라 낸다.

    ⚠️ 응답은 **한 주**를 준다. 그것을 전부 적으면 `_slate` 가 요청하지 않은 날까지
       쓴다 — §14-9(*"요청받은 리그·날짜만 슬레이트에 넣는다"*) 위반이다.
       🔴 다른 날 것은 버리지 않고 **호출부가 따로 요청**한다(`sources_slate(day)`).
    """
    if not got.ok:
        return []
    try:
        data = json.loads(got.text)
    except ValueError as exc:
        logger.warning("[nhl] JSON 이 아니다: %s", exc)
        return []

    out: list[dict] = []
    skipped: list[str] = []      # 🔴 창 밖인 경기 — 사유로 남긴다(#3)
    for wk in data.get("gameWeek") or []:
        for g in wk.get("games") or []:
            row = _row(g)
            if not row:
                continue
            # 🔴 **KST 날짜로 거른다 — API 의 날짜 버킷이 아니다.**
            #    NHL 의 버킷은 북미 현지 날짜다. 10-01 저녁(ET) 경기는 KST 로
            #    **10-02** 다 — 버킷으로 거르면 하루씩 어긋난 채 저장된다.
            #    ⚠️ 우리 `games.starts_kst` 가 KST 이므로 거르는 기준도 KST 여야
            #       한 곳만 보고도 슬레이트가 맞는다(§14-9).
                # ══════════════════════════════════════════════════════════
            # 🔴🔴 **창으로 거른다** — 지금부터 36시간(UTC) · 지시 2026-10-04
                # ══════════════════════════════════════════════════════════
            #
            #  ⚠️ 종전엔 **KST 달력 날짜**가 같아야 통과였다. 🔴 유럽·북미 저녁
            #     경기는 KST 로 **내일**이라(유럽 20:45 = KST 03:45) *"오늘의 경기"*
            #     가 **구조적으로 전부** 떨어졌다(실측: 포르투갈 vs 노르웨이).
            #  🔴 수는 `app/window.py` **한 곳**에 있다(사본 금지).
            said = window.why_out(row["starts_utc"])
            if said:
                skipped.append(f"{row.get('home')}–{row.get('away')}: {said}")
                continue
            out.append(row)
    if skipped:
        logger.info("[nhl] 창 밖 %d경기 — %s", len(skipped),
                    " · ".join(skipped[:3]))
    logger.info("[nhl] %s 일정 %d경기", day, len(out))
    return out


def _row(g: dict) -> dict | None:
    start = _when(g.get("startTimeUTC"))
    if start is None:
        return None                     # 🔴 시각을 모르면 슬레이트에 안 넣는다
    home = _team(g.get("homeTeam"))
    away = _team(g.get("awayTeam"))
    if not (home and away):
        return None
    raw = str(g.get("gameState") or "")
    status = STATE.get(raw)
    if status is None:
        # 🔴 **조용히 `scheduled` 로 때우지 않는다.** 모르는 상태를 예정으로 읽으면
        #    끝난 경기를 분석 대상으로 넣는다(§2: 진행 중·종료는 대상이 아니다).
        logger.info("[nhl] 모르는 gameState=%r — scheduled 로 때우지 않는다", raw)
        status = "scheduled" if raw in ("", None) else f"unknown:{raw}"
    return {
        "sport": SPORT, "league": LEAGUE,
        # 🔴 §8-1 — `출처:경기ID`
        "ext_id": matchkey.make("nhl", g.get("id")),
        "home": home, "away": away,
        "home_id": (g.get("homeTeam") or {}).get("id"),
        "away_id": (g.get("awayTeam") or {}).get("id"),
        "venue": ((g.get("venue") or {}).get("default")),
        "starts_utc": start,
        "starts_kst": start.astimezone(KST),
        "starts_local": None,           # 🔴 현지 시각은 응답에 없다 — 지어내지 않는다
        "status": status,
        "round_note": None,
        "home_score": (g.get("homeTeam") or {}).get("score"),
        "away_score": (g.get("awayTeam") or {}).get("score"),
        # 하키에는 예고 선발(투수)이 없다 — 골리는 경기 직전에 나온다
        "probable": {},
    }


def _team(t: dict | None) -> str:
    """팀 이름. 🔴 **정식명을 쓴다** — 약칭만 쓰면 기사와 못 맞춘다."""
    t = t or {}
    for key in ("commonName", "placeName"):
        got = t.get(key)
        if isinstance(got, dict) and got.get("default"):
            place = (t.get("placeName") or {}).get("default") or ""
            name = (t.get("commonName") or {}).get("default") or ""
            full = f"{place} {name}".strip()
            if full:
                return full
    return str(t.get("abbrev") or "")


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
    return timefmt.aware(got, where="nhl._when")


# ══════════════════════════════════════════════════════════════════
# 세포가 쓸 소스 목록
# ══════════════════════════════════════════════════════════════════


def _slate_fact(got: Fetched, q: Question, day: date) -> list[Fact]:
    """🔴 파서는 `dict` 행을 낸다 — 세포 경계에서 `Fact` 로 감싼다(mlb·npb 와 같다)."""
    rows = parse_schedule(got, day)
    if not rows:
        return []
    return [Fact(question_id=q.id, value=rows, hardness="hard",
                 publisher="NHL", source=schedule_url(day), step=0)]


def sources_slate(day: date) -> list[Source]:
    """🔴 공식 API 이므로 `verify=False` 다 — 발행 시각이 없다(§12-c-5 1층)."""
    return [Source("NHL api-web 일정", "url", url=schedule_url(day), tier=1,
                   parse=lambda got, q: _slate_fact(got, q, day))]


# ══════════════════════════════════════════════════════════════════
# 🔴 깊이 — **축구·야구와 같은 수준으로** (사용자 지시 2026-10-01)
# ══════════════════════════════════════════════════════════════════
#
# > **모든 경기를** 사용자가 경기분석 해줘 했을 때 내가 보여준 결과치대로 .. 거짓없이
#
# `api-web.nhle.com` 이 공식으로 준다(키 없음·카드 없음·robots 404 = 제한 없음):
#
#     /gamecenter/{id}/boxscore          팀 약칭·구장·상태 (경기 후에는 선수 기록)
#     /club-schedule-season/{약칭}/now    시즌 전 일정 → **휴식일 · 맞대결**
#     /club-stats/{약칭}/now              선수 시즌 기록(스케이터·골리)
#     /standings/now                     순위(디비전·콘퍼런스)
#
# 🔴 **박스스코어에서 약칭이 나온다** — §19-c 따라가기로 나머지를 연다.
#    `games` 표에 약칭 칸이 없어 스키마를 건드리지 않아도 된다.
#
# ⚠️ **하키에는 경기 전 라인업이 없다.** 골리도 경기 직전에 나온다 — 그래서
#    `:baseline` 을 만들지 않는다. 있는 척하지 않는다(이 파일 머리글이 이미 그렇게
#    적어 뒀다: *"하키에는 예고 선발(투수)이 없다"*).

API = "https://api-web.nhle.com/v1"


def boxscore_url(game_id) -> str:
    return f"{API}/gamecenter/{game_id}/boxscore"


def club_schedule_url(abbrev: str) -> str:
    return f"{API}/club-schedule-season/{abbrev}/now"


def club_stats_url(abbrev: str) -> str:
    return f"{API}/club-stats/{abbrev}/now"


def standings_url() -> str:
    return f"{API}/standings/now"


def game_id_of(ext_id: str) -> str:
    """`nhl-2026020021` → `2026020021`. 🔴 꼴이 아니면 빈 문자열."""
    # 🔴 §8-1 — `matchkey` 가 뗀다(`nhl:2026020021` 도 `nhl-…` 도 읽는다).
    #    ⚠️ 종전 `split("-")[-1]` 은 `출처:ID` 꼴을 통째로 돌려줘 숫자 검사에
    #       걸렸고 **깊이가 조용히 0** 이 됐다(실측 2026-10-04).
    tail = matchkey.mine(ext_id, "nhl")
    return tail if tail.isdigit() else ""


def _json(got) -> dict | None:
    try:
        return json.loads(getattr(got, "text", "") or "")
    except ValueError as exc:
        logger.info("[nhl] JSON 이 아니다: %s", exc)
        return None


def _mine(d: dict, q: Question) -> tuple[str, dict, dict] | None:
    """질문한 팀의 약칭·내 블록·상대 블록. 🔴 모르면 `None`."""
    from app import factspec, verify as V
    for key, other in (("homeTeam", "awayTeam"), ("awayTeam", "homeTeam")):
        t = d.get(key) or {}
        name = _team(t) or str(t.get("abbrev") or "")
        if name and (not q.team or V.mentions_team(name, q.team, q.local)):
            return str(t.get("abbrev") or ""), t, (d.get(other) or {})
    return None


def parse_boxscore(got, q: Question) -> list[Fact]:
    """박스스코어 → 구장·상태, 그리고 **경기 후에는** 선수 기록."""
    url = getattr(got, "url", "") or ""
    if "/gamecenter/" not in url:
        return []
    d = _json(got)
    if d is None:
        return []
    picked = _mine(d, q)
    if picked is None:
        return []
    abbrev, me, opp = picked
    name = _team(me) or abbrev
    out = [Fact(
        question_id=f"{q.id}:info",
        value={"team": name, "abbrev": abbrev,
               "opponent": _team(opp) or str(opp.get("abbrev") or ""),
               "venue": ((d.get("venue") or {}).get("default")),
               "game_state": d.get("gameState"),
               "game_date": d.get("gameDate")},
        hardness="hard", source=url, publisher="NHL api-web",
        article_title=f"{name} 경기 정보", tier=verify.TIER_OFFICIAL,
        extracted_by="rule:nhl_boxscore", step=1, team=name)]
    # 🔴 경기 전에는 선수 기록이 **없다** — 0 으로 채우지 않는다
    pg = d.get("playerByGameStats") or {}
    side = "homeTeam" if (d.get("homeTeam") or {}).get("abbrev") == abbrev \
        else "awayTeam"
    block = pg.get(side) or {}
    for group in ("forwards", "defense", "goalies"):
        for p in (block.get(group) or []):
            nm = str(((p.get("name") or {}).get("default") or "")).strip()
            if not nm:
                continue
            out.append(Fact(
                question_id=f"{q.id}:player",
                value={"team": name, "player": nm, "player_id": p.get("playerId"),
                       "position": p.get("position") or group,
                       "goals": p.get("goals"), "assists": p.get("assists"),
                       "points": p.get("points"), "shots": p.get("sog"),
                       "toi": p.get("toi"), "saves": p.get("saves"),
                       "save_pct": p.get("savePctg")},
                hardness="hard", source=url, publisher="NHL api-web",
                article_title=f"{nm} 경기 기록", tier=verify.TIER_OFFICIAL,
                extracted_by="rule:nhl_player", step=1, team=name))
    return out


def follow_links(got, q: Question) -> list[str]:
    """🔴 §19-c — 박스스코어의 **약칭**으로 일정·선수·순위를 연다."""
    if "/gamecenter/" not in (getattr(got, "url", "") or ""):
        return []
    d = _json(got)
    if d is None:
        return []
    picked = _mine(d, q)
    if picked is None or not picked[0]:
        return []
    a = picked[0]
    return [club_schedule_url(a), club_stats_url(a), standings_url()]


def _rows(d: dict) -> list[dict]:
    out = []
    for g in (d.get("games") or []):
        if not isinstance(g, dict):
            continue
        out.append({"date": g.get("gameDate"),
                    "home": (g.get("homeTeam") or {}).get("abbrev"),
                    "away": (g.get("awayTeam") or {}).get("abbrev"),
                    "home_score": (g.get("homeTeam") or {}).get("score"),
                    "away_score": (g.get("awayTeam") or {}).get("score"),
                    "state": g.get("gameState")})
    return out


def parse_club_schedule(got, q: Question) -> list[Fact]:
    """시즌 일정 → **휴식일**(`:form`) + **맞대결**(`:h2h`).

    ⚠️ 휴식일은 **날짜를 센다** — 시간을 빼면 하루 어긋난다(축구에서 고친 그 병).
    🔴 끝난 경기만 센다 — 예정 경기를 "직전"으로 읽으면 휴식일이 음수가 된다.
    """
    url = getattr(got, "url", "") or ""
    if "/club-schedule-season/" not in url:
        return []
    d = _json(got)
    if d is None:
        return []
    rows = _rows(d)
    if not rows:
        return []
    team = (q.team or "").strip()
    done = sorted(r["date"] for r in rows
                  if str(r["state"]).upper() in ("FINAL", "OFF") and r["date"])
    when = q.deadline.astimezone(KST).date() if q.deadline else None
    rest = ((when - date.fromisoformat(done[-1])).days
            if (when and done) else None)
    # 🔴 §8-3 — `last5` 를 **어댑터 안에서** 계산한다(위 mlb 주석과 같은 까닭)
    recent = [r for r in rows
              if r["date"] and (not done or r["date"] <= done[-1])][-5:]
    last5, how = factspec.last5_from(recent, team_name=team)
    out = [Fact(question_id=f"{q.id}:form",
                value={"team": team or None,
                       "last_game": done[-1] if done else None,
                       "rest_days": rest, "games": len(rows),
                       "recent": recent, "last5": last5, "last5_how": how},
                hardness="hard", from_past_match=True,
                source=url, publisher="NHL api-web",
                article_title=f"{team} 최근 일정", tier=verify.TIER_OFFICIAL,
                extracted_by="rule:nhl_form", step=1, team=team or None)]
    # 🔴 **맞대결은 같은 응답에서 걸러 낸다** — 따로 요청하지 않는다(요청 수가 곧 비용)
    opp = (q.opponent or "").strip()
    if opp:
        oa = opp[:3].upper()
        met = [r for r in rows if r["date"] and
               (str(r["home"] or "") == oa or str(r["away"] or "") == oa)]
        # 🔴 **끝난 경기만 맞대결이다.** 예정 경기를 섞으면 *"지난 대결 결과"* 가
        #    `null` 로 들어온다(실측 2026-10-01: 바로 오늘 경기가 섞였다).
        #    ⚠️ 남은 맞대결 수는 **이름으로** 적는다 — 버리지 않는다.
        h2h = [r for r in met if str(r["state"]).upper() in ("FINAL", "OFF")]
        if h2h:
            out.append(Fact(
                question_id=f"{q.id}:h2h",
                value={"matches": h2h, "count": len(h2h),
                       "scheduled_left": len(met) - len(h2h),
                       "note_opponent": oa},
                hardness="hard", from_past_match=True,
                source=url, publisher="NHL api-web",
                article_title="맞대결 기록", tier=verify.TIER_OFFICIAL,
                extracted_by="rule:nhl_h2h", step=1, team=team or None))
    return out


def parse_club_stats(got, q: Question) -> list[Fact]:
    """선수 **시즌** 기록. 🔴 통산과 섞지 않는다 — 칸 이름이 `season_*` 이다."""
    url = getattr(got, "url", "") or ""
    if "/club-stats/" not in url:
        return []
    d = _json(got)
    if d is None:
        return []
    team = (q.team or "").strip()
    out: list[Fact] = []
    for group in ("skaters", "goalies"):
        for p in (d.get(group) or []):
            nm = " ".join(x for x in (
                ((p.get("firstName") or {}).get("default") or ""),
                ((p.get("lastName") or {}).get("default") or "")) if x).strip()
            if not nm:
                continue
            out.append(Fact(
                question_id=f"{q.id}:player",
                value={"team": team or None, "player": nm,
                       "player_id": p.get("playerId"),
                       "position": p.get("positionCode") or group,
                       "season_games": p.get("gamesPlayed"),
                       "season_goals": p.get("goals"),
                       "season_assists": p.get("assists"),
                       "season_points": p.get("points"),
                       "season_plus_minus": p.get("plusMinus"),
                       "season_save_pct": p.get("savePercentage")},
                hardness="hard", from_past_match=True,
                source=url, publisher="NHL api-web",
                article_title=f"{nm} 시즌 기록", tier=verify.TIER_OFFICIAL,
                extracted_by="rule:nhl_club_stats", step=1, team=team or None))
    return out


#: 🔴 홈/원정 쪼갠 줄의 칸 이름. **API 가 원본이다** — 여기서 새로 만들지 않는다.
_SPLIT = {"home": ("homeGamesPlayed", "homeGoalsFor", "homeGoalsAgainst",
                   "homeWins", "homeLosses", "homeOtLosses"),
          "road": ("roadGamesPlayed", "roadGoalsFor", "roadGoalsAgainst",
                   "roadWins", "roadLosses", "roadOtLosses")}


def _split_rows(rows: list[dict], side: str) -> list[dict]:
    """한쪽 장소의 표를 `league.TABLE_FIELDS` 공통 꼴로.

    🔴 **못 읽은 칸은 `None`** — 0 으로 때우면 "0골"이라는 거짓이 된다.
    """
    gp, gf, ga, w, lo, otl = _SPLIT[side]
    out = []
    for r in rows:
        if not isinstance(r, dict) or r.get(gp) is None:
            continue
        out.append({"team": str(((r.get("teamName") or {}).get("default")
                                 or "")).strip(),
                    "played": r.get(gp), "wins": r.get(w),
                    "draws": None, "losses": r.get(lo),
                    "ot_losses": r.get(otl), "points": None,
                    "goals_for": r.get(gf), "goals_against": r.get(ga),
                    "goal_diff": None})
    return out


def _derived(rows: list[dict]) -> dict:
    """§5-c-1 문턱 · §6-c-3 기준선 · §4 `home_field` 의 재료.

    🔴 **축구와 같은 이름을 낸다**(`fotmob._derived`). 이름이 갈리면 단계 5~7 이
       종목별 분기를 써야 하고, 분기는 한 종목이 바뀔 때 다른 종목을 조용히 깬다.
    ⚠️ 하키는 **리그 하나**다(콘퍼런스로 쪼개지 않는다) — `league_tables` 는 1 이다.
    """
    allr = [{"team": str(((r.get("teamName") or {}).get("default") or "")).strip(),
             "played": r.get("gamesPlayed"), "goals_for": r.get("goalFor"),
             "goals_against": r.get("goalAgainst")}
            for r in rows if isinstance(r, dict)]
    homes = _split_rows(rows, "home")
    aways = _split_rows(rows, "road")
    return {
        "league_avg_goals": league.avg_goals(allr),
        "total_baseline": league.baseline_total(allr),
        "open_game_threshold": league.open_game_threshold(allr),
        "home_advantage": league.home_advantage(homes, aways),
        "venue_averages": league.venue_averages(homes, aways),
        "venue_rows": {"home": homes, "away": aways} if homes and aways else None,
        "league_tables": 1,
        # 🔴 **플레이오프 경계는 리그 규정이다** — API 는 `divisionSequence`·
        #    `wildcardSequence` 를 주지만 *"3"·"2"* 라는 수는 주지 않는다.
        #    사용자 지시 2026-10-02 로 `config/playoff_cuts.yaml` 에 **출처와 확인
        #    날짜를 붙여** 선언했다. ⚠️ 없으면 `None` — 지어내지 않는다.
        **_cut(),
    }


def _cut() -> dict:
    """§4 `stakes` 가 쓰는 경계. 🔴 **값은 yaml 이 원본이다**(사본 금지)."""
    cfg = rules.playoff_cut("NHL")
    if not cfg or cfg.get("unknown"):
        return {"cut_lines": None, "playoff_cut": None,
                "cut_reason": cfg.get("unknown") or "NHL 경계 선언이 없다"}
    top = cfg.get("division_top")
    wc = cfg.get("wildcard_slots")
    if top is None or wc is None:
        return {"cut_lines": None, "playoff_cut": None,
                "cut_reason": "선언에 division_top·wildcard_slots 가 없다"}
    return {
        # 🔴 **경계가 둘이다** — 디비전 안 순위와 와일드카드 순번. 하나로 뭉개면
        #    "5위인데 진출권"을 설명할 수 없다(와일드카드로 들어가는 자리다).
        "cut_lines": {f"디비전 상위 {top}": int(top),
                      f"와일드카드 {wc}장": int(wc)},
        # ⚠️ `playoff_cut` 은 **한 수를 쓰는 쪽**을 위한 칸이다. 하키는 두 경계가
        #    있으므로 **디비전 쪽**을 쓴다(그 사실을 사유에 적는다).
        "playoff_cut": int(top),
        "cut_reason": (f"{cfg['rule']} — 디비전 상위 {top} + 와일드카드 {wc} "
                       f"(출처 {cfg.get('source')} · 확인 {cfg.get('verified')})"),
        "cut_fields": {"division": cfg.get("division_field"),
                       "wildcard": cfg.get("wildcard_field")},
    }


def parse_standings(got, q: Question) -> list[Fact]:
    """순위. 🔴 **디비전·콘퍼런스를 함께** 싣는다 — 안 적으면 순위가 무슨 뜻인지 모른다."""
    url = getattr(got, "url", "") or ""
    if "/standings" not in url:
        return []
    d = _json(got)
    if d is None:
        return []
    from app import verify as V
    team = (q.team or "").strip()
    for r in (d.get("standings") or []):
        nm = str(((r.get("teamName") or {}).get("default") or "")).strip()
        if not nm or (team and not V.mentions_team(nm, team, q.local)):
            continue
        return [Fact(
            question_id=f"{q.id}:standings",
            # 🔴 **공통 꼴**(`league.TABLE_FIELDS`) — 세 종목이 같은 이름을 낸다.
            #    ⚠️ 하키에는 무승부가 없다 — `draws` 는 **`None`** 이다.
            #       0 으로 때우면 "무승부가 0회"라는 거짓이 된다(조용한 0 금지).
            value={"team": nm, "table": r.get("divisionName"),
                   "rank": r.get("divisionSequence"),
                   "draws": None,
                   "conference": r.get("conferenceName"),
                   "conference_rank": r.get("conferenceSequence"),
                   "played": r.get("gamesPlayed"), "wins": r.get("wins"),
                   "losses": r.get("losses"), "ot_losses": r.get("otLosses"),
                   "points": r.get("points"),
                   "goal_diff": r.get("goalDifferential"),
                   "goals_for": r.get("goalFor"), "goals_against": r.get("goalAgainst"),
                   # 🔴 **파생 측정을 함께 싣는다**(사용자 지시 2026-10-02).
                   #    실측 라이브: `home_field` 가 *"홈/원정 쪼갠 표가 없다"* 로
                   #    미결정이었다 — 그런데 **이 응답이 그 칸을 다 들고 있었다**
                   #    (`homeGoalsFor`·`roadGoalsFor` …). 안 뽑고 있던 것이다.
                   #    ⚠️ 축구와 **같은 이름**을 낸다(`fotmob._derived`) — 이름이
                   #       갈리면 단계 5~7 이 종목별 분기를 써야 한다.
                   **_derived(d.get("standings") or [])},
            hardness="soft",
            source=url, publisher="NHL api-web",
            article_title=f"{nm} 순위", tier=verify.TIER_OFFICIAL,
            extracted_by="rule:nhl_standings", step=1, team=nm)]
    return []


def parse_followed(got, q: Question) -> list[Fact]:
    """🔴 따라간 자료를 **주소로** 가른다."""
    url = getattr(got, "url", "") or ""
    if "/club-schedule-season/" in url:
        return parse_club_schedule(got, q)
    if "/club-stats/" in url:
        return parse_club_stats(got, q)
    if "/standings" in url:
        return parse_standings(got, q)
    return []


def sources_context(ext_id: str) -> list[Source]:
    """🔴 경기 하나의 **깊이 소스.** `ext_id` 는 `nhl-{경기번호}` 다."""
    gid = game_id_of(ext_id)
    if not gid:
        return []
    return [Source("NHL 박스스코어", "url", url=boxscore_url(gid),
                   tier=verify.TIER_OFFICIAL, parse=parse_boxscore,
                   follow=follow_links, parse_follow=parse_followed,
            # 🔴 `follow_links` 가 **셋**을 낸다(일정·팀 성적·순위) — 실측.
            #    ⚠️ 몫을 안 적으면 깊이 예산이 조용히 샌다(2026-10-04 · MLB 가
            #       그 병으로 둘째 소스를 한 번도 못 돌렸다).
            follow_max=3)]
