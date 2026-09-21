"""[FMR-1 / STEP 1-i-2] FotMob 결과 적재.

🔴 왜 — football-data 무료로는 J·K·UEL·ACL 결과를 받을 수 없다
   (`/competitions/{code}/matches` 전건 `ApiAuthError` · 실측 2026-09-20).
   그런데 FotMob 하루치 목록이 **그 전부를 결과까지** 준다:

     K-League 1(KOR) 09-13 2경기 종료 2 · K League 2 4/4
     J. League / J2 / J3 (JPN) 09-19 8·8·4 전부 종료
     Europa League(INT) 09-16 9/9 · AFC Champions League Elite 2/2

   `slate()` 이 `id·league·home·away·utc` 만 뽑고 **점수를 버리고 있었다.**

🔴 연장·승부차기 실측(6144851 AET · 6144860 Pen):
     · 90분 점수를 **직접 주는 칸은 없다** (`header.teams[].score` 는 연장 포함)
     · 득점 이벤트의 분은 **깔끔히 갈린다** — 후반 추가시간은 `time=90` +
       `overloadTime`, 연장 득점은 `time>=91`
     · 승부차기는 `penaltyShootoutEvents` 별도 배열 + `whoLostOnPenalties`
   → `minute <= 90` 인 득점만 합산하고 `result_basis` 에 근거를 적는다.
   ⚠️ 그 합이 **동점이 아니면** 계산이 틀린 것이다(동점이라야 연장에 간다) →
      수동 확인 목록. **추측으로 채점하지 않는다.**
"""
from __future__ import annotations

import pytest


# ── 상태 매핑

def test_reason_이_상태를_가른다():
    from app.collectors.fotmob import status_of

    assert status_of({"finished": True, "reason": {"short": "FT"}}) == ("final", "FT")
    assert status_of({"finished": True, "reason": {"short": "AET"}}) == ("final", "AET")
    assert status_of({"finished": True, "reason": {"short": "Pen"}}) == ("final", "Pen")
    assert status_of({"cancelled": True}) == ("cancelled", None)
    assert status_of({"finished": False, "started": False}) == ("scheduled", None)


def test_연기는_final_이_아니다():
    from app.collectors.fotmob import status_of

    st, basis = status_of({"finished": False, "started": False,
                           "reason": {"short": "Postp."}})
    assert st != "final", (st, basis)


# ── 90분 점수 (실측 JSON 조각 · 가짜 구조 아님)

#: 🔴 실측 원문 — matchId 6144851 (Førde 3-4 Aalesund · AET)
F_FM_AET_EVENTS = [
    {"type": "Goal", "time": 7, "timeStr": 7, "overloadTime": None,
     "isHome": True, "newScore": [1, 0]},
    {"type": "Goal", "time": 11, "timeStr": 11, "overloadTime": None,
     "isHome": True, "newScore": [2, 0]},
    {"type": "Goal", "time": 89, "timeStr": 89, "overloadTime": None,
     "isHome": False, "newScore": [2, 1]},
    {"type": "Goal", "time": 90, "timeStr": "90 + 1", "overloadTime": 1,
     "isHome": False, "newScore": [2, 2]},
    {"type": "Goal", "time": 94, "timeStr": 94, "overloadTime": None,
     "isHome": False, "newScore": [2, 3]},
    {"type": "Goal", "time": 107, "timeStr": 107, "overloadTime": None,
     "isHome": True, "newScore": [3, 3]},
    {"type": "Goal", "time": 115, "timeStr": 115, "overloadTime": None,
     "isHome": False, "newScore": [3, 4]},
]


def test_f_fm_aet_90분_점수는_2대2():
    """🔴 `time <= 90` 만 합산. 후반 추가시간(90+1)은 포함, 연장(94~)은 제외."""
    from app.collectors.fotmob import score_at_90

    assert score_at_90(F_FM_AET_EVENTS) == (2, 2)


def test_f_fm_aet_동점이_아니면_수동확인():
    """⚠️ 자기검증 — AET 인데 90분이 동점이 아니면 계산이 틀렸다."""
    from app.collectors.fotmob import score_at_90

    bad = [{"type": "Goal", "time": 10, "newScore": [1, 0]}]
    assert score_at_90(bad) == (1, 0)          # 계산 자체는 된다
    from app.collectors.fotmob import ninety_ok

    assert ninety_ok((2, 2)) is True
    assert ninety_ok((1, 0)) is False          # 호출부가 수동 확인으로 보낸다
    assert ninety_ok(None) is False


def test_승부차기는_어디에도_합산하지_않는다():
    """🔴 실측 6144860 — 본선 events 의 PenaltyShootout 은 newScore 가 None."""
    from app.collectors.fotmob import score_at_90

    rows = [{"type": "Goal", "time": 19, "newScore": [0, 1]},
            {"type": "Goal", "time": 71, "newScore": [2, 2]},
            {"type": "PenaltyShootout", "time": 121, "newScore": None}]
    assert score_at_90(rows) == (2, 2)


# ── slate 가 점수를 싣는다

def test_slate_가_점수와_상태를_함께_뽑는다():
    import inspect

    from app.collectors import fotmob as FM

    # ⚠️ [FOT-STOP 2026-09-21] `slate` 는 **캐시 껍데기**가 됐다. 실제로
    #    뽑는 것은 `_slate_rows` 다 — 껍데기를 검사하면 늘 통과한다.
    src = inspect.getsource(FM._slate_rows)
    for want in ("finished", "scoreStr", "reason", "score"):
        assert want in src, f"slate 가 {want} 를 안 뽑는다"


# ── 별칭 / id

def test_norm_이_치환표를_읽는다():
    """🔴 실측: `NFKD → ascii ignore` 라 ø·æ 는 **통째로 삭제**된다.

        Brøndby IF   → 'brndby if'    (우리 'Brondby IF' → 'brondby if')
        SønderjyskE  → 'snderjyske'
        FC København → 'fc kbenhavn'
    ⚠️ 치환표는 `config/team_name_map.yaml` 이 원본이다 — 코드에 박지 않는다.
    """
    from app.collectors.fotmob import norm

    assert norm("Brøndby IF") == "brondby if"
    assert norm("SønderjyskE") == "sonderjyske"
    assert norm("Málaga CF") == "malaga cf"       # 종전 동작 보존
    assert norm("1. FC Köln") == "1. fc koln"


def test_대기표가_있고_자동승격하지_않는다():
    """🔴 이름이 달라 못 찾은 팀은 **사람이 승인**해야 별칭이 된다."""
    import pathlib

    import yaml

    root = pathlib.Path(__file__).resolve().parents[1]
    f = root / "config" / "team_alias_pending.yaml"
    assert f.exists(), "config/team_alias_pending.yaml 이 없다"
    doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    assert "pending" in doc, doc.keys()
    for row in (doc.get("pending") or []):
        assert row.get("approved") is not True or row.get("fotmob_id"), \
            f"승인했는데 id 가 없다: {row}"
