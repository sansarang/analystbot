"""ORD-15 (4단계) — DB 를 통째로 주고 AI 가 자율로 판단한다.

사용자 지시 2026-09-12: "경기 관련 DB를 통째로 주고, AI가 그 안에서 필요한 걸
찾아 쓰게 한다...db 관련도 ai 판단에 의해 결정나게 해라..자율적으로"

🔴 종전(ORD-13)은 AI 가 `DB요청` 이름을 적고 우리가 키워드로 맞춰 골라 줬다.
   **그 왕복이 샜다** — 실측 2026-09-12: 4경기 중 2경기가 이름을 풀어 써서
   매핑에 실패했다. 우리가 고르는 구조 자체가 새는 지점이었다.
🔴 그리고 코드가 결과를 강제했다(승자 불변·확신 강등). 이제 막지 않는다.
   대신 **전부 센다** — 이 저장소가 `check_flow` 에 적어 둔 "프롬프트만으로는
   부족하다"의 대가를 알고 하는 선택이다. 조용한 변경만 없앤다.
"""

import pytest

from app.engine import dbref as D


def _jg():
    return {"game_id": 1737, "sport": "kbo", "league": "KBO",
            "home": "Doosan Bears", "away": "NC Dinos"}


def _tri():
    return {"갈림길": [{"질문": "구창모가 5이닝을 넘기는가"}],
            "채택": [{"답": "x", "소스": "pplx"}]}


def _payloads(monkeypatch, have=("lineups_payload",), big=False):
    import app.engine.matchup as MU

    for _, fn in D.ITEMS:
        val = ({"x": "가" * 5000} if big else {"a": 1}) if fn in have else {}
        monkeypatch.setattr(MU, fn, lambda jg, _v=val: _v)


def _reply(monkeypatch, text):
    import app.engine.team_form as TF

    async def _cj(prompt, *, model, max_tokens, role, mock=False):
        _cj.prompt = prompt
        return text

    monkeypatch.setattr(TF, "complete_json", _cj)
    return _cj


# ═══════════════ ① 통째로 준다 — 요청 왕복이 없다

def test_요청_매핑_왕복이_사라졌다():
    """🔴 실측 2026-09-12: 4경기 중 2경기가 이름을 풀어 써서 매핑 실패."""
    assert not hasattr(D, "_match")
    assert not hasattr(D, "_HINTS")
    assert not hasattr(D, "SOURCES")


def test_항목_이름이_2단계_목록과_같다():
    from app.engine.prompts import TRIAGE

    for name, _ in D.ITEMS[:5]:
        assert name in TRIAGE, name


def test_있는_것과_없는_것을_모두_돌려준다(monkeypatch):
    _payloads(monkeypatch, have=("lineups_payload", "elo_payload"))
    b = D.bundle(_jg())
    assert b["있음"] == ["오늘 타순", "실력 레이팅"]
    assert len(b["없음"]) == len(D.ITEMS) - 2
    assert len(b["줄"]) == len(D.ITEMS)


def test_없는_것을_없음이라_적는다(monkeypatch):
    """🔴 조용히 빠뜨리면 AI 는 원래 없는 건지 아직 안 온 건지 모른다.
    실측 2026-09-12: 오늘 KBO/NPB 는 research 가 안 차서 9종 중 3종만 있었다."""
    _payloads(monkeypatch, have=("lineups_payload",))
    t = D.fmt(D.bundle(_jg())["줄"])
    assert "· 오늘 타순 — {" in t
    assert "· 실력 레이팅 — 없음" in t


def test_한_항목이_터져도_나머지가_산다(monkeypatch):
    import app.engine.matchup as MU

    _payloads(monkeypatch, have=("lineups_payload",))

    def boom(jg):
        raise RuntimeError("터졌다")

    monkeypatch.setattr(MU, "elo_payload", boom)
    assert D.bundle(_jg())["있음"] == ["오늘 타순"]


def test_긴_항목은_자른다(monkeypatch):
    _payloads(monkeypatch, have=("lineups_payload",), big=True)
    _, text = D.bundle(_jg())["줄"][1]
    assert len(text) <= D.ITEM_MAX + 1


def test_숫자를_여기서_계산하지_않는다():
    """원본은 `matchup.*_payload` 다."""
    src = open("app/engine/dbref.py", encoding="utf-8").read()
    for banned in ("sum(", "round(", "/ len(", "mean"):
        assert banned not in src, banned


# ═══════════════ ② 자율 — 막지 않는다

@pytest.mark.asyncio
async def test_AI_가_승자를_바꿀_수_있다(monkeypatch):
    """🔴 종전에는 코드가 막았다. 이제 AI 판단이다."""
    _payloads(monkeypatch)
    _reply(monkeypatch, '{"본것": ["오늘 타순"], "승자": "NC Dinos", '
                        '"확신": "중", "사유": "타순에서 주전 4명이 빠졌다"}')
    out = await D.recheck(_jg(), _tri(), {"승자": "Doosan Bears", "확신": "하"})
    assert out["승자"] == "NC Dinos"
    assert out["승자변경"] is True and out["판정"] == "정정"
    assert out["사유"] == "타순에서 주전 4명이 빠졌다"


@pytest.mark.asyncio
async def test_AI_가_확신을_올릴_수도_있다(monkeypatch):
    """🔴 종전에는 내리기만 했다(`lower`). 이제 양방향이다."""
    _payloads(monkeypatch)
    _reply(monkeypatch, '{"본것": ["오늘 타순"], "승자": "Doosan Bears", '
                        '"확신": "상", "사유": ""}')
    out = await D.recheck(_jg(), _tri(), {"승자": "Doosan Bears", "확신": "하"})
    assert out["확신"] == "상" and out["승자변경"] is False


@pytest.mark.asyncio
async def test_그대로_두면_그대로다(monkeypatch):
    _payloads(monkeypatch)
    _reply(monkeypatch, '{"본것": [], "승자": "Doosan Bears", "확신": "하",'
                        ' "사유": ""}')
    out = await D.recheck(_jg(), _tri(), {"승자": "Doosan Bears", "확신": "하"})
    assert out["판정"] == "확인" and out["승자변경"] is False


# ═══════════════ ③ 조용한 변경만 없앤다

@pytest.mark.asyncio
async def test_사유_없는_승자_변경은_되돌린다(monkeypatch, caplog):
    """🔴 사유 없는 변경은 자율이 아니라 실수다."""
    _payloads(monkeypatch)
    _reply(monkeypatch, '{"본것": [], "승자": "NC Dinos", "확신": "중",'
                        ' "사유": ""}')
    with caplog.at_level("WARNING"):
        out = await D.recheck(_jg(), _tri(), {"승자": "Doosan Bears", "확신": "하"})
    assert out["승자"] == "Doosan Bears" and out["승자변경"] is False
    assert "사유 없이 승자를 바꾸려" in caplog.text


@pytest.mark.asyncio
async def test_승자_변경은_경고로_남는다(monkeypatch, caplog):
    """🔴 막지는 않되 반드시 드러낸다."""
    _payloads(monkeypatch)
    _reply(monkeypatch, '{"본것": [], "승자": "NC Dinos", "확신": "중",'
                        ' "사유": "이유"}')
    with caplog.at_level("WARNING"):
        await D.recheck(_jg(), _tri(), {"승자": "Doosan Bears", "확신": "하"})
    assert "DB 참조로 승자 변경" in caplog.text


@pytest.mark.asyncio
async def test_본것은_우리가_실은_것만_인정한다(monkeypatch):
    """🔴 자기 보고다 — 상한이 아니라 하한으로 읽는다. 안 실은 것을 봤다고
    적으면 세지 않는다."""
    _payloads(monkeypatch, have=("lineups_payload",))
    _reply(monkeypatch, '{"본것": ["오늘 타순", "실력 레이팅", "점성술"],'
                        ' "승자": "Doosan Bears", "확신": "하", "사유": ""}')
    out = await D.recheck(_jg(), _tri(), {"승자": "Doosan Bears", "확신": "하"})
    assert out["본것"] == ["오늘 타순"]


@pytest.mark.asyncio
async def test_기록이_통째로_비면_부르지_않는다(monkeypatch):
    _payloads(monkeypatch, have=())
    called = {"n": 0}
    import app.engine.team_form as TF

    async def _cj(*a, **k):
        called["n"] += 1
        return "{}"

    monkeypatch.setattr(TF, "complete_json", _cj)
    out = await D.recheck(_jg(), _tri(), {"승자": "두산", "확신": "중"})
    assert out["판정"] == "미조회" and called["n"] == 0
    assert out["확신"] == "중"


@pytest.mark.asyncio
async def test_호출_실패면_3단계_판정_그대로(monkeypatch):
    _payloads(monkeypatch)
    import app.engine.team_form as TF

    async def boom(*a, **k):
        raise RuntimeError("터졌다")

    monkeypatch.setattr(TF, "complete_json", boom)
    out = await D.recheck(_jg(), _tri(), {"승자": "두산", "확신": "중"})
    assert out["판정"] == "조회실패"
    assert out["승자"] == "두산" and out["확신"] == "중"


# ═══════════════ ④ 프롬프트 계약

def test_찾아_보라고_한다():
    from app.engine.prompts import DB_OPEN

    assert "필요한 것만 찾아 봐라" in DB_OPEN
    assert "전부 읽고 전부 쓰려 들지 마라" in DB_OPEN


def test_어떻게_쓸지는_네_판단이라고_한다():
    from app.engine.prompts import DB_OPEN

    assert "어떻게 쓸지는 네 판단이다" in DB_OPEN
    assert "우리는 막지 않는다" in DB_OPEN


def test_조사_결과가_먼저라고_알린다():
    """🔴 기록은 오늘 무엇이 달라졌는지를 모른다 — 부상·말소·연투는 조사에만."""
    from app.engine.prompts import DB_OPEN

    assert "조사 결과로 내린 것이 먼저다" in DB_OPEN
    assert "부상·말소·연투는 조사 결과에만 있다" in DB_OPEN


def test_사유와_본것을_요구한다():
    from app.engine.prompts import DB_OPEN

    assert "승자를 바꾸려면 사유를 써라" in DB_OPEN
    assert "본 것을 적어라" in DB_OPEN
    assert "안 본 것을 봤다고 적지" in DB_OPEN


def test_없음_항목을_가정하지_말라고_한다():
    from app.engine.prompts import DB_OPEN

    assert "`없음` 인 항목은 없는 것이다" in DB_OPEN
