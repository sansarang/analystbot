"""SRCH-5 — 슬레이트 카드가 ORDER_V3 판정을 읽는다.

🔴 실측 2026-09-12(운영, ORDER_V3=1 첫 가동): 4경기 판정이 **전부 성공**했는데
   카드는 이렇게 나갔다 —

     ⚠️ 판정 실패 — 오늘 경기 판정을 받지 못해 분석을 완료하지 못했습니다.
     판정 부착 0건 / 분석 대상 4경기 — judge 응답 확인 필요

   원인은 `_render_card` 의 이 한 줄이다:

     judged = [g for g in scheduled if g.get("p_claude") is not None]

   슬레이트 조립이 **확률이 있어야 판정으로 센다.** ORDER_V3 는 확률을 통째로
   지운 경로다(ORD-3 "수치는 전부다 삭제"). 경기별 `render_form_card` 에는
   v3 분기가 있는데, 그 **앞 단계**에서 막혔다.

🔴 카드가 틀린 값을 내보내는 P0 다. 그날 스위치를 되돌려 막았다.

⚠️ **반대 위험이 더 크다 — 구 경로를 건드리면 안 된다.** 운영은 지금도
   구 경로로 돈다. v3 가 아닌 슬레이트는 별점·자격·조합이 종전 그대로여야
   한다. 그 계약이 이 파일의 절반이다.
"""

import pytest

from app import pipeline as P


def _v3_game(gid, away, home, winner, conf="중", *, order=True):
    g = {"game_id": gid, "sport": "kbo", "league": "KBO",
         "status": "scheduled", "away": away, "home": home,
         "away_kr": away, "home_kr": home,
         "starts_at_kst": "2026-09-12T17:00:00+09:00"}
    if order:
        g["winner"] = winner
        g["matchup"] = {"승자": winner, "확신": conf}
        g["order_v3"] = {"수집": {"satellite": 12}, "계측": {"수집": 20, "채택": 11},
                         "갈림길목록": [{"질문": "선발이 6이닝을 막는가"}],
                         "자료": [], "없는것": [], "DB본것": ["오늘 타순"],
                         "DB판정": "확인", "승자변경": False, "DB사유": "",
                         "검색요청": [], "검색n": 0, "검색출처": {}}
    return g


def _analysis(games):
    return {"sport": "kbo", "date": "2026-09-12", "games": games,
            "picks": [], "recommended": [], "combos": {}}


def _legacy_game(gid, away, home, p):
    return {"game_id": gid, "sport": "kbo", "league": "KBO",
            "status": "scheduled", "away": away, "home": home,
            "away_kr": away, "home_kr": home, "p_claude": p,
            "starts_at_kst": "2026-09-12T17:00:00+09:00",
            "matchup": {"p_home": p, "우세": "home"}}


# ═══════════════ ① v3 판정을 판정으로 센다

def test_v3_판정을_실패로_적지_않는다():
    """🔴 실측: 판정 4/4 성공인데 "판정 부착 0건"이 나갔다."""
    out = P._render_card(_analysis([
        _v3_game(1, "NC Dinos", "Doosan Bears", "Doosan Bears"),
        _v3_game(2, "LG Twins", "Samsung Lions", "LG Twins")]))
    assert "판정 실패" not in out
    assert "판정 부착 0건" not in out


def test_경기별_승자가_첫_화면에_있다():
    """드릴다운을 눌러야 결론이 보이면 결론이 없는 것과 같다(§9-3단)."""
    out = P._render_card(_analysis([
        _v3_game(1, "NC Dinos", "Doosan Bears", "Doosan Bears"),
        _v3_game(2, "LG Twins", "Samsung Lions", "LG Twins", "하")]))
    head = out.split(P.DETAIL_SEP)[0]
    assert "Doosan Bears" in head and "LG Twins" in head
    assert "중" in head and "하" in head, "확신이 첫 화면에 없다"


def test_확률과_추천_장치가_v3_카드에_없다():
    """🔴 ORD-3 사용자 지시: "추천 로직도 다 삭제…수치는 전부다 삭제"."""
    out = P._render_card(_analysis([
        _v3_game(1, "NC Dinos", "Doosan Bears", "Doosan Bears")]))
    for banned in ("★", "승률", "자격", "조합", "%", "별점"):
        assert banned not in out, f"v3 카드에 {banned} 가 남았다"


def test_판정_못_받은_경기를_드러낸다():
    """🔴 조용히 빠지면 분석된 것으로 오인된다."""
    out = P._render_card(_analysis([
        _v3_game(1, "NC Dinos", "Doosan Bears", "Doosan Bears"),
        _v3_game(2, "Kia Tigers", "KT Wiz", None, order=False)]))
    assert "Kia Tigers" in out
    assert "판정" in out and "1경기" in out


def test_전부_판정_실패면_정직하게_실패라고_쓴다():
    """게이트를 넓히다 **진짜 실패**를 못 보면 그게 더 나쁘다."""
    out = P._render_card(_analysis([
        _v3_game(1, "NC Dinos", "Doosan Bears", None, order=False)]))
    assert "판정 실패" in out


# ═══════════════ ② 경기별 분석글이 실린다

def test_경기별_v3_카드가_상세에_들어간다():
    """🔴 검색·수집해 놓고 카드에 안 실으면 돈만 쓴 것이다."""
    g = _v3_game(1, "NC Dinos", "Doosan Bears", "Doosan Bears")
    g["order_v3"]["자료"] = [{"질문": "", "답": "박민우가 선발 라인업에서 빠졌다",
                              "소스": "satellite", "소스유형": "뉴스",
                              "시점": "2026-09-12", "계정": "", "url": ""}]
    out = P._render_card(_analysis([g]))
    detail = out.split(P.DETAIL_SEP)[1]
    assert "갈림길" in detail
    assert "박민우" in detail, "수집한 사실이 카드에 없다"


def test_경기별_카드는_기존_렌더러를_쓴다():
    """🔴 사본 금지 — 원본은 `form_card.render_form_card` 다.
    `render_game_easy` 가 그것을 부른다(pipeline.py:4501)."""
    import inspect

    src = inspect.getsource(P._render_card_v3)
    assert "render_game_easy" in src or "render_form_card" in src


# ═══════════════ ③ 반대 위험 — 구 경로는 그대로다

def test_v3_가_아니면_별점_보드가_그대로다():
    """🔴 운영은 지금도 구 경로로 돈다. 여기를 건드리면 그게 P0 다."""
    out = P._render_card(_analysis([
        _legacy_game(1, "NC Dinos", "Doosan Bears", 0.55),
        _legacy_game(2, "LG Twins", "Samsung Lions", 0.52)]))
    assert "★" in out
    assert "자격" in out
    assert "조합" in out


def test_구_경로의_판정_실패_문구도_그대로다():
    out = P._render_card(_analysis([
        {"game_id": 1, "sport": "kbo", "league": "KBO", "status": "scheduled",
         "away": "A", "home": "B", "starts_at_kst": "2026-09-12T17:00:00+09:00"}]))
    assert "판정 실패" in out


def test_v3_카드에도_면책이_붙는다():
    """확률이 없다는 사실을 숨기지 않는다."""
    out = P._render_card(_analysis([
        _v3_game(1, "NC Dinos", "Doosan Bears", "Doosan Bears")]))
    assert "확률도 추천도 내지 않습니다" in out


def test_DB가_승자를_바꾸면_첫_화면에_드러난다():
    """🔴 [ORD-15] 조용한 변경만 없앤다."""
    g = _v3_game(1, "Kia Tigers", "KT Wiz", "Kia Tigers")
    g["order_v3"]["승자변경"] = True
    g["order_v3"]["DB사유"] = "네일이 5경기 연속 6+이닝"
    out = P._render_card(_analysis([g])).split(P.DETAIL_SEP)[0]
    assert "승자 바꿈" in out


def test_분기는_설정이_아니라_데이터로_한다():
    """🔴 [ORD-3] `order_v3` 가 붙은 경기를 보고 가른다 — 설정을 읽으면
    스위치를 끈 뒤에도 옛 원장이 새 카드로 렌더된다."""
    import inspect

    src = inspect.getsource(P._render_card)
    i = src.index("order_v3")
    around = src[max(0, i - 300):i + 300]
    assert "get_settings" not in around, "설정으로 갈랐다"
