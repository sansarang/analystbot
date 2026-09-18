"""[v1.4] 상수 로더 — **`config/rules.yaml` 의 `flow:` 블록이 원본이다.**

🔴 **여기에 숫자를 적지 않는다.** `app/engine/rules.py` 가 이미 그 파일의
   유일한 로더이고, 이 모듈은 `flow.` 접두사를 붙여 그쪽에 넘기기만 한다.
   별도 `pipeline/rules.yaml` 을 만들면 문턱이 두 곳에 생긴다 — 그것이 사본이다.
⚠️ 순수 읽기다. 쓰기 함수를 만들지 않는다.
"""
from __future__ import annotations

from app.engine import rules as _R


def get(path: str, default=None):
    """`"gate_pp.agree"` → `config/rules.yaml` 의 `flow.gate_pp.agree`."""
    return _R.get(f"flow.{path}", default)


def vars_for(sport: str) -> dict:
    """종목별 조정 변수표. `{var: {"max_abs": float, "core": bool}}`.

    🔴 종목 이름은 `analysis_state.sport` 규약(`baseball|soccer`)이다 —
       리그 코드(kbo·npb·mlb)가 아니다.
    """
    return get(f"adjust_prior_pp.{(sport or '').lower()}", {}) or {}


def core_vars(sport: str) -> tuple:
    """핵심 변수만. ⑥ 채점의 `refuted >= 1` 판정이 이것을 본다."""
    return tuple(k for k, v in vars_for(sport).items()
                 if isinstance(v, dict) and v.get("core"))
