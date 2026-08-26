"""[§8-25] KBO 파크팩터 — **직접 측정한다.**

왜 만드나 (2026-08-26):
  KBO λ가 매번 `λ 미확보 입력: 파크팩터`로 나왔다. 잠실은 투수친화, 사직은
  타자친화라는 것이 상식인데 λ가 그걸 반영하지 못했다.
  스탯티즈는 접속이 막히고, KBO 공식 구장별 페이지는 비어 있다.
  → **경기 결과로 직접 잰다.** 공식 일정에 구장과 점수가 다 있다.

계산법 — 팀 편향을 제거한다:
    PF = (그 팀 홈 경기당 총득점) / (그 팀 원정 경기당 총득점)
  같은 팀이 분자·분모 양쪽에 있으므로 **팀 전력이 상쇄**된다.
  단순히 "구장별 평균 득점"을 쓰면 한화 홈(대전)이 높은 것이 구장 탓인지
  팀 탓인지 구분되지 않는다.

실측(2026-08-26, 543경기):
    사직 1.208 · 대전 1.151 · 수원 1.107 · 대구 1.095 · 창원 0.992
    고척 0.947 · 광주 0.913 · 문학 0.906 · 잠실 0.888
  잠실은 LG·두산 두 팀이 홈으로 쓰므로 둘의 평균이다.

⚠️ 시즌 중에는 표본이 계속 늘어난다 — 주 1회 갱신하고, 표본 미달 구장은
   1.0(중립)으로 두되 **그 사실을 남긴다**(없는 것을 있는 척하지 않는다).
"""

import logging

logger = logging.getLogger(__name__)

CACHE_TTL = 8 * 24 * 3600      # 주 1회 갱신 + 여유
MIN_GAMES_PER_SIDE = 20        # 홈·원정 각각 최소 경기 수 (이하면 신뢰하지 않는다)

# 팀(공식 표기) → 홈 구장. 잠실은 LG·두산 공용이다.
TEAM_HOME_STADIUM = {
    "LG": "잠실", "두산": "잠실", "키움": "고척", "NC": "창원", "KIA": "광주",
    "롯데": "사직", "SSG": "문학", "한화": "대전", "KT": "수원", "삼성": "대구",
}

# 구장 → Odds 팀명 (research에 얹을 때 홈팀 판정용)
STADIUM_OF_TEAM = {
    "LG Twins": "잠실", "Doosan Bears": "잠실", "Kiwoom Heroes": "고척",
    "NC Dinos": "창원", "Kia Tigers": "광주", "Lotte Giants": "사직",
    "SSG Landers": "문학", "Hanwha Eagles": "대전", "KT Wiz": "수원",
    "Samsung Lions": "대구",
}


def compute(games: list[dict]) -> dict[str, dict]:
    """종료 경기 목록 → {구장: {"pf", "games", "teams"}}.

    games 원소는 `app.collectors.kbo.parse_rows` 형식을 따른다
    (home_kr·away_kr·home_score·away_score·stadium·status).
    """
    home: dict[str, list[int]] = {}
    away: dict[str, list[int]] = {}
    for g in games:
        if g.get("status") != "final":
            continue
        hs, as_ = g.get("home_score"), g.get("away_score")
        if hs is None or as_ is None or not g.get("stadium"):
            continue
        total = hs + as_
        home.setdefault(g.get("home_kr"), []).append(total)
        away.setdefault(g.get("away_kr"), []).append(total)

    by_stadium: dict[str, list[tuple[float, int]]] = {}
    for team, h in home.items():
        a = away.get(team) or []
        stadium = TEAM_HOME_STADIUM.get(team)
        if not stadium:
            logger.warning("[kbo_park] 매핑 없는 팀 표기: %r", team)
            continue
        if len(h) < MIN_GAMES_PER_SIDE or len(a) < MIN_GAMES_PER_SIDE:
            continue                      # 표본 미달 — 신뢰하지 않는다
        hm, am = sum(h) / len(h), sum(a) / len(a)
        if am <= 0:
            continue
        by_stadium.setdefault(stadium, []).append((hm / am, len(h)))

    out: dict[str, dict] = {}
    for stadium, rows in by_stadium.items():
        # 잠실처럼 두 팀이 쓰는 구장은 **경기 수 가중 평균**
        n = sum(g for _p, g in rows)
        pf = sum(p * g for p, g in rows) / n if n else 1.0
        out[stadium] = {"pf": round(pf, 3), "games": n, "teams": len(rows)}
    logger.info("[kbo_park] 구장 %d개 산출", len(out))
    return out


def _key(season: int) -> str:
    return f"kbo_park:{season}"


async def refresh(redis, season: int = 2026, months: tuple[int, ...] = (3, 4, 5, 6, 7, 8, 9, 10),
                  client=None) -> dict:
    """공식 일정에서 시즌 전 경기를 받아 파크팩터를 산출·캐시."""
    import json

    from app.collectors.kbo import KBOClient, fetch_month

    client = client or KBOClient()
    games: list[dict] = []
    for m in months:
        try:
            games += await fetch_month(season, m, client)
        except Exception as exc:          # 한 달 실패가 전체를 막지 않는다
            logger.warning("[kbo_park] %d-%02d 조회 실패: %s", season, m, exc)
    table = compute(games)
    if not table:
        from app.alerts import StageResult, stage_failed

        await stage_failed(StageResult(
            name="KBO 파크팩터", ok=0, total=1, cause="missing",
            detail=f"{season} 시즌 종료 경기 {len(games)}건에서 산출 실패",
            impact="구장 효과 없이 λ를 냅니다 (잠실 0.89 · 사직 1.21 차이가 사라집니다)"))
    await redis.set(_key(season), json.dumps(table, ensure_ascii=False), ex=CACHE_TTL)
    return {"stadiums": len(table), "games": len(games)}


async def load(redis, season: int = 2026) -> dict[str, dict]:
    import json

    raw = await redis.get(_key(season))
    return json.loads(raw) if raw else {}


def merge_into_research(research: dict, jg: dict, table: dict) -> list[str]:
    """홈팀의 구장 파크팩터를 research에 얹는다. 반환: 채운 필드 목록.

    ⚠️ 표본 미달이거나 구장을 모르면 **넣지 않는다.** 1.0으로 채우면
       "측정했는데 중립"과 "못 쟀다"가 구분되지 않는다.
    """
    stadium = STADIUM_OF_TEAM.get(jg.get("home"))
    row = (table or {}).get(stadium or "")
    if not row or row.get("pf") is None:
        return []
    research["park_factor"] = row["pf"]
    research["park"] = (f"{stadium} — 파크팩터 {row['pf']:.3f} "
                        f"({row['games']}경기 실측)")
    return ["park_factor"]
