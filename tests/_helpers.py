"""테스트 공용 헬퍼 — 🔴 **계약이 아니다.** 이름이 `test_` 로 시작하지 않는다.

⚠️ 리뷰 N8: `strip_docs` 가 `tests/test_wiring.py` 에 살아서, 그것을 쓰는
   다른 계약 파일이 **테스트 모듈을 import** 해야 했다(그 모듈의 `app` 전체
   import 가 딸려 오고, 파일을 옮기면 같이 깨진다). 사본을 만들지 않으면서
   결합을 끊는 자리가 여기다.
"""
from __future__ import annotations

import ast
import re


def strip_docs(src: str) -> str:
    """독스트링·주석을 뺀 코드만.

    🔴 **D46 — 이 저장소에서 네 번 다친 자리.** 주석이 금칙 이름을 *설명하는*
       것과 코드가 그것을 *부르는* 것은 다르다. 2026-09-29 에도 `legacy DB 이름
       0건` 계약이 내 주석에 걸려 빨개졌다.
    ⚠️ `ast.get_source_segment` 는 쓰지 않는다 — col_offset 이 바이트라 한글
       줄에서 터진다.
    """
    lines = src.splitlines()
    kill: set[int] = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return re.sub(r"#.*", "", src)
    for n in ast.walk(tree):
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) \
                and isinstance(n.value.value, str):
            kill.update(range(n.lineno - 1, (n.end_lineno or n.lineno)))
    return re.sub(r"#.*", "",
                  "\n".join("" if i in kill else ln
                             for i, ln in enumerate(lines)))


# ══════════════════════════════════════════════════════════════════
# v4 단계 1 — 폐기된 배선의 계약은 함께 갔다
# ══════════════════════════════════════════════════════════════════
#
# 🔴 지운 계약 9건: 스케줄러·봇이 `run_slate` 를 부르나 · `send_card` 상한 ·
#    미발송 사유 · 흐름이 소스를 전부 부르나(`motivation`·`close_counter`·
#    `lineup_confirmed` 포함) · 판정 단계가 전부 불리나 · 재판정이 방아쇠를
#    평가하나 · 채점 태그 배선 · 수집이 흐름보다 먼저 도나.
#    그 배선이 가리키던 코드가 v4 §8 폐기 목록이다.
#
# ⚠️ 그 자리에 들어갈 계약은 **단계 6~8** 에서 짓는다(시나리오·생존·카드·재실행).
#    지금 "수집이 무엇을 부르나"만 남긴다.



def strip_sh(src: str) -> str:
    """🔴 **쉘 주석을 뺀 코드만** — D46 을 `.sh` 에도 쓴다.

    ⚠️ 실사고 2026-10-04: `tools/mutate.sh` 계약이 **내가 쓴 설명 주석**에
       걸려 빨개졌다 — 주석이 *"종전엔 `cp` 였다"* · *"`git stash` 는 금지"* 를
       **설명**하는데, 계약은 그것을 코드가 **부른다**고 읽었다.
    🔴 파이썬에서 네 번 다친 그 자리(D46)와 **같은 병**이고, 그래서 같은 답을
       쓴다 — 검사는 **코드만** 본다.

    ⚠️ 문자열 안의 `#` 는 못 가린다(쉘은 파싱이 어렵다). 🔴 그래서 이 함수는
       *"주석을 지운다"* 까지만 하고, **더 똑똑한 척하지 않는다** — 쓰는 쪽이
       그 한계를 알고 쓴다.
    """
    out = []
    for raw in str(src or "").splitlines():
        s = raw.lstrip()
        if s.startswith("#"):
            continue            # 🔴 주석 줄 — 통째로 버린다
        out.append(raw.split(" #", 1)[0] if " #" in raw else raw)
    return "\n".join(out)
