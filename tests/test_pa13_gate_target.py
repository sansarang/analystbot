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
async def test_대상이_아니어도_추출한다(probe, label):
    """🔴 [EXT-2 / STEP 1-g 2026-09-20] **PA-13 의 이 조건은 폐기됐다.**

    종전 계약: "대상이 아니면 추출하지 않는다"(§3 — 동의는 층1만).
    뒤집은 이유(사용자 결정 `two_gates_0920`):
      위성이 보는 게이트는 **구경로**(`pick_ledger.gate_of`, tier+form)이고
      흐름은 다른 사전값(team_elo)을 쓴다. 같은 경기에 게이트가 둘이라
      흐름의 가설이 수집에 닿지 못했다.
      실측 2026-09-20: KBO 5경기가 기사 6~14건을 모으고도 `out` 이 찬 것은
      한 경기뿐. 두산@KT 는 기사 12건을 쥐고 여섯 변수 전건 미상이었다.
        [scout] Doosan Bears@KT Wiz — 게이트 동의 · 빅매치 아님 · LLM 추출 생략

    ⚠️ **반대 위험(무료 한도)은 사라지지 않았다** — 조건을 없앤 대신
       경기당 기사 상한(depth)과 **일일 LLM 상한**으로 묶는다.
       그 둘은 `test_ext2_extract_all_games.py` 가 잰다.
    """
    assert await probe(label, False) is True


def test_게이트_라벨로_추출을_가르지_않는다():
    """🔴 [EXT-2] 종전 `test_라벨을_손으로_적지_않았다` 를 대체한다.

    그 테스트는 `gate_target = ...` 블록이 `gate` 상수를 쓰는지 봤다.
    이제 그 블록 자체가 없어야 한다.
    """
    src = pathlib.Path("app/collectors/satellite.py").read_text(encoding="utf-8")
    body = "\n".join(ln for ln in src.splitlines()
                     if ln.strip() and not ln.strip().startswith("#"))
    assert "gate_target" not in body, "추출이 아직 게이트 라벨로 갈린다"


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
