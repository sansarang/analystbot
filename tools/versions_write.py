"""🔴🔴 **계수 판 쓰기** — 사용자 지시 2026-10-12(3번 · L3)의 **도구 쪽 절반**.

🔴 왜 도구에 있나 — 앱은 **읽기만** 한다(계약 `test_설정_yaml_을_코드가_쓰지_
   않는다`). 판을 만드는 것은 적합 도구의 일이고, 운영은 그 판을 고를 뿐이다
   (`app/core/versions.pick`).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("versions_write")


def write(table: str, key: str, *, day, body: dict, head: str = ""):
    """🔴 판을 적는다 — `data/<표>/<열쇠>/<as_of>.yaml`. 덮어쓰지 않는 길이다."""
    import yaml

    from app.core import versions as vz
    box = vz.path_of(table, key)
    box.mkdir(parents=True, exist_ok=True)
    said = day.isoformat() if hasattr(day, "isoformat") else str(day)
    out = box / f"{said[:10]}.yaml"
    out.write_text((head + "\n" if head else "")
                   + yaml.safe_dump(dict(body), allow_unicode=True,
                                    sort_keys=False), encoding="utf-8")
    logger.info("[versions] 판을 적었다 — %s", out)
    return out
