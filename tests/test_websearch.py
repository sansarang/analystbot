"""SRCH-2 — Anthropic 웹 검색. **날짜는 코드가 검사한다.**

사용자 지시 2026-09-12: "x seach 삭제....그자리에 안트로픽 서치로"

🔴 왜 날짜 게이트인가. 실측 2026-09-12, 같은 질문을 게이트 없이 던졌을 때:

      질문   "삼성 구자욱의 최근 결장 사유가 부상인가 컨디션 관리인가"
      답     "좌측 가슴뼈 미세골절 — 2루 슬라이딩 역동작"  (인용까지 붙었다)
      실제   그 부상은 **2026년 4월**이다. 오늘 결장 사유는
             "훈련 중 등 담 증세로 긴급 제외"(2026-09-12)였다.

   **인용이 붙은 확신 있는 오답은 "수집 실패"보다 나쁘다.** 카드가 5개월 전
   부상을 오늘 일로 말하게 된다.

🔴 **프롬프트만으로는 부족하다.** 같은 날 `grok-4.20` 에게 "2026-09-10 이후
   기사만"이라고 적어 주었더니 **9월 8일 기사를 근거일자로 적었고**, 기사가
   아니라 "성격이 강함"이라는 추론으로 답을 채웠다. 그래서 코드가 센다.

⚠️ 반대 위험도 함께 잰다 — 게이트가 **멀쩡한 답을 버리면** 그게 더 나쁘다.
   그래서 폐기는 조용하지 않다: 사유별 건수를 돌려주고 로그에 남긴다.
"""

import pytest

from app.collectors import websearch as WS

TODAY = "2026-09-12"


def _jg():
    return {"game_id": 1, "sport": "kbo", "league": "KBO",
            "home": "Samsung Lions", "away": "LG Twins"}


def _payload(*items):
    import json

    return json.dumps({"답": list(items)}, ensure_ascii=False)


def _item(no=1, ans="구자욱이 담 증세로 라인업에서 빠졌다", when=TODAY,
          kind="뉴스", url="https://ex.com/1"):
    return {"번호": no, "답": ans, "근거일자": when, "소스유형": kind, "url": url}


# ═══════════════ ① 날짜 게이트 — 오래된 것을 버린다

def test_오늘_기사는_통과한다():
    rows, m = WS.parse_answers(_payload(_item()), TODAY)
    assert len(rows) == 1
    assert rows[0]["시점"] == TODAY
    assert m["폐기"] == 0


def test_허용_범위_안이면_통과한다():
    """어제·그제 기사는 오늘을 설명할 수 있다."""
    for when in ("2026-09-11", "2026-09-10", "2026-09-09"):
        rows, _ = WS.parse_answers(_payload(_item(when=when)), TODAY)
        assert len(rows) == 1, when


def test_범위_밖_기사는_버린다():
    """🔴 실측: 5개월 전 가슴뼈 골절이 "최근 결장 사유"로 왔다."""
    rows, m = WS.parse_answers(_payload(_item(when="2026-04-14")), TODAY)
    assert rows == []
    assert m["폐기_오래됨"] == 1


def test_경계_하루_차이를_정확히_가른다():
    """경계값은 이 저장소가 반복해서 틀린 자리다."""
    inside, _ = WS.parse_answers(_payload(_item(when="2026-09-09")), TODAY)
    outside, _ = WS.parse_answers(_payload(_item(when="2026-09-08")), TODAY)
    assert len(inside) == 1 and outside == []


def test_근거일자가_없으면_버린다():
    """날짜를 안 적은 답은 언제 것인지 알 수 없다 — 모르는 것은 쓰지 않는다."""
    it = _item()
    del it["근거일자"]
    rows, m = WS.parse_answers(_payload(it), TODAY)
    assert rows == [] and m["폐기_날짜없음"] == 1


@pytest.mark.parametrize("bad", ["", "모름", "2026-13-01", "어제", "2026/09/12"])
def test_읽을_수_없는_날짜는_버린다(bad):
    rows, m = WS.parse_answers(_payload(_item(when=bad)), TODAY)
    assert rows == [] and m["폐기_날짜없음"] == 1


def test_미래_날짜는_버린다():
    """🔴 오늘보다 뒤인 기사는 존재하지 않는다 — 지어낸 것이다."""
    rows, m = WS.parse_answers(_payload(_item(when="2026-09-13")), TODAY)
    assert rows == [] and m["폐기_미래"] == 1


# ═══════════════ ② "모름"은 답이 아니다. 그러나 폐기도 아니다

def test_모름은_행이_되지_않는다():
    rows, m = WS.parse_answers(_payload(_item(ans="모름")), TODAY)
    assert rows == []
    assert m["모름"] == 1
    assert m["폐기"] == 0, "모름은 폐기가 아니다 — 정직한 답이다"


def test_빈_답은_행이_되지_않는다():
    rows, _ = WS.parse_answers(_payload(_item(ans="   ")), TODAY)
    assert rows == []


# ═══════════════ ③ 조용히 버리지 않는다

def test_폐기_건수를_사유별로_돌려준다():
    """🔴 게이트가 멀쩡한 답을 버리면 그게 더 나쁘다 — 세지 않으면 못 묻는다."""
    rows, m = WS.parse_answers(_payload(
        _item(1, when=TODAY),
        _item(2, when="2026-01-01"),
        _item(3, when="없음"),
        _item(4, ans="모름"),
    ), TODAY)
    assert len(rows) == 1
    assert m == {"받음": 4, "채택": 1, "모름": 1, "폐기": 2,
                 "폐기_오래됨": 1, "폐기_날짜없음": 1, "폐기_미래": 0}


def test_전량_폐기도_숫자로_남는다():
    rows, m = WS.parse_answers(_payload(_item(when="2020-01-01")), TODAY)
    assert rows == [] and m["받음"] == 1 and m["폐기"] == 1


def test_폐기를_로그로_남긴다(caplog):
    import logging

    with caplog.at_level(logging.INFO):
        WS.parse_answers(_payload(_item(when="2020-01-01")), TODAY)
    assert any("폐기" in r.getMessage() for r in caplog.records), caplog.text


# ═══════════════ ④ 응답이 데이터가 아닐 때

def test_JSON_이_아니면_빈손이다():
    """🔴 200 OK 산문이 재료 0인 분석을 만든 전례가 있다."""
    rows, m = WS.parse_answers("죄송합니다, 찾지 못했습니다.", TODAY)
    assert rows == [] and m["받음"] == 0


def test_답이_리스트가_아니면_빈손이다():
    rows, _ = WS.parse_answers('{"답": "구자욱 결장"}', TODAY)
    assert rows == []


def test_항목이_딕셔너리가_아니면_건너뛴다():
    rows, m = WS.parse_answers('{"답": ["문자열", {"답": "x", "근거일자": "2026-09-12"}]}',
                               TODAY)
    assert len(rows) == 1 and m["받음"] == 2


# ═══════════════ ⑤ 행 모양 — 새 계약을 만들지 않는다

def test_행_모양이_수집_행과_같다():
    """🔴 사본 금지. 원본은 `gather._row` 다 — 키를 손으로 늘리지 않는다."""
    from app.engine.gather import _row

    rows, _ = WS.parse_answers(_payload(_item()), TODAY)
    assert set(rows[0]) == set(_row("x", src="y"))


def test_소스가_이_채널임을_밝힌다():
    rows, _ = WS.parse_answers(_payload(_item()), TODAY)
    assert rows[0]["소스"] == WS.SOURCE


def test_질문을_행에_남긴다():
    """어느 질문의 답인지 모르면 ②가 짝을 못 맞춘다."""
    rows, _ = WS.parse_answers(_payload(_item(no=2)), TODAY,
                               questions=["첫째", "둘째"])
    assert rows[0]["질문"] == "둘째"


def test_번호가_범위_밖이면_질문을_비운다():
    """🔴 지어낸 번호로 엉뚱한 질문에 붙이면 그게 창작이다."""
    rows, _ = WS.parse_answers(_payload(_item(no=9)), TODAY,
                               questions=["첫째"])
    assert rows[0]["질문"] == ""


# ═══════════════ ⑥ 프롬프트가 날짜를 박는다

def test_프롬프트가_오늘과_하한을_박는다():
    p = WS.build_prompt(_jg(), ["구창모 등판 가능한가"], TODAY)
    assert TODAY in p
    assert "2026-09-09" in p, "허용 하한이 프롬프트에 박혀야 한다"
    assert "구창모 등판 가능한가" in p


def test_프롬프트가_오래된_기사로_채우지_말라고_한다():
    p = WS.build_prompt(_jg(), ["q"], TODAY)
    assert "근거일자" in p
    assert "모름" in p
    assert "오래된 기사로 채우지 마라" in p


def test_프롬프트가_성적을_금지한다():
    """🔴 ORD-5 실측: 조사요청 38문 중 28문(74%)이 성적 조회였다."""
    p = WS.build_prompt(_jg(), ["q"], TODAY)
    assert "성적" in p and "어느 날에나 같은 값" in p


def test_프롬프트가_경기를_밝힌다():
    p = WS.build_prompt(_jg(), ["q"], TODAY)
    assert "Samsung Lions" in p and "LG Twins" in p


# ═══════════════ ⑦ 캡 — 코드가 자른다

def test_질문은_세_개까지다():
    """사용자 결정 2026-09-12: "경기당 1회 질문 3개로 해라"."""
    p = WS.build_prompt(_jg(), [f"q{i}" for i in range(9)], TODAY)
    assert "q3" not in p and "q2" in p


def test_도구_사용_횟수도_캡이_걸린다():
    """🔴 프롬프트가 아니라 **API 가** 자른다 — 지시는 어겨진 전례가 있다."""
    assert WS.TOOL["max_uses"] == WS.MAX_ASKS == 3
    assert WS.TOOL["type"].startswith("web_search_")


# ═══════════════ ⑧ 스위치와 차단

@pytest.mark.asyncio
async def test_꺼져_있으면_호출하지_않는다(monkeypatch):
    """🔴 유료다. 기본은 꺼짐이고, 켜는 것은 사람이 한다."""
    from app.config import Settings

    assert Settings.model_fields["websearch_enabled"].default is False

    fired = {"n": 0}

    async def _boom(*a, **k):
        fired["n"] += 1
        raise AssertionError("꺼져 있는데 호출했다")

    monkeypatch.setattr(WS, "_call", _boom)
    monkeypatch.setattr(WS, "_enabled", lambda s: False)
    assert await WS.ask(_jg(), ["q"], today=TODAY) == []
    assert fired["n"] == 0


@pytest.mark.asyncio
async def test_질문이_없으면_호출하지_않는다(monkeypatch):
    async def _boom(*a, **k):
        raise AssertionError("질문이 없는데 호출했다")

    monkeypatch.setattr(WS, "_call", _boom)
    monkeypatch.setattr(WS, "_enabled", lambda s: True)
    assert await WS.ask(_jg(), [], today=TODAY) == []


@pytest.mark.asyncio
async def test_호출이_터져도_빈손으로_돌려준다(monkeypatch):
    """🔴 검색 실패로 판정을 멈추지 않는다 — 재료가 줄 뿐이다."""
    async def _boom(*a, **k):
        raise RuntimeError("터졌다")

    monkeypatch.setattr(WS, "_enabled", lambda s: True)
    monkeypatch.setattr(WS, "_call", _boom)
    assert await WS.ask(_jg(), ["q"], today=TODAY) == []


@pytest.mark.asyncio
async def test_잔액_소진은_차단기를_내린다(monkeypatch):
    """🔴 잔액 없는 키로 계속 부르면 요금만 탄다(CLAUDE.md 규약)."""
    tripped = []

    async def _boom(*a, **k):
        raise RuntimeError("credit balance is too low")

    monkeypatch.setattr(WS, "_enabled", lambda s: True)
    monkeypatch.setattr(WS, "_call", _boom)
    monkeypatch.setattr("app.engine.credit_guard.trip_credit",
                        lambda at, exc: tripped.append(at))
    await WS.ask(_jg(), ["q"], today=TODAY)
    assert tripped == ["websearch"]


# ═══════════════ ⑨ 비용을 남긴다

def test_단가가_한_곳에만_적혀_있다():
    """🔴 사본 금지. 그리고 출처와 날짜가 붙어 있어야 한다."""
    src = open("app/collectors/websearch.py", encoding="utf-8").read()
    assert "PRICE_SEARCH" in src
    assert "platform.claude.com" in src, "단가 출처가 없다"
    assert "2026-09-12" in src, "언제 확인한 값인지 없다"


def test_비용을_계산해_돌려준다():
    """입력·출력·검색수가 다 들어가야 한다 — 검색만 세면 8할을 놓친다.
    실측 2026-09-12: 입력 31,069 토큰이 비용의 61% 였다."""
    got = WS.cost(input_tokens=31069, output_tokens=625, searches=3)
    assert 0.09 < got < 0.11, got
