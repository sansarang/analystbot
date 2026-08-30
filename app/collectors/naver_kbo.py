"""[§8-19] 네이버 스포츠 KBO — **LLM 0회**로 경기력 재료를 모은다.

왜 만드나 (2026-08-26 실측):
  KBO 5경기 딥서치에서 3경기가 "재료 없음"으로 실패했다. Perplexity를 한 번 부르고
  같은 프롬프트로 한 번 더 부르고 포기하는 구조였다 — 그건 딥서치가 아니라 API 호출이다.
  네이버 스포츠 preview API 하나가 **선발·구종·최근폼·순위·상대전적**을 한 번에 준다.
  무료이고, LLM을 쓰지 않으며, 실패해도 쿼터를 소모하지 않는다.

수집 우선순위 (§8-19 소스 계약):
  선발 이름·구종·시즌 성적 · 최근 폼 · 순위 · 상대전적  → **여기가 1순위**
  결장 상세·감독 코멘트·동기·여론                      → 딥서치·Grok (빈칸 전용)

⚠️ 비공개 API다. 구조가 바뀌면 조용히 0건이 된다 — 필드 검증 후 실패를 알린다.
⚠️ 팀 표기가 축약형이다("LG"·"NC"). games 테이블은 Odds 표기를 쓰므로 매핑이 필요하다.
"""

import logging
import re

logger = logging.getLogger(__name__)

BASE = "https://api-gw.sports.naver.com"
SCHEDULE = "/schedule/games"
CACHE_TTL = 3 * 3600          # 타순이 실린 스냅샷 — 확정 뒤에는 잘 안 바뀐다
# 타순이 아직 없는 스냅샷은 **오래 들고 있으면 안 된다.** KBO 타순 공시는
# 경기 1시간 전(18:30 → 17:30)인데, 낮 프리페치(14:00)가 채운 3시간 캐시를
# 그대로 읽으면 17:00까지 "타순 없음"이 고정된다.
# 실측 2026-08-29 17:22: `라인업 0/4경기 — 발표 시각이 지났는데 0건`.
LINEUP_PENDING_TTL = 10 * 60

HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://m.sports.naver.com/"}

# 네이버 축약 표기 → Odds API 팀명 (games 테이블과 잇는 키)
TEAM_TO_ODDS = {
    "LG": "LG Twins", "두산": "Doosan Bears", "KT": "KT Wiz", "SSG": "SSG Landers",
    "NC": "NC Dinos", "키움": "Kiwoom Heroes", "한화": "Hanwha Eagles",
    "삼성": "Samsung Lions", "롯데": "Lotte Giants", "KIA": "Kia Tigers",
}

# 응답에 반드시 있어야 하는 키 — 없으면 구조가 바뀐 것이다
REQUIRED_PREVIEW = ("homeStarter", "awayStarter", "homeStandings", "awayStandings")


class NaverKBOClient:
    """비공개 JSON API. 무인증·무료."""

    timeout = 15.0

    def __init__(self, mock: bool = False):
        self.mock = mock

    async def _get(self, path: str, params: dict | None = None) -> dict:
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as c:
            r = await c.get(BASE + path, headers=HEADERS, params=params)
        r.raise_for_status()
        return r.json()

    async def games(self, date: str) -> list[dict]:
        """그 날짜 KBO 경기 목록 (gameId 포함)."""
        d = await self._get(SCHEDULE, {
            "fields": "basic,superCategoryId,category", "upperCategoryId": "kbaseball",
            "fromDate": date, "toDate": date, "size": "30"})
        return ((d.get("result") or {}).get("games")) or []

    async def preview(self, game_id: str) -> dict:
        d = await self._get(f"{SCHEDULE}/{game_id}/preview")
        return ((d.get("result") or {}).get("previewData")) or {}


def _num(v):
    """'120.1'(이닝 표기: 120과 1/3) · '4.14' → float. 못 바꾸면 None."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    # 야구 이닝 표기: 120.1 = 120⅓, 120.2 = 120⅔
    m = re.match(r"^(\d+)\.([12])$", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 3
    try:
        return float(s)
    except ValueError:
        return None


def form_from_previous(games: list[dict], team_code: str) -> str | None:
    """직전 경기 목록 → 최신순 W/L 문자열.

    ⚠️ `result` 필드는 **그 팀 기준 승패**가 아니라 경기 결과 표기다.
       홈/원정을 보고 우리 팀 기준으로 뒤집어야 한다 — 안 그러면 폼이 반대로 들어간다.
    ⚠️ **그 팀이 참가하지 않은 경기는 건너뛴다.** 홈코드만 비교하고 아니면 원정으로
       치면, 목록에 남의 경기가 섞였을 때 조용히 반대 결과를 센다(테스트로 잡은 버그).
    """
    out = []
    tc = str(team_code)
    for g in games or []:
        hs, as_ = g.get("hScore"), g.get("aScore")
        if hs is None or as_ is None:
            continue
        h, a = str(g.get("hCode")), str(g.get("aCode"))
        if tc not in (h, a):
            continue                      # 우리 팀 경기가 아니다
        mine, theirs = (hs, as_) if tc == h else (as_, hs)
        out.append("W" if mine > theirs else "L" if mine < theirs else "D")
    return "".join(out[:10]) or None


def lineup_text(rows) -> str:
    """Go crawler `lineupText` 와 같은 계약. 선발투수는 타순이 아니다."""
    names = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if r.get("positionName") == "선발투수":
            continue
        name = (r.get("playerName") or "").strip()
        if not name:
            continue
        pos = (r.get("positionName") or "").strip()
        names.append(f"{name}({pos})" if pos else name)
    return "-".join(names)


def status_from_naver(info: str | None) -> str:
    """네이버 statusInfo → games.status.

    실측 2026-08-29: 시작 후면 '경기중'이 아니라 '1회초'처럼 이닝 표기다.
    기록실 0-0 만으로 live 를 주면 시작 전 경기가 분석에서 빠진다(1447).
    """
    s = info or ""
    if "취소" in s:
        return "cancelled"
    if "종료" in s:
        return "final"
    if "경기중" in s or "회초" in s or "회말" in s:
        return "live"
    return "scheduled"


def parse_preview(pv: dict) -> dict | None:
    """previewData → 우리 계약의 research 조각. 구조가 어긋나면 None."""
    if not pv or any(k not in pv for k in REQUIRED_PREVIEW):
        logger.error("[naver_kbo] preview 구조 불일치 — 키 %s", sorted(pv or {})[:12])
        return None

    info = pv.get("gameInfo") or {}
    out: dict = {"stadium": info.get("stadium"), "source": "네이버 스포츠"}

    for side, st_key, sd_key, prev_key, code_key in (
        ("home", "homeStarter", "homeStandings", "homeTeamPreviousGames", "hCode"),
        ("away", "awayStarter", "awayStandings", "awayTeamPreviousGames", "aCode"),
    ):
        st = pv.get(st_key) or {}
        pi, cs = st.get("playerInfo") or {}, st.get("currentSeasonStats") or {}
        pitcher: dict = {}
        if pi.get("name"):
            pitcher["name"] = pi["name"]
        hit_type = str(pi.get("hitType") or "")
        if hit_type.startswith("좌"):
            pitcher["throws"] = "L"
        elif hit_type.startswith("우"):
            pitcher["throws"] = "R"
        for src, dst in (("era", "era_season"), ("whip", "whip")):
            v = _num(cs.get(src))
            if v is not None:
                pitcher[dst] = v
        ip = _num(cs.get("inn"))
        gc = _num(cs.get("gameCount"))
        if ip and gc:
            pitcher["ip_avg_recent"] = round(ip / gc, 2)   # λ의 선발 담당 이닝 입력
        kinds = [f"{k.get('type')} {k.get('speed')}km"
                 for k in (st.get("currentPitKindStats") or []) if k.get("type")]
        if kinds:
            pitcher["pitch_mix"] = " / ".join(kinds[:4])
        if pitcher:
            out[f"{side}_pitcher"] = pitcher

        sd = pv.get(sd_key) or {}
        team_stats: dict = {}
        for src, dst in (("hra", "avg"), ("era", "team_era")):
            v = _num(sd.get(src))
            if v is not None:
                team_stats[dst] = v
        if sd.get("rank"):
            team_stats["rank"] = sd["rank"]
        for k in ("w", "l", "d"):
            if sd.get(k) is not None:
                team_stats[k] = sd[k]
        if team_stats:
            out[f"{side}_team"] = team_stats

        form = form_from_previous(pv.get(prev_key), info.get(code_key))
        if form:
            out[f"{side}_form"] = form

    vs = pv.get("seasonVsResult") or {}
    if vs:
        out["h2h"] = {"home_w": vs.get("hw"), "home_l": vs.get("hl"),
                      "draw": vs.get("hd")}
    # 타순 — 실측 2026-08-29: preview JSON에 homeTeamLineUp.fullLineUp 이 있는데
    #   파이썬 파서가 선발·순위만 읽고 타순을 버려 저녁까지 수집 0이었다.
    #   HTML이 아니라 같은 JSON API. Go 크롤러와 필드를 맞춘다.
    for side, key in (("home", "homeTeamLineUp"), ("away", "awayTeamLineUp")):
        order = lineup_text((pv.get(key) or {}).get("fullLineUp"))
        if order:
            out[f"lineup_{side}"] = order
    return out


# KBO 정규시즌 경기 수 — 잔여 경기 계산의 분모.
# ⚠️ 시즌 제도가 바뀌면 여기를 고쳐야 한다. 틀리면 '잔여 경기'가 조용히 틀어진다.
KBO_SEASON_GAMES = 144


def build_standings(table: dict) -> dict[str, dict]:
    """[§8-34] 하루치 프리뷰 전체 → 팀별 순위표. 카드 ④칸("무게")의 재료.

    **추가 HTTP가 없다.** 그날 5경기 프리뷰가 10팀 순위를 모두 담고 있으므로
    캐시된 값에서 조립한다. 네이버·KBO의 순위 전용 엔드포인트는 403이라
    쓸 수 없었다(2026-08-27 실측).

    게임차는 직접 계산한다 — 응답에 없다.
        GB = ((선두승 - 팀승) + (팀패 - 선두패)) / 2

    ⚠️ 순위는 응답값을 그대로 쓴다. 승률로 다시 매기면 무승부 처리 규칙 차이로
       공식 순위와 어긋날 수 있다 — 있는 값을 재계산하지 않는다.
    """
    rows: dict[str, dict] = {}
    for key, parsed in (table or {}).items():
        if "@" not in key or not isinstance(parsed, dict):
            continue
        away, home = key.split("@", 1)
        for side, team in (("home", home), ("away", away)):
            t = parsed.get(f"{side}_team") or {}
            w, l, d = t.get("w"), t.get("l"), t.get("d")
            if w is None or l is None:
                continue
            rows[team] = {"rank": t.get("rank"), "w": w, "l": l, "d": d or 0}
    if not rows:
        return {}
    # ⚠️ 게임차는 **1위 팀이 표에 있을 때만** 낸다.
    #   부분 표에서 가장 높은 순위를 선두로 삼으면 조용히 틀린 값이 나온다
    #   (테스트가 실제로 잡았다: 4위·6위만 있는 표에서 4위 게임차가 0.0).
    #   못 구하는 값은 만들지 않는다 — 빈칸이 틀린 값보다 낫다.
    lead = next((r for r in rows.values() if r.get("rank") == 1), None)
    # [§9 카드 ④칸] **컷(가을야구 진출선) 대비 게임차**도 낸다.
    #   선두 게임차만으로는 경쟁권을 판정할 수 없다 — 선두와 16게임 차여도
    #   5위와 1게임 차면 그 팀은 명백히 경쟁 중이다.
    from app.config import get_settings

    cut_rank = get_settings().contention_cut_rank
    cut = next((r for r in rows.values() if r.get("rank") == cut_rank), None)
    for r in rows.values():
        if lead is not None:
            r["games_behind"] = round(
                ((lead["w"] - r["w"]) + (r["l"] - lead["l"])) / 2, 1)
        if cut is not None:
            # 컷보다 위면 음수가 된다(= 여유). 그대로 둔다 — 부호가 정보다.
            r["games_behind_cut"] = round(
                ((cut["w"] - r["w"]) + (r["l"] - cut["l"])) / 2, 1)
        played = r["w"] + r["l"] + r["d"]
        r["played"] = played
        r["remaining"] = max(0, KBO_SEASON_GAMES - played)
    return rows


def merge_standings_into_research(research: dict, jg: dict, table: dict) -> list[str]:
    """순위·게임차·잔여를 research에 얹는다.

    ⚠️ '총력전'·'정리 모드' 같은 **해석을 넣지 않는다** — 2단 해석봇의 일이다.
    """
    filled = []
    for side in ("home", "away"):
        row = (table or {}).get(jg.get(side) or "")
        if not row:
            continue
        blk = research.setdefault(f"{side}_standing", {})
        for k, v in row.items():
            if v is not None and blk.get(k) != v:
                blk[k] = v
                filled.append(f"{side}_standing.{k}")
    return filled


def merge_into_research(research: dict, jg: dict, data: dict) -> list[str]:
    """[§8-19] 크롤링 결과를 research에 얹는다. 반환: 채운 필드 목록.

    ⚠️ **크롤링이 딥서치를 이긴다.** 정식 기록·구단 발표가 LLM 산문보다 정확하다
       (규율: LLM 수치는 API와 교차검증, 충돌 시 API 승).
       단, 여기 없는 것(결장 상세·감독 코멘트·여론)은 딥서치가 채운다.
    """
    filled: list[str] = []
    if not data:
        return filled
    for side in ("home", "away"):
        p = data.get(f"{side}_pitcher")
        if p:
            blk = research.setdefault(f"{side}_pitcher", {})
            for k, v in p.items():
                if blk.get(k) != v:
                    blk[k] = v
                    filled.append(f"{side}_pitcher.{k}")
        form = data.get(f"{side}_form")
        if form:
            blk = research.setdefault(f"{side}_recent_form", {})
            if blk.get("form") != form:
                blk["form"] = form
                filled.append(f"{side}_recent_form.form")
        # [§9 게이트③] 공식 기록실과 **같은 필드**에 넣는다. 그래야 두 소스가
        #   같은 값을 봤는지(교차) 다른 값을 봤는지(모순) 대조된다.
        #   ⚠️ 값이 이미 같아도 **채운 목록에 넣는다.** 빼면 각인이 안 되고,
        #      각인이 없으면 "두 소스가 일치했다"는 사실이 기록되지 않아
        #      교차 라벨이 영원히 0%가 된다(실측 2026-08-27: 교차 0/405).
        t = data.get(f"{side}_team")
        if t:
            if t.get("team_era") is not None:
                research.setdefault(f"{side}_bullpen", {}).setdefault(
                    "era", t["team_era"])
                filled.append(f"{side}_bullpen.era")
            if t.get("avg") is not None:
                research.setdefault(f"{side}_offense", {}).setdefault(
                    "avg", t["avg"])
                filled.append(f"{side}_offense.avg")
    if data.get("stadium"):
        research.setdefault("park", f"{data['stadium']} 구장")
    for side in ("home", "away"):
        order = (data.get(f"lineup_{side}") or "").strip(" -")
        if not order:
            continue
        parts = [p for p in order.split("-") if p.strip()]
        if len(parts) < 9:
            continue
        blk = research.setdefault(f"{side}_lineup", {})
        if blk.get("order") != order:
            blk["order"] = order
            blk["source"] = "네이버"
            filled.append(f"{side}_lineup.order")
    return filled


def _key(date: str) -> str:
    return f"naver_kbo:{date}"


async def refresh(redis, date: str, client: NaverKBOClient | None = None) -> dict:
    """그 날짜 전 경기 preview를 수집해 캐시. 반환 요약.

    ⚠️ 조용한 0건을 막는다 — 경기가 있는데 파싱이 전부 실패하면 알린다.
    """
    import json

    client = client or NaverKBOClient()
    games = await client.games(date)
    playable = [g for g in games if g.get("homeTeamName") and g.get("awayTeamName")]
    out: dict[str, dict] = {}
    failed = 0
    for g in playable:
        gid = g.get("gameId")
        if not gid:
            continue
        try:
            parsed = parse_preview(await client.preview(gid))
        except Exception as exc:                       # 한 경기 실패가 전체를 막지 않는다
            logger.warning("[naver_kbo] preview 실패 %s: %s", gid, exc)
            parsed = None
        if parsed is None:
            failed += 1
            continue
        home = TEAM_TO_ODDS.get(g.get("homeTeamName"))
        away = TEAM_TO_ODDS.get(g.get("awayTeamName"))
        if not home or not away:
            logger.warning("[naver_kbo] 매핑 없는 팀: %r vs %r",
                           g.get("awayTeamName"), g.get("homeTeamName"))
            continue
        out[f"{away}@{home}"] = parsed
        st = status_from_naver(g.get("statusInfo"))
        parsed["naver_status"] = g.get("statusInfo") or ""
        parsed["naver_status_mapped"] = st
        n_lu = sum(1 for s in ("home", "away") if parsed.get(f"lineup_{s}"))
        logger.info("[naver_kbo] %s %s@%s status=%s starters=%s/%s lineup_sides=%d",
                    date, away, home, parsed["naver_status"] or "-",
                    (parsed.get("away_pitcher") or {}).get("name") or "-",
                    (parsed.get("home_pitcher") or {}).get("name") or "-",
                    n_lu)
    if playable and not out:
        from app.alerts import StageResult, stage_failed

        await stage_failed(StageResult(
            name="네이버 KBO 수집", ok=0, total=len(playable), cause="parse",
            detail=f"{date} 경기 {len(playable)}건 중 파싱 실패 {failed}건",
            impact="선발·최근폼을 딥서치에만 의존하게 됩니다"))
    ttl = CACHE_TTL if not lacks_lineups(out) else LINEUP_PENDING_TTL
    await redis.set(_key(date), json.dumps(out, ensure_ascii=False), ex=ttl)
    logger.info("[naver_kbo] %s — %d경기 수집 (실패 %d) · 타순 %s · TTL %d분",
                date, len(out), failed,
                "미확정" if lacks_lineups(out) else "확정", ttl // 60)
    return {"games": len(out), "failed": failed}


def lacks_lineups(snap: dict) -> bool:
    """이 스냅샷에 **양 팀 타순이 다 실린 경기가 하나도 없는가.**

    하나라도 있으면 공시가 시작된 것이므로 확정 캐시로 본다. 한 경기만 늦게
    올라오는 경우는 다음 폴링이 잡는다 — 여기서 전부를 요구하면 마지막
    한 경기 때문에 이미 받은 타순까지 10분마다 다시 받는다.
    """
    if not snap:
        return True
    return not any(
        (g.get("lineup_home") or "").strip() and (g.get("lineup_away") or "").strip()
        for g in snap.values() if isinstance(g, dict)
    )


async def load(redis, date: str) -> dict:
    """캐시에서 {"원정@홈": research조각}. 없으면 빈 dict — 크래시 금지."""
    import json

    raw = await redis.get(_key(date))
    return json.loads(raw) if raw else {}
