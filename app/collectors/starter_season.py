"""[C 2026-09-01] 선발투수의 **시즌 라인** — 표본 보정 전용.

🔴 **규율 개정이다.** `CLAUDE.md`는 "시즌 ERA/xwOBA 금지"를 명시한다. 그 규칙은
   시즌 통념이 최근 폼을 덮는 것을 막으려는 것이고, **타선에는 그대로 유효하다.**
   여기서 푸는 것은 **선발투수 한 칸뿐**이다.

   실사고 2026-09-01 (NYY @ LAA, 1:7 패):
     Rodríguez 최근 등판 표본 1경기(6이닝 3실점) → 판정 "안정적" → NYY 66% 추천
     시즌: 6선발 26.2이닝 ERA 5.40 WHIP 1.58 **BB 16개(BB/9 5.4)**
     오늘: 3.2이닝 3볼넷 4실점 — 시즌 평균 그대로였다
     Ureña 최근 3경기가 부진 구간 → "이닝 소화력 불안"
     시즌: 23선발 123.1이닝 ERA 2.85 — 정상급. 오늘 7이닝 1실점 0볼넷 8K
   시즌 데이터가 결과를 예측하고 있었는데 판정이 볼 수 없게 되어 있었다.

⚠️ **용도는 표본 보정뿐이다.** 프롬프트가 이 값으로 우세를 정하지 못하게 막는다 —
   최근 등판이 시즌 성향과 크게 어긋날 때 "그 표본을 얼마나 믿을지"만 판단한다.
⚠️ 실패해도 판정을 막지 않는다. 못 받으면 빈 dict 이고, 그러면 종전과 같다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

BASE = "https://statsapi.mlb.com/api/v1"
TIMEOUT = 20.0


def slim_season(stat: dict) -> dict:
    """시즌 라인 한 줄. **승패(W-L)는 담지 않는다** — 기존 규율 그대로."""
    def _f(k):
        v = stat.get(k)
        return v if v not in ("", None) else None

    ip = _f("inningsPitched")
    bb, k = _f("baseOnBalls"), _f("strikeOuts")
    out = {"선발": _f("gamesStarted"), "이닝": ip, "ERA": _f("era"),
           "WHIP": _f("whip"), "K": k, "BB": bb}
    try:
        innings = float(ip)
        if innings > 0 and bb is not None:
            out["BB9"] = round(float(bb) * 9 / innings, 2)
        if innings > 0 and k is not None:
            out["K9"] = round(float(k) * 9 / innings, 2)
    except (TypeError, ValueError):
        pass
    return {k2: v for k2, v in out.items() if v is not None}


async def fetch_mlb(names: list[str], season: int) -> dict[str, dict]:
    """이름 → 시즌 라인. MLB만. statsapi 2콜(명단 1 + 선수당 1)."""
    import httpx

    want = {n for n in names if n}
    if not want:
        return {}
    out: dict[str, dict] = {}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as cli:
            r = await cli.get(f"{BASE}/sports/1/players", params={"season": season})
            r.raise_for_status()
            ids = {p["fullName"]: p["id"] for p in r.json().get("people", [])
                   if p.get("fullName") in want}
            for name, pid in ids.items():
                try:
                    d = await cli.get(
                        f"{BASE}/people/{pid}",
                        params={"hydrate": f"stats(group=[pitching],type=[season],"
                                           f"season={season})"})
                    d.raise_for_status()
                    for st in (d.json().get("people") or [{}])[0].get("stats", []):
                        for sp in st.get("splits", []):
                            line = slim_season(sp.get("stat") or {})
                            if line:
                                out[name] = line
                except Exception as exc:
                    logger.warning("[starter_season] %s 조회 실패: %s", name, exc)
    except Exception as exc:
        logger.warning("[starter_season] 명단 조회 실패: %s", exc)
        return {}
    missing = want - set(out)
    if missing:
        logger.info("[starter_season] 미확보 %s — 표본 보정 없이 간다",
                    ", ".join(sorted(missing)))
    return out


async def attach(jg: dict, season: int | None = None) -> None:
    """research.{side}_starter_season 을 채운다. MLB 전용, 실패해도 조용히 넘어간다."""
    if (jg.get("sport") or "") != "mlb":
        return
    from datetime import UTC, datetime

    from app.config import get_settings
    from app.engine.starter_recent import pitcher_name

    # 🔴 목 모드에서는 **호출하지 않는다.** 판정 경로에 새 외부 호출을 붙일
    #    때는 목 분기를 같은 커밋에 넣어야 한다 — 딥서치 배선에서 이미 겪었다
    #    (스위트가 api.anthropic.com 을 때려 35초 → 419초).
    #    실측 2026-09-01: 이 가드 없이 커밋했더니 P5-2 외부 차단이 테스트 4건에서
    #    statsapi.mlb.com 접근을 잡아냈다.
    if get_settings().force_mock:
        research = jg.setdefault("research", {})
        for side in ("home", "away"):
            research.setdefault(f"{side}_starter_season", {})
        return

    season = season or datetime.now(UTC).year
    names = {side: pitcher_name(jg, side) for side in ("home", "away")}
    lines = await fetch_mlb([n for n in names.values() if n], season)
    research = jg.setdefault("research", {})
    for side, name in names.items():
        research[f"{side}_starter_season"] = lines.get(name) or {}
