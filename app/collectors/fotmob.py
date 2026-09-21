"""[FOT-1] FotMob — 라인업·결장을 **구조 JSON 으로** 받는다 (사용자 지시).

🔴 **추출 1순위는 LLM 이 아니라 이것이다.** 기사에서 뽑던 방식은 groq 무료
   한도에 막혔고(실측 2026-09-14: 429 백오프 340~527초), 뽑아도 로마 `out` 이
   비었다. 같은 사실이 FotMob JSON 에는 칸으로 들어 있다.

🔴 **경로는 실측한 것을 쓴다.** 지시문의 `/api/matches`·`/api/matchDetails` 는
   404(HTML)였고, 실제로 200 을 주는 것은 `/api/data/...` 다 (실측 2026-09-14).

🔴 **`unavailable` 키가 없는 것은 "결장 0명"이 아니라 "모른다"** 다.
   실측: 토리노에는 있고 로마에는 **키 자체가 없었다.** None 으로 돌려주고
   호출부가 교차검증(API-Football)·`missing` 으로 넘긴다.

⚠️ UA·Referer 헤더가 필요하다. 요청 간격 2초(사용자 지시).
⚠️ 이 모듈은 **받아서 모양만 고른다.** 판정·가공은 호출부의 일이다.
"""
from __future__ import annotations

import asyncio
import logging
import time
import pathlib
import unicodedata

logger = logging.getLogger(__name__)

BASE = "https://www.fotmob.com/api/data"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "application/json",
           "Referer": "https://www.fotmob.com/"}

#: 요청 최소 간격(초) — 사용자 지시.
MIN_GAP_SEC = 2.0
TIMEOUT = 25

#: 라인업 단계. 🔴 **그대로 저장한다** — T-60 재호출에서 이 값이 바뀌는 것이
#  Part 1-B 이동 분류의 입력이다.
PREDICTED, CONFIRMED = "predicted", "confirmed"

_last_at = 0.0


async def _pace() -> None:
    global _last_at
    gap = MIN_GAP_SEC - (time.monotonic() - _last_at)
    if _last_at and gap > 0:
        await asyncio.sleep(gap)
    _last_at = time.monotonic()


async def _get(path: str, params: dict) -> dict | None:
    """실패는 **결측**이다 — 예외를 올리지 않고 None 을 준다."""
    import httpx

    await _pace()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True,
                                     headers=HEADERS) as c:
            r = await c.get(f"{BASE}/{path}", params=params)
        if r.status_code != 200:
            logger.warning("[fotmob] %s %s — status %s", path, params, r.status_code)
            return None
        return r.json()
    except Exception as exc:
        logger.warning("[fotmob] %s %s 실패: %s", path, params, exc)
        return None


#: [FMR-1 2026-09-20] 발음부호 치환표. 🔴 원본은 `config/team_name_map.yaml` 이다.
_NAME_MAP: dict | None = None


def _name_map() -> dict:
    global _NAME_MAP
    if _NAME_MAP is None:
        try:
            import yaml

            f = (pathlib.Path(__file__).resolve().parents[2]
                 / "config" / "team_name_map.yaml")
            _NAME_MAP = (yaml.safe_load(f.read_text(encoding="utf-8")) or {}) \
                .get("replace") or {}
        except Exception as exc:
            logger.warning("[fotmob] 이름 치환표 로드 실패: %s", exc)
            _NAME_MAP = {}
    return _NAME_MAP


def norm(name: str) -> str:
    """비교용 정규화. 🔴 퍼지 금지 — 악센트·기호만 지운다.

    🔴 [FMR-1] **치환을 먼저 한다.** `NFKD → ascii ignore` 는 `á`·`ö` 는
       분해해 기본 문자를 남기지만, `ø`·`æ`·`ß`·`ł`·`đ` 는 분해되지 않는
       독립 문자라 **통째로 지운다**(실측: `Brøndby IF` → `brndby if`).
       그래서 우리 `Brondby IF`(→`brondby if`)와 영영 안 맞았다.
    ⚠️ 치환표는 `config/team_name_map.yaml` 이 원본이다 — 코드에 박지 않는다.
    ⚠️ 언어가 다르거나(København↔Copenhagen) 개명(Jeju SK)인 것은 치환으로
       풀리지 않는다 — `config/team_alias_pending.yaml` → 승인 → 별칭표다.
    """
    raw = str(name or "")
    for a, b in _name_map().items():
        raw = raw.replace(a, b)
    s = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace("-", " ").split())


#: [FMR-1] 상태 매핑. 🔴 `reason.short` 가 원본이다 — `statusId` 는 뜻이
#  문서화돼 있지 않아 읽지 않는다(추측 금지).
_FINAL_REASONS = ("FT", "AET", "Pen", "AP", "PEN")


def status_of(st: dict | None) -> tuple:
    """FotMob `status` → `(우리 status, result_basis)`.

    🔴 `AET`·`Pen` 도 **종료는 종료**다 — 점수는 저장하고 채점만 따로 본다.
    ⚠️ 연기·취소·중단은 **final 이 아니다.**
    """
    st = st or {}
    short = str(((st.get("reason") or {}).get("short")) or "")
    if st.get("cancelled"):
        return "cancelled", None
    if st.get("finished"):
        if short in ("AET", "Pen", "AP", "PEN"):
            return "final", short
        if short == "FT" or not short:
            return "final", "FT"
        # 🔴 종료인데 모르는 표지 — final 로 올리지 않는다(추측 금지).
        return "suspended", short
    if short:
        return "postponed", short
    return "scheduled", None


def score_at_90(events) -> tuple | None:
    """득점 이벤트 → **90분 점수**. 없으면 `(0, 0)`.

    🔴 실측(matchId 6144851): 후반 추가시간은 `time=90` + `overloadTime`,
       연장 득점은 `time >= 91` 로 온다. 그래서 `time <= 90` 만 합산한다.
    🔴 승부차기는 본선 `events` 에 `newScore=None` 으로만 있고 점수는
       `penaltyShootoutEvents` 별도 배열이다 — **어디에도 합산하지 않는다.**
    """
    best = (0, 0)
    for e in events or []:
        if not isinstance(e, dict):
            continue
        sc = e.get("newScore")
        if not (isinstance(sc, (list, tuple)) and len(sc) == 2):
            continue
        try:
            t = int(e.get("time"))
        except (TypeError, ValueError):
            continue
        if t > 90:
            continue
        best = (int(sc[0]), int(sc[1]))
    return best


def ninety_ok(score) -> bool:
    """연장에 간 경기의 90분 점수가 **말이 되는가.**

    🔴 동점이라야 연장에 간다. 아니면 계산이 틀린 것이고, 그때는
       **수동 확인 목록**으로 보낸다 — 추측으로 채점하지 않는다.
    """
    if not (isinstance(score, (list, tuple)) and len(score) == 2):
        return False
    return score[0] == score[1]


async def slate(date_yyyymmdd: str) -> list[dict]:
    """그 날짜의 전 경기. `[{id, league, home, away, utc}]`. 실패면 빈 목록."""
    d = await _get("matches", {"date": date_yyyymmdd})
    out: list[dict] = []
    for lg in (d or {}).get("leagues") or []:
        for m in lg.get("matches") or []:
            st = m.get("status") or {}
            status, basis = status_of(st)
            h, a = m.get("home") or {}, m.get("away") or {}
            out.append({
                "id": m.get("id"),
                "league": lg.get("name"),
                "league_id": lg.get("id") or lg.get("primaryId"),
                "ccode": lg.get("ccode"),
                "home": h.get("name"),
                "away": a.get("name"),
                # 🔴 [FMR-1] **점수를 버리지 않는다.** 종전에는 이름·시각만
                #    뽑아서 J·K·UEL·ACL 결과가 전부 유실됐다(실측: 그 리그들의
                #    `games.status` 가 전건 `scheduled`).
                "home_id": h.get("id"), "away_id": a.get("id"),
                "home_score": h.get("score"), "away_score": a.get("score"),
                "home_pen": h.get("penScore"), "away_pen": a.get("penScore"),
                "finished": bool(st.get("finished")),
                "score_str": st.get("scoreStr"),
                "reason": ((st.get("reason") or {}).get("short")),
                "status": status, "result_basis": basis,
                "utc": st.get("utcTime"),
            })
    logger.info("[fotmob] %s — %d경기", date_yyyymmdd, len(out))
    return out


def find_match(rows: list[dict], *, home: str, away: str) -> dict | None:
    """우리 경기 ↔ FotMob 경기. **양쪽 이름이 다 맞아야** 붙인다.

    🔴 퍼지 유사도를 쓰지 않는다(AC밀란 오매칭 전례). 정규화 후 한쪽이
       다른 쪽을 **포함**하면 같은 팀으로 본다(`Torino` ⊂ `Torino FC`).
    """
    h, a = norm(home), norm(away)
    # 🔴 [ACL-2 2026-09-15] **FotMob 쪽만** canonical 을 거친다. `home`/`away`
    #    인자는 이미 우리 `games` 표기(=canonical)라 또 매핑하면 안 된다.
    #    ACL-1 이 `Daejeon Hana Citizen → Daejeon Citizen` 을 넣은 순간
    #    이 함수가 그 경기를 못 찾았다(실측: C-5 매칭 0).
    for r in rows or []:
        rh, ra = norm(canonical(r.get("home"))), norm(canonical(r.get("away")))
        if not rh or not ra:
            continue
        if (rh in h or h in rh) and (ra in a or a in ra):
            return r
    return None


def _players(side: dict) -> list[dict]:
    """선발 명단 → `[{id, name, market_value, position_id, shirt}]`.

    🔴 **id 를 반드시 싣는다** — 주전 판정은 이름이 아니라 id 로 센다(사용자 지시).
    🔴 [U6 2026-09-15] 시장가치를 함께 싣는다. 원자료에 있는데 버리고 있었다
       (실측: `starters[].marketValue = 1173408`). U8 의 `importance` 가 이
       값을 쓴다 — 없으면 결장이 **이름 수**로 세어진다.
    ⚠️ 기존 키(`id`·`name`)는 **그대로 둔다.** 읽는 곳이 넷이다.
    """
    out: list[dict] = []
    for grp in (side or {}).get("starters") or []:
        items = grp if isinstance(grp, list) else [grp]
        for x in items:
            if isinstance(x, dict) and (x.get("id") or x.get("name")):
                out.append({
                    "id": x.get("id"),
                    "name": x.get("name") or x.get("fullName"),
                    "market_value": x.get("marketValue"),
                    "position_id": x.get("positionId"),
                    "shirt": x.get("shirtNumber"),
                })
    return out


def parse_form(details: dict) -> dict:
    """[U6] 최근 경기 결과 → `{"home": [...], "away": [...]}`.

    🔴 원본은 `content.matchFacts.teamForm` 이고 **[홈, 원정] 두 칸**이다.
       한 경기는 `{"resultString": "W", "date": {...}, "linkToMatch": …}`.
    ⚠️ 없으면 빈 목록이다 — 0승으로 읽지 않는다.
    """
    tf = (((details or {}).get("content") or {}).get("matchFacts") or {}) \
        .get("teamForm")
    out = {"home": [], "away": []}
    if not isinstance(tf, list):
        return out
    for i, key in enumerate(("home", "away")):
        rows = tf[i] if len(tf) > i and isinstance(tf[i], list) else []
        for m in rows[:5]:
            if not isinstance(m, dict):
                continue
            out[key].append({
                "result": m.get("resultString"),
                "utc": ((m.get("date") or {}).get("utcTime")
                        if isinstance(m.get("date"), dict) else None),
                "link": m.get("linkToMatch"),
            })
    return out


def _unavailable(side: dict):
    """결장 명단. 🔴 **키가 없으면 None**(모른다) — 빈 목록(0명)과 다르다."""
    if "unavailable" not in (side or {}):
        return None
    out = []
    for x in (side.get("unavailable") or []):
        if not isinstance(x, dict):
            continue
        u = x.get("unavailability") or {}
        out.append({"id": x.get("id"), "name": x.get("name"),
                    "type": u.get("type"), "expected_return": u.get("expectedReturn")})
    return out


def parse_lineup(details: dict) -> dict | None:
    """matchDetails → 라인업 요약. 없으면 None."""
    lu = ((details or {}).get("content") or {}).get("lineup") or {}
    if not lu.get("homeTeam") and not lu.get("awayTeam"):
        return None
    out = {"lineup_type": lu.get("lineupType"), "source": lu.get("source"),
           "match_id": lu.get("matchId")}
    for key, side in (("home", "homeTeam"), ("away", "awayTeam")):
        t = lu.get(side) or {}
        out[key] = {
            "team_id": t.get("id"), "team": t.get("name"),
            "formation": t.get("formation"),
            # 🔴 [U6] 팀 선발 총가치. importance 의 분모다
            #    (실측: 가시마 6,352,468 · 뉴캐슬제츠 4,098,733).
            "total_market_value": t.get("totalStarterMarketValue"),
            "avg_age": t.get("averageStarterAge"),
            "starters": _players(t),
            "bench": [{"id": x.get("id"), "name": x.get("name")}
                      for x in (t.get("subs") or []) if isinstance(x, dict)],
            "unavailable": _unavailable(t),
            "coach": ((t.get("coach") or {}) or {}).get("name")
            if isinstance(t.get("coach"), dict) else t.get("coach"),
        }
    # 🔴 [U6] 최근 5경기. 같은 응답에서 읽는다 — 요청은 늘지 않는다.
    out["last5"] = parse_form(details)
    return out


async def match_lineup(match_id) -> dict | None:
    """경기 하나의 라인업 요약. 실패·결측이면 None."""
    d = await _get("matchDetails", {"matchId": match_id})
    return parse_lineup(d) if d else None


def diff_xi(before: dict | None, after: dict | None) -> dict:
    """[사용자 지시 2] 예상 XI → 공식 XI **차이를 코드가 센다.**

    반환 `{side: {"bench_notable": [...], "surprise_in": [...]}}`.
    🔴 **id 로 센다.** 이름 매칭은 금지(동명이인·표기 흔들림).
    ⚠️ 한쪽이라도 없으면 빈 dict — 모르는 것을 "변화 없음"으로 만들지 않는다.
    """
    if not before or not after:
        return {}
    out: dict = {}
    for side in ("home", "away"):
        b = {p.get("id") for p in ((before.get(side) or {}).get("starters") or [])
             if p.get("id")}
        a_list = (after.get(side) or {}).get("starters") or []
        a = {p.get("id") for p in a_list if p.get("id")}
        if not b or not a:
            continue
        names = {p.get("id"): p.get("name") for p in a_list}
        bnames = {p.get("id"): p.get("name")
                  for p in ((before.get(side) or {}).get("starters") or [])}
        out[side] = {
            # 예상 선발이었는데 공식에서 빠졌다
            "bench_notable": [bnames.get(i) for i in sorted(b - a, key=str)],
            # 예상에 없었는데 공식에 들어왔다
            "surprise_in": [names.get(i) for i in sorted(a - b, key=str)],
        }
    return out


#: 예상 XI 보관 키 — T-60 재호출에서 `confirmed` 와 대조하려고 남긴다.
XI_KEY = "fotmob:xi:{game_id}"


async def attach(jg: dict, *, redis=None, date_yyyymmdd: str | None = None) -> dict:
    """[FOT-1] 경기 하나에 라인업·결장을 붙인다. 반환은 붙인 요약(없으면 {}).

    `jg["fotmob"]` 에 넣는다:
      lineup_type · formation · starters(id·이름) · bench · unavailable(None=모름)
      · diff(예상→공식, confirmed 일 때만) · missing(모르는 칸)

    🔴 **`unavailable` 이 None 이면 `missing` 에 남긴다.** 0명으로 쓰지 않는다.
    ⚠️ 실패는 결측이다 — 예외를 올리지 않는다.
    """
    import json as _json
    from datetime import datetime, timezone

    d = date_yyyymmdd
    if not d:
        ts = jg.get("starts_at")
        ts = ts if isinstance(ts, datetime) else datetime.now(timezone.utc)
        d = ts.astimezone(timezone.utc).strftime("%Y%m%d")
    rows = await slate(d)
    m = find_match(rows, home=jg.get("home") or "", away=jg.get("away") or "")
    if m is None:
        logger.info("[fotmob] %s@%s — 그 날짜 표에 없다(%s)",
                    jg.get("away"), jg.get("home"), d)
        return {}
    lu = await match_lineup(m["id"])
    if not lu:
        logger.info("[fotmob] match=%s — 라인업 칸이 없다", m["id"])
        return {}

    before = None
    if redis is not None and jg.get("game_id"):
        try:
            raw = await redis.get(XI_KEY.format(game_id=jg["game_id"]))
            before = _json.loads(raw) if raw else None
        except Exception:
            before = None

    missing = [f"{side} 결장 명단 미제공" for side in ("home", "away")
               if (lu.get(side) or {}).get("unavailable") is None]
    out = dict(lu)
    out["missing"] = missing
    # 🔴 [사용자 지시 2] confirmed 로 바뀌면 예상 XI 와 **코드가** 대조한다.
    if lu.get("lineup_type") == CONFIRMED and before:
        out["diff"] = diff_xi(before, lu)
    jg["fotmob"] = out

    if redis is not None and jg.get("game_id"):
        try:
            await redis.set(XI_KEY.format(game_id=jg["game_id"]),
                            _json.dumps(lu, ensure_ascii=False), ex=12 * 3600)
        except Exception as exc:
            logger.debug("[fotmob] XI 보관 실패 game=%s: %s", jg.get("game_id"), exc)
    logger.info("[fotmob] %s@%s match=%s %s — 선발 %d/%d · 결장 %s/%s%s",
                jg.get("away"), jg.get("home"), m["id"], lu.get("lineup_type"),
                len((lu.get("home") or {}).get("starters") or []),
                len((lu.get("away") or {}).get("starters") or []),
                _n(lu, "home"), _n(lu, "away"),
                f" · diff {out.get('diff')}" if out.get("diff") else "")
    return out


def _n(lu: dict, side: str) -> str:
    v = (lu.get(side) or {}).get("unavailable")
    return "모름" if v is None else str(len(v))


#: [FOT-5] 소급 적재 대상 국가 코드(사용자 지시).
#  🔴 리그 **이름**으로 거르지 않는다 — "Serie A" 는 이탈리아와 에콰도르가
#     같이 쓴다(실측 2026-09-14: Delfín vs Técnico Universitario 가 섞였다).
BACKFILL_CCODES = ("ITA", "ESP", "ENG", "GER", "FRA", "NED", "KOR", "JPN", "POR")

_HISTORY_SQL = """
    INSERT INTO lineup_history (game_id, team_id, player_id, player_name,
                                started, minutes, lineup_type, kickoff_utc,
                                league, ccode, kickoff_date)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
    ON CONFLICT (game_id, team_id, player_id, lineup_type) DO UPDATE
      SET started = EXCLUDED.started,
          minutes = COALESCE(EXCLUDED.minutes, lineup_history.minutes),
          player_name = EXCLUDED.player_name,
          -- 🔴 [LH-1] 이미 있는 값을 NULL 로 덮지 않는다.
          league = COALESCE(EXCLUDED.league, lineup_history.league),
          ccode = COALESCE(EXCLUDED.ccode, lineup_history.ccode),
          kickoff_date = COALESCE(EXCLUDED.kickoff_date,
                                  lineup_history.kickoff_date),
          captured_at = now()
"""

#: [LH-1] 과거 행의 리그를 날짜별 목록으로 역매핑한다. **경기 상세는 부르지
#  않는다**(사용자 지시). 목록에 id·ccode·league·utc 가 다 들어 있다.
_HISTORY_META_SQL = """
    UPDATE lineup_history
       SET league = COALESCE(league, $2), ccode = COALESCE(ccode, $3),
           kickoff_date = COALESCE(kickoff_date, $4::date)
     WHERE game_id = $1 AND (league IS NULL OR ccode IS NULL
                             OR kickoff_date IS NULL)
"""


async def backfill_meta(pool, dates: list[str]) -> dict:
    """[LH-1] 이미 쌓인 행에 리그·킥오프를 채운다. 반환 `{날짜: 갱신 행 수}`.

    🔴 **날짜별 목록만 쓴다** — 경기 상세 재호출 금지(사용자 지시).
    ⚠️ 못 찾은 `game_id` 는 **건드리지 않는다**. NULL 이 곧 "모른다"다.
    """
    out: dict = {}
    for d in dates:
        rows = await slate(d)
        n = 0
        for r in rows:
            if not r.get("id"):
                continue
            kd = _as_date(r.get("utc"))
            try:
                res = await pool.execute(_HISTORY_META_SQL, int(r["id"]),
                                         r.get("league"), r.get("ccode"), kd)
                n += int(str(res or "").split()[-1] or 0)
            except Exception as exc:
                logger.warning("[fotmob] 메타 갱신 실패 game=%s: %s", r["id"], exc)
        out[d] = n
        logger.info("[fotmob] 메타 %s — %d경기 목록 · %d행 갱신", d, len(rows), n)
    return out


def _as_dt(v):
    """ISO 문자열 → `datetime`. 🔴 [LH-2] asyncpg 는 TIMESTAMPTZ 에 문자열을
    받지 않는다(ODP-2 와 같은 결함이 재발했다). 모르면 None."""
    from datetime import datetime as _dt

    if v is None or isinstance(v, _dt):
        return v
    try:
        return _dt.fromisoformat(str(v).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _as_date(v):
    """ISO 문자열/datetime → `date`. 🔴 `$n::date` 는 `date` 만 받는다."""
    from datetime import date as _d
    from datetime import datetime as _dt

    if v is None or isinstance(v, _d) and not isinstance(v, _dt):
        return v
    if isinstance(v, _dt):
        return v.date()
    try:
        return _d.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


async def save_lineup_history(pool, lineup: dict, *, kickoff_utc=None,
                              league: str | None = None,
                              ccode: str | None = None) -> int:
    """[FOT-5] 선발·벤치를 이력 표에 남긴다. 반환 적재 행 수.

    🔴 **선수 id 가 없으면 건너뛴다.** 0을 키로 쓰면 서로 다른 선수가 한
       사람이 된다(실측: 일부 리그에 `id=0` 이 있다).
    ⚠️ `lineup_type` 을 그대로 남긴다 — confirmed(T-60 이후)와 standard
       (경기 후)를 **따로** 세야 출장률이 정직하다.
    """
    if pool is None or not lineup:
        return 0
    gid, lt = lineup.get("match_id"), lineup.get("lineup_type")
    if gid is None or not lt:
        return 0
    n = 0
    for side in ("home", "away"):
        box = lineup.get(side) or {}
        tid = box.get("team_id")
        rows = [(p, True) for p in (box.get("starters") or [])]
        rows += [(p, False) for p in (box.get("bench") or [])]
        for p, started in rows:
            pid = p.get("id")
            if not pid:
                continue
            try:
                await pool.execute(_HISTORY_SQL, int(gid), tid, int(pid),
                                   p.get("name") or "", started,
                                   p.get("minutes"), lt, _as_dt(kickoff_utc),
                                   league, ccode, _as_date(kickoff_utc))
                n += 1
            except Exception as exc:
                logger.warning("[fotmob] 이력 적재 실패 game=%s player=%s: %s",
                               gid, pid, exc)
    if n:
        logger.info("[fotmob] 이력 %d행 (match=%s %s)", n, gid, lt)
    return n


async def backfill(pool, dates: list[str], *, ccodes=BACKFILL_CCODES) -> dict:
    """[FOT-5] 과거 날짜의 확정 XI 를 이력 표에 소급 적재한다.

    반환 `{리그: 적재 경기 수}`. 🔴 국가 코드로 거른다(이름 겹침 실측).
    """
    out: dict = {}
    for d in dates:
        rows = [r for r in await slate(d) if r.get("ccode") in ccodes]
        for r in rows:
            lu = await match_lineup(r["id"])
            if not lu:
                continue
            got = await save_lineup_history(
                pool, lu, kickoff_utc=r.get("utc"),
                league=r.get("league"), ccode=r.get("ccode"))
            if got:
                key = f"{r.get('ccode')} {r.get('league')}"
                out[key] = out.get(key, 0) + 1
        logger.info("[fotmob] 소급 %s — 대상 %d경기 · 누적 %s", d, len(rows), out)
    return out


#: 🔴 [ACL-1 2026-09-15] FotMob 표기 → 우리 canonical 표기.
#   지금은 **항등**이다 — ACL 팀은 FotMob 이 유일한 적재원이라 그 표기가 곧
#   canonical 이다. 표를 비워 두지 않고 명시하는 이유는, 다른 소스(오즈포털)가
#   같은 팀을 다르게 적기 때문이다. 그쪽 별칭은 `oddsportal.SOCCER_ALIAS` 에 있고
#   **값이 이 표의 키**다. 두 표가 만나는 지점을 계약이 대조한다.
SLATE_CANONICAL: dict[str, str] = {
    # 🔴 같은 구단이 리그마다 다른 이름을 갖지 않게 한다. K리그1 은 이미
    #    `Daejeon Citizen` 으로 들어와 있다(oddsportal.SOCCER_ALIAS) — ACL 이
    #    `Daejeon Hana Citizen` 으로 또 만들면 **한 구단이 두 팀**이 된다.
    "Daejeon Hana Citizen": "Daejeon Citizen",
}


def canonical(name: str) -> str | None:
    """FotMob 팀명 → 우리 표기. 모르면 **None**(조용히 지어내지 않는다)."""
    n = " ".join(str(name or "").split())
    if not n:
        return None
    return SLATE_CANONICAL.get(n, n)


def league_matches(fotmob_league: str, league_key: str) -> bool:
    """FotMob 리그명이 **이 리그인가.** 🔴 고르는 규칙은 여기 한 곳이다.

    🔴 [W3-1 2026-09-21] `fotmob_league` 가 있으면 **정확 일치**다.
       종전 `fotmob_contains` 는 부분 문자열이라, J1 에 `'J. League'` 를
       넣는 순간 `'J. League 2'`·`'J. League 3'` 가 전부 1부로 적재된다
       (실측: 하루 9+8경기). 이름을 넣는 것만으로 결함이 되는 자리다.

    ⚠️ 옛 키(`fotmob_contains`)는 **그대로 둔다** — ACL 은 종전 규칙으로 돈다.
       바꾸지 않은 리그의 동작은 한 글자도 달라지지 않는다.
    ⚠️ 둘 다 없으면 **False** 다. "설정이 없으면 전부"는 위험한 기본값이다.
    """
    from app.leagues import LEAGUES

    cfg = LEAGUES.get(league_key) or {}
    name = str(fotmob_league or "")
    exact = cfg.get("fotmob_league")
    if exact:
        return name.strip() == str(exact).strip()
    needle = cfg.get("fotmob_contains")
    return bool(needle) and needle in name


async def upsert_slate(pool, date_yyyymmdd: str, *, league_key: str) -> dict:
    """[ACL-1] FotMob 슬레이트 → `games`. 반환 `{fetched, matched, saved, skipped}`.

    🔴 **The Odds API 에 없는 대회를 받는 유일한 길이다.** 종목 178개를 전수
       조회했고 AFC 계열 키가 0개였다(실측 2026-09-15). 기존 적재
       (`odds.upsert_games_from_odds_events`)는 `odds_key` 가 있어야 돈다.
    🔴 키는 **fotmob_id** 다 — `ext_id = 'fotmob:{id}'`. `odds:{id}` 와 섞이지
       않는다(UNIQUE(sport, ext_id)).
    🔴 별칭으로 canonical 을 못 찾으면 **로그를 남기고 제외**한다. 이름을
       추측해서 넣으면 배당이 엉뚱한 경기에 붙는다(AC밀란 오매칭 전례).
    ⚠️ 이 함수는 ACL 전용이 아니다 — `league_key` 의 `fotmob_contains` 로
       고른다. ACL2·컵대회·A매치도 항목만 추가하면 같은 길로 들어온다.
    """
    from app.leagues import LEAGUES

    cfg = LEAGUES.get(league_key) or {}
    # 🔴 [W3-1] 고르는 규칙은 `league_matches` 한 곳이다. 여기서 문자열을
    #    다시 비교하지 않는다(사본 금지).
    needle = cfg.get("fotmob_league") or cfg.get("fotmob_contains")
    # 🔴 [ACL-3 2026-09-15] `ext_ids` 를 **반드시** 돌려준다. 축구는 슬레이트를
    #    DB 에서 다시 읽지 않고 이 반환값을 그대로 쓴다(ext_id 재조회는 야구
    #    전용 분기다). 형제 함수(`upsert_games_from_football_data`·
    #    `upsert_games_from_odds_events`)와 같은 계약이다.
    out = {"fetched": 0, "matched": 0, "saved": 0, "skipped": [], "ext_ids": []}
    if not needle:
        logger.warning("[fotmob] %s 에 fotmob_contains 가 없다 — 적재 생략", league_key)
        return out
    rows = await slate(date_yyyymmdd)
    out["fetched"] = len(rows)
    for r in rows:
        if not league_matches(r.get("league") or "", league_key):
            continue
        out["matched"] += 1
        h, a = canonical(r.get("home")), canonical(r.get("away"))
        ko = _as_dt(r.get("utc"))
        if not (h and a and ko and r.get("id")):
            out["skipped"].append(f"{r.get('away')}@{r.get('home')}"
                                  f"(이름·시각·id 결측)")
            logger.warning("[fotmob] 적재 제외 %s @ %s — canonical/시각/id 결측",
                           r.get("away"), r.get("home"))
            continue
        # 🔴 [FMR-1 2026-09-20] **점수·상태를 함께 쓴다.** 종전에는 항상
        #    `'scheduled'` 로 넣어서, 이 경로로만 들어오는 리그(J·K·UEL·ACL)의
        #    결과가 **영원히 안 채워졌다**(실측: 그 리그들 status 전건 scheduled ·
        #    ACL 판정 8건이 채점 0).
        # ⚠️ 멱등이다 — 같은 날 두 번 돌려도 같은 행을 갱신한다(ext_id 유니크).
        # ⚠️ 점수는 **덮어쓰지 않고** coalesce 한다. 다른 소스(football-data)가
        #    먼저 넣었으면 그 값이 남고, 차이는 아래 conflict 로그가 잡는다.
        hs, as_ = r.get("home_score"), r.get("away_score")
        st = r.get("status") or "scheduled"
        basis = r.get("result_basis")
        if st == "final" and basis in ("AET", "Pen", "AP", "PEN"):
            # 🔴 연장·승부차기는 **90분 점수로 채점**해야 한다. 여기서는
            #    저장만 하고 `result_basis` 를 남긴다 — 90분 점수 산출은
            #    `score_at_90`(상세 호출)이고 FT 가 아닌 경기에만 부른다.
            out.setdefault("needs_90", []).append(
                {"ext_id": f"fotmob:{r['id']}", "match_id": r["id"],
                 "basis": basis, "final_score": [hs, as_]})
        prev = await pool.fetchrow(
            "SELECT home_score, away_score FROM games "
            "WHERE sport='soccer' AND ext_id=$1", f"fotmob:{r['id']}")
        if (prev and prev["home_score"] is not None and hs is not None
                and (prev["home_score"], prev["away_score"]) != (hs, as_)):
            out.setdefault("conflict", []).append(
                {"ext_id": f"fotmob:{r['id']}",
                 "db": [prev["home_score"], prev["away_score"]],
                 "fotmob": [hs, as_]})
            logger.warning("[fotmob] 점수 충돌 %s — DB %s vs FotMob %s (덮지 않는다)",
                           f"fotmob:{r['id']}",
                           [prev["home_score"], prev["away_score"]], [hs, as_])
        # 🔴 [W3-1b 2026-09-21] **다른 소스의 같은 경기를 찾아 그 행에 쓴다.**
        #    종전에는 `ON CONFLICT (sport, ext_id)` 로 **자기 ext_id 만** 봤다.
        #    그래서 W3-1 배포 직후 같은 경기가 두 행이 됐다(실측):
        #        K리그1 Incheon United vs Daejeon Citizen  09-20 10:00Z
        #          odds:f882c79a…  status=scheduled  score=None  ← 판정·픽이 붙은 행
        #          fotmob:5140040  status=final      score=1     ← 점수가 들어간 행
        #    판정이 붙은 행은 여전히 `scheduled` 라 **채점이 안 닫힌다** —
        #    점수를 엉뚱한 행에 쓴 셈이다.
        # 🔴 매칭 규칙을 여기서 새로 짓지 않는다. `game_match.apply_result` 가
        #    이미 그 일을 한다("기존 행을 찾으면 그 행을 갱신한다 — 그래야 그
        #    행에 붙은 예측이 채점된다"). 같은 소스의 다른 id 는 다른 경기로
        #    가르는 규칙(GM-4)도 그쪽에 있다.
        from app.collectors.game_match import apply_result

        mode = await apply_result(
            pool, sport="soccer", league=cfg.get("label") or league_key,
            ext_id=f"fotmob:{r['id']}", starts_at=ko, home=h, away=a,
            status=st, home_score=hs, away_score=as_)
        # ⚠️ **킥오프 갱신은 잃지 않는다.** `apply_result` 의 UPDATE 는
        #    status·점수만 쓴다. 종전 `ON CONFLICT` 는 `starts_at` 도 새로
        #    썼고, 일정이 옮겨지는 대회(ACL·컵)에서 그 값이 필요하다.
        #    ⚠️ **끝난 경기의 시각은 건드리지 않는다** — 이미 치른 경기의
        #       시각을 나중 목록이 흔들면 그 자체가 오염이다.
        if mode == "updated" and st != "final":
            await pool.execute(
                "UPDATE games SET starts_at = $2, updated_at = now() "
                "WHERE sport = 'soccer' AND ext_id = $1 AND status <> 'final'",
                f"fotmob:{r['id']}", ko)
        out["ext_ids"].append(f"fotmob:{r['id']}")
        out["saved"] += 1
    logger.info("[fotmob] %s 적재 — 슬레이트 %d · 해당 %d · 저장 %d · 제외 %d",
                league_key, out["fetched"], out["matched"], out["saved"],
                len(out["skipped"]))
    return out
