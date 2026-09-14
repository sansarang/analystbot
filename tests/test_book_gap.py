"""D1-1 — 북별 저장 + sharp_proxy + pinnacle_gap (Phase D1, 사용자 지시).

🔴 실측 2026-09-14: 오즈포털 응답에 북별 값이 이미 있다(JS 전용 아님).
   그런데 우리는 평균 한 줄만 저장하고 있었다.
🔴 피나클은 **이름으로 특정할 수 없다** — 북메이커 페이지에 id↔이름 표가
   없다. 그래서 기준은 `sharp_proxy`(환급률 최대 id)다.
"""
from app.collectors import oddsportal as OP
from app.engine import book_gap as BG

BLOB = ('{"aaaaaa":{"event":10692547,"odds":[{"active":true,"maxOdds":5.4,'
        '"avgOdds":5.23,"bettingTypeId":1,"scopeId":2,"outcomeId":"x",'
        '"resultId":1,"cntActive":4,"eventId":10692547,"maxOddsProviderId":1133,'
        '"positionsWithProviders":{"0":{"549":{"odds":[5.25],"highestPayout":94.4},'
        '"851":{"odds":[5.25],"highestPayout":95},"1133":{"odds":[5.4],'
        '"highestPayout":92.9},"1205":{"odds":[5],"highestPayout":92.3}},'
        '"1":{"549":{"odds":[3.4],"highestPayout":94.4},"851":{"odds":[3.5],'
        '"highestPayout":95},"1133":{"odds":[3.45],"highestPayout":92.9}},'
        '"2":{"549":{"odds":[1.7],"highestPayout":94.4},"851":{"odds":[1.72],'
        '"highestPayout":95},"1133":{"odds":[1.71],"highestPayout":92.9}}}}],'
        '"cnt":1}')


def test_북별_값을_읽고_환급률_최대를_샤프대용으로_고른다():
    got = OP.parse_books(BLOB, three_way=True)[10692547]

    # 1205 는 세 칸이 다 안 차서 빠진다(반쪽 배당으로 디빅하면 확률이 부푼다).
    assert sorted(got["books"]) == [549, 851, 1133]
    assert got["books"][851] == {"home": 5.25, "draw": 3.5, "away": 1.72}
    assert got["sharp_id"] == 851, "highestPayout 95.0 이 최대"
    assert got["n"] == 3


def test_활성_북이_적으면_샤프대용을_만들지_않는다():
    """🔴 표본이 적으면 '가장 높은 환급률'이 우연이다."""
    small = BLOB.replace('"851":{"odds":[5.25],"highestPayout":95},', "") \
                .replace('"851":{"odds":[3.5],"highestPayout":95},', "") \
                .replace('"851":{"odds":[1.72],"highestPayout":95},', "")
    got = OP.parse_books(small, three_way=True)[10692547]

    assert got["n"] == 2 and got["sharp_id"] is None
    assert OP.SHARP_MIN_BOOKS == 3


def test_평균_줄은_그대로_남고_북별_줄이_는다():
    books = OP.parse_books(BLOB, three_way=True)[10692547]

    rows = OP.to_rows("Torino", "Roma", {"home": 5.23, "draw": 3.45, "away": 1.71},
                      books=books)

    kinds = sorted({r["book"] for r in rows})
    assert kinds == ["oddsportal-avg", "op-1133", "op-549", "op-851", "sharp_proxy"]
    sharp = [r for r in rows if r["book"] == "sharp_proxy"]
    assert {r["side"]: r["odds"] for r in sharp} == {"Torino": 5.25, "Draw": 3.5,
                                                     "Roma": 1.72}


def test_books_를_안_주면_종전과_같다():
    """야구 경로가 같은 함수를 쓴다 — 기본 동작이 바뀌면 안 된다."""
    rows = OP.to_rows("A", "B", {"home": 1.8, "away": 2.0})

    assert {r["book"] for r in rows} == {"oddsportal-avg"}


def test_한쪽이_없으면_gap_은_NULL_이다():
    """🔴 평균으로 대체하지 않는다(문서 '하지 말 것')."""
    assert BG.pinnacle_gap(None, {"home": 1.6, "away": 2.4}) is None
    assert BG.pinnacle_gap({"home": 1.6, "away": 2.4}, None) is None


def test_강팀_기준으로_사설이_후하면_양수다():
    soft = {"home": 1.80, "draw": 3.60, "away": 4.50}    # 강팀(홈) 확률 낮게 = 후하게
    sharp = {"home": 1.55, "draw": 3.90, "away": 5.50}

    got = BG.pinnacle_gap(soft, sharp)

    assert got["side"] == "home"
    assert got["gap_pp"] < 0, "사설이 강팀을 더 낮게 보면 음수"
    flip = BG.pinnacle_gap(sharp, soft)
    assert flip["gap_pp"] > BG.GAP_STRONG_PP
    assert flip["label"] == "사설 후함(약팀 파생 후보)"
