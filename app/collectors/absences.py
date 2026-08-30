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
        role = "주포"
    elif rank is not None and rank < REGULAR_TOP_N:
        role = "주전 타자"
    else:
        role = "선수"
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
        out.append(_describe(team, names.get(pid, f"선수 #{pid}"), rank, "라인업 제외"))
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
            out.append(f"{team}의 {p['name']}(불펜) {p.get('status') or '부상자 명단'}로 결장"
                       if pos == "RP" else
                       f"{team}의 {p['name']}(선발) {p.get('status') or '부상자 명단'}로 결장")
            continue
        out.append(_describe(team, p.get("name") or "선수", rank,
                             p.get("status") or "부상자 명단"))
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
