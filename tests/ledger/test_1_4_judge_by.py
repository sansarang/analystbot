"""[LDG-1] 원장에 **누가 판정했는지**를 남긴다.

🔴 지금은 봇 판정만 들어간다. 사람이 건 픽(페이블 채팅·승률 모드)을 같은
   game_id 로 나란히 두지 못하면 "봇 vs 페이블"을 숫자로 비교할 수 없다(7-2).
🔴 유니크 인덱스가 한 경기 1행으로 막고 있다 → `(game_id, judge_by)` 로 넓힌다.
   ⚠️ 그때 `judge_by` 가 NULL 이면 유니크가 **풀린다**(Postgres 는 NULL 을
      서로 다른 값으로 본다). 그래서 NOT NULL DEFAULT 다 — docs/FORKS.md F-19.
"""
from __future__ import annotations

import pathlib
import re

SCHEMA = (pathlib.Path(__file__).resolve().parents[2] / "db" / "schema.sql"
          ).read_text(encoding="utf-8")


def test_새_컬럼이_스키마에_있다():
    for col in ("judge_by", "market", "market_side", "line", "odds_taken"):
        assert re.search(rf"ADD COLUMN IF NOT EXISTS\s+{col}\b", SCHEMA), col


def test_judge_by_는_NOT_NULL_기본값이다():
    m = re.search(r"ADD COLUMN IF NOT EXISTS\s+judge_by[^;]*;", SCHEMA)
    assert m, "judge_by 컬럼이 없다"
    sql = m.group(0)
    assert "NOT NULL" in sql and "DEFAULT" in sql and "bot_v14" in sql, sql


def test_유니크가_judge_by_까지_본다():
    m = re.search(r"CREATE UNIQUE INDEX IF NOT EXISTS idx_pick_ledger_final[^;]*;",
                  SCHEMA)
    assert m, "유니크 인덱스가 없다"
    assert "judge_by" in m.group(0), m.group(0)
    assert "WHERE is_final" in m.group(0), m.group(0)


def test_옛_유니크를_먼저_지운다():
    """🔴 `CREATE UNIQUE INDEX IF NOT EXISTS` 는 **이미 있으면 아무것도 안 한다.**
       옛 정의가 그대로 남아 새 정의가 적용되지 않는다 — DROP 이 먼저다."""
    drop = SCHEMA.find("DROP INDEX IF EXISTS idx_pick_ledger_final")
    create = SCHEMA.find("CREATE UNIQUE INDEX IF NOT EXISTS idx_pick_ledger_final")
    assert drop != -1, "옛 인덱스를 지우지 않는다"
    assert drop < create, "DROP 이 CREATE 보다 뒤에 있다"


# ── 사람이 넣는 도구

def test_ledger_add_도구가_있다():
    from tools import ledger_add

    assert set(ledger_add.JUDGES) == {"bot_v14", "fable_chat", "user_mode_b"}
    assert set(ledger_add.MARKETS) == {"ml", "ah", "total", "team_total", "f5"}


def test_팀토탈은_홈원정_접미사를_받는다():
    from tools.ledger_add import valid_market

    assert valid_market("team_total_away")
    assert valid_market("ml")
    assert not valid_market("moneyline")
    assert not valid_market("team_total_middle")


def test_인자를_행으로_옮긴다():
    from tools.ledger_add import build_row

    row = build_row(game_id=10098, sport="mlb", league="MLB", date="2026-09-19",
                    judge_by="fable_chat", market="team_total_away", line=3.5,
                    side="under", odds=1.90, note="페이블 채팅 판정")
    assert row["judge_by"] == "fable_chat"
    assert row["market"] == "team_total_away"
    assert row["market_side"] == "under"
    assert row["line"] == 3.5
    assert row["odds_taken"] == 1.90
    assert row["is_final"] is True


def test_모르는_판정자는_거부한다():
    import pytest

    from tools.ledger_add import build_row

    with pytest.raises(SystemExit):
        build_row(game_id=1, sport="mlb", league="MLB", date="2026-09-19",
                  judge_by="누군가", market="ml", line=None, side="away",
                  odds=2.0, note=None)
