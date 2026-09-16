"""PA-15 계약 — 위성 검색 예산 (지시문 §3).

> 상한 슬레이트 30%(최소 2, 최대 8), **우선순위 |gap| 큰 순**.

🔴 PA-13 이 "게이트 대상이면 추출"을 열었는데 **몇 건까지인지는 안 걸었다.**
   게이트 대상이 많은 날이면 무료 한도(groq 분당 8,000 토큰)가 그대로 터진다.
🔴 `gate.select` 가 §3 을 글자 그대로 구현해 놓고 **호출 0건**이었다.
"""
import pathlib

from app.collectors import satellite as SAT
from app.engine import gate as G


def _rows(n, label=G.OVER, gap=lambda i: -(20 - i)):
    return [{"id": i, "sport": "mlb", "league": "MLB",
             "home": f"H{i}", "away": f"A{i}", "starts_at": None,
             "gate_label": label, "gate_gap_pp": gap(i)} for i in range(n)]


def test_상한_30퍼센트():
    assert len(SAT.select_search_targets(_rows(12))) == 4      # round(12*0.30)


def test_최대_8을_안_넘는다():
    """🔴 반대 위험 — 상한이 없으면 무료 한도가 터진다."""
    assert len(SAT.select_search_targets(_rows(40))) == G.BUDGET_MAX == 8


def test_최소_2():
    assert len(SAT.select_search_targets(_rows(3))) == 2


def test_대상이_1건이면_1건이다():
    """"최소 2"는 **대상 안에서** 최소다 — 없는 것을 만들어 채우지 않는다."""
    rows = _rows(5)
    for r in rows[1:]:
        r["gate_label"] = G.AGREE
    assert len(SAT.select_search_targets(rows)) == 1


def test_gap_큰_순이다():
    got = SAT.select_search_targets(_rows(12))
    assert {r["id"] for r in got} == {0, 1, 2, 3}      # |gap| 20,19,18,17


def test_게이트_대상이_아니면_안_뽑힌다():
    """§3: 동의는 층1만 · 보드 고정은 찾을 것이 없다."""
    for label in (G.AGREE, G.BOARD, None):
        assert SAT.select_search_targets(_rows(10, label=label)) == []


def test_gap이_없으면_안_뽑힌다():
    """|gap| 로 줄을 세우는데 값이 없으면 순위를 못 매긴다."""
    assert SAT.select_search_targets(_rows(10, gap=lambda i: None)) == []


def test_예산_숫자를_손으로_안_적었다():
    """🔴 사본 금지 — 30%·2·8 은 `gate` 가 원본이다."""
    src = pathlib.Path("app/collectors/satellite.py").read_text(encoding="utf-8")
    fn = src[src.index("def select_search_targets"):].split("\nasync def ")[0]
    for lit in ("0.30", "0.3,", "= 8", "= 2"):
        assert lit not in fn, f"예산 값을 손으로 적었다: {lit}"
    assert "_G.select(" in fn


def test_예산_밖이면_라벨을_안_싣는다():
    """예산 밖 경기는 빅매치일 때만 추출된다(PA-13 경로로 되돌아간다)."""
    src = pathlib.Path("app/collectors/satellite.py").read_text(encoding="utf-8")
    assert 'if r["id"] in selected else None' in src


def test_수집_자체는_막지_않는다():
    """⚠️ §3 상한은 **검색·추출** 예산이다 — 층1 수집은 전 경기가 받는다."""
    src = pathlib.Path("app/collectors/satellite.py").read_text(encoding="utf-8")
    body = src.split("selected = {r[\"id\"]")[1]
    loop = body.split("for r in rows:")[1][:500]
    assert "in selected" not in loop.split("jg =")[0], \
        "예산 밖 경기의 수집을 건너뛴다 — §3 은 검색 예산만 막는다"


def test_칸이_스키마에_있다():
    assert "gate_gap_pp" in pathlib.Path("db/schema.sql").read_text(encoding="utf-8")


def test_record_prior가_gap을_쓴다():
    src = pathlib.Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    assert "gate_gap_pp = $7" in src
