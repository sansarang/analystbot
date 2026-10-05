"""해외축구 일정 — `football-data.org`. §9 단계 9 의 **"해외축구"** 가 이것이다.

🔴 **유료 API 가 아니다**(§19-i-1 정의): *"카드 미등록·과금 0·무료 플랜 상한 안에서
   도는 키는 유료가 아니다."* football-data.org 무료 티어는 **키만 발급**하고 카드를
   요구하지 않는다. `.env` 의 `FOOTBALL_DATA_KEY` 가 그것이고, `app/config.py` 가
   이미 읽고 있었다 — **부르는 곳이 없었을 뿐이다**(안 이어진 코드).

실측 2026-09-30: 키가 살아 있고 플랜은 `TIER_ONE`, **13개 대회**다.

```
Premier League · Championship · UEFA Champions League · European Championship
Ligue 1 · Bundesliga · Serie A · Eredivisie · Primeira Liga · Primera Division
Campeonato Brasileiro Série A · Copa Libertadores · FIFA World Cup
```

⚠️ **K리그·J리그는 그 13개에 없다.** 그 둘은 검색 경로(`app/collect/kleague.py`)로
   간다 — 여기서 있는 척하지 않는다.

🔴 **무료 상한이 있다**: 분당 10회. 하루 이틀치(D+0·D+1)를 **한 요청**으로 받으므로
   상한 안이다 — `dateFrom`/`dateTo` 를 쓴다.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from app import matchkey, timefmt, window
from app.blackboard import Fact
from app.cells import Question, Source
from app.config import get_settings
from app.net import Fetched

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))
SPORT = "soccer"
#: 🔴 이 이름이 `ADAPTERS` 의 열쇠다. 개별 대회 이름은 **응답이 정한다** —
#   13개를 손으로 적으면 그 목록이 한 발 늦는다(CLAUDE.md §사본 금지).
LEAGUE = "해외축구"

BASE = "https://api.football-data.org/v4/matches"

#: football-data `status` → 우리 규약. 🔴 모르는 값은 **이름으로 남긴다.**
STATUS = {
    "SCHEDULED": "scheduled", "TIMED": "scheduled",
    "IN_PLAY": "inprogress", "PAUSED": "inprogress",
    "FINISHED": "final", "AWARDED": "final",
    "POSTPONED": "postponed", "SUSPENDED": "postponed",
    "CANCELLED": "postponed",
}


def api_key() -> str:
    """🔴 키가 없으면 **빈 문자열**이다 — 없는 것을 있는 척하지 않는다."""
    return (get_settings().football_data_key or "").strip()


def schedule_url() -> str:
    return BASE


def parse_schedule(got: Fetched, day: date | None = None) -> list[dict]:
    """football-data 응답 → `games` 행.

    🔴 **요청한 날짜만** 골라 낸다(§14-9). 한 요청으로 이틀을 받으므로 응답에는
       내일 것도 들어 있다 — 호출부가 날짜별로 따로 요청한다.
    ⚠️ 대회 이름은 **응답이 준다**(`competition.name`). 13개를 여기 적지 않는다.
    """
    if not got.ok:
        return []
    try:
        data = json.loads(got.text)
    except ValueError as exc:
        logger.warning("[fdorg] JSON 이 아니다: %s", exc)
        return []

    out: list[dict] = []
    skipped: list[str] = []
    for m in data.get("matches") or []:
        row = _row(m)
        if not row:
            continue
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
            # 🔴 **조용히 버리지 않는다**(#3) — *"날짜가 다르다"* 는 거짓
            #    사유였다(§8-6). 창 밖인지 이미 지났는지를 가려 적는다.
            skipped.append(f"{row.get('home')}–{row.get('away')}: {said}")
            continue
        out.append(row)
    if skipped:
        logger.info("[fdorg] 창 밖 %d경기 — %s", len(skipped),
                    " · ".join(skipped[:3]))
    logger.info("[fdorg] %s 일정 %d경기 · 대회 %s", day, len(out),
                sorted({r["league"] for r in out})[:6])
    return out


def _row(m: dict) -> dict | None:
    start = _when(m.get("utcDate"))
    if start is None:
        return None                     # 🔴 시각을 모르면 슬레이트에 안 넣는다
    home = ((m.get("homeTeam") or {}).get("name") or "").strip()
    away = ((m.get("awayTeam") or {}).get("name") or "").strip()
    if not (home and away):
        # 🔴 추첨 전 경기는 팀이 비어 온다 — 지어내지 않고 버린다
        return None
    raw = str(m.get("status") or "")
    status = STATUS.get(raw)
    if status is None:
        logger.info("[fdorg] 모르는 status=%r — scheduled 로 때우지 않는다", raw)
        status = f"unknown:{raw}"
    score = (m.get("score") or {}).get("fullTime") or {}
    return {
        "sport": SPORT,
        # 🔴 대회 이름을 **리그로 쓴다** — EPL 과 UCL 은 다른 슬레이트다
        "league": ((m.get("competition") or {}).get("name") or LEAGUE),
        # 🔴 §8-1 — `출처:경기ID`(종전 `fd-…`)
        "ext_id": matchkey.make("fdorg", m.get("id")),
        "home": home, "away": away,
        "home_id": (m.get("homeTeam") or {}).get("id"),
        "away_id": (m.get("awayTeam") or {}).get("id"),
        "venue": None,                  # 무료 티어는 구장을 안 준다 — 비운다
        "starts_utc": start,
        # 🔴 `timestamptz` 는 **순간**이다 — `.astimezone(KST)` 는 이 칸에
        #    아무 효과가 없었다(실측 2026-10-05: 라이브 52행 전부
        #    `starts_kst = starts_utc`). 🔴 그 거짓 믿음을 입구에서 끊는다 —
        #    표시 KST 는 `timefmt.kst_label`, KST 날짜 질의는
        #    `timefmt.sql_kst_day` **하나씩**이다.
        "starts_kst": timefmt.db_instant(start),
        "starts_local": None,
        "status": status,
        # 🔴 §4 `match_type` 의 재료다 — 라운드·단계를 그대로 싣는다
        "round_note": _round(m),
        "home_score": score.get("home"),
        "away_score": score.get("away"),
        "probable": {},                 # 축구에는 예고 선발이 없다
    }


def _round(m: dict) -> str | None:
    """`stage`·`matchday` 를 한 줄로. 🔴 없으면 `None` — 지어내지 않는다."""
    bits = [str(m.get("stage") or "").strip(),
            f"MD{m['matchday']}" if m.get("matchday") else ""]
    got = " ".join(b for b in bits if b)
    return got or None


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
    try:
        got = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return timefmt.aware(got, where="fdorg._when")


# ══════════════════════════════════════════════════════════════════
# 세포가 쓸 소스 목록
# ══════════════════════════════════════════════════════════════════


def _slate_fact(got: Fetched, q: Question, day: date) -> list[Fact]:
    rows = parse_schedule(got, day)
    if not rows:
        return []
    return [Fact(question_id=q.id, value=rows, hardness="hard",
                 publisher="football-data.org", source=schedule_url(), step=0)]


def sources_slate(day: date) -> list[Source]:
    """🔴 키가 없으면 **소스를 만들지 않는다** — 세포가 unknown + 사유를 남긴다.

    ⚠️ 키 없이 부르면 401 이 오고, 그것이 "오늘 경기가 없다"로 읽힌다.
       없는 것은 없다고 하는 편이 낫다(§19-b-6).
    """
    key = api_key()
    if not key:
        return []
    # 🔴 **UTC 창을 하루씩 넓혀 요청하고 KST 로 거른다.**
    #    실측 2026-10-01: 브라질 경기가 `10-02` UTC 저녁이면 KST 로는 **10-03** 이다.
    #    API 는 UTC 날짜로 거르고 우리는 KST 로 저장하므로, 창을 안 넓히면 **경계
    #    경기를 통째로 놓친다**(그날 해외축구가 0건으로 나온 이유가 이것이었다).
    #    ⚠️ 분당 10회 상한 안이다 — 창이 넓어도 요청 수는 그대로다.
    lo, hi = day - timedelta(days=1), day + timedelta(days=1)
    url = f"{BASE}?dateFrom={lo:%Y-%m-%d}&dateTo={hi:%Y-%m-%d}"
    return [Source("football-data.org 일정", "url", url=url, tier=1,
                   # 🔴 키는 **헤더**로 간다 — URL 에 실으면 카세트 파일에 남는다
                   headers={"X-Auth-Token": key},
                   parse=lambda got, q: _slate_fact(got, q, day))]
