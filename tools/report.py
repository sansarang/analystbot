"""[RPT-1] 원장 성적표 — 축별·판정자별. 🔴 **사람이 부른다**(09-17 지시).

🔴 **계수기 규율**(09-08): 세기 전에 그 계수기가 무엇을 세는지 확인한다.
   `hit` 은 True·False·None(미채점) 셋이고 `void`(우천취소 등)가 따로 있다.
   적중률의 분모는 `hit IS NOT NULL AND NOT void` 이고, **뺀 것을 같은 줄에
   찍는다.** 찍지 않으면 그 숫자는 검증할 수 없다.
🔴 표본이 0이면 비율을 **지어내지 않는다** — "표본 0"이라고 적는다.
   조용히 끝내면 "성적이 없다"와 "도구가 안 돌았다"가 구분되지 않는다.
⚠️ 읽기만 한다. 원장을 고치지 않고 판정 경로를 부르지 않는다.
⚠️ 성적을 판정에 되먹이지 않는다 — `tests/test_pick_ledger.py` 가 그 경로를
   잠그고 있다. 이 도구는 사람이 읽는 표를 낼 뿐이다.

사용:
  tools/report.py --since 2026-09-15 --by judge_by
  tools/report.py --since 2026-09-01 --by main_axis --sport mlb
"""
from __future__ import annotations

import argparse
import asyncio
import sys

#: `--by` 로 쓸 수 있는 컬럼. 🔴 **화이트리스트다** — 컬럼명이 SQL 에 들어가므로
#  임의 문자열을 받지 않는다.
BY_COLUMNS = ("judge_by", "main_axis", "counter_axis", "market", "sport",
              "league", "gate_label", "confidence", "flow_class")


def check_by(by: str) -> str:
    if by not in BY_COLUMNS:
        raise SystemExit(f"🔴 모르는 축: {by} (가능: {', '.join(BY_COLUMNS)})")
    return by


def summarize(rows: list[dict]) -> dict:
    """행 목록 → `{축값: 집계}`.

    🔴 분모가 둘이다 — 적중률은 `graded`, CLV 는 `clv_n`. 한 줄에 섞지 않는다.
    """
    out: dict = {}
    for r in rows:
        k = r.get("k")
        k = "(없음)" if k in (None, "") else str(k)
        d = out.setdefault(k, {"n": 0, "graded": 0, "hit": 0, "ungraded": 0,
                               "void": 0, "clv_n": 0, "_clv_sum": 0.0})
        d["n"] += 1
        if r.get("void"):
            d["void"] += 1
        elif r.get("hit") is None:
            d["ungraded"] += 1
        else:
            d["graded"] += 1
            if r["hit"]:
                d["hit"] += 1
        if r.get("clv") is not None:
            d["clv_n"] += 1
            d["_clv_sum"] += float(r["clv"])
    for d in out.values():
        d["rate"] = (d["hit"] / d["graded"]) if d["graded"] else None
        d["clv_avg"] = (d["_clv_sum"] / d["clv_n"]) if d["clv_n"] else None
        d.pop("_clv_sum")
    return out


def render(agg: dict, *, by: str) -> str:
    """사람이 읽는 표. 🔴 표본 0 은 **그렇게 적는다.**"""
    head = (f"{by:<16} {'건수':>5} {'채점':>5} {'적중':>5} {'적중률':>8}"
            f" {'CLV건':>6} {'평균CLV':>9}   비고")
    lines = [head, "-" * len(head)]
    if not agg:
        lines.append("(행이 없다) — 표본 0")
        return "\n".join(lines)
    for k in sorted(agg):
        d = agg[k]
        rate = "표본 0" if d["rate"] is None else f"{100 * d['rate']:.1f}%"
        clv = "표본 0" if d["clv_avg"] is None else f"{d['clv_avg']:+.4f}"
        note = []
        if d["ungraded"]:
            note.append(f"미채점 {d['ungraded']}")
        if d["void"]:
            note.append(f"무효 {d['void']}")
        lines.append(f"{k:<16} {d['n']:>5} {d['graded']:>5} {d['hit']:>5}"
                     f" {rate:>8} {d['clv_n']:>6} {clv:>9}   {' · '.join(note)}")
    return "\n".join(lines)


_SQL = """
    SELECT {by} AS k, hit, void, clv
      FROM pick_ledger
     WHERE is_final
       AND date >= $1 AND date <= $2
       {sport}
"""


async def _run(a) -> int:
    from app.db import close_pool, get_pool

    by = check_by(a.by)
    pool = await get_pool()
    try:
        sql = _SQL.format(by=by, sport=" AND sport = $3" if a.sport else "")
        args = [a.since, a.until] + ([a.sport] if a.sport else [])
        rows = [dict(r) for r in await pool.fetch(sql, *args)]
        scope = f"{a.since} ~ {a.until}" + (f" · {a.sport}" if a.sport else "")
        print(f"원장 성적표 · {scope} · 축 {by} · 행 {len(rows)}건\n")
        print(render(summarize(rows), by=by))
        print("\n적중률 분모 = 채점(hit 이 True/False 이고 무효 아님) · "
              "CLV 분모 = clv 가 있는 행. 두 분모는 다르다.")
        return 0
    finally:
        await close_pool()


def main(argv=None) -> int:
    import datetime as _dt

    ap = argparse.ArgumentParser(description="원장 성적표 (읽기 전용)")
    ap.add_argument("--since", required=True, help="슬레이트 날짜 YYYY-MM-DD")
    ap.add_argument("--until", default=None, help="기본: 오늘 KST")
    ap.add_argument("--by", default="judge_by", help=" | ".join(BY_COLUMNS))
    ap.add_argument("--sport", default=None)
    a = ap.parse_args(argv)
    if not a.until:
        kst = _dt.timezone(_dt.timedelta(hours=9))
        a.until = _dt.datetime.now(kst).date().isoformat()
    return asyncio.run(_run(a))


if __name__ == "__main__":
    raise SystemExit(main())
