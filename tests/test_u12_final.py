"""U12 — 최종 판정·서술·발송. analyze 를 **배선한다**.

🔴 `analyze` 는 두 달 전에 만들어졌는데 **호출부가 0건**이었다(실측: app/ 전체
   grep 결과 테스트 하나뿐). 그래서 결정축·시장 판단·구조 후보가 전부 NULL 이었다.
🔴 그리고 favored 가 v3 경로에서 안 찼다(U0-c) — ACL 4경기 전부 NULL.
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib

import pytest

from app.engine import analyze as AN
from app.engine import cases as CS
from app.engine import dispatch_rule as D
from app.engine import gate as G


# ── 배선

def test_analyze가_배선됐다():
    assert hasattr(AN, "run") and asyncio.iscoroutinefunction(AN.run)
    hits = [p for p in pathlib.Path("app").rglob("*.py")
            if "def run(" in p.read_text(encoding="utf-8")
            and p.name == "analyze.py"]
    assert hits


@pytest.mark.asyncio
@pytest.mark.parametrize("label", [G.AGREE, G.BOARD, None, "이상한값"])
async def test_게이트_대상만_부른다(label):
    """🔴 반대 위험 — 전 경기에 돌리면 무료 한도가 즉시 터진다
    (CHN-1 실측: groq 8,000 TPM · 판정 1콜이 그 한도를 넘는다)."""
    got = await AN.run({"game_id": 1}, {}, gate_label=label)
    assert got["skipped"], label
    assert got["out"] is None


def test_발송을_켜지_않는다():
    """🔴 반대 위험 — 이 U 는 원장에만 남긴다. 경로 전환은 U14 다."""
    src = inspect.getsource(AN.run)
    for bad in ("send", "dispatch", "telegram", "bot."):
        assert bad not in src.lower(), bad


def test_main_axis는_코드값이_이긴다():
    """🔴 LLM 이 결정축을 바꾸면 P0-1 에서 고친 구조가 다시 깨진다."""
    src = inspect.getsource(AN.run)
    assert "axis_disagree" in src
    assert 'led["main_axis"] = code_axes[0]' in src


# ── L2 · 금지어

def test_L2는_승자와_확신_글자_일치():
    ok, why = AN.l2({"승자": "Como", "확신": "하"},
                    code_winner="Como", code_level="하")
    assert ok is True and why == ""
    bad, why2 = AN.l2({"승자": "Parma", "확신": "상"},
                      code_winner="Como", code_level="하")
    assert bad is False and "Parma" in why2


def test_L2는_L1과_다른_것을_잡는다():
    """L1 은 숫자·이름이 자료에 있는지, L2 는 코드 값과 같은지 본다."""
    assert inspect.getsource(AN.l1) != inspect.getsource(AN.l2)
    doc = inspect.getdoc(AN.l2) or ""
    assert "코드" in doc


def test_코드값이_없으면_통과시킨다():
    """⚠️ 비교할 것이 없으면 반려하지 않는다 — 없는 근거로 막지 않는다."""
    assert AN.l2({"승자": "X"}, code_winner=None, code_level=None)[0] is True


@pytest.mark.parametrize("word", AN.BANNED)
def test_금지어가_걸린다(word):
    assert AN.banned_words(f"이 경기는 {word} 하다") == [word]


def test_정상_문장은_안_걸린다():
    """🔴 반대 위험 — 정상 문장을 반려하면 카드가 0장이 된다."""
    for s in ("홈이 우세하다", "원정 핵심이 빠졌다", "시장이 홈을 높게 본다",
              "라인업이 확정됐다"):
        assert AN.banned_words(s) == [], s


# ── 조건 B

def test_조건B_다섯_항목():
    ok = D.condition_b(lineup_status="confirmed", diff_adverse=False,
                       flow_label="news", edge_pp=7.0, grade="중")
    assert ok["ok"] is True and ok["missing"] == []
    assert set(ok["checks"]) == {"official", "불리 diff 없음",
                                 "흐름 contra 아님", "edge 유지", "등급 중 이상"}


@pytest.mark.parametrize("kw,missing", [
    ({"lineup_status": "predicted"}, "official"),
    ({"diff_adverse": True}, "불리 diff 없음"),
    ({"flow_label": "contra"}, "흐름 contra 아님"),
    ({"edge_pp": 3.0}, "edge 유지"),
    ({"edge_pp": None}, "edge 유지"),
    ({"grade": "하"}, "등급 중 이상"),
])
def test_하나라도_빠지면_불가(kw, missing):
    base = dict(lineup_status="confirmed", diff_adverse=False,
                flow_label="news", edge_pp=7.0, grade="중")
    base.update(kw)
    got = D.condition_b(**base)
    assert got["ok"] is False and missing in got["missing"]


def test_edge_문턱은_structure가_원본이다():
    src = inspect.getsource(D.condition_b)
    assert "EDGE_MIN_PP" in src and "6" not in src.replace("U12", "")


# ── 취소

def test_contra면_취소다():
    got = D.cancel_notice(flow_label="contra", diff_adverse=False, was_sent=True)
    assert got["cancel"] is True and got["notify"] is True


def test_안_나갔으면_통지하지_않는다():
    """🔴 안 나갔으면 그냥 안 내면 된다 — 통지가 오히려 소음이다."""
    got = D.cancel_notice(flow_label="contra", diff_adverse=False, was_sent=False)
    assert got["cancel"] is True and got["notify"] is False


def test_사유가_없으면_취소도_없다():
    got = D.cancel_notice(flow_label="news", diff_adverse=False, was_sent=True)
    assert got["cancel"] is False and got["notify"] is False


# ── 사례집

def test_사례집_유사도는_네_축():
    assert set(CS.WEIGHTS) == {"league_group", "gap_bucket",
                               "confirmed", "rest_bucket"}
    assert sum(CS.WEIGHTS.values()) == pytest.approx(1.0)


def test_퍼지_문자열을_안_쓴다():
    """🔴 AC밀란 오매칭의 원인이었다."""
    src = inspect.getsource(CS)
    for bad in ("difflib", "SequenceMatcher", "fuzz", "levenshtein"):
        assert bad not in src.lower(), bad


@pytest.mark.parametrize("gap,want", [(3.9, "0-4"), (4.0, "4-8"), (9.0, "8-15"),
                                      (20.0, "15+"), (None, None)])
def test_gap_버킷(gap, want):
    assert CS.gap_bucket(gap) == want


@pytest.mark.parametrize("days,want", [(2, "짧음"), (3, "짧음"), (4, "보통"),
                                       (6, "보통"), (7, "충분"), (None, None)])
def test_휴식_버킷(days, want):
    assert CS.rest_bucket(days) == want


def test_사례집이_비면_빈_목록():
    """⚠️ 값은 사용자가 채운다. 없는 것을 만들지 않는다."""
    assert CS.similar(league_group="유럽5대", gap_pp=9.0) == []


def test_사례집_파일이_있다():
    assert pathlib.Path("config/fable_cases.yaml").exists()
    import yaml
    doc = yaml.safe_load(pathlib.Path("config/fable_cases.yaml")
                         .read_text(encoding="utf-8"))
    assert "cases" in doc


def test_점수가_축별로_더해진다():
    case = {"league_group": "유럽5대", "gap_bucket": "8-15",
            "confirmed": ["핵심결장"], "rest_bucket": "짧음"}
    full = CS.score(case, league_group="유럽5대", gap_pp=9.0,
                    confirmed=["핵심결장"], rest_days=2)
    assert full == pytest.approx(1.0)
    none = CS.score(case, league_group="아시아", gap_pp=1.0,
                    confirmed=["주중대항전"], rest_days=9)
    assert none == 0.0


# ── U0-c

def test_favored가_predicted_side와_같다():
    """🔴 실측: ACL 4경기 favored 전부 NULL. v3 는 `우세` 키를 안 쓴다."""
    from app.engine import pick_ledger as PL

    jg = {"game_id": 1, "sport": "soccer", "home": "H", "away": "A",
          "matchup": {"승자": "H", "확신": "하"}, "winner": "H"}
    row = PL._row_from_game(jg, {}, {})
    assert row["favored"] == row["predicted_side"] == "home"


def test_favored를_새로_계산하지_않는다():
    """⚠️ 두 칸이 갈리면 채점이 어느 쪽인지 모른다."""
    from app.engine import pick_ledger as PL

    src = inspect.getsource(PL._row_from_game)
    i = src.index('"favored"')
    assert "_side_of" in src[i:i + 200]


# ═══════════════ [U12 배선] record_confirm_and_analysis
#
# 🔴 `analyze` 와 `confirm` 은 U7·U12 에서 만들어 놓고 **부르는 곳이 0건**이었다.
#    이 계약이 그 자리를 고정한다 — 진입점이 사라지면 여기서 빨개진다.

class _StubConn:
    def __init__(self, gate_ok=True):
        self.saved = []

    async def fetchrow(self, sql, *a):
        if "FROM games" in sql:
            return {"id": 1, "sport": "soccer", "league": "serie_a",
                    "home": "Como 1907", "away": "Parma Calcio 1913",
                    "starts_at": None}
        return {"hypothesis": {"direction": "home",
                               "need": [{"field": "out", "side": "away",
                                         "why": "x"}],
                               "sufficient_count": 2, "reason": ""},
                "p_code": 0.61, "adj_pp": {}, "p_market": 0.55, "p_prior": 0.58,
                "predicted_side": "home", "confidence": "중"}

    async def fetch(self, sql, *a):
        return []

    async def execute(self, sql, *a):
        self.saved.append((sql, a))


def _fake_analyze(calls):
    async def _run(jg, blk, **kw):
        calls.append((jg, blk, kw))
        from app.engine import analyze as AN
        return {"ledger": AN.to_ledger({"결정축": "결장", "시장_판단": "과대",
                                        "구조_후보": []},
                                       model="m", gate_label=kw.get("gate_label")),
                "l1": True, "l2": True, "banned": [], "skipped": None}
    return _run


@pytest.mark.asyncio
async def test_게이트_대상이면_analyze가_불린다(monkeypatch):
    from app.engine import analyze as AN
    from app.engine import gate as G
    from app.engine import pick_ledger as PL

    calls = []
    monkeypatch.setattr(AN, "run", _fake_analyze(calls))
    conn = _StubConn()
    out = await PL.record_confirm_and_analysis(
        conn, game_id=1, gate={"label": G.OVER, "gap_pp": -17.9})
    assert len(calls) == 1, "게이트 대상인데 analyze.run 이 안 불렸다"
    assert out is not None
    # 확인 판정과 분석이 **둘 다** 저장돼야 한다
    sqls = " ".join(s for s, _ in conn.saved)
    assert "confirmed" in sqls and "main_axis" in sqls


@pytest.mark.asyncio
async def test_게이트_대상이_아니면_부르지_않는다(monkeypatch):
    from app.engine import analyze as AN
    from app.engine import pick_ledger as PL

    calls = []
    monkeypatch.setattr(AN, "run", _fake_analyze(calls))
    conn = _StubConn()
    out = await PL.record_confirm_and_analysis(
        conn, game_id=1, gate={"label": "정합", "gap_pp": 1.0})
    assert out is None and calls == [] and conn.saved == []


@pytest.mark.asyncio
async def test_분석이_터져도_예외가_밖으로_안_나간다(monkeypatch):
    """⚠️ 저장 전용이다 — 측정 장치가 판정을 죽이면 안 된다."""
    from app.engine import analyze as AN
    from app.engine import gate as G
    from app.engine import pick_ledger as PL

    async def _boom(*a, **k):
        raise RuntimeError("한도")

    monkeypatch.setattr(AN, "run", _boom)
    out = await PL.record_confirm_and_analysis(
        _StubConn(), game_id=1, gate={"label": G.DOUBT, "gap_pp": 9.0})
    assert out is not None and "analyze" not in out


def test_record_analysis_는_원장_저장_본체_그대로다():
    """🔴 같은 이름을 뒤에 정의해 원장 저장이 통째로 죽은 적이 있다."""
    import inspect

    from app.engine import pick_ledger as PL

    assert list(inspect.signature(PL.record_analysis).parameters)[:2] == \
        ["pool", "analysis"]
