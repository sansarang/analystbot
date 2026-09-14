"""D1-1 — 북별 저장 + sharp_proxy + pinnacle_gap (Phase D1, 사용자 지시).

🔴 실측 2026-09-14: 오즈포털 응답에 북별 값이 이미 있다(JS 전용 아님).
   그런데 우리는 평균 한 줄만 저장하고 있었다.
🔴 피나클은 **이름으로 특정할 수 없다** — 북메이커 페이지에 id↔이름 표가
   없다. 그래서 기준은 `sharp_proxy`(환급률 최대 id)다.
"""
from app.collectors import oddsportal as OP
from app.engine import book_gap as BG

# 🔴 [D1-2] **실측 원문 모양 그대로다.** 위치 0 은 배열 `[5.25]`, 위치 1·2 는
#    객체 `{"1":3.8}` — 배열만 받던 정규식이 무·원정 칸을 비워 북별 파싱이
#    0건이 됐다(실측 2026-09-14, 3경기 전부 sharp_proxy 없음).
BLOB = ('{"aaaaaa":{"event":10692547,"odds":[{"active":true,"maxOdds":5.4,'
        '"avgOdds":5.23,"bettingTypeId":1,"scopeId":2,"outcomeId":"x",'
        '"resultId":1,"cntActive":4,"eventId":10692547,"maxOddsProviderId":1133,'
        '"positionsWithProviders":{"0":{"549":{"odds":[5.25],"highestPayout":94.4},'
        '"851":{"odds":[5.25],"highestPayout":95},"1133":{"odds":[5.4],'
        '"highestPayout":92.9},"1205":{"odds":[5],"highestPayout":92.3}},'
        '"1":{"549":{"odds":{"1":3.4},"highestPayout":94.4},"851":{"odds":{"1":3.5},'
        '"highestPayout":95},"1133":{"odds":{"1":3.45},"highestPayout":92.9}},'
        '"2":{"549":{"odds":{"2":1.7},"highestPayout":94.4},"851":{"odds":{"2":1.72},'
        '"highestPayout":95},"1133":{"odds":{"2":1.71},"highestPayout":92.9}}}}],'
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
                .replace('"851":{"odds":{"1":3.5},"highestPayout":95},', "") \
                .replace('"851":{"odds":{"2":1.72},"highestPayout":95},', "")
    got = OP.parse_books(small, three_way=True)[10692547]

    assert got["n"] == 2 and got["sharp_id"] is None
    assert OP.SHARP_MIN_BOOKS == 3


def test_평균_줄은_그대로_남고_북별_줄이_는다():
    books = OP.parse_books(BLOB, three_way=True)[10692547]

    rows = OP.to_rows("Torino", "Roma", {"home": 5.23, "draw": 3.45, "away": 1.71},
                      books=books)

    kinds = sorted({r["book"] for r in rows})
    # [D1-3] soft_proxy 가 더해졌다(마진 최대 북).
    assert kinds == ["oddsportal-avg", "op-1133", "op-549", "op-851",
                     "sharp_proxy", "soft_proxy"]
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


# ── D1-3: soft_proxy (마진 최대 북)

def test_마진이_가장_넓은_북이_사설_대용이다():
    """🔴 ESPN 축구는 우리 IP 에서 403 이다(실측). 같은 스냅샷 안에서 채운다."""
    got = OP.parse_books(BLOB, three_way=True)[10692547]

    # payout: 549=94.4 · 851=95 · 1133=92.9  → 최대 851(sharp) · 최소 1133(soft)
    assert got["sharp_id"] == 851 and got["soft_id"] == 1133


def test_샤프와_사설이_같은_북이면_둘_다_없다():
    """같은 북을 양쪽에 놓으면 gap 이 늘 0이다."""
    one = ('{"x":{"event":1234567,"odds":[{"positionsWithProviders":{'
           '"0":{"549":{"odds":[5.25],"highestPayout":94.4},'
           '"851":{"odds":[5.25],"highestPayout":94.4},'
           '"1133":{"odds":[5.4],"highestPayout":94.4}},'
           '"1":{"549":{"odds":{"1":3.8},"highestPayout":94.4},'
           '"851":{"odds":{"1":3.75},"highestPayout":94.4},'
           '"1133":{"odds":{"1":3.7},"highestPayout":94.4}},'
           '"2":{"549":{"odds":{"2":1.65},"highestPayout":94.4},'
           '"851":{"odds":{"2":1.68},"highestPayout":94.4},'
           '"1133":{"odds":{"2":1.61},"highestPayout":94.4}}}}],"cnt":1}')

    got = OP.parse_books(one, three_way=True)[1234567]

    assert got["sharp_id"] is None and got["soft_id"] is None


def test_soft_proxy_줄이_저장된다():
    books = OP.parse_books(BLOB, three_way=True)[10692547]

    rows = OP.to_rows("Torino", "Roma", {"home": 5.23, "draw": 3.45, "away": 1.71},
                      books=books)

    assert "soft_proxy" in {r["book"] for r in rows}
    soft = {r["side"]: r["odds"] for r in rows if r["book"] == "soft_proxy"}
    assert soft == {"Torino": 5.4, "Draw": 3.45, "Roma": 1.71}, soft


# ── D1-4: 샤프 부재 플래그 (오즈포털 북 넷이 전부 소프트북)

def test_최고_환급률이_96_미만이면_샤프_부재다():
    """🔴 실측 2026-09-14: 오늘 3경기 최고 환급률 94.8 · 95.7 · 95.9%.
    피나클급(97~98%)이 하나도 없다."""
    got = OP.parse_books(BLOB, three_way=True)[10692547]

    assert got["top_payout"] == 95.0        # 851
    assert got["sharp_absent"] is True
    assert OP.SHARP_MIN_PAYOUT == 96.0


def test_샤프가_있으면_플래그가_서지_않는다():
    rich = BLOB.replace('"highestPayout":95}', '"highestPayout":97.5}')
    got = OP.parse_books(rich, three_way=True)[10692547]

    assert got["top_payout"] == 97.5 and got["sharp_absent"] is False


def test_샤프_부재면_값은_두고_해석을_막는다():
    """🔴 값을 지우지 않는다 — 비교 대상이 샤프가 아니었다는 사실을 라벨로."""
    soft = {"home": 1.80, "draw": 3.60, "away": 4.50}
    sharp = {"home": 1.55, "draw": 3.90, "away": 5.50}

    plain = BG.pinnacle_gap(soft, sharp)
    flagged = BG.pinnacle_gap(soft, sharp, sharp_absent=True)

    assert flagged["gap_pp"] == plain["gap_pp"], "값은 그대로다"
    assert flagged["sharp_absent"] is True
    assert flagged["label"].startswith("샤프 부재 · ")
    assert "소프트북끼리" in flagged["label"]
