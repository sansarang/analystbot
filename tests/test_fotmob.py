"""FOT-1 — 라인업·결장을 구조 JSON 으로 받는다 (사용자 지시).

🔴 실측 2026-09-14 (운영 컨테이너):
     /api/matches      → 404 (HTML)
     /api/data/matches → 200 · Serie A 3경기
     matchDetails 5749678 → lineupType=predicted · Torino 3-5-2 선발 11 ·
        unavailable 3명 · **Roma 는 unavailable 키 자체가 없음**
"""
import json

import pytest

from app.collectors import fotmob as FM

_DETAILS = {
    "content": {"lineup": {
        "matchId": 5749678, "lineupType": "predicted",
        "homeTeam": {"id": 9881, "name": "Torino", "formation": "3-5-2",
                     "starters": [{"id": 1, "name": "Perri"},
                                  {"id": 2, "name": "Simeone"}],
                     "subs": [],
                     "unavailable": [{"id": 9, "name": "Ché Adams",
                                      "unavailability": {"type": "injury",
                                                         "expectedReturn": "Late September 2026"}}]},
        # 🔴 로마에는 unavailable 키가 **없다** — 0명이 아니라 모른다.
        "awayTeam": {"id": 8686, "name": "Roma", "formation": "3-4-1-2",
                     "starters": [{"id": 3, "name": "Svilar"},
                                  {"id": 4, "name": "Soulé"}], "subs": []},
    }}
}


def test_경로는_실측한_것을_쓴다():
    """지시문의 /api/matches 는 404(HTML)였다."""
    assert FM.BASE.endswith("/api/data")
    assert FM.MIN_GAP_SEC == 2.0
    assert "User-Agent" in FM.HEADERS and "Referer" in FM.HEADERS


def test_결장_키가_없으면_None_이다():
    """🔴 "결장 0명"과 "모른다"는 다른 말이다."""
    lu = FM.parse_lineup(_DETAILS)

    assert lu["lineup_type"] == "predicted"
    assert len(lu["home"]["unavailable"]) == 1
    assert lu["home"]["unavailable"][0]["type"] == "injury"
    assert lu["away"]["unavailable"] is None, "키가 없으면 None"


def test_선발은_id_를_싣는다():
    """🔴 주전 판정·diff 는 이름이 아니라 id 로 센다(사용자 지시 3)."""
    lu = FM.parse_lineup(_DETAILS)

    assert [p["id"] for p in lu["home"]["starters"]] == [1, 2]
    assert lu["home"]["formation"] == "3-5-2"


def test_예상과_공식의_차이를_코드가_센다():
    """[사용자 지시 2] confirmed 로 바뀌면 predicted XI 와 diff."""
    before = FM.parse_lineup(_DETAILS)
    after = json.loads(json.dumps(_DETAILS))
    after["content"]["lineup"]["lineupType"] = "confirmed"
    after["content"]["lineup"]["homeTeam"]["starters"] = [
        {"id": 1, "name": "Perri"}, {"id": 7, "name": "Ngonge"}]

    d = FM.diff_xi(before, FM.parse_lineup(after))

    assert d["home"]["bench_notable"] == ["Simeone"], "예상 선발이 빠졌다"
    assert d["home"]["surprise_in"] == ["Ngonge"], "예상에 없던 선수가 들어왔다"
    assert d["away"]["bench_notable"] == [] and d["away"]["surprise_in"] == []


def test_한쪽이_없으면_변화_없음으로_읽지_않는다():
    assert FM.diff_xi(None, FM.parse_lineup(_DETAILS)) == {}
    assert FM.diff_xi(FM.parse_lineup(_DETAILS), None) == {}


def test_매칭은_양쪽_이름이_다_맞아야_한다():
    """🔴 퍼지 금지(AC밀란→인테르 오매칭 전례). 포함 관계만 본다."""
    rows = [{"id": 1, "home": "Torino", "away": "Roma"},
            {"id": 2, "home": "Como", "away": "Parma"}]

    assert FM.find_match(rows, home="Torino FC", away="AS Roma")["id"] == 1
    assert FM.find_match(rows, home="Como 1907",
                         away="Parma Calcio 1913")["id"] == 2
    # 한쪽만 맞으면 붙이지 않는다.
    assert FM.find_match(rows, home="Torino FC", away="Juventus FC") is None


@pytest.mark.asyncio
async def test_붙일_때_모르는_칸을_missing_에_남긴다(monkeypatch):
    async def _slate(d):
        return [{"id": 5749678, "home": "Torino", "away": "Roma"}]

    async def _lineup(mid):
        return FM.parse_lineup(_DETAILS)

    monkeypatch.setattr(FM, "slate", _slate)
    monkeypatch.setattr(FM, "match_lineup", _lineup)
    jg = {"home": "Torino FC", "away": "AS Roma", "game_id": 7433}

    out = await FM.attach(jg, date_yyyymmdd="20260914")

    assert jg["fotmob"] is out
    assert out["missing"] == ["away 결장 명단 미제공"]
    assert "diff" not in out, "predicted 단계에서는 diff 가 없다"
