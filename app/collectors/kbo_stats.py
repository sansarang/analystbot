"""[§8-14] KBO 공식 기록실 — **숫자 지표** 수집. λ의 1차 입력.

왜 필요한가 (2026-08-26 실측):
  KBO 1경기 딥서치를 실호출했더니 서술(불펜 소모·로테이션·동기)은 잘 가져왔지만
  **ERA·OPS·최근 폼 같은 숫자는 하나도 못 가져왔다.** Perplexity는 못 찾으면
  200 OK로 "왜 못 찾았는지"를 산문에 담아 보내고, 그것이 validate에서 전량 폐기돼
  **재료 0**이 된다. MLB는 Statcast라는 숫자 백본이 있어 딥서치가 실패해도 λ가
  버티지만, KBO에는 그 백본이 없었다.

  → 공식 기록실이 팀 타격·팀 투수·선수 투수 지표를 **정적 HTML 표**로 준다.
    (AJAX인 일정 페이지와 달리 그냥 GET하면 나온다 — 실조회 2026-08-26)

⚠️ 이 값들은 **시즌 누적**이다. MLB의 15경기 창(§8-6)과 성격이 다르다.
   KBO는 경기별 로그 공개 경로가 없어 창을 자를 수 없다. 그 한계를 숨기지 말고
   `window="season"`으로 표기해 판정과 카드가 알 수 있게 한다.

⚠️ HTML 구조가 바뀌면 조용히 0건이 된다 — 헤더를 검증하고 어긋나면 알림을 보낸다.
"""

import logging
import re

logger = logging.getLogger(__name__)

BASE = "https://www.koreabaseball.com"
TEAM_HITTER1 = "/Record/Team/Hitter/Basic1.aspx"
TEAM_HITTER2 = "/Record/Team/Hitter/Basic2.aspx"
TEAM_PITCHER = "/Record/Team/Pitcher/Basic1.aspx"
PLAYER_PITCHER = "/Record/Player/PitcherBasic/BasicOld.aspx"

CACHE_TTL = 26 * 3600      # 하루 1회 갱신 + 여유 (시즌 누적이라 자주 볼 이유가 없다)

# 실조회 2026-08-26 기준 헤더. 어긋나면 파싱 결과를 믿지 않는다.
EXPECTED = {
    TEAM_HITTER1: ["순위", "팀명", "AVG", "G", "PA", "AB", "R", "H"],
    TEAM_HITTER2: ["순위", "팀명", "AVG", "BB", "IBB", "HBP", "SO", "GDP", "SLG", "OBP", "OPS"],
    TEAM_PITCHER: ["순위", "팀명", "ERA", "G", "W", "L", "SV", "HLD", "WPCT", "IP"],
    PLAYER_PITCHER: ["순위", "선수명", "팀명", "ERA", "G"],
}

# KBO 공식 축약 표기 → Odds API 팀명 (games 테이블과 잇는 키)
TEAM_TO_ODDS = {
    "LG": "LG Twins", "두산": "Doosan Bears", "KT": "KT Wiz", "SSG": "SSG Landers",
    "NC": "NC Dinos", "키움": "Kiwoom Heroes", "한화": "Hanwha Eagles",
    "삼성": "Samsung Lions", "롯데": "Lotte Giants", "KIA": "Kia Tigers",
}


def _cells(row: str) -> list[str]:
    return [re.sub(r"<[^>]+>", "", x).replace("&nbsp;", " ").strip()
            for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]


def parse_table(html: str, path: str) -> tuple[list[dict], list[str]]:
    """HTML 표 → [{헤더: 값}]. 반환 (행들, 헤더). 헤더가 어긋나면 빈 목록.

    ⚠️ 헤더 검증을 건너뛰면 컬럼이 밀렸을 때 **엉뚱한 값이 ERA로 들어간다.**
       조용한 오염이 조용한 0건보다 나쁘다.
    """
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    if not rows:
        return [], []
    header = _cells(rows[0])
    want = EXPECTED.get(path, [])
    if header[:len(want)] != want:
        logger.error("[kbo_stats] 헤더 불일치 %s — 기대 %s / 실제 %s",
                     path, want, header[:len(want)])
        return [], header
    out = []
    for r in rows[1:]:
        c = _cells(r)
        if len(c) != len(header):
            continue
        out.append(dict(zip(header, c)))
    return out, header


def _num(v):
    """'1008 1/3'(이닝) · '0.279' → float. 못 바꾸면 None (지어내지 않는다)."""
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    m = re.match(r"^(\d+)\s+(\d)/(\d)$", s)          # 이닝 표기 '1008 1/3'
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    try:
        return float(s)
    except ValueError:
        return None


class KBOStatsClient:
    """공식 기록실 정적 페이지 조회. 무인증·무료."""

    timeout = 25.0

    def __init__(self, mock: bool = False):
        self.mock = mock

    async def get(self, path: str) -> str:
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as c:
            r = await c.get(BASE + path, headers={"User-Agent": "Mozilla/5.0",
                                                  "Referer": BASE + path})
        r.raise_for_status()
        return r.text


async def fetch_team_stats(client: KBOStatsClient | None = None) -> dict[str, dict]:
    """팀별 지표 — {Odds 팀명: {runs_per_game, ops, obp, slg, era, whip, ...}}."""
    client = client or KBOStatsClient()
    h1, _ = parse_table(await client.get(TEAM_HITTER1), TEAM_HITTER1)
    h2, _ = parse_table(await client.get(TEAM_HITTER2), TEAM_HITTER2)
    pt, _ = parse_table(await client.get(TEAM_PITCHER), TEAM_PITCHER)

    by2 = {r["팀명"]: r for r in h2}
    byp = {r["팀명"]: r for r in pt}
    out: dict[str, dict] = {}
    for r in h1:
        kr = r["팀명"]
        name = TEAM_TO_ODDS.get(kr)
        if not name:
            logger.warning("[kbo_stats] 매핑 없는 팀 표기: %r", kr)
            continue
        g, runs = _num(r.get("G")), _num(r.get("R"))
        p, o = byp.get(kr, {}), by2.get(kr, {})
        stats = {
            "team_kr": kr,
            "window": "season",          # ⚠️ 시즌 누적 — MLB의 15경기 창과 다르다
            "games": g,
            "runs_per_game": round(runs / g, 3) if g and runs is not None else None,
            "avg": _num(r.get("AVG")),
            "obp": _num(o.get("OBP")), "slg": _num(o.get("SLG")), "ops": _num(o.get("OPS")),
            "team_era": _num(p.get("ERA")), "team_whip": _num(p.get("WHIP")),
        }
        ip, er = _num(p.get("IP")), _num(p.get("ER"))
        if ip and er is not None and g:
            stats["runs_allowed_per_game"] = round(_num(p.get("R")) / g, 3) \
                if _num(p.get("R")) is not None else None
        out[name] = {k: v for k, v in stats.items() if v is not None}
    logger.info("[kbo_stats] 팀 지표 %d팀", len(out))
    return out


async def fetch_pitcher_stats(client: KBOStatsClient | None = None) -> dict[str, dict]:
    """선수명 → 투수 지표. 선발 억제력의 입력.

    ⚠️ 이 페이지는 **규정이닝 상위 투수만** 싣는다. 명단에 없는 선발은
       '미수집'이며 리그 평균으로 대체하지 않는다 — 없는 것을 있는 척하지 않는다.
    """
    client = client or KBOStatsClient()
    rows, _ = parse_table(await client.get(PLAYER_PITCHER), PLAYER_PITCHER)
    out: dict[str, dict] = {}
    for r in rows:
        name = (r.get("선수명") or "").strip()
        if not name:
            continue
        ip, h, bb = _num(r.get("IP")), _num(r.get("H")), _num(r.get("BB"))
        era = _num(r.get("ERA"))
        rec = {"team_kr": r.get("팀명"), "era_season": era, "window": "season",
               "innings": ip, "games": _num(r.get("G")),
               "so": _num(r.get("SO")), "bb": bb}
        if ip and h is not None and bb is not None:
            rec["whip"] = round((h + bb) / ip, 3)
        out[name] = {k: v for k, v in rec.items() if v is not None}
    logger.info("[kbo_stats] 투수 지표 %d명", len(out))
    return out


def _key(kind: str, date: str) -> str:
    return f"kbo_stats:{kind}:{date}"


async def refresh(redis, date: str) -> dict:
    """하루 1회 갱신 → Redis 캐시. 반환 요약."""
    import json

    from app.collectors.base import freesource_mocked

    if freesource_mocked(None):        # [P5-1] 무인증 소스 — 목 모드
        return {"ok": False, "teams": 0, "pitchers": 0, "mock": True}

    teams = await fetch_team_stats()
    pitchers = await fetch_pitcher_stats()
    if not teams:
        from app.alerts import StageResult, stage_failed

        await stage_failed(StageResult(
            name="KBO 지표 수집", ok=0, total=1, cause="parse",
            detail="공식 기록실 헤더 불일치 또는 표 없음",
            impact="KBO는 숫자 지표 없이 서술만으로 판정하게 됩니다"))
    for kind, payload in (("teams", teams), ("pitchers", pitchers)):
        await redis.set(_key(kind, date), json.dumps(payload, ensure_ascii=False),
                        ex=CACHE_TTL)
    return {"teams": len(teams), "pitchers": len(pitchers)}


async def load(redis, date: str) -> tuple[dict, dict]:
    """캐시에서 (팀 지표, 투수 지표). 없으면 빈 dict — 크래시하지 않는다."""
    import json

    out = []
    for kind in ("teams", "pitchers"):
        raw = await redis.get(_key(kind, date))
        out.append(json.loads(raw) if raw else {})
    return out[0], out[1]


# [§8-15] KBO 공개 매체가 제공하지 않는 지표. LLM이 채워 오면 **출처 불명**이므로
#   λ에 넣지 않는다. (스탯티즈 등 일부 사설 사이트가 산출하지만 공식 기록이 아니고,
#   Perplexity가 그것을 인용했는지 지어냈는지 구분할 방법이 없다)
UNPUBLISHED_OFFENSE = ("xwoba_30d", "woba_30d", "xwoba", "woba", "iso_30d", "iso")
UNPUBLISHED_PITCHER = ("xwoba_allowed", "siera", "xfip", "fip")


def league_baselines(teams: dict) -> dict:
    """[§8-14] 수집한 팀 지표에서 **KBO 리그 평균**을 만든다.

    ⚠️ config의 `league_obp = 0.318`은 **MLB 값**이다. KBO 실측 리그 OBP는 0.355
    수준이라, MLB 기준으로 계수를 내면 전 팀이 일괄 +14% 부풀어 오른다
    (실측 사고 2026-08-26: 평균 타선인 LG가 ×1.141을 받아 λ가 5.76까지 올라갔다).
    `scoring._baseline`이 `research["league_baselines"]`를 1순위로 보므로
    여기에 심어 두면 종목별 상수를 새로 만들지 않고도 올바른 분모가 쓰인다.
    """
    def avg(key):
        vals = [v[key] for v in teams.values() if v.get(key) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    out = {}
    for src, dst in (("obp", "obp"), ("ops", "ops"), ("slg", "slg")):
        v = avg(src)
        if v is not None:
            out[dst] = v
    # wOBA·xwOBA는 KBO 공개 지표가 아니다 — 만들어 넣지 않는다(없는 것을 있는 척 금지)
    return out


def merge_into_research(research: dict, jg: dict, teams: dict, pitchers: dict) -> list[str]:
    """수집한 숫자를 research에 얹는다. 반환: 채운 필드 목록.

    ⚠️ **공식 기록이 딥서치를 덮어쓴다.** 규율: "LLM 출력의 수치는 API 숫자와
       교차검증. 충돌 시 API가 이긴다."

    실사고(2026-08-26 KBO 첫 실행): 초안은 `if dst not in blk`로 **빈칸만 채웠다.**
    그 결과 Perplexity가 준 wOBA 0.325·SIERA 3.50이 그대로 λ에 들어갔고,
    공식 기록(OBP 0.357·ERA 4.14)은 한 번도 쓰이지 않았다.
    **KBO는 wOBA·SIERA를 공개하지 않는다** — 그 값들은 출처 불명이며 지어냈을
    가능성이 높다. 규율이 정반대로 구현돼 있었던 셈이다.

    → 공식 값이 있으면 **무조건 덮어쓰고**, 공개되지 않는 지표(wOBA·xwOBA·SIERA·
      xFIP·FIP)는 **제거한다.** 없는 지표를 LLM이 만들어 오면 그것은 데이터가 아니다.
    """
    filled: list[str] = []
    # KBO 미공개 지표 — LLM이 만들어 왔다면 그것은 출처가 없다. λ에 들어가기 전에 지운다.
    for side in ("home", "away"):
        for blk_key, keys in ((f"{side}_offense", UNPUBLISHED_OFFENSE),
                              (f"{side}_pitcher", UNPUBLISHED_PITCHER)):
            blk = research.get(blk_key)
            if not isinstance(blk, dict):
                continue
            for k in keys:
                if blk.pop(k, None) is not None:
                    filled.append(f"-{blk_key}.{k}")
    base = league_baselines(teams)
    if base:
        research.setdefault("league_baselines", {}).update(base)
        filled.append("league_baselines")
    for side in ("home", "away"):
        t = teams.get(jg.get(side))
        if not t:
            continue
        blk = research.setdefault(f"{side}_offense", {})
        # `avg`를 포함한다 — 네이버도 같은 값을 주므로 **교차 대조 지점**이 된다.
        for src, dst in (("ops", "ops"), ("obp", "obp_30d"), ("slg", "slg"),
                         ("avg", "avg"), ("runs_per_game", "runs_per_game")):
            if t.get(src) is None:
                continue
            if blk.get(dst) != t[src]:
                blk[dst] = t[src]          # 공식 값이 이긴다 — 덮어쓴다
            filled.append(f"{side}_offense.{dst}")   # 값이 같아도 '관측'은 기록한다
        if t.get("team_era") is not None:
            research.setdefault(f"{side}_bullpen", {}).setdefault("era", t["team_era"])
            filled.append(f"{side}_bullpen.era")
    # 선발 — 이름은 딥서치가 준다(공식 기록실에 '오늘 선발' 필드가 없다)
    for side in ("home", "away"):
        blk = research.get(f"{side}_pitcher") or {}
        name = (blk.get("name") or "").strip()
        p = pitchers.get(name) if name else None
        if not p:
            continue
        for src, dst in (("era_season", "era_season"), ("whip", "whip")):
            if p.get(src) is not None and blk.get(dst) != p[src]:
                blk[dst] = p[src]          # 공식 값이 이긴다 — 덮어쓴다
                filled.append(f"{side}_pitcher.{dst}")
        research[f"{side}_pitcher"] = blk
    return filled
