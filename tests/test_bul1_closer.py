"""[BUL-1] 마무리와 14일 방어율 — **코드 규칙으로 정한다, 이름표가 아니라.**

🔴 종전 내보내기:
     "closer": null, "closer_reason": "마무리 지정 저장 없음"
     "era_14d": null, "era_14d_reason": "14일 집계 없음"
   둘 다 `pitcher_appearances` 로 **계산되는 값**인데 안 하고 있었다.
🔴 마무리를 이름 목록으로 박지 않는다(09-14 "이름 매칭 금지"). **규칙**이다 —
   최근 14일에 그 팀 경기에서 **가장 마지막에 나온 횟수**가 많은 투수.
   그러려면 등판 순서가 필요한데, 파서는 이미 안다(`enumerate` 의 `i`)
   — 저장만 안 했다. PIT-1 과 같은 자리다.
🔴 연투 가능 여부(`available`)도 **모르면 None** 이다. "던질 수 있다"와
   "모른다"는 다르다.
"""
from __future__ import annotations

import pathlib
import re

SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "db" / "schema.sql"
          ).read_text(encoding="utf-8")


def test_등판_순서_칸이_있다():
    assert re.search(r"ADD COLUMN IF NOT EXISTS\s+app_order\b", SCHEMA)


def test_적재가_순서를_싣는다():
    import inspect

    from app.collectors import pitcher_log as P

    src = inspect.getsource(P)
    assert "app_order" in src.split("INSERT INTO pitcher_appearances")[1][:400]


def test_마무리는_마지막_등판_횟수로_정한다():
    from app.export.for_fable import pick_closer

    rows = [
        {"pitcher": "A", "d": "2026-09-18", "app_order": 5},
        {"pitcher": "B", "d": "2026-09-18", "app_order": 4},
        {"pitcher": "A", "d": "2026-09-17", "app_order": 6},
        {"pitcher": "C", "d": "2026-09-16", "app_order": 3},
        {"pitcher": "B", "d": "2026-09-16", "app_order": 4},
    ]
    assert pick_closer(rows) == "A", pick_closer(rows)


def test_순서를_모르면_마무리도_모른다():
    from app.export.for_fable import pick_closer

    assert pick_closer([{"pitcher": "A", "d": "2026-09-18", "app_order": None}]) is None
    assert pick_closer([]) is None


def test_연투는_어제_그제를_본다():
    from app.export.for_fable import closer_available

    rows = [{"pitcher": "A", "d": "2026-09-18"}, {"pitcher": "A", "d": "2026-09-17"}]
    assert closer_available("A", rows, today="2026-09-19") is False   # 이틀 연투
    rows2 = [{"pitcher": "A", "d": "2026-09-17"}]
    assert closer_available("A", rows2, today="2026-09-19") is True
    assert closer_available(None, rows, today="2026-09-19") is None


def test_era_14d_는_자책_이닝이다():
    from app.export.for_fable import era_14d

    rows = [{"innings": 3.0, "er": 1}, {"innings": 6.0, "er": 2}]
    assert era_14d(rows) == 3.0
    assert era_14d([{"innings": 0.0, "er": 0}]) is None
    assert era_14d([]) is None
