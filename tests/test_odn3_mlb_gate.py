"""[ODN-3] MLB 파생 배당은 **게이트 대상만** 긁는다 — 예산이 먼저다.

🔴 실측 2026-09-19: `api_credits_used=109 / limit=1000`, 주기 09-17~10-17.
   1.7일에 109 → 하루 ~64콜. KBO·NPB 정기 잡만으로 월 720콜이라
   **MLB 여유는 하루 5콜 안쪽**이다. 창 안 MLB 는 27경기다 — 전수로 긁으면
   월 1,620콜이고 소스가 통째로 죽는다(KBO·NPB 까지 같이).
🔴 그래서 **상한을 두고, 버린 것을 센다.** 조용히 자르면 "전부 훑었다"로
   읽히고, 그 오해가 다음 사람의 판단을 바꾼다.
"""
from __future__ import annotations


def test_상한이_있고_예산에서_나온_숫자다():
    from app.scheduler import MLB_DERIV_CAP

    assert 1 <= MLB_DERIV_CAP <= 6, MLB_DERIV_CAP


def test_게이트_대상만_고른다():
    """🔴 보드고정(stop=true)은 조사할 자리가 아니다 — 긁을 이유가 없다."""
    from app.scheduler import pick_deriv_targets

    rows = [
        {"game_id": 1, "gate": "동의", "stop": False, "gap_pp": 1.2},
        {"game_id": 2, "gate": "보드고정", "stop": True, "gap_pp": None},
        {"game_id": 3, "gate": "시장과대", "stop": False, "gap_pp": -9.1},
        {"game_id": 4, "gate": "가치의심", "stop": False, "gap_pp": 6.0},
    ]
    got, dropped = pick_deriv_targets(rows, cap=2)
    assert [g["game_id"] for g in got] == [3, 4], got   # |gap| 큰 순
    assert dropped == {"보드고정": 1, "상한초과": 1}, dropped


def test_상한을_넘으면_버린_수를_센다():
    from app.scheduler import pick_deriv_targets

    rows = [{"game_id": i, "gate": "동의", "stop": False, "gap_pp": i}
            for i in range(1, 8)]
    got, dropped = pick_deriv_targets(rows, cap=3)
    assert len(got) == 3
    assert dropped["상한초과"] == 4


def test_괴리를_모르면_뒤로_보낸다():
    """⚠️ `gap_pp` 가 없는 경기를 앞에 두면 상한이 그쪽에 다 쓰인다."""
    from app.scheduler import pick_deriv_targets

    rows = [{"game_id": 1, "gate": "동의", "stop": False, "gap_pp": None},
            {"game_id": 2, "gate": "동의", "stop": False, "gap_pp": 0.1}]
    got, _ = pick_deriv_targets(rows, cap=1)
    assert [g["game_id"] for g in got] == [2], got


def test_잡이_등록돼_있다():
    from app import scheduler as S

    ids = {spec[0] for spec in S._job_specs()}
    assert "odds_mlb_deriv_10m" in ids, sorted(ids)
    assert hasattr(S, "odds_mlb_deriv_job")


def test_정기_잡은_여전히_KBO_NPB_만이다():
    """🔴 반대 위험 — MLB 를 정기 목록에 흘리면 예산이 터진다."""
    from app.collectors.oddsapinet import JOB_LEAGUES

    assert set(JOB_LEAGUES) == {"kbo", "npb"}
