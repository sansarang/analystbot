"""🔴🔴 **유형 규칙표 회귀** — 산문의 사건 낱말 → §4 유형(사용자 기술 지시 2026-10-03).

> ② 유형 판정 (코드 규칙표) — 사건 단어 → 변수 유형. **LLM이 아니라 표로 정한다.**
> ④ 회귀 테스트 — 오늘 사실들을 **고정 입력**으로 넣고, 기대 변수가 나오는지 확인한다.

══════════════════════════════════════════════════════════════════
🔴🔴 **이것은 정답지가 아니다**
══════════════════════════════════════════════════════════════════

사용자 지시 2026-10-02: *"정답지는 없다... 정답지는 지운다..."* — 그것은 **경기
결과를 맞혔나**에 대한 말이다. 🔴 여기 있는 것은 *"**규칙표가 제가 적힌 대로
도는가**"* 이고, 답은 **표 자신**이 정한다(경기 결과가 아니다).

| 무엇 | 어디 |
|---|---|
| 우리가 적은 것이 **맞았나** | `ledger` · 경기 결과 — 🔴 **여기가 아니다** |
| 규칙표가 **제 말대로 하나** | 이 파일 |

⚠️ 기대값이 틀렸다고 판명되면 **기대값을 고친다** — 그것은 측정이지 정답지가 아니다.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app import classify, rules

ROOT = Path(__file__).resolve().parents[1]

#: 🔴 **고정 입력**. 사용자가 준 문장 + 라이브에서 **실제로 나온** 문장이다.
#   ⚠️ 지어낸 문장을 넣지 않는다 — 안 나오는 글로 표를 맞추면 그 표가 거짓이 된다.
GOLDEN: list[tuple[str, tuple[str, ...], str]] = [
    # ── 사용자 분석 2026-10-03 (KBO)
    ("전민재는 9/30 홈 슬라이딩 중 오른 팔꿈치 타박, 송구 불편으로 선발 라인업에 제외",
     ("absence",), "사용자 분석 2026-10-03"),
    ("카라스코 4이닝 2피안타 6탈삼진 무실점 … 노게임",
     ("pitcher_state",), "사용자 분석 2026-10-03"),
    ("LG 5연패 … 9회말 4실점 끝내기 패",
     ("recent_pattern",), "사용자 분석 2026-10-03"),
    # 🔴 **한 문장이 둘을 말한다** — 사용자가 직접 그렇게 셌다
    #    (*"매직+4연승(stakes·recent_pattern)"*)
    ("KT 매직 넘버 2 … 4연승",
     ("recent_pattern", "stakes"), "사용자 분석 2026-10-03 — 둘을 함께 센다"),
    ("고영표 다승 1위 경쟁", ("individual",), "사용자 분석 2026-10-03"),
    ("감독 반드시 이긴다 총력전", ("lineup_intent",), "사용자 분석 2026-10-03"),
    # ── 라이브에서 실제로 나온 글
    ("가쿠나카 은퇴 경기 선발 기용", ("event_match",), "실측 2026-10-02 NPB"),
    ("비 가능성이 있습니다. 출발 전 최신 예보를 다시 확인하세요.",
     ("venue_weather",), "실측 2026-10-03 — 이 글이 **감독 발언**으로 들어왔었다"),
    ("Jamaica defender ruled out with injury",
     ("def_absence",), "실측 2026-10-03 — 좁은 유형이 넓은 유형을 이긴다"),
    ("監督 辞任 … 新監督 就任", ("coach_change",), "실측 2026-10-02 NPB"),
    # ── 🔴 **안 맞아야 하는 것**도 넣는다. 오탐이 더 해롭다
    ("43전 4승", (), "사용자 지적 — 숫자만으로는 유형이 아니다"),
    ("경기장 주차 안내 및 입장 시간 공지", (), "오탐 방지"),
]


@pytest.mark.parametrize("text,want,src", GOLDEN,
                         ids=[g[0][:22] for g in GOLDEN])
def test_고정_입력이_기대_유형을_낸다(text, want, src):
    got, why = classify.types_from_text(text)
    assert tuple(sorted(got)) == tuple(sorted(want)), (
        f"{src}\n  글: {text}\n  나온 것: {got}\n  사유: {why}")


def test_표는_yaml_에서_자란다():
    """🔴 CLAUDE.md #1 — 유형 이름을 **코드에 적지 않는다**.

    ⚠️ 표를 코드에 두면 yaml 에 유형이 늘 때 한 발 늦고, 그 유형은 **영원히 0**
       으로 보인다(그 사실이 안 보이면 "자료가 없다"로 오진한다).
    """
    src = (ROOT / "app" / "classify.py").read_text(encoding="utf-8")
    code = "\n".join(
        ast.unparse(n) for n in ast.parse(src).body
        if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)))
    assert "rules.type_patterns()" in code
    # 🔴 유형마다 패턴이 **하나라도** 있어야 한다 — 없으면 그 유형은 산문에서 못 온다
    have = {n for n, _ in rules.type_patterns()}
    missing = sorted(set(rules.variable_types()) - have)
    assert not missing, f"`match:` 가 없는 유형 — 산문에서 영영 안 잡힌다: {missing}"


def test_좁은_유형이_넓은_유형을_이긴다():
    """🔴 `def_absence ⊂ absence` — 둘 다 맞으면 **모순이 아니라 포함**이다.

    ⚠️ 그 관계는 **yaml 이 선언한다**(`refines:`) — 코드가 유형 이름 쌍을 외우지
       않는다. 새 유형이 다른 유형을 좁히면 yaml 한 줄로 끝난다.
    """
    assert (rules.variable_types()["def_absence"] or {}).get("refines") == "absence"
    got, why = classify.types_from_text("센터백 부상으로 결장")
    assert got == ("def_absence",), (got, why)
    assert "좁은 쪽" in why


def test_질문_경로가_유형을_주면_그쪽이_이긴다():
    """🔴 산문 표는 **대체**다(§19-b-4 와 같은 결) — 세포는 자기가 뭘 묻는지 안다.

    ⚠️ 표가 질문 경로를 덮으면, 세포가 정확히 물어 받은 답을 **낱말 추측**이
       뒤집는다.
    """
    import inspect
    src = inspect.getsource(classify.classify_fact)
    i, j = src.index("types_for("), src.index("types_from_text(")
    assert i < j, "산문 표가 질문 경로보다 먼저 돈다"


def test_종목을_가리지_않는다():
    """🔴🔴 사용자 지시 2026-10-03: *"야구뿐만 아니라 **전경기**다."*

    ⚠️ 한 유형의 패턴이 한 언어·한 종목에만 있으면 다른 종목에서 **영영 0** 이다.
    🔴 적어도 **한국어 밖 패턴이 하나는** 있어야 한다 — 봇은 en/es/ja/zh 로도 읽는다.
    """
    import re as _re
    hangul = _re.compile(r"[가-힣]")
    only_ko = []
    for name, pats in rules.type_patterns():
        if not any(not hangul.search(p.pattern) for p in pats):
            only_ko.append(name)
    assert not only_ko, (
        f"한국어 패턴만 있는 유형 — 다른 언어 기사에서 영영 안 잡힌다: {only_ko}")
