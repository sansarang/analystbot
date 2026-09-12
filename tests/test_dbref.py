"""ORD-13 (4단계) — DB 는 참조용이다. 확인하거나 반박할 뿐, 정하지 않는다.

사용자 지시 2026-09-12: "db가치를 내린다..db는 단순 참조용이다"

🔴 왜 필요한가: 3단계 실측 2026-09-12 — 확신 4/4 전부 `하`, `DB요청` 이 네 경기
   모두 ['선발 최근 등판', '오늘 타순']. 검색으로 못 채우는데 우리는 갖고 있다.
🔴 동시에 왜 위험한가: ORD-1 실측 — DB 를 뒤에 붙였더니 ④가 3/3 돌았고
   NYM@NYY 는 **승자째 뒤집혔다**(0.54 NYY → 0.46 NYM). 막을 장치가 없었다.
"""

import pytest

from app.engine import dbref as D


def _jg():
    return {"game_id": 1737, "sport": "kbo", "league": "KBO",
            "home": "Doosan Bears", "away": "NC Dinos"}


def _tri(req=None):
    return {"갈림길": [{"질문": "구창모가 5이닝을 넘기는가"}],
            "채택": [{"답": "x", "소스": "pplx"}],
            "DB요청": req if req is not None else ["선발 최근 등판"]}


def _patch(monkeypatch, text, payload=None):
    import app.engine.matchup as MU
    import app.engine.team_form as TF

    async def _cj(prompt, *, model, max_tokens, role, mock=False):
        _cj.prompt = prompt
        return text

    monkeypatch.setattr(TF, "complete_json", _cj)
    for fn in D.SOURCES.values():
        monkeypatch.setattr(MU, fn, lambda jg, _p=payload: _p if _p is not None
                            else {"home": {"선발등판": [{"innings": 5.0}]}})
    return _cj


# ═══════════════ ① 요청한 것만, 한 줄씩

def test_요청한_것만_붙인다(monkeypatch):
    import app.engine.matchup as MU

    called = []
    for name, fn in D.SOURCES.items():
        monkeypatch.setattr(MU, fn, lambda jg, _n=name: called.append(_n) or {"a": 1})
    got = D.summarize(_jg(), ["선발 최근 등판"])
    assert called == ["starters_recent_payload"] or called == ["선발 최근 등판"]
    assert [n for n, _ in got["붙임"]] == ["선발 최근 등판"]


def test_이름이_2단계_목록과_같다():
    """🔴 두 곳이 다른 이름을 쓰면 요청이 영영 안 붙는다."""
    from app.engine.prompts import TRIAGE

    for name in D.SOURCES:
        assert name in TRIAGE, name


def test_모르는_요청은_조용히_버리지_않는다():
    got = D.summarize(_jg(), ["점성술 궁합"])
    assert got["붙임"] == []
    assert got["모르는요청"] == ["점성술 궁합"]


def test_같은_것을_두_번_붙이지_않는다(monkeypatch):
    _patch(monkeypatch, "{}")
    got = D.summarize(_jg(), ["선발 최근 등판", "선발 최근 등판 기록"])
    assert len(got["붙임"]) == 1


def test_한_줄을_자른다(monkeypatch):
    """🔴 길면 그 자체로 판정을 끌고 간다. 전량 주입(21,000자)은 하지 않는다."""
    _patch(monkeypatch, "{}", payload={"x": "가" * 5000})
    got = D.summarize(_jg(), ["선발 최근 등판"])
    assert len(got["붙임"][0][1]) <= D.ROW_MAX + 1
    assert D.ROW_MAX <= 400


def test_조립이_터져도_나머지가_산다(monkeypatch):
    import app.engine.matchup as MU

    def boom(jg):
        raise RuntimeError("터졌다")

    monkeypatch.setattr(MU, "starters_recent_payload", boom)
    monkeypatch.setattr(MU, "lineups_payload", lambda jg: {"a": 1})
    got = D.summarize(_jg(), ["선발 최근 등판", "오늘 타순"])
    assert [n for n, _ in got["붙임"]] == ["오늘 타순"]


def test_숫자를_여기서_계산하지_않는다():
    """원본은 `matchup.*_payload` 다."""
    src = open("app/engine/dbref.py", encoding="utf-8").read()
    assert "payload" in src
    for banned in ("sum(", "round(", "/ len(", "mean"):
        assert banned not in src, banned


# ═══════════════ ② 승자를 뒤집지 않는다 — 이 단계의 본업

@pytest.mark.asyncio
async def test_모순이어도_승자를_바꾸지_않는다(monkeypatch):
    """🔴 ORD-1 에서 DB 가 승자를 뒤집었다. 이번엔 막는 것이 본업이다."""
    _patch(monkeypatch, '{"판정": "모순", "사유": "선발 등판이 반대를 가리킨다"}')
    v = {"승자": "Doosan Bears", "확신": "중"}
    out = await D.recheck(_jg(), _tri(), v)
    assert out["판정"] == "모순"
    assert v["승자"] == "Doosan Bears", "승자는 손대지 않는다"
    assert "승자" not in out


@pytest.mark.asyncio
async def test_모순이면_확신을_한_단계_내린다(monkeypatch):
    _patch(monkeypatch, '{"판정": "모순", "사유": "어긋난다"}')
    out = await D.recheck(_jg(), _tri(), {"승자": "두산", "확신": "상"})
    assert out["확신"] == "중"


def test_하에서는_더_내리지_않는다():
    """🔴 3단계가 이미 4/4 `하` 였다. 또 내리면 바닥에 깔려 신호가 죽는다."""
    assert D.lower("상") == "중"
    assert D.lower("중") == "하"
    assert D.lower("하") == "하"
    assert D.lower("모르는값") == "하"


@pytest.mark.asyncio
async def test_확인이면_확신이_그대로다(monkeypatch):
    _patch(monkeypatch, '{"판정": "확인", "사유": ""}')
    out = await D.recheck(_jg(), _tri(), {"승자": "두산", "확신": "중"})
    assert out["판정"] == "확인" and out["확신"] == "중"


@pytest.mark.asyncio
async def test_사유_없는_모순은_확인으로_본다(monkeypatch):
    """🔴 사유 없는 모순은 셀 수 없다."""
    _patch(monkeypatch, '{"판정": "모순", "사유": ""}')
    out = await D.recheck(_jg(), _tri(), {"승자": "두산", "확신": "상"})
    assert out["판정"] == "확인" and out["확신"] == "상"


# ═══════════════ ③ 있던 판정을 잃지 않는다

@pytest.mark.asyncio
async def test_재질의_실패면_3단계_확신_그대로(monkeypatch):
    import app.engine.matchup as MU
    import app.engine.team_form as TF

    async def boom(*a, **k):
        raise RuntimeError("터졌다")

    monkeypatch.setattr(TF, "complete_json", boom)
    monkeypatch.setattr(MU, "starters_recent_payload", lambda jg: {"a": 1})
    out = await D.recheck(_jg(), _tri(), {"승자": "두산", "확신": "중"})
    assert out["판정"] == "조회실패" and out["확신"] == "중"


@pytest.mark.asyncio
async def test_요청이_없으면_부르지_않는다(monkeypatch):
    called = {"n": 0}
    import app.engine.team_form as TF

    async def _cj(*a, **k):
        called["n"] += 1
        return "{}"

    monkeypatch.setattr(TF, "complete_json", _cj)
    out = await D.recheck(_jg(), _tri([]), {"승자": "두산", "확신": "상"})
    assert out["판정"] == "미조회" and called["n"] == 0
    assert out["확신"] == "상"


# ═══════════════ ④ 근거로 샐 자리가 없다

def test_출력에_근거_칸이_없다():
    """🔴 3·4단계 출력에 근거 칸 자체가 없다 — "근거 중 DB 인용 0줄"은
    구조로 이미 참이다. 계약으로 잠근다."""
    from app.engine.prompts import DB_CHECK

    out = DB_CHECK[DB_CHECK.index("[출력]"):]
    assert '"판정"' in out and '"사유"' in out
    for gone in ("근거", "변수", "p_home", "승자", "전개"):
        assert gone not in out, gone


def test_근거가_될_수_없다고_못박는다():
    from app.engine.prompts import DB_CHECK

    assert "근거가 될 수 없다" in DB_CHECK
    assert "승자를 뒤집지 마라" in DB_CHECK
    assert "새 근거를 만들지 마라" in DB_CHECK


def test_모순을_아껴_쓰라고_한다():
    from app.engine.prompts import DB_CHECK

    assert "`모순` 은 아껴 써라" in DB_CHECK
    assert "모순에는 사유를 한 줄 붙여라" in DB_CHECK
