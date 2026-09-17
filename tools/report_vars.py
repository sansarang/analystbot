"""[RPT-1 2026-09-17] 원장 → `report.py` 표 출력 CLI.

    python tools/report_vars.py                    # 최근 90일
    python tools/report_vars.py --days 30
    python tools/report_vars.py --days 30 --sport soccer
    python tools/report_vars.py --json             # 원자료

🔴 **계산은 여기서 하지 않는다.** 평균·브라이어·판정은 전부
   `app/engine/report.py` 가 한다. `tools/calibration.py` 와 같은 규약이다 —
   "도구와 운영이 다른 계산을 하면 **표를 믿을 수 없다**".
   이 파일이 하는 일은 셋뿐: ① 원장에서 행을 읽고 ② report 에 넣고 ③ 찍는다.

🔴 **읽기 전용이다.** INSERT·UPDATE 를 하지 않는다.

⚠️ 로컬에서 돌리면 **로컬 DB** 를 본다. 운영 원장은 `railway ssh` 로 봐야
   한다 — `railway run` 은 운영 환경변수만 주입하고 컨테이너에 안 닿는다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: 🔴 읽는 칸만 적는다. `hit` 은 **우리 픽** 기준이고(원장 주석: "▲를 준 쪽이
#   이겼으면 hit"), `p_home` 은 **홈** 기준이다 — 아래에서 픽 기준으로 돌린다.
_SQL = """
    SELECT sport, league, date, predicted_side, favored,
           p_home, p_code, p_market,
           adj_pp, adj_evidence, hypothesis, confirmed, analyze_failed,
           clv, clv_line_shift, cancel_virtual_clv,
           watch_state, gate_label, gate_vs_llm, main_axis, flow_class,
           confidence, hit
      FROM pick_ledger
     WHERE is_final
       AND judged_at >= now() - ($1::int * interval '1 day')
       AND ($2::text IS NULL OR sport = $2::text)
     ORDER BY judged_at
"""


def _jsonb(v):
    """JSONB 칸은 드라이버에 따라 str 로 온다. 🔴 못 읽으면 **None**."""
    if v is None or isinstance(v, dict):
        return v
    try:
        got = json.loads(v)
    except (TypeError, ValueError):
        return None
    return got if isinstance(got, dict) else None


def to_rows(records, *, board_label: str) -> list[dict]:
    """원장 행 → `report.py` 가 먹는 모양. **계산하지 않는다 — 옮기기만 한다.**

    🔴 `p` 는 **고른 쪽 확률**이다. `p_home` 은 홈 기준인데 `hit` 은 우리 픽
       기준이라, 원정을 골랐으면 `1 − p_home` 이다. 안 돌리면 브라이어가
       통째로 뒤집힌다(PA-28 의 부호 문제와 같은 종류다).
    🔴 값이 없으면 **없는 채로** 넘긴다. 0 으로 채우지 않는다.
    """
    out = []
    for r in records:
        d = dict(r)
        side = str(d.get("predicted_side") or d.get("favored") or "").lower()
        p_home = d.get("p_home")
        if p_home is None:
            p_home = d.get("p_code")
        if p_home is None or side not in ("home", "away"):
            p = None
        else:
            p = float(p_home) if side == "home" else 1.0 - float(p_home)
        out.append({
            **d,
            "adj_pp": _jsonb(d.get("adj_pp")),
            "adj_evidence": _jsonb(d.get("adj_evidence")),
            "predicted_side": side or None,
            "p": p,
            "hit": (None if d.get("hit") is None else int(d["hit"])),
            # 🔴 라벨 문자열은 `gate.BOARD` 가 원본이다 — 호출부가 넘겨준다.
            "board_only": (d.get("gate_label") == board_label) or None,
        })
    return out


def _n(v, digits: int = 3) -> str:
    """🔴 없으면 `—`. 0 으로 찍으면 '0건'과 '0%'가 같아진다."""
    return "—" if v is None else (f"{v:.{digits}f}" if isinstance(v, float)
                                  else str(v))


def render(rep, rows: list[dict]) -> str:
    """표를 글자로. 🔴 숫자는 전부 `report.py` 가 준 값 그대로다."""
    L = []
    hy = rep.hygiene(rows)
    L.append(f"■ 표본 {hy['n']}건 · 도달 체크포인트 {_n(hy['reached'])} "
             f"(구간 {hy['checkpoints']})")
    for blk in ("위생", "방향", "결정"):
        L.append(f"  {blk}: " + " · ".join(f"{k} {_n(v)}"
                                           for k, v in hy[blk].items()))

    bv = rep.by_variable(rows)
    L.append(f"\n■ 변수별 채점 (문턱 {bv['min_n']}건 · 기준 **평균 CLV**)")
    if not bv["variables"]:
        L.append("  (조정 변수가 붙은 행이 없다)")
    else:
        L.append(f"  {'변수':<12}{'n':>5}{'기여(픽)':>10}{'평균CLV':>9}"
                 f"{'일치율':>8}{'적중률':>8}  제안")
        for name, v in sorted(bv["variables"].items(),
                              key=lambda kv: -kv[1]["n"]):
            L.append(f"  {name:<12}{v['n']:>5}{_n(v['평균_기여_픽기준'], 2):>10}"
                     f"{_n(v['평균_CLV'], 2):>9}{_n(v['부호_일치율'], 2):>8}"
                     f"{_n(v['적중률'], 2):>8}  {v['제안']}"
                     + (f"   출처 {v['출처']}" if v["출처"] else ""))

    for key in ("main_axis", "flow_class", "confidence"):
        ax = rep.by_axis(rows, key=key)
        L.append(f"\n■ {key} 별")
        if not ax["groups"]:
            L.append("  (없다)")
        for k, g in ax["groups"].items():
            L.append(f"  {str(k):<14}n {g['n']:<5} 적중 {_n(g['적중률'], 2)} "
                     f"· 브라이어 {_n(g['브라이어'], 4)} "
                     f"· 평균CLV {_n(g['평균_CLV'], 2)}")

    cc = rep.cancel_clv(rows)
    L.append(f"\n■ 취소 검증: 취소 {cc['취소건']}건 · 가상CLV 있음 "
             f"{cc['가상CLV_있음']}건 · 평균 {_n(cc['평균_가상CLV'], 2)} "
             f"→ {cc['판정']}")

    # 🔴 `source_score` 는 `{source, claimed, actual}` 대조 자료를 받는데
    #    원장에 그 자료가 없다. 없는 것을 억지로 채우지 않고 **말한다.**
    L.append("\n■ 결장 소스 정확도: 대조 자료(claimed/actual)가 원장에 없다 "
             "— report.source_score 는 부르지 않았다")
    return "\n".join(L)


async def main() -> int:
    ap = argparse.ArgumentParser(description="원장 변수별 채점 표")
    ap.add_argument("--days", type=int, default=90, help="집계 기간 (기본 90일)")
    ap.add_argument("--sport", default=None, help="mlb|kbo|npb|soccer (기본 전체)")
    ap.add_argument("--json", action="store_true", help="원자료를 JSON 으로")
    args = ap.parse_args()

    from app.db import close_pool, get_pool
    from app.engine import gate as G
    from app.engine import report as RP

    pool = await get_pool()
    try:
        recs = await pool.fetch(_SQL, args.days, args.sport)
    finally:
        await close_pool()

    rows = to_rows(recs, board_label=G.BOARD)
    if args.json:
        print(json.dumps({"n": len(rows),
                          "hygiene": RP.hygiene(rows),
                          "by_variable": RP.by_variable(rows),
                          "by_axis": {k: RP.by_axis(rows, key=k)
                                      for k in ("main_axis", "flow_class",
                                                "confidence")},
                          "cancel_clv": RP.cancel_clv(rows)},
                         ensure_ascii=False, indent=2, default=str))
    else:
        print(f"기간 {args.days}일 · 종목 {args.sport or '전체'}")
        print(render(RP, rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
