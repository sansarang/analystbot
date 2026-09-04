"""[C1] 불펜 최근 폼 — **시즌 누적은 판정 입력이 아니다.**

🔴 대원칙(2026-09-04 사용자 확정): 판정 데이터는 최근 3~5경기(불펜은 최근
   3일)만. 시즌·통산·상대전적 금지. 이 파일이 그 경계를 잠근다.
"""
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.engine import bullpen_recent as BR

SRC = Path("app/engine/bullpen_recent.py").read_text(encoding="utf-8")
NOW = datetime(2026, 9, 4, tzinfo=UTC)


# ═════════ 라벨 경계 — 임계는 config 가 원본 ═════════

def test_three_straight_days_is_spent():
    """3연투 → 소진."""
    assert BR.label_of(3, 0) == BR.SPENT


def test_two_days_rest_is_available():
    assert BR.label_of(0, 0) == BR.AVAILABLE
    assert BR.label_of(1, 5) == BR.AVAILABLE


def test_boundaries_come_from_config():
    from app.config import get_settings

    s = get_settings()
    assert BR.label_of(s.bullpen_fatigue_apps, 0) == BR.TIRED
    assert BR.label_of(s.bullpen_fatigue_apps - 1, 0) == BR.AVAILABLE
    assert BR.label_of(0, s.bullpen_spent_tbf) == BR.SPENT
    assert BR.label_of(0, s.bullpen_spent_tbf - 1) == BR.TIRED
    # 숫자를 코드에 적지 않았다
    i = SRC.index("def label_of")
    seg = SRC[i:SRC.index("\nasync def ", i)]
    assert "bullpen_spent_apps" in seg and "8" not in seg and "13" not in seg


# ═════════ 조회·조립 ═════════

class Pool:
    def __init__(self, runs=None, core=None, last3=None):
        self._runs, self._core, self._last3 = runs, core or [], last3 or []

    async def fetchrow(self, sql, *a):
        return self._runs

    async def fetch(self, sql, *a):
        return self._core if "ORDER BY n DESC" in sql else self._last3


@pytest.mark.asyncio
async def test_block_has_recent_form_only():
    pool = Pool(runs={"runs": 7, "ip": 9.0, "appearances": 11, "games": 3},
                core=[{"pitcher": "김OO", "n": 6}, {"pitcher": "이OO", "n": 5}],
                last3=[{"pitcher": "김OO", "apps": 2, "tbf": 9, "last_at": NOW}])
    out = await BR.team_block(pool, "kbo", "LG", NOW)
    assert out["최근3경기"] == {"실점": 7, "이닝": 9.0, "등판": 11,
                               "경기": 3, "경기당실점": 2.33}
    assert out["가용성"]["종합"] == BR.TIRED       # 김OO 2등판·9타자
    assert "era" not in out and "whip" not in out


@pytest.mark.asyncio
async def test_small_core_reports_n():
    pool = Pool(runs={"runs": 2, "ip": 3.0, "appearances": 3, "games": 3},
                core=[{"pitcher": "A", "n": 2}], last3=[])
    out = await BR.team_block(pool, "npb", "T", NOW)
    assert "표본 부족, n=1" in out["가용성"]["주의"]


@pytest.mark.asyncio
async def test_attach_removes_season_fields():
    """🔴 시즌 값을 **지운다.** 남기면 프롬프트에 계속 실려 원칙이 깨진다."""
    jg = {"sport": "kbo", "home": "LG", "away": "두산", "starts_at": NOW,
          "research": {"home_bullpen": {"era": 4.2, "whip": 1.3, "k9": 8.1,
                                        "roster": ["김OO(2.16·보통)"]},
                       "away_bullpen": {"era": 3.9, "bb9": 3.2}}}
    pool = Pool(runs={"runs": 4, "ip": 6.0, "appearances": 7, "games": 3},
                core=[{"pitcher": "김OO", "n": 4}], last3=[])
    await BR.attach(pool, jg)
    for side in ("home", "away"):
        blk = jg["research"][f"{side}_bullpen"]
        for stale in ("era", "whip", "k9", "bb9"):
            assert stale not in blk, f"{side} 에 시즌 {stale} 가 남았다"
        assert "최근3경기" in blk
    # 컨디션(최근 정보)은 유지한다
    assert jg["research"]["home_bullpen"]["roster"] == ["김OO(2.16·보통)"]


@pytest.mark.asyncio
async def test_no_pool_is_safe():
    assert await BR.attach(None, {}) == 0
    assert await BR.team_block(None, "kbo", "LG", NOW) == {}


# ═════════ 대원칙·설계 ═════════

def test_core_selection_window_is_documented_as_an_exception():
    """주력 5인 **선정**만 14일을 본다 — 수치는 3일이다. 이유가 적혀 있어야 한다."""
    assert "선정" in SRC and "명단 문제" in SRC
    assert "bullpen_core_days" in SRC


def test_tbf_proxy_is_disclosed():
    """🔴 대리값을 실측처럼 보이게 하지 않는다."""
    assert "투구수가 DB 에 없다" in SRC
    assert "대리값" in SRC
    from app.engine.prompts import MATCHUP

    assert "상대 타자 수를 소모 대리값" in MATCHUP


def test_no_league_branch():
    for sp in ("kbo", "npb", "mlb"):
        assert f'"{sp}"' not in SRC, f"{sp} 가 하드코딩됐다"


def test_pipeline_attaches_after_season_sources():
    """시즌 부착보다 **뒤**여야 지워진다."""
    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    seg = src[src.index("async def _run_baseball_matchups"):]
    assert seg.index("mlb_team_pitching") < seg.index("bullpen_recent")
    assert seg.index("bullpen_recent") < seg.index("await judge_matchup")
