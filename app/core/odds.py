"""🔴🔴 **④ 시장 층** — 봇이 **스스로** 배당을 받아 공정 확률로. 네 층 지시서 §2.

> 배당은 봇이 스스로 가져온다. 사용자가 배당을 옮겨 적지 않는다.

## 이 파일이 지키는 것

| 조항 | 어떻게 |
|---|---|
| §2-1 피드 표 | `config/odds_sources.yaml` 만 읽는다 — 이름·한도를 코드에 안 박는다 |
| §2-2 예산 | 분석 **2회**·재분석 **1회** · 이벤트 목록 6시간 캐시 · 월 한도 80%/100% |
| §2-3 매칭 | 킥오프 ±8시간 **그리고** 두 팀 이름이 우리 열쇠 별칭과 맞을 때 **하나**면 |
| §2-4 기준 업체 | 피나클 있으면 피나클 · 없으면 업체별 **디빅한 확률의 중앙값** |
| §2-5 디빅 | `app/core/devig.py`(비례 + Shin) · 한 칸이라도 빠지면 그 마켓은 없음 |

🔴 **키가 없으면 아무것도 부르지 않는다** — `MarketProb(why=…)` 로 조용히 비운다.
🔴 **기대값·금액 계산은 없다**(§0 금지 · 계약이 AST 로 잠근다).
⚠️ 요청은 `app.net` 으로만 간다 — robots·UA·카세트 녹화가 전부 거기 붙어 있다.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

from app import rules
from app.core.schema import (Board, BoardLine, Market, MarketProb, MarketQuote,
                             MatchRef)
from app.core.state import RunState
from app.core import devig

logger = logging.getLogger(__name__)

#: 🔴 3-way 승무패의 쪽 이름 — 키 꼴은 `마켓:쪽[:점]` 하나다
WIN_SIDES = ("home", "draw", "away")


def key_of(market: str, side: str, point: float | None = None) -> str:
    """🔴 확률 표의 열쇠 — `마켓:쪽` 또는 `마켓:쪽:점`. ⚠️ 한 꼴만 쓴다."""
    return f"{market}:{side}" if point is None else f"{market}:{side}:{point:g}"


def feed_key(feed: dict) -> str:
    """🔴 `.env` 에서 키를 꺼낸다. ⚠️ 없으면 빈 문자열 — 그러면 부르지 않는다."""
    return (os.getenv(str(feed.get("key_env") or "")) or "").strip()


def ready_feeds() -> tuple[list[dict], list[str]]:
    """🔴 **키까지 있는** 피드만. `(피드들, 사유들)` — 빠진 이유를 전부 적는다."""
    out: list[dict] = []
    whys: list[str] = []
    for feed in rules.odds_feeds():
        name = str(feed.get("name"))
        if feed.get("card_required") is True:
            whys.append(f"{name} — 카드 등록이 필요해 **등록하지 않았다**(§2-1)")
            continue
        if feed.get("needs_key") and not feed_key(feed):
            whys.append(f"{name} — 키가 없다(`{feed.get('key_env')}` 비었다)")
            continue
        out.append(feed)
    if not out and not whys:
        whys.append("허용된 피드가 표에 없다")
    return out, whys


async def usage(pool, feed: str, *, when: date | None = None) -> tuple[int, int | None]:
    """🔴 §2-2 — 이번 **UTC 달**에 그 피드를 몇 번 불렀나. `(센 수, 피드가 말한 한도)`."""
    if pool is None:
        return 0, None
    month = (when or datetime.now(timezone.utc).date()).replace(day=1)
    async with pool.acquire() as con:
        got = await con.fetchrow(
            "SELECT calls, limit_said FROM odds_usage WHERE feed=$1 AND month=$2",
            feed, month)
    return (int(got["calls"]), got["limit_said"]) if got else (0, None)


async def note_call(pool, feed: str, *, remaining: int | None = None,
                    limit_said: int | None = None, used: int | None = None,
                    when: date | None = None) -> None:
    """🔴 한 번 불렀다고 원장에 적는다. ⚠️ 피드가 남은 수를 주면 그것도 적는다.

    🔴 `used` 는 **피드가 말한 누적**이다(우리가 센 수와 다를 수 있다 — 다른 기계가
       같은 키로 불렀을 때). 그 둘을 **따로** 쌓는다: `calls` 는 우리 수,
       `remaining` 은 피드 수다.
    """
    if pool is None:
        return
    month = (when or datetime.now(timezone.utc).date()).replace(day=1)
    async with pool.acquire() as con:
        await con.execute(
            """INSERT INTO odds_usage (feed, month, calls, limit_said, remaining)
               VALUES ($1, $2, 1, $3, $4)
               ON CONFLICT (feed, month) DO UPDATE SET
                 calls = odds_usage.calls + 1,
                 limit_said = COALESCE($3, odds_usage.limit_said),
                 remaining = COALESCE($4, odds_usage.remaining),
                 updated_at = now()""",
            feed, month, limit_said, remaining)
    if used is not None and limit_said:
        logger.info("[odds] 피드가 말한 누적 %s/%s", used, limit_said)


def budget_left(calls: int, limit: int | None) -> tuple[bool, str]:
    """🔴 §2-2 — 더 불러도 되나. `(된다, 사유)`. 80% 경고 · 100% 중단."""
    box = rules.odds_budget()
    if not limit:
        return True, ""
    pct = 100.0 * calls / float(limit)
    if pct >= float(box.get("stop_at_pct", 100)):
        return False, f"월 한도 {calls}/{limit} — **호출 중단**(§2-2)"
    if pct >= float(box.get("warn_at_pct", 80)):
        return True, f"월 사용 {calls}/{limit}({pct:.0f}%) — 한도에 가깝다"
    return True, f"월 사용 {calls}/{limit}"


# ══════════════════════════════════════════════════════════════════
# §2-3 경기 매칭
# ══════════════════════════════════════════════════════════════════


def match_event(ref: MatchRef, events: list[dict]) -> tuple[dict | None, str]:
    """🔴 §2-3 — 피드 이벤트를 우리 경기에 붙인다. **후보가 정확히 하나일 때만.**

    (a) 킥오프 UTC **±`window.same_match_hours`** (b) 두 팀 이름이 우리 열쇠의
    별칭과 **둘 다** 맞을 때. ⚠️ 둘 이상이거나 0 이면 *"시장 매칭 실패 — 사유"*.
    🔴 새 이름은 **별칭 후보로만** 기록한다 — 별칭표를 제 맘대로 늘리지 않는다.
    """
    from app import teamref
    hours = float((rules.odds_sources().get("match_window") or {}).get(
        "same_match_hours", 8))
    span = timedelta(hours=hours)
    hits: list[dict] = []
    for ev in events:
        when = _utc(ev.get("commence_time") or ev.get("start_time") or "")
        if when is None or abs(when - ref.kickoff_utc) > span:
            continue
        keys = set()
        for nm in (ev.get("home_team"), ev.get("away_team")):
            got, _ = teamref.key_of(str(nm or ""))
            if got:
                keys.add(got)
        if {str(ref.home), str(ref.away)} <= keys:
            hits.append(ev)
    if len(hits) == 1:
        return hits[0], f"킥오프 ±{hours:g}h · 두 팀 열쇠 일치"
    if not hits:
        return None, (f"후보 0건 — 창 ±{hours:g}h 안에 두 팀 열쇠가 맞는 이벤트가 없다"
                      f"(이벤트 {len(events)}건)")
    return None, f"후보 {len(hits)}건 — 하나로 못 좁혔다(§2-3 은 하나일 때만 쓴다)"


def _utc(said: object) -> datetime | None:
    try:
        got = datetime.fromisoformat(str(said).replace("Z", "+00:00"))
    except ValueError:
        return None
    return got if got.tzinfo else got.replace(tzinfo=timezone.utc)


# ══════════════════════════════════════════════════════════════════
# §2-4·§2-5 업체 고르기와 디빅
# ══════════════════════════════════════════════════════════════════

#: 🔴 피드 마켓 이름 → 우리 `Market`. ⚠️ 모르는 이름은 **버린다**(조용히 안 바꾼다)
FEED_MARKETS: dict[str, Market] = {
    "h2h": "win", "1x2": "win", "moneyline": "win",
    "spreads": "handicap", "asian_handicap": "handicap",
    "totals": "total", "btts": "btts",
}


#: 🔴 odds-api.io 마켓 이름 → 우리 `Market`(실측 `/markets?sport=football`)
IO_MARKETS: dict[str, Market] = {
    "ml": "win", "spread": "handicap", "totals": "total",
    "goals over/under": "total", "both teams to score": "btts",
    "double chance": "unbeaten",
}


def quotes_io(event: dict) -> tuple[list[MarketQuote], list[str]]:
    """🔴🔴 **odds-api.io 꼴** → 배당 묶음(§2-1 두 번째 피드).

    실측한 응답 꼴(문서 `llms-full.txt`):

    ```
    bookmakers: {"Bet365": [{"name": "ML", "odds": [{"home": "2.10",
                 "draw": "3.40", "away": "3.20"}]},
                            {"name": "Spread", "odds": [{"hdp": -0.5,
                 "home": "1.95", "away": "1.85"}]}]}
    ```

    ⚠️ 배당이 **문자열**로 온다 — 숫자로 바꾸고 못 바꾸면 그 줄을 버린다.
    🔴 `hdp`·`points` 가 기준선이다. `Double Chance` 는 쪽 이름이 `homeDraw` 꼴이라
       **우리 `unbeaten`** 으로 옮긴다(없으면 버린다 — 지어내지 않는다).
    """
    out: list[MarketQuote] = []
    skipped: list[str] = []
    box = event.get("bookmakers")
    if not isinstance(box, dict):
        return out, ["`bookmakers` 가 표 꼴이 아니다"]
    for bname, rows in box.items():
        for mk in (rows or []):
            if not isinstance(mk, dict):
                continue
            said = str(mk.get("name") or "").strip().lower()
            mine = IO_MARKETS.get(said)
            if mine is None:
                skipped.append(f"{bname}/{mk.get('name')} — 모르는 마켓")
                continue
            for row in (mk.get("odds") or []):
                if not isinstance(row, dict):
                    continue
                point = _point(row.get("hdp", row.get("points",
                                                      row.get("total"))))
                for side_key, side in (("home", "home"), ("draw", "draw"),
                                       ("away", "away"), ("over", "over"),
                                       ("under", "under"), ("yes", "yes"),
                                       ("no", "no"), ("homeDraw", "home"),
                                       ("awayDraw", "away")):
                    got = row.get(side_key)
                    if got is None:
                        continue
                    try:
                        price = float(str(got))
                    except (TypeError, ValueError):
                        skipped.append(f"{bname}/{said}/{side_key} — 숫자가 아니다")
                        continue
                    if price < 1.01:
                        continue
                    out.append(MarketQuote(market=mine, side=side, point=point,
                                           price=price, bookmaker=str(bname)))
    return out, skipped


def quotes_for(feed: dict, event: dict) -> tuple[list[MarketQuote], list[str]]:
    """🔴 그 피드의 **응답 꼴**에 맞는 변환기를 고른다(`shape` 칸이 든다)."""
    if str(feed.get("shape") or "") == "odds_api_io":
        return quotes_io(event)
    return quotes_of(event)


def quotes_of(event: dict) -> tuple[list[MarketQuote], list[str]]:
    """🔴 피드 이벤트 → 배당 묶음. ⚠️ 모르는 마켓·쪽은 사유와 함께 **버린다**.

    The-Odds-API 꼴: `bookmakers[].markets[].outcomes[{name, price, point}]`.
    """
    out: list[MarketQuote] = []
    skipped: list[str] = []
    for book in (event.get("bookmakers") or []):
        bname = str(book.get("key") or book.get("title") or "")
        for mk in (book.get("markets") or []):
            said = str(mk.get("key") or "")
            mine = FEED_MARKETS.get(said)
            if mine is None:
                skipped.append(f"{bname}/{said} — 모르는 마켓")
                continue
            for row in (mk.get("outcomes") or []):
                price = row.get("price")
                side = _side_of(mine, str(row.get("name") or ""), event)
                if side is None or not price:
                    skipped.append(f"{bname}/{said}/{row.get('name')} — 쪽을 못 읽었다")
                    continue
                try:
                    out.append(MarketQuote(market=mine, side=side,
                                           point=_point(row.get("point")),
                                           price=float(price), bookmaker=bname))
                except ValueError as exc:
                    skipped.append(f"{bname}/{said}/{side} — {exc}")
    return out, skipped


def _point(said: object) -> float | None:
    try:
        return float(said)                                  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _side_of(market: Market, name: str, event: dict) -> str | None:
    """🔴 피드의 쪽 이름 → 우리 쪽 이름. ⚠️ 팀 이름은 홈/원정으로 바꾼다."""
    low = name.strip().lower()
    if market == "win":
        if low in ("draw", "tie"):
            return "draw"
        if low == str(event.get("home_team") or "").lower():
            return "home"
        if low == str(event.get("away_team") or "").lower():
            return "away"
        return None
    if market == "handicap":
        if low == str(event.get("home_team") or "").lower():
            return "home"
        if low == str(event.get("away_team") or "").lower():
            return "away"
        return None
    if market == "total":
        return low if low in ("over", "under") else None
    if market == "btts":
        return low if low in ("yes", "no") else None
    return None


def books_of(quotes: list[MarketQuote]) -> list[str]:
    return sorted({q.bookmaker for q in quotes if q.bookmaker})


def pick_basis(quotes: list[MarketQuote]) -> tuple[list[str], str]:
    """🔴 §2-4 — 어느 업체로 볼까. `(업체들, 카드에 적을 말)`.

    피나클이 있으면 **피나클 하나**, 없으면 **전부**(그러면 중앙값을 쓴다).
    """
    names = books_of(quotes)
    ref = str(rules.odds_sources().get("reference_bookmaker") or "pinnacle")
    # ⚠️ **"시장 = " 을 붙이지 않는다** — 카드가 그 말을 이미 적는다(실측 2026-10-06:
    #    `시장 = 시장 = pinnacle(...)` 로 두 번 찍혔다).
    if ref in names:
        return [ref], ref
    if len(names) == 1:
        return names, f"{names[0]}(단일 업체)"
    return names, f"{len(names)}개 업체 중앙값"


def probs_of(quotes: list[MarketQuote], *, basis: list[str]
             ) -> tuple[dict[str, float], dict[str, float], dict[str, float],
                        list[str]]:
    """🔴 §2-5 — 배당 → `(공정 확률, Shin, 업체 몫, 못 만든 사유)`.

    🔴 **같은 마켓의 모든 결과가 있어야** 한다. 승무패 셋 · 핸디·총점·양팀득점 둘.
    ⚠️ 업체가 여럿이면 **업체별로 디빅한 뒤 중앙값**이다(디빅 전 평균 금지 · §2-4).
    """
    use = [q for q in quotes if not basis or q.bookmaker in basis]
    groups: dict[tuple, dict[str, list[tuple[str, float]]]] = {}
    for q in use:
        gk = (q.market, q.point)
        groups.setdefault(gk, {}).setdefault(q.bookmaker, []).append((q.side, q.price))
    out: dict[str, float] = {}
    shin_out: dict[str, float] = {}
    vig: dict[str, float] = {}
    bad: list[str] = []
    for (market, point), per_book in sorted(groups.items(), key=lambda kv: str(kv[0])):
        want = WIN_SIDES if market == "win" else None
        rows: list[list[float]] = []
        sides: list[str] = []
        vigs: list[float] = []
        shins: list[list[float]] = []
        for _, pairs in sorted(per_book.items()):
            box = dict(pairs)
            if want is not None:
                if not set(want) <= set(box):
                    continue
                order = [str(x) for x in want]
            else:
                if len(box) != 2:
                    continue
                order = sorted(box)
            prices = [box[s] for s in order]
            probs, mine = devig.proportional(prices)
            if not probs:
                continue
            rows.append(probs)
            vigs.append(mine)
            if market == "win":
                shins.append(devig.shin(prices))
            sides = order
        if not rows:
            bad.append(f"{market}{'' if point is None else f' {point:g}'} — "
                       f"결과 배당이 다 안 왔다(§2-5)")
            continue
        final = devig.median_of(rows) if len(rows) > 1 else rows[0]
        for side, p in zip(sides, final, strict=False):
            out[key_of(market, side, point)] = round(float(p), 6)
        if shins:
            said = devig.median_of(shins) if len(shins) > 1 else shins[0]
            for side, p in zip(sides, said, strict=False):
                shin_out[key_of(market, side, point)] = round(float(p), 6)
        vkey = market if point is None else f"{market}:{point:g}"
        vig[vkey] = round(sum(vigs) / len(vigs), 6)
    # 🔴 §2-5 — 더블찬스는 **유도**한다(따로 받지 않는다)
    h, d, a = (out.get(key_of("win", s)) for s in WIN_SIDES)
    if None not in (h, d, a):
        for k, v in devig.double_chance(float(h), float(d), float(a)).items():  # type: ignore[arg-type]
            out[k] = round(v, 6)
    return out, shin_out, vig, bad


def from_board(board: Board | None, *, source: str) -> MarketProb:
    """🔴 §2-6 — **사용자 보드** 배당으로 시장 확률. 피드가 없을 때 이것이 시장 열이다.

    ⚠️ 피드 배당과 **한 열에 섞지 않는다**(불변식) — 호출부가 열을 가른다.
    """
    lines = list(getattr(board, "lines", []) or [])
    # 🔴🔴 **무승부 줄을 승무패로 모은다** — 보드 파서는 무승부를 `market="draw"` 로
    #    적는다(그쪽은 판정용 줄이다). ⚠️ 그대로 두면 승무패 셋이 **둘**로 보여
    #    §2-5("한 칸이라도 빠지면 확률 없음")가 사용자 보드를 늘 버린다
    #    (실측 2026-10-06: 1.66/3.79/4.55 를 줬는데 시장 열이 `—` 였다).
    quotes = [MarketQuote(market=("win" if ln.market == "draw" else ln.market),
                          side=("draw" if ln.market == "draw" else ln.side),
                          point=ln.point, price=float(ln.price),
                          bookmaker="user_board")
              for ln in lines if ln.price]
    if not quotes:
        return MarketProb(basis="", source=source,
                          why="사용자 보드에 배당 숫자가 없다")
    probs, shin, vig, bad = probs_of(quotes, basis=["user_board"])
    return MarketProb(probs=probs, shin=shin, vig=vig, quotes=quotes,
                      basis="사용자 보드", source=source,
                      why=" · ".join(bad))


async def from_feed(ref: MatchRef, *, pool, net, state: RunState,
                    reanalyze: bool = False) -> MarketProb:
    """🔴 §2 — 피드에서 배당을 받는다. ⚠️ **키·예산이 없으면 조용히 비운다.**

    요청은 최대 2회(재분석 1회): 이벤트 목록 1 + 그 경기 배당 1(§2-2).
    """
    feeds, whys = ready_feeds()
    if not feeds:
        return MarketProb(why="시장 없음 — " + " · ".join(whys))
    box = rules.odds_budget()
    cap = int(box.get("per_reanalyze" if reanalyze else "per_analyze", 2))
    for feed in feeds:
        name = str(feed.get("name"))
        calls, said_limit = await usage(pool, name)
        limit = said_limit or feed.get("monthly_limit")
        ok, note = budget_left(calls, int(limit) if limit else None)
        if not ok:
            whys.append(f"{name} — {note}")
            continue
        got, why = await _one_feed(feed, ref, pool=pool, net=net, state=state,
                                   cap=cap)
        if got is not None:
            return got.model_copy(update={
                "used": calls + (1 if cap >= 1 else 0),
                "limit": int(limit) if limit else None,
                "why": note})
        whys.append(f"{name} — {why}")
    return MarketProb(why="시장 없음 — " + " · ".join(whys))


def sport_key_of(feed: dict, ref: MatchRef) -> tuple[str, str]:
    """🔴🔴 그 경기의 **피드 종목 열쇠**. `(열쇠, 사유)` — 없으면 빈 글자.

    🔴 표는 `config/odds_sources.yaml` 의 `sport_words` 다(코드에 박지 않는다).
    ⚠️ 실측 2026-10-06: 이 피드에는 **대표팀 친선·CONCACAF·AFC 가 없다**. 그 경기에
       열쇠를 억지로 붙여 부르면 크레딧만 쓰고 0건이 온다 — 그래서 **안 부른다**.
    """
    said = f"{ref.competition} {ref.competition_short}".lower()
    for skey, words in (feed.get("sport_words") or {}).items():
        for w in (words or []):
            if str(w).lower() in said:
                return str(skey), f"대회명에 `{w}` 가 있다"
    return "", (f"`{ref.competition}` 에 맞는 종목 열쇠가 표에 없다 — 이 피드는 "
                f"대표팀 친선·CONCACAF·AFC 를 다루지 않는다(실측 2026-10-06)")


async def _one_feed(feed: dict, ref: MatchRef, *, pool, net, state: RunState,
                    cap: int) -> tuple[MarketProb | None, str]:
    """🔴 피드 하나 — 이벤트 목록 → 매칭 → 그 경기 배당. 요청 수는 `cap` 이내."""
    base = str(feed.get("base_url") or "").rstrip("/")
    eps = dict(feed.get("endpoints") or {})
    key = feed_key(feed)
    sport, why_s = sport_key_of(feed, ref)
    if not sport:
        return None, why_s
    url = base + str(eps.get("events") or "").replace("{sport}", sport)
    if not str(eps.get("events") or ""):
        return None, "이벤트 목록 경로가 표에 없다"
    spent = 0
    events, why, head = await _json(net, url, {"apiKey": key}, state=state)
    spent += 1
    # 🔴 **크레딧이 든 요청만** 센다 — 실측 2026-10-06: `/events` 는 **0 크레딧**이고
    #    `/events/{id}/odds` 가 1 크레딧이다(`x-requests-last` 가 그렇게 말한다).
    cost = _last_cost(head)
    if cost:
        await note_call(pool, str(feed.get("name")), **_quota(head))
    state.note(f"s2c 이벤트 목록 — 크레딧 {cost} · 남은 "
               f"{head.get('x-requests-remaining', '?')}")
    if events is None:
        return None, f"이벤트 목록을 못 받았다 — {why}"
    ev, said = match_event(ref, list(events if isinstance(events, list) else []))
    if ev is None:
        return None, f"매칭 실패 — {said}"
    if spent >= cap:
        return None, f"예산 소진 — 요청 {spent}/{cap}(이벤트 목록까지만)"
    odds_url = base + str(eps.get("event_odds") or "").replace(
        "{sport}", sport).replace("{event_id}", str(ev.get("id") or ""))
    markets = ",".join(k for k in ("h2h", "spreads", "totals")
                       if k in (feed.get("markets") or []))
    got, why2, head2 = await _json(net, odds_url,
                                   {"apiKey": key, "regions": "eu",
                                    "markets": markets or "h2h",
                                    "oddsFormat": "decimal"}, state=state)
    if _last_cost(head2):
        await note_call(pool, str(feed.get("name")), **_quota(head2))
    if not isinstance(got, dict):
        return None, f"그 경기 배당을 못 받았다 — {why2}"
    quotes, skipped = quotes_for(feed, got)
    if not quotes:
        return None, "배당 줄을 하나도 못 읽었다 · " + " · ".join(skipped[:3])
    basis, label = pick_basis(quotes)
    probs, shin, vig, bad = probs_of(quotes, basis=basis)
    for line in skipped[:5]:
        state.note(f"s2c 버린 줄 — {line}")
    said = _quota(head2)
    return MarketProb(probs=probs, shin=shin, vig=vig, quotes=quotes,
                      basis=f"{label}(피드 {feed.get('name')} · 업체 "
                            f"{len(books_of(quotes))}곳)",
                      source=str(feed.get("name")),
                      captured_at=datetime.now(timezone.utc),
                      used=said.get("used"), limit=said.get("limit_said"),
                      why=" · ".join(bad)), ""


async def _json(net, url: str, params: dict, *, state: RunState
                ) -> tuple[object | None, str, dict]:
    """🔴 피드 한 번 — `app.net` 으로만 간다(robots·UA·카세트). `(값, 사유, 머리말)`.

    ⚠️ 키는 로그에 안 남긴다. 🔴 머리말에 **남은 요청 수**가 온다(§2-2 · 실측
       2026-10-06: `x-requests-remaining: 499` · `x-requests-last: 1`).
    """
    ok, why = await net.allowed(url)
    if not ok:
        return None, f"robots 가 막았다 — {why}", {}
    got = await net.get(url, params=params)
    body = getattr(got, "text", "") or ""
    status = getattr(got, "status", 0)
    head = dict(getattr(got, "headers", {}) or {})
    if not body:
        return None, f"빈 응답(HTTP {status})", head
    try:
        return json.loads(body), "", head
    except json.JSONDecodeError:
        state.note(f"s2c JSON 이 아니다(HTTP {status}) — {body[:80]}")
        return None, f"JSON 이 아니다(HTTP {status})", head


def lines_from(probs: MarketProb, *, extra: list[BoardLine] | None = None
               ) -> list[BoardLine]:
    """🔴 §2-6 마지막 — 사용자 보드가 없으면 **피드가 준 마켓**이 평가 줄이 된다."""
    out: list[BoardLine] = []
    seen: set[str] = set()
    for q in probs.quotes:
        k = key_of(q.market, q.side, q.point)
        if k in seen:
            continue
        seen.add(k)
        out.append(BoardLine(market=q.market, side=q.side, point=q.point,
                             price=q.price))
    for ln in (extra or []):
        k = key_of(ln.market, ln.side, ln.point)
        if k not in seen:
            seen.add(k)
            out.append(ln)
    return out


def _last_cost(head: dict) -> int:
    """🔴 그 요청이 **크레딧 몇 개**를 썼나(`x-requests-last`). 모르면 1 로 본다.

    ⚠️ 실측 2026-10-06: `/v4/sports/{키}/events/` 는 **0** 이고
       `/v4/sports/{키}/events/{id}/odds/` 는 **1** 이었다(지역 1 · 마켓 1묶음).
    🔴 모를 때 0 으로 보면 한도를 **조용히 넘는다** — 그래서 1 로 본다.
    """
    try:
        return int(str(head.get("x-requests-last") or "1").strip())
    except ValueError:
        return 1


def _quota(head: dict) -> dict:
    """🔴 머리말 → 원장 칸(`remaining`·`limit_said`·`used`). 모르면 `None`."""
    out: dict[str, int | None] = {"remaining": None, "limit_said": None,
                                  "used": None}
    try:
        left = int(str(head.get("x-requests-remaining") or "").strip())
    except ValueError:
        return out
    out["remaining"] = left
    try:
        used = int(str(head.get("x-requests-used") or "").strip())
    except ValueError:
        return out
    out["used"] = used
    out["limit_said"] = used + left          # 🔴 피드가 말한 **한도**다(우리 추측 아님)
    return out
