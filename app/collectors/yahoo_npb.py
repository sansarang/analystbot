"""[§8-20] Yahoo!スポーツ NPB — **LLM 0회**로 선발·불펜·컨디션을 모은다.

왜 만드나 (2026-08-26 실측):
  NPB 6경기 전부 `λ 미확보 입력: 핵심 지표(타선·선발) 전무`로 나왔다.
  지표 소스가 없어 `game_distribution`이 None을 반환했고, 확률이 판정 단독이었다.
  그 결과 지바 롯데 70%처럼 근거를 검증할 수 없는 값이 나왔다.

Yahoo!スポーツ 경기 페이지가 주는 것 (실조회 2026-08-26):
  선발 이름·투구손·방어율·컨디션(好調/普通/絶不調)
  불펜 명단 전원의 방어율·컨디션        ← 딥서치가 절대 못 주는 재료
  일정 목록에서 **(予)예상 / (先)확정** 구분

⚠️ HTML 파싱이다. 구조가 바뀌면 조용히 0건이 된다 — 헤더를 검증하고 실패를 알린다.
⚠️ 일본어 팀 약칭을 Odds API 표기로 매핑해야 games 테이블과 이어진다.
"""

import logging
import re

logger = logging.getLogger(__name__)

BASE = "https://baseball.yahoo.co.jp"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36"}
CACHE_TTL = 3 * 3600      # 선발·라인업은 경기 임박 시 바뀐다

# Yahoo 약칭 → Odds API 팀명 (실조회 2026-08-26 기준)
TEAM_TO_ODDS = {
    "ヤクルト": "Tokyo Yakult Swallows", "巨人": "Yomiuri Giants",
    "中日": "Chunichi Dragons", "阪神": "Hanshin Tigers",
    "広島": "Hiroshima Toyo Carp", "DeNA": "Yokohama DeNA BayStars",
    "西武": "Saitama Seibu Lions", "日本ハム": "Hokkaido Nippon-Ham Fighters",
    "ロッテ": "Chiba Lotte Marines", "ソフトバンク": "Fukuoka SoftBank Hawks",
    "オリックス": "Orix Buffaloes", "楽天": "Tohoku Rakuten Golden Eagles",
}

# 선발 표의 기대 헤더 — 어긋나면 파싱 결과를 믿지 않는다
STARTER_HEADER = ("投手", "位置", "選手名", "投", "防御率")
# 컨디션 표기(그 팀이 매기는 정성 평가) → 우리 라벨. 확률 계수로는 쓰지 않는다.
CONDITION_KR = {"絶好調": "매우 좋음", "好調": "좋음", "普通": "보통",
                "不調": "나쁨", "絶不調": "매우 나쁨"}

# [§8-20] 표본 가드. 실측(2026-08-26): 齋藤 響介가 **1등판 ERA 189.00**이었다.
#   0이닝대 대량 실점이면 산술적으로 이런 값이 나온다 — 데이터는 맞지만
#   λ의 선발 억제 계수에 넣으면 그 경기가 통째로 망가진다.
#   → 등판 수가 이 값 미만이면 `era_season`을 **버린다**(리그 평균으로 대체하지도 않는다.
#     없는 것을 있는 척하지 않는다 — 판정이 "선발 정보 없음"으로 다루게 한다).
MIN_STARTER_APPEARANCES = 3
MAX_CREDIBLE_ERA = 15.0

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _text(html: str) -> str:
    return _WS.sub(" ", _TAG.sub(" ", html)).strip()


def _cells(row: str) -> list[str]:
    return [_text(x) for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]


def _num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _throws(v: str | None) -> str | None:
    """'右'·'右左'(투타) → R/L. 첫 글자가 투구손이다."""
    s = (v or "").strip()
    if s.startswith("右"):
        return "R"
    if s.startswith("左"):
        return "L"
    return None


class YahooNPBClient:
    timeout = 20.0

    def __init__(self, mock: bool = False):
        self.mock = mock

    async def _get(self, path: str) -> str:
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as c:
            r = await c.get(BASE + path, headers=HEADERS)
        r.raise_for_status()
        return r.text

    async def schedule(self, date: str) -> str:
        return await self._get(f"/npb/schedule/?date={date}")

    async def game(self, game_id: str) -> str:
        return await self._get(f"/npb/game/{game_id}/top")


def parse_schedule(html: str) -> list[dict]:
    """일정 HTML → [{game_id, home, away, starters_confirmed}].

    ⚠️ 일정 페이지에는 **어제·내일 경기도 섞여 있다.** 종료(試合終了)·미정(試合前)
       블록을 걸러내고, 팀명이 실제로 잡히는 행만 남긴다.
    ⚠️ `(予)`는 예상 선발, `(先)`는 확정이다 — 예상을 확정으로 취급하면
       '최종 픽' 자격이 잘못 부여된다(라인업 2단계 규율).
    """
    out, seen = [], set()
    for href, gid, inner in re.findall(
            r'href="(/npb/game/(\d+)/[a-z]*)"[^>]*>(.*?)</a>', html, re.S):
        if gid in seen:
            continue
        seen.add(gid)
        txt = _text(inner)
        teams = [t for t in TEAM_TO_ODDS if t in txt]
        if len(teams) != 2:
            continue                      # 종료·미정 블록 또는 다른 리그
        # 등장 순서: 홈이 먼저 (실조회: "神宮 ヤクルト 巨人 18:00")
        teams.sort(key=txt.index)
        out.append({
            "game_id": gid,
            "home": TEAM_TO_ODDS[teams[0]], "away": TEAM_TO_ODDS[teams[1]],
            "home_kr": teams[0], "away_kr": teams[1],
            # (先) = 확정 발표 / (予) = 예상
            "starters_confirmed": "(先)" in txt,
        })
    return out


# 경기 **전** 페이지(予告先発 블록)의 표 헤더 — 실조회 2026-08-26
PREGAME_NAME_HEADER = ("背番号", "投", "選手名")
PREGAME_STAT_HEADER = ("", "防御率", "登板", "勝利", "敗戦")


def _parse_pregame(html: str) -> list[dict]:
    """경기 **전** 페이지 — `予告先発` 블록. 시즌 ERA + **상대전적 ERA**를 준다.

    상대전적 ERA(`対戦`)는 딥서치가 절대 못 주는 재료다. 같은 상대에게 강한지
    약한지가 그 경기의 실제 기대 실점에 가깝다.
    """
    i = html.find("予告先発")
    if i < 0:
        return []
    seg = html[i:i + 12000]
    tables = [
        [_cells(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", tb, re.S)]
        for tb in re.findall(r"<table[^>]*>(.*?)</table>", seg, re.S)
    ]
    out: list[dict] = []
    pending: dict | None = None
    for rows in tables:
        rows = [r for r in rows if r]
        if not rows:
            continue
        head = tuple(rows[0])
        if head[:3] == PREGAME_NAME_HEADER and len(rows) > 1 and len(rows[1]) >= 3:
            pending = {"name": rows[1][2], "throws": _throws(rows[1][1])}
        elif head[:2] == PREGAME_STAT_HEADER[:2] and pending is not None:
            for r in rows[1:]:
                if len(r) < 2:
                    continue
                era = _num(r[1])
                if era is None:
                    continue
                if r[0] == "今季":
                    pending["era_season"] = era
                    pending["appearances"] = int(_num(r[2]) or 0) if len(r) > 2 else 0
                elif r[0] == "対戦":
                    pending["era_vs_opponent"] = era     # 상대전적 방어율
            out.append(pending)
            pending = None
    return out


# Yahoo /top 打順 약어. 한글 1루수·3루수는 숫자라 크롤러 게이트가 이름을 버린다.
# 실측 2026-08-28: 종료 경기 선발 표는 한 글자(遊·指·投). 교체 행은 이 표에 없다.
_POS_JP = ("遊", "三", "左", "一", "右", "捕", "二", "投", "中", "指")


def score_card_html(html: str) -> str:
    """일정 페이지의 **그날 카드**만. 주간 표에 어제·내일이 섞인다.

    실측 2026-08-28: `id="gm_card"`가 요청 날짜 6경기이고, 그 아래 month 표에
    다른 날 링크가 수십 개다. 날짜를 요청 파라미터로 덮어씌우면 8/26 경기가
    8/28로 적재된다.
    """
    i = html.find('id="gm_card"')
    if i < 0:
        return html
    j = html.find('id="', i + 12)
    return html[i:j] if j > 0 else html[i:]


def parse_batting_orders(html: str) -> dict[str, list[str]]:
    """Yahoo `/top`의 `打順` 표 → 선발 9명. 없으면 빈 목록.

    실측 2026-08-28:
      - 경기 **전**(시작 7시간 전): 표 없음. 予告先発(투수)만.
      - 종료 후: 팀당 1~9번 9행. 대타 없음.
      - 첫 표가 홈(神宮 ヤクルト). 두 번째가 원정.
      - `/stats`·npb.jp 「最新のオーダー」는 교체·막판 타순이라 쓰지 않는다.
    9명이 아니면 그 쪽을 버린다 — 불완전 타순으로 평소를 만들지 않는다.
    """
    found: list[list[str]] = []
    for tb in re.findall(r"<table[^>]*>(.*?)</table>", html, re.S):
        rows = [r for r in (_cells(tr) for tr in
                            re.findall(r"<tr[^>]*>(.*?)</tr>", tb, re.S)) if r]
        if not rows or rows[0][:1] != ["打順"] or "選手名" not in rows[0]:
            continue
        head = rows[0]
        name_i, pos_i = head.index("選手名"), head.index("位置") if "位置" in head else 1
        order: list[str] = []
        for r in rows[1:]:
            if len(r) <= max(name_i, pos_i) or not r[0].isdigit():
                break
            if int(r[0]) != len(order) + 1:
                break
            name = r[name_i].strip()
            pos = (r[pos_i] or "").strip()
            if not name:
                break
            pos = pos[0] if pos and pos[0] in _POS_JP else ""
            order.append(f"{name}({pos})" if pos else name)
        if len(order) == 9:
            found.append(order)
    if len(found) < 2:
        return {"home": [], "away": []}
    return {"home": found[0], "away": found[1]}


# 종료 경기 표기: "神宮 ヤクルト 巨人 6 - 8 試合終了 …"  (홈 원정 홈점수 - 원정점수)
_SCORE_RE = re.compile(r"(\d+)\s*-\s*(\d+)")


def parse_finals(html: str) -> list[dict]:
    """[§8-28] 일정 HTML → **종료 경기와 최종 점수.**

    NPB 채점 경로다. 종전에는 Odds API `/scores`에 의존했는데 완료 경기가
    한 건도 안 잡혀(실측 2026-08-26, daysFrom=3) 채점이 증명되지 않았다.
    Yahoo 일정에는 `試合終了`와 점수가 그대로 있다.

    ⚠️ **`試合終了`가 있어야 종료다.** 점수만 보고 판단하면 진행 중 0-0 경기를
       종료로 오판한다 — KBO 공식 파서에서 겪은 것과 같은 유형의 사고다.
    ⚠️ 표기 순서는 **홈 먼저**다(일정 파서와 같은 규칙).
    """
    out, seen = [], set()
    for gid, inner in re.findall(
            r'href="/npb/game/(\d+)/[a-z]*"[^>]*>(.*?)</a>', html, re.S):
        if gid in seen:
            continue
        seen.add(gid)
        t = _text(inner)
        if "試合終了" not in t:
            continue                      # 진행 중·예정은 채점 대상이 아니다
        teams = [x for x in TEAM_TO_ODDS if x in t]
        if len(teams) != 2:
            continue
        teams.sort(key=t.index)
        m = _SCORE_RE.search(t)
        if not m:
            continue
        out.append({
            "game_id": gid,
            "home": TEAM_TO_ODDS[teams[0]], "away": TEAM_TO_ODDS[teams[1]],
            "home_kr": teams[0], "away_kr": teams[1],
            "home_score": int(m.group(1)), "away_score": int(m.group(2)),
        })
    return out


async def upsert_final_scores(pool, date: str, days: int = 3,
                              client: YahooNPBClient | None = None) -> int:
    """[§8-28] 채점기 진입점 — 최근 며칠의 NPB 종료 경기 점수를 games에 반영.

    `grader.grade_date`가 MLB·KBO와 같은 계약으로 부른다.
    """
    from datetime import UTC, date as _date, datetime, timedelta
    from zoneinfo import ZoneInfo

    client = client or YahooNPBClient()
    end = _date.fromisoformat(date)
    jst = ZoneInfo("Asia/Tokyo")
    n = 0
    for back in range(days + 1):
        day = (end - timedelta(days=back)).strftime("%Y-%m-%d")
        try:
            finals = parse_finals(score_card_html(await client.schedule(day)))
        except Exception as exc:          # 하루 실패가 채점 전체를 막지 않는다
            logger.warning("[yahoo_npb] %s 종료 경기 조회 실패: %s", day, exc)
            continue
        for g in finals:
            starts = datetime.fromisoformat(f"{day}T18:00:00").replace(tzinfo=jst)
            # [§8-37] ext_id가 아니라 **경기 자체**로 찾아 갱신한다 — 같은 경기가
            #   소스마다 다른 ext_id를 받아 갈라지면 예측이 붙은 행이 미채점으로 남는다.
            from app.collectors.game_match import apply_result

            await apply_result(
                pool, sport="npb", league="NPB", ext_id=f"yahoo:{g['game_id']}",
                starts_at=starts.astimezone(UTC), home=g["home"], away=g["away"],
                status="final", home_score=g["home_score"],
                away_score=g["away_score"])
            n += 1
    logger.info("[yahoo_npb] 종료 경기 %d건 적재 (%s 기준 %d일)", n, date, days)
    return n


def parse_game(html: str) -> dict | None:
    """경기 페이지 → 선발·불펜. 경기 전/후 **두 구조를 모두** 지원한다.

    ⚠️ 실사고(2026-08-26): 종료 경기 구조만 보고 파서를 만들었더니 **오늘 경기
       6건이 전부 파싱 실패**했다. 경기 전에는 `予告先発` 블록이고, 종료 후에는
       `投手|位置|選手名|投|防御率|調子` 표다. 구조가 다르다.
       → 개발 중 본 한 페이지가 전부라고 가정하면 안 된다.
    """
    starters: list[dict] = []
    bullpens: list[list[dict]] = []
    for tb in re.findall(r"<table[^>]*>(.*?)</table>", html, re.S):
        if "防御率" not in tb:
            continue
        rows = [r for r in (_cells(r) for r in
                            re.findall(r"<tr[^>]*>(.*?)</tr>", tb, re.S)) if r]
        if not rows:
            continue
        header = rows[0]
        if header[:len(STARTER_HEADER)] == list(STARTER_HEADER):
            for r in rows[1:]:
                if len(r) < 5:
                    continue
                starters.append({"name": r[2], "throws": _throws(r[3]),
                                 "era_season": _num(r[4]),
                                 "condition": CONDITION_KR.get(r[5] if len(r) > 5 else "")})
        elif header[:3] == ["選手名", "投打", "防御率"]:
            pen = [{"name": r[0], "throws": _throws(r[1]), "era": _num(r[2]),
                    "condition": CONDITION_KR.get(r[3] if len(r) > 3 else "")}
                   for r in rows[1:] if len(r) >= 3]
            if pen:
                bullpens.append(pen)
    if len(starters) < 2:
        starters = _parse_pregame(html)          # 경기 전 구조로 재시도
    if len(starters) < 2:
        logger.error("[yahoo_npb] 선발을 찾지 못했다 (선발 %d · 불펜표 %d)",
                     len(starters), len(bullpens))
        return None
    for st in starters:
        era, n = st.get("era_season"), st.get("appearances")
        thin = (n is not None and n < MIN_STARTER_APPEARANCES)
        if era is not None and (thin or era > MAX_CREDIBLE_ERA):
            st["era_unreliable"] = f"{era:.2f} (등판 {n if n is not None else '?'}회)"
            st.pop("era_season")           # λ에 넣지 않는다
            logger.info("[yahoo_npb] 표본 미달 선발 %s — ERA %s 폐기",
                        st.get("name"), st["era_unreliable"])
    out = {"home_pitcher": starters[0], "away_pitcher": starters[1]}
    if len(bullpens) >= 2:
        out["home_bullpen_list"] = bullpens[0]
        out["away_bullpen_list"] = bullpens[1]
    lu = parse_batting_orders(html)
    if lu["home"] and lu["away"]:
        out["lineup_home"] = "-".join(lu["home"])
        out["lineup_away"] = "-".join(lu["away"])
    return out


def _bullpen_era(pen: list[dict]) -> float | None:
    vals = [p["era"] for p in pen or [] if p.get("era") is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def merge_into_research(research: dict, jg: dict, data: dict) -> list[str]:
    """[§8-20] 크롤링 결과를 research에 얹는다. **크롤링이 딥서치를 이긴다.**

    ⚠️ 컨디션(好調/絶不調)은 **확률 계수로 쓰지 않는다.** Yahoo가 매기는 정성 평가라
       근거가 측정된 적이 없다 — 판정이 읽는 재료로만 넘긴다.
    """
    filled: list[str] = []
    if not data:
        return filled
    for side in ("home", "away"):
        p = data.get(f"{side}_pitcher")
        if p:
            blk = research.setdefault(f"{side}_pitcher", {})
            for k in ("name", "throws", "era_season"):
                v = p.get(k)
                if v is not None and blk.get(k) != v:
                    blk[k] = v
                    filled.append(f"{side}_pitcher.{k}")
            if p.get("condition"):
                blk["condition"] = p["condition"]      # 판정용 — λ 계수 아님
        pen = data.get(f"{side}_bullpen_list")
        if pen:
            era = _bullpen_era(pen)
            blk = research.setdefault(f"{side}_bullpen", {})
            if era is not None and blk.get("era") != era:
                blk["era"] = era
                filled.append(f"{side}_bullpen.era")
            blk["roster"] = ", ".join(
                f"{x['name']}({x['era']:.2f}"
                + (f"·{x['condition']}" if x.get("condition") else "") + ")"
                for x in pen if x.get("era") is not None)[:400]
    for side in ("home", "away"):
        order = (data.get(f"lineup_{side}") or "").strip(" -")
        if not order:
            continue
        n = len([x for x in order.split("-") if x.strip()])
        if n != 9:
            continue
        blk = research.setdefault(f"{side}_lineup", {})
        if blk.get("order") != order:
            blk["order"] = order
            blk["source"] = "Yahoo"
            filled.append(f"{side}_lineup.order")
    return filled


def _key(date: str) -> str:
    return f"yahoo_npb:{date}"


async def refresh(redis, date: str, client: YahooNPBClient | None = None) -> dict:
    """그 날짜 전 경기를 수집해 캐시. 조용한 0건은 알린다."""
    import json

    client = client or YahooNPBClient()
    games = parse_schedule(score_card_html(await client.schedule(date)))
    out: dict[str, dict] = {}
    failed = 0
    for g in games:
        try:
            parsed = parse_game(await client.game(g["game_id"]))
        except Exception as exc:
            logger.warning("[yahoo_npb] 경기 조회 실패 %s: %s", g["game_id"], exc)
            parsed = None
        if parsed is None:
            failed += 1
            continue
        parsed["starters_confirmed"] = g["starters_confirmed"]
        out[f"{g['away']}@{g['home']}"] = parsed
    if games and not out:
        from app.alerts import StageResult, stage_failed

        await stage_failed(StageResult(
            name="Yahoo NPB 수집", ok=0, total=len(games), cause="parse",
            detail=f"{date} 경기 {len(games)}건 중 파싱 실패 {failed}건",
            impact="NPB는 선발 지표 없이 판정 단독으로 갑니다"))
    await redis.set(_key(date), json.dumps(out, ensure_ascii=False), ex=CACHE_TTL)
    logger.info("[yahoo_npb] %s — %d경기 수집 (실패 %d)", date, len(out), failed)
    return {"games": len(out), "failed": failed}


async def load(redis, date: str) -> dict:
    import json

    raw = await redis.get(_key(date))
    return json.loads(raw) if raw else {}


async def upsert_schedule(pool, date: str,
                          client: YahooNPBClient | None = None) -> dict:
    """[Odds 이관] 그날 NPB 일정을 **Yahoo!スポーツ에서** games에 적재한다.

    KBO와 같은 이유다 — 배당을 판정에 쓰지 않는데 일정 소스가 Odds라
    크레딧이 마르면 응답 전체가 죽었다. 반환 계약은 Odds 경로와 같다.

    ⚠️ 시각: 일정 페이지가 경기 시각을 안정적으로 주지 않아 18:00 JST를 쓴다.
       `apply_result`가 ±20시간 창으로 경기를 찾으므로 매칭에는 지장이 없지만,
       **표시 시각은 부정확하다.** 시각 파싱은 별도 과제다.
    """
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    from app.collectors.game_match import apply_result

    client = client or YahooNPBClient()
    jst = ZoneInfo("Asia/Tokyo")
    html = score_card_html(await client.schedule(date))
    games = parse_schedule(html)
    finals = {g["game_id"] for g in parse_finals(html)}
    counts = {"scheduled": 0, "final": 0, "total": len(games)}
    for g in games:
        done = g["game_id"] in finals
        starts = datetime.fromisoformat(f"{date}T18:00:00").replace(tzinfo=jst)
        await apply_result(
            pool, sport="npb", league="NPB", ext_id=f"yahoo:{g['game_id']}",
            starts_at=starts.astimezone(UTC), home=g["home"], away=g["away"],
            status="final" if done else "scheduled",
            home_score=None, away_score=None)
        counts["final" if done else "scheduled"] += 1
    logger.info("[yahoo_npb] %s 일정 %d경기 적재 (예정 %d / 종료 %d) — Yahoo 소스",
                date, counts["total"], counts["scheduled"], counts["final"])
    return counts
