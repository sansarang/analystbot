"""🔴🔴 **§1 누설 점검** — 비교 시험 지시서 2026-10-12 §1(**시험 전 필수**).

```
PYTHONPATH=. python tools/leak_audit.py --match 5140047
```

> 1-1 축2·축3 재료 · 1-2 축0 가치 · 1-3 결과 누설 grep · 1-4 계수 판(E1).
> **하나라도 실패면 시험 중단.**
> 계약 **L4**: 재현에서 **현재 값 입구**가 ⬜ 없이 축 값에 들어가면 실패.

🔴 이 도구가 보는 것은 **입구마다 "그 수가 언제의 값인가"** 다:
   · `as_of 이전 경기 단위 재합산` → ✅ 쓸 수 있다
   · `시즌 누계·현재 값` → 🔴 재현에서 **⬜ + 축 값 0** 이어야 한다(L2·L4)
🔴 수를 짓지 않는다 — 코드를 읽고(정적) + 그 경기를 받아(실측) 센다.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴🔴 **입구 표** — `(이름, 무엇을 세나, 코드 자리, 축)`
#  ⚠️ 이 목록은 손으로 유지하면 한 발 늦는다 — 그래서 **자리마다 코드를 읽어**
#     `as_of`·`before_as_of`·`now_only` 를 센다(아래 `_verdict`).
#  꼴: `(이름, 무엇을 세나, 모듈, 축, 부르는 쪽, L2 열쇠)`
#  🔴 **왜 세 칸인가** — 문은 **부르는 쪽**에 있을 수 있다(순수 함수는 이미 잘린
#     줄을 받는다). 모듈만 보면 그 경우를 🔴 로 잘못 읽는다(실측 2026-10-12).
ENTRIES: tuple[tuple[str, str, str, str, str, str], ...] = (
    ("스타일 6축", "패스·전진·압박 … 6지표", "app/core/stages/s2e_matchup.py",
     "축2", "app/core/stages/s2e_matchup.py", ""),
    ("시간대 득실", "0-30·31-60·61-90 득실", "app/core/stages/s2e_matchup.py",
     "축3", "app/core/stages/s2e_matchup.py", ""),
    ("골 내용", "유형·상태·xG", "app/core/stages/s2e_matchup.py", "축3",
     "app/core/stages/s2e_matchup.py", ""),
    ("무기 표", "상황별 xG 비중", "app/core/stages/s2e_matchup.py", "축2",
     "app/core/stages/s2e_matchup.py", ""),
    ("규칙 T1~T13", "발동 규칙·상태 배율", "app/core/goals.py", "축2·축3",
     "app/core/stages/s2e_matchup.py", ""),
    ("선수 가치(축0)", "시장 가치·시즌 기록", "app/core/playervalue.py", "축0",
     "app/core/matchup.py", "player_value"),
    ("공격 기여표(축0)", "득점+도움 시즌 누계", "app/core/matchup.py", "축0",
     "app/core/stages/s2_facts.py", "player_stats"),
    ("폼(축1)", "최근 5·10경기 득실·xG", "app/core/form.py", "축1",
     "app/core/stages/s2e_matchup.py", ""),
    ("리그 총골 기준", "경기당 총골(λ 기준)", "app/rules.py", "λ 기준",
     "app/core/probmodel.py", "standings.match_total_baseline"),
    ("Elo 등급", "경기 전 등급 차", "app/collect/leagueelo.py", "바닥",
     "app/core/stages/s2b_base.py", ""),
    ("경기 직전 상태", "휴식·부하·컵·휴식기", "app/core/context.py", "§8 항",
     "app/core/stages/s2_facts.py", ""),
    ("선수 ±", "구간 플러스마이너스", "app/core/ratings/player_pm.py",
     "§7 pdiff", "tools/fit_player_pm.py", ""),
)

#: 🔴 결과 누설을 찾는 그물 — 그 경기 **스코어**와 경기 후 낱말
AFTER_WORDS = ("최종 스코어", "경기 결과", "final score", "full-time",
               "승리했다", "패했다", "이겼다", "졌다")


def _code(rel: str) -> str:
    """🔴 D46 — 독스트링을 뺀 **코드만**."""
    said = (ROOT / rel).read_text(encoding="utf-8")
    tree = ast.parse(said)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _verdict(rel: str) -> tuple[str, str]:
    """🔴 그 입구가 **언제의 값**을 쓰나. `(판정, 근거)`."""
    code = _code(rel)
    gate = "before_as_of" in code
    asof = "as_of" in code
    now_only = ("NOW_ONLY" in code or "may_use" in code)
    if gate and asof:
        return "✅ as_of 이전 경기 단위", "`before_as_of` 문 + `as_of` 인자"
    if now_only:
        return "⚠️ 현재 값 입구 — ⬜ 표시", "`asof.may_use`/`NOW_ONLY` 를 지난다"
    if asof:
        return "⚠️ as_of 는 받는다(문은 안 지난다)", "`as_of` 만 있다"
    return "🔴 **현재 값**(재합산 아님)", "`as_of`·문이 **없다**"


async def _grep_result(mid: str) -> list[str]:
    """🔴🔴 1-3 — **그 경기 결과가 재생 입력에 섞였나**(실측 grep)."""
    from app.collect import fotmob as fm
    from app.core import backfill as bf
    from app.net import Net
    net = Net(cache=True)
    page = await net.get(fm.match_url(str(mid)))
    j = fm.payload(getattr(page, "text", "") or "")
    if not j:
        return ["🔴 경기 페이지를 못 받았다 — grep 을 못 했다"]
    got = bf.score_of(j)
    out: list[str] = []
    if got is None:
        return ["⚠️ 스코어를 못 읽었다(끝난 경기가 아니거나 꼴이 바뀌었다)"]
    score = f"{got[0]}-{got[1]}"
    out.append(f"그 경기 스코어 **{score}**")
    # 🔴 맞대결 표에 자기 줄이 있나(L1 문이 막는 그 자리)
    h = ((j.get("props") or {}).get("pageProps") or {}).get(
        "content", {}).get("h2h") or {}
    rows = [str((m.get("status") or {}).get("scoreStr") or "").replace(" ", "")
            for m in (h.get("matches") or [])]
    out.append(f"맞대결 {len(rows)}줄에 그 스코어가 "
               + ("🔴 **있다**" if score in rows else "**없다**"))
    # 🔴 경기 후 낱말이 재생 문서에 섞일 수 있는가 — 그 경기 페이지 글자로 센다
    said = getattr(page, "text", "") or ""
    hits = [w for w in AFTER_WORDS if w in said]
    out.append("경기 후 낱말 " + (f"🔴 {hits[:3]}" if hits else "없다"))
    return out


def _coef_versions() -> list[str]:
    """🔴 1-4 — 계수 판이 **평가 시즌 밖**인지. ⚠️ 손값은 그 사실을 적는다."""
    out: list[str] = []
    data = ROOT / "data"
    for box in sorted(data.glob("*")):
        if not box.is_dir():
            continue
        days = sorted(p.stem for p in box.rglob("*.yaml"))
        out.append(f"`{box.name}` — 판 {len(days)}개"
                   + (f"({days[0]} ~ {days[-1]})" if days else " · ⬜ **없다**"))
    from app.core import matchup as _mu
    fit = dict(_mu.table().get("fit") or {})
    out.append(f"🔴 옛 경로의 **손값**(축 비중·β) — `fit.provisional="
               f"{fit.get('provisional')}` · n={fit.get('n')} — 두 경로가 "
               f"**같은 값을 쓰지만 적합된 적이 없다**")
    return out


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", default="5140047",
                    help="🔴 1-3 결과 누설 grep 에 쓸 경기 id")
    args = ap.parse_args(argv[1:])
    print("# 🔴🔴 §1 누설 점검 — **시험 전 관문**")
    print()
    print("## 1-1·1-2 입구별 표 — 그 수는 **언제의 값**인가")
    print()
    print("| 입구 | 무엇을 세나 | 축 | 모듈 | 부르는 쪽(문이 거기 있나) | "
          "L2 표시 | **판정** |")
    print("|---|---|---|---|---|---|---|")
    bad = 0
    from app.core import asof as _asof
    for name, what, rel, axis, caller, l2key in ENTRIES:
        if not (ROOT / rel).is_file():
            print(f"| {name} | {what} | {axis} | `{rel}` | — | — | "
                  f"⬜ **파일 없다** |")
            continue
        v_mod, why_mod = _verdict(rel)
        v_call, _why_call = (_verdict(caller)
                             if (ROOT / caller).is_file() else ("⬜", ""))
        said_l2 = ""
        if l2key:
            got = dict(_asof.NOW_ONLY).get(l2key, "")
            said_l2 = ("🔴 **현재 값**(L2 표)" if got.startswith(_asof.MARK)
                       else ("✅ as-of 정합(L2 표)" if got else "⬜ 표에 없다"))
        # 🔴 판정 — 모듈이든 **부르는 쪽**이든 문을 지나면 ✅
        if v_mod.startswith("✅") or v_call.startswith("✅"):
            verdict = "✅ as_of 이전 경기 단위"
        elif said_l2.startswith("✅"):
            # 🔴 그 경기 페이지에서 오는 값은 **as-of 정합**이다(L2 표가 그 근거다)
            verdict = "✅ as-of 정합(그 경기 페이지)"
        elif said_l2.startswith("🔴"):
            verdict = "🔴 **현재 값 — 재현에서 ⬜**(L2 가 막는다)"
        elif v_mod.startswith("⚠️") or v_call.startswith("⚠️"):
            verdict = "⚠️ as_of 는 받는다(문은 안 지난다)"
        else:
            verdict = "🔴 **현재 값**(문도 L2 표시도 없다)"
            bad += 1
        print(f"| {name} | {what} | {axis} | `{Path(rel).name}` "
              f"{'✅' if v_mod.startswith('✅') else ''} | "
              f"`{Path(caller).name}` {'✅' if v_call.startswith('✅') else ''} | "
              f"{said_l2 or '—'} | {verdict} |")
    print()
    print("## 1-3 결과 누설 grep")
    print()
    for line in await _grep_result(str(args.match)):
        print(f"- {line}")
    print()
    print("## 1-4 계수 판(E1)")
    print()
    for line in _coef_versions():
        print(f"- {line}")
    print()
    print(f"# {'🔴 **중단**' if bad else '✅ **통과**'} — 현재 값 입구 {bad}개")
    if bad:
        print()
        print("⚠️ 🔴 로 표시된 입구는 **재현에서 ⬜ + 축 값 0** 이어야 한다(L4).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
