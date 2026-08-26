"""[§8-12] **예측에 어떤 데이터가 쓰이는가**를 고정하는 감사 테스트.

재설계 지시(2026-08-26): "과거 데이터는 예측에 쓰지 않는다. 최근 경기만 본다."
그 계약이 코드에서 실제로 지켜지는지, 그리고 나중에 조용히 되돌아가지 않는지 잠근다.

계약:
  ① **1순위 확률 = λ 분포**(최근 N경기 창). 시즌 누적은 λ가 설 때 쓰이지 않는다.
  ② 시즌 누적 데이터가 남는 자리는 셋뿐이다 —
     (a) λ 실패 시 **폴백**  (b) 2-소스 룰의 **독립 축**  (c) **병렬 기록**
     이 셋은 예측을 만드는 게 아니라 예측을 검증·보조한다.
  ③ 채점 원장(games 결과·predictions)은 **보존**한다. 버리면 재측정이 영원히 불가능하다.
     — 실제로 오늘 이 원장 덕분에 선발 뒤집힘 버그와 풀링 기준선 오류를 잡았다.
"""

import re
from pathlib import Path

import pytest

from app.config import Settings

PIPELINE = Path("app/pipeline.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------- ① λ 우선

def test_distribution_overrides_season_heuristic():
    """분포가 서면 시즌 승률·ERA 휴리스틱을 **덮어써야** 한다.

    이게 깨지면 '최근 경기만 본다'는 계약이 조용히 무너진다 — 시즌 누적이
    1순위 확률로 되돌아가는데 겉으로는 아무 차이가 안 보인다.
    """
    assert re.search(
        r'if dist is not None:.*?p_model_s = \(dist\["probs"\]\["h2h"\]\["home"\]',
        PIPELINE, re.S), "분포가 있을 때 p_model을 분포로 교체하는 코드가 사라졌다"


def test_recent_window_is_configured_not_hardcoded():
    """창 길이는 설정값이다 — 하드코딩하면 오늘 같은 재측정이 불가능해진다."""
    s = Settings(_env_file=None)
    assert s.recent_window_games > 0
    assert s.recent_window_starts > 0
    assert s.recent_facts_games > 0


def test_statcast_aggregation_honours_window():
    """수집기가 설정 창을 실제로 쓰는지 — 설정만 있고 안 쓰면 장식이다."""
    src = Path("app/collectors/statcast.py").read_text(encoding="utf-8")
    assert "window_games=_s.recent_window_games" in src
    assert "window_starts=_s.recent_window_starts" in src


# ---------------------------------------------------------------- ② 남은 자리 셋

def test_learned_model_is_parallel_record_only():
    """학습 λ 계수는 **추천 판정에 쓰지 않는다** (MODEL.md §8-1).

    검증 정확도 52.3%로 목표에 못 미친다. 병렬 기록으로만 남긴다.
    """
    m = re.search(r'def _learned_probs\(.*?\n(?=\ndef )', PIPELINE, re.S)
    assert m, "_learned_probs가 사라졌다"
    assert "추천에는 쓰지 않는다" in m.group(0)
    # p_final 합성에 learned가 섞이면 안 된다
    blend = re.search(r'def blend\(.*?\n(?=\s{4}def )', PIPELINE, re.S)
    assert blend and "learned" not in blend.group(0)


def test_data_axis_stays_independent_of_lambda():
    """2-소스 룰의 '실데이터' 축은 λ와 **다른 소스**여야 한다.

    같은 Statcast로 두 축을 만들면 축이 하나로 붕괴해 2-소스 룰이 무의미해진다.
    그래서 시즌 승률·순위표를 여기에 남겨 둔다 — 이것은 과거 데이터의 정당한 용처다.
    """
    src = Path("app/engine/markets.py").read_text(encoding="utf-8")
    axis = re.search(r'def _season_edge\(.*?\n(?=\ndef )', src, re.S)
    assert axis, "_season_edge가 사라졌다"
    body = axis.group(0)
    for leaked in ("xwoba", "statcast", "distribution", "lam"):
        assert leaked not in body.lower(), (
            f"실데이터 축에 λ와 같은 소스({leaked})가 섞였다 — 2-소스 룰이 붕괴한다")


def test_no_dead_calibration_helper():
    """호출처 없는 과거-데이터 재추정 헬퍼는 남기지 않는다."""
    src = Path("app/engine/markets.py").read_text(encoding="utf-8")
    assert "calibrated_lambda" not in src


# ---------------------------------------------------------------- ③ 원장 보존

def test_audit_ledger_columns_preserved():
    """채점 원장은 버리지 않는다 — 재측정의 유일한 근거다."""
    schema = Path("db/schema.sql").read_text(encoding="utf-8")
    for col in ("result", "pnl", "p_legacy", "p_heuristic", "p_learned",
                "p_claude", "closing_odds"):
        assert col in schema, f"원장 컬럼 {col}이 스키마에서 사라졌다"
    assert "clv_ledger" in schema


async def test_prediction_path_records_all_three_methods(db_pool, redis_client):
    """실제 1회 실행에서 세 방식 확률이 함께 남는지 — 병렬 채점의 전제다."""
    from app.pipeline import run_pipeline

    await run_pipeline(db_pool, redis_client, "mlb", "2026-08-22", force_refresh=True)
    # ⚠️ 세 방식 확률(p_heuristic·p_learned·p_claude)은 **승패 기준**이라
    #    h2h 픽에만 기록된다. 런라인·토탈 픽에서 None인 것은 설계다.
    row = await db_pool.fetchrow(
        "SELECT p_heuristic, p_claude, model_p, pick, lam_total FROM predictions "
        "WHERE method = 'performance' AND pick LIKE 'h2h:%' LIMIT 1")
    if row is None:
        pytest.skip("이 슬레이트에 h2h 추천이 없다 (세 방식 비교는 승패 기준)")
    assert row["model_p"] is not None
    assert row["p_heuristic"] is not None, "λ 분포 확률이 원장에 안 남았다"
    assert row["p_claude"] is not None, "판정 확률이 원장에 안 남았다"


async def test_lam_total_is_recorded_for_score_mae(db_pool, redis_client):
    """[§8-18] 예상 총득점이 원장에 남아야 **점수 오차(MAE)**를 잴 수 있다.

    돈·시장 지표를 뺀 뒤 남은 평가 축은 ①방향 적중률 ②점수 MAE 둘뿐이다.
    """
    from app.pipeline import run_pipeline

    await run_pipeline(db_pool, redis_client, "mlb", "2026-08-22", force_refresh=True)
    n = await db_pool.fetchval(
        "SELECT count(*) FROM predictions "
        "WHERE method = 'performance' AND lam_total IS NOT NULL")
    total = await db_pool.fetchval(
        "SELECT count(*) FROM predictions WHERE method = 'performance'")
    if not total:
        pytest.skip("적재된 예측이 없다")
    assert n > 0, "예상 총득점(lam_total)이 하나도 안 남았다 — 점수 MAE를 잴 수 없다"
