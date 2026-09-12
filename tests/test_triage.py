"""ORD-11 (2단계) — AI 가 거른다.

사용자 지시 2026-09-12: "그후 ai에게 정보를 준다.ai가 거른다"

🔴 왜: 1단계는 질문 없이 긁어 **잡음을 줄이지 않는다**(설계가 그렇다).
   실측 2026-09-12 수집물 — 위성 12건에 어제 경기 결과·타팀(KIA·한화) 기사가
   섞였고, 퍼플렉시티는 티켓 예매·좌석 번호까지 물어 왔다.
   거르는 단계가 없으면 DSM-1 상태다 — 위성 76건 중 조사 인용 0건.
"""

import pytest

from app.engine import triage as T


def _jg():
    return {"game_id": 1737, "sport": "kbo", "league": "KBO",
            "home": "Doosan Bears", "away": "NC Dinos"}


def _rows(n=4):
    return [{"질문": "", "답": f"사실{i}", "소스": "pplx", "소스유형": "뉴스",
             "시점": "2026-09-11", "계정": "", "url": ""} for i in range(1, n + 1)]


async def _reply(payload):
    """`_complete_free` 를 대신해 정해진 JSON 을 돌려준다."""
    import json

    async def f(routes, prompt, max_tokens, role):
        return json.dumps(payload, ensure_ascii=False)

    return f


def _patch(monkeypatch, payload):
    import json

    import app.engine.team_form as TF
    from app.config import get_settings

    async def _cf(routes, prompt, max_tokens, role):
        return json.dumps(payload, ensure_ascii=False) if payload is not None else ""

    monkeypatch.setattr(TF, "_complete_free", _cf)
    import app.llm.judge_route as JR

    monkeypatch.setattr(JR, "chain", lambda role: [("gemini", "m")])
    s = get_settings()
    if s.mock_judge:                       # 테스트 환경은 목일 수 있다
        monkeypatch.setattr(type(s), "mock_judge", property(lambda self: False))


# ═══════════════ ① 번호로만 받는다

def test_수집물에_번호가_붙는다():
    t = T.number_rows([{"답": "a", "소스": "x", "계정": "@k", "시점": "2026-09-11"},
                       {"답": "b", "소스": "pplx"}])
    assert t.startswith("1. [x @k] [2026-09-11] a")
    assert "\n2. [pplx] b" in t


def test_긴_항목은_자른다():
    t = T.number_rows([{"답": "가" * 500, "소스": "pplx"}])
    assert "…" in t and len(t) < 400


@pytest.mark.asyncio
async def test_채택_기각을_원문으로_돌려준다(monkeypatch):
    """🔴 모델이 문장을 다시 쓰면 창작이다. 번호만 받고 원문은 우리가 꺼낸다."""
    _patch(monkeypatch, {"채택": [1, 3],
                         "기각": [{"번호": 2, "사유": "어제 결과"},
                                  {"번호": 4, "사유": "타팀 기사"}],
                         "갈림길": [], "변수": [], "없는것": [], "DB요청": []})
    out = await T.run(_jg(), "brief", _rows())
    assert [r["답"] for r in out["채택"]] == ["사실1", "사실3"]
    assert [d["행"]["답"] for d in out["기각"]] == ["사실2", "사실4"]
    assert out["기각"][0]["사유"] == "어제 결과"


# ═══════════════ ② 지어낸 번호·사유 없는 기각을 막는다

@pytest.mark.asyncio
async def test_범위_밖_번호는_버린다(monkeypatch):
    """🔴 지어낸 번호를 채택하면 없는 사실이 판정에 들어간다(DSM-1 근거번호 99)."""
    _patch(monkeypatch, {"채택": [1, 99, -1, 0], "기각": [],
                         "갈림길": [], "변수": [], "없는것": [], "DB요청": []})
    out = await T.run(_jg(), "b", _rows(2))
    assert out["계측"]["채택"] == 1


@pytest.mark.asyncio
async def test_사유_없는_기각은_기각이_아니다(monkeypatch):
    """🔴 사유가 없으면 셀 수 없고, 세지 못하면 "거름이 과한가"를 못 묻는다."""
    _patch(monkeypatch, {"채택": [1], "기각": [{"번호": 2, "사유": ""}],
                         "갈림길": [], "변수": [], "없는것": [], "DB요청": []})
    out = await T.run(_jg(), "b", _rows(2))
    assert out["기각"] == []
    assert [r["답"] for r in out["채택"]] == ["사실1", "사실2"]


@pytest.mark.asyncio
async def test_빠뜨린_것은_채택으로_남긴다(monkeypatch):
    """🔴 모델이 빠뜨린 것을 조용히 기각하면 그게 가장 나쁜 손실이다."""
    _patch(monkeypatch, {"채택": [1], "기각": [{"번호": 2, "사유": "무관"}],
                         "갈림길": [], "변수": [], "없는것": [], "DB요청": []})
    out = await T.run(_jg(), "b", _rows(4))
    assert [r["답"] for r in out["채택"]] == ["사실1", "사실3", "사실4"]
    assert out["계측"]["미분류"] == 2


@pytest.mark.asyncio
async def test_채택과_기각에_같은_번호가_오면_채택이_이긴다(monkeypatch):
    _patch(monkeypatch, {"채택": [1], "기각": [{"번호": 1, "사유": "x"}],
                         "갈림길": [], "변수": [], "없는것": [], "DB요청": []})
    out = await T.run(_jg(), "b", _rows(1))
    assert out["계측"] == {"수집": 1, "채택": 1, "기각": 0, "미분류": 0}


# ═══════════════ ③ 조용한 손실 금지

@pytest.mark.asyncio
async def test_전부_기각이면_소리를_낸다(monkeypatch, caplog):
    """🔴 채택 0 은 "재료 없음"이다. 조용히 넘기면 ③이 아는 척 판정한다."""
    _patch(monkeypatch, {"채택": [], "기각": [{"번호": 1, "사유": "무관"},
                                            {"번호": 2, "사유": "무관"}],
                         "갈림길": [], "변수": [], "없는것": [], "DB요청": []})
    with caplog.at_level("WARNING"):
        out = await T.run(_jg(), "b", _rows(2))
    assert out["채택"] == []
    assert "전부 기각" in caplog.text


@pytest.mark.asyncio
async def test_계측을_남긴다(monkeypatch):
    """🔴 채택/수집 비율이 이 설계의 유일한 품질 척도다 — 질문이 없어져
    "조사 답률"을 못 쓴다."""
    _patch(monkeypatch, {"채택": [1, 2], "기각": [{"번호": 3, "사유": "x"}],
                         "갈림길": [], "변수": [], "없는것": [], "DB요청": []})
    out = await T.run(_jg(), "b", _rows(4))
    assert out["계측"] == {"수집": 4, "채택": 2, "기각": 1, "미분류": 1}


@pytest.mark.asyncio
async def test_파싱_실패는_None(monkeypatch):
    """⚠️ 여기서 판정을 대신 내리지 않는다 — 호출부가 정한다."""
    _patch(monkeypatch, None)
    assert await T.run(_jg(), "b", _rows()) is None


@pytest.mark.asyncio
async def test_수집물이_없으면_부르지_않는다(monkeypatch):
    called = {"n": 0}
    import app.engine.team_form as TF

    async def _cf(*a, **k):
        called["n"] += 1
        return "{}"

    monkeypatch.setattr(TF, "_complete_free", _cf)
    assert await T.run(_jg(), "b", []) is None
    assert called["n"] == 0


# ═══════════════ ④ 프롬프트 계약

def test_의심스러우면_채택하라고_한다():
    """🔴 거름이 과하면 판정이 굶는다."""
    from app.engine.prompts import TRIAGE

    assert "의심스러우면 채택하라" in TRIAGE
    assert "거름이 과하면 판정이 굶는다" in TRIAGE


def test_채택한_것에_없는_사실로_갈림길을_만들지_말라고_한다():
    from app.engine.prompts import TRIAGE

    assert "채택한 것에 없는 사실로 갈림길을 만들지 마라" in TRIAGE


def test_번호만_쓰라고_한다():
    from app.engine.prompts import TRIAGE

    assert "번호만 쓴다" in TRIAGE
    assert "옮겨" in TRIAGE and "고쳐 쓰지 마라" in TRIAGE


def test_변수_채점_규칙을_재사용한다():
    """🔴 사본 금지 — 임계 규칙을 다시 적으면 채점 불가 변수가 샌다."""
    from app.engine.prompts import TRIAGE, VARIABLE_GRADEABLE

    assert VARIABLE_GRADEABLE in TRIAGE


def test_DB가_줄_수_있는_것을_알려준다():
    from app.engine.prompts import TRIAGE

    for item in ("최근 3경기 박스스코어", "오늘 타순", "선발 최근 등판",
                 "불펜 최근 폼과 가용성", "실력 레이팅"):
        assert item in TRIAGE, item
    assert "습관적으로 채우지 마라" in TRIAGE


def test_기각_사유를_강제한다():
    from app.engine.prompts import TRIAGE

    assert "기각에는 사유를 한 줄 붙여라" in TRIAGE


def test_새_라우팅을_만들지_않는다():
    """정찰이 쓰던 그 역할 그대로."""
    assert T.DEEPSEARCH_ROLE == "deepsearch"
