"""STC-1 — 애리조나만 Statcast 재료가 통째로 없었다.

🔴 운영 실측 2026-09-08: `statcast:offense:2026-09-07` 캐시 팀 **29/30**,
   빠진 팀 = Arizona Diamondbacks. 원본이 주는 코드는 `AZ` 인데 매핑에는
   `ARI` 로 적혀 있었고, `_team_of_batter` 는 모르는 코드를 `None` 으로 만든 뒤
   `notna()` 가 그 행을 통째로 버린다.

   애리조나 경기 25건(그중 판정 원장 23건)에서 λ 타선 축 전체·불펜 과소모 판정·
   타자 랭킹(결장 중요도 기준)이 비었고, `league_baselines` 는 29팀 평균으로
   계산됐다.

   이 파일은 개명(OAK → ATH)을 이미 겪어 **둘 다** 넣어 두었다. 즉 코드가
   바뀔 수 있다는 것을 아는 상태였는데, `ARI` 가 한 번도 오지 않는다는 사실을
   **확인하는 장치가 없었다.** 0건이 아니라 29/30 이라 더 안 보였다.
"""
import logging

import pytest

from app.collectors import statcast as sc


def test_AZ_코드가_매핑에_있다():
    assert sc.TEAM_CODE_TO_NAME.get("AZ") == "Arizona Diamondbacks"


def test_매핑이_MLB_30팀을_전부_덮는다():
    names = set(sc.TEAM_CODE_TO_NAME.values())
    assert len(names) == sc.MLB_TEAM_COUNT, (
        f"매핑이 {len(names)}팀뿐이다 — 빠진 팀의 재료는 통째로 사라진다")


def test_모르는_코드가_오면_조용히_버리지_않는다(caplog):
    """🔴 '조용한 성공' — 분모가 사라지는 실패는 반드시 시끄러워야 한다."""
    with caplog.at_level(logging.ERROR, logger="app.collectors.statcast"):
        gaps = sc.audit_team_coverage({"AZ", "NYY", "XYZ"}, {"New York Yankees"})
    assert "XYZ" in gaps["unknown_codes"]
    assert "Arizona Diamondbacks" in gaps["missing_teams"]
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "XYZ" in text and "29" not in text  # 숫자를 지어내지 않는다


def test_전부_정상이면_조용하다(caplog):
    """반대 위험 — 정상인데 우는 대사는 곧 무시된다."""
    all_names = set(sc.TEAM_CODE_TO_NAME.values())
    with caplog.at_level(logging.WARNING, logger="app.collectors.statcast"):
        gaps = sc.audit_team_coverage(set(sc.TEAM_CODE_TO_NAME), all_names)
    assert gaps == {"unknown_codes": [], "missing_teams": []}
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_갱신_경로가_대사를_부른다():
    """등록은 배선이 아니다 — refresh 본문에서 확인한다."""
    from pathlib import Path

    src = Path("app/collectors/statcast.py").read_text(encoding="utf-8")
    i = src.index("async def refresh(")
    body = src[i:i + 3000]
    assert "audit_team_coverage" in body, "갱신 경로가 팀 커버리지를 대사하지 않는다"
