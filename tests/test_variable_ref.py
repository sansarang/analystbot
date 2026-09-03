"""[C1 · 자료10] 변수가 인용할 **답 데이터**가 실제로 만들어지는가.

🔴 왜: 오늘 저녁 카드의 변수가 이랬다 —
     "원정 선발 이로운은 선발등판 기록이 0건이라 이닝 소화력 예측 불가"
   위험을 말하기만 하고 크기를 주지 않았다. 읽는 사람은 3%p 인지 15%p 인지
   알 수 없고, 우리도 나중에 그 변수가 맞았는지 채점할 수 없다.
   판정이 숫자를 쓰려면 **인용할 숫자가 프롬프트에 있어야 한다.**
"""
from datetime import UTC, datetime

import pytest

from app.engine import variable_ref as VR
from app.engine.matchup import insert_material10, material10_payload

NOW = datetime(2026, 9, 3, tzinfo=UTC)


class Pool:
    """`fetch`/`fetchrow`/`fetchval` 을 SQL 로 분기하는 최소 스텁."""

    def __init__(self, apps=None, regression=None, opp=None):
        self.apps = apps or []
        self.regression = regression
        self.opp = opp or {}

    async def fetch(self, sql, *a):
        return self.apps

    async def fetchrow(self, sql, *a):
        return self.regression

    async def fetchval(self, sql, *a):
        return self.opp.get(a[0])


def _app(ip, r=0, starter=False):
    return {"innings": ip, "r": r, "is_starter": starter, "starts_at": NOW}


# ═════════ 1-a 이닝 분포 — 이로운 케이스(선발 0 · 구원만) ═════════

@pytest.mark.asyncio
async def test_relief_only_pitcher_gets_an_innings_distribution():
    """🔴 이 파일의 목적 — "예측 불가"를 **분포**로 바꾼다.

    실사고 원문(2026-09-03 리허설, SSG@키움): "away 선발 이로운은 선발등판
    기록이 0건(구원등판 4회뿐)이라 이닝 소화력 예측 불가".
    구원 45회의 이닝 기록이 DB 에 있는데 판정이 볼 수 없었다.
    """
    apps = [_app(1.0), _app(2.0), _app(1.2), _app(0.2), _app(3.0),
            _app(1.0), _app(1.1), _app(2.0), _app(0.1), _app(1.0)]
    out = await VR.innings_profile(Pool(apps), "kbo", "이로운", NOW)
    assert out["n"] == 10 and out["선발등판"] == 0 and out["구원등판"] == 10
    assert out["최장"] == 3.0
    assert out["p50"] in [a["innings"] for a in apps], "실제 등판 값이 아니다"
    assert "이닝" in out and len(out["이닝"]) == 10


@pytest.mark.asyncio
async def test_fewer_than_ten_appearances_reports_n():
    out = await VR.innings_profile(Pool([_app(1.0), _app(2.0)]), "npb", "X", NOW)
    assert out["n"] == 2


@pytest.mark.asyncio
async def test_no_records_is_empty_not_invented():
    assert await VR.innings_profile(Pool([]), "mlb", "X", NOW) == {}


def test_quantiles_do_not_interpolate():
    """보간하면 **실제로 던진 적 없는 이닝**이 참조가 된다 — L1 이 환각으로 찍는다."""
    q = VR.quantiles([1.0, 2.0, 3.0, 10.0])
    for v in q.values():
        assert v in (1.0, 2.0, 3.0, 10.0), q


def test_low_start_threshold_reads_config():
    from app.config import get_settings

    jg = {"research": {"home_starter_recent": [{}, {}],
                       "away_starter_recent": [{}, {}, {}]}}
    assert get_settings().var_ref_low_start_max == 3
    assert VR.needs_innings_profile(jg, "home") is True      # 2 < 3
    assert VR.needs_innings_profile(jg, "away") is False     # 3 은 미만이 아니다


# ═════════ 1-b 부진 후 회귀 — 발동 경계와 표본 라벨 ═════════

def _gap_jg(runs, ip, season_era):
    return {"research": {
        "home_starter_recent": [{"innings": ip / 3, "r": runs / 3}] * 3,
        "home_starter_season": {"era": season_era}}}


def test_gap_boundary_199_vs_201():
    """1.99 → 미계산 / 2.01 → 계산. 경계를 코드가 아니라 config 가 정한다."""
    from app.config import get_settings

    thr = float(get_settings().var_ref_era_gap)
    assert thr == 2.00
    lo = VR.form_gap(_gap_jg(runs=18, ip=27, season_era=4.01), "home")   # 6.00-4.01
    hi = VR.form_gap(_gap_jg(runs=18, ip=27, season_era=3.99), "home")   # 6.00-3.99
    assert lo is not None and hi is not None
    assert lo < thr <= hi, (lo, hi)


def test_gap_needs_three_starts():
    jg = {"research": {"home_starter_recent": [{"innings": 5, "r": 5}],
                       "home_starter_season": {"era": 2.0}}}
    assert VR.form_gap(jg, "home") is None


def test_gap_without_season_line_is_none():
    jg = {"research": {"home_starter_recent": [{"innings": 5, "r": 5}] * 3}}
    assert VR.form_gap(jg, "home") is None


@pytest.mark.asyncio
async def test_small_sample_is_labelled_not_asserted():
    """표본 29 → "참조 불충분" 라벨. **단정하지 않는다.**"""
    out = await VR.regression_reference(
        Pool(regression={"n": 29, "ip": 5.1, "r": 3.2}), None, "kbo", "2026-01-01")
    assert out["표본"] == 29 and "참조 불충분" in out["주의"]


@pytest.mark.asyncio
async def test_sufficient_sample_has_no_warning():
    out = await VR.regression_reference(
        Pool(regression={"n": 30, "ip": 5.1, "r": 3.2}), None, "npb", "2026-01-01")
    assert out["표본"] == 30 and "주의" not in out
    assert out["리그"] == "NPB", "리그를 섞으면 안 된다"


# ═════════ 1-c 상대 선발 시즌 ERA ═════════

@pytest.mark.asyncio
async def test_unmatched_opponent_starter_is_null_with_log(caplog):
    """이름 매칭 실패 → null + 로그. **조용히 지나가지 않는다.**"""
    jg = {"sport": "kbo", "research": {"home_usage": {"games": [
        {"game_id": 1, "opponent": "LG"}]}}}
    with caplog.at_level("INFO"):
        await VR.attach_opp_starter_era(Pool(opp={}), jg)
    g = jg["research"]["home_usage"]["games"][0]
    assert "opp_starter_season_era" in g and g["opp_starter_season_era"] is None
    assert any("상대 선발 미상" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_attach_does_not_raise_without_pool():
    assert await VR.attach_opp_starter_era(None, {}) == 0


# ═════════ 자료10 미포함 = 프롬프트 바이트 동일 ═════════

def test_prompt_is_byte_identical_when_material10_is_absent():
    """🔴 해당 없는 경기는 종전과 **완전히 같은** 프롬프트여야 한다."""
    base = "1. 자료\n\n[판정 규칙]\n- 규칙"
    assert insert_material10(base, {}) == base
    assert insert_material10(base, None) == base


def test_material10_goes_before_the_rules():
    base = "1. 자료\n\n[판정 규칙]\n- 규칙"
    out = insert_material10(base, {"home": {"이닝분포": {"p50": 1.2}}})
    assert out != base
    assert out.index("10. 변수 참조") < out.index("[판정 규칙]")
    assert "1.2" in out


def test_payload_reads_only_no_io():
    """판정 경로는 읽기만 한다 — 조립은 파이프라인이 끝냈다."""
    assert material10_payload({}) == {}
    assert material10_payload({"material10": {"home": {}}}) == {"home": {}}


@pytest.mark.asyncio
async def test_status_is_three_valued():
    jg = {"sport": "kbo", "research": {
        "home_starter_recent": [{}, {}, {}], "away_starter_recent": [{}, {}, {}]}}
    assert await VR.attach_material10(None, None, jg) == VR.M10_NA
    assert jg["material10"] == {}


def test_pipeline_attaches_before_the_judge_call():
    """🔴 조립이 판정보다 **뒤**면 그 슬레이트는 자료10 없이 판정된다."""
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    seg = src[src.index("async def _run_baseball_matchups"):]
    assert seg.index("attach_material10") < seg.index("await judge_matchup")
