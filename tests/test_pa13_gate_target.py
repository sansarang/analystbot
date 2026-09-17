"""PA-13 계약 — 위성이 게이트 결과로 대상을 고른다 (지시문 §3).

> 검색 대상 = `시장 과대`·`가치 의심` **+** 태그 `빅매치`.

🔴 종전 코드는 `is_big_match` **하나만** 봤다. 실측 2026-09-16: NPB 2경기가
   기사 7건씩 모으고 추출 0건.
🔴 게이트 판단 자체를 잰다 — LLM 결과를 보면 "게이트가 막았다"와 "호출이
   실패했다"를 구분할 수 없다.
"""
import pathlib

import pytest

from app.collectors import satellite as SAT
from app.engine import gate as G

ARTS = [{"team": "A", "body": "x" * 600, "url": "http://a.example/1",
         "published": "2026-09-16"}]


@pytest.fixture
def probe(monkeypatch):
    """LLM 을 스텁으로 갈고 **불렸는가**만 본다."""
    import app.engine.team_form as TF
    from app.engine import bigmatch as BM

    async def _run(label, big):
        called = []

        async def _stub(*a, **k):
            called.append(1)
            return '{"home": {"out": []}, "away": {"out": []}}'

        monkeypatch.setattr(TF, "_complete_free", _stub)
        monkeypatch.setattr(BM, "is_big_match",
                            lambda **kw: type("T", (), {"big": big,
                                                        "reason": "테스트"})())
        try:
            await SAT.extract_game_facts(
                ARTS, home="Orix Buffaloes", away="Fukuoka SoftBank Hawks",
                league="npb", redis=None,
                jg={"game_id": 1, "gate_label": label})
        except Exception:
            pass
        return bool(called)

    return _run


@pytest.mark.asyncio
@pytest.mark.parametrize("label", [G.OVER, G.DOUBT])
async def test_게이트_대상이면_빅매치가_아니어도_추출한다(probe, label):
    assert await probe(label, False) is True


@pytest.mark.asyncio
async def test_빅매치는_종전대로_추출한다(probe):
    """🔴 반대 위험 — 빅매치 경로를 없애면 사전값 없는 경기가 통째로 빠진다."""
    assert await probe(None, True) is True


@pytest.mark.asyncio
@pytest.mark.parametrize("label", [G.BOARD, G.AGREE, None, "알 수 없음"])
async def test_대상이_아니면_추출하지_않는다(probe, label):
    """🔴 반대 위험 — 전건 추출은 무료 한도를 즉시 태운다.

    §3: 동의 경기는 층1만 · 보드 고정은 찾을 것이 없다.
    """
    assert await probe(label, False) is False


def test_라벨을_손으로_적지_않았다():
    """🔴 사본 금지 — `gate` 상수가 원본이다."""
    src = pathlib.Path("app/collectors/satellite.py").read_text(encoding="utf-8")
    blk = src.split("gate_target =")[1][:200]
    assert "_G.OVER" in blk and "_G.DOUBT" in blk
    assert '"시장 과대"' not in blk and '"가치 의심"' not in blk


def test_gate_reason_텍스트를_파싱하지_않는다():
    """🔴 그 텍스트는 이미 어긋나 있다 — '보드고정' vs gate.BOARD '보드 고정'."""
    src = pathlib.Path("app/collectors/satellite.py").read_text(encoding="utf-8")
    assert "l.gate_reason" not in src
    assert 'split(" · ")' not in src


def test_위성은_확률과_승자를_읽지_않는다():
    """🔴 레저 경계 — 읽는 것은 **선별 신호**이지 판정이 아니다."""
    src = pathlib.Path("app/collectors/satellite.py").read_text(encoding="utf-8")
    sql = src.split("_DUE_SQL")[1].split('"""')[2] if '_DUE_SQL' in src else ""
    for banned in ("p_code", "p_claude", "predicted_side", "confidence",
                   "p_prior", "p_market"):
        assert banned not in sql, f"위성 SQL 이 {banned} 를 읽는다"


def test_라벨_칸이_스키마에_있다():
    src = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    assert "gate_label" in src


def test_record_prior가_라벨을_칸으로_쓴다():
    src = pathlib.Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    assert "gate_label = $6" in src
    # 보드 고정 분기도 같은 칸을 쓴다(PA-6 경로)
    # ⚠️ 인자가 늘 때마다 꼬리가 바뀐다(PA-15 gap · PA-24 p_base).
    #    **칸을 쓰는지**만 본다 — 꼬리 모양은 계약이 아니다.
    assert "G.BOARD," in src or "G.BOARD)" in src
