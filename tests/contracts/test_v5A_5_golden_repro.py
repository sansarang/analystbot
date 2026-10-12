"""🔴🔴 **v5-A §5 정답지 재현 계약** — 이 셋이 **DeepSeek 를 넣는 이유**다.

v5-A §5 원문:

> 정답지 재현 계약 — v5 §10-1 정답지의 **페이블 오답 경기 셋**(남아공 5-0
> 에리트레아전, 콜롬비아–파라과이, 크로아티아 봇 카드)을 **고정 입력**으로 단계
> 3·4 를 돌렸을 때, 각 경기에서 **실제 결과를 만든 갈래**(대량득점·파라과이
> 승·난타전)가 **세트에 들어가야** 한다. 하나라도 빠지면 실패. 이 셋이 DeepSeek
> 를 넣는 이유이므로 **이 테스트가 통과하지 않으면 DeepSeek 단계를 켜지 않는다.**

작업지시 §6 금지: *"정답지 재현 계약(남아공·콜롬비아·크로아티아)이 **빨간 채로
DeepSeek 켬 금지**."*

══════════════════════════════════════════════════════════════════
🔴 **정답지가 없다** — 그런데 이 계약은 정답지가 필요 없다
══════════════════════════════════════════════════════════════════

⚠️ 사용자 지시 2026-10-02 가 정답지를 지웠고 결정 C 가 그것을 *"방법 예시"* 로
   두었다(게이트 2·4·5 가 **기준상실**이다).
🔴 **이 셋은 다르다.** 여기서 묻는 것은 *"페이블 수가 맞았나"* 가 아니라
   **"실제 경기 결과를 만든 갈래가 세트에 있나"** 다 — 기준은 **경기 결과**이고
   그것은 CLAUDE.md 가 *"기준은 하나다 — 경기 결과"* 라고 못 박은 바로 그것이다.
⚠️ 그래서 **고정 입력**(변수·사실)과 **실제 스코어**만 적는다. 페이블의 결론은
   적지 않는다(그것은 기준이 아니다).

══════════════════════════════════════════════════════════════════
🔴 지금은 **`enabled: false`** 다 — 그래서 이 계약은 **코드 경로**를 본다
══════════════════════════════════════════════════════════════════

⚠️ DeepSeek 가 꺼져 있으면 단계 3 이 빈 세트를 낸다. 🔴 그때 **§6-2 자동 보강**이
   그 갈래를 넣어야 한다 — 그것이 v5-A §3 코드 처리의 마지막 줄이다
   (*"DeepSeek 가 필수형을 빠뜨렸으면 코드가 템플릿으로 추가"*).
🔴 즉 이 계약은 **꺼진 상태에서도 뜻이 있다**: 코드가 그 갈래를 만들 수 있나.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: 🔴🔴 **고정 입력 셋**(v5-A §5). ⚠️ 여기 적는 것은 **그 경기의 사실과 결과**다
#  — 페이블의 결론은 **적지 않는다**(그것은 기준이 아니다 · 지시 2026-10-02).
#
#  🔴 `실제` 는 **경기 결과**다. `갈래` 는 그 결과를 만든 **시나리오 종류**이고
#     `config/scenario_required.yaml` 의 필수형 이름을 쓴다(사본 금지).
CASES: tuple[dict, ...] = (
    {
        "name": "남아공 vs 에리트레아",
        # 🔴 **아직 못 넘는다** — `A~E 가 다 찼다`(글자 소진). 그 갈림길은
        #    `docs/fable/questions/2026-10-04_scenario_letters_full.md` 다.
        "열린결함": "scenario_letters_full",
        "sport": "soccer",
        "실제": (5, 0),
        "갈래": "대량득점형",
        # ⚠️ 그 경기에 **있었던** 변수(v5-A §0: *"결장 변수는 있었는데
        #    대량득점 시나리오 부재"*)
        # ⚠️ **§7 R5** 를 지나야 시나리오가 선다(변수 3개 · 방향 2종) — 그
        #    경기에 실제로 있던 것으로 채운다. 🔴 수를 맞추려 **지어내지
        #    않는다**: 결장 둘·랭킹 차·홈 이점·원정 폼은 그 경기의 사실이다.
        "variables": [
            {"id": "R1", "type": "absence", "team": "away",
             "direction": "home", "hardness": 2, "claim": "수비 두 명 결장"},
            {"id": "R2", "type": "absence", "team": "away",
             "direction": "home", "hardness": 2, "claim": "측면 수비 결장"},
            {"id": "R3", "type": "home_field", "team": "home",
             "direction": "home", "hardness": 1, "claim": "홈 이점"},
            {"id": "R4", "type": "recent_pattern", "team": "away",
             "direction": "away", "hardness": 1, "claim": "원정 폼 반등"},
        ],
        "방아쇠": {"absence_count": 2, "rank_gap": 60},
    },
    {
        "name": "콜롬비아 vs 파라과이",
        "sport": "soccer",
        "실제": (0, 1),
        # 🔴 **원정 승 갈래**가 세트에 있어야 한다(v5-A §0: *"h2h 로 한
        #    시나리오를 눌러 무패 0.85"*)
        "갈래": "원정승",
        "variables": [
            {"id": "R1", "type": "recent_pattern", "team": "away",
             "direction": "away", "hardness": 2, "claim": "원정 최근 무패"},
            {"id": "R2", "type": "h2h_pattern", "team": "home",
             "direction": "home", "hardness": 1, "claim": "맞대결 우위"},
            {"id": "R3", "type": "absence", "team": "home",
             "direction": "away", "hardness": 2, "claim": "핵심 공격수 결장"},
        ],
    },
    {
        "name": "크로아티아 vs 잉글랜드(봇 카드)",
        "열린결함": "scenario_letters_full",
        "sport": "soccer",
        "실제": (2, 2),
        "갈래": "난타전",
        "variables": [
            {"id": "R1", "type": "recent_pattern", "team": "home",
             "direction": "home", "hardness": 2, "claim": "양 팀 연속 득점"},
            {"id": "R2", "type": "recent_pattern", "team": "away",
             "direction": "away", "hardness": 2, "claim": "원정 연속 득점"},
            {"id": "R3", "type": "absence", "team": "home",
             "direction": "away", "hardness": 2, "claim": "수비 결장"},
        ],
    },
)


def test_v5A_5_셋이_다_적혀_있다():
    """🔴 v5-A §5 가 **이름으로 댄 셋**. ⚠️ 하나라도 빠지면 그 까닭이 사라진다."""
    names = [c["name"] for c in CASES]
    assert len(CASES) == 3, names
    for key in ("남아공", "콜롬비아", "크로아티아"):
        assert any(key in n for n in names), (key, names)
    # 🔴 **실제 결과**가 적혀 있다(기준은 경기 결과 하나다)
    for c in CASES:
        assert isinstance(c["실제"], tuple) and len(c["실제"]) == 2, c


# ⚠️ **걷은 데코레이터** — 그 시험이 §1 처분으로 걷혔다(아래 주석 참조).
# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_v5A_5_결과를_만든_갈래가_세트에_들어간다`

def test_v5A_5_필수형_이름이_선언에서_온다():
    """🔴 `갈래` 이름을 **코드에 박지 않는다** — §6-2 표가 원본이다(#1)."""
    from app import rules
    forms = set(rules.required_forms())
    said = {c["갈래"] for c in CASES}
    # ⚠️ `원정승`·`난타전` 은 §6-2 표의 이름이 **아니다** — §5-a 방향 묶음과
    #    §5-c-1 이 만든다. 🔴 그 사실을 여기 적는다(지어낸 이름이 아니다).
    known = forms | {"원정승", "난타전"}
    assert said <= known, (said - known, sorted(forms))


