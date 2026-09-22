"""[§9-라인업 의도] KBO 공식 박스스코어에서 **과거 라인업을 백필**한다.

왜 필요한가 (2026-08-27):
  평소 라인업 비교에 최소 5경기 이력이 필요한데 `lineup_events`가 0행이었다.
  네이버 preview는 **과거 라인업을 보관하지 않는다**(실조회: 어제 경기 fullLineUp
  0명). KBO 공식 박스스코어에는 타순·포지션·이름이 전부 남아 있다.

⚠️ **이것은 "실제 출전 기록"이지 "발표 라인업"이 아니다.**
   경기 중 교체가 같은 타순에 여러 행으로 쌓인다. 같은 타순의 **첫 행**이 선발이다.
   그래도 발표 라인업과 완전히 같지는 않다(발표 후 경기 전 교체는 알 수 없다).
   → `source='boxscore'`로 구분해 저장하고, 평소 기준을 낼 때 어느 쪽을 썼는지
     반드시 표시한다. 두 소스를 섞어놓고 같은 것처럼 쓰면 안 된다.

⚠️ G_ID는 **일정 응답에서 그대로 읽는다.** 팀 코드를 추측해 조립하지 않는다
   (실측: HH·HT·KT·LG·LT·NC·OB·SK·SS·WO).
"""
from __future__ import annotations

import html as htmlmod
import json
import logging
import re

import httpx

from app.collectors.kbo import BASE, KBO_TEAMS, UA, polite_gap

logger = logging.getLogger(__name__)

BOX_PATH = "/ws/Schedule.asmx/GetBoxScoreScroll"
SCHED_PATH = "/ws/Schedule.asmx/GetScheduleList"
_HEADERS = {"User-Agent": UA,
            "Referer": f"{BASE}/Schedule/Schedule.aspx",
            "X-Requested-With": "XMLHttpRequest"}
_GID = re.compile(r"(\d{8}[A-Z]{4}\d)")

# 박스스코어 포지션 약어 → 정식 명칭. 크롤러(네이버)는 정식 명칭을 주므로
# 두 소스를 비교하려면 한쪽으로 맞춰야 한다.
POSITION_FULL = {
    "중": "중견수", "좌": "좌익수", "우": "우익수", "지": "지명타자",
    "포": "포수", "유": "유격수", "一": "1루수", "二": "2루수", "三": "3루수",
    "투": "투수",
}
# 교체 표기 — 대타(타)·대주자(주)가 앞에 붙는다. 선발이 아니다.
_SUB_PREFIX = ("타", "주")


def normalize_position(raw: str) -> str:
    """약어·정식 명칭을 하나로 맞춘다. 모르면 원문 그대로(버리지 않는다).

    ⚠️ 두 글자 이상은 **경기 중 수비 이동**이다("우중" = 우익수→중견수,
       "유二" = 유격수→2루수). 우리가 알고 싶은 것은 **선발 위치**이므로
       첫 글자를 쓴다. 실측 2026-08-26 박스스코어에 실제로 있었다.
    """
    p = (raw or "").strip()
    if not p:
        return ""
    if p in POSITION_FULL:
        return POSITION_FULL[p]
    if len(p) > 1 and p[0] in POSITION_FULL:
        return POSITION_FULL[p[0]]
    return p


def is_substitute(raw: str) -> bool:
    """대타·대주자로 들어온 행인가. 두 글자 이상이고 앞이 타/주면 교체다."""
    p = (raw or "").strip()
    return len(p) >= 2 and p[0] in _SUB_PREFIX


def parse_starting_order(table_json: str | dict) -> list[str]:
    """박스스코어 타자표 → `["이름(포지션)", ...]` 9명(선발만).

    같은 타순의 **첫 행**이 선발이다. 교체 표기(대타·대주자)는 건너뛴다.
    ⚠️ 9명이 안 되면 **빈 목록**을 돌려준다 — 불완전한 라인업으로 '평소'를
       만들면 그 결손이 매번 '변경'으로 잡힌다.
    """
    t = json.loads(table_json) if isinstance(table_json, str) else (table_json or {})
    best: dict[int, str] = {}
    for row in t.get("rows") or []:
        cells = [(c or {}).get("Text", "").strip() for c in (row.get("row") or [])]
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        slot = int(cells[0])
        if slot in best or is_substitute(cells[1]):
            continue
        pos = normalize_position(cells[1])
        best[slot] = f"{cells[2]}({pos})" if pos else cells[2]
    if len(best) < 9:
        return []
    return [best[i] for i in sorted(best)][:9]


# 실측 2026-08-28 GetBoxScoreScroll arrPitcher 헤더 17열:
#   선수명, 등판, 결과, 승, 패, 세, 이닝, 타자, 투구수, 타수,
#   피안타, 홈런, 4사구, 삼진, 실점, 자책, 평균자책점
# 등판="선발" 또는 투입 이닝("7.9" = 7회 2사 투입. **이닝이 아니다**).
# 평균자책점은 시즌값 — 이 표의 경기 ERA로 쓰지 않는다.
_FRAC_IP = {"1/3": 1 / 3, "2/3": 2 / 3}


def _cells(tbl) -> tuple[list[list[str]], list[str]]:
    """`{"rows":[{"row":[{"Text":…}]}], "tfoot":[…]}` → (행 목록, 합계 행)."""
    import json as _json

    d = _json.loads(tbl) if isinstance(tbl, str) else (tbl or {})
    rows = [[(c or {}).get("Text") or "" for c in (r.get("row") or [])]
            for r in (d.get("rows") or [])]
    tf = [[(c or {}).get("Text") or "" for c in (r.get("row") or [])]
          for r in (d.get("tfoot") or [])]
    return rows, (tf[0] if tf else [])


#: [BAT-9 2026-09-09] 타석 결과 코드 → 우리 칸. **실측으로 만든 목록이다** —
#  KBO 9월 62경기 전수에서 서로 다른 표기 81종 · 1,537칸을 세어 확인했다.
#    홈런  좌홈 · 우홈 · 중홈 · 좌중홈 · 우중홈   → 전부 `홈` 으로 끝난다
#    삼진  삼진 · 스낫(스트라이크낫아웃)
#    볼넷  4구 · 고4(고의4구)
#    사구  사구  ← **볼넷이 아니다.** MLB `baseOnBalls`·NPB `四球` 와 같은 경계다.
#  ⚠️ 목록을 손으로 적는 것은 이 저장소가 가장 자주 데인 형태다. 없앨 수는
#     없으니(원본에 사전이 없다) **틀렸을 때 울리게** 만들었다 —
#     아래 `_cross_check` 가 같은 응답의 투수 기록과 대조한다.
_PA_SO = ("삼진", "스낫")
_PA_BB = ("4구", "고4")
_PA_HBP = ("사구",)

#: 한 이닝에 두 타석이면 한 칸에 합쳐진다 — `사구<br />/ 삼진`.
#  실측: 구분자는 이 하나뿐이고 62경기에 10칸 있었다. 나누지 않으면 **둘 다**
#  사라진다(대조에서 삼진·4사구가 1~2씩 모자랐다).
_PA_SPLIT = re.compile(r"<br\s*/?>\s*/?\s*")


def _pa_counts(cells) -> dict:
    """타석 결과 칸들 → {"hr","bb","so","hbp"}. 모르는 표기는 세지 않는다."""
    out = {"hr": 0, "bb": 0, "so": 0, "hbp": 0}
    for c in cells or ():
        for part in _PA_SPLIT.split(str(c or "")):
            t = part.replace("&nbsp;", "").strip()
            if not t:
                continue
            if t.endswith("홈"):
                out["hr"] += 1
            elif t in _PA_SO:
                out["so"] += 1
            elif t in _PA_BB:
                out["bb"] += 1
            elif t in _PA_HBP:
                out["hbp"] += 1
    return out


def _opp_totals(box: dict, side_idx: int) -> dict | None:
    """상대 투수진의 피홈런·4사구·삼진 합계. 못 읽으면 None.

    🔴 **이것이 타석 코드 목록의 감시자다.** `arrPitcher[0]` 이 원정 투수,
       `[1]` 이 홈 투수이므로 타자 블록 `i` 의 상대는 `1 - i` 다.
    """
    pit = box.get("arrPitcher") or []
    if len(pit) < 2:
        return None
    rows = parse_official_pitchers(_pitcher_table(pit[1 - side_idx]))
    if not rows:
        return None
    return {"hr": sum(p.get("hr") or 0 for p in rows),
            "bb4": sum(p.get("bb") or 0 for p in rows),
            "so": sum(p.get("k") or 0 for p in rows)}


def parse_batting(box: dict) -> dict:
    """KBO 공식 박스스코어 `arrHitter` → {"home": [...], "away": [...]}.

    🔴 [BAT-2 2026-09-08] **원본을 실제로 열어 확인했다(추측 아님).**
       `arrHitter` 는 원소 2개이고 각각 `table1/2/3` 을 갖는다:
         table1 = [타순, 포지션, 이름]
         table3 = [타수, 안타, 타점, 득점, 타율]   ← **헤더가 없다**
         table2 = 이닝별 결과 (여기서는 안 쓴다)
       실측 20260901LGOB0: `arrHitter[0]` = LG(원정), `[1]` = 두산(홈).
       교체 선수는 **같은 타순 번호를 공유**한다(5,5 / 9,9,9,9).

    ⚠️ **열 순서가 NPB 와 다르다.** NPB 는 `打数·得点·安打·打点` 이고
       KBO 는 `타수·안타·타점·득점` 이다. 헤더가 없으니 위치로 읽되,
       **tfoot 합계와 대조**해 열이 바뀌면 `_mismatch` 로 알린다.
       열 의미 검증 근거(실측): 두산 4열 합계 1 = DB `home_score` 1,
       양의지(타점1·득점0)·안재석(타점0·득점1)이 의미와 맞았다.

    ⚠️ 팀 이름을 여기서 만들지 않는다 — 적재가 `games` 에서 읽는다.
    """
    out: dict = {"home": [], "away": []}
    blocks = (box or {}).get("arrHitter") or []
    # 실측: [0]=원정, [1]=홈
    for _i, (side, blk) in enumerate(zip(("away", "home"), blocks)):
        rows1, _ = _cells((blk or {}).get("table1"))
        rows3, tf3 = _cells((blk or {}).get("table3"))
        # 🔴 [BAT-9] 타석 결과. **행수가 다르면 채우지 않는다** — 줄이 어긋난
        #    채로 붙이면 남의 홈런이 내 기록이 된다.
        rows2, _ = _cells((blk or {}).get("table2"))
        if len(rows2) != len(rows1):
            if rows2:
                logger.warning("[kbo_box] %s 타석표 행수 불일치 %d vs %d — "
                               "홈런·볼넷·삼진을 채우지 않는다",
                               side, len(rows2), len(rows1))
            rows2 = []
        pa_sum = {"hr": 0, "bb": 0, "so": 0, "hbp": 0}
        sums = [0, 0, 0, 0]
        for _r, (names, nums) in enumerate(zip(rows1, rows3)):
            if len(names) < 3 or len(nums) < 4:
                continue
            name = (names[2] or "").strip()
            if not name:
                continue
            vals = []
            for i in range(4):
                t = (nums[i] or "").strip()
                vals.append(int(t) if t.lstrip("-").isdigit() else None)
                if vals[-1] is not None:
                    sums[i] += vals[-1]
            slot = (names[0] or "").strip()
            pa = _pa_counts(rows2[_r]) if _r < len(rows2) else None
            if pa:
                for k in pa_sum:
                    pa_sum[k] += pa[k]
            out[side].append({
                "batter": name,
                "slot": int(slot) if slot.isdigit() else None,
                # 🔴 포지션 사전을 새로 만들지 않는다 — `parse_starting_order` 와
                #    같은 `normalize_position` 을 쓴다(사본 금지). 실측: 같은
                #    표에 `二`(2루수)와 `중`(중견수)이 섞여 온다.
                "pos": normalize_position(names[1]) or None,
                "sub": is_substitute(names[1]),
                "ab": vals[0], "h": vals[1], "rbi": vals[2], "r": vals[3],
                "hr": pa["hr"] if pa else None,
                "bb": pa["bb"] if pa else None,
                "so": pa["so"] if pa else None,
            })
        # 🔴 헤더가 없으니 합계로 검증한다. 조용히 뒤바뀌면 안 된다.
        if tf3:
            tot = [int(x) if (x or "").strip().lstrip("-").isdigit() else None
                   for x in tf3[:4]]
            if any(t is not None and t != s for t, s in zip(tot, sums)):
                out.setdefault("_mismatch", {})[f"{side}_tfoot"] = {
                    "tfoot": tot, "sum": sums}
                logger.warning("[kbo_box] 타자표 합계 불일치 %s — tfoot %s vs 합 %s "
                               "(열 순서가 바뀌었을 수 있다)", side, tot, sums)
        # 🔴 [BAT-9] **타석 코드 목록의 감시자.** 같은 응답의 상대 투수 기록과
        #    대조한다 — 코드가 하나 늘거나 표기가 바뀌면 여기서 어긋난다.
        #    투수 표의 `4사구` 는 볼넷+사구 합이므로 그렇게 비교한다.
        opp = _opp_totals(box, _i) if rows2 else None
        if opp:
            got = {"hr": pa_sum["hr"], "bb4": pa_sum["bb"] + pa_sum["hbp"],
                   "so": pa_sum["so"]}
            if got != opp:
                out.setdefault("_mismatch", {})[f"{side}_pa"] = {
                    "타자표": got, "투수표": opp}
                logger.warning("[kbo_box] %s 타석 코드 대조 불일치 — 타자표 %s "
                               "vs 투수표 %s (코드 표기가 바뀌었을 수 있다)",
                               side, got, opp)
    return out


def _pitcher_cell(c) -> str:
    raw = (c or {}).get("Text", "") if isinstance(c, dict) else str(c or "")
    raw = re.sub(r"<[^>]+>", "", raw)
    return htmlmod.unescape(raw).replace("\xa0", " ").strip()


def parse_official_ip(v) -> float | None:
    """공식 박스 '이닝' 열. '1 2/3' · '6'. '7.9'(등판 시각)는 거부."""
    s = str(v or "").strip()
    if not s or s in (".", "-", "—"):
        return None
    if s in _FRAC_IP:
        return round(_FRAC_IP[s], 3)
    m = re.match(r"^(\d+)(?:\s+(\d/\d))?$", s)
    if not m:
        return None
    total = float(m.group(1))
    frac = m.group(2)
    if frac:
        if frac not in _FRAC_IP:
            return None
        total += _FRAC_IP[frac]
    return round(total, 3)


def _opt_int(v):
    s = str(v or "").strip().replace(",", "")
    if not s or s in (".", "-", "—"):
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def parse_official_pitchers(table_json: str | dict) -> list[dict]:
    """arrPitcher → 등판 순서. 시즌 ERA(마지막 열)는 버린다.

    실측 2026-08-28: 헤더는 `headers[0]`이고 `rows`는 선수부터다.
    타자표(`table1`)처럼 첫 행을 헤더로 보면 선수명이 헤더가 되어 0건이 된다.
    """
    t = json.loads(table_json) if isinstance(table_json, str) else (table_json or {})
    rows_raw = t.get("rows") or []
    header_rows = t.get("headers") or []
    if header_rows:
        head = [_pitcher_cell(c) for c in (header_rows[0].get("row") or [])]
        data = rows_raw
    else:
        if len(rows_raw) < 2:
            return []
        head = [_pitcher_cell(c) for c in (rows_raw[0].get("row") or [])]
        data = rows_raw[1:]
    idx = {name: i for i, name in enumerate(head)}
    if "선수명" not in idx or "이닝" not in idx:
        logger.warning("[백필] arrPitcher 헤더 불일치: %s", head)
        return []
    out = []
    for row in data:
        cells = [_pitcher_cell(c) for c in (row.get("row") or [])]
        if not cells:
            continue
        name = cells[idx["선수명"]] if idx["선수명"] < len(cells) else ""
        if not name:
            continue
        entry = cells[idx["등판"]] if "등판" in idx and idx["등판"] < len(cells) else ""
        ip = parse_official_ip(cells[idx["이닝"]] if idx["이닝"] < len(cells) else "")
        def col(key, _cells=cells, _idx=idx):
            i = _idx.get(key)
            return _cells[i] if i is not None and i < len(_cells) else ""
        out.append({
            "name": name,
            "is_starter": entry == "선발",
            "innings": ip,
            "batters": _opt_int(col("타자")),
            "hits": _opt_int(col("피안타")),
            "hr": _opt_int(col("홈런")),
            "bb": _opt_int(col("4사구")),
            "k": _opt_int(col("삼진")),
            "r": _opt_int(col("실점")),
            "er": _opt_int(col("자책")),
        })
    if out and not any(p["is_starter"] for p in out):
        out[0]["is_starter"] = True
    return out


async def fetch_box(game_id: str) -> dict:
    """GetBoxScoreScroll JSON 1회. 라인업·투수 등판이 같은 응답에 있다."""
    # 🔴 [SRC-OFF 2026-09-21] robots 거부 소스 — 요청을 보내지 않는다.
    from app.collectors.source_gate import require

    require("koreabaseball")
    # 🔴 [KBO-ON] 연속 요청 사이 간격. 지시가 바꾼 것은 "수집하느냐"이지
    #    "얼마나 빨리 치느냐"가 아니다(원본: config sources.koreabaseball).
    await polite_gap()
    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as c:
        await c.get(f"{BASE}/Schedule/Schedule.aspx", headers=_HEADERS)
        r = await c.post(BASE + BOX_PATH,
                         data={"leId": "1", "srId": "0",
                               "seasonId": game_id[:4],
                               "gameDate": game_id[:8], "gameId": game_id},
                         headers=_HEADERS)
    r.raise_for_status()
    return r.json()


def _pitcher_table(block: dict) -> str | dict | None:
    """투수표 키. 실측 2026-08-28: arrPitcher는 `table`, arrHitter는 `table1`."""
    b = block or {}
    return b.get("table") or b.get("table1")


def parse_box(j: dict, date: str, game_id: str) -> dict:
    hitters = j.get("arrHitter") or []
    pitchers = j.get("arrPitcher") or []
    if len(hitters) < 2:
        return {}
    out = {
        "away": parse_starting_order((hitters[0] or {}).get("table1")),
        "home": parse_starting_order((hitters[1] or {}).get("table1")),
        # 🔴 [BAT-3] 같은 응답에 이미 와 있다. 두 번 받지 않는다.
        "batting": parse_batting(j),
        "away_pitchers": parse_official_pitchers(_pitcher_table(pitchers[0]))
        if len(pitchers) >= 1 else [],
        "home_pitchers": parse_official_pitchers(_pitcher_table(pitchers[1]))
        if len(pitchers) >= 2 else [],
        "date": date, "game_id": game_id,
    }
    return out


async def fetch_game_ids(season: int, month: int) -> list[dict]:
    """그 달의 경기 목록 — G_ID·날짜·양 팀(공식 표기).

    ⚠️ **팀은 같은 행의 매치업 문구에서 읽는다.** G_ID의 팀 코드를 추측해
       해석하지 않는다 — 코드표를 지어내면 한 팀만 틀려도 남의 라인업이
       그 팀의 '평소'가 된다.
    """
    from app.collectors.kbo import parse_matchup

    # 🔴 [SRC-OFF 2026-09-21] robots 거부 소스 — 요청을 보내지 않는다.
    from app.collectors.source_gate import require

    require("koreabaseball")
    # 🔴 [KBO-ON] 연속 요청 사이 간격. 지시가 바꾼 것은 "수집하느냐"이지
    #    "얼마나 빨리 치느냐"가 아니다(원본: config sources.koreabaseball).
    await polite_gap()
    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as c:
        await c.get(f"{BASE}/Schedule/Schedule.aspx", headers=_HEADERS)
        r = await c.post(BASE + SCHED_PATH,
                         data={"leId": "1", "srIdList": "0,9,6",
                               "seasonId": str(season),
                               "gameMonth": f"{month:02d}", "teamId": ""},
                         headers=_HEADERS)
    r.raise_for_status()
    out, seen = [], set()
    cur_date = None
    for row in r.json().get("rows") or []:
        cells = [(c or {}).get("Text", "") for c in (row.get("row") or [])]
        plain = [re.sub(r"<[^>]+>", "", x).strip() for x in cells]
        # 날짜는 그 날 첫 행에만 있다 — 이어지는 행은 앞 날짜를 물려받는다.
        m = re.match(r"^(\d{2})\.(\d{2})", plain[0] if plain else "")
        if m:
            cur_date = f"{season}-{m.group(1)}-{m.group(2)}"
        gids = _GID.findall("".join(cells))
        if not gids or cur_date is None:
            continue
        gid = gids[0]
        if gid in seen:
            continue
        mu = next((parse_matchup(x) for x in plain if parse_matchup(x)), None)
        if not mu:
            continue
        seen.add(gid)
        out.append({"game_id": gid, "date": cur_date,
                    "away": KBO_TEAMS.get(mu["away"], mu["away"]),
                    "home": KBO_TEAMS.get(mu["home"], mu["home"])})
    return out


async def fetch_lineups(game_id: str, date: str) -> dict:
    """한 경기의 선발 라인업. 반환 {"away": [...], "home": [...], "teams": (a,h)}.

    ⚠️ arrHitter[0]이 원정, [1]이 홈이다 — 야구 기록의 통상 순서(원정 선공)다.
       G_ID도 `날짜+원정+홈+0` 순서라 서로 교차검증된다.
    """
    return parse_box(await fetch_box(game_id), date, game_id)


async def backfill(pool, season: int, months: tuple[int, ...],
                   limit_per_team: int = 10) -> dict:
    """최근 경기 라인업을 `lineup_events`에 적재한다. 반환 계측 dict.

    ⚠️ `source='boxscore'`로 남긴다 — 발표 라인업(`crawler`)과 구분해야 한다.
    ⚠️ 경기 매칭은 **날짜 + 양 팀**으로 한다. 날짜만으로 고르면 같은 날 5경기 중
       아무거나 잡혀 남의 라인업이 그 팀 '평소'가 된다.
    """
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    from app.collectors import batter_log
    from app.collectors.game_match import _FIND
    from app.collectors.lineup_history import record
    from app.collectors.pitcher_log import record_appearances

    stats = {"games": 0, "rows": 0, "appearances": 0, "batters": 0,
             "skipped": 0, "no_game": 0, "teams": 0}
    per_team: dict[str, int] = {}
    games: list[dict] = []
    for mo in months:
        games.extend(await fetch_game_ids(season, mo))
    games.sort(key=lambda g: g["date"], reverse=True)      # 최신부터

    for g in games:
        if per_team and min(per_team.values()) >= limit_per_team \
                and len(per_team) >= len(KBO_TEAMS):
            break
        if (per_team.get(g["home"], 0) >= limit_per_team
                and per_team.get(g["away"], 0) >= limit_per_team):
            continue
        starts = datetime.fromisoformat(f"{g['date']}T18:30:00").replace(
            tzinfo=ZoneInfo("Asia/Seoul")).astimezone(UTC)
        # 🔴 [FIND-6 2026-09-23] `_FIND` 는 **여섯 번째 인자**로 출처 ext_id 를
        #    받는다. 종전에는 다섯 개만 넘겨 asyncpg 가 InterfaceError 를 냈고,
        #    백필이 통째로 0 이 됐다 — KBO 적재가 09-12 에서 끊긴 진짜 원인이다
        #    (robots 게이트는 09-21 이라 그보다 9일 뒤다).
        #    ⚠️ 접두사를 `kbo:`(일정)와 **다르게** 둔다. `game_match` 머리말:
        #       "가르는 기준은 ext_id 의 접두사다 — 같으면 다른 경기, 다르면
        #       병합". 박스스코어는 다른 출처이므로 기존 행에 병합돼야 한다.
        #    ⚠️ `None` 을 넘기면 안 된다 — split_part(NULL) 이 NULL 이라
        #       NOT (…) 이 NULL 이 되고 ext_id 있는 행이 전부 탈락한다.
        gid_db = await pool.fetchval(
            _FIND, "kbo", g["home"], g["away"], starts, 20,
            f"kbobox:{g['game_id']}") if pool else None
        if gid_db is None:
            stats["no_game"] += 1
            continue
        try:
            lu = await fetch_lineups(g["game_id"], g["date"])
        except Exception as exc:
            logger.debug("[백필] %s 조회 실패: %s", g["game_id"], exc)
            stats["skipped"] += 1
            continue
        # 🔴 [BAT-3] **선발 9명 파싱 관문보다 앞에서 적재한다.**
        #    `parse_starting_order` 는 9명이 안 되면 빈 목록을 주고, 그러면
        #    아래에서 이 경기가 통째로 버려진다. 타자 성적은 그것과 무관하다.
        stats["batters"] += await batter_log.store_batting(
            pool, gid_db, "kbo", (lu or {}).get("batting") or {}, source="boxscore")
        if not lu or not (lu.get("home") and lu.get("away")):
            stats["skipped"] += 1
            continue
        stats["games"] += 1
        for side in ("home", "away"):
            team = g[side]
            if per_team.get(team, 0) >= limit_per_team:
                continue
            starter = next((p["name"] for p in (lu.get(f"{side}_pitchers") or [])
                            if p.get("is_starter") and p.get("name")), None)
            if await record(pool, gid_db, side, team, lu[side],
                            starter=starter, source="boxscore"):
                stats["rows"] += 1
                per_team[team] = per_team.get(team, 0) + 1
        n_app = await record_appearances(
            pool, gid_db, "kbo", g["home"], g["away"],
            {"home": lu.get("home_pitchers") or [],
             "away": lu.get("away_pitchers") or []},
            source="boxscore")
        stats["appearances"] += n_app
    stats["teams"] = len(per_team)
    logger.info("[백필] 경기 %d · 적재 %d행 · 등판 %d · 타자 %d · %d팀 "
                "(건너뜀 %d · 경기없음 %d)",
                stats["games"], stats["rows"], stats["appearances"],
                stats["batters"], stats["teams"], stats["skipped"], stats["no_game"])
    return stats
