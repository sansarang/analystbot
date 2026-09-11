"""SCT-1 · WIN-1 — 딥서치가 변수를 정하고, 승자 칸을 코드가 검사한다.

사용자 지시 2026-09-11: "변수를 딥서치가 정하게 하고 찾아온 딥서치를 최종
제미나이가 분석해서 승패를 예측하게 해라." · "스위치 기본 켜라."

🔴 순서를 뒤집되 **판정 단계 안에서** 뒤집는다. 파이프라인 순서를 건드리면
   L1 사실 감시가 정찰 변수를 원문에서 못 찾아 무력해진다 — 자료15 로 넣으면
   그 변수가 **판정 프롬프트에 들어가므로** 감시가 종전처럼 대조할 수 있다.

🔴 WIN-1 은 절제 실험에서 나왔다(운영 재료 game=1733, 4회 호출):
     자료15 없음 → 승자='home' 2/2   · 자료15 있음 → 승자='삼성' 2/2
   자료15 가 원인이 **아니었다.** 진짜 결함은 `결론.승자` 를 아무도 검사하지
   않는다는 것이고(`check_flow` 는 예상점수만 본다), gemini 는 seed 를 못 받아
   (`openai_compat._NO_SEED`) 회차마다 흔들린다.
"""

import pytest

from app.engine import matchup as MU


def _jg(home="Samsung Lions", away="Kiwoom Heroes"):
    return {"game_id": 1, "sport": "kbo", "home": home, "away": away}


# ═══════════════ WIN-1 승자 정합성

@pytest.mark.parametrize("raw", ["home", "away", "KT Wiz", "", None])
def test_경기의_팀이_아니면_p_home_방향으로_정정한다(raw):
    v = {"결론": {"승자": raw, "판단": "x"}, "p_home": 0.63}
    MU.normalize_winner(v, _jg())
    assert v["결론"]["승자"] == "Samsung Lions"
    assert "정정" in v["승자_정정"]


def test_원정_우세면_원정팀으로():
    v = {"결론": {"승자": "home"}, "p_home": 0.37}
    MU.normalize_winner(v, _jg())
    assert v["결론"]["승자"] == "Kiwoom Heroes"


@pytest.mark.parametrize("w", ["삼성", "Samsung Lions", "samsung lions"])
def test_약칭도_정식표기도_정상으로_본다(w):
    """🔴 반대 위험 — 멀쩡한 승자를 바꾸면 그게 더 나쁘다."""
    v = {"결론": {"승자": w}, "p_home": 0.63}
    assert MU.normalize_winner(v, _jg()) is None
    assert v["결론"]["승자"] == w
    assert "승자_정정" not in v


def test_박빙이면_손대지_않는다():
    """0.50 은 방향이 없다 — 방향 없는 값으로 고쳐 쓰는 것이 창작이다."""
    v = {"결론": {"승자": "home"}, "p_home": 0.5}
    assert MU.normalize_winner(v, _jg()) is None
    assert v["결론"]["승자"] == "home"


def test_p_home_이_없으면_손대지_않는다():
    v = {"결론": {"승자": "home"}}
    assert MU.normalize_winner(v, _jg()) is None


def test_두_팀_모두에_걸리면_손대지_않는다는_것이_아니라_정정한다():
    """모호한 표기는 그대로 두면 카드가 거짓을 말한다 — p_home 이 답을 안다."""
    v = {"결론": {"승자": "Lions"}, "p_home": 0.63}   # 양쪽 다 'Lions'
    MU.normalize_winner(v, {"game_id": 1, "sport": "kbo",
                            "home": "Samsung Lions", "away": "Seibu Lions"})
    assert v["결론"]["승자"] == "Samsung Lions"


def test_판정_문에_배선돼_있다():
    """🔴 존재하는 것과 불리는 것은 다르다(PGP-2)."""
    src = open("app/engine/matchup.py", encoding="utf-8").read()
    body = src[src.index("def apply_matchup"):src.index("def apply_matchup") + 900]
    assert "normalize_winner" in body


# ═══════════════ SCT-1 정찰 → 자료15

def test_스위치가_기본_켜짐이다():
    from app.config import Settings

    assert Settings.model_fields["deepsearch_first"].default is True


def test_정찰이_비면_프롬프트가_바이트_동일이다():
    """🔴 `test_batter_freeze_gate` 가 프롬프트를 BAT-1 시점과 대조한다."""
    p = "자료들…\n" + MU._RULES_MARK + "\n규칙"
    for empty in (None, {}, {"변수": [], "발견": []}):
        assert MU.insert_scout(p, empty) == p


def test_정찰_결과가_규칙_앞에_들어간다():
    p = "자료들…\n" + MU._RULES_MARK + "\n규칙"
    out = MU.insert_scout(p, {"변수": ["홈 선발이 5이닝 미만"], "발견": [],
                              "요약": "x"})
    assert out != p
    assert out.index("15.") < out.index(MU._RULES_MARK)
    assert "홈 선발이 5이닝 미만" in out


def test_자료15_가_변수의_출처임을_밝힌다():
    from app.engine.prompts import SCOUT_BLOCK

    assert "변수는 여기 있는 것을 쓴다" in SCOUT_BLOCK
    assert "자료와 어긋나는 변수는 버려라" in SCOUT_BLOCK


def test_정찰_프롬프트가_승패를_묻지_않는다():
    """정찰은 무엇이 경기를 가르는지만 말한다 — 승패는 최종 판정의 몫이다."""
    from app.engine.prompts import SCOUT

    assert "승패·확률을 적지 마라" in SCOUT
    assert "p_home" in SCOUT and "네 몫이 아니다" in SCOUT


def test_정찰이_변수_형식_규칙을_재사용한다():
    """🔴 사본 금지 — 임계 규칙을 다시 적으면 채점 불가 변수가 샌다."""
    from app.engine.prompts import SCOUT, VARIABLE_AXES

    assert VARIABLE_AXES in SCOUT


def test_정찰_실패는_종전_경로다():
    """조사가 안 됐다고 판정을 멈추지 않는다 — 폴백이 곧 '정찰 없음'이다."""
    src = open("app/engine/matchup.py", encoding="utf-8").read()
    i = src.index('jg["scout"] = await _scout')
    body = src[i - 400:i + 600]
    assert "except Exception" in body
    assert "insert_scout" in body
