"""[DEC-4] 매체 **유형** — 등급이 아니라 사실.

🔴 **유형은 사실이고 등급은 의견이다.** 종전 `config/sources.yaml` 의 tier0~3
   은 "얼마나 믿나"인데, KBO 는 tier1 에 한 곳뿐이고 tier2 는 빈 목록이라
   실제 매체가 전부 `RANK_UNKNOWN` 이었다(D41). 등급을 내가 채우면 취향이다.
   "구단 공식인가"는 **근거 URL 로 확인되는 사실**이다.

🔴 **등급은 `official` 만 상위다.** 나머지는 전부 `unrated`(soft).
   승격은 `공식·라인업과의 일치율`이 **n≥20** 일 때 **후보**가 될 뿐이고,
   올리는 것은 **사용자**다. 이 파일에 자동 승격 경로는 없다.

⚠️ `config/sources.yaml`(tier0~3)을 건드리지 않는다 — **별개 축**이다.
   그쪽은 리그별 등급, 이쪽은 매체 유형.
⚠️ 아직 아무도 부르지 않는다. 이을 자리는 `scout_config.rank` 인데 그것은
   **승격 규칙이 정해진 뒤**다.
"""
from __future__ import annotations

import logging
import pathlib

logger = logging.getLogger(__name__)

_PATH = (pathlib.Path(__file__).resolve().parents[2]
         / "config" / "source_types.yaml")
_DOC: dict | None = None

#: 승격 **후보**가 되려면 이만큼의 표본이 있어야 한다(사용자 결정: n≥20).
MIN_SAMPLES = 20


def _doc() -> dict:
    global _DOC
    if _DOC is None:
        try:
            import yaml

            _DOC = yaml.safe_load(_PATH.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.warning("[source_types] %s 를 못 읽었다: %s", _PATH, exc)
            _DOC = {}
    return _DOC


def type_of(host: str) -> str | None:
    """이 도메인의 유형. 모르면 None. ⚠️ 모르는 것을 짐작하지 않는다."""
    row = (_doc().get("sources") or {}).get(str(host or "")) or {}
    return row.get("type")


def evidence_url(host: str) -> str | None:
    return ((_doc().get("sources") or {}).get(str(host or "")) or {}).get(
        "evidence_url")


def tier_of(host: str) -> str:
    """상위인가. 🔴 **`official` 만 `primary`** 이고 나머지는 전부 `unrated`.

    ⚠️ 모르는 도메인도 `unrated` 다 — **조용히 낮추지도 올리지도 않는다.**
       종전 `rank()` 는 모르는 것을 `RANK_UNKNOWN(9)` 으로 밀어 사실상 버렸다.
    """
    primary = tuple(_doc().get("primary_types") or ("official",))
    return "primary" if type_of(host) in primary else "unrated"


def promotion_candidate(host: str, *, agree: float, n: int) -> bool:
    """승격 **후보**인가. 🔴 후보일 뿐 승격이 아니다 — 올리는 것은 사용자다.

    조건: 표본 **n>=20** (`MIN_SAMPLES`) · 이미 상위가 아닐 것.
    ⚠️ `agree`(공식·라인업과의 일치율)는 **기록만** 한다. 문턱을 여기서 정하지
       않는다 — 그 값은 실측이 쌓인 뒤 사용자가 정한다.
    """
    if tier_of(host) == "primary":
        return False
    return int(n or 0) >= MIN_SAMPLES


def candidates(rows) -> list[dict]:
    """승격 후보 목록. ⚠️ **표시 전용**이다 — 이 함수는 아무것도 바꾸지 않는다."""
    out = []
    for r in (rows or []):
        h = r.get("host") or ""
        if promotion_candidate(h, agree=r.get("agree") or 0.0, n=r.get("n") or 0):
            out.append({"host": h, "type": type_of(h), "agree": r.get("agree"),
                        "n": r.get("n"), "needs": "사용자 승인"})
    return out
