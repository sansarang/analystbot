"""ORD-20 (5/5단계) — 1~4단계를 판정에 배선한다.

사용자 지시 2026-09-12: "전부다 차례대로 구현해라..각단계별 테스트 진행후
다음단계로 넘어가라"

🔴 ORD-10~16 으로 수집·선별·판정·DB참조가 만들어졌는데 **호출부가 없었다.**
🔴 그리고 종전 ORD-2 경로가 x_search 를 캡 없이 경기당 2~4콜 불렀다
   (실측 2026-09-12: 호출당 $0.40 · 하루 $21~43). 새 경로는 `gather` 가
   `xsearch` 의 경기당 1콜·일일 30 캡을 탄다.
"""

import inspect

import pytest

from app.engine import matchup as MU


# ═══════════════ ① 세 순서가 공존한다

def test_스위치는_기본_꺼짐이다():
    """🔴 오늘 하루에만 순서를 세 번 바꿨다. 되돌릴 길 없이 켜지 않는다."""
    from app.config import Settings

    assert Settings.model_fields["order_v3"].default is False


def test_v3_도_팀폼과_박스스코어를_안_만든다():
    """🔴 여기서 함께 건너뛰지 않으면 **팀 폼 LLM 2콜을 만들어 놓고 버린다.**
    v3 는 자료1~14 를 한 줄도 안 쓴다."""
    jm = inspect.getsource(MU.judge_matchup)
    assert "_skip_db = _order_v2 or _order_v3" in jm
    assert "if _skip_db:\n        home_form, away_form = {}, {}" in jm
    assert "boxes = {} if _skip_db else boxscore_payload(jg)" in jm
    assert "if not _skip_db:\n            await _council" in jm


def test_v3_가_v2_보다_먼저_갈린다():
    jm = inspect.getsource(MU.judge_matchup)
    assert jm.index("if _order_v3:") < jm.index("if _order_v2:")


def test_종전_두_경로를_지우지_않았다():
    """🔴 되돌릴 길이 없으면 다음 사고 때 멈출 수단이 사라진다."""
    jm = inspect.getsource(MU.judge_matchup)
    assert "render_matchup_prompt(jg, boxes, news, prev)" in jm   # 구경로
    assert "_prescout(jg, _brief)" in jm                          # ORDER_V2


def test_목_모드에서는_안_탄다():
    jm = inspect.getsource(MU.judge_matchup)
    i = jm.index("order_v3")
    assert "not is_mock" in jm[i:i + 120]


# ═══════════════ ② 호출 순서가 계약이다

def test_수집이_경기정보보다_먼저다():
    """🔴 collect 가 크롤러 선발로 jg 를 메운다(ORD-16). 반대로 부르면
    game_brief 가 '미정' 을 낸다."""
    v3 = inspect.getsource(MU._judge_v3)
    assert v3.index("gather.collect") < v3.index("game_brief(jg)")


def test_네_단계를_순서대로_부른다():
    v3 = inspect.getsource(MU._judge_v3)
    order = [v3.index(x) for x in ("gather.collect", "triage.run",
                                   "verdict.decide", "dbref.recheck")]
    assert order == sorted(order)


# ═══════════════ ③ 탈락 사유를 전부 남긴다 — 조용한 0 금지

@pytest.mark.parametrize("why", ["수집 0건", "선별 실패", "채택 0건",
                                 "판정 실패", "승자가 이 경기의 팀이 아니다"])
def test_단계마다_탈락_사유가_다르다(why):
    """🔴 어느 단계에서 멈췄는지 모르면 "봇이 죽었나"와 "재료가 없었나"를
    사용자가 구분할 수 없다(실측 2026-09-01 전례)."""
    assert f'"{why}"' in inspect.getsource(MU._judge_v3)


def test_탈락하면_최종_권한을_반납한다():
    """🔴 안 그러면 다음 폴링이 "이미 완료"로 막혀 카드가 0장이 된다
    (P0 전례 2026-09-06)."""
    v3 = inspect.getsource(MU._judge_v3)
    i = v3.index("async def _drop")
    blk = v3[i:i + 500]
    assert "release_final" in blk and 'jg["form_unavailable"] = True' in blk
    assert "logger.warning" in blk


def test_DB_참조_실패는_탈락이_아니다():
    """🔴 있던 판정을 재질의 실패로 잃지 않는다(ORD-1 규약)."""
    v3 = inspect.getsource(MU._judge_v3)
    i = v3.index("dbref.recheck")
    assert "_drop" not in v3[i:i + 300]


def test_재료_없이_판정하지_않는다():
    """🔴 절대 규칙 6 — 채택 0건이면 멈춘다."""
    v3 = inspect.getsource(MU._judge_v3)
    assert 'if not tri["채택"]' in v3
    assert v3.index('if not tri["채택"]') < v3.index("verdict.decide")


# ═══════════════ ④ 카드

def _jg_v3(**kw):
    base = {"sport": "kbo", "league": "KBO", "home": "Doosan Bears",
            "away": "NC Dinos", "lineup_status": "none",
            "winner": "Doosan Bears",
            "matchup": {"승자": "Doosan Bears", "확신": "중"},
            "order_v3": {"갈림길목록": [{"질문": "q"}], "질문": ["q"],
                         "출처": {"pplx": 1},
                         "자료": [{"질문": "q", "답": "a", "소스": "pplx",
                                  "소스유형": "뉴스", "url": ""}],
                         "DB본것": [], "승자변경": False, "DB사유": ""}}
    base["order_v3"].update(kw)
    return base


def test_v3_도_조사_카드를_탄다():
    from app.engine.form_card import render_form_card

    card = render_form_card(_jg_v3(), "kbo")
    assert "🔎 조사 결과" in card and "🏆 승리 예상" in card


def test_카드가_확신을_보인다():
    """[ORD-12] 되살린 것은 확신 한 칸뿐이다 — 설명이 아니라 라벨이다."""
    from app.engine.form_card import render_form_card

    assert "🏆 승리 예상 — 두산 베어스 · 확신 중" in render_form_card(_jg_v3(), "kbo")


def test_승자_변경을_카드가_드러낸다():
    """🔴 [ORD-15] 막지 않는 대신 조용한 변경만 없앤다."""
    from app.engine.form_card import render_form_card

    jg = _jg_v3(승자변경=True, DB사유="타순에서 주전 4명이 빠졌다")
    card = render_form_card(jg, "kbo")
    assert "🔴 우리 기록을 보고 승자를 바꿨다 — 타순에서 주전 4명이 빠졌다" in card


def test_DB에서_본_것을_카드가_밝힌다():
    from app.engine.form_card import render_form_card

    jg = _jg_v3(DB본것=["선발 최근 등판", "오늘 타순"])
    assert "(우리 기록에서 본 것: 선발 최근 등판 · 오늘 타순)" in \
        render_form_card(jg, "kbo")


def test_카드에_우리_수치가_없다():
    """🔴 ORD-3 결정 — 확률·별표·신호등·가치·시장 비교는 없다."""
    from app.engine.form_card import render_form_card

    card = render_form_card(_jg_v3(), "kbo")
    for gone in ("%", "★", "신호등", "가치", "시장", "레이팅", "보드만"):
        assert gone not in card, gone
