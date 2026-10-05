"""단계 2 계약이 사는 곳 — 🔴 **이 디렉터리는 `stage_gate` 가 잠근다.**

`config/stage_gate.yaml` 의 `stage: 2` 항목이 `docs/fable/stages/v4_1_done.md` 의
`APPROVED` 줄을 요구한다. 그 줄이 없으면 이 파일은 **수집조차 되지 않는다**
(v4 §13-2).

⚠️ 단계 2 **본체**(pydantic 타입 7종·스키마 9표·`variable_types.yaml`·
   `scenario_rules.yaml`·계약 C1~C11)는 아직 없다. 지금 있는 것은 2-0 의
   산출물, 즉 **잠금 그 자체**뿐이다.
"""
from __future__ import annotations

import tests.stage_gate as SG


def test_이_파일이_수집된_것이_단계_1_승인의_증거다():
    """🔴 잠금의 자기 검증 — 이 계약이 **도는 것 자체**가 증거다.

    단계 1 승인 서명이 없으면 `pytest_ignore_collect` 가 이 파일을 버리므로
    이 함수는 아예 수집되지 않는다. 즉 **초록이면 서명이 있다.**

    ⚠️ 그래서 이 계약은 스스로 "서명이 있나"를 다시 확인하지 않는다 — 그러면
       잠금을 우회하고도 초록일 수 있다(수집이 되었는데 서명을 따로 읽는 꼴).
       대신 **잠금 표가 이 디렉터리를 실제로 지목하는지**를 본다. [§13-2]
    """
    cfg = SG.load()
    gate = next(g for g in cfg["gates"] if g["stage"] == 2)
    assert "tests/stage2" in SG.locks_of(2), \
        "이 디렉터리가 잠금 대상이 아니다 — 잠기지 않은 채 돌고 있다"
    assert gate["requires"] == "v4_1_done.md"


def test_단계_2_는_지금_열려_있다():
    """단계 1 이 승인됐으므로 `locked_dirs()` 에 `tests/stage2` 가 없어야 한다. [§13-2]"""
    assert "tests/stage2" not in SG.locked_dirs(), \
        "열려 있어야 하는데 잠겼다고 나온다"


def test_승인_안_된_단계는_아직_잠겨_있다():
    """🔴 §13-2 — 앞 단계 코드를 미리 쓰지 못한다.

    ⚠️ **이것이 잠금이 살아 있다는 증거다.** 전부 열려 있으면 잠금은 장식이다.
    🔴 **번호를 손으로 적지 않는다.** 종전 판은 `[3,4,5,6,7,8,9]` 와
       `"tests/stage3" in locked` 를 박아 뒀고, 단계 2 승인이 들어오자
       **정상 동작인데 빨개졌다**(실측 2026-09-30 · 리뷰 N3). [§13-2]
    """
    cfg = SG.load()
    want = sorted(g["stage"] for g in cfg["gates"]
                  if SG.signature_of(g, cfg)[1] is None)
    stages = sorted(v["stage"] for v in SG.locked_dirs().values())
    assert stages == want, f"잠긴 단계가 서명 상태와 다르다: {stages} ≠ {want}"
    assert stages, "잠긴 단계가 하나도 없다 — 잠금이 장식인지 확인하라"
    # 🔴 단계 2 는 열려 있어야 한다 (이 파일이 수집된 것이 그 증거이기도 하다)
    assert 2 not in stages
