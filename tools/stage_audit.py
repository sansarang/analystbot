"""🔴🔴 **§1 단계 감사표 — 코드를 지우기 전에 측정한다**(지시서 2026-10-12(셋째)).

```
PYTHONPATH=. python tools/stage_audit.py                 # 정적 감사(호출·LLM·닿음)
PYTHONPATH=. python tools/stage_audit.py --log var/judge/gwangju4.log
```

> `tools/stage_audit.py` — 단계별 **호출 수 · LLM 호출 수 · 비용 · 시간 ·
> 확률/등급 닿음 여부** 표 → 처분 실행 → 점검표를 새 단계 목록으로 갱신.

🔴 **무엇을 어떻게 세나**
| 칸 | 어떻게 |
|---|---|
| 호출 | `app/` 안에서 그 단계 입구(`모듈.run` 등)를 부르는 자리 수(AST) |
| LLM | 그 모듈 **코드**에서 `app.core.llm`·`ask`·`rerank` 를 부르는 자리 수(D46) |
| 확률 닿음 | 그 모듈이 `probmodel`·`probfloor`·`sim` 에 **값을 준다**(수입 + 인자) |
| 등급 닿음 | 그 모듈이 `grade`·`stance`·`evals` 를 **고치는가** |
| 비용·시간 | 🔴 **라이브 실행 로그**에서만 나온다(`--log`) — 없으면 `⬜` 다 |

⚠️ 정적 감사는 *"부를 수 있다"* 를 세고, 로그는 *"그 경기에서 실제로 몇 번"* 을
   센다. **둘을 섞어 적지 않는다**(#3 · 조용한 0 금지).
"""
from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 🔴🔴 단계 목록 — **지시서 §1 표의 그 단계들**과 그 모듈
#  ⚠️ 번호는 흐름도의 번호다(사본이 아니라 **가리키는 이름표**다).
STAGES: tuple[tuple[str, str, str], ...] = (
    ("①", "질문 해석", "app/core/stages/s1_resolve.py"),
    ("③", "구조 사실", "app/core/stages/s2_facts.py"),
    ("③b", "기준 확률(Elo)", "app/core/stages/s2b_base.py"),
    ("③c", "시장", "app/core/stages/s2c_market.py"),
    ("⑩", "전략 판정(LLM)", "app/core/stages/s2d_strategy.py"),
    ("⑪", "상성 재료", "app/core/stages/s2e_matchup.py"),
    ("⑤", "문서", "app/core/stages/s3_docs.py"),
    ("⑥", "추출(LLM)", "app/core/stages/s4_extract.py"),
    ("⑦", "변수 배치", "app/core/stages/s5_verify.py"),
    ("⑱", "반증 딥서치", "app/core/stages/s5b_falsify.py"),
    ("⑭⑮", "가설·무너뜨릴 조건(LLM)", "app/core/stages/s6_hypo.py"),
    ("㉑", "보드 판정", "app/core/stages/s7_judge.py"),
    ("㉔", "최종 평·논평(LLM)", "app/core/stages/s9_say.py"),
    ("⑨", "우선순위 지수", "app/core/priority.py"),
    ("⑳", "시나리오 재가중", "app/core/reweight.py"),
    ("⑯", "확률", "app/core/probmodel.py"),
    ("⑯b", "λ 식", "app/core/probfloor.py"),
    ("⑳b", "이변 경고", "app/core/upset.py"),
    ("㉑b", "정보 품질", "app/core/infoquality.py"),
    ("㉓", "카드", "app/core/render.py"),
)

#: 🔴 LLM 을 부르는 글자 — ⚠️ 독스트링을 뺀 **코드**에서만 센다(D46)
LLM_WORDS = ("core.llm", "llm.ask", "llm.json", "_llm.", "rerank")

#: 🔴 확률에 값을 주는 자리 — 그 모듈이 이 이름을 **부르면** 닿는다
PROB_WORDS = ("probmodel", "probfloor", "sim.run", "score_grid")

#: 🔴 등급을 고치는 자리
GRADE_WORDS = ("grade", "stance", "evals")


def _code(path: Path) -> str:
    """🔴 D46 — **독스트링을 뺀 코드만**. 문서가 금지어를 설명하는 것과 코드가
    그것을 부르는 것은 다르다."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _callers(mod: str) -> int:
    """🔴 `app/` 안에서 그 모듈을 **부르는 파일 수**(자기 자신은 뺀다)."""
    name = Path(mod).stem
    got = 0
    for p in sorted((ROOT / "app").rglob("*.py")):
        if p.as_posix().endswith(mod):
            continue
        said = p.read_text(encoding="utf-8", errors="ignore")
        if re.search(rf"\b{name}\b", said):
            got += 1
    return got


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="", help="🔴 라이브 실행 로그(비용·시간)")
    args = ap.parse_args(argv[1:])
    print("# 🔴🔴 §1 단계 감사표 — **처분 전**(정적 측정)")
    print()
    print("| 단계 | 모듈 | 줄 | 부르는 파일 | **LLM 호출** | 확률 닿음 | "
          "등급 닿음 |")
    print("|---|---|---|---|---|---|---|")
    tot_llm = 0
    for num, name, rel in STAGES:
        p = ROOT / rel
        if not p.is_file():
            print(f"| {num} {name} | `{rel}` | ⬜ **파일 없다** | — | — | — | — |")
            continue
        code = _code(p)
        lines = len(p.read_text(encoding="utf-8").splitlines())
        llm = sum(code.count(w) for w in LLM_WORDS)
        tot_llm += llm
        prob = any(w in code for w in PROB_WORDS)
        grade = any(w in code for w in GRADE_WORDS)
        print(f"| {num} {name} | `{Path(rel).name}` | {lines} | "
              f"{_callers(rel)} | {'**' + str(llm) + '곳**' if llm else '0'} | "
              f"{'🔴 예' if prob else '아니다'} | "
              f"{'🔴 예' if grade else '아니다'} |")
    print()
    print(f"🔴 **LLM 을 부르는 자리 합 {tot_llm}곳** · 단계 {len(STAGES)}개")
    print()
    print("⚠️ 이 표는 *\"부를 수 있다\"* 를 센다 — **한 경기에서 몇 번**은 라이브")
    print("   로그가 말한다(`--log`). 두 수를 섞어 적지 않는다.")
    if args.log:
        said = Path(args.log)
        if not said.is_file():
            print(f"\n🔴 로그가 없다 — `{args.log}`")
            return 1
        text = said.read_text(encoding="utf-8", errors="ignore")
        print()
        print("## 라이브 실행에서 실제로(한 경기)")
        print()
        cost = re.findall(r"\[비용\] \$([\d.]+) · 호출 (\d+)", text)
        if cost:
            print(f"- 💵 **${cost[-1][0]}** · LLM 호출 **{cost[-1][1]}회**")
        for tag, pat in (("추출(⑥)", r"s4 .*추출"),
                         ("가설(⑭)", r"s6 가설|가설 \d+개"),
                         ("반증(⑱)", r"s5b\] 반증"),
                         ("전략(⑩)", r"전략 판정|라인업 전략"),
                         ("최종 평(㉔)", r"s9|최종 평")):
            print(f"- {tag} — 로그 줄 **{len(re.findall(pat, text))}개**")
        got_time = re.findall(r"(\d{2}:\d{2}:\d{2}),\d+", text)
        if len(got_time) >= 2:
            print(f"- ⏱ 벽시계 **{got_time[0]} → {got_time[-1]}**")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv))
