"""PA-21 계약 — 사이트 안내문을 거른다. **길이 검사가 못 잡는 것.**

🔴 실측 2026-09-16 g8360(Kashiwa@Jeonbuk): 캐시 기사 17건 중 15건이
   v.daum.net 의 같은 안내문 1,200자였다 —
   "가장 빠른 뉴스가 있고 다양한 정보, 쌍방향 소통이 숨쉬는 다음뉴스를…"
   §7 의 "본문 < 500자" 검사를 통과해서 여태 안 걸렸고, LLM 이 뽑을 사실이
   없어 `out 0` 이 됐다. **S6 확인 0건의 원인이다.**
"""
import pathlib

import pytest

from app.engine import scout_config as SC

BOILER = ("가장 빠른 뉴스가 있고 다양한 정보, 쌍방향 소통이 숨쉬는 다음뉴스를 "
          "만나보세요. 다음뉴스는 국내외 주요이슈와 실시간 속보, 문화생활 및 "
          "다양한 분야의 뉴스를 입체적으로 전달하고 있습니다. " * 4)


def _art(title, body, url="https://x.example/1"):
    return {"title": title, "body": body, "url": url}


def test_반복_안내문을_버린다():
    arts = ([_art("전북 라인업", "포메이션 1-4-2-3-1 — 선발 Cho Wi-Je")]
            + [_art(f"기사{i}", BOILER, f"https://v.daum.net/v/{i}")
               for i in range(15)])
    kept = SC.drop_boilerplate(arts)
    assert len(kept) == 1
    assert "포메이션" in kept[0]["body"]


def test_한_번만_나온_본문은_안_건드린다():
    """🔴 반대 위험 — 한 건짜리는 아무리 짧아도 기사다."""
    arts = [_art("A", "짧은 본문"), _art("B", "다른 짧은 본문")]
    assert SC.drop_boilerplate(arts) == arts


def test_정상_기사가_여러_건이어도_산다():
    """🔴 반대 위험 — 같은 사건을 다룬 기사들이 통째로 죽으면 안 된다."""
    arts = [_art("전북 1", "전북이 가시와를 만난다. 조규성이 선발로 나선다."),
            _art("전북 2", "가시와는 3-4-2-1 로 나온다. 바바가 복귀했다."),
            _art("전북 3", "전북 김진규는 경고 누적으로 결장한다.")]
    assert len(SC.drop_boilerplate(arts)) == 3


def test_앞부분만_비교한다():
    """광고 꼬리 하나로 갈리면 안내문을 못 잡는다."""
    kept = SC.drop_boilerplate([_art("1", BOILER + " 광고 A"),
                                _art("2", BOILER + " 광고 B")])
    assert kept == []


def test_공백_차이는_같은_것으로_본다():
    b = BOILER.replace(" ", "  ")
    assert SC.drop_boilerplate([_art("1", BOILER), _art("2", b)]) == []


@pytest.mark.parametrize("arts", [[], [_art("A", "본문")], None])
def test_기사가_적으면_그대로(arts):
    assert SC.drop_boilerplate(arts) == (arts or [])


def test_본문이_없는_기사는_안_센다():
    """본문 빈 기사끼리 묶여 서로를 죽이면 안 된다."""
    arts = [_art("A", ""), _art("B", ""), _art("C", "진짜 본문")]
    kept = SC.drop_boilerplate(arts)
    assert any(a["body"] == "진짜 본문" for a in kept)


def test_v_daum_은_js_셸이다():
    assert SC.js_only("https://v.daum.net/v/20260916")
    assert SC.js_only("https://sports.daum.net/match/1")
    assert SC.js_only("https://flashscore.com/x")


def test_정상_도메인은_js셸이_아니다():
    """🔴 반대 위험 — js_only 는 fetch 를 통째로 막는다."""
    for dom in ("the-afc.com", "jleague.jp", "chosun.com",
                "transfermarkt.com", "nikkansports.com"):
        assert not SC.js_only(f"https://{dom}/x")


def test_추출이_이_검사를_부른다():
    """만들고 안 이으면 소용없다 — 오늘만 여덟 번 겪었다."""
    src = pathlib.Path("app/collectors/satellite.py").read_text(encoding="utf-8")
    assert "drop_boilerplate(articles)" in src


def test_문턱을_상수로_둔다():
    assert SC.BOILER_MIN_REPEAT == 2
    assert SC.BOILER_HEAD == 200
