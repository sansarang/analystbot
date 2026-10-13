"""🔴🔴 **§6-4 신원 감사** — 버린 문서가 **정말 남의 글이었나**(지시 2026-10-13 밤 셋째).

```
PYTHONPATH=. python tools/identity_audit.py
```

> identity_mismatch 표본 감사 먼저: 최근 카드에서 버린 문서 100건을 뽑아
> "정말 다른 경기였나" 판정 표(맞게 버림 / 잘못 버림 / 애매).
> 판정 기준 변경: 팀 이름 정확 일치 → **신원표 별칭(현지어 포함) 일치 + 날짜 창 +
> 상대 팀 언급 + 선수 이름 중 2개 이상**이면 통과.
> 계약 **ID1**: **잘못 버림 비율 > 10%** 면 기준 재조정 후 재측정.

🔴 **자동 판정이다**(수작업 아님) — 카드에 남은 것은 **제목뿐**이고 스니펫·본문은
   저장되지 않았다. 그래서 *"제목만으로도 그 경기 글임이 보이나"* 를 센다.
   ⚠️ 그 한계를 보고가 **매번** 적는다(#4 추측 금지).
"""
from __future__ import annotations

import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

HEAD = re.compile(r"^🏟 \*\*(.+?) vs (.+?)\*\* · (.+?) · (\d\d)-(\d\d) ")
#: 🔴 `| \`s3/신원\` | \`identity_mismatch\` | 제목 | 사유 |`
DROP = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*`identity_mismatch`\s*\|"
                  r"\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")

#: 🔴 흔한 **목록·태그·쇼핑** 제목 — 맞게 버린 것이 명백한 꼴(실측에서 온 글자)
JUNK = ("transfermarkt", "squad analysis", "/league", "season/", "tag?",
        "wikipedia", "표 ·", "fixtures & results", "livescore")


def rows() -> list[dict]:
    """🔴 카드마다 `{home, away, league, titles[]}`(신원으로 버린 제목)."""
    out: list[dict] = []
    for path in sorted((ROOT / "var/accept").glob("*card*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        head = HEAD.search(text)
        if not head:
            continue
        said: list[str] = []
        for line in text.splitlines():
            got = DROP.match(line)
            if not got:
                continue
            title = got.group(2).strip()
            if title and "제목 없음" not in title:
                said.append(title)
        if said:
            out.append({"file": path.name, "home": head.group(1).strip(),
                        "away": head.group(2).strip(),
                        "league": head.group(3).strip(), "titles": said})
    return out


def new_rule(title: str, *, home: str, away: str) -> tuple[bool, list[str]]:
    """🔴🔴 **새 기준** — 신호 **둘 이상**이면 통과(별칭·상대 팀·선수·날짜 창).

    🔴 별칭은 `discover.aliases_of` 하나가 든다(사본 금지 · 현지어 포함).
    ⚠️ 제목만 있으므로 *"날짜 창"* 신호는 **제목 안의 날짜**로만 본다.
    """
    from app.core import discover as _d
    said = str(title or "").lower()
    hits: list[str] = []
    for side, name in (("home", home), ("away", away)):
        for one in _d.aliases_of(name):
            got = str(one or "").strip().lower()
            if len(got) >= 3 and got in said:
                hits.append(f"{side}:{one}")
                break
    if re.search(r"20\d\d[-/.]\d\d|\d\d[-/.]\d\d[-/.]20\d\d", said):
        hits.append("날짜")
    for word in ("lineup", "선발", "예상", "결장", "injur", "부상", "출전",
                 "스타팅", "선발 라인업", "欠場", "先発"):
        if word in said:
            hits.append(f"말:{word}")
            break
    return (len(hits) >= 2), hits


def main(argv: list[str]) -> int:
    box = rows()
    pool = [(r, t) for r in box for t in r["titles"]]
    rnd = random.Random(7)
    rnd.shuffle(pool)
    said = pool[:100]
    print("# 🔴🔴 §6-4 신원 감사(자동 판정 · 제목만)")
    print()
    print(f"카드 **{len(box)}장**에서 신원으로 버린 **제목 {len(pool)}개** · "
          f"무작위 **{len(said)}개**를 본다(씨앗 7)")
    print()
    print("🔴 **한계** — 카드에 남은 것은 **제목뿐**이다(스니펫·본문은 저장되지"
          " 않았다). 그래서 이 표는 *\"제목만으로도 그 경기 글임이 보이나\"* 를"
          " 센다. ⚠️ 제목에 안 보여도 **본문에는 있을 수** 있다(그쪽은 다시"
          " 받아야 알 수 있고, 그것이 §6-3 의 일이다).")
    print()
    tally: Counter = Counter()
    wrong: list[tuple[str, list[str]]] = []
    for r, title in said:
        ok, hits = new_rule(title, home=r["home"], away=r["away"])
        junk = any(j in title.lower() for j in JUNK)
        if ok and not junk:
            tally["🔴 잘못 버림(새 기준은 통과)"] += 1
            wrong.append((title, hits))
        elif ok and junk:
            tally["애매(새 기준 통과 · 목록/태그 꼴)"] += 1
        elif junk:
            tally["맞게 버림(목록·태그·쇼핑)"] += 1
        else:
            tally["맞게 버림(신호 1개 이하)"] += 1
    print("| 판정 | 건수 | 비율 |")
    print("|---|---|---|")
    for key, n in tally.most_common():
        print(f"| {key} | {n} | {n / len(said):.0%} |")
    bad = tally["🔴 잘못 버림(새 기준은 통과)"]
    print()
    print(f"🔴 **잘못 버림 비율 {bad / len(said):.0%}** — 계약 ID1 의 문턱은"
          f" **10%** 다 → "
          + ("🔴 **기준을 바꿔야 한다**" if bad / len(said) > 0.10
             else "✅ 문턱 안(기준을 바꿀 근거가 약하다)"))
    if wrong:
        print()
        print("## 🔴 잘못 버린 것으로 보이는 제목(앞 12개)")
        print()
        for title, hits in wrong[:12]:
            print(f"- `{title[:70]}` — 신호 {hits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
