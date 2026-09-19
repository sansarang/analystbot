"""[VEN-1] 구장을 받아 놓고 버리고 있었다.

🔴 `mlb.py:227` 이 `hydrate=probablePitcher,venue(location)` 로 **이미 받는다.**
   실측 응답:
     "venue": {"id": 4, "name": "Rate Field",
               "location": {"defaultCoordinates": {"latitude": 41.83, ...},
                            "elevation": 595, ...}}
   그런데 `_parse_games` 가 그 칸을 통째로 무시한다(주석이 "무시한다"고 적고
   있었다). 그래서 내보내기가 이렇게 적었다:
     "venue": {"name": null, "roof": null, "park_factor_runs": null,
               "reason": "…_parse_games 가 무시한다 — 저장 테이블 없음"}
🔴 쿠어스 9·9점을 걸러내려면 파크팩터가 있어야 한다. 값은 **지어내지 않고**
   MLB 자체 Baseball Savant 3년 롤링 지수를 받아 `config/park_factors.yaml`
   에 굳혔다(출처 URL 을 파일 머리말에 적었다).
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")


def test_구장_칸이_스키마에_있다():
    for col in ("venue_id", "venue_name"):
        assert re.search(rf"ADD COLUMN IF NOT EXISTS\s+{col}\b", SCHEMA), col


def test_파서가_구장을_버리지_않는다():
    import inspect

    from app.collectors import mlb as M

    assert hasattr(M, "_venue_of"), "구장 파서가 없다"
    assert '"venue_id"' in inspect.getsource(M._venue_of)
    assert "_venue_of" in inspect.getsource(M._parse_games), \
        "_parse_games 가 아직 venue 를 버린다"
    assert "venue_id" in inspect.getsource(M.upsert_games), \
        "파싱만 하고 저장하지 않는다"


def test_파크팩터_파일에_출처가_있다():
    """🔴 손으로 지어낸 값이 아님을 파일이 스스로 증명해야 한다."""
    txt = (ROOT / "config" / "park_factors.yaml").read_text(encoding="utf-8")
    assert "baseballsavant.mlb.com" in txt, "출처 URL 이 없다"
    assert "받은 날" in txt, "언제 받은 값인지 없다"


def test_쿠어스가_가장_높다():
    """⚠️ 값이 진짜인지 한 눈으로 확인하는 자리 — 쿠어스는 최고 득점 구장이다."""
    from app.engine.park import load_parks

    parks = load_parks()
    assert len(parks) >= 25, len(parks)
    top = max(parks.values(), key=lambda p: p["runs"])
    assert "Coors" in top["name"], top


def test_키는_이름이_아니라_id_다():
    """🔴 구장명은 바뀐다(Guaranteed Rate → Rate Field · Minute Maid → Daikin)."""
    from app.engine.park import load_parks

    assert all(isinstance(k, int) for k in load_parks()), "키가 정수 id 가 아니다"


def test_모르는_구장은_지어내지_않는다():
    from app.engine.park import park_of

    assert park_of(None) is None
    assert park_of(999999) is None
    got = park_of(19)
    assert got and got["runs"] == 125 and got["roof"] == "Open", got
