"""ORD-12 (3단계) — 조사 결과만으로 승자 + 확신 한 칸.

사용자 지시 2026-09-12: "ai가 db 참조 승패를 예측한다" · "나로 해라..확신 한
칸만 살려라"

🔴 ORD-3 에서 지운 것 중 `확신` **하나만** 되살린다. 설명이 아니라 라벨이고,
   4단계에서 DB 와 모순이 났을 때 낮출 곳이 필요하다.
"""

import pytest

from app.engine import matchup as MU
from app.engine import verdict as V


def _jg():
    return {"game_id": 1737, "sport": "kbo", "league": "KBO",
            "home": "Doosan Bears", "away": "NC Dinos"}


def _tri(kept=1, missing=1):
    return {"채택": [{"답": f"사실{i}", "소스": "pplx", "시점": "2026-09-11",
                     "계정": ""} for i in range(1, kept + 1)],
            "갈림길": [{"질문": "구창모가 5이닝을 넘기는가", "왜": "1번"}],
            "변수": ["구창모 5이닝 미만"],
            "없는것": [f"없는것{i}" for i in range(1, missing + 1)],
            "DB요청": []}


def _patch(monkeypatch, text):
    import app.engine.team_form as TF

    async def _cj(prompt, *, model, max_tokens, role, mock=False):
        return text

    monkeypatch.setattr(TF, "complete_json", _cj)


# ═══════════════ ① 확신 — 되살린 것은 이 한 칸뿐

@pytest.mark.parametrize("raw,want", [("상", "상"), ("중", "중"), ("하", "하")])
def test_세_값을_그대로_쓴다(raw, want):
    assert V.level(raw) == want


@pytest.mark.parametrize("raw", ["high", "높음", "", None, "매우 높음", 3])
def test_모르는_라벨은_하로_떨어뜨린다(raw):
    """🔴 그대로 실으면 카드가 못 읽는다. 낮은 쪽이 안전한 방향이다."""
    assert V.level(raw) == "하"


def test_눈금을_새로_만들지_않았다():
    """원본은 `prompts.MATCHUP` 의 확신도(상|중|하)다."""
    from app.engine.prompts import MATCHUP

    assert V.LEVELS == ("상", "중", "하")
    assert '"확신도": "상|중|하"' in MATCHUP


def test_모르면_하라고_프롬프트가_말한다():
    from app.engine.prompts import JUDGE2

    assert "모르면 `하` 다" in JUDGE2
    assert "확신이 유일한" in JUDGE2


# ═══════════════ ② 설명은 되돌아오지 않는다

def test_출력은_승자와_확신_둘뿐이다():
    """🔴 확신을 되살렸다고 설명이 도로 들어오면 안 된다."""
    from app.engine.prompts import JUDGE2

    out = JUDGE2[JUDGE2.index("[출력]"):]
    assert '"승자"' in out and '"확신"' in out
    for gone in ("p_home", "근거", "변수", "전개", "예상점수", "우세",
                 "뉴스반영", "추가확인"):
        assert gone not in out, gone


def test_DB가_이_자리에_오지_않는다고_못박는다():
    from app.engine.prompts import JUDGE2

    assert "이 자리에 오지 않는다" in JUDGE2
    assert "기억으로 판단하지 마라" in JUDGE2


# ═══════════════ ③ 2단계 산출을 그대로 받는다

def test_채택_자료를_원문으로_싣는다():
    """🔴 다시 쓰면 창작이다."""
    t = V.fmt_kept([{"답": "구창모 예고", "소스": "x", "계정": "@a",
                     "시점": "2026-09-11"}])
    assert t == "1. [x @a] [2026-09-11] 구창모 예고"


def test_없는것을_그대로_보여준다():
    """🔴 못 찾은 것을 숨기면 판정이 다 아는 것처럼 답한다."""
    assert V.fmt_missing(["오늘 타순"]) == "· 오늘 타순"
    assert V.fmt_missing([]) == "(없음)"


def test_프롬프트에_자료1_14가_없다():
    p = V.render(_jg(), "brief", _tri())
    assert "[입력 자료]" not in p and "{{" not in p
    assert "구창모가 5이닝을 넘기는가" in p and "사실1" in p and "없는것1" in p


# ═══════════════ ④ 재료 없으면 판정하지 않는다

@pytest.mark.asyncio
async def test_채택_0건이면_판정하지_않는다(monkeypatch, caplog):
    """🔴 절대 규칙 6 — 팀 이름 위에서 승자를 고르는 것이 곧 기억으로 판정하기다."""
    called = {"n": 0}
    import app.engine.team_form as TF

    async def _cj(*a, **k):
        called["n"] += 1
        return '{"승자": "Doosan Bears"}'

    monkeypatch.setattr(TF, "complete_json", _cj)
    tri = _tri(); tri["채택"] = []
    with caplog.at_level("WARNING"):
        assert await V.decide(_jg(), "b", tri) is None
    assert called["n"] == 0
    assert "채택 0건" in caplog.text


@pytest.mark.asyncio
async def test_승자가_없으면_None(monkeypatch):
    _patch(monkeypatch, '{"확신": "상"}')
    assert await V.decide(_jg(), "b", _tri()) is None


@pytest.mark.asyncio
async def test_파싱_실패는_None(monkeypatch):
    _patch(monkeypatch, "미안하지만 알 수 없습니다")
    assert await V.decide(_jg(), "b", _tri()) is None


@pytest.mark.asyncio
async def test_정상이면_승자와_확신을_돌려준다(monkeypatch):
    _patch(monkeypatch, '{"승자": "Doosan Bears", "확신": "중"}')
    out = await V.decide(_jg(), "b", _tri())
    assert out == {"승자": "Doosan Bears", "확신": "중"}


@pytest.mark.asyncio
async def test_확신이_빠지면_하로_채운다(monkeypatch):
    _patch(monkeypatch, '{"승자": "Doosan Bears"}')
    assert (await V.decide(_jg(), "b", _tri()))["확신"] == "하"


# ═══════════════ ⑤ 판정 배선 — 확신이 실린다

def test_apply_winner_가_확신을_싣는다():
    jg = _jg()
    assert MU.apply_winner(jg, {"승자": "두산", "확신": "상"}) is True
    assert jg["matchup"]["확신"] == "상"
    assert jg["winner"] == "Doosan Bears"


def test_모르는_확신은_하로_실린다():
    jg = _jg()
    MU.apply_winner(jg, {"승자": "두산", "확신": "매우 높음"})
    assert jg["matchup"]["확신"] == "하"


def test_확신이_없으면_칸을_만들지_않는다():
    """🔴 ORD-3 경로(승자만)는 이 칸이 없다 — 그쪽 동작은 바뀌지 않는다."""
    jg = _jg()
    MU.apply_winner(jg, {"승자": "두산"})
    assert "확신" not in jg["matchup"]


def test_경기의_팀이_아니면_확신이_있어도_버린다():
    """🔴 확률이 없어 고쳐 쓸 근거가 없다(실측: gemini 가 `KT Wiz` 를 냈다)."""
    jg = _jg()
    assert MU.apply_winner(jg, {"승자": "KT Wiz", "확신": "상"}) is False
    assert "matchup" not in jg


def test_원장_컬럼을_새로_만들지_않았다():
    """확신은 기존 `confidence` 칸에 들어간다."""
    from app.engine.pick_ledger import _row_from_game

    jg = {"game_id": 9, "sport": "kbo", "home": "Doosan Bears",
          "away": "NC Dinos", "matchup": {"승자": "Doosan Bears", "확신": "중"}}
    row = _row_from_game(jg, {"sport": "kbo", "date": "2026-09-12"}, {})
    assert row["confidence"] == "중"
