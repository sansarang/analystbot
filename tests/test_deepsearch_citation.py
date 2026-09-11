"""DSM-1 — 딥서치 재료가 **실제로 쓰였는지** 잴 수 있어야 한다.

🔴 왜. 종전 성과 지표는 `이동_pp` 하나였고, `0.0%p` 가 두 가지를 뭉갠다:
     (a) 재료가 쓸모없어서 안 움직였다
     (b) 재료는 좋았는데 판정이 안 썼다
   실측 2026-09-11: KBO 4경기 **전부 이동 0.0%p** · 발견 소스유형 **100% 뉴스** ·
   위성 캐시는 경기당 12건이 쌓여 있었다. 어느 쪽인지 구분할 수 없으니
   위성을 고쳐도 나아졌는지 증명할 방법이 없었다.

🔴 **모델 자백만 믿지 않는다.** 두 축으로 센다 —
   모델이 적은 `근거번호` 와 우리가 맞춘 `url`. `deepsearch._src` 와 같은 태도다.
⚠️ `url` 축은 **하한**이다. 기사를 읽고 썼는데 url 을 안 적을 수 있다.
"""

import pytest

# ⚠️ `citation_stats` 는 **모듈 최상단에서 임포트하지 않는다.** 수정 전 코드에
#    없는 심볼이라 파일이 통째로 ImportError 로 죽고, 그러면 배선 계약이
#    "심볼이 없다"로 실패해 **결함 자체를 겨눈 단언**에 닿지 못한다.
from app.engine.deepsearch import apply_findings


def citation_stats(*a, **k):
    from app.engine.deepsearch import citation_stats as _f

    return _f(*a, **k)


def _data(발견, n=3, urls=None, 출처=None):
    return {"발견": 발견,
            "조정": {"delta_pp": 0, "사유": "x", "단일기사여부": False},
            "요약": "y",
            "_재료": {"n": n, "출처": 출처 or {"satellite": n},
                      "urls": urls or [(1, "https://a.com/1"),
                                       (2, "https://b.com/2"),
                                       (3, "https://c.com/3")]}}


def _jg(p=0.60):
    return {"game_id": 1, "sport": "kbo", "away": "A", "home": "B",
            "p_claude": p, "matchup": {"p_home": p, "우세": "home"}}


# ═══════════════ ① 두 축으로 센다

def test_근거번호로_인용을_센다():
    st = citation_stats(_data([{"사실": "x", "근거번호": 2}]))
    assert st["인용_기사"] == 1 and st["축"]["번호"] == 1


def test_url_로도_인용을_센다():
    """번호를 안 적어도 url 이 맞으면 인용이다."""
    st = citation_stats(_data([{"사실": "x", "url": "https://b.com/2"}]))
    assert st["인용_기사"] == 1 and st["축"]["url"] == 1


def test_같은_기사를_두_축이_가리키면_한_번만_센다():
    st = citation_stats(_data([{"사실": "x", "근거번호": 2,
                                "url": "https://b.com/2"}]))
    assert st["인용_기사"] == 1
    assert st["축"] == {"번호": 1, "url": 1}


def test_url_정규화_차이는_같은_기사로_본다():
    """스킴·www·쿼리·꼬리 슬래시로 매칭이 깨지면 인용률이 거짓으로 낮아진다."""
    st = citation_stats(_data([{"사실": "x",
                                "url": "HTTP://WWW.b.com/2/?utm=1#top"}]))
    assert st["축"]["url"] == 1


# ═══════════════ ② 아는 척하지 않는다

def test_주입이_0이면_인용률은_None():
    """0/0 을 0% 로 적으면 '재료가 없었다'와 '안 썼다'가 또 같아진다."""
    st = citation_stats({"발견": [], "_재료": {"n": 0, "출처": {}, "urls": []}})
    assert st["인용률"] is None and st["주입"] == 0


def test_범위_밖_번호는_인용이_아니다():
    """🔴 지어낸 번호가 인용률을 부풀리면 그 측정은 쓸모없다."""
    st = citation_stats(_data([{"사실": "x", "근거번호": 99}]))
    assert st["인용_기사"] == 0


@pytest.mark.parametrize("no", [0, -1, "2", 2.0, None])
def test_숫자가_아닌_번호는_무시한다(no):
    st = citation_stats(_data([{"사실": "x", "근거번호": no}]))
    assert st["축"]["번호"] == 0


def test_외부_url_은_인용이_아니다():
    """PPLX 가 직접 물어온 url 은 **우리가 모아 준 재료가 아니다.**"""
    st = citation_stats(_data([{"사실": "x", "url": "https://newspim.com/x"}]))
    assert st["인용_기사"] == 0


def test_재료가_없으면_빈_계측():
    st = citation_stats({"발견": [{"사실": "x", "근거번호": 1}]})
    assert st["주입"] == 0 and st["인용_기사"] == 0


# ═══════════════ ③ 배선 — 원장에 실제로 남는가

def test_판정에_계측이_실린다():
    jg, d = _jg(), _data([{"사실": "x", "근거번호": 1}])
    apply_findings(jg, d)
    mat = jg["deepsearch"]["재료"]
    assert mat["주입"] == 3 and mat["인용_기사"] == 1
    assert mat["인용률"] == pytest.approx(1 / 3, abs=1e-3)
    assert mat["출처"] == {"satellite": 3}


def test_판정이_없어도_재료는_기록된다():
    """🔴 재료가 들어갔다는 사실을 버리면 '왜 안 움직였나'를 못 푼다."""
    jg = {"game_id": 1, "sport": "kbo", "matchup": {}}      # p_claude 없음
    apply_findings(jg, _data([{"사실": "x", "근거번호": 1}]))
    assert jg["deepsearch"]["재료"]["주입"] == 3


def test_내부_계측키는_카드로_새지_않는다():
    """`_재료` 는 우리 계측용이다. 발견·요약과 같은 칸에 남으면 안 된다."""
    jg, d = _jg(), _data([{"사실": "x", "근거번호": 1}])
    apply_findings(jg, d)
    assert "_재료" not in d
    assert "_재료" not in jg["deepsearch"]


def test_이동이_0이어도_인용은_따로_보인다():
    """이 계측의 존재 이유 — 0.0%p 의 두 가지 뜻을 가른다."""
    jg, d = _jg(), _data([{"사실": "x", "근거번호": 1}])
    res = apply_findings(jg, d)
    assert res["moved"] == 0.0
    assert jg["deepsearch"]["재료"]["인용_기사"] == 1


# ═══════════════ ④ 프롬프트가 번호를 요구한다

def test_프롬프트가_근거번호를_요구한다():
    from app.engine.deepsearch import PROMPT

    assert "근거번호" in PROMPT
    assert "지어내지 마라" in PROMPT


def test_주입_기사에_번호가_붙는다():
    """번호 체계를 새로 만들지 않는다 — `_inject_articles` 가 이미 1..N 이다."""
    from app.engine.deepsearch import _inject_articles

    out = _inject_articles("P", [{"title": "t1", "url": "u1"},
                                 {"title": "t2", "url": "u2"}])
    assert "\n1. " in out and "\n2. " in out
