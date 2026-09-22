"""[LE-1a / learning_engine_0922] 학습 엔진.

🔴 **상수의 원본은 `config/learning.yaml` 하나다**(지시문 §1). 이 모듈의 `get`
   이 그것을 읽는 유일한 통로다 — 다른 곳에서 yaml 을 다시 열지 않는다.
   ⚠️ `app.engine.rules` 는 `config/rules.yaml` 을 읽는다. **다른 파일이다.**

🔴 **여기에 기본값을 박지 않는다.** 파일이 없으면 `None` 을 돌려주고 경고를
   남긴다 — 조용히 내장 기본값으로 도는 것이 CFG-1 사고였다(설정 파일이 배포
   이미지에 안 올라갔고 첫 사이클 실측이 잡았다).
"""
from __future__ import annotations

import logging
import pathlib

logger = logging.getLogger(__name__)

CONFIG_PATH = (pathlib.Path(__file__).resolve().parents[2]
               / "config" / "learning.yaml")

_DOC: dict | None = None


def load(force: bool = False) -> dict:
    """설정 전체. 한 번 읽고 캐시한다."""
    global _DOC
    if _DOC is not None and not force:
        return _DOC
    if not CONFIG_PATH.exists():
        logger.warning("[learning] 🔴 %s 가 없다 — 상수를 못 읽는다. 배포 "
                       "이미지에 config/ 가 올라갔는지 확인하라(CFG-1)",
                       CONFIG_PATH)
        _DOC = {}
        return _DOC
    try:
        import yaml

        _DOC = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("[learning] 🔴 %s 읽기 실패: %s", CONFIG_PATH, exc)
        _DOC = {}
    return _DOC


def get(path: str, default=None):
    """`"learning.min_samples"` → 점으로 내려간다. 없으면 `default`."""
    cur = load()
    for part in str(path or "").split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur if cur is not None else default
