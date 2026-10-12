"""🔴🔴 **3a 무너뜨릴 조건 목록** — 수정 지시서 2026-10-12(반증 우선).

> [3a] 위치: ⑩ 가설 세우기 직후, ⑪ 확률 앞. 모듈: 가설 세우기 모듈 안에 함수
> `build_break_conditions` 추가. … 종류(코드만 만든다, **LLM 추가·삭제 금지**)
>   K1 우위 팀 핵심 공격 선수(공격 기여 상위 2) 결장·벤치
>   K2 우위 팀 무기 꺼짐 · K3 V5 맞대결 반대 방향 · K4 라인업 미확정
>   K5 우위 팀 우선순위 지수 낮음 · K6 열세 팀 핵심 복귀(returning)
> C3 유지: 이 함수는 **S3 숫자를 보지 않는다**.

🔴 계약(B2): 종류 목록은 **코드 상수**다 — LLM 이 늘리거나 줄이면 실패다.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class _Fired:
    def __init__(self, side: str, rule: str = "T1") -> None:
        self.side, self.rule = side, rule


class _MR:
    """🔴 `MatchupReport` 의 **이 함수가 보는 칸만** 흉내 낸다."""

    def __init__(self, *, edge: str = "home", off: dict | None = None,
                 xi_state: str = "confirmed") -> None:
        self.verdict = {"edge": edge, "strength": "중"}
        self.off_weapons = dict(off or {})
        self.xi_state = xi_state
        self.axes: dict = {}

    def edge_of(self) -> str:
        return str(self.verdict.get("edge") or "")


def _ref():
    from app.core.schema import MatchRef
    return MatchRef(id="m", sport="soccer", competition="L",
                    competition_short="L", home="team:000001",
                    away="team:000002", home_name="A", away_name="B",
                    kickoff_utc="2026-10-20T12:00:00Z")


def _var(vid: str, kind: str, side: str, *, hard: bool = True):
    """🔴 `Variable` 의 **필수 칸만** 채운다(실측: id·type·subject·favors·
    hardness·weight·claim·quote)."""
    from app.core.schema import Variable
    return Variable(id=vid, type=kind,
                    subject=("team:000002" if side == "away"
                             else "team:000001"),
                    favors=side, hardness=("hard" if hard else "soft"),
                    weight=0.7, claim=f"{vid} claim", quote=f"{vid} quote")


# ══════════════════════════════════════════════════════════════════
# 종류 — 코드가 만든다(B2)
# ══════════════════════════════════════════════════════════════════

def test_kinds_are_code_constants() -> None:
    from app.core.stages import s6_hypo
    assert tuple(s6_hypo.BREAK_KINDS) == ("K1", "K2", "K3", "K4", "K5", "K6")


def _code_only(fn) -> str:
    """🔴 D46 — **독스트링을 뺀 코드만** 본다(문서가 금지어를 설명하는 것과
    코드가 그것을 부르는 것은 다르다)."""
    tree = ast.parse(inspect.getsource(fn).lstrip())
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_llm_cannot_touch_the_list() -> None:
    """🔴 B2 — 이 함수에 LLM 호출이 **없다**."""
    from app.core.stages import s6_hypo
    said = _code_only(s6_hypo.build_break_conditions).lower()
    for word in ("llm", "ask(", "deepseek", "qwen"):
        assert word not in said, word


def test_c3_does_not_see_s3() -> None:
    """🔴 C3 — 확률을 인자로도 본문으로도 안 본다."""
    from app.core.stages import s6_hypo
    sig = inspect.signature(s6_hypo.build_break_conditions)
    for bad in ("prob", "sim", "probability", "dist"):
        assert bad not in sig.parameters, bad
    said = inspect.getsource(s6_hypo.build_break_conditions)
    tree = ast.parse(said.lstrip())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in (
                "home", "draw", "away"):
            # ⚠️ 승무패 확률 칸을 읽으면 C3 위반이다
            assert "mr" not in ast.unparse(node), ast.unparse(node)


# ══════════════════════════════════════════════════════════════════
# 종류별로 조건이 선다
# ══════════════════════════════════════════════════════════════════

def test_k4_fires_when_xi_not_confirmed() -> None:
    from app.core.stages import s6_hypo
    got = s6_hypo.build_break_conditions(
        _ref(), _MR(xi_state="predicted"), [], hypo_ids=["H1"])
    kinds = {c.kind for c in got}
    assert "K4" in kinds
    one = next(c for c in got if c.kind == "K4")
    assert one.state == "미확인" and one.how == "구조 사실"


def test_k2_fires_for_the_leader_only() -> None:
    """🔴 우위 팀의 무기가 꺼진 것이 반증이다(열세 팀 것은 아니다)."""
    from app.core.stages import s6_hypo
    got = s6_hypo.build_break_conditions(
        _ref(), _MR(edge="home", off={"home": ["forward"], "away": ["press"]}),
        [], hypo_ids=["H1"])
    k2 = [c for c in got if c.kind == "K2"]
    assert len(k2) == 1 and k2[0].team == "team:000001", [(c.kind, c.team)
                                                     for c in got]


def test_k6_fires_on_returning_for_the_trailing_side() -> None:
    from app.core.stages import s6_hypo
    rows = [_var("R1", "returning", "away")]
    got = s6_hypo.build_break_conditions(
        _ref(), _MR(edge="home"), rows, hypo_ids=["H1"])
    assert any(c.kind == "K6" and c.team == "team:000002" for c in got), got


# ⚠️ **K5 계약은 걷었다** — ⑨ 우선순위 지수가 지시서 2026-10-12(셋째) §1 으로
#    **지워졌다**(§7 결장의 무게가 그 일을 한다). 🔴 그래서 K5 라는 조건 자체가
#    없다 — 없는 조건을 시험하면 그 계약이 거짓을 지킨다.

def test_every_condition_has_an_id_and_a_hypothesis() -> None:
    from app.core.stages import s6_hypo
    got = s6_hypo.build_break_conditions(
        _ref(), _MR(xi_state="predicted"), [_var("R1", "returning", "away")],
        hypo_ids=["H1", "H2"])
    assert got
    ids = [c.id for c in got]
    assert len(ids) == len(set(ids)), ids
    for one in got:
        assert one.id.startswith("BRK:")
        assert one.kind in s6_hypo.BREAK_KINDS
        assert one.how in ("구조 사실", "질의")
        assert one.state == "미확인"


def test_wired_before_probability() -> None:
    """🔴 배선 — ⑩ 직후·⑪(확률) **앞**에서 부른다."""
    said = (ROOT / "app/core/pipeline.py").read_text(encoding="utf-8")
    assert "build_break_conditions" in said
    assert said.index("build_break_conditions") < said.index(
        "prob = _pm.run("), "🔴 확률보다 뒤에서 부른다"
