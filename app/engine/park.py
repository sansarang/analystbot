"""[VEN-1] 구장 파크팩터 — `config/park_factors.yaml` 이 원본이다.

🔴 값을 코드에 적지 않는다. yaml 이 출처 URL·받은 날짜를 머리말에 갖고 있고,
   여기서는 **읽기만** 한다.
🔴 키는 **statsapi venue id** 다 — 구장명은 바뀐다(Guaranteed Rate → Rate
   Field · Minute Maid → Daikin Park, 둘 다 2026-09-19 응답에서 확인).
⚠️ 모르는 구장은 **None** 이다. 리그 평균 100 으로 메우지 않는다 — 채운 구장과
   안 채운 구장이 같아 보이면 읽는 쪽이 오분류한다.
"""
from __future__ import annotations

import functools
import logging
import pathlib

logger = logging.getLogger(__name__)

PATH = pathlib.Path(__file__).resolve().parents[2] / "config" / "park_factors.yaml"

#: 지수의 기준. 🔴 **100 이 리그 평균**이다(비율이 아니라 지수).
SCALE_NOTE = "100 = 리그 평균 (Baseball Savant 3년 롤링 지수)"


@functools.lru_cache(maxsize=1)
def load_parks() -> dict:
    """`{venue_id: {name, runs, hr, roof, pa}}`. 못 읽으면 빈 dict."""
    try:
        import yaml

        doc = yaml.safe_load(PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("[park] %s 못 읽음: %s", PATH, exc)
        return {}
    out = {}
    for k, v in (doc.get("parks") or {}).items():
        try:
            out[int(k)] = dict(v)
        except (TypeError, ValueError):
            continue
    return out


def park_of(venue_id) -> dict | None:
    """그 구장의 값. 🔴 모르면 None — 지어내지 않는다."""
    if venue_id is None:
        return None
    try:
        return load_parks().get(int(venue_id))
    except (TypeError, ValueError):
        return None
