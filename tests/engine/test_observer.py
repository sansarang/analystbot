"""OBS-1 — 상시 관측 모드 (Part 4).

지금 봇은 "슬레이트 전체를 시각에 맞춰 한 번 판정하고 발송"한다. 페이블
방식은 반대다 — **모든 경기를 계속 보되 대부분은 침묵하고, 조건이 갖춰진
소수만 단계적으로 올려서, 라인업 확정 후에 최종 한 번 말한다.**

실측(오늘): 축구 20경기 관측 → 후보 6 → 라인업 확정 후 최종 2.

🔴 **상태 전이는 코드만 한다.** LLM 출력은 조건 A·B 의 **입력일 뿐**이다.
"""
import pytest

from app.engine import observer as O


# ── 상태

def test_상태가_여섯이다():
    assert O.STATES == ("관측", "후보", "추천대기", "추천", "취소", "종료")


def test_어떤_상태에서든_contra면_즉시_취소다():
    """🔴 지시문 7-1 — 이동 분류가 contra 면 그 자리에서 취소."""
    for st in ("관측", "후보", "추천대기", "추천"):
        assert O.next_state(st, move_class="contra") == "취소"


def test_취소와_종료는_되돌아가지_않는다():
    for st in ("취소", "종료"):
        assert O.next_state(st, move_class="contra") == st


# ── 조건 A (후보 → 추천대기)

def _a(**kw):
    base = {"gate": "시장 과대", "gap_pp": -9.0,
            "facts": {"out": ["A"], "last3": ["L 0-2"]},
            "market_view": "과대", "swap_agree": True,
            "pick_edge_pp": 7.0}
    base.update(kw)
    return base


def test_조건A는_넷을_전부_본다():
    ok, why = O.cond_a(_a())
    assert ok is True, why


@pytest.mark.parametrize("bad,word", [
    ({"gate": "동의"}, "게이트"),
    ({"gap_pp": -3.0}, "괴리"),
    ({"facts": {}}, "사실"),
    ({"market_view": "적정"}, "분석"),
    ({"swap_agree": False}, "스왑"),
    ({"pick_edge_pp": 3.0}, "우위"),
])
def test_조건A는_하나라도_빠지면_탈락이다(bad, word):
    ok, why = O.cond_a(_a(**bad))
    assert ok is False and word in why, (bad, why)


def test_이유_없는_괴리는_후보가_아니다():
    """지시문 7-2 A-2: 결장·일정·폼 사실이 **1개 이상** 있어야 한다."""
    assert O.cond_a(_a(facts={"out": [], "last3": [], "midweek": None}))[0] is False
    assert O.cond_a(_a(facts={"midweek": "UCL 원정"}))[0] is True


# ── 조건 B (추천대기 → 추천, 최종)

def _b(**kw):
    base = {"xi_status": "official", "diff_adverse": False,
            "move_class": "news", "axis_kept": True, "swap_agree": True,
            "edge_pp": 7.0, "confidence": "중"}
    base.update(kw)
    return base


def test_조건B는_여섯을_전부_본다():
    ok, why = O.cond_b(_b())
    assert ok is True, why


def test_공식_라인업이_없으면_추천하지_않는다():
    """🔴 지시문 7-2 B-1 — **잠정 발송 없음.**"""
    ok, why = O.cond_b(_b(xi_status="predicted"))
    assert ok is False and "라인업" in why


def test_픽에_불리한_변화가_있으면_취소다():
    ok, why = O.cond_b(_b(diff_adverse=True))
    assert ok is False and "불리" in why


def test_money_이동은_유지_contra는_취소다():
    assert O.cond_b(_b(move_class="money"))[0] is True
    assert O.cond_b(_b(move_class="none"))[0] is True
    ok, why = O.cond_b(_b(move_class="contra"))
    assert ok is False and "역이동" in why


def test_확신_하는_발송하지_않는다():
    assert O.cond_b(_b(confidence="하"))[0] is False
    assert O.cond_b(_b(confidence="중"))[0] is True
    assert O.cond_b(_b(confidence="상"))[0] is True


def test_라인이_움직였으면_새_라인으로_다시_본다():
    ok, why = O.cond_b(_b(edge_pp=4.0))
    assert ok is False and "우위" in why


# ── 발송 규칙 (7-4) — 침묵이 기본

@pytest.mark.parametrize("frm,to,send", [
    ("관측", "관측", None),
    ("후보", "관측", None),
    ("관측", "후보", None),
    ("후보", "추천대기", None),
    ("추천대기", "추천", "최종"),
    ("추천대기", "취소", "취소"),
    ("추천", "취소", "취소"),
    ("추천", "종료", None),
])
def test_발송은_최종과_취소뿐이다(frm, to, send):
    assert O.dispatch_for(frm, to) == send


def test_최종은_경기당_한_번이다():
    """🔴 재판정 카드·수정 카드는 없다."""
    assert O.dispatch_for("추천", "추천") is None


# ── 상시 루프 (7-3)

def test_주기가_지시문_그대로다():
    assert O.TICK_SEC == 60
    assert O.SNAP_SEC == 600
    assert O.RECHECK_SEC == 3600


def test_동시_실행_상한은_트리거와_같은_값을_쓴다():
    """🔴 사본 금지 — 상한을 두 곳에 적지 않는다."""
    from app.engine import triggers

    assert O.MAX_CONCURRENT is triggers.MAX_CONCURRENT


def test_검색과_LLM은_후보_이상에서만_돈다():
    """🔴 24시간 도는 것은 트리거와 배당 스냅이지 검색이 아니다 — 예산."""
    assert O.uses_search("관측") is False
    assert O.uses_search("후보") is True
    assert O.uses_search("추천대기") is True


# ── 원장

def test_원장에_세_칸이_있다():
    s = open("db/schema.sql", encoding="utf-8").read()
    for col in ("promoted_at", "finalized_at", "cancel_reason"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in s, col


def test_games에_상태_칸이_있다():
    s = open("db/schema.sql", encoding="utf-8").read()
    assert "ADD COLUMN IF NOT EXISTS watch_state" in s


# ── 격리

def test_관측자는_판정하지_않는다():
    """🔴 상태 전이는 코드만 한다. LLM 을 부르면 그 자리가 판정이 된다."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(O))
    mods = {a.name.split(".")[0]
            for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {(n.module or "").split(".")[0]
             for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert mods <= {"__future__", "logging", "app"}, mods
