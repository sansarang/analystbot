"""🔴🔴 **22단계 파이프라인 점검표** — 실행 로그 하나를 읽어 단계별로 **산출물**을 뽑는다.

사용자 지시 2026-10-11: *"22단계 파이프라인 다운로드 폴더에 저장해줘... 제대로
분석이 되고 있는지 확인용이다."*

```
PYTHONPATH=. python tools/pipeline_report.py var/accept/min1.log [내보낼_경로.md]
```

🔴 **표식이 아니라 산출물로 센다**(실사고 2026-10-10): 로그 표식으로 세면 INFO 를
   안 찍는 단계가 *"건너뛴 것"* 으로 나온다 — 거짓 경보 다섯이 났다. 그래서 각 단계가
   **만든 칸**(카드 블록·로그 줄)을 보고, 그 **원문 한 줄**을 증거로 붙인다.
🔴 주인 모듈은 **있는지 확인한다** — 이름이 바뀌면 이 표가 먼저 빨개진다(사본 방지).
⚠️ 이 도구는 **읽기만** 한다. 봇을 돌리지 않는다(#12 — 돌리는 것은 `run_stage8.py`).
"""
from __future__ import annotations

import pathlib
import re
import sys

#: 🔴 (단계, 하는 일, 주인, 산출 표식)
#   ⚠️ 주인은 `app/core/...` 의 **실제 모듈**이다 — 아래 `_check_owners` 가 센다.
STAGES: tuple[tuple[str, str, str, str], ...] = (
    ("S0 경기 확정", "질문 → 그 경기 하나(② 팀 색인 → 팀 일정 사다리)",
     "app.core.stages.s1_resolve", r"^🏟 \*\*"),
    ("S1 구조 사실", "오늘 XI·포메이션·감독(확정/예상 상태를 함께)",
     "app.core.stages.s2_facts", r"\*\*2\. 기준 XI\*\*"),
    ("S1 결장·감독", "결장 명단과 사유·복귀 시점",
     "app.core.stages.s2_facts", r"\*\*2b\. 결장\*\*"),
    ("S1 기준 전력", "Elo·라인업 보정(①②) — 확률의 출처가 **아니다**(V1 검증으로 간다)",
     "app.core.stages.s2b_base", r"\*\*3c\. 기준 전력"),
    ("S1 딥서치", "하위 과제별 질의 → 문서(기사)",
     "app.core.stages.s3_docs", r"\[searx\]|\[bing-news\]"),
    ("S1 추출", "문서 → 변수 후보(LLM 스키마 강제)",
     "app.core.stages.s4_extract", r"\*\*4\. 뒤집는 변수\*\*"),
    ("S1V 변수 검증", "후보 → 변수(신원·날짜·유형 검사)",
     "app.core.stages.s5_verify", r"\*\*4\. 뒤집는 변수\*\*"),
    ("S1V 변수 배치", "변수 → 자리(axis0~3 · lambda_const · V1~V6 · hypo)",
     "app.core.routing", r"\*\*🔢 변수 \(배치 자리\)\*\*"),
    ("S1V 선수단 교체", "깃발①②③ · r 가중(확정 XI 전에는 **안 센다**)",
     "app.core.turnover", r"TURN-(home|away)|선수단 교체|평소 그대로|확정 XI 전"),
    ("S1 시장", "배당 피드 → 시장 열(표시용 · 등급은 **내리기만**)",
     "app.core.stages.s2c_market", r"\*\*7b\. 확률 세 열\*\*"),
    ("축2 전략 판정", "오늘 XI ↔ 평소 XI → 전략(로테이션·수비 위주·선수단 교체…)",
     "app.core.stages.s2d_strategy", r"\*\*🧠 라인업 전략"),
    ("전술 예측", "운영·흐름·승부처(근거 id 를 달아서)",
     "app.core.stages.s2f_tactic", r"\*\*🎓 전술 전문가 예측"),
    ("상성 재료", "골 내용·스타일 6축·폼 — 축의 재료",
     "app.core.stages.s2e_matchup", r"\*\*⚔️ 상성 세 축"),
    ("S2 상성 판정", "축0~3 → 종합(우위·강도)",
     "app.core.matchup", r"\*\*⚔️ MatchupReport \(전체\)\*\*"),
    ("S3 확률", "λ = 리그 평균 × 홈 배율 × exp(β·축) → **확률의 유일한 출처**",
     "app.core.probmodel", r"\*\*🎯 상성 확률 \(S3\)\*\*"),
    ("S3 시뮬", "λ → 분 단위 시뮬 → 스코어 분포·승무패·오버",
     "app.core.sim", r"\*\*🎲 시뮬 스코어 상위 10\*\*"),
    ("S4 가설", "변수 + 상성 → 팀별 가설(시뮬을 **보기 전에** 선다)",
     "app.core.stages.s6_hypo", r"\*\*5\. 팀별 가설"),
    ("S5 검증(가설↔시뮬)", "가설의 예측 신호를 시뮬 산출과 대조(지지·반박·판단 불가)",
     "app.core.stages.s6c_check", r"\*\*🧪 가설 검증표"),
    ("S5 검증표(V1~V7)", "상성 **밖** 정보(Elo·맞대결·동기·일정·시장) — 등급만 내린다",
     "app.core.stages.s6c_check", r"\*\*🔎 VerificationTable\*\*"),
    ("적합 정보", "계수가 적합됐나 — 아니면 **🔴 임시값**이라고 적는다",
     "tools.fit_matchup_model", r"\*\*🧮 적합 정보\*\*"),
    ("S6 시나리오", "시뮬 분포에서 시나리오 + 필수형 보강",
     "app.core.stages.s6_hypo", r"\*\*6\. 시나리오\*\*"),
    ("S8 보드 판정", "시나리오 ↔ 마켓 → 생존·상한·등급",
     "app.core.stages.s7_judge", r"\*\*7\. 보드 대입\*\*"),
    ("최종 평", "사실 묶음만으로 쓴 전문가 평(검열 포함)",
     "app.core.stages.s9_say", r"\*\*🧑‍🏫 최종 평"),
    ("결론·논평·방아쇠", "등급·종합 논평·방향·재계산 방아쇠",
     "app.core.stages.s8_comment", r"\*\*8\. 결론\*\*|\*\*10\. 방아쇠\*\*"),
)

#: 🔴 **조용한 실패**로 세는 말들(#3) — 있으면 그대로 적는다
BAD: tuple[str, ...] = (
    "Traceback", "🔴 터졌다", "llm_unavailable", "llm_truncated", "replay_miss",
    "🔴 **미배치**", "배치 실패", "match_not_found", "확정 XI 전",
    "리그 평균을 **모른다**", "우리 없음", "축0 ⬜", "템플릿",
)


def _check_owners() -> list[str]:
    """🔴 주인 모듈이 **실제로 있나** — 이름이 바뀌면 이 표가 먼저 빨개진다."""
    import importlib
    out = []
    for name, _what, owner, _pat in STAGES:
        try:
            importlib.import_module(owner)
        except Exception as exc:                            # noqa: BLE001
            out.append(f"{name} → `{owner}` 를 못 연다({exc!r})")
    return out


def _evidence(said: str, pat: str, *, width: int = 150) -> str:
    """🔴 그 단계가 **실제로 낸 줄** 한 개(없으면 빈 글자)."""
    hit = re.search(pat, said, re.M)
    if not hit:
        return ""
    line = said[hit.start():].split("\n", 1)[0].strip()
    return line[:width] + ("…" if len(line) > width else "")


def report(path: str) -> str:
    said = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    head = _evidence(said, r"^🏟 \*\*") or "(경기 줄 없음)"
    rows = [f"# {len(STAGES)}단계 파이프라인 점검표",
            "",
            "⚠️ 실행 중 감시는 **22줄**로 찍었다 — 이 표는 그 22줄에 `S1 기준 전력`과 "
            "`S3 시뮬`을 **따로 뗀 것**이라 두 줄이 더 많다(같은 파이프라인이다).",
            "",
            f"- 대상 실행: `{path}`",
            f"- 경기: {head}",
            "- 🔴 **표식이 아니라 산출물로 센다** — 각 단계가 만든 칸을 보고 그 "
            "원문 한 줄을 증거로 붙인다.",
            "", "## 단계별", "",
            "| # | 단계 | 하는 일 | 주인(코드) | 산출 | 증거(원문) |",
            "|---|---|---|---|---|---|"]
    gone: list[str] = []
    for i, (name, what, owner, pat) in enumerate(STAGES, 1):
        n = len(re.findall(pat, said, re.M))
        got = _evidence(said, pat).replace("|", "\\|")
        rows.append(f"| {i} | {name} | {what} | `{owner}` | "
                    f"{'✅ ' + str(n) + '건' if n else '🔴 0건'} | {got or '—'} |")
        if not n:
            gone.append(name)
    rows += ["", f"**건너뛴 단계: {gone or '없다'}**", "", "## 조용한 실패 표시", ""]
    said_bad = [f"- `{w}` {said.count(w)}건" for w in BAD if said.count(w)]
    rows += said_bad or ["- 없다"]
    bad_owner = _check_owners()
    rows += ["", "## 주인 모듈 확인", ""]
    rows += ([f"- 🔴 {x}" for x in bad_owner]
             or [f"- ✅ {len(STAGES)}단계의 주인 모듈이 **전부 열린다**"])
    rows += ["", "## 수치", ""]
    for key in ("벽시계", "비용", "예산 뒤"):
        one = _evidence(said, rf"\[§8 수치\] {key}.*")
        if one:
            rows.append(f"- {one}")
    return "\n".join(rows) + "\n"


if __name__ == "__main__":
    log = sys.argv[1]
    out = pathlib.Path(sys.argv[2] if len(sys.argv) > 2
                       else pathlib.Path(log).with_suffix(".report.md"))
    out.write_text(report(log), encoding="utf-8")
    print(f"적었다 — {out}")
