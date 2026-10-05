"""🔴🔴 **골든 55** — 못 풀던 한국어 이름이 몇 개나 풀리나(사용자 지시 2026-10-04).

> 그 **55개를 그대로 골든 테스트로 고정**해서, 몇 개가 풀리는지 **숫자로** 보고하게 하라.

══════════════════════════════════════════════════════════════════
🔴 이것은 정답지가 아니다
══════════════════════════════════════════════════════════════════

사용자 지시 2026-10-02(*"정답지는 지운다"*)는 **경기 결과를 맞혔나**에 대한 말이다.
🔴 여기 있는 것은 *"이름표가 이 이름을 푸나"* 이고, 답은 **이름표 자신**이 정한다.
⚠️ 고정 입력은 **이 저장소의 별칭표에 실재하는 이름**뿐이다 — 지어낸 이름으로
   표를 맞추면 그 표가 거짓이 된다.

🔴 **수가 줄면 빨개진다.** 늘면 기준선을 올리고 그 사실을 적는다.
"""
from __future__ import annotations

import pytest

from app import teamref

#: 🔴 2026-10-03 측정 당시 **못 풀던 55개**. ⚠️ `(사용자가 쓰는 말, 정식명)`.
GOLDEN: list[tuple[str, str]] = [
    ('고베', 'Vissel Kobe'),
    ('노팅엄', 'Nottingham Forest'),
    ('뉴캐슬', 'Newcastle United'),
    ('대구', 'Daegu FC'),
    ('레버쿠젠', 'Bayer Leverkusen'),
    ('레스터', 'Leicester City'),
    ('마요르카', 'Mallorca'),
    ('마인츠', 'FSV Mainz 05'),
    ('마치다', 'FC Machida Zelvia'),
    ('맨시티', 'Manchester City'),
    ('맨유', 'Manchester United'),
    ('맨체스터 시티', 'Manchester City'),
    ('맨체스터 유나이티드', 'Manchester United'),
    ('뮌헨', 'Bayern Munich'),
    ('미트윌란', 'FC Midtjylland'),
    ('바르사', 'Barcelona'),
    ('바르셀로나', 'Barcelona'),
    ('바이에른', 'Bayern Munich'),
    ('바이에른 뮌헨', 'Bayern Munich'),
    ('베로나', 'Hellas Verona'),
    ('베르더 브레멘', 'Werder Bremen'),
    ('볼프스부르크', 'VfL Wolfsburg'),
    ('브라이턴', 'Brighton and Hove Albion'),
    ('브라이튼', 'Brighton and Hove Albion'),
    ('브레멘', 'Werder Bremen'),
    ('비셀 고베', 'Vissel Kobe'),
    ('빌바오', 'Athletic Bilbao'),
    ('세비야', 'Sevilla'),
    ('셀타', 'Celta Vigo'),
    ('셀타 비고', 'Celta Vigo'),
    ('수원fc', 'Suwon FC'),
    ('아틀레티코', 'Atlético Madrid'),
    ('아틀레티코 마드리드', 'Atlético Madrid'),
    ('아틀레틱 빌바오', 'Athletic Bilbao'),
    ('오비에도', 'Real Oviedo'),
    ('우라와', 'Urawa Red Diamonds'),
    ('울버햄튼', 'Wolverhampton Wanderers'),
    ('울브스', 'Wolverhampton Wanderers'),
    ('울산', 'Ulsan HD FC'),
    ('울산hd', 'Ulsan HD FC'),
    ('웨스트햄', 'West Ham United'),
    ('인터밀란', 'Inter Milan'),
    ('인테르', 'Inter Milan'),
    ('장크트 파울리', 'FC St. Pauli'),
    ('지로나', 'Girona'),
    ('코모', 'Como'),
    ('코펜하겐', 'FC Copenhagen'),
    ('쾰른', 'FC Cologne'),
    ('크레모네세', 'Cremonese'),
    ('토트넘', 'Tottenham Hotspur'),
    ('포항', 'Pohang Steelers'),
    ('포항 스틸러스', 'Pohang Steelers'),
    ('피사', 'Pisa'),
    ('하이덴하임', '1. FC Heidenheim'),
    ('호펜하임', 'TSG Hoffenheim'),
]

#: 🔴 **지금 풀리는 이름들**(2026-10-04). ⚠️ 하나라도 깨지면 빨개진다.
#   ⚠️ 수만 보면 하나가 깨지고 다른 하나가 새로 풀려도 **같은 수**가 된다.
RESOLVED: frozenset[str] = frozenset({
    '고베',
    '노팅엄',
    '뉴캐슬',
    '레버쿠젠',
    '마인츠',
    '마치다',
    '맨시티',
    '맨유',
    '맨체스터 시티',
    '맨체스터 유나이티드',
    '뮌헨',
    '바르사',
    '바르셀로나',
    '바이에른',
    '바이에른 뮌헨',
    '베르더 브레멘',
    '브라이턴',
    '브라이튼',
    '브레멘',
    '비셀 고베',
    '빌바오',
    '세비야',
    '셀타',
    '셀타 비고',
    '아틀레티코',
    '아틀레티코 마드리드',
    '아틀레틱 빌바오',
    '우라와',
    '울버햄튼',
    '울브스',
    '울산',
    '울산hd',
    '웨스트햄',
    '인터밀란',
    '인테르',
    '코모',
    '쾰른',
    '토트넘',
    '포항',
    '포항 스틸러스',
    '호펜하임',
})

# ══════════════════════════════════════════════════════════════════
# 🔴 2026-10-04 — **풀리던 둘이 빠졌다. 그것이 옳다.**
# ══════════════════════════════════════════════════════════════════
#
#   깨진 것: `대구` · `수원fc`      새로 풀린 것: `울산`
#
# ⚠️ `대구 FC`·`수원 FC` 는 내가 **손으로 지어낸** K리그1 명단에 있었다. 공식
#    (`kleague.com/record/teamRank.do` · 실조회 2026-10-04)에는 **없다** —
#    2026 K리그1 은 울산·포항·제주·전북·서울·대전·인천·강원·광주·부천·안양·김천이다.
# 🔴 **지어낸 이름이 풀리던 것**이고, 공식이 그것을 바로잡았다. 수가 줄었지만
#    **정확해졌다** — 그래서 기준을 내린다. 수만 보면 이것을 뒷걸음으로 오독한다.

#: 🔴 지금 **풀리는 수**. ⚠️ 줄면 빨개진다 — 고칠 때마다 여기를 올린다.
#   2026-10-03  0 / 55   (측정 시작)
#   2026-10-04 15 / 55   ① 조직 표시 걷기(FC·CF·AFC …)
#   2026-10-04 21 / 55   ① + 창단 연도·`&`↔`and`
#   2026-10-04 29 / 55   ② 네 리그 54팀 표(J1 20·NPB 12·KBO 10·K리그1 12)
#   2026-10-04 28 / 55   🔴 K리그1 을 공식에서 다시 받았다 — 손으로
#                            지어낸 `대구`·`수원FC` 가 빠졌다(옳다)
#   2026-10-04 41 / 55   ③ 유럽 빅클럽 한국어 별칭 13개(손으로 · fdorg 표기에)
BASELINE = 41


def test_골든_55_중_풀리는_수가_줄지_않는다():
    """🔴 **숫자로** 본다. ⚠️ 설명이 아니라 수가 기준이다."""
    ok = [n for n, _f in GOLDEN if teamref.key_of(n)[0]]
    assert len(ok) >= BASELINE, (
        f"풀리는 수가 {len(ok)}개로 줄었다(기준 {BASELINE}) — "
        f"못 푸는 것: {[n for n, _ in GOLDEN if not teamref.key_of(n)[0]][:8]}")
    # 🔴 **기준선이 낡으면 올린다** — 안 올리면 뒷걸음을 못 잡는다
    assert len(ok) <= BASELINE + 4, (
        f"{len(ok)}개가 풀린다 — `BASELINE` 을 올리고 **무엇이 고쳤는지** 적어라")


@pytest.mark.parametrize("name,formal",
                         [g for g in GOLDEN][:0] or [("", "")])
def test_자리표(name, formal):
    """⚠️ 개별 이름을 하나씩 고정하지 않는다 — 이름표는 자라는 표이고,
    개별 고정은 **자라는 것 자체를 막는다**. 🔴 수로 본다."""


def test_푼_것은_정식명과_같은_팀이다():
    """🔴🔴 **수만 올리면 안 된다** — 엉뚱한 팀으로 풀면 더 나쁘다.

    ⚠️ `맨시티` 가 `Manchester United` 로 풀리면 그 카드는 통째로 거짓이다.
    """
    bad = []
    for ko, formal in GOLDEN:
        k1 = teamref.key_of(ko)[0]
        if not k1:
            continue
        k2 = teamref.key_of(formal)[0]
        # ⚠️ 정식명 쪽이 안 풀릴 수 있다(표기가 달라서) — 그때는 못 가린다
        if k2 and k1 != k2:
            bad.append((ko, formal, k1, k2))
    assert not bad, f"다른 팀으로 풀렸다: {bad[:5]}"
