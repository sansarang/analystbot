"""[AUD-1 / deepsearch_addendum DS-3a 3] 검색 공급자 오디션 — **표만 낸다.**

    python -m tools.search_audition [--out docs/SEARCH_AUDITION_<날짜>.md] [--dry]

🔴 **자동 채택 금지**(지시문). 이 도구는 설정을 건드리지 않는다. 사용자가 표를
   보고 고른다. 계약이 이 방향을 잠근다.

🔴 **1순위 지표를 지시문에서 바꿨다 — 실측이 그렇게 하게 했다.**
   지시문 DS-3a 4 는 "당일 기사 회수율"을 1순위로 둔다. 그런데 실측
   2026-09-21 (Bing, 같은 시각):
     川崎フロンターレ        11항목/8최근 → 최신 「감독 교체책 반성」(쓸모없음)
     川崎フロンターレ スタメン  5항목/2최근 → 최신 「スタメン発表」(찾던 것)
     한화 이글스 12/8  ·  한화 이글스 선발 12/**10**  ← 좁혔는데 최근이 늘었다
   회수율을 1순위로 두면 **쓸모없는 기사를 많이 받는 쪽이 이긴다.**
   → 1순위는 `verified`(검증 통과 사실 수)다.
   ⚠️ 회수 수는 **버리지 않고 함께 싣는다** — 둘을 나란히 봐야 이 뒤집힘이 보인다.

⚠️ **경기 전 시점만** 쓴다. 과거 경기로 돌리면 경기 후 기사가 섞여 회수율이
   좋아 보인다(지시문 경고).
⚠️ 새로 만드는 것은 **표와 정렬뿐**이다. 질의는 `search_terms.yaml`,
   공급자는 `deepsearch.search`, 검증은 `situation`, 요청은 DS-1 런타임,
   도메인 등급은 `scout_config.rank` 가 원본이다(사본 금지).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import pathlib
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
logger = logging.getLogger(__name__)

#: 🔴 무엇으로 줄 세우나. 근거는 위 docstring 의 실측이다.
PRIMARY_METRIC = "verified"


@dataclass
class Row:
    provider: str
    league: str
    market: str
    query: str
    got: int = 0
    fresh: int = 0
    verified: int = 0
    dropped: dict = field(default_factory=dict)
    ms: float = 0.0
    cost_usd: float = 0.0
    whitelisted: int = 0
    window_ok: bool = True
    note: str = ""


def rank_rows(rows) -> list:
    """🔴 `verified` 우선. 같으면 화이트리스트 비율, 그다음 빠른 쪽."""
    return sorted(rows or [],
                  key=lambda r: (-r.verified, -r.whitelisted, r.ms))


def _pct(n, d) -> str:
    return "대상없음" if not d else f"{n / d * 100:.0f}%"


def summarize(rows) -> list:
    """공급자별 합계. ⚠️ 표본이 얇으면 **얇다고 적는다** — 얇은 표본으로
    공급자를 고르는 것이 이 프로젝트에서 가장 비싼 실수다."""
    by: dict = {}
    for r in rows or []:
        b = by.setdefault(r.provider, {"provider": r.provider, "n": 0, "got": 0,
                                       "fresh": 0, "verified": 0, "cost": 0.0,
                                       "ms": [], "white": 0, "dropped": {}})
        b["n"] += 1
        b["got"] += r.got
        b["fresh"] += r.fresh
        b["verified"] += r.verified
        b["cost"] += r.cost_usd
        b["white"] += r.whitelisted
        b["ms"].append(r.ms)
        for k, v in (r.dropped or {}).items():
            b["dropped"][k] = b["dropped"].get(k, 0) + v
    out = []
    for b in by.values():
        b["median_ms"] = round(statistics.median(b["ms"]), 0) if b["ms"] else None
        b["thin"] = b["n"] < 10
        out.append(b)
    return sorted(out, key=lambda b: -b["verified"])


def write_report(rows, out_path, *, date_kst: str) -> pathlib.Path:
    p = pathlib.Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    L = [f"# 검색 공급자 오디션 — {date_kst}", "",
         "🔴 **표만 낸다. 채택은 사용자가 한다**(지시문 DS-3a 3 자동 채택 금지).",
         "",
         "🔴 **1순위 지표는 `검증 통과`다 — 회수 수가 아니다.**",
         "   지시문 원문은 '당일 기사 회수율'이었으나 실측이 뒤집었다:",
         "   `川崎フロンターレ` 11항목/8최근 → 최신이 「감독 교체책 반성」(쓸모없음)",
         "   `川崎フロンターレ スタメン` 5항목/2최근 → 최신이 「スタメン発表」(찾던 것).",
         "   회수율로 고르면 **쓸모없는 기사를 많이 받는 쪽이 이긴다.**",
         "   ⚠️ 회수 수도 함께 싣는다 — 둘을 나란히 봐야 이 뒤집힘이 보인다.", "",
         "## 1. 공급자별 합계", "",
         "| 공급자 | 질의 | 받음 | 당일 | **검증통과** | 화이트리스트 | 중앙 ms | 비용 | 표본 |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for b in summarize(rows):
        L.append(f"| {b['provider']} | {b['n']} | {b['got']} | {b['fresh']} | "
                 f"**{b['verified']}** | {_pct(b['white'], b['got'])} | "
                 f"{b['median_ms']} | ${b['cost']:.4f} | "
                 f"{'🔴 얇다' if b['thin'] else 'ok'} |")
    _out = [r for r in (rows or []) if not r.window_ok]
    if _out:
        L += ["", f"🔴 **창 밖 질의 {len(_out)}건** — 검증통과가 구조적으로 0 이다.",
              "   창은 `[경기시작 − 24h, 경기시작)` 이고 그 전에는 아직 열리지 않는다.",
              "   **창 밖이라 0** 과 **회수 실패로 0** 을 섞어 읽지 마라.", "",
              "| 공급자 | 질의 | 사유 |", "|---|---|---|"]
        for r in _out[:10]:
            L.append(f"| {r.provider} | `{r.query}` | {r.note} |")
    _note = [r for r in (rows or []) if r.note and r.window_ok]
    if _note:
        L += ["", "⚠️ **못 잰 것** — 빈손과 다르다.", "",
              "| 공급자 | 질의 | 사유 |", "|---|---|---|"]
        for r in _note[:10]:
            L.append(f"| {r.provider} | `{r.query}` | {r.note} |")
    L += ["", "## 2. 폐기 사유 분포", "",
          "⚠️ 왜 버렸는지 모르면 **회수율이 좋아 보이는 쪽**을 고르게 된다.", ""]
    for b in summarize(rows):
        L.append(f"- `{b['provider']}` — {b['dropped'] or '없음'}")
    L += ["", "## 3. 질의별 (검증 통과 순)", "",
          "| 공급자 | 리그 | 시장 | 질의 | 받음 | 당일 | 검증 | 폐기 | ms |",
          "|---|---|---|---|---:|---:|---:|---|---:|"]
    for r in rank_rows(rows):
        L.append(f"| {r.provider} | {r.league} | {r.market} | `{r.query}` | "
                 f"{r.got} | {r.fresh} | **{r.verified}** | {r.dropped or '—'} | "
                 f"{r.ms:.0f} |")
    L += ["", "## 4. 읽는 법", "",
          "- **3일 이상** 돌린 표를 보고 고른다(지시문). 하루치로 고르지 않는다.",
          "- `표본 🔴 얇다` 가 붙은 줄은 질의가 10건 미만이다 — 믿지 마라.",
          "- 키가 없는 유료 공급자는 **표에 없다**. 빈칸이 아니라 부재다.", ""]
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    return p


async def _measure(provider, *, league, market, query, sport, starts_at) -> Row:
    """🔴 **창 밖에서 돌리면 검증통과가 구조적으로 0 이다.**

    `situation.published_before` 의 창은 `[경기시작 − window_hours, 경기시작)`
    이다. 오디션을 T-24h 보다 일찍 돌리면 아직 그 창이 열리지 않았으므로
    모든 기사가 `out_of_window` 로 떨어진다 — 실측 2026-09-21 16:15:
    받음 70 · out_of_window 59 · 검증통과 0.
    지시문은 "경기 전 시점에 돌린다"고 했는데 **정확히는 창 안**이다.
    → 창 밖이면 `window_ok=False` 로 표시한다. "창 밖이라 0"과 "회수 실패로
      0"은 다른 말이고, 섞으면 공급자를 잘못 고른다.
    """
    import time
    from datetime import timedelta

    from app.deepsearch import search as S
    from app.engine.scout_config import RANK_UNLISTED, rank
    from app.engine.situation import window_hours

    now_ = datetime.now(KST)
    win_open = (starts_at - timedelta(hours=window_hours(sport))
                if starts_at else None)
    in_window = bool(win_open and win_open <= now_ < starts_at)

    t0 = time.monotonic()
    try:
        hits = await provider.search(query=query, market=market, max_results=20)
    except Exception as exc:
        return Row(provider=provider.name, league=league, market=market,
                   query=query, note=f"실패: {str(exc)[:60]}")
    ms = (time.monotonic() - t0) * 1000
    now = datetime.now(KST)
    fresh = sum(1 for h in hits if h.published_at
                and (now - h.published_at).total_seconds() <= 86400)
    ok, dropped = S.verify(hits, sport=sport, starts_at=starts_at)
    why: dict = {}
    for d in dropped:
        why[d["reason"]] = why.get(d["reason"], 0) + 1
    white = sum(1 for h in hits
                if rank(h.url or "", league) < RANK_UNLISTED)
    return Row(provider=provider.name, league=league, market=market, query=query,
               got=len(hits), fresh=fresh, verified=len(ok), dropped=why,
               ms=ms, cost_usd=0.0, whitelisted=white, window_ok=in_window,
               # ⚠️ DB 는 UTC 저장, **표시만 KST**(절대 규칙 4). 안 바꾸면
               #    "열림 09:30 · 지금 16:15" 처럼 보여 창 밖인 이유가 거꾸로 읽힌다.
               note="" if in_window else
               f"창 밖(열림 {win_open.astimezone(KST):%m-%d %H:%M} KST · "
               f"시작 {starts_at.astimezone(KST):%m-%d %H:%M} KST · "
               f"지금 {now_:%m-%d %H:%M} KST)")


async def run(*, out=None, dry=False, limit_games=6) -> list:
    """오늘 슬레이트의 **경기 전** 경기로 돈다.

    🔴 과거 경기로 돌리지 않는다 — 경기 후 기사가 섞여 회수율이 좋아 보인다.
    """
    from app.collectors.news_rss import QUERY_ALIAS
    from app.db import close_pool, get_pool
    from app.deepsearch import search as S
    from app.engine.scout_config import SEARCH_TERMS, local_name, queries

    now = datetime.now(KST)
    pool = await get_pool()
    try:
        games = await pool.fetch(
            "SELECT sport, league, home, away, starts_at FROM games "
            "WHERE starts_at > now() ORDER BY starts_at LIMIT $1", limit_games)
    finally:
        await close_pool()
    if not games:
        logger.warning("[audition] **경기 전** 경기가 없다 — 표를 내지 않는다")
        return []

    names = S.active_names()
    logger.info("[audition] 공급자 %s · 경기 %d개", names, len(games))
    rows: list[Row] = []
    for g in games:
        lg = (g["league"] or "").lower()
        if not (SEARCH_TERMS.get(lg) or {}).get("pre"):
            logger.info("[audition] %s — 질의 없음(search_terms 에 리그가 없다)", lg)
            continue
        mkt = {"kbo": "ko-KR", "npb": "ja-JP", "mlb": "en-US"}.get(
            (g["sport"] or "").lower(), "ko-KR")
        # 🔴 **현지 표기로 바꾼다.** DB 이름은 영문이고 기사는 `한화 이글스`·
        #    `中日ドラゴンズ` 로 쓴다. 안 바꾸면 `Hanwha Eagles 내일의 선발투수`
        #    같은 질의가 나가고 회수가 0 이 된다(실측 2026-09-21 — 이 도구가
        #    첫 실행에서 그 상태였다).
        #    원본은 `news_rss.QUERY_ALIAS`(한/일) 와 `scout_config.local_name`
        #    (축구) 다. 여기서 표를 만들지 않는다(사본 금지).
        def _local(name: str) -> str:
            return QUERY_ALIAS.get(name) or local_name(lg, name)

        # 🔴 치환도 **`scout_config.queries` 가 원본**이다 — 자리표시자를 못
        #    채우면 그 줄을 빼는 규칙이 거기 있다. 여기서 다시 짜지 않는다.
        qs = queries(lg, _local(g["home"] or ""), "pre",
                     home=_local(g["home"] or ""), away=_local(g["away"] or ""))
        for q in qs[:2]:
            for n in names:
                p = S.build(n)
                if p is None:
                    continue
                if dry:
                    rows.append(Row(provider=n, league=lg, market=mkt, query=q,
                                    note="dry"))
                    continue
                if n == "media_rss" and not getattr(p, "_feeds", None):
                    # ⚠️ 빈손과 **미설정**은 다르다. 섞으면 "media_rss 는
                    #    쓸모없다"는 틀린 결론이 나온다.
                    rows.append(Row(provider=n, league=lg, market=mkt, query=q,
                                    note="피드 미설정(config 의 feeds 가 비었다)"))
                    continue
                rows.append(await _measure(
                    p, league=lg, market=mkt, query=q,
                    sport=(g["sport"] or "").lower(),
                    starts_at=g["starts_at"]))
    if out:
        path = write_report(rows, out, date_kst=now.strftime("%Y-%m-%d"))
        logger.info("[audition] 표: %s", path)
    return rows


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    d = datetime.now(KST).strftime("%Y-%m-%d")
    ap.add_argument("--out", default=f"docs/SEARCH_AUDITION_{d}.md")
    ap.add_argument("--dry", action="store_true",
                    help="요청을 보내지 않고 무엇을 물을지만 본다")
    ap.add_argument("--games", type=int, default=6)
    a = ap.parse_args()
    rows = asyncio.run(run(out=a.out, dry=a.dry, limit_games=a.games))
    print(f"질의 {len(rows)}건 · 표 {a.out}")


if __name__ == "__main__":
    main()
