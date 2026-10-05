"""🔴 게이트2 보고 — **로그에서** 작업지시 §3 이 요구한 수를 뽑는다.

작업지시 §3:

> 수정된 예산의 재실행 결과를 보고한다 — **턴 수 · `done` 턴 · 검색어
> 통과/거부 · `verified_vars` · 사유별 폐기 수 · `in`·`cache`·`out` 토큰과 USD.**
> 경기마다 **깔때기 한 줄과 변수 목록**(유형·방향·hardness·인용 유무)을 보고한다.

⚠️ 이것은 **프로브가 아니다**(규율 11) — 봇을 부르지 않는다. 봇이 남긴 로그를
   읽어 **세기만** 한다. 🔴 못 찾은 칸은 `-` 로 남긴다(조용한 0 금지 · #3).
"""
from __future__ import annotations

import pathlib
import re
import sys

#: 🔴 로그 줄에서 뽑을 것. ⚠️ 글을 지어내지 않는다 — **봇이 적은 그대로** 센다.
TURN = re.compile(r"\[agent\] 턴 (\d+) · (\w+)\(")
DONE = re.compile(r"\[agent\] 턴 (\d+) · done\(")
FUNNEL = re.compile(r"\[funnel\] (\w+) (queries:.*)$")
DROPS = re.compile(r"\[funnel\] \w+ (.*탈락.*)$")
COST = re.compile(r"입력\(새로\) ([\d,]+)/[\d,]+ · 출력 ([\d,]+)/[\d,]+ · "
                  r"캐시 ([\d,]+) · \$([\d.]+)")
CELL = re.compile(r"· 세포 에이전트:([^:]+): (.*)$")

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **게이트2 조건 재정의** — 지시서(오픈월드) §1-3 (2026-10-05)
# ══════════════════════════════════════════════════════════════════
#
# > 5경기 중 4경기에서 `verified_vars ≥ 6` 이면서 **그중 에이전트 출처 ≥ 3**.
# > **구조 자료만으로 채운 6개는 통과가 아니다.** `tools/gate2_report.py` 에
# > **출처 열(agent/structured)** 을 추가한다.
#
# ⚠️ 왜 — 실측 2026-10-04(포르투갈): `verified_vars 11` 이었지만 **에이전트
#    기여가 0** 이었다(전부 fotmob 구조 자료). 🔴 미등록 리그에는 그 구조 자료가
#    **없으므로**, 그 상태로 오픈월드를 켜면 카드가 빈 카드가 된다.
NEED_VERIFIED = 6
NEED_AGENT = 3

#: 🔴 에이전트가 낸 검증 통과 수를 적는 줄. ⚠️ 봇이 쓴 글을 **그대로** 센다.
AGENT_PASS = re.compile(r"\*\*검증 통과 (\d+)개\*\*")


def sources_of(lines: list[str]) -> dict:
    """🔴 **출처별 변수 수** — `{agent, structured}`.

    ⚠️ `structured` 는 **못 센다**(어댑터 변수에 출처 표시가 없다). 🔴 그래서
       `verified_vars - agent` 로 **뺀다** — 그 수가 음수면 셈이 어긋난 것이고,
       조용히 0 으로 만들지 않는다(#3).
    """
    agent = 0
    for ln in lines:
        if "세포 에이전트" not in ln:
            continue
        for m in AGENT_PASS.finditer(ln):
            agent += int(m.group(1))
    return {"agent": agent}


def passes(box: dict) -> bool:
    """🔴🔴 한 경기가 **게이트2 를 넘었나** — 두 조건을 **같이** 본다(§1-3)."""
    return (int(box.get("verified") or 0) >= NEED_VERIFIED
            and int(box.get("agent") or 0) >= NEED_AGENT)
SENT = re.compile(r"@@@SENT@@@ (.*)$")


def _n(s: str) -> int:
    return int(str(s).replace(",", "") or 0)


def read(p: pathlib.Path) -> dict:
    """🔴 한 경기 로그 → 수들. ⚠️ 없는 것은 **넣지 않는다**(`-` 로 보인다)."""
    out: dict = {"file": p.name, "turns": {}, "ok": 0, "bare": 0, "dup": 0,
                 "funnel": {}, "drops": [], "cells": [], "cost": [],
                 # 🔴 §1-3 출처 열이 줄을 다시 봐야 한다(세포 에이전트 줄)
                 "lines": []}
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        out["error"] = f"{exc}"
        return out
    out["lines"] = lines
    for ln in lines:
        if m := SENT.search(ln):
            out["asked"] = m.group(1)
        if m := TURN.search(ln):
            out["turns"][m.group(1)] = out["turns"].get(m.group(1), 0) + 1
            if m.group(2) == "search":
                if "→ ok" in ln:
                    out["ok"] += 1
                elif "query_too_bare" in ln:
                    out["bare"] += 1
                elif "duplicate_query" in ln:
                    out["dup"] += 1
        if m := DONE.search(ln):
            out["done_turn"] = m.group(1)
        if m := FUNNEL.search(ln):
            out["funnel"][m.group(1)] = m.group(2)
        if m := DROPS.search(ln):
            if m.group(1) not in out["drops"]:
                out["drops"].append(m.group(1))
        if m := COST.search(ln):
            out["cost"].append({"in": _n(m.group(1)), "out": _n(m.group(2)),
                                "cache": _n(m.group(3)),
                                "usd": float(m.group(4))})
        if m := CELL.search(ln):
            out["cells"].append((m.group(1).strip(), m.group(2).strip()[:150]))
    return out


def verified(box: dict) -> int | None:
    """🔴 `verified_vars` — **마지막 깔때기**가 말한 수. 없으면 `None`."""
    line = box["funnel"].get("build") or box["funnel"].get("gather") or ""
    m = re.search(r"verified_vars:(\d+|-)", line)
    if not m or m.group(1) == "-":
        return None
    return int(m.group(1))


def report(paths: list[pathlib.Path]) -> str:
    rows = [read(p) for p in paths]
    out = ["# 게이트2 — 작업지시 §3 보고", ""]
    # 🔴 **출처 열**(지시서 §1-3) — 구조 자료만으로 채운 6개는 통과가 아니다
    out += ["| 경기 | 턴 | `done` | 검색 ok/거부/중복 | `verified_vars` | "
            "에이전트 | 구조 | 합격 | in | cache | out | USD |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        v = verified(r)
        # 🔴 출처를 가른다(§1-3). ⚠️ `구조` 는 **뺀 수**다 — 어댑터 변수에 출처
        #    표시가 없어 **직접 셀 수 없다**(그 사실을 적는다 · #3).
        src = sources_of(r.get("lines") or [])
        ag = src["agent"]
        st = (v - ag) if (v is not None) else None
        ok = passes({"verified": v or 0, "agent": ag})
        c = r["cost"]
        s = {k: sum(x[k] for x in c) for k in ("in", "out", "cache")} if c else {}
        usd = sum(x["usd"] for x in c) if c else None
        name = re.sub(r"^g\d+_", "", r["file"]).replace(".log", "")
        head = (f"| {name} | {len(r['turns']) or '-'} "
                f"| {r.get('done_turn', '-')} "
                f"| {r['ok']}/{r['bare']}/{r['dup']} "
                f"| {v if v is not None else '-'} "
                f"| {'🔴 ' + str(ag) if ag < NEED_AGENT else ag} "
                f"| {st if st is not None else '-'} "
                f"| {'✅' if ok else '🔴'} ")
        out.append(head + (
            f"| {s.get('in', 0):,} | {s.get('cache', 0):,} "
            f"| {s.get('out', 0):,} | {'$%.4f' % usd} |" if s else
            "| - | - | - | - |"))
    ok = [r for r in rows
          if passes({"verified": verified(r) or 0,
                     "agent": sources_of(r.get("lines") or [])["agent"]})]
    out += ["", f"## 완료 조건 — 5경기 중 **4경기**가 "
                f"`verified_vars ≥ {NEED_VERIFIED}` **이면서 에이전트 출처 "
                f"≥ {NEED_AGENT}**(지시서 §1-3)",
            "", "🔴 **구조 자료만으로 채운 6개는 통과가 아니다** — 미등록 "
                "리그에는 그 구조 자료가 없다",
            "", f"지금 **{len(ok)}/{len(rows)}** 경기가 넘었다 "
                f"→ {'✅ 통과' if len(ok) >= 4 else '🔴 아직'}"]
    for r in rows:
        name = r["file"].replace("g3_", "").replace(".log", "")
        out += ["", f"## {name} — {r.get('asked', '(질문 못 찾음)')}"]
        if r.get("error"):
            out += [f"🔴 로그를 못 읽었다: {r['error']}"]
            continue
        for stage, line in r["funnel"].items():
            out += [f"- 깔때기(`{stage}`) `{line}`"]
        for d in r["drops"]:
            out += [f"- 🔴 {d}"]
        for who, said in r["cells"]:
            out += [f"- 에이전트 `{who}` — {said}"]
    return "\n".join(out)


if __name__ == "__main__":        # pragma: no cover
    args = [pathlib.Path(x) for x in sys.argv[1:]]
    print(report(args))
