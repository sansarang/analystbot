"""[Odds 이관] KBO·NPB는 배당 API 없이 완주해야 한다.

🔴 실사고 2026-08-27: Odds 크레딧이 마르자 KBO 응답 전체가
   "⚠️ odds API 사용량/크레딧이 소진되어 분석을 완료하지 못했습니다" 한 줄로
   대체됐다. KBO는 배당을 판정에도 표시에도 쓰지 않는데(#38·#39) 일정 소스만
   Odds였기 때문이다. 이 파일은 그 의존이 되살아나지 않게 고정한다.
"""
import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _branch_source(sport_marker: str) -> str:
    src = (ROOT / "app/pipeline.py").read_text(encoding="utf-8")
    start = src.index(sport_marker)
    return src[start:src.index("    else:", start)]


def test_kbo_npb_branch_does_not_call_the_odds_api():
    """🔴 일정 분기에서 OddsClient를 부르면 크레딧이 마를 때 다시 죽는다."""
    branch = _branch_source('    elif sport in ("kbo", "npb"):')
    for banned in ("OddsClient", "upsert_games_from_scores", "snapshot_odds"):
        assert banned not in branch, f"KBO·NPB 일정 경로에 {banned}이 남아 있다"
    assert "upsert_schedule" in branch, "공식 일정 소스가 배선되지 않았다"


def test_kbo_npb_request_no_odds_keys():
    """배당 조회 대상 리그가 비어 있어야 API 호출 자체가 없다."""
    src = (ROOT / "app/pipeline.py").read_text(encoding="utf-8")
    i = src.index('    elif sport in ("kbo", "npb"):\n        # 🔴 **호출조차')
    block = src[i:src.index("    else:", i)]
    assert "active_keys = []" in block


def test_odds_snapshot_is_skipped_when_no_keys():
    src = (ROOT / "app/pipeline.py").read_text(encoding="utf-8")
    fn = src[src.index("async def _odds_or_none():"):src.index("stats, _odds_rows")]
    assert "if not active_keys:" in fn and "return []" in fn


def test_official_schedule_entrypoints_exist_and_share_a_contract():
    """KBO·NPB가 같은 계약을 돌려줘야 파이프라인이 한 갈래로 처리한다."""
    from app.collectors import kbo, yahoo_npb

    for mod in (kbo, yahoo_npb):
        fn = getattr(mod, "upsert_schedule", None)
        assert fn is not None, f"{mod.__name__}에 upsert_schedule이 없다"
        args = [a.arg for a in ast.parse(
            (ROOT / mod.__file__.split("analystbot/")[-1]).read_text(encoding="utf-8")
        ).body[-1].args.args]
        assert args[:2] == ["pool", "date"], f"{mod.__name__} 시그니처 불일치: {args}"


@pytest.mark.asyncio
async def test_kbo_schedule_upsert_counts_by_status(monkeypatch):
    """예정/종료 집계가 Odds 경로와 같은 키로 나와야 호출부가 안 깨진다."""
    from app.collectors import kbo

    async def fake_month(season, month, client=None):
        return [
            {"date": "2026-08-27", "time": "18:30", "home": "H1", "away": "A1",
             "status": "scheduled", "home_score": None, "away_score": None,
             "ext_id": "kbo:1"},
            {"date": "2026-08-27", "time": "18:30", "home": "H2", "away": "A2",
             "status": "final", "home_score": 5, "away_score": 3, "ext_id": "kbo:2"},
            {"date": "2026-08-26", "time": "18:30", "home": "H3", "away": "A3",
             "status": "final", "home_score": 1, "away_score": 0, "ext_id": "kbo:3"},
        ]

    seen = []

    async def fake_upsert(pool, games):
        seen.extend(games)
        return len(games)

    monkeypatch.setattr(kbo, "fetch_month", fake_month)
    monkeypatch.setattr(kbo, "upsert_games", fake_upsert)
    counts = await kbo.upsert_schedule(None, "2026-08-27")
    assert counts == {"scheduled": 1, "final": 1, "total": 2}
    assert all(g["date"] == "2026-08-27" for g in seen), "다른 날 경기가 섞였다"


def test_kbo_card_shows_no_odds_warnings():
    """🔴 안 쓰는 배당의 경고를 띄우면 사용자가 고칠 수 없는 잡음이 된다."""
    from app.pipeline import _render_card, data_limitation_line

    out = _render_card({"date": "2026-08-27", "sport": "kbo", "games": [],
                        "picks": [], "recommended": [], "quota_warning": True})
    assert "배당 데이터 잔여 쿼터" not in out
    # MLB에서는 여전히 띄운다 — 거기서는 실제로 배당을 쓴다
    mlb = _render_card({"date": "2026-08-27", "sport": "mlb", "games": [],
                        "picks": [], "recommended": [], "quota_warning": True})
    assert "배당 데이터 잔여 쿼터" in mlb


def test_odds_stage_is_not_recorded_without_odds_leagues():
    import ast
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app/pipeline.py").read_text(encoding="utf-8")
    i = src.index('await record("배당 수집"')
    assert "if active_keys:" in src[i - 400:i], "배당 계측이 무조건 실행된다"
