"""🔴 **봇이 단계별로 어떻게 예측했나** — 로그에서 눈으로 볼 수 있게 펼친다.

사용자 요청 2026-10-04: *"단계별 변수 가설 결론카드를 단계별로 어떻게
예측했는지 눈으로 확인할수 있게 해주라."*

⚠️ **프로브가 아니다**(규율 11) — 봇을 부르지 않는다. 봇이 남긴 로그를 읽어
   **순서대로 늘어놓기만** 한다. 🔴 못 찾은 칸은 *"그 줄이 없다"* 로 적는다(#3).
"""
from __future__ import annotations

import pathlib
import re
import sys

#: 🔴 단계마다 **어느 줄을 보나**. ⚠️ 글을 지어내지 않는다 — 봇이 쓴 그대로다.
STEPS: tuple[tuple[str, str], ...] = (
    ("① 입구 — 팀·리그·경기 찾기",
     r"\[teamref\]|\[league_index\] (KBO|NPB|MLB|NHL|해외축구)|\[findgame\]"
     r"|\[analyze\] 입구"),
    ("② 수집 — 어떤 자료를 봤나",
     r"\[collect\.|\[search\] 병렬 합계|\[searx\]|\[bing-news\]|\[gdelt\]"),
    ("③ 읽기 — 본문을 어떻게 줄였나", r"\[readtext\]|\[intent\]"),
    ("④ 에이전트 — 턴마다 무엇을 했나", r"\[agent\] 턴|\[agent\] 🔴"),
    ("⑤ 깔때기 — 아홉 칸과 사유", r"\[funnel\]"),
    ("⑥ 변수 — 판정층에 들어간 것", r"§3 에이전트 변수|\[classify\]|§5-4"),
    ("⑦ 시나리오·생존·등급", r"\[scenarios\]|\[survive\]|\[judgeorder\]"),
    ("⑧ 비용", r"\[solar\]|\[ledger\]|단가 미확인"),
)


def read(p: pathlib.Path) -> tuple[list[str], str]:
    """로그 → `(줄들, 카드)`. 🔴 카드는 `@@@CARD@@@` 뒤 전부다."""
    text = p.read_text(encoding="utf-8", errors="replace")
    head, _, card = text.partition("@@@CARD@@@")
    return head.splitlines(), card.strip()


def render(p: pathlib.Path, *, each: int = 14) -> str:
    lines, card = read(p)
    out = [f"# 봇이 단계별로 어떻게 예측했나 — `{p.name}`", ""]
    asked = next((x.split("@@@SENT@@@", 1)[1].strip()
                  for x in lines if "@@@SENT@@@" in x), "(물은 것을 못 찾았다)")
    out += [f"**물은 것**: `{asked}`", ""]
    for title, pat in STEPS:
        rx = re.compile(pat)
        got = [x for x in lines if rx.search(x)]
        out += [f"## {title}", ""]
        if not got:
            # 🔴 **조용한 0 금지** — 그 단계가 안 돌았다는 사실을 적는다
            out += ["🔴 **그 단계의 줄이 로그에 없다** — 안 돌았거나 사유가 "
                    "다른 이름으로 남았다", ""]
            continue
        keep = got if len(got) <= each else got[:each // 2] + \
            [f"… (가운데 {len(got) - each}줄 생략)"] + got[-(each // 2):]
        out += ["```"] + [x[:220] for x in keep] + ["```", ""]
    out += ["## ⑨ 카드 — 봇이 낸 결론", "", card or "🔴 **카드가 없다**"]
    return "\n".join(out)


if __name__ == "__main__":        # pragma: no cover
    for arg in sys.argv[1:]:
        print(render(pathlib.Path(arg)))
