"""🔴🔴 **보드 수집 사다리**(의심 검증 통합본 v2 · 2026-10-14i §1).

> 보드는 **봇이 직접 가져온다** · 보드 없는 경기는 없다.
> ① 사용자 캡처 ② 국내/공개 배당 페이지 ③ 배당 API(the_odds_api) ④ 비교 사이트
> ①~④ 전부 실패 = **수집 실패 경보**(정상 상태가 아니다).

🔴 **로그인·우회·약관 위반 수집은 하지 않는다**(절대규칙 3).
🔴 줄마다 **출처 · 수집 시각 · 북메이커**를 붙인다(§1-1 마지막 줄).
🔴 국내 보드 구조로 **한 줄씩** 고른다(§1-2) — 승무패 그대로 · 핸디 기준선 하나 ·
   언오버 기준선 하나 · 추가 옵션은 후보로 표시.
⚠️ 아시안 **쿼터 라인**(±0.25·±0.75·±1.25)은 국내 보드에 없다 → **옮기지 않고**
   `국내 미대응` 으로 적는다(§1-2).
⚠️ ② 는 실측으로 `football-data.co.uk/fixtures.csv` 다 — robots 가 **전면 허용**
   이고(`Disallow:` 비었다 · 실측 2026-10-14) 승무패·**AHh**·O/U 2.5 를 준다.
   🔴 그 파일은 **유럽 리그 주간분**만 든다(그날 코드 예: E1·E2·SC1) — 없는 대회는
   ③ 으로 내려가고, 거기도 없으면 **경보**다.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FIXTURES = "https://www.football-data.co.uk/fixtures.csv"
#: 🔴 국내 보드에 있는 핸디 단위(0.5 刻) — 쿼터 라인은 여기 없다
DOMESTIC_STEP = 0.5
#: 🔴 언오버 기준선 — 국내 보드에서 흔한 값
TOTAL_LINES = (1.5, 2.5, 3.5)


@dataclass
class Row:
    """🔴 보드 한 줄 — 어느 마켓 · 기준선 · 배당 · 어디서 · 언제."""

    market: str = ""          # win · handicap · total
    side: str = ""            # home·draw·away · over·under
    point: float | None = None
    price: float | None = None
    source: str = ""          # 캡처 · football-data · the_odds_api …
    book: str = ""
    at: str = ""
    note: str = ""            # 국내 미대응 · 추가 옵션 후보 …

    def name(self) -> str:
        """🔴 칠 표가 쓰는 줄 이름(`core/picks` 와 같은 꼴)."""
        if self.market == "win":
            return {"home": "홈 승", "draw": "무", "away": "원정 승"}.get(
                self.side, "")
        if self.market == "handicap" and self.point is not None:
            got = f"핸디 {self.side}{self.point:+g}"
            return (f"{got} 승" if float(self.point).is_integer() else got)
        if self.market == "total" and self.point is not None:
            return f"{'오버' if self.side == 'over' else '언더'} {self.point:g}"
        return ""


@dataclass
class Board:
    rows: list = field(default_factory=list)
    source: str = ""
    why: str = ""
    extra: list = field(default_factory=list)
    alarm: str = ""

    def names(self) -> list[str]:
        out = []
        for r in self.rows:
            got = r.name()
            if got and got not in out:
                out.append(got)
            # 🔴 정수 기준선은 **승·무·패 세 갈래**(§1-2)
            if (r.market == "handicap" and r.point is not None
                    and float(r.point).is_integer()):
                said = f"핸디 {r.side}{r.point:+g} 무"
                if said not in out:
                    out.append(said)
        return out


def domestic(point: float) -> bool:
    """🔴 그 기준선이 **국내 보드 단위**인가(0.5 刻 · 쿼터 라인은 아니다)."""
    got = round(float(point) / DOMESTIC_STEP, 6)
    return abs(got - round(got)) < 1e-9


# ══════════════════════════════════════════════════════════════════
# ① 사용자 캡처
# ══════════════════════════════════════════════════════════════════

def from_capture(name: str) -> Board | None:
    """🔴 `var/board/<날짜>.yaml` — 들어오면 **최우선**(아래를 덮는다)."""
    import yaml

    from app.core import board as _bd
    from app.core import teamname as _tn
    box = ROOT / "var/board"
    for path in sorted(box.glob("*.yaml"), reverse=True) if box.is_dir() else []:
        got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        said = None
        if name in got:
            said = str(got[name])
        else:
            for key, val in got.items():
                if _tn.share(str(key), name) >= 0.5:
                    said = str(val)
                    break
        if said is None:
            continue
        parsed, extra, bad = _bd.parse(said)
        rows = []
        for one in (parsed.lines or []):
            rows.append(Row(market=str(one.market), side=str(one.side or ""),
                            point=one.point, price=one.price,
                            source="① 사용자 캡처", book="국내 보드",
                            at=path.stem))
        if rows:
            return Board(rows=rows, source="① 사용자 캡처", extra=list(extra),
                         why=(f"캡처 `{path.name}` · 줄 {len(rows)}개"
                              + (f" · 못 읽은 조각 {len(bad)}" if bad else "")))
    return None


# ══════════════════════════════════════════════════════════════════
# ② 공개 배당 페이지 — football-data.co.uk 주간 일정
# ══════════════════════════════════════════════════════════════════

async def fixtures_rows(net) -> tuple[list[dict], str]:
    """🔴 그 주 경기의 공개 배당(승무패 · AHh · O/U 2.5). robots 전면 허용."""
    got = await net.get(FIXTURES)
    text = getattr(got, "text", "") or ""
    if not text:
        return [], f"🔴 `fixtures.csv` 를 못 받았다({getattr(got, 'reason', '')})"
    rows = list(csv.DictReader(io.StringIO(text)))
    return rows, f"`fixtures.csv` {len(rows)}줄"


def from_fixtures(name: str, rows: list[dict]) -> Board | None:
    """🔴 이름으로 그 경기를 찾아 **국내 보드 한 줄**을 만든다."""
    from app.core import teamname as _tn
    want = [x.strip() for x in str(name).replace("–", "vs").split("vs")
            if x.strip()]
    if len(want) < 2:
        return None
    best, score = None, 0.0
    for r in rows:
        got = (_tn.share(str(r.get("HomeTeam") or ""), want[0])
               + _tn.share(str(r.get("AwayTeam") or ""), want[1])) / 2
        if got > score:
            best, score = r, got
    if not best or score < 0.75:
        return None
    at = datetime.now(timezone.utc).isoformat(timespec="minutes")
    out: list[Row] = []
    extra: list[str] = []
    for side, col in (("home", "B365H"), ("draw", "B365D"), ("away", "B365A")):
        price = _num(best.get(col))
        if price:
            out.append(Row(market="win", side=side, price=price,
                           source="② football-data(공개)", book="B365", at=at))
    got_h = _num(best.get("AHh"))
    if got_h is not None:
        ok = domestic(got_h)
        for side, col in (("home", "B365AHH"), ("away", "B365AHA")):
            price = _num(best.get(col))
            point = got_h if side == "home" else -got_h
            out.append(Row(market="handicap", side=side, point=point,
                           price=price, source="② football-data(공개)",
                           book="B365", at=at,
                           note="" if ok else "🔴 국내 미대응(아시안 쿼터)"))
        if not ok:
            extra.append(f"AHh {got_h:+g} — 국내 미대응(쿼터 라인)")
    for side, col in (("over", "B365>2.5"), ("under", "B365<2.5")):
        price = _num(best.get(col))
        if price:
            out.append(Row(market="total", side=side, point=2.5, price=price,
                           source="② football-data(공개)", book="B365", at=at))
    if not out:
        return None
    return Board(rows=out, source="② football-data(공개)", extra=extra,
                 why=(f"`fixtures.csv` 의 {best.get('HomeTeam')} vs "
                      f"{best.get('AwayTeam')}(이름 맞춤 {score:.2f})"))


def _num(said: object) -> float | None:
    try:
        got = float(str(said).strip())
    except (TypeError, ValueError):
        return None
    return got if got else None


# ══════════════════════════════════════════════════════════════════
# ③ 배당 API — 이미 쓰는 피드(MarketProb 의 원 배당)
# ══════════════════════════════════════════════════════════════════

def from_feed(market) -> Board | None:
    """🔴 ③ — `layer4` 가 받은 피드(h2h·spreads·totals)를 보드 꼴로."""
    quotes = list(getattr(market, "quotes", None) or [])
    if not quotes:
        return None
    at = datetime.now(timezone.utc).isoformat(timespec="minutes")
    rows: list[Row] = []
    for q in quotes:
        market_name = str(getattr(q, "market", "") or "")
        side = str(getattr(q, "side", "") or "")
        point = getattr(q, "point", None)
        rows.append(Row(market=market_name, side=side, point=point,
                        price=float(getattr(q, "price", 0.0) or 0.0),
                        source="③ 배당 API", at=at,
                        book=str(getattr(q, "bookmaker", "") or ""),
                        note=("" if point is None or domestic(point)
                              else "🔴 국내 미대응(아시안 쿼터)")))
    return Board(rows=rows, source="③ 배당 API",
                 why=f"피드 줄 {len(rows)}개 · 업체 "
                     f"{len({r.book for r in rows if r.book})}곳")


# ══════════════════════════════════════════════════════════════════
# 사다리 + 국내 한 줄 고르기
# ══════════════════════════════════════════════════════════════════

def main_line(rows: list[Row], market: str) -> list[Row]:
    """🔴🔴 §1-2 — **메인 기준선 하나**(양쪽 배당이 가장 비슷한 기준선).

    🔴 여러 업체면 **가장 많이 쓰는 기준선**을 먼저 고른다.
    ⚠️ 국내 미대응(쿼터)은 **고르지 않는다** — 표시로만 남는다.
    """
    want = [r for r in rows if r.market == market and r.point is not None
            and domestic(r.point)]
    if not want:
        return []
    by: dict[float, list[Row]] = {}
    for r in want:
        by.setdefault(abs(float(r.point)), []).append(r)
    def gap(point: float) -> tuple:
        got = by[point]
        prices = [r.price for r in got if r.price]
        spread = (abs(max(prices) - min(prices)) if len(prices) >= 2
                  else 9.9)
        # 🔴 업체 수가 많은 기준선 먼저 · 그다음 두 배당 차가 작은 기준선
        return (-len({r.book for r in got}), spread)
    best = min(by, key=gap)
    return by[best]


def pick_domestic(board: Board) -> Board:
    """🔴 §1-2 — 국내 보드 구조(승무패 + 핸디 하나 + 언오버 하나)로 좁힌다."""
    rows = list(board.rows)
    out = [r for r in rows if r.market in ("win", "draw")]
    out += main_line(rows, "handicap")
    said_total = main_line(rows, "total")
    if said_total:
        got = {abs(float(r.point or 0)) for r in said_total}
        keep = min(got, key=lambda x: min(abs(x - y) for y in TOTAL_LINES))
        out += [r for r in said_total if abs(float(r.point or 0)) == keep]
    extra = list(board.extra)
    for r in rows:
        if r not in out and r.point is not None:
            extra.append(f"추가 옵션 후보 — {r.name() or r.market} "
                         f"{r.point:+g}" + (f" {r.note}" if r.note else ""))
    return Board(rows=out, source=board.source, why=board.why,
                 extra=extra, alarm=board.alarm)


async def of(name: str, *, net=None, market=None,
             fixtures: list[dict] | None = None) -> Board:
    """🔴🔴 **사다리 전체** — ① → ② → ③ → ④. 전부 실패면 **경보**다(§1-3)."""
    got = from_capture(name)
    if got:
        return pick_domestic(got)
    if fixtures is None and net is not None:
        fixtures, _why = await fixtures_rows(net)
    if fixtures:
        got = from_fixtures(name, fixtures)
        if got:
            return pick_domestic(got)
    if market is not None:
        got = from_feed(market)
        if got and got.rows:
            return pick_domestic(got)
    return Board(rows=[], source="", why="",
                 alarm=("🔴🔴 **보드 수집 실패** — ① 캡처 없음 · "
                        "② 공개 페이지(football-data)에 그 경기가 없다 · "
                        "③ 배당 API 매칭 실패 · ④ 통로 없음"))


def said_of(board: Board) -> str:
    """🔴 카드 맨 위 **보드 블록**(§7) — 줄마다 기준선·배당·출처·시각."""
    if board.alarm:
        return board.alarm
    rows = []
    for r in board.rows:
        rows.append(f"    {r.name() or r.market} "
                    + (f"{r.point:+g} " if r.point is not None else "")
                    + (f"배당 **{r.price:g}**" if r.price else "배당 ⬜")
                    + f" · {r.source}"
                    + (f"({r.book})" if r.book else "")
                    + (f" · {r.at}" if r.at else "")
                    + (f" · {r.note}" if r.note else ""))
    said = [f"📋 **보드**({board.source}) — {board.why}"]
    said += rows
    if board.extra:
        said.append("    ⚠️ " + " · ".join(str(x) for x in board.extra[:4]))
    return "\n".join(said)
