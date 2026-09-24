"""[§2] 결장 정보 — statsapi(IL 명단 + 확정 라인업)로 자체 산출.

그동안 결장은 Perplexity 산문에서만 왔고, 리서치가 없으면 λ의 ⑦단계가
통째로 건너뛰어졌다(실측 2026-08-25: 15경기 전부 미반영).

두 가지 근거를 구분한다 — 이게 이 모듈의 핵심이다:

- **라인업 확정**: 오늘 타순 9명이 확정된 경기. 최근 타석 상위 9명 중
  오늘 타순에 없는 선수가 곧 결장이다. IL이 아니어도(휴식·부진) 잡힌다.
- **IL 명단**: 라인업 미확정 경기. 부상자 명단만으로 판단하므로
  "오늘 쉬는 주전"은 놓친다 — 근거가 약하다는 뜻이고, 그대로 표기한다.

중요도는 Statcast **타석 수 상위 9명**으로 가른다. IL 명단만으로는 그 선수가
팀에 얼마나 중요한지 알 수 없다.

⚠️ 선수 대조는 이름이 아니라 **MLBAM id**로 한다. Statcast의 `player_name`은
투수 이름이라 타자에 쓸 수 없고, statsapi도 같은 id 체계를 쓴다.
"""

import logging

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
# [ABS-1] 결장 근거(basis) — **만든 쪽이 적는다.**
#
# 🔴 읽는 쪽이 문장을 정규식으로 되짚으면 그것이 사본이고, 사본은 원본이
#    바뀔 때 따라가지 않는다(워치독 오탐 4건이 전부 그 실수였다).
#    그래서 표지 문자열을 **여기 한 번** 적고 생산자들이 가져다 쓴다.
# 🔴 표지를 바꾸면 문장이 바뀌고, 문장이 바뀌면 λ 계수가 바뀐다
#    (`_describe` 머리말 · `scoring._absence_factors`). 표지는 건드리지 않는다.
# ══════════════════════════════════════════════════════════════════

BASIS_IL = "IL"                          # 부상자 명단
BASIS_LINEUP = "lineup_excluded"         # 오늘 확정 라인업에서 빠짐
BASIS_TRANSFERMARKT = "transfermarkt"    # 축구 — 이적/결장 정보
BASIS_FOTMOB = "fotmob_unavailable"      # 축구 — FotMob `unavailable`

BASES = (BASIS_IL, BASIS_LINEUP, BASIS_TRANSFERMARKT, BASIS_FOTMOB)

#: 이 모듈이 쓰는 표지 — `_describe(..., reason="라인업 제외")`.
MARK_LINEUP_EXCLUDED = "라인업 제외"
#: `lineup_diff.merge_absences_from_diff` 가 쓰는 표지. 🔴 거기서 손으로 적지 않는다.
MARK_TODAY_OUT = "오늘 라인업에서 빠짐"
#: IL 문장의 표지. statsapi `status` 가 `Injured 10-Day` 꼴로 들어온다.
MARK_INJURED = "Injured"
#: IL 이 상태 문구를 못 준 경우의 기본값(`from_injured` 가 쓴다).
MARK_IL_DEFAULT = "부상자 명단"


#: [PIPE-5 2026-09-25] **역할 표지.** `_describe`·`from_injured` 가 괄호 안에
#  적는 말이다. 🔴 읽는 쪽이 정규식으로 되짚으면 사본이다 — 여기가 원본이다.
ROLE_TOP = "주포"
ROLE_REGULAR = "주전 타자"
ROLE_PLAYER = "선수"
ROLE_STARTER = "선발"
ROLE_BULLPEN = "불펜"
#: 투수 역할. 🔴 타순에 없는 사람들이다 — `lineup_out`(타순 결장)이 아니다.
PITCHER_ROLES = (ROLE_STARTER, ROLE_BULLPEN)
BATTER_ROLES = (ROLE_TOP, ROLE_REGULAR, ROLE_PLAYER)


def is_pitcher_line(sentence: str) -> bool:
    """[PIPE-5] 이 결장 문장이 **투수**의 것인가.

    🔴 왜 가르는가. `from_injured` 는 투수도 결장 문장으로 만든다. 그런데
       `lineup_out` 은 **타순에서 빠진 수**를 재는 변수다 — IL 에 오른 불펜
       투수를 거기 세면 "결장 18명" 같은 숫자가 서술·내보내기로 나간다
       (실측 2026-09-25 TB@NYY: 18건 중 9건이 투수).
    🔴 투수 결장은 `starter_recent3`·`bullpen_3d` 가 따로 본다 — 버리는 것이
       아니라 **다른 칸으로 보내는 것**이다.
    ⚠️ 표지는 위 상수가 원본이다. 여기서 문자열을 다시 적지 않는다.
    """
    t = str(sentence or "")
    return any(f"({r})" in t for r in PITCHER_ROLES)


def classify(sentence: str) -> str | None:
    """결장 문장 → 근거. 🔴 **모르면 None** 이다 — 지어내지 않는다.

    ⚠️ 순서가 있다. 라인업 표지가 IL 표지보다 먼저다 — IL 로 빠진 선수가
       오늘 라인업에도 없는 것은 당연하므로, 두 표지가 같이 있으면
       "오늘 빠졌다"가 더 구체적인 사실이다.
    """
    t = str(sentence or "")
    if MARK_TODAY_OUT in t or MARK_LINEUP_EXCLUDED in t:
        return BASIS_LINEUP
    if MARK_INJURED in t or MARK_IL_DEFAULT in t:
        return BASIS_IL
    return None


REGULAR_TOP_N = 9        # 최근 타석 상위 이만큼이면 주전으로 본다
TOP_HITTER_N = 2         # 상위 이만큼이면 '주포' — λ 조정폭이 2배다


def _rank_map(batters: list[dict]) -> dict[int, int]:
    """{선수 id: 타석 순위(0부터)}. 상위일수록 팀 기여가 크다."""
    return {int(b["id"]): i for i, b in enumerate(batters or []) if b.get("id") is not None}


def _describe(team: str, name: str, rank: int | None, reason: str) -> str:
    """`performance._split_absences`가 팀을 가르고 `_absence_factors`가
    중요도를 읽는 문장으로 만든다.

    문구가 곧 계수다 — '주포'는 -4%p, 그 외 타자는 -2%p로 매핑된다.
    """
    if rank is not None and rank < TOP_HITTER_N:
        role = ROLE_TOP
    elif rank is not None and rank < REGULAR_TOP_N:
        role = ROLE_REGULAR
    else:
        role = ROLE_PLAYER
    return f"{team}의 {name}({role}) {reason}로 결장"


def from_lineup(team: str, batters: list[dict], order_ids: list[int],
                names: dict[int, str] | None = None) -> list[str]:
    """확정 라인업 기준 — 상위 9명 중 오늘 타순에 없는 선수."""
    names = names or {}
    today = {int(x) for x in (order_ids or [])}
    out = []
    for rank, b in enumerate(batters or []):
        if rank >= REGULAR_TOP_N:
            break
        pid = int(b["id"])
        if pid in today:
            continue
        out.append(_describe(team, names.get(pid, f"선수 #{pid}"), rank,
                             MARK_LINEUP_EXCLUDED))
    return out


def from_injured(team: str, batters: list[dict], injured: list[dict]) -> list[str]:
    """IL 명단 기준 — 라인업이 아직 확정되지 않은 경기에서 쓴다."""
    ranks = _rank_map(batters)
    out = []
    for p in injured or []:
        pid = p.get("id")
        rank = ranks.get(int(pid)) if pid is not None else None
        # 투수 결장은 선발 억제력·불펜에서 따로 다룬다 — 여기서는 타자만
        pos = str(p.get("position") or "").upper()
        if pos in ("P", "SP", "RP"):
            out.append(f"{team}의 {p['name']}({ROLE_BULLPEN}) {p.get('status') or MARK_IL_DEFAULT}로 결장"
                       if pos == "RP" else
                       f"{team}의 {p['name']}({ROLE_STARTER}) {p.get('status') or MARK_IL_DEFAULT}로 결장")
            continue
        out.append(_describe(team, p.get("name") or "선수", rank,
                             p.get("status") or MARK_IL_DEFAULT))
    return out


def collect(jg: dict, batters_by_team: dict, lineup: dict | None,
            injured_by_side: dict | None) -> tuple[list[str], str]:
    """경기 1건의 결장 문장과 **근거 라벨**을 만든다.

    반환: (문장 리스트, 근거) — 근거는 '라인업 확정' | 'IL 명단' | '없음'.
    라인업이 확정된 쪽은 라인업 기준, 아닌 쪽은 IL 기준으로 **사이드별로** 가른다.
    """
    lineup = lineup or {}
    injured_by_side = injured_by_side or {}
    confirmed = bool(lineup.get("confirmed"))
    sentences: list[str] = []
    used: set[str] = set()
    for side in ("home", "away"):
        team = jg.get(side)
        if not team:
            continue
        batters = batters_by_team.get(team) or []
        order_ids = ((lineup.get(side) or {}).get("batting_order_ids")) or []
        if confirmed and order_ids and batters:
            sentences += from_lineup(team, batters, order_ids,
                                     (lineup.get(side) or {}).get("names"))
            used.add("라인업 확정")
        elif injured_by_side.get(side):
            sentences += from_injured(team, batters, injured_by_side[side])
            used.add("IL 명단")
    if not sentences:
        return [], "없음"
    basis = " + ".join(sorted(used)) if used else "없음"
    return sentences, basis


def merge_into_research(research: dict, jg: dict, batters_by_team: dict,
                        lineup: dict | None, injured_by_side: dict | None) -> str | None:
    """결장 문장을 리서치에 얹는다. 리서치가 이미 채웠으면 덮지 않는다."""
    if research.get("absences"):
        return None
    sentences, basis = collect(jg, batters_by_team, lineup, injured_by_side)
    if not sentences:
        return None
    research["absences"] = sentences
    research["absence_basis"] = basis      # 상세 데이터에 근거를 밝힌다
    return f"결장 {len(sentences)}명 ({basis})"


async def fetch_for_games(games: list[dict], client=None) -> dict[int, dict]:
    """경기별 (확정 라인업, 사이드별 IL 명단)을 statsapi에서 수집.

    반환: {game_id: {"lineup": parse_boxscore 결과, "injured": {side: [...]}}}
    로스터는 **팀 단위로 캐시**한다 — 15경기면 boxscore 15콜 + 로스터 최대 30콜.
    statsapi는 무료·무인증이라 Perplexity 쿼터와 무관하다.
    """

    from app.collectors.base import freesource_mocked

    if freesource_mocked(client):        # [P5-1] 무인증 소스 — 목 모드
        return {}
    from app.collectors.lineups import (
        MLBLineupClient, parse_boxscore, parse_injured, parse_roster_names,
    )

    client = client or MLBLineupClient()
    roster_cache: dict[int, dict] = {}
    out: dict[int, dict] = {}
    for g in games:
        gid, ext = g.get("game_id") or g.get("id"), g.get("ext_id")
        if gid is None or not ext:
            continue
        try:
            parsed = parse_boxscore(await client.fetch_boxscore(str(ext)))
        except Exception as exc:
            logger.warning("[absences] boxscore 실패 game=%s: %s", gid, exc)
            continue
        injured: dict[str, list[dict]] = {}
        for side in ("home", "away"):
            team_id = (parsed.get(side) or {}).get("team_id")
            if not team_id:
                continue
            if team_id not in roster_cache:
                try:
                    raw = await client.fetch_roster(team_id)
                    roster_cache[team_id] = {
                        "injured": parse_injured(raw),
                        "names": parse_roster_names(raw),
                    }
                except Exception as exc:
                    logger.warning("[absences] roster 실패 team=%s: %s", team_id, exc)
                    roster_cache[team_id] = {"injured": [], "names": {}}
            if roster_cache[team_id]["injured"]:
                injured[side] = roster_cache[team_id]["injured"]
            blk = parsed.setdefault(side, {})
            blk["names"] = {**roster_cache[team_id]["names"],
                            **(blk.get("names") or {})}
        out[gid] = {"lineup": parsed, "injured": injured}
    return out
