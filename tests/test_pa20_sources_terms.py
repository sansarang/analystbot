"""PA-20 계약 — 베팅·예측 차단과 ACL 현지어 검색어.

🔴 실측 2026-09-16 18:08 ACLE 위성 사이클:
     후보 11건이 coinbase.com · freetips.com · footballpredictions.net ·
     livetipsportal.com · sportsgambler.com 로 채워졌고 **coinbase 를 fetch** 했다.
🔴 지시문 §2 "하지 말 것": *영어 검색어로 비영어권 리그 검색(지역지가 안 잡힌다)*.
"""
import pathlib

import pytest
import yaml

from app.engine import scout_config as SC

#: 그날 실제로 후보에 오른 도메인들
SEEN_BAD = ["coinbase.com", "freetips.com", "footballpredictions.net",
            "livetipsportal.com", "sportsgambler.com", "sportskeeda.com"]

#: 정상 소스 — 하나라도 막히면 자료가 줄어든다
GOOD = ["the-afc.com", "jleague.jp", "sportsmole.co.uk", "transfermarkt.com",
        "baseball.yahoo.co.jp", "koreabaseball.com", "fotmob.com",
        "nikkansports.com", "mlb.com", "kicker.de", "chroniclelive.co.uk"]


@pytest.mark.parametrize("dom", SEEN_BAD)
def test_베팅_예측_사이트를_막는다(dom):
    assert SC.blocked(f"https://{dom}/some/page")


@pytest.mark.parametrize("dom", GOOD)
def test_정상_소스는_안_막는다(dom):
    """🔴 반대 위험 — 필터를 넓히면 정상 자료가 줄어든다.

    저장소 규칙: 새 필터를 추가할 때 **반대 위험을 함께 측정**한다.
    """
    assert not SC.blocked(f"https://{dom}/some/page")


def test_등록된_소스와_충돌이_없다():
    """차단 조각이 tier0~3 에 등록된 도메인을 하나도 안 죽인다."""
    d = yaml.safe_load(pathlib.Path("config/sources.yaml").read_text(encoding="utf-8"))
    good = set()
    for sec in ("tier0_primary", "tier1_club_local", "tier2_aggregator",
                "tier3_wire"):
        v = d.get(sec) or {}
        if isinstance(v, dict):
            for lst in v.values():
                if isinstance(lst, list):
                    good |= {str(x).lower() for x in lst}
                elif isinstance(lst, dict):
                    for x in lst.values():
                        if isinstance(x, list):
                            good |= {str(y).lower() for y in x}
                        elif isinstance(x, str):
                            good.add(x.lower())
        elif isinstance(v, list):
            good |= {str(x).lower() for x in v}
    killed = [g for g in good if g and "." in g
              and SC.blocked(f"https://{g}/x")]
    assert not killed, f"등록 소스를 막는다: {killed}"


def test_yaml이_깨지지_않았다():
    """🔴 설정이 안 읽히면 차단이 통째로 꺼진다 — CFG-1 과 같은 사고다."""
    d = yaml.safe_load(pathlib.Path("config/sources.yaml").read_text(encoding="utf-8"))
    for sec in ("blocked", "blocked_fragments", "js_only", "tier0_primary",
                "tier1_club_local", "tier2_aggregator", "tier3_wire"):
        assert sec in d, f"{sec} 섹션이 사라졌다"
    assert len(d["blocked_fragments"]) >= 13


def test_ACL_검색어에_현지어가_있다():
    """§2: ACL 동부는 J리그·K리그 팀이 대부분이다."""
    terms = SC.SEARCH_TERMS.get("acl") or {}
    allq = [q for v in terms.values() if isinstance(v, list) for q in v]
    assert len(allq) >= 6
    assert any(any("぀" <= ch <= "ヿ" for ch in q) for q in allq), "일본어 없음"
    assert any(any("가" <= ch <= "힣" for ch in q) for q in allq), "한국어 없음"


def test_ACL_영어_질의도_남아_있다():
    """⚠️ 태국·호주·중국 팀은 영어가 낫다 — 현지어로 **대체**하지 않는다."""
    terms = SC.SEARCH_TERMS.get("acl") or {}
    allq = [q for v in terms.values() if isinstance(v, list) for q in v]
    assert any("AFC Champions League" in q for q in allq)


def test_ACL_두_단계가_다_있다():
    terms = SC.SEARCH_TERMS.get("acl") or {}
    assert terms.get("pre") and terms.get("lineup")
