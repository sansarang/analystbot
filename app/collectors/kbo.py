"""[KBO 1단계] KBO 공식 기록실 — 경기별 최종 점수 수집.

**이 모듈이 채점 경로다.** KBO는 statsapi가 껍데기라(sportId=32는 팀 명단만,
schedule totalGames=0) 최종 점수를 받을 다른 경로가 없다. 채점이 안 되면
픽이 맞았는지 알 수 없고, 그런 리그에 추천을 내보내는 것은 이 프로젝트의
규율 위반이다 — 그래서 다른 무엇보다 이것을 먼저 만든다.

소스: `/ws/Schedule.asmx/GetScheduleList` (form-encoded POST).
페이지의 표는 AJAX로 채워지므로 HTML을 긁으면 빈 표가 나온다.

행 형식(실측 2026-08): `['08.01(토)', '18:00', 'LG2vs2두산', ..., '잠실', '-']`
- 같은 날짜의 두 번째 행부터는 날짜 칸이 빠진다 → 직전 날짜를 이어 쓴다
- 매치업은 **`{원정}{원정점수}vs{홈점수}{홈}`** (구장으로 검증: 수원=KT, 고척=키움)
- 우천·폭염 취소는 점수가 없다 → 채점 대상이 아니다

⚠️ HTML/JSON 구조가 바뀌면 조용히 0건이 된다. `fetch_month`가 빈 결과나
파싱 실패율 급증을 감지하면 알림을 보낸다 — 조용한 실패 금지.
"""

import logging
import re
from datetime import date as _date
from datetime import datetime
from zoneinfo import ZoneInfo

from app.collectors.base import BaseAPIClient

logger = logging.getLogger(__name__)

BASE = "https://www.koreabaseball.com"
SCHEDULE_PATH = "/ws/Schedule.asmx/GetScheduleList"

# KBO 공식 표기 → Odds API 표기. 이 사전이 배당과 결과를 잇는다.
# (Odds API 실조회 2026-08-25 기준 명칭)
KBO_TEAMS = {
    "LG": "LG Twins",
    "두산": "Doosan Bears",
    "KT": "KT Wiz",
    "SSG": "SSG Landers",
    "NC": "NC Dinos",
    "키움": "Kiwoom Heroes",
    "한화": "Hanwha Eagles",
    "삼성": "Samsung Lions",
    "롯데": "Lotte Giants",
    "KIA": "Kia Tigers",
}

# 구장 → 홈팀(공식 표기). 매치업 파싱이 맞는지 교차검증하는 용도.
STADIUM_HOME = {
    "잠실": {"LG", "두산"}, "고척": {"키움"}, "수원": {"KT"}, "문학": {"SSG"},
    "창원": {"NC"}, "대전": {"한화"}, "대구": {"삼성"}, "사직": {"롯데"},
    "광주": {"KIA"},
}

# 취소·연기 사유 — 점수가 없는 정상 상태다(파싱 실패가 아니다)
CANCEL_MARKERS = ("취소", "연기", "서스펜디드", "노게임")

# ⚠️ **진행 중 경기도 점수 칸이 채워진다.** 실측(2026-08-25 18:30 경기):
#      완료: ['08.24(월)', '18:30', 'LG2vs2두산', '리뷰', '하이라이트', ...]
#      진행: ['08.25(화)', '18:30', 'NC0vs0LG',   '',     '',           ...]
#      예정: ['08.26(수)', '18:30', 'NCvsLG',     '프리뷰', '',          ...]
#    점수 유무만 보면 방금 시작한 0-0 경기를 '종료'로 오판해 채점이 오염된다.
#    **'리뷰' 링크가 붙어야 종료다** — 이것이 KBO 공식의 완료 신호다.
DONE_MARKERS = ("리뷰", "하이라이트")
PREVIEW_MARKER = "프리뷰"

_SCORED = re.compile(r"^(?P<away>\D+?)(?P<as>\d+)vs(?P<hs>\d+)(?P<home>\D+)$")
_UNSCORED = re.compile(r"^(?P<away>\D+?)vs(?P<home>\D+)$")
_DATE = re.compile(r"^(\d{2})\.(\d{2})")


class KBOClient(BaseAPIClient):
    """KBO 공식 기록실. 무료·무인증이며 세션 쿠키를 먼저 받아야 200이 온다."""

    name = "kbo"
    base_url = BASE
    timeout = 20.0
    max_concurrency = 2
    min_interval = 1.0

    def __init__(self, mock: bool = False):
        super().__init__(mock=mock)

    async def schedule_rows(self, season: int, month: int) -> list[list[str]]:
        """그 달의 일정·결과 행. 셀은 태그를 벗긴 문자열."""
        import httpx

        headers = {"User-Agent": "Mozilla/5.0",
                   "Referer": f"{BASE}/Schedule/Schedule.aspx",
                   "X-Requested-With": "XMLHttpRequest"}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as c:
            await c.get(f"{BASE}/Schedule/Schedule.aspx", headers=headers)
            r = await c.post(
                BASE + SCHEDULE_PATH,
                data={"leId": "1", "srIdList": "0,9,6", "seasonId": str(season),
                      "gameMonth": f"{month:02d}", "teamId": ""},
                headers=headers,
            )
        r.raise_for_status()
        payload = r.json()
        out = []
        for row in payload.get("rows") or []:
            cells = [re.sub(r"<[^>]+>", "", (c or {}).get("Text", "")).strip()
                     for c in (row.get("row") or [])]
            if cells:
                out.append(cells)
        return out


def parse_matchup(text: str) -> dict | None:
    """`한화4vs7KT` → {away, away_score, home, home_score}. 점수 없으면 None 점수."""
    t = (text or "").replace(" ", "")
    m = _SCORED.match(t)
    if m:
        return {"away": m.group("away"), "away_score": int(m.group("as")),
                "home": m.group("home"), "home_score": int(m.group("hs"))}
    m = _UNSCORED.match(t)
    if m:
        return {"away": m.group("away"), "away_score": None,
                "home": m.group("home"), "home_score": None}
    return None


def _has_started(date_s: str, time_s: str) -> bool:
    """그 경기가 이미 시작했는가 (KST). 못 읽으면 **시작한 것으로 보지 않는다.**

    ⚠️ 모를 때 `False` 를 주는 쪽이 안전하다. `True` 로 기울면 시작 전 경기가
       `live` 로 굳어 판정 대상에서 빠진다 — 그게 오늘 카드를 0장으로 만든
       고장이다. 반대로 기울면 이미 끝난 경기가 잠깐 `scheduled` 로 남을 뿐이고,
       그건 `done` 마커가 곧 `final` 로 덮는다.
    """
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _Z

    if not date_s or not time_s:
        return False
    try:
        kst = _Z("Asia/Seoul")
        h, m = time_s.strip().split(":")
        start = _dt.fromisoformat(date_s).replace(
            hour=int(h), minute=int(m), tzinfo=kst)
    except (ValueError, TypeError):
        return False
    return _dt.now(kst) >= start


def parse_rows(rows: list[list[str]], season: int) -> tuple[list[dict], int]:
    """행 목록 → 경기 dict 목록. 반환: (경기들, 파싱 실패 수).

    날짜 칸은 그 날의 첫 경기에만 있으므로 직전 날짜를 이어 쓴다.
    """
    games: list[dict] = []
    failed = 0
    cur_date: str | None = None
    for cells in rows:
        idx = 0
        m = _DATE.match(cells[0]) if cells else None
        if m:
            cur_date = f"{season}-{m.group(1)}-{m.group(2)}"
            idx = 1
        if cur_date is None or len(cells) < idx + 2:
            failed += 1
            continue
        time_s, matchup = cells[idx], cells[idx + 1]
        parsed = parse_matchup(matchup)
        if parsed is None:
            failed += 1
            logger.debug("[kbo] 매치업 파싱 실패: %r", matchup)
            continue
        tail = cells[idx + 2:]
        stadium = next((c for c in tail if c in STADIUM_HOME), "")
        note = tail[-1] if tail else ""
        cancelled = any(k in note for k in CANCEL_MARKERS)
        done = any(any(m in c for m in DONE_MARKERS) for c in tail)
        # 구장으로 홈팀 교차검증 — 파싱 방향이 뒤집히면 여기서 드러난다
        if stadium and parsed["home"] not in STADIUM_HOME.get(stadium, set()):
            logger.warning("[kbo] 홈팀 불일치 %s: 파싱=%s 구장=%s",
                           cur_date, parsed["home"], stadium)
        games.append({
            "date": cur_date, "time": time_s, "stadium": stadium,
            "away": KBO_TEAMS.get(parsed["away"], parsed["away"]),
            "home": KBO_TEAMS.get(parsed["home"], parsed["home"]),
            "away_kr": parsed["away"], "home_kr": parsed["home"],
            "away_score": parsed["away_score"], "home_score": parsed["home_score"],
            # 점수가 있어도 '리뷰'가 없으면 진행 중이다 — 채점 대상이 아니다
            # 🔴 [P0 2026-09-03] **시작 전에는 점수가 있어도 `live` 가 아니다.**
            #    공식 페이지가 경기 전 경기에 `0-0` 플레이스홀더를 싣는다.
            #    그걸 "점수가 있다"로 읽어 4경기가 통째로 `live` 가 됐고,
            #    `upsert_schedule` 의 예정 카운트가 0 이 되어 파이프라인이
            #    "경기 적재 0/1건"으로 죽었다 → **KBO 5경기 판정 0건, 카드 0장.**
            #    실측 17:52 KST: LG@두산·롯데@삼성·한화@KT·SSG@키움 전부
            #    `status=live score=0-0` (시작 18:30, 즉 38분 뒤).
            #    시작 시각이 미래면 무조건 `scheduled` 다 — 점수가 뭐든.
            "status": ("cancelled" if cancelled
                       else "final" if (done and parsed["home_score"] is not None)
                       else "live" if (parsed["home_score"] is not None
                                       and _has_started(cur_date, time_s))
                       else "scheduled"),
            "ext_id": f"kbo:{cur_date}:{time_s}:{parsed['away']}:{parsed['home']}",
        })
    return games, failed


async def fetch_month(season: int, month: int,
                      client: KBOClient | None = None) -> list[dict]:
    """그 달 경기 목록. 구조가 바뀌어 조용히 비면 알림을 보낸다."""

    from app.collectors.base import freesource_mocked

    if freesource_mocked(client):        # [P5-1] 무인증 소스 — 목 모드
        return []
    client = client or KBOClient()
    rows = await client.schedule_rows(season, month)
    games, failed = parse_rows(rows, season)
    total = len(rows) or 1
    if not games or failed / total > 0.30:
        from app.alerts import StageResult, stage_failed

        await stage_failed(StageResult(
            name="KBO 일정 파싱", ok=len(games), total=len(rows) or 1,
            cause="parse",
            detail=f"{season}-{month:02d} 행 {len(rows)}건 중 실패 {failed}건",
            impact="KBO 채점이 멈춥니다 — 공식 사이트 구조 변경 가능성"))
    logger.info("[kbo] %d-%02d 일정 %d경기 (행 %d · 파싱실패 %d)",
                season, month, len(games), len(rows), failed)
    return games


async def fetch_finals(days: int = 7, end: _date | None = None,
                       client: KBOClient | None = None) -> list[dict]:
    """최근 `days`일의 **종료 경기**. 종료 점수 적재가 쓰는 진입점.

    ⚠️ 기본 종료일은 **KST 오늘**이다. `date.today()`는 서버 로컬 날짜라
       Railway(UTC)에서는 KST 09:00 이전에 하루 전 날짜가 나온다 — KBO는
       한국 리그이므로 서버가 어디 있든 KST 날짜여야 한다.
    """
    end = end or datetime.now(ZoneInfo("Asia/Seoul")).date()
    start = _date.fromordinal(end.toordinal() - days)
    months = {(d.year, d.month) for d in (start, end)}
    out: list[dict] = []
    client = client or KBOClient()
    for season, month in sorted(months):
        for g in await fetch_month(season, month, client):
            if g["status"] != "final":
                continue
            try:
                d = _date.fromisoformat(g["date"])
            except ValueError:
                continue
            if start <= d <= end:
                out.append(g)
    return out


async def upsert_games(pool, games: list[dict]) -> int:
    """KBO 경기를 games 테이블에 반영. 반환: 적재·갱신 건수.

    `sport='kbo'`로 넣어 MLB·축구 경로와 섞이지 않게 한다.
    시간대: KBO 일정 시각은 KST다 — DB는 UTC 저장 규약이므로 변환해 넣는다.
    """
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    kst = ZoneInfo("Asia/Seoul")
    n = 0
    for g in games:
        try:
            hh, mm = (g.get("time") or "18:30").split(":")
            starts = datetime.fromisoformat(g["date"]).replace(
                hour=int(hh), minute=int(mm), tzinfo=kst)
        except (ValueError, AttributeError):
            continue
        # [§8-37] ext_id가 아니라 **경기 자체**로 찾아 갱신한다.
        #   같은 경기가 소스마다 다른 ext_id를 받아 두 행으로 갈라지면,
        #   예측이 붙은 행은 영원히 미채점으로 남는다(실측 2026-08-27).
        from app.collectors.game_match import apply_result

        await apply_result(
            pool, sport="kbo", league="KBO", ext_id=g["ext_id"],
            starts_at=starts.astimezone(UTC), home=g["home"], away=g["away"],
            status=g["status"], home_score=g["home_score"],
            away_score=g["away_score"])
        n += 1
    return n


async def upsert_final_scores(pool, date: str, days: int = 7,
                              client: KBOClient | None = None) -> int:
    """종료 점수 적재 — 최근 종료 경기의 점수를 games에 반영. 반환: final 건수.

    MLB의 `mlb.upsert_final_scores`와 같은 계약이라 ingest_finals가 동일하게 부른다.
    """
    end = _date.fromisoformat(date)
    finals = await fetch_finals(days=days, end=end, client=client)
    await upsert_games(pool, finals)
    return len(finals)


async def upsert_schedule(pool, date: str, client: KBOClient | None = None) -> dict:
    """[Odds 이관] 그날 KBO 일정을 **공식 사이트에서** games에 적재한다.

    🔴 종전에는 Odds API `/scores`가 KBO 일정의 유일한 소스였다. KBO는 배당을
       판정에 쓰지 않는데(#38·#39) 크레딧이 마르면 **응답 전체가 죽었다**
       (실측 2026-08-27: "크레딧 소진" 한 줄만 나갔다).
       일정·점수는 공식 소스에 다 있고 파서도 이미 있었다 — 배선만 없었다.

    반환: {"scheduled": n, "final": n, "total": n} — Odds 경로와 같은 계약.
    """
    d = _date.fromisoformat(date)
    games = [g for g in await fetch_month(d.year, d.month, client)
             if g.get("date") == date]
    await upsert_games(pool, games)
    counts = {"scheduled": 0, "final": 0, "total": len(games)}
    for g in games:
        if g["status"] == "final":
            counts["final"] += 1
        elif g["status"] == "scheduled":
            counts["scheduled"] += 1
    logger.info("[kbo] %s 일정 %d경기 적재 (예정 %d / 종료 %d) — 공식 소스",
                date, counts["total"], counts["scheduled"], counts["final"])
    return counts
