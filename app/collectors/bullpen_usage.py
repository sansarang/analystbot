"""[ORD-7] 불펜 등판 — **우리가 이미 긁어 둔 것**을 읽어 한 문장으로 만든다.

사용자 지시 2026-09-12: "2번으로 해라..크롤러로 직접 긁어라"

🔴 **새로 긁지 않는다.** 조사해 보니 `pitcher_appearances` 에 이미 들어 있다
   (실측 2026-09-12 운영: MLB 3,573행·투수 573 · KBO 2,327 · NPB 1,437).
   적재는 `mlb_boxscore.backfill`·`kbo_usage` 가 한다. 여기서 또 긁으면 그게
   사본이고, 원본이 바뀔 때 따라가지 않는다. 이 모듈은 **읽는 길**이다.

🔴 왜 필요한가. 검색이 이 축을 못 찾는다 — 실측 2026-09-12 game=5633
   "텍사스 불펜 사용량·마무리 가용"을 두 차례 모두 못 찾았다. 공개 소스가
   약한 곳인데 우리는 원시 기록을 갖고 있었다.

⚠️ **역할을 추정하지 않는다.** `kbo_usage` 가 이미 못박은 규약이다 — 응답에
   마무리·셋업 라벨이 없다. "마무리가 연투 중"은 추정이고, 추정을 사실 칸에
   넣으면 카드가 오염된다. 누가 · 언제 · 몇 이닝 · 몇 타자까지만 쓴다.
⚠️ **투구수는 없다.** 상대 타자 수가 소모 대리값이다(타자당 ~4구). 그렇게
   밝혀 적는다 — 투구수처럼 보이게 쓰면 그것이 거짓이다.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 되돌아보는 날수. 연투·소모는 사흘이면 드러난다.
DAYS = 3

#: 질문이 이 축을 겨눴는지 보는 말들. 원본은 `prompts.PRESCOUT` 의 불펜 축이다.
KEYWORDS = ("불펜", "bullpen", "연투", "back-to-back", "구원", "relief",
            "마무리", "closer", "필승조", "가용")


def matches(question: str) -> bool:
    """이 질문이 불펜 소모를 묻는가."""
    q = (question or "").lower()
    return any(k.lower() in q for k in KEYWORDS)


async def recent(pool, sport: str, team: str, *, days: int = DAYS) -> dict:
    """최근 `days` 일 **구원 등판**. 반환 `{"투수": [...], "마지막적재": date|None}`.

    🔴 등판이 0건인 것과 **적재가 안 된 것**은 다르다. 마지막 적재일을 함께
       돌려줘 호출부가 "등판 없음"과 "기록 없음"을 가를 수 있게 한다.
       가르지 않으면 "전원 가용"이라는 거짓이 카드로 나간다.
    """
    if pool is None:
        return {"투수": [], "마지막적재": None}
    try:
        rows = await pool.fetch(
            """SELECT pa.pitcher, g.starts_at::date AS d,
                      pa.innings, pa.batters
                 FROM pitcher_appearances pa
                 JOIN games g ON g.id = pa.game_id
                WHERE pa.sport = $1 AND pa.team = $2
                  AND NOT pa.is_starter
                  AND g.starts_at >= now() - ($3 || ' days')::interval
                  AND g.starts_at < now()
             ORDER BY g.starts_at DESC""", sport, team, str(int(days)))
        last = await pool.fetchval(
            """SELECT max(g.starts_at)::date
                 FROM pitcher_appearances pa
                 JOIN games g ON g.id = pa.game_id
                WHERE pa.sport = $1 AND pa.team = $2""", sport, team)
    except Exception as exc:                       # 조사 실패가 판정을 막지 않는다
        logger.warning("[bullpen] %s %s 조회 실패: %s", sport, team, exc)
        return {"투수": [], "마지막적재": None}

    by: dict[str, dict] = {}
    for r in rows:
        it = by.setdefault(r["pitcher"], {"이름": r["pitcher"], "날짜": [],
                                          "이닝": 0.0, "타자": 0})
        it["날짜"].append(r["d"])
        if r["innings"] is not None:
            it["이닝"] += float(r["innings"])
        if r["batters"] is not None:
            it["타자"] += int(r["batters"])
    out = []
    for it in by.values():
        ds = sorted(set(it["날짜"]))
        it["날짜"] = ds
        # 연투 = **날짜가 연속**. 새 임계를 만들지 않는다.
        it["연투"] = any((ds[i + 1] - ds[i]).days == 1 for i in range(len(ds) - 1))
        it["이닝"] = round(it["이닝"], 2)
        out.append(it)
    out.sort(key=lambda x: (-len(x["날짜"]), -x["타자"]))
    return {"투수": out, "마지막적재": last}


def to_answer(team: str, data: dict, *, days: int = DAYS) -> str:
    """한 문장. 없으면 빈 문자열(호출부가 싣지 않는다)."""
    pit = data.get("투수") or []
    last = data.get("마지막적재")
    if not pit:
        if last is None:
            return ""                              # 아무 기록도 없다 — 말하지 않는다
        # 🔴 "등판 없음"이 아니라 "기록상 없음"이다. 적재 시점을 함께 밝힌다.
        return (f"{team} 최근 {days}일 구원 등판 기록 없음 "
                f"(우리 기록 마지막 적재 {last}). 등판이 없었는지 기록이 안 들어왔는지는 "
                f"이 자료만으로 구분되지 않는다.")
    bits = []
    for p in pit:
        d = "·".join(f"{x.month}/{x.day}" for x in p["날짜"])
        tag = " 연투" if p["연투"] else ""
        bits.append(f"{p['이름']} {d}{tag} {p['이닝']}이닝 {p['타자']}타자")
    return (f"{team} 최근 {days}일 구원 등판 — " + " · ".join(bits)
            + ". 투구수는 수집되지 않아 상대 타자 수가 소모 대리값이다"
            + (f" (우리 기록 마지막 적재 {last})." if last else "."))


async def answers(pool, jg: dict, asks: list[str], *,
                  days: int = DAYS) -> list[dict]:
    """①이 불펜을 물었으면 우리 기록으로 답한다. 안 물었으면 빈 목록.

    ⚠️ 묻지 않은 것을 밀어 넣지 않는다 — 그러면 순서를 바꾼 의미가 없다.
    """
    hit = next((q for q in asks if matches(q)), None)
    if hit is None:
        return []
    sport = (jg.get("sport") or "").lower()
    out = []
    for side in ("away", "home"):
        team = jg.get(side) or ""
        if not team:
            continue
        text = to_answer(team, await recent(pool, sport, team, days=days),
                         days=days)
        if text:
            out.append({"질문": hit, "답": text, "소스": "크롤러",
                        "소스유형": "기록", "시점": "", "url": ""})
    if out:
        logger.info("[bullpen] %s@%s 우리 기록으로 %d건 답했다",
                    jg.get("away"), jg.get("home"), len(out))
    return out
