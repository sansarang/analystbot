"""[§8-33] 투수 소모 — 카드 ①칸 "불펜 가용"의 재료. **LLM 0회.**

왜 이것이 가장 중요한가:
  "어제 불펜 5명이 26타자를 상대했다"는 시즌 ERA 100개보다 **오늘** 승패를 잘
  설명한다. 야구에서 하루 단위로 결과를 가장 크게 흔드는 것이 투수 가용성인데,
  기존 λ는 시즌 누적만 봐서 이것을 통째로 놓쳤다.
  실측(2026-08-26 광주): KIA가 투수 **9명**, 롯데가 6명을 썼다. 다음 날 두 팀의
  불펜 상태는 전혀 다른데, 시즌 지표로는 구분되지 않는다.

소스: 네이버 `record` API — `pitchersBoxscore`.

⚠️ **역할을 추정하지 않는다.** 응답에 '마무리'·'셋업' 같은 라벨이 없다.
   "마무리가 연투 중"은 추정이고, 추정을 사실 칸에 넣으면 카드가 오염된다.
   대신 **직접 관측되는 것만** 낸다 — 누가 언제 나와 몇 이닝·몇 타자를 상대했나.
   해석("뒷문이 얇다")은 2단 해석봇의 일이다.

⚠️ 경기값과 시즌값이 한 행에 섞여 있다. 실측으로 갈랐다(2026-08-27):
   **경기값** inn·pa·ab·hit·bb·kk·hr·er·r  (선수 pa 합 = 팀 pa 합으로 확인: 47/47, 50/50)
   **시즌값** bf·gameCount·era·w·l·seasonWin·seasonLose
   bf를 경기값으로 오인하면 상대 타자 수가 4배로 부풀려진다.
"""

import logging
import re

from app.collectors.naver_kbo import HEADERS, SCHEDULE, TEAM_TO_ODDS, NaverKBOClient

logger = logging.getLogger(__name__)

CACHE_TTL = 20 * 3600      # 하루 1회 갱신 — 종료 경기 기록은 바뀌지 않는다
def _key_top() -> int:
    """핵심 불펜 상한 — config에서. 지어낸 값이 아니라 설정값이다."""
    from app.config import get_settings

    return int(get_settings().key_reliever_top)


RECENT_GAMES = 3           # 카드 ①칸이 보는 창 (설계: 최근 3경기)
LOOKBACK_DAYS = 10         # 3경기를 찾기 위해 되짚는 최대 일수 (월요일 휴식일 대비)

# "3 ⅔" · "0 ⅓" · "1" — 네이버 이닝 표기
_FRAC = {"⅓": 1 / 3, "⅔": 2 / 3}


def parse_innings(v) -> float | None:
    """네이버 이닝 표기 → 실수. 못 읽으면 None(0이 아니다).

    0과 '모름'을 섞으면 "던지지 않았다"와 "파싱 실패"가 구분되지 않는다.
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    total, whole = 0.0, re.match(r"^\s*(\d+)", s)
    if whole:
        total += float(whole.group(1))
    for ch, frac in _FRAC.items():
        if ch in s:
            total += frac
    if not whole and not any(c in s for c in _FRAC):
        return None
    return round(total, 3)


def _opt_int(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


class _RecordMixin:
    """NaverKBOClient에 record 엔드포인트를 더한다."""

    async def record(self, game_id: str) -> dict:
        d = await self._get(f"{SCHEDULE}/{game_id}/record")
        return ((d.get("result") or {}).get("recordData")) or {}


class NaverRecordClient(_RecordMixin, NaverKBOClient):
    pass


def parse_pitchers(record: dict, side: str) -> list[dict]:
    """한 팀의 그 경기 투수 등판 기록. 반환은 **등판 순서**다.

    ⚠️ 첫 번째 항목을 선발로 본다. 네이버가 등판 순서로 주기 때문인데,
       이것은 관측된 규칙이지 문서화된 계약이 아니다 — 호출부에서 preview의
       예고 선발과 대조할 수 있도록 이름을 그대로 넘긴다.
    """
    rows = ((record.get("pitchersBoxscore") or {}).get(side)) or []
    out = []
    for i, p in enumerate(rows):
        name = (p.get("name") or "").strip()
        ip = parse_innings(p.get("inn"))
        if not name or ip is None:
            continue
        row = {
            "name": name,
            "innings": ip,
            "batters": int(p.get("pa") or 0),   # 경기값 (bf는 시즌값이다)
            "is_starter": i == 0,
            "hits": _opt_int(p.get("hit")),
            "hr": _opt_int(p.get("hr")),
            "bb": _opt_int(p.get("bb")),
            "k": _opt_int(p.get("kk")),
            "r": _opt_int(p.get("r")),
            "er": _opt_int(p.get("er")),
        }
        # 투구수는 응답에 있을 때만. 없으면 만들지 않는다 (시즌값 bf와 혼동 금지).
        pit = _opt_int(p.get("np") if p.get("np") not in (None, "") else p.get("pit"))
        if pit is not None:
            row["pitches"] = pit
        out.append(row)
    return out


def parse_scoreboard(record: dict, side: str) -> dict | None:
    """[§8-34] 그 경기의 이닝별 득점. 카드 ③칸("최근 3경기 내용")의 재료.

    **승패만으로는 상태를 알 수 없다.** 같은 3연승도
      · 매번 8점 차 완승 = 타선 폭발
      · 매번 1점 차 진땀승 = 불펜 소모
    로 정반대다. 이닝별 득점이 있어야 그 차이가 보인다.

    ⚠️ 홈팀은 이기고 있으면 9회말을 치지 않는다 — 이닝 배열 길이가 다를 수 있다.
       짧은 쪽을 0으로 채우지 말고 길이 차이를 그대로 다뤄야 한다.
    """
    sb = record.get("scoreBoard") or {}
    inn, rheb = sb.get("inn") or {}, sb.get("rheb") or {}
    opp = "home" if side == "away" else "away"
    mine, theirs = inn.get(side), inn.get(opp)
    if not isinstance(mine, list) or not isinstance(theirs, list):
        return None
    box, obox = rheb.get(side) or {}, rheb.get(opp) or {}
    out = {
        "runs_by_inning": [int(x or 0) for x in mine],
        "runs": int(box.get("r") or sum(int(x or 0) for x in mine)),
        "hits": int(box.get("h") or 0),
        "opp_runs": int(obox.get("r") or sum(int(x or 0) for x in theirs)),
    }
    if "e" in box:
        try:
            out["errors"] = int(box.get("e") or 0)
        except (TypeError, ValueError):
            pass
    out.update(classify_game([int(x or 0) for x in mine],
                             [int(x or 0) for x in theirs]))
    return out


def classify_game(mine: list[int], theirs: list[int]) -> dict:
    """이닝별 득점 → 경기의 **성격**. 전부 결정적으로 유도되는 사실이다.

    역전승/역전패는 이닝별 누적 리드를 따라가야만 나온다 — 최종 스코어만으로는
    "9회에 뒤집혔다"와 "처음부터 앞섰다"가 구분되지 않는다.
    """
    cum_m = cum_t = 0
    was_behind = was_ahead = False
    for i in range(max(len(mine), len(theirs))):
        cum_m += mine[i] if i < len(mine) else 0
        cum_t += theirs[i] if i < len(theirs) else 0
        if cum_m < cum_t:
            was_behind = True
        elif cum_m > cum_t:
            was_ahead = True
    result = "W" if cum_m > cum_t else "L" if cum_m < cum_t else "D"
    return {
        "result": result,
        "margin": cum_m - cum_t,
        "comeback_win": result == "W" and was_behind,
        "blown_lead": result == "L" and was_ahead,
        "shutout_loss": result == "L" and cum_m == 0,
        "shutout_win": result == "W" and cum_t == 0,
        "one_run": abs(cum_m - cum_t) == 1,
    }


def parse_batters(record: dict, side: str) -> list[dict]:
    """한 팀의 그 경기 타자 기록. 반환: [{"name", "pa"}].

    타석(PA)은 응답에 없어 **타수 + 볼넷**으로 센다. 희생타·사구가 빠지므로
    정확한 PA는 아니지만, 우리가 쓰는 용도(**누가 주전인가**)에는 순위가
    같으면 충분하다. 정확한 값인 척하지 않으려고 이름을 `pa`로 쓰되
    산출 방식을 여기 적어둔다.

    ⚠️ 같은 타순에 여러 명이 나온다(선발 + 교체). 둘 다 센다 — 교체로만 나온
       선수는 타석이 적어 상위 9명에 들지 않는다.
    """
    rows = ((record.get("battersBoxscore") or {}).get(side)) or []
    out = []
    for b in rows:
        name = (b.get("name") or "").strip()
        if not name:
            continue
        pa = int(b.get("ab") or 0) + int(b.get("bb") or 0)
        row = {"name": name, "pa": pa}
        for src, dst in (("hit", "hits"), ("hr", "hr"), ("bb", "bb"), ("kk", "k")):
            v = _opt_int(b.get(src))
            if v is not None:
                row[dst] = v
        out.append(row)
    return out


def regulars_from(games: list[dict], top: int = 9) -> list[dict]:
    """[A-2단계] 최근 경기 **타석 상위 9명** = 주전.

    결장의 '중요도'를 출전 기록으로 판단한다 — IL 명단만으로는 그 선수가 팀에
    얼마나 중요한지 알 수 없다(MLB 쪽 `absences.py`가 같은 이유로 타석 상위
    9명을 쓴다).
    """
    tally: dict[str, int] = {}
    for g in games:
        for b in g.get("batters") or []:
            tally[b["name"]] = tally.get(b["name"], 0) + int(b.get("pa") or 0)
    ranked = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
    return [{"name": n, "pa": pa, "rank": i + 1}
            for i, (n, pa) in enumerate(ranked) if pa > 0]


def _game_row(g: dict) -> dict:
    """폼 프롬프트용 한 경기. 시즌 ERA는 넣지 않는다. 없는 칸은 생략."""
    score = g.get("score") or {}
    pits = g.get("pitchers") or []
    starter = next((p for p in pits if p.get("is_starter")), None)
    rel = [p for p in pits if not p.get("is_starter")]
    row: dict = {}
    for k in ("date", "game_id", "opponent", "home"):
        if g.get(k) is not None:
            row[k] = g[k]
    for k in ("runs", "opp_runs", "hits", "errors", "result"):
        if score.get(k) is not None:
            row[k] = score[k]
    if starter:
        row["starter_name"] = starter.get("name")
        row["starter_ip"] = starter.get("innings")
        if starter.get("r") is not None:
            row["starter_r"] = starter["r"]
        if starter.get("pitches") is not None:
            row["starter_pitches"] = starter["pitches"]
    row["bullpen_count"] = len(rel)
    if rel:
        row["bullpen_ip"] = round(sum(p["innings"] for p in rel), 3)
    bats = g.get("batters") or []
    for key in ("hr", "bb", "k"):
        vals = [b[key] for b in bats if b.get(key) is not None]
        if vals:
            row[key] = sum(vals)
    return row


def summarize(games: list[dict], standings: dict | None = None) -> dict:
    """경기별 등판 기록(최신순) → 카드 ①칸의 **사실** 층.

    games 원소: {"date": "YYYY-MM-DD", "pitchers": [parse_pitchers 결과]}
    """
    if not games:
        return {}
    recent = games[:RECENT_GAMES]
    starter_ip = relief_ip = 0.0
    relief_batters = 0
    per_game_names: list[set[str]] = []
    for g in recent:
        names = set()
        for p in g["pitchers"]:
            names.add(p["name"])
            if p["is_starter"]:
                starter_ip += p["innings"]
            else:
                relief_ip += p["innings"]
                relief_batters += p["batters"]
        per_game_names.append(names)

    # [핵심 불펜 자체 산출] 관측 창 전체에서 **구원 등판이 잦은 순**.
    #   ⚠️ 누가 마무리·셋업인지 **지어내지 않는다.** 등판 횟수는 관측이고,
    #      역할은 추정이다. 관측만으로 정의한다 — "많이 나온 구원투수".
    #   ⚠️ 상한(config `key_reliever_top`)은 운용값이지 실측이 아니다.
    #      채점(lineup_type_ledger)이 쌓이면 몇 명이 적당한지 재서 교체한다.
    relief_counts: dict[str, int] = {}
    for g in games:                      # 최근 3경기가 아니라 **관측 창 전체**
        for p in g["pitchers"]:
            if not p["is_starter"]:
                relief_counts[p["name"]] = relief_counts.get(p["name"], 0) + 1

    # 연투 = 최근 두 경기에 **모두** 등판. 역할 추정 없이 관측만으로 나온다.
    b2b = sorted(per_game_names[0] & per_game_names[1]) if len(per_game_names) >= 2 else []
    last = recent[0]
    # 카드 ③ — 최근 3경기의 **내용**. 승패가 아니라 어떻게 이기고 졌는가.
    scores = [g["score"] for g in recent if g.get("score")]
    card3: dict = {}
    if scores:
        card3 = {
            "runs_l3": sum(s["runs"] for s in scores),
            "runs_allowed_l3": sum(s["opp_runs"] for s in scores),
            "runs_per_game_l3": round(sum(s["runs"] for s in scores) / len(scores), 2),
            "results_l3": "".join(s["result"] for s in scores),   # 최신순
            "comeback_wins_l3": sum(1 for s in scores if s["comeback_win"]),
            "blown_leads_l3": sum(1 for s in scores if s["blown_lead"]),
            "shutout_losses_l3": sum(1 for s in scores if s["shutout_loss"]),
            "one_run_games_l3": sum(1 for s in scores if s["one_run"]),
            "score_games": len(scores),
        }
    out = {
        **card3,
        "regulars": regulars_from(recent),
        "window_games": len(recent),
        "last_game_date": last["date"],
        "pitchers_used_last": len(last["pitchers"]),
        "pitchers_used_last_names": sorted(p["name"] for p in last["pitchers"]),
        "relief_ip_last": round(sum(p["innings"] for p in last["pitchers"]
                                    if not p["is_starter"]), 2),
        "relief_batters_last": sum(p["batters"] for p in last["pitchers"]
                                   if not p["is_starter"]),
        "starter_ip_l3": round(starter_ip, 2),
        "relief_ip_l3": round(relief_ip, 2),
        "relief_batters_l3": relief_batters,
        # [핵심 불펜 자체 산출] 등판 횟수 상위 — 이름과 횟수를 함께 남긴다.
        #   횟수를 버리면 "왜 이 사람이 핵심인가"를 되짚을 수 없다.
        "key_relievers": [n for n, _ in sorted(
            relief_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:_key_top()]],
        "relief_appearances": dict(sorted(relief_counts.items(),
                                          key=lambda kv: (-kv[1], kv[0]))),
        "back_to_back": b2b,
        "back_to_back_count": len(b2b),
        "games": [_game_row(g) for g in recent],
    }
    from app.collectors.last3 import attach_opponent_context, strip_banned

    out = strip_banned(out)
    games_out = []
    for row in out["games"]:
        attach_opponent_context(row, standings)
        games_out.append(strip_banned(row))
    out["games"] = games_out
    return out


async def fetch_recent_usage(date: str, client: NaverRecordClient | None = None,
                             teams: set[str] | None = None,
                             standings: dict | None = None) -> dict[str, dict]:
    """`date` **이전** 종료 경기들에서 팀별 투수 소모를 모은다.

    ⚠️ `date` 당일 경기는 **넣지 않는다.** 당일 결과는 예측 시점에 알 수 없다 —
       넣으면 누출이다(2026-08-27에 실제로 검증한 항목).
    """
    from datetime import date as _date
    from datetime import timedelta

    client = client or NaverRecordClient()
    day = _date.fromisoformat(date)
    by_team: dict[str, list[dict]] = {}

    for back in range(1, LOOKBACK_DAYS + 1):
        d = (day - timedelta(days=back)).isoformat()
        if all(len(v) >= RECENT_GAMES for v in by_team.values()) and len(by_team) >= 10:
            break
        try:
            games = await client.games(d)
        except Exception as exc:
            logger.warning("[kbo_usage] %s 일정 조회 실패: %s", d, exc)
            continue
        for g in games:
            home = TEAM_TO_ODDS.get(g.get("homeTeamName") or "")
            away = TEAM_TO_ODDS.get(g.get("awayTeamName") or "")
            gid = g.get("gameId")
            if not (home and away and gid):
                continue
            if teams and not ({home, away} & teams):
                continue
            if all(len(by_team.get(t, [])) >= RECENT_GAMES for t in (home, away)):
                continue
            try:
                rec = await client.record(gid)
            except Exception as exc:
                logger.warning("[kbo_usage] %s 기록 조회 실패: %s", gid, exc)
                continue
            for side, team in (("home", home), ("away", away)):
                rows = parse_pitchers(rec, side)
                if not rows:
                    continue
                if len(by_team.setdefault(team, [])) < RECENT_GAMES:
                    # 스코어보드는 **같은 응답**에서 뽑는다 — 추가 HTTP가 없다.
                    opp = away if side == "home" else home
                    by_team[team].append({
                        "date": d, "game_id": gid,
                        "opponent": opp, "home": side == "home",
                        "pitchers": rows,
                        "batters": parse_batters(rec, side),
                        "score": parse_scoreboard(rec, side),
                    })

    out = {t: summarize(v, standings) for t, v in by_team.items() if v}
    logger.info("[kbo_usage] %s 기준 %d팀 소모 산출", date, len(out))
    return out


def _key(date: str) -> str:
    return f"kbo_usage:{date}"


async def refresh(redis, date: str, client: NaverRecordClient | None = None) -> dict:
    import json

    from app.collectors.base import freesource_mocked

    if freesource_mocked(client):        # [P5-1] 무인증 소스 — 목 모드
        return {"ok": False, "teams": 0, "mock": True}

    standings = None
    try:
        from app.collectors.naver_kbo import build_standings, load as load_naver

        standings = build_standings(await load_naver(redis, date) or {})
    except Exception as exc:
        logger.warning("[kbo_usage] 순위표 부착 생략: %s", exc)
    data = await fetch_recent_usage(date, client, standings=standings)
    if not data:
        from app.alerts import StageResult, stage_failed

        await stage_failed(StageResult(
            name="KBO 투수 소모", ok=0, total=1, cause="missing",
            detail=f"{date} 이전 종료 경기에서 산출 실패",
            impact="카드 ①칸(불펜 가용)이 '모름'으로 나갑니다"))
    await redis.set(_key(date), json.dumps(data, ensure_ascii=False), ex=CACHE_TTL)
    return {"teams": len(data)}


async def load(redis, date: str) -> dict[str, dict]:
    import json

    raw = await redis.get(_key(date))
    return json.loads(raw) if raw else {}


def merge_into_research(research: dict, jg: dict, table: dict) -> list[str]:
    """팀별 소모를 research에 얹는다. 반환: 채운 필드 목록.

    ⚠️ 값을 **해석하지 않는다.** '얇다'·'충분하다'는 2단 해석봇이 정한다.
    """
    filled = []
    for side in ("home", "away"):
        row = (table or {}).get(jg.get(side) or "")
        if not row:
            continue
        blk = research.setdefault(f"{side}_usage", {})
        for k, v in row.items():
            if blk.get(k) != v:
                blk[k] = v
                filled.append(f"{side}_usage.{k}")
    return filled
