"""[D 2026-09-02] 오늘 타순 9명의 **시즌 타격 라인**.

🔴 **규율 개정이다.** `CLAUDE.md`는 "타선·팀의 시즌 지표 금지"를 명시했고,
   9/01 선발 시즌 라인을 열 때도 "선발 한 칸만, 타선은 그대로"로 못을 박았다.
   **사용자 지시(2026-09-02)로 그 금지를 해제한다.**

   근거는 선발 때와 같은 구조다. 판정은 오늘 나온 9명이 기준이라고 말하면서,
   정작 그 9명이 어떤 타자인지는 볼 수 없었다. 타선 재료가 **팀 3경기 총득점**
   하나뿐이었기 때문이다. 3경기 득점은 표본 3이고 상대 선발에 좌우된다 —
   NYY@LAA에서 선발 표본 1경기를 "안정적"이라 읽은 것과 같은 실수를 타선에서
   반복할 구조였다.

   선발과 달리 **표본 보정 전용이 아니라 정식 근거**다 (사용자 결정).
   프롬프트가 "타선 평가의 주 근거"로 쓰게 하고, 3경기 득점은 그 위의 변동으로
   읽게 한다. 클립 0.32~0.68 · 뉴스/의도 ±3%p 상한은 그대로다.

⚠️ **`replay=True` 면 붙이지 않는다.** statsapi·기록실 시즌 값은 언제나 "지금"
   값이라 끝난 경기를 재현하면 그 경기가 시즌 라인에 들어간다 — 선발 시즌
   라인에서 이미 겪은 누수다(Will Dion, 2026-09-01).
⚠️ 실패해도 판정을 막지 않는다. 못 받으면 빈 dict 이고 그러면 종전과 같다.

수집 경로 (전부 2026-09-02 실호출로 확인):
  MLB  statsapi `/people?personIds=…&hydrate=stats(group=[hitting])` — 배치 1콜 20명
  KBO  기록실 HitterBasic Basic1+Basic2, 팀 드롭다운 POST (팀당 1페이지)
  NPB  npb.jp `/bis/{y}/stats/idb1_{팀}.html` — 팀별 **전 선수** 개인 타격표

  ⚠️ NPB 리그 순위표(`bat_c`/`bat_p`)는 쓰지 않는다. 규정타석 도달자만 43명
     (필요 108명의 40%)이고, 빠지는 쪽이 정확히 플래툰·하위타순 약한 타자들이라
     **모든 팀 타선이 실제보다 좋아 보이는 계통 편향**이 생긴다 (실측 2026-09-02).
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

#: 시즌 누적이라 하루 1회면 충분하다. 선발 시즌 라인과 같은 주기.
CACHE_TTL = 26 * 3600
_KBO_KEY = "lineup_season:kbo:{season}"
_NPB_KEY = "lineup_season:npb:{season}"

#: 프로세스 내 폴백 — redis 가 없어도 한 슬레이트 안에서는 1회로 줄인다.
#  🔴 **TTL 을 함께 들고 있어야 한다.** 스케줄러는 며칠씩 도는 프로세스라
#     만료 없는 dict 에 넣으면 시즌 성적이 기동 시점 값으로 영원히 굳는다
#     (redis 쪽은 26시간이라 자동으로 갱신되는데 메모리만 안 따라간다).
_mem: dict[str, tuple[float, dict]] = {}

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")


# ─────────────────────────── 이름 처리 ───────────────────────────

def split_order(order: str | None, known=None) -> list[str]:
    """`"이름-이름-…"` → 이름 목록. **하이픈 이름을 다시 붙인다.**

    🔴 실측 2026-09-02: `order.split("-")` 만으로는 MLB 24개 라인업 중 3개가
       깨졌다 — `Ha-Seong Kim` → `Ha` + `Seong Kim`,
       `Pete Crow-Armstrong` → `Pete Crow` + `Armstrong`,
       `Hao-Yu Lee` → `Hao` + `Yu Lee`. 219조각 중 6개가 사람이 아니었다.
       `known`(실명 사전)이 있으면 사전에 없는 조각을 다음 조각과 붙여본다.
       재결합 후 216/216 = 100%, 전 팀 정확히 9명.

    `known` 이 없으면 종전과 같이 그냥 자른다 — 사전 없이 추측하지 않는다.
    """
    raw = [x.strip() for x in (order or "").split("-") if x.strip()]
    if not known:
        return raw
    out: list[str] = []
    i = 0
    while i < len(raw):
        tok = raw[i]
        if tok in known or i + 1 >= len(raw):
            out.append(tok)
            i += 1
            continue
        merged = f"{tok}-{raw[i + 1]}"
        if merged in known:
            out.append(merged)
            i += 2
        else:
            out.append(tok)
            i += 1
    return out


#: 타순 표기의 투수 자리. 소스마다 다르다 — 전수로 적어둔다.
_PITCHER_POS = ("投", "투수", "투", "P", "SP")


def is_pitcher_slot(name: str) -> bool:
    """타순 항목이 **투수 자리**인가. 포지션 표기가 없으면 False (추측하지 않는다)."""
    m = re.search(r"\(([^)]*)\)\s*$", str(name or ""))
    return bool(m) and m.group(1).strip() in _PITCHER_POS


def strip_pos(name: str) -> str:
    """`"홍창기(중견수)"` → `"홍창기"`. 포지션 표기는 소스마다 다르다."""
    return re.sub(r"\([^)]*\)\s*$", "", str(name or "")).strip()


def norm_jp(name: str) -> str:
    """NPB 이름 정규화.

    🔴 라인업은 `浦田 俊輔(二)`(반각 공백), 성적표는 `浦田　俊輔`(전각 U+3000)다.
       공백을 전부 지워야 맞는다. `*` 는 npb.jp 의 좌타 표기다.
       실측 2026-09-02: 정규화 후 102/102 = 100%.
    """
    return re.sub(r"[\s　*＊]", "", strip_pos(name))


def _f(v):
    """숫자 칸. 빈 칸은 만들지 않는다."""
    if v in ("", None, "-", "－"):
        return None
    return v


# ─────────────────────────── 라인 정규화 ───────────────────────────

def slim_bat(*, pa=None, avg=None, obp=None, slg=None, ops=None,
             hr=None, bb=None, so=None) -> dict:
    """타자 한 줄. **없는 칸은 만들지 않는다.**

    ⚠️ **OPS 가 없는 소스는 OBP+SLG 로 만든다.** 그것이 OPS 의 정의다.
       실측 2026-09-02: npb.jp idb1 표에는 打率·長打率·出塁率만 있고 OPS 칸이
       없어, 합성하지 않으면 NPB 팀 가중 OPS 가 **통째로 빈 dict** 이 됐다.
       (statsapi·KBO Basic2 는 OPS 를 직접 준다 — 그때는 원값을 쓴다.)
    """
    out = {}
    for key, val in (("PA", pa), ("AVG", avg), ("OBP", obp), ("SLG", slg),
                     ("OPS", ops), ("HR", hr), ("BB", bb), ("SO", so)):
        v = _f(val)
        if v is not None:
            out[key] = v
    return out


def fill_ops(blk: dict) -> dict:
    """OPS 칸이 없으면 OBP+SLG 로 채운다. 둘 중 하나라도 없으면 만들지 않는다."""
    if blk.get("OPS") is not None:
        return blk
    obp, slg = _num(blk.get("OBP")), _num(blk.get("SLG"))
    if obp is not None and slg is not None:
        blk["OPS"] = f"{obp + slg:.3f}"
    return blk


def _num(v) -> float | None:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def team_line(batters: list[dict]) -> dict:
    """타순 9명 → 팀 합계. **타석 가중 OPS** 다.

    ⚠️ 단순 평균이 아니다. 대타·백업이 낀 라인업에서 표본 20타석짜리가
       주전과 같은 무게를 갖으면 팀 타선 수준이 왜곡된다.
    ⚠️ 재료가 하나도 없으면 빈 dict — 0.000 을 만들어내지 않는다.
    """
    num, den, pas = 0.0, 0.0, 0.0
    for b in batters or []:
        ops, pa = _num(b.get("OPS")), _num(b.get("PA"))
        if ops is None:
            continue
        w = pa if pa and pa > 0 else 1.0
        num += ops * w
        den += w
        pas += pa or 0
    if den <= 0:
        return {}
    return {"가중OPS": round(num / den, 3), "합계타석": int(pas), "인원": len(batters)}


# ─────────────────────────── MLB ───────────────────────────

async def fetch_mlb(names: list[str], season: int, redis=None) -> dict[str, dict]:
    """이름 → 시즌 타격 라인. 명단은 `starter_season` 의 캐시를 그대로 쓴다.

    ⚠️ 선수마다 1콜이면 15경기 슬레이트에 270콜이다. `personIds` 배치로 묶는다 —
       실측 2026-09-02: 20명 1콜 39KB.
    """
    from app.collectors.starter_season import StatsAPIClient, _roster

    want = {n for n in names if n}
    if not want:
        return {}
    try:
        roster = await _roster(season, redis)
    except Exception as exc:
        logger.warning("[lineup_season] MLB 명단 조회 실패 — 타선 시즌 없이 간다: %s", exc)
        return {}
    ids = {roster[n]: n for n in want if n in roster}
    if not ids:
        return {}
    cli = StatsAPIClient(mock=False)
    out: dict[str, dict] = {}
    batch = sorted(ids)
    for i in range(0, len(batch), 40):
        chunk = batch[i:i + 40]
        try:
            d = await cli.get("/people", {
                "personIds": ",".join(str(x) for x in chunk),
                "hydrate": f"stats(group=[hitting],type=[season],season={season})"})
        except Exception as exc:
            logger.warning("[lineup_season] MLB 배치 조회 실패 %d명: %s", len(chunk), exc)
            continue
        for p in (d or {}).get("people") or []:
            name = ids.get(p.get("id"))
            if not name:
                continue
            for st in p.get("stats") or []:
                for sp in st.get("splits") or []:
                    s = sp.get("stat") or {}
                    line = slim_bat(pa=s.get("plateAppearances"), avg=s.get("avg"),
                                    obp=s.get("obp"), slg=s.get("slg"),
                                    ops=s.get("ops"), hr=s.get("homeRuns"),
                                    bb=s.get("baseOnBalls"), so=s.get("strikeOuts"))
                    if line:
                        out[name] = line
    missing = want - set(out)
    if missing:
        logger.info("[lineup_season] MLB 미확보 %d명 (%s)", len(missing),
                    ", ".join(sorted(missing)[:5]))
    return out


# ─────────────────────────── KBO ───────────────────────────

KBO_BASE = "https://www.koreabaseball.com"
KBO_HITTER = "/Record/Player/HitterBasic/{page}.aspx"
_KBO_P = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$"

#: 기록실 팀 드롭다운 코드 → 우리 팀명 (`kbo_stats.TEAM_TO_ODDS` 와 같은 계약).
#  실조회 2026-09-02 의 option value/text 쌍에서 뽑았다.
KBO_TEAMS = {
    "LG": "LG Twins", "OB": "Doosan Bears", "KT": "KT Wiz", "SK": "SSG Landers",
    "NC": "NC Dinos", "WO": "Kiwoom Heroes", "HH": "Hanwha Eagles",
    "SS": "Samsung Lions", "LT": "Lotte Giants", "HT": "Kia Tigers",
}

#: Basic1/Basic2 헤더. 어긋나면 파싱 결과를 믿지 않는다 (`kbo_stats` 와 같은 규율).
KBO_EXPECT = {
    "Basic1": ["순위", "선수명", "팀명", "AVG", "G", "PA", "AB", "R", "H"],
    "Basic2": ["순위", "선수명", "팀명", "AVG", "BB", "IBB", "HBP", "SO", "GDP",
               "SLG", "OBP", "OPS"],
}


def _form_fields(html: str) -> dict:
    """ASP.NET WebForms 폼 상태를 **통째로** 뜬다.

    🔴 실측 2026-09-02: `__VIEWSTATE` 만 넣고 팀만 바꿔 POST 했더니 3,383바이트
       빈 페이지(0행)가 왔다. hidden 9개 + select 6개의 **현재 선택값을 전부**
       그대로 되돌려줘야 표가 온다. 하나라도 빠지면 조용히 0건이 된다.
    """
    f = {m.group(1): m.group(2) for m in re.finditer(
        r'<input[^>]+type="hidden"[^>]+name="([^"]+)"[^>]*value="([^"]*)"', html)}
    for m in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', html, re.S):
        name, body = m.group(1), m.group(2)
        sel = (re.search(r'<option[^>]*selected[^>]*value="([^"]*)"', body)
               or re.search(r'<option[^>]*value="([^"]*)"[^>]*selected', body)
               or re.search(r'<option[^>]*value="([^"]*)"', body))
        if sel:
            f[name] = sel.group(1)
    return f


def _cells(row: str) -> list[str]:
    return [re.sub(r"<[^>]+>", "", x).replace("&nbsp;", " ").strip()
            for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]


def parse_kbo(html: str, page: str) -> list[list[str]]:
    """기록실 표 → 행 목록. 헤더가 어긋나면 **빈 목록** (지어내지 않는다)."""
    head = [re.sub(r"<[^>]+>", "", t).strip()
            for t in re.findall(r"<th[^>]*>(.*?)</th>", html, re.S)]
    want = KBO_EXPECT[page]
    if head[:len(want)] != want:
        logger.error("[lineup_season] KBO %s 헤더 불일치 — 파싱 중단. 실제=%s",
                     page, head[:len(want)])
        return []
    return [cs for cs in (_cells(r) for r in
                          re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S))
            if len(cs) > len(want) - 1 and cs[0].isdigit()]


async def fetch_kbo(redis=None, season: int | None = None) -> dict[str, dict]:
    """KBO 전 팀 타자 시즌 라인. `{선수명: {..., "team": 팀명}}`.

    Basic1(AVG/PA/HR) 과 Basic2(SLG/OBP/OPS/BB/SO) 를 팀별로 각각 받아 합친다.
    10팀 × 2페이지 = 20요청, 26시간 캐시.
    """
    import httpx

    from app.config import get_settings

    season = season or _season_year()
    key = _KBO_KEY.format(season=season)
    cached = await _cache_get(redis, key)
    if cached is not None:
        return cached
    if get_settings().force_mock:
        return {}

    out: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True,
                                 headers={"User-Agent": UA,
                                          "Accept-Language": "ko-KR,ko;q=0.9"}) as c:
        for page, cols in (("Basic1", {"PA": 5, "HR": 11}),
                           ("Basic2", {"BB": 4, "SO": 7, "SLG": 9, "OBP": 10, "OPS": 11})):
            url = KBO_BASE + KBO_HITTER.format(page=page)
            try:
                base = await c.get(url)
                fields = _form_fields(base.text)
            except Exception as exc:
                logger.warning("[lineup_season] KBO %s 기본 페이지 실패: %s", page, exc)
                continue
            for code, team in KBO_TEAMS.items():
                f = dict(fields)
                f.update({"__EVENTTARGET": _KBO_P + "ddlTeam$ddlTeam",
                          "__EVENTARGUMENT": "", "__LASTFOCUS": "",
                          _KBO_P + "ddlTeam$ddlTeam": code})
                try:
                    r = await c.post(url, data=f, headers={
                        "Referer": url,
                        "Content-Type": "application/x-www-form-urlencoded"})
                    rows = parse_kbo(r.text, page)
                except Exception as exc:
                    logger.warning("[lineup_season] KBO %s %s 실패: %s", page, team, exc)
                    continue
                for cs in rows:
                    name = cs[1].strip()
                    blk = out.setdefault(name, {"team": team})
                    if page == "Basic1":
                        blk["AVG"] = cs[3]
                    for label, idx in cols.items():
                        if idx < len(cs):
                            v = _f(cs[idx])
                            if v is not None:
                                blk[label] = v
    for blk in out.values():
        fill_ops(blk)
    logger.info("[lineup_season] KBO 타자 %d명 적재 (season=%d)", len(out), season)
    if out:
        await _cache_set(redis, key, out)
    return out


# ─────────────────────────── NPB ───────────────────────────

NPB_BASE = "https://npb.jp"
NPB_PATH = "/bis/{season}/stats/idb1_{code}.html"

#: 팀 코드 → 우리 팀명. 실조회 2026-09-02 에 각 페이지 <title> 로 12건 전수 확인.
NPB_TEAMS = {
    "g": "Yomiuri Giants", "t": "Hanshin Tigers", "db": "Yokohama DeNA BayStars",
    "c": "Hiroshima Toyo Carp", "s": "Tokyo Yakult Swallows", "d": "Chunichi Dragons",
    "h": "Fukuoka SoftBank Hawks", "f": "Hokkaido Nippon-Ham Fighters",
    "m": "Chiba Lotte Marines", "e": "Tohoku Rakuten Golden Eagles",
    "l": "Saitama Seibu Lions", "b": "Orix Buffaloes",
}

#: idb1 표의 23칸. 인덱스로 읽으므로 칸 수가 어긋나면 그 행을 버린다.
_NPB_COLS = 23
_NPB_IDX = {"PA": 2, "HR": 8, "BB": 15, "SO": 18, "AVG": 20, "SLG": 21, "OBP": 22}


async def fetch_npb(redis=None, season: int | None = None) -> dict[str, dict]:
    """NPB 12팀 개인 타격. 키는 `norm_jp` 정규화 이름."""
    import httpx

    from app.config import get_settings

    season = season or _season_year()
    key = _NPB_KEY.format(season=season)
    cached = await _cache_get(redis, key)
    if cached is not None:
        return cached
    if get_settings().force_mock:
        return {}

    out: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True,
                                 headers={"User-Agent": UA}) as c:
        for code, team in NPB_TEAMS.items():
            try:
                r = await c.get(NPB_BASE + NPB_PATH.format(season=season, code=code))
                r.raise_for_status()
            except Exception as exc:
                logger.warning("[lineup_season] NPB %s 실패: %s", team, exc)
                continue
            n = 0
            for row in re.findall(r"<tr[^>]*>(.*?)</tr>", r.text, re.S):
                cs = _cells(row)
                if len(cs) != _NPB_COLS:
                    continue
                blk = {"team": team}
                for label, idx in _NPB_IDX.items():
                    v = _f(cs[idx])
                    if v is not None:
                        blk[label] = v
                out[norm_jp(cs[0])] = fill_ops(blk)
                n += 1
            logger.debug("[lineup_season] NPB %s %d명", team, n)
    logger.info("[lineup_season] NPB 타자 %d명 적재 (season=%d)", len(out), season)
    if out:
        await _cache_set(redis, key, out)
    return out


# ─────────────────────────── 캐시 · 배선 ───────────────────────────

def _season_year() -> int:
    from datetime import UTC, datetime

    return datetime.now(UTC).year


def _mem_get(key: str):
    hit = _mem.get(key)
    if hit is None:
        return None
    import time

    exp, val = hit
    if exp <= time.time():
        _mem.pop(key, None)
        return None
    return val


def _mem_put(key: str, val: dict) -> None:
    import time

    _mem[key] = (time.time() + CACHE_TTL, val)


async def _cache_get(redis, key: str):
    hit = _mem_get(key)
    if hit is not None:
        return hit
    if redis is None:
        return None
    try:
        import json

        raw = await redis.get(key)
        if raw:
            val = json.loads(raw)
            _mem_put(key, val)
            return val
    except Exception as exc:
        logger.debug("[lineup_season] 캐시 읽기 실패 %s: %s", key, exc)
    return None


async def _cache_set(redis, key: str, val: dict) -> None:
    _mem_put(key, val)
    if redis is None:
        return
    try:
        import json

        await redis.set(key, json.dumps(val, ensure_ascii=False), ex=CACHE_TTL)
    except Exception as exc:
        logger.debug("[lineup_season] 캐시 기록 실패 %s: %s", key, exc)


async def _table_for(sport: str, redis, season: int | None) -> dict[str, dict]:
    if sport == "kbo":
        return await fetch_kbo(redis, season)
    if sport == "npb":
        return await fetch_npb(redis, season)
    return {}


def lookup(table: dict, sport: str, name: str, team: str | None = None) -> dict:
    """정규화된 조회. 같은 이름이 두 팀에 있으면 **팀이 맞는 쪽**을 고른다."""
    key = norm_jp(name) if sport == "npb" else strip_pos(name)
    blk = table.get(key)
    if blk is None:
        return {}
    if team and blk.get("team") and blk["team"] != team:
        return {}
    return {k: v for k, v in blk.items() if k != "team"}


async def attach(jg: dict, redis=None, season: int | None = None,
                 *, replay: bool = False) -> None:
    """`research.{side}_lineup_season` 을 채운다. 실패해도 조용히 넘어간다.

    ⚠️ `replay=True` 면 **붙이지 않는다** — 시즌 값은 언제나 "지금" 값이라
       끝난 경기를 재현하면 그 경기가 시즌 라인에 포함된다(누수).
       선발 시즌 라인에서 이미 겪었다: `starter_season.attach` 의 같은 가드.
    """
    from app.config import get_settings

    sport = (jg.get("sport") or "").lower()
    if sport not in ("mlb", "kbo", "npb"):
        return
    research = jg.setdefault("research", {})
    if replay:
        for side in ("home", "away"):
            research[f"{side}_lineup_season"] = {}
        jg["lineup_season_suppressed"] = True
        logger.info("[lineup_season] 재현 모드 — 타선 시즌 제외(누수 차단) game=%s",
                    jg.get("game_id"))
        return
    # 목 모드에서는 외부를 때리지 않는다 — 판정 경로에 새 외부 호출을 붙일 때는
    # 목 분기를 같은 커밋에 넣는다 (딥서치·선발 시즌 라인에서 이미 겪었다).
    if get_settings().force_mock:
        for side in ("home", "away"):
            research.setdefault(f"{side}_lineup_season", {})
        return

    season = season or _season_year()
    orders = {s: ((research.get(f"{s}_lineup") or {}).get("order")
                  or jg.get(f"lineup_{s}") or "") for s in ("home", "away")}
    if not any(orders.values()):
        return

    if sport == "mlb":
        from app.collectors.starter_season import _roster

        try:
            roster = await _roster(season, redis)
        except Exception as exc:
            logger.warning("[lineup_season] MLB 명단 실패 — 타선 시즌 없이 간다: %s", exc)
            return
        names = {s: split_order(o, roster) for s, o in orders.items()}
        table = await fetch_mlb([n for v in names.values() for n in v], season, redis)
        get = lambda s, n: table.get(n) or {}       # noqa: E731
    else:
        table = await _table_for(sport, redis, season)
        if not table:
            return
        # 🔴 여기서 `strip_pos` 를 걸면 안 된다. 포지션 표기를 미리 지우면
        #    아래 투수 판정이 `(投)` 를 못 본다 (실측 2026-09-02: 센트럴 6경기
        #    전부 타자를 9명으로 셌다). 정규화는 `lookup` 이 조회 시점에 한다.
        names = {s: split_order(o) for s, o in orders.items()}
        get = lambda s, n: lookup(table, sport, n, jg.get(s))   # noqa: E731

    hit = tot = 0
    for side in ("home", "away"):
        batters = []
        for nm in names[side]:
            # NPB 센트럴은 타순 9번이 투수다(DH 없음). 타선 평가에서 뺀다 —
            # 투수 타격을 팀 가중 OPS 에 넣으면 라인업 수준이 부당하게 눌린다.
            # 🔴 표기가 소스마다 다르다: 일본 `(投)` · 한국 `(투수)` · 영문 `(P)`.
            #    실측 2026-09-02: `(투)`만 보다가 요미우리 戸郷 翔征(投)를 놓쳐
            #    센트럴 6경기 전부 타자 9명으로 세고 있었다.
            if is_pitcher_slot(nm):
                continue
            tot += 1
            line = get(side, nm)
            if line:
                hit += 1
            batters.append({"이름": strip_pos(nm), **line})
        research[f"{side}_lineup_season"] = {
            "타자": batters, "팀": team_line(batters)} if batters else {}
    if tot:
        logger.info("[lineup_season] %s 타선 시즌 game=%s 매칭 %d/%d (%d%%)",
                    sport.upper(), jg.get("game_id"), hit, tot, hit * 100 // tot)
