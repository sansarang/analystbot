"""[§8-20] NPB.jp 공식 팀 타격·투수 표 — λ의 타선(OBP) 입력.

왜 필요한가 (2026-08-26·28 실측):
  Yahoo는 선발 ERA·타순을 주지만 **팀 OBP가 없다.** `scoring._offense`는
  wOBA/OBP가 없으면 타선 계수를 못 만들고, NPB는 p_model이 0.5로 남거나
  선발 ERA만으로 양쪽 λ가 거의 같아진다.
  npb.jp 팀 타격 표는 시즌 누적 出塁率·長打率을 정적 HTML로 준다
  (실조회 2026-08-28: tmb_c.html / tmb_p.html).

⚠️ 시즌 누적이다. KBO와 같고 MLB 15경기 창과 다르다. `window="season"`.
⚠️ OPS 컬럼은 없다 — 出塁率+長打率로 계산한다. 없는 지표(wOBA)는 만들지 않는다.
⚠️ 선발 ERA는 Yahoo가 그 경기 투수를 안다. 여기서는 팀 타격·팀 방어율만.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from app.collectors.yahoo_npb import TEAM_TO_ODDS

logger = logging.getLogger(__name__)

JST = ZoneInfo("Asia/Tokyo")
BASE = "https://npb.jp"
CACHE_TTL = 26 * 3600

# 실조회 2026-08-28. 어긋나면 파싱 결과를 믿지 않는다.
HIT_HEADER = [
    "チーム", "打率", "試合", "打席", "打数", "得点", "安打", "二塁打",
    "三塁打", "本塁打", "塁打", "打点", "盗塁", "盗塁刺", "犠打", "犠飛",
    "四球", "故意四", "死球", "三振", "併殺打", "長打率", "出塁率",
]
PIT_HEADER = [
    "チーム", "防御率", "試合", "勝利", "敗北", "セーブ", "ホールド", "ＨＰ",
    "完投", "完封勝", "無四球", "勝率", "打者", "投球回", "安打", "本塁打",
    "四球", "故意四", "死球", "三振", "暴投", "ボーク", "失点", "自責点",
]

UNPUBLISHED_OFFENSE = ("xwoba_30d", "woba_30d", "xwoba", "woba", "iso_30d", "iso")
UNPUBLISHED_PITCHER = ("xwoba_allowed", "siera", "xfip", "fip")


def _season_year() -> int:
    return datetime.now(JST).year


def _paths(year: int | None = None) -> dict[str, str]:
    y = year or _season_year()
    return {
        "hit_c": f"/bis/{y}/stats/tmb_c.html",
        "hit_p": f"/bis/{y}/stats/tmb_p.html",
        "pit_c": f"/bis/{y}/stats/tmp_c.html",
        "pit_p": f"/bis/{y}/stats/tmp_p.html",
    }


def _cells(row: str) -> list[str]:
    return [re.sub(r"<[^>]+>", "", x).replace("&nbsp;", " ").strip()
            for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]


def _num(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_table(html: str, expect: list[str]) -> tuple[list[dict], list[str]]:
    """HTML 표 → [{헤더: 값}]. 헤더가 어긋나면 빈 목록."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    if not rows:
        return [], []
    header = _cells(rows[0])
    if header[:len(expect)] != expect:
        logger.error("[npb_stats] 헤더 불일치 — 기대 %s / 실제 %s",
                     expect[:8], header[:8])
        return [], header
    out = []
    for r in rows[1:]:
        c = _cells(r)
        if len(c) != len(header):
            continue
        out.append(dict(zip(header, c)))
    return out, header


class NPBStatsClient:
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


def _merge_rows(hit: list[dict], pit: list[dict]) -> dict[str, dict]:
    byp = {r.get("チーム"): r for r in pit}
    out: dict[str, dict] = {}
    for r in hit:
        jp = (r.get("チーム") or "").strip()
        name = TEAM_TO_ODDS.get(jp)
        if not name:
            logger.warning("[npb_stats] 매핑 없는 팀 표기: %r", jp)
            continue
        g, runs = _num(r.get("試合")), _num(r.get("得点"))
        obp, slg = _num(r.get("出塁率")), _num(r.get("長打率"))
        p = byp.get(jp) or {}
        stats = {
            "team_jp": jp,
            "window": "season",
            "games": g,
            "runs_per_game": round(runs / g, 3) if g and runs is not None else None,
            "avg": _num(r.get("打率")),
            "obp": obp,
            "slg": slg,
            "ops": round(obp + slg, 3) if obp is not None and slg is not None else None,
            "team_era": _num(p.get("防御率")),
        }
        out[name] = {k: v for k, v in stats.items() if v is not None}
    return out


async def fetch_team_stats(client: NPBStatsClient | None = None,
                           year: int | None = None) -> dict[str, dict]:
    """팀별 지표 — {Odds 팀명: {obp, slg, ops, team_era, ...}}."""
    client = client or NPBStatsClient()
    paths = _paths(year)
    hit, _ = parse_table(await client.get(paths["hit_c"]), HIT_HEADER)
    hit_p, _ = parse_table(await client.get(paths["hit_p"]), HIT_HEADER)
    pit, _ = parse_table(await client.get(paths["pit_c"]), PIT_HEADER)
    pit_p, _ = parse_table(await client.get(paths["pit_p"]), PIT_HEADER)
    out = _merge_rows(hit + hit_p, pit + pit_p)
    logger.info("[npb_stats] 팀 지표 %d팀", len(out))
    return out


def _key(kind: str, date: str) -> str:
    return f"npb_stats:{kind}:{date}"


async def refresh(redis, date: str) -> dict:
    import json

    from app.collectors.base import freesource_mocked

    if freesource_mocked(None):        # [P5-1] 무인증 소스 — 목 모드
        return {"ok": False, "teams": 0, "mock": True}

    teams = await fetch_team_stats()
    if not teams:
        from app.alerts import StageResult, stage_failed

        await stage_failed(StageResult(
            name="NPB 지표 수집", ok=0, total=1, cause="parse",
            detail="npb.jp 팀 성적 헤더 불일치 또는 표 없음",
            impact="NPB는 팀 OBP 없이 선발 ERA만으로 λ를 냅니다"))
    await redis.set(_key("teams", date), json.dumps(teams, ensure_ascii=False),
                    ex=CACHE_TTL)
    return {"teams": len(teams)}


async def load(redis, date: str) -> dict:
    import json

    raw = await redis.get(_key("teams", date))
    return json.loads(raw) if raw else {}


def league_baselines(teams: dict) -> dict:
    """수집한 12팀에서 리그 평균. config `league_obp=0.318`은 MLB 값이다."""
    def avg(key):
        vals = [v[key] for v in teams.values() if v.get(key) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    out = {}
    for src in ("obp", "ops", "slg"):
        v = avg(src)
        if v is not None:
            out[src] = v
    return out


def merge_into_research(research: dict, jg: dict, teams: dict) -> list[str]:
    """공식 팀 타격이 딥서치를 덮어쓴다. 선발 ERA는 Yahoo가 채운 것을 유지한다."""
    filled: list[str] = []
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
        for src, dst in (("ops", "ops"), ("obp", "obp_30d"), ("slg", "slg"),
                         ("avg", "avg"), ("runs_per_game", "runs_per_game")):
            if t.get(src) is None:
                continue
            if blk.get(dst) != t[src]:
                blk[dst] = t[src]
            filled.append(f"{side}_offense.{dst}")
        if t.get("team_era") is not None:
            research.setdefault(f"{side}_bullpen", {}).setdefault("era", t["team_era"])
            filled.append(f"{side}_bullpen.era")
    return filled
