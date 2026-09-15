"""[U13 2026-09-15] 상수표 로더 — `config/rules.yaml` 이 원본이다.

🔴 **모듈 상수를 여기서도 적지 않는다.** 이 파일에 있는 `_FALLBACK` 은
   yaml 이 사라졌을 때 봇이 죽지 않게 하는 **최후 수단**이고, 그 경우
   WARNING 을 남긴다 — 조용히 기본값으로 도는 것이 CFG-1 사고였다
   (설정 파일이 배포 이미지에 안 올라갔고 첫 사이클 실측이 잡았다).
🔴 **값 변경은 사용자가 한다.** 코드가 이 파일의 숫자를 고치지 않는다.
⚠️ 순수 읽기다. 쓰기 함수를 만들지 않는다.
"""
from __future__ import annotations

import logging
import pathlib

logger = logging.getLogger(__name__)

RULES_PATH = pathlib.Path(__file__).resolve().parents[2] / "config" / "rules.yaml"

#: 🔴 yaml 이 **없을 때만** 쓰인다. 여기 값을 보고 판단하지 마라 —
#   원본은 `config/rules.yaml` 이다. 이 표는 "파일이 사라져도 죽지 않는다"는
#   뜻이지 "값이 두 벌 있다"는 뜻이 아니다(없으면 경고가 뜬다).
_FALLBACK: dict = {
    "adjust": {"out_mult": 1.5, "out_cap": 6.0, "return_mult": 1.5,
               "min_contrib_pp": 2.0, "recent_starts_n": 10},
    "odds_move": {"steam_min_books": 3, "steam_min_pp": 3.0,
                  "disagree_sd_pp": 2.0, "line_pp_per_half": 4.0},
    "structure": {"edge_min_pp": 6.0, "grade_high_pp": 8.0,
                  "ah_lines": [0.5, 1.0, 1.5]},
    "hypothesis": {"sufficient_default": 2, "sufficient_bigmatch": 3,
                   "unknown_board_ratio": 0.5},
    "prob": {"adj_shrink": 0.5, "adj_sum_cap": 6.0},
    "cases": {"weights": {"league_group": 0.25, "gap_bucket": 0.30,
                          "confirmed": 0.30, "rest_bucket": 0.15}},
    "report": {"checkpoints": [50, 150, 300]},
}

_DOC: dict | None = None
_FROM_FILE = False


def load(force: bool = False) -> dict:
    """상수표 전체. 한 번 읽고 캐시한다."""
    global _DOC, _FROM_FILE
    if _DOC is not None and not force:
        return _DOC
    if not RULES_PATH.exists():
        logger.warning("[rules] 🔴 %s 가 없다 — 내장 기본값으로 돈다. "
                       "배포 이미지에 config/ 가 올라갔는지 확인하라(CFG-1)",
                       RULES_PATH)
        _DOC, _FROM_FILE = dict(_FALLBACK), False
        return _DOC
    try:
        import yaml

        doc = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("[rules] 🔴 %s 읽기 실패 — 내장 기본값: %s",
                       RULES_PATH, exc)
        _DOC, _FROM_FILE = dict(_FALLBACK), False
        return _DOC
    _DOC, _FROM_FILE = doc, True
    return _DOC


def from_file() -> bool:
    """지금 값이 **파일에서** 왔는가. 계약·진단이 본다."""
    load()
    return _FROM_FILE


def get(path: str, default=None):
    """`"adjust.out_mult"` 처럼 점으로 찾는다.

    🔴 없는 키는 **내장 기본값**을 보고, 거기도 없으면 `default` 다.
       0 으로 읽지 않는다 — 없는 것과 0 은 다르다.
    """
    keys = [k for k in str(path or "").split(".") if k]
    if not keys:
        return default
    for src in (load(), _FALLBACK):
        cur = src
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                cur = None
                break
            cur = cur[k]
        if cur is not None:
            return cur
    return default
