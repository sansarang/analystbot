"""[DEC-4] 매체를 **유형**으로만 분류한다. 등급은 official 만 상위.

사용자 결정 2026-09-21: "결정 4: `config/source_types.yaml` — 매체를
유형(official·wire·beat·general·aggregator)으로만 분류(**사실 기준, 근거 URL**).
등급은 **official 만 상위**, 나머지 unrated(soft). 승격은 `source_scorecard` 의
'공식·라인업과 일치율' **n≥20** 후보만, **사용자 승인**."

🔴 **왜 유형인가.** 종전 `sources.yaml` 은 tier0/1/2/3 으로 **믿음의 등급**을
   매긴다. 그런데 KBO 는 `tier1` 에 `gukjenews.com` 하나뿐이고 나머지는 전부
   `RANK_UNKNOWN` 이다(D41). 등급을 내가 채우면 그건 **취향**이다.
   유형은 다르다 — "구단 공식인가"는 **사실**이고 근거 URL 로 확인된다.

🔴 **등급은 official 만 상위다.** 나머지는 `unrated`(soft) 다. 올리려면
   `source_scorecard` 가 **공식·라인업과의 일치율**을 n≥20 으로 재야 하고,
   그 뒤에도 **사용자가 승인**해야 한다. 코드가 스스로 올리지 않는다.
"""
from __future__ import annotations

import pathlib

import pytest

TYPES = ("official", "wire", "beat", "general", "aggregator")


def _doc():
    import yaml

    p = pathlib.Path("config/source_types.yaml")
    assert p.exists(), "config/source_types.yaml 이 없다"
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def test_유형은_다섯_가지뿐이다():
    for h, row in (_doc().get("sources") or {}).items():
        assert row.get("type") in TYPES, f"{h}: {row.get('type')}"


def test_근거_URL_이_전건_있다():
    """🔴 **사실 기준**이라면 근거가 있어야 한다. 없으면 그건 의견이다."""
    for h, row in (_doc().get("sources") or {}).items():
        u = str(row.get("evidence_url") or "")
        assert u.startswith("https://"), f"{h}: 근거 URL 없음"


def test_못_찾은_근거는_그렇게_적혀_있다():
    """⚠️ `yna.co.kr/about`(400) · `news.yahoo.co.jp/info`(404) 는 **없었다.**
    루트로 대체하고 그 사실을 남긴다 — 없는 URL 을 적으면 그게 거짓이다."""
    d = _doc()
    for h in ("www.yna.co.kr", "news.yahoo.co.jp"):
        row = (d.get("sources") or {}).get(h) or {}
        assert "소개 페이지" in str(row.get("note") or ""), row


def test_official_만_상위다():
    from app.engine.source_types import tier_of

    assert tier_of("sp.baystars.co.jp") == "primary"
    for h in ("www.yna.co.kr", "www.osen.co.kr", "news.yahoo.co.jp",
              "www.mt.co.kr", "www.transfermarkt.com"):
        assert tier_of(h) == "unrated", h
    # 모르는 도메인도 unrated — **조용히 낮추지도 올리지도 않는다**
    assert tier_of("아무데나.example") == "unrated"


def test_코드가_스스로_승격하지_않는다():
    """🔴 승격은 n≥20 실측 + **사용자 승인**이다. 자동 승격 경로가 없어야 한다."""
    import inspect

    from app.engine import source_types as ST

    src = inspect.getsource(ST)
    for banned in ("promote(", "auto_promote", "upgrade("):
        assert banned not in src, f"자동 승격 경로가 있다: {banned}"
    assert "n>=20" in src or "n≥20" in src or "MIN_SAMPLES" in src


def test_승격_후보는_표본이_차야_한다():
    from app.engine.source_types import promotion_candidate

    assert promotion_candidate("www.osen.co.kr", agree=0.9, n=19) is False
    assert promotion_candidate("www.osen.co.kr", agree=0.9, n=20) is True
    # ⚠️ 이미 official 인 곳은 후보가 아니다
    assert promotion_candidate("sp.baystars.co.jp", agree=1.0, n=99) is False


def test_종전_등급표를_건드리지_않았다():
    """⚠️ `sources.yaml` 의 tier0~3 은 **그대로 둔다.** 이 단위는 별개 축이다."""
    import yaml

    d = yaml.safe_load(open("config/sources.yaml", encoding="utf-8"))
    assert "tier0_primary" in d and "tier1_club_local" in d


def test_분류가_실측_도메인에서_왔다():
    """🔴 지어낸 목록이면 이 계약은 아무것도 안 지킨다.
    운영 캐시에서 실제로 본 13종이 들어 있어야 한다."""
    have = set((_doc().get("sources") or {}).keys())
    seen = {"v.daum.net", "news.yahoo.co.jp", "news.google.com",
            "www.sanspo.com", "www.transfermarkt.com", "sp.baystars.co.jp",
            "news.mynavi.jp", "www.goal.com", "www.baseballchannel.jp",
            "www.nikkansports.com", "www.sponichi.co.jp",
            "www.sportingnews.com"}
    missing = seen - have
    assert not missing, f"운영에서 본 도메인이 빠졌다: {sorted(missing)}"
