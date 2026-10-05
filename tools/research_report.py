"""🔴🔴 **하위별 보고 표**(작업 지시서 2026-10-05 §2).

> 경기 하나의 **하위별 표**(질의·통과/거부·fetch·변수 후보·검증 통과·토큰·초)
> + 합계 출력.

⚠️ 지시서 §8: *"표 없이 '됐다' 는 보고는 받지 않는다."*
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

#: 🔴 `lead.funnel_lines` 가 만든 줄의 꼴. ⚠️ 그 함수가 원본이다 — 여기서
#  꼴을 **다시 정하지 않는다**(#1 사본 금지). 이 정규식은 **읽는** 쪽이다.
_ROW = re.compile(
    r"(?P<name>[A-D]-(?:홈|원정)(?:\(2차\))?):\s*q(?P<q>\d+)\s+"
    r"통과(?P<pass>\d+)\s+거부(?P<rej>\d+)\s+fetch(?P<fetch>\d+)\s+"
    r"후보(?P<cand>\d+)\s+검증(?P<ver>\d+)\s+(?P<tok>[\d.]+k?)\s*tok\s+"
    r"(?P<sec>[\d.]+)s")

#: 🔴 하위가 **안 돌았을 때** 그 까닭 — 깔때기 사유와 같은 글자다.
_BLOCKED = re.compile(r"안 돌렸다\s*—\s*(?P<why>[^|\n]+)")

#: 🔴 깔때기 탈락 사유 — **수치가 0 인 까닭**이 여기 있다.
#  ⚠️ 표만 내고 까닭을 빼면 *"안 찾았다"* 와 *"못 돌렸다"* 가 섞인다(#3).
_DROP = re.compile(r"(?P<stage>[a-z_]+) 탈락: (?P<why>[^|\n]+)")


def rows_of(text: str) -> list[dict]:
    """🔴 로그/카드 글 → 하위별 행들. ⚠️ 없으면 **빈 목록**(지어내지 않는다)."""
    out: list[dict] = []
    for m in _ROW.finditer(str(text or "")):
        box = m.groupdict()
        tok = box["tok"]
        box["tok_n"] = int(float(tok[:-1]) * 1000) if tok.endswith("k") \
            else int(float(tok))
        out.append(box)
    return out


def blocked_of(text: str) -> list[str]:
    """🔴 **안 돌아간 까닭**들 — 조용히 0 으로 적지 않는다(#3).

    두 곳을 읽는다: 하위 노트의 *"안 돌렸다 — …"* 와 **깔때기 탈락 사유**.
    ⚠️ 표만 내고 까닭을 빼면 *"안 찾았다"* 와 *"못 돌렸다"* 가 섞인다.
    """
    said = {m.group("why").strip() for m in _BLOCKED.finditer(str(text or ""))}
    for m in _DROP.finditer(str(text or "")):
        said.add(f"{m.group('stage')} 탈락: {m.group('why').strip()}")
    return sorted(said)


def report(text: str) -> str:
    """🔴🔴 **하위별 표 + 합계**(지시서 §2·§8).

    > 경기 하나의 하위별 표(질의·통과/거부·fetch·변수 후보·검증 통과·토큰·초)
    > + 합계 출력. ⚠️ *"표 없이 '됐다' 는 보고는 받지 않는다."*
    """
    rows = rows_of(text)
    gone = blocked_of(text)
    out = ["| 하위 | 질의 | 통과 | 거부 | fetch | 후보 | 검증 | 토큰 | 초 |",
           "|---|---|---|---|---|---|---|---|---|"]
    tot = dict.fromkeys(("q", "pass", "rej", "fetch", "cand", "ver",
                         "tok_n"), 0)
    secs = 0.0
    for r in rows:
        for k in tot:
            tot[k] += int(r[k])
        secs = max(secs, float(r["sec"]))
        out.append(f"| {r['name']} | {r['q']} | {r['pass']} | {r['rej']} | "
                   f"{r['fetch']} | {r['cand']} | {r['ver']} | {r['tok']} | "
                   f"{r['sec']} |")
    if not rows:
        out.append("| — | — | — | — | — | — | — | — | — |")
    out.append(f"| **합계** | {tot['q']} | {tot['pass']} | {tot['rej']} | "
               f"{tot['fetch']} | {tot['cand']} | {tot['ver']} | "
               f"{tot['tok_n'] / 1000:.1f}k | {secs:.0f} |")
    if gone:
        out.append("")
        out.append("🔴 **안 돌아간 하위의 까닭**(조용한 0 금지):")
        out += [f"  · {w}" for w in gone]
    if not rows and not gone:
        out.append("")
        out.append("⚠️ **하위별 줄을 못 찾았다** — 이 글에 `lead.funnel_lines` "
                   "출력이 없다(경기를 안 돌렸거나 로그가 잘렸다)")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    """🔴 `tools/research_report.py <로그파일>` — 표를 찍는다."""
    if len(argv) < 2:
        print("쓰는 법: tools/research_report.py <로그 또는 카드 파일>")
        return 2
    said = Path(argv[1]).read_text(encoding="utf-8", errors="replace")
    print(report(said))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
