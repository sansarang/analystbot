"""단계 잠금 — `config/stage_gate.yaml` 을 읽어 "무엇이 아직 잠겨 있나"를 낸다.

🔴 **v4 §13-2.** 승인 서명 파일이 없으면 다음 단계 테스트가 **수집조차 되지
   않는다.** 이 모듈이 그 판단을 하고, `conftest.pytest_ignore_collect` 가 그
   판단대로 경로를 버린다.

⚠️ 이름이 `test_` 로 시작하지 않으므로 pytest 가 이 파일을 계약으로 수집하지
   않는다. 계약은 `tests/test_stage_gate.py` 에 있다.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GATE_FILE = "config/stage_gate.yaml"


def load() -> dict:
    """잠금 표 원문."""
    return yaml.safe_load((ROOT / GATE_FILE).read_text(encoding="utf-8"))


def signature_of(gate: dict, cfg: dict) -> tuple[Path, str | None, str | None]:
    """(서명 파일 경로, ISO 시각, 사용자 메시지 원문).

    서명이 없으면 시각·메시지가 `None` 이다. 🔴 **파일이 있어도 `APPROVED` 줄이
    없으면 승인이 아니다** — 보고서만 써 두고 승인받지 않은 상태가 그것이다
    (실제로 있었던 일: 단계 1 보고서가 `> (대기)` 인 채로 코드가 커밋됐다).
    """
    path = ROOT / cfg["signature_dir"] / gate["requires"]
    if not path.exists():
        return path, None, None
    pat = re.compile(cfg["signature_pattern"], re.M)
    m = pat.search(path.read_text(encoding="utf-8"))
    if not m:
        return path, None, None
    return path, m.group(1), m.group(2)


def locks_of(stage: int) -> list[str]:
    """단계 N 이 잠그는 디렉터리. 🔴 **규칙이 정한다 — 표에 적지 않는다.**

    ⚠️ 리뷰 P4: 종전에는 `stage_gate.yaml` 에 `locks: [tests/stage3]` 같은 줄이
       여덟 개 있었고 계약이 그것을 이 규칙과 대조했다. 보장은 같았으나 **손
       유지 항목이 여덟 개**였다. 여기서 계산하면 0 이다.
    """
    return [f"tests/stage{stage}"]


def locked_dirs() -> dict[str, dict]:
    """{잠긴 디렉터리(저장소 상대): 왜 잠겼나}.

    승인 서명이 **있는** 단계는 여기 나오지 않는다 — 열린 것이다.
    """
    cfg = load()
    out: dict[str, dict] = {}
    for gate in cfg["gates"]:
        path, when, _msg = signature_of(gate, cfg)
        if when is not None:
            continue
        for d in locks_of(gate["stage"]):
            out[d] = {
                "stage": gate["stage"],
                "requires": str(path.relative_to(ROOT)),
                "why": (f"단계 {gate['stage']} 는 단계 {gate['stage'] - 1} 승인 "
                        f"서명이 있어야 열린다 (v4 §13-2). "
                        f"{path.relative_to(ROOT)} 에 `APPROVED <ISO시각> "
                        f"<사용자 메시지 원문>` 줄이 없다."),
            }
    return out


def is_locked(path: Path) -> dict | None:
    """이 경로가 잠긴 디렉터리 안에 있나. 있으면 이유를, 없으면 `None`."""
    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        return None  # 저장소 밖 — 우리가 판단할 것이 아니다
    for d, why in locked_dirs().items():
        if rel == Path(d) or Path(d) in rel.parents:
            return why
    return None
