#!/usr/bin/env python
"""[LE-1b] 역사 배당·결과 적재 — football-data.co.uk CSV → `history_*`.

🔴 **왜 필요한가.** 우리 DB 배당은 **한 달치뿐**이다(실측 2026-09-22:
   MLB 8/22~ · KBO·NPB 9/2~ · 축구 8/23~). walk-forward(LE-2)를 돌릴 길이가
   없다. 축구는 이 CSV 에 **4시즌 · 개별 북 8개 · 개장/마감**이 다 있다.

🔴 **`odds_snapshots` 에 넣지 않는다.** 그 표는 `games(id)` 를 참조하므로
   역사 경기를 넣으려면 `games` 를 오염시켜야 한다 — D32 가 겪은 사고다.

⚠️ **파일을 새로 받지 않는다**(기본). `soccer_elo.CSV_DIR` 의 캐시를 읽는다.
   `--download` 를 주면 `soccer_elo.download_csvs()` 를 부른다 — 다운로드
   코드를 여기서 다시 쓰지 않는다(사본 금지).
⚠️ 멱등이다. 두 번 돌려도 중복이 없다(`ON CONFLICT DO NOTHING`).

  python -m tools.backfill_history                 # 캐시에서 적재
  python -m tools.backfill_history --download      # 먼저 받고 적재
  python -m tools.backfill_history --markets h2h   # h2h 만
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_history")

SOURCE = "football-data.co.uk"

#: 🔴 북 이름 → (홈, 무, 원정) 컬럼. **개장가**다.
#   실측 헤더(2026-09-22 · `data/elo/csv/D1_2223.csv`)에서 그대로 옮겼다.
H2H_OPEN = {
    "B365": ("B365H", "B365D", "B365A"),
    "BW":   ("BWH", "BWD", "BWA"),
    "IW":   ("IWH", "IWD", "IWA"),
    "PS":   ("PSH", "PSD", "PSA"),        # 피나클
    "WH":   ("WHH", "WHD", "WHA"),
    "VC":   ("VCH", "VCD", "VCA"),
    "Max":  ("MaxH", "MaxD", "MaxA"),     # 최고가(북이 아니라 집계)
    "Avg":  ("AvgH", "AvgD", "AvgA"),     # 평균(북이 아니라 집계)
}
#: 같은 북의 **마감가**. 🔴 `C` 가 붙는다.
H2H_CLOSE = {
    "B365": ("B365CH", "B365CD", "B365CA"),
    "BW":   ("BWCH", "BWCD", "BWCA"),
    "IW":   ("IWCH", "IWCD", "IWCA"),
    "PS":   ("PSCH", "PSCD", "PSCA"),
    "WH":   ("WHCH", "WHCD", "WHCA"),
    "VC":   ("VCCH", "VCCD", "VCCA"),
    "Max":  ("MaxCH", "MaxCD", "MaxCA"),
    "Avg":  ("AvgCH", "AvgCD", "AvgCA"),
}
#: 총점 2.5 — (오버, 언더). `P` 는 피나클이다(h2h 의 `PS` 와 이름이 다르다).
TOT_OPEN = {
    "B365": ("B365>2.5", "B365<2.5"), "P": ("P>2.5", "P<2.5"),
    "Max": ("Max>2.5", "Max<2.5"),    "Avg": ("Avg>2.5", "Avg<2.5"),
}
TOT_CLOSE = {
    "B365": ("B365C>2.5", "B365C<2.5"), "P": ("PC>2.5", "PC<2.5"),
    "Max": ("MaxC>2.5", "MaxC<2.5"),    "Avg": ("AvgC>2.5", "AvgC<2.5"),
}
TOT_LINE = 2.5

_SIDES3 = ("home", "draw", "away")
_SIDES2 = ("over", "under")


def _f(row: dict, key: str):
    """숫자로 읽되 **빈 칸은 None**. 🔴 0 으로 채우지 않는다."""
    v = (row or {}).get(key)
    if v is None or str(v).strip() == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # 소수배당은 1 보다 크다. 그렇지 않으면 그 칸은 배당이 아니다.
    return f if f > 1.0 else None


def prices_of(row: dict, markets: tuple) -> list[tuple]:
    """한 경기 행 → `[(book, phase, market, line, side, odds)]`.

    ⚠️ **빈 칸은 행을 만들지 않는다.** 북마다 제공 범위가 다르다 —
       없는 값을 0 이나 평균으로 채우면 "이 북이 그 가격을 냈다"가 거짓이 된다.
    """
    out: list[tuple] = []
    if "h2h" in markets:
        for phase, table in (("open", H2H_OPEN), ("close", H2H_CLOSE)):
            for book, cols in table.items():
                for side, col in zip(_SIDES3, cols):
                    o = _f(row, col)
                    if o is not None:
                        out.append((book, phase, "h2h", None, side, o))
    if "totals" in markets:
        for phase, table in (("open", TOT_OPEN), ("close", TOT_CLOSE)):
            for book, cols in table.items():
                for side, col in zip(_SIDES2, cols):
                    o = _f(row, col)
                    if o is not None:
                        out.append((book, phase, "totals", TOT_LINE, side, o))
    return out


def _int(row: dict, key: str):
    try:
        return int(str((row or {}).get(key) or "").strip())
    except (TypeError, ValueError):
        return None


def read_file(path, season_hint: str | None, markets: tuple) -> list[dict]:
    """CSV 한 파일 → 경기 목록. 🔴 파싱을 `soccer_elo._parse_csv` 와 공유하지
    않는다 — 그쪽은 Elo 용이라 **북별 배당을 버린다**(확률 하나만 남긴다).
    고치면 Elo 가 깨진다."""
    from app.models.soccer_elo import _parse_date

    out: list[dict] = []
    with open(path, encoding="latin-1", newline="") as f:
        for row in csv.DictReader(f):
            home = (row.get("HomeTeam") or row.get("Home") or "").strip()
            away = (row.get("AwayTeam") or row.get("Away") or "").strip()
            d = _parse_date(row.get("Date", ""))
            if not home or not away or d is None:
                continue
            out.append({
                "div": (row.get("Div") or "").strip() or None,
                "season": season_hint or ((row.get("Season") or "").strip() or None),
                "date": d.date(), "home": home, "away": away,
                "fthg": _int(row, "FTHG"), "ftag": _int(row, "FTAG"),
                "ftr": (row.get("FTR") or row.get("Res") or "").strip() or None,
                "prices": prices_of(row, markets),
            })
    return out


def csv_files() -> list[tuple]:
    """`[(경로, 시즌힌트, 기본div)]`. 🔴 목록의 원본은 `soccer_elo` 다."""
    from app.models.soccer_elo import (CSV_DIR, EXTRA_LEAGUES, MAIN_LEAGUES,
                                       MAIN_SEASONS)

    out = []
    for code in MAIN_LEAGUES:
        for season in MAIN_SEASONS:
            p = CSV_DIR / f"{code}_{season}.csv"
            if p.exists():
                out.append((p, season, code))
    for code in EXTRA_LEAGUES:
        p = CSV_DIR / f"{code}.csv"
        if p.exists():
            out.append((p, None, code))
    return out


_M_INS = """
    INSERT INTO history_matches
      (source, div, season, match_date, home, away, fthg, ftag, ftr)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
    ON CONFLICT (source, div, season, match_date, home, away) DO NOTHING
    RETURNING id
"""
_M_GET = """
    SELECT id FROM history_matches
     WHERE source=$1 AND div=$2 AND season IS NOT DISTINCT FROM $3
       AND match_date=$4 AND home=$5 AND away=$6
"""
_P_INS = """
    INSERT INTO history_prices (match_id, book, phase, market, line, side, odds)
    VALUES ($1,$2,$3,$4,$5,$6,$7)
    ON CONFLICT (match_id, book, phase, market, line, side) DO NOTHING
"""


async def load(pool, *, markets: tuple = ("h2h", "totals")) -> dict:
    """캐시된 CSV 전부를 적재. 반환: 소스·리그·시즌별 건수."""
    files = csv_files()
    if not files:
        logger.warning("[history] 캐시가 비어 있다 — `--download` 로 먼저 받아라")
        return {"files": 0}
    out = {"files": len(files), "matches": 0, "prices": 0, "skipped": 0,
           "by_div": {}}
    async with pool.acquire() as conn:
        for path, season, code in files:
            rows = read_file(path, season, markets)
            key = f"{code}/{season or '-'}"
            got = {"matches": 0, "prices": 0}
            for r in rows:
                div = r["div"] or code
                mid = await conn.fetchval(
                    _M_INS, SOURCE, div, r["season"], r["date"], r["home"],
                    r["away"], r["fthg"], r["ftag"], r["ftr"])
                if mid is None:          # 이미 있다 — 멱등
                    mid = await conn.fetchval(
                        _M_GET, SOURCE, div, r["season"], r["date"],
                        r["home"], r["away"])
                if mid is None:
                    out["skipped"] += 1
                    continue
                got["matches"] += 1
                for bk, ph, mk, ln, sd, od in r["prices"]:
                    await conn.execute(_P_INS, mid, bk, ph, mk, ln, sd, od)
                    got["prices"] += 1
            out["by_div"][key] = got
            out["matches"] += got["matches"]
            out["prices"] += got["prices"]
            logger.info("[history] %-12s 경기 %5d · 가격 %7d",
                        key, got["matches"], got["prices"])
    return out


async def report(pool) -> None:
    """완료 조건 표 — 소스·기간·행 수 · **개장/마감 둘 다 있는 경기**."""
    print(f"\n{'='*74}\n역사 적재 결과\n{'='*74}")
    for r in await pool.fetch("""
        SELECT m.div, m.season, count(*) matches,
               min(m.match_date) d0, max(m.match_date) d1
          FROM history_matches m GROUP BY 1,2 ORDER BY 1,2"""):
        print(f"  {r['div']:5s} {str(r['season'] or '-'):6s} "
              f"경기 {r['matches']:5d}  {r['d0']} ~ {r['d1']}")
    print("\n[북별 가격 행 수]")
    for r in await pool.fetch("""
        SELECT book, phase, market, count(*) n FROM history_prices
         GROUP BY 1,2,3 ORDER BY market, book, phase"""):
        print(f"  {r['market']:7s} {r['book']:5s} {r['phase']:5s} {r['n']:8d}")
    print("\n[🔴 개장·마감이 둘 다 있는 경기 — LE-4 가 쓸 표본]")
    for r in await pool.fetch("""
        SELECT p.book, count(DISTINCT p.match_id) n FROM history_prices p
         WHERE p.market='h2h' AND p.side='home'
         GROUP BY p.book HAVING count(DISTINCT p.match_id) > 0
         ORDER BY n DESC"""):
        print(f"  {r['book']:5s} {r['n']:6d}")
    got = await pool.fetchrow("""
        SELECT count(*) n FROM (
          SELECT match_id FROM history_prices
           WHERE market='h2h' AND side='home'
           GROUP BY match_id
          HAVING bool_or(phase='open') AND bool_or(phase='close')) t""")
    print(f"\n  🔴 개장+마감 둘 다: **{got['n']}경기**")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true",
                    help="soccer_elo.download_csvs() 로 먼저 받는다")
    ap.add_argument("--markets", default="h2h,totals")
    a = ap.parse_args()

    if a.download:
        # 🔴 다운로드 코드를 여기서 다시 쓰지 않는다 — 원본은 soccer_elo 다.
        from app.models.soccer_elo import download_csvs

        logger.info("[history] 받은 파일 %d개", download_csvs())

    from app.db import get_pool

    pool = await get_pool()
    got = await load(pool, markets=tuple(
        x.strip() for x in a.markets.split(",") if x.strip()))
    print(f"\n적재: 파일 {got.get('files')} · 경기 {got.get('matches')} · "
          f"가격 {got.get('prices')} · 건너뜀 {got.get('skipped')}")
    await report(pool)
    print("\n⚠️ 이 표에는 **마감 배당과 결과**가 들어 있다 — 정답지다.")
    print("   `phase='close'`·`ftr`·`fthg`·`ftag` 는 학습 입력이 될 수 없다(LE-2).")
    print("⚠️ 야구 역사 배당 무료 소스는 **찾지 못했다.** 야구는 실시간 축적분만이다.")


if __name__ == "__main__":
    asyncio.run(main())
