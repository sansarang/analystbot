"""🔴🔴 **§6-7 손실 깔때기** — 어느 단계에서 잃나(지시 2026-10-13 밤 셋째).

```
PYTHONPATH=. python tools/search_funnel.py
```

> 잃는 단계(원천/질의/본문/신원/추출)별 **손실 깔때기**.

🔴 카드가 적어 둔 **자기 집계**로 센다(다시 돌리지 않는다 — 카드가 그때의 봇이다).
🔴 단계 묶음은 **버린 사유를 그 단계로** 모은 것이다(사유 이름은 `app/reasons.py`).
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

HEAD = re.compile(r"^🏟 \*\*(.+?) vs (.+?)\*\* · (.+?) · ")
DROPS = re.compile(r"- 버린 것: (.+)$")
ONE = re.compile(r"`([a-z_]+)` (\d+)건")
DOCS = re.compile(r"문서 (\d+)건 · 변수 (\d+)개")

#: 🔴 사유 → 단계(지시서의 다섯 묶음)
STAGE = {
    "type_off_catalog": "① 원천(도메인 등급)",
    "sport_mismatch": "① 원천(종목 다름)",
    "identity_mismatch": "④ 신원",
    "team_tier_mismatch": "④ 신원(등급)",
    "team_reattached": "④ 신원(재부착)",
    "off_match": "④ 신원(다른 경기)",
    "stale": "② 질의·날짜(오래됨)",
    "body_missing": "③ 본문",
    "llm_schema": "⑤ 추출(스키마)",
    "llm_truncated": "⑤ 추출(잘림)",
    "type_content_mismatch": "⑤ 추출(유형 불일치)",
    "stakes_vague": "⑤ 추출(모호)",
    "premature_result": "⑤ 추출(결과 유출 차단)",
    "conflict": "⑤ 추출(충돌)",
    "duplicate": "— 중복",
}


def main(argv: list[str]) -> int:
    per_card: list[dict] = []
    for path in sorted((ROOT / "var/accept").glob("*card*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if not HEAD.search(text):
            continue
        box: Counter = Counter()
        for line in text.splitlines():
            got = DROPS.search(line)
            if got:
                for name, n in ONE.findall(got.group(1)):
                    box[name] += int(n)
        said = DOCS.search(text)
        per_card.append({"file": path.name, "drops": box,
                         "docs": int(said.group(1)) if said else None,
                         "vars": int(said.group(2)) if said else None})
    print("# 🔴🔴 §6-7 손실 깔때기(카드 자체 집계)")
    print()
    print(f"카드 **{len(per_card)}장** · 버린 것 집계를 적은 카드 "
          f"{sum(1 for c in per_card if c['drops'])}장 · 문서/변수 수를 적은 카드 "
          f"{sum(1 for c in per_card if c['docs'] is not None)}장")
    print()
    total: Counter = Counter()
    for one in per_card:
        total.update(one["drops"])
    by_stage: Counter = Counter()
    for name, n in total.items():
        by_stage[STAGE.get(name, f"⬜ 미분류({name})")] += n
    print("| 단계 | 버린 문서 | 비율 |")
    print("|---|---|---|")
    tot = sum(by_stage.values()) or 1
    for stage, n in by_stage.most_common():
        print(f"| {stage} | {n:,} | {n / tot:.1%} |")
    print(f"| **합** | **{tot:,}** | 100% |")
    print()
    print("| 사유 | 건수 |")
    print("|---|---|")
    for name, n in total.most_common(12):
        print(f"| `{name}` | {n:,} |")
    print()
    docs = [c for c in per_card if c["docs"] is not None]
    if docs:
        zero = [c for c in docs if c["docs"] == 0]
        novar = [c for c in docs if c["docs"] and not c["vars"]]
        print(f"🔴 **문서 0건 카드 {len(zero)}/{len(docs)}장** · "
              f"**문서는 있는데 변수 0개 카드 {len(novar)}장**")
        print(f"🔴 카드당 평균 — 문서 "
              f"{sum(c['docs'] for c in docs) / len(docs):.1f}건 · 변수 "
              f"{sum(c['vars'] or 0 for c in docs) / len(docs):.1f}개")
    print()
    print("⚠️ 이 표는 **버린 문서 수**다 — 검색이 **애초에 못 찾은 것**(질의가"
          " 안 닿은 기사)은 여기 **안 보인다**. 그쪽은 §6-7 의 재현율이 센다"
          "(기준선 16.3%).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
