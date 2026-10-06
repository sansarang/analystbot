"""§12-c 검증기 계약 — **통과·거부 픽스처 한 쌍**이 7종 전부에 있다(§16-b 단계 1).

게이트: *"09-27 다음스포츠 지난주 일정 픽스처가 거부됨"*.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app import verify as V

NOW = datetime(2026, 9, 27, 15, 0, tzinfo=V.KST)


# ══════════════════════════════════════════════════════════════════
# ① 날짜 — 🔴 fail-closed
# ══════════════════════════════════════════════════════════════════

def test_오늘_기사는_통과한다():
    assert V.date_ok("2026-09-27T09:00:00+09:00", NOW).ok


def test_어제_기사도_통과한다():
    assert V.date_ok("2026-09-26T21:00:00+09:00", NOW).ok


def test_지난주_기사는_거부된다():
    v = V.date_ok("2026-09-20T09:00:00+09:00", NOW)
    assert not v.ok and "지난" in v.reason


def test_날짜를_못_읽으면_거부다():
    """🔴 사용자 결정 2026-09-27 — "못 읽는 자료는 통과가 아니라 거부".

    D25 재발 경로를 막는다: "모르면 통과" 였으면 9/11 중지 공지를 오늘 것으로
    읽는다.
    """
    v = V.date_ok(None, NOW)
    assert not v.ok
    assert v.unknown is True          # "틀렸다"가 아니라 "못 읽었다"
    assert v.hardness == "soft"


def test_미래_발행은_거부된다():
    assert not V.date_ok("2026-09-28T09:00:00+09:00", NOW).ok


def test_한국식_날짜를_읽는다():
    assert V.parse_when("2026.09.27. 오후 3:12",
                        assume_tz=V.KST).hour == 15


def test_일본식_날짜를_읽는다():
    got = V.parse_when("2026年9月27日 15:12", assume_tz=V.KST)
    assert got and (got.month, got.day) == (9, 27)


def test_요일_없는_RFC를_읽는다():
    got = V.parse_when("20 Sep 2026 09:00:00 +0900")
    assert got and got.day == 20


def test_naive_한국어_시각을_UTC로_읽지_않는다():
    """실사고 2026-09-27 — 그러면 오늘 오후 기사가 **미래 발행**으로 보인다."""
    assert V.date_ok("2026.09.27. 오후 2:00", NOW).ok


def test_순연_경기는_원래_날짜_기사를_soft로_허용한다():
    v = V.date_ok("2026-09-13T09:00:00+09:00", NOW, allow_original_date=True)
    assert v.ok and v.hardness == "soft"


# ══════════════════════════════════════════════════════════════════
# ② 경기 후 기사 배제
# ══════════════════════════════════════════════════════════════════

def test_경기전_기사는_통과한다():
    assert V.not_post_game("KT 두산전 선발 배제성 예고").ok


@pytest.mark.parametrize("title", [
    "두산 3-5 KT 역전승",
    "라쿠텐 試合終了",
    "Astros beat the Athletics",
    "中信 擊敗 富邦",
])
def test_경기후_기사는_거부된다(title):
    assert not V.not_post_game(title).ok


def test_라인업_번호는_스코어로_오독하지_않는다():
    assert V.not_post_game("KT 선발 오더 1번 김민혁").ok


# ══════════════════════════════════════════════════════════════════
# ③ as_of stale (D26)
# ══════════════════════════════════════════════════════════════════

def test_as_of가_없으면_대상이_아니다():
    assert V.as_of_fresh(None, NOW).ok


def test_방금_시점은_통과한다():
    assert V.as_of_fresh(NOW - timedelta(minutes=5), NOW).ok


def test_30분_지난_시점은_stale이다():
    v = V.as_of_fresh(NOW - timedelta(minutes=45), NOW)
    assert not v.ok and "stale" in v.reason


# ══════════════════════════════════════════════════════════════════
# ④ 중복 제거 — n_sources 는 서로 다른 원문 수다
# ══════════════════════════════════════════════════════════════════

def test_같은_URL은_한_건이다():
    arts = [{"url": "https://x/1", "body": "가"},
            {"url": "https://x/1?utm=a", "body": "가"}]
    kept, dups = V.dedupe(arts)
    assert len(kept) == 1 and len(dups) == 1


def test_같은_보도자료_8건은_원문_1건이다():
    body = "주니치는 오늘 涌井 를 선발로 예고했다 그는 2주 만에 재등록됐다"
    arts = [{"url": f"https://m{i}/a", "body": body} for i in range(8)]
    kept, dups = V.dedupe(arts)
    assert len(kept) == 1, [a["url"] for a in kept]
    assert len(dups) == 7


def test_다른_기사는_따로_센다():
    arts = [{"url": "https://a/1",
             "body": "강원 김대원 누적경고 결장에서 복귀 가능해졌다"},
            {"url": "https://b/1",
             "body": "인천 센터백 부상으로 임시 수비 구성이 불가피하다"}]
    kept, _ = V.dedupe(arts)
    assert len(kept) == 2


# ══════════════════════════════════════════════════════════════════
# ⑤ 공식 우선
# ══════════════════════════════════════════════════════════════════

def test_예측_사이트는_판정_입력에_못_쓴다():
    assert not V.admissible(V.TIER_FORECAST).ok


def test_프리뷰는_라인업_확인용만이다():
    assert not V.admissible(V.TIER_PREVIEW, purpose="judgement").ok
    assert V.admissible(V.TIER_PREVIEW, purpose="lineup").ok


def test_공식은_hard다():
    assert V.admissible(V.TIER_OFFICIAL).hardness == "hard"
    assert V.admissible(V.TIER_PRIMARY).hardness == "likely"


def test_출처가_갈리면_낮은_층이_이긴다():
    assert V.wins(V.TIER_OFFICIAL, V.TIER_PRIMARY) == V.TIER_OFFICIAL
    assert V.wins(V.TIER_PREVIEW, V.TIER_PRIMARY) == V.TIER_PRIMARY


# ══════════════════════════════════════════════════════════════════
# ⑥ 인용 검증
# ══════════════════════════════════════════════════════════════════

def test_본문에_있는_인용은_hard다():
    body = '정경호 감독은 "하이프레싱 강도를 낮춘다"고 말했다'
    v = V.quote_grounded("하이프레싱 강도를 낮춘다", body)
    assert v.ok and v.hardness == "hard"


def test_본문에_없는_인용은_soft로_떨어진다():
    """🔴 LLM 추출기는 그럴듯한 인용을 만들어낸다. 본문 대조가 유일한 방어다."""
    v = V.quote_grounded("총력전으로 간다", "감독은 선발 로테이션을 지켰다")
    assert not v.ok and v.hardness == "soft"


def test_공백과_따옴표_표기가_달라도_대조된다():
    body = "감독은 “주전을 쉬게 한다” 고 밝혔다"
    assert V.quote_grounded('"주전을 쉬게 한다"', body).ok


# ══════════════════════════════════════════════════════════════════
# 🔴 한 글자 오타로 **진짜 발견을 버리지 않는다** (실측 2026-10-02)
# ══════════════════════════════════════════════════════════════════

#: 🔴 실측 그대로다. 라이브에서 qwen3:8b 가 `ソフトバンク` 의 `ク` 를 떨어뜨렸고,
#   그 탓에 **唐川 은퇴 세레머니(10/3)** 가 통째로 사라졌다 — 사람이 손으로 쓴
#   분석의 변수 R7 이 그것이다.
_BODY = ("千葉ロッテマリーンズは、ロッテ・唐川侑己投手引退セレモニーを10月3日の"
         "ソフトバンク戦（ZOZOマリンスタジアム、18時00分試合開始）の試合後に"
         "実施すると発表した。角中勝也外野手も引退する。")
_TYPO = ("ロッテ・唐川侑己投手引退セレモニーを10月3日のソフトバン戦"
         "（ZOZOマリンスタジアム、18時00分試合開始）の試合後に")








# ══════════════════════════════════════════════════════════════════
# ⑦ 실측 예 — 🔴 §16-b 단계 1 게이트
# ══════════════════════════════════════════════════════════════════

def test_다음스포츠_지난주_일정이_거부된다():
    """🔴 게이트 원문: *"09-27 다음스포츠 지난주 일정 픽스처가 거부됨"*.

    실측: 그 페이지는 JS 렌더링이라 `<time>`·`meta` 날짜가 **0건**이고, 행
    날짜가 `09.27 일` 처럼 **연도가 없다.** 연도 없는 표기는 못 읽는 것으로
    보고 fail-closed 로 떨어뜨린다 — 지난주 4경기를 오늘 것으로 읽은 사고가
    바로 이것이었다.
    """
    v = V.slate_date_ok(["09.27 일", "09.20 토"], date(2026, 9, 27), now=NOW)
    assert not v.ok
    assert v.unknown is True
    assert "연도" in v.reason


def test_연도가_있는_일정_페이지는_통과한다():
    v = V.slate_date_ok(["2026-09-27", "2026-09-28"], date(2026, 9, 27),
                        now=NOW)
    assert v.ok


def test_슬레이트_날짜가_페이지에_없으면_거부된다():
    v = V.slate_date_ok(["2026-09-20"], date(2026, 9, 27), now=NOW)
    assert not v.ok and "없다" in v.reason


def test_날짜가_아예_없는_페이지는_거부된다():
    assert not V.slate_date_ok([], date(2026, 9, 27), now=NOW).ok


# ══════════════════════════════════════════════════════════════════
# 묶음
# ══════════════════════════════════════════════════════════════════

def test_통과하는_기사():
    art = {"title": "주니치 涌井 재등록 선발 예고",
           "body": '감독은 "2주 쉬었다"고 말했다',
           "published_at": "2026-09-27T08:00:00+09:00",
           "tier": V.TIER_PRIMARY, "quote": "2주 쉬었다"}
    got = V.check_article(art, NOW)
    assert got.ok and got.hardness == "likely"


def test_하나라도_거부면_거부다():
    art = {"title": "주니치 3-1 야쿠르트", "body": "",
           "published_at": "2026-09-27T08:00:00+09:00",
           "tier": V.TIER_PRIMARY}
    got = V.check_article(art, NOW)
    assert not got.ok and any("post_game" in r for r in got.reasons)


def test_못_읽은_것은_unknown으로_구분된다():
    """🔴 §7-5e — 검색 0건은 unknown 이지 refuted 가 아니다. 같은 규율이다."""
    art = {"title": "선발 예고", "body": "", "published_at": None,
           "tier": V.TIER_PRIMARY}
    got = V.check_article(art, NOW)
    assert not got.ok and got.unknowns == ["date"]


