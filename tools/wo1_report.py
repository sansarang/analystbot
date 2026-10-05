"""🔴 지시서 §1 완료 기준 보고 — **로그에서** 센다(프로브 아니다 · 규율 12).

사용자 지시 2026-10-05:

> 1. **재실행 보고** — 에이전트 출처 변수의 **유형 분포**(카탈로그 이름 기준),
>    **장부 상태표**(유형×팀: searched/found/empty/not_tried)
>    - 결장·로테이션·감독 갈등·경기외 중 **`found` 가 둘 이상**이면 §1 완료
>    - 미달이면 네 유형 각각이 **`empty`**(찾았는데 없음)인지, **`found` 였는데
>      검증에서 떨어졌는지**(사유 코드 + 인용 + 본문 부근 200자)를 갈라 보고
"""
from __future__ import annotations

import pathlib
import re
import sys

#: 🔴 네 유형 — 목록은 `ledgerbook` 하나다(사본 금지)
def _must() -> tuple[str, ...]:
    from app.ledgerbook import MUST_TRY
    return MUST_TRY


VAR = re.compile(r"^  (R\d+) \[([a-z_0-9]+)·([a-z]+)·([a-z]+)\](.*)$")
AGENT = re.compile(r"§3 에이전트")
BOOK = re.compile(r"장부 (\d+)칸 — searched (\d+) · empty (\d+) · found (\d+)")
DROP = re.compile(r"\[verify\] 폐기 (\w+) — (.*)$")
DONE_NO = re.compile(r"`done` \*\*거부\*\* — (.*)$")


def read(p: pathlib.Path) -> dict:
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    head, card = [], []
    seen = False
    for ln in lines:
        if "@@@CARD@@@" in ln:
            seen = True
            continue
        (card if seen else head).append(ln)
    return {"head": head, "card": card}


def types_of(card: list[str]) -> dict:
    """🔴 **에이전트 출처** 변수의 유형 분포. ⚠️ 구조 자료와 가른다."""
    got: dict = {}
    for ln in card:
        m = VAR.match(ln)
        if not m or not AGENT.search(m.group(5)):
            continue
        got[m.group(2)] = got.get(m.group(2), 0) + 1
    return got


def book_of(head: list[str]) -> dict:
    """🔴 장부 한 줄에서 상태 수. ⚠️ 없으면 **그 사실을** 남긴다(#3)."""
    for ln in reversed(head):
        m = BOOK.search(ln)
        if m:
            return {"cells": int(m.group(1)), "searched": int(m.group(2)),
                    "empty": int(m.group(3)), "found": int(m.group(4))}
    return {}


def drops_of(head: list[str], *, kinds: tuple[str, ...]) -> list[str]:
    """🔴 그 네 유형이 **검증에서 떨어졌나** — 사유 + 인용 + 본문 부근."""
    out = []
    for ln in head:
        m = DROP.search(ln)
        if not m:
            continue
        said = m.group(2)
        if any(k in said for k in kinds):
            out.append(f"{m.group(1)} — {said[:220]}")
    return out


def report(p: pathlib.Path) -> str:
    box = read(p)
    kinds = _must()
    t = types_of(box["card"])
    b = book_of(box["head"])
    out = [f"# §1 완료 기준 — `{p.name}`", ""]
    out += ["## 에이전트 출처 변수 — 유형 분포(카탈로그 이름 기준)", ""]
    if not t:
        out += ["🔴 **에이전트 출처 변수가 0개다**", ""]
    else:
        from app import rules
        cat = set(rules.variable_types())
        out += ["| 유형 | 수 | 카탈로그 |", "|---|---|---|"]
        for k, n in sorted(t.items(), key=lambda x: -x[1]):
            out.append(f"| `{k}` | {n} | {'✅' if k in cat else '🔴 **밖**'} |")
        off = [k for k in t if k not in cat]
        out += ["", (f"🔴 카탈로그 **밖** 유형 {len(off)}종: {off}" if off
                     else "✅ 전부 카탈로그 이름이다")]
    out += ["", "## 장부", ""]
    out += [(f"`장부 {b['cells']}칸 — searched {b['searched']} · "
             f"empty {b['empty']} · found {b['found']}`") if b else
            "🔴 **장부 줄이 로그에 없다** — 안 돌았거나 안 적혔다(#3)"]
    out += ["", f"## 네 유형 — {list(kinds)}", ""]
    hit = [k for k in kinds if k in t]
    out += [f"에이전트 변수에 **{len(hit)}종**이 있다: {hit or '없다'}",
            "", ("✅ **§1 완료**(둘 이상)" if len(hit) >= 2 else
                 "🔴 **미달** — 아래를 갈라 본다")]
    if len(hit) < 2:
        gone = drops_of(box["head"], kinds=kinds)
        out += ["", "### 검증에서 떨어진 것(사유 + 인용 + 본문 부근)", ""]
        out += [f"- {x}" for x in gone[:10]] or [
            "🔴 **그 유형으로 떨어진 기록이 없다** — 애초에 **안 찾았다**"]
        no = [ln for ln in box["head"] if DONE_NO.search(ln)]
        out += ["", f"### `done` 거부 {len(no)}회", ""]
        out += [f"- {ln.split('—', 1)[-1][:200]}" for ln in no[:4]]
    return "\n".join(out)


if __name__ == "__main__":        # pragma: no cover
    for a in sys.argv[1:]:
        print(report(pathlib.Path(a)))
