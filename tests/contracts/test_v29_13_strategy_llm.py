"""🔴🔴 **전략 전문가(LLM) 변수** — 사용자 지시 2026-10-15.

> 라인업 확장 포메이션 결장 선수가 **주요선수가 뜨면** 전략 전문가 deepseek 에게
> **변수 생성하는 프롬프트**를 주입해라.

🔴 잠금 — LLM 은 **글만** 낸다. 방향·가중은 코드가 넣는다(절대규칙 5).
"""
from __future__ import annotations

import inspect

from app.core import strategy_llm as sl
from app.core.schema import MatchRef

REF = MatchRef(id="m1", sport="soccer", home="team:100001", away="team:100002",
               home_name="홈팀", away_name="원정팀", competition="ACL2",
               competition_short="ACL2",
               kickoff_utc="2026-10-15T10:00:00+00:00")


class _Facts:
    xi = {"team:100001": object()}


class _Plan:
    def __init__(self, box: dict) -> None:
        self.facts = box


def test_핵심_선수가_빠지면_묻는다() -> None:
    ok, why = sl.may_ask(REF, _Facts(), _Plan(
        {"L6": {"kind": "key_player", "text": "홈팀 핵심 선수 X — 명단 제외"}}))
    assert ok and "핵심 선수 빠짐" in why, why


def test_포메이션이_바뀌면_묻는다() -> None:
    ok, why = sl.may_ask(REF, _Facts(), _Plan(
        {"A1": {"kind": "formation", "text": "원정팀 포메이션 4-4-2→5-3-2"}}))
    assert ok and "포메이션 바뀜" in why, why


def test_자리가_많이_바뀌면_묻는다() -> None:
    ok, _ = sl.may_ask(REF, _Facts(), _Plan(
        {"L2": {"kind": "rotation", "text": "바뀐 자리 5개", "value": 5.0}}))
    assert ok


def test_트리거가_없으면_안_묻는다() -> None:
    """🔴 늘 부르면 예산을 태운다."""
    ok, why = sl.may_ask(REF, _Facts(), _Plan(
        {"L2": {"kind": "rotation", "text": "바뀐 자리 1개", "value": 1.0}}))
    assert not ok and "트리거 없음" in why, why


def test_XI_가_없으면_안_묻는다() -> None:
    class _NoXI:
        xi: dict = {}
    ok, why = sl.may_ask(REF, _NoXI(), _Plan(
        {"L6": {"kind": "key_player", "text": "핵심 선수 X — 명단 제외"}}))
    assert not ok and "XI 가 없다" in why, why


def test_LLM_은_방향과_가중을_못_정한다() -> None:
    """🔴🔴 절대규칙 5 — 모델 글이 `favors`·`weight` 에 닿으면 안 된다."""
    got = sl.StrategyRead(rows=[sl.StrategyRow(
        side="home", kind="압박 높이", text="공격수가 빠져 압박이 얕아진다")])
    got_v = sl.vars_of(got, REF)
    assert len(got_v) == 1
    one = got_v[0]
    assert one.favors == "both", "🔴 방향이 붙었다"
    assert one.weight == 0.0, "🔴 가중이 붙었다"
    assert one.goals == "none"
    assert one.usable_as_basis is False
    # 🔴 스키마에 수 칸이 아예 없어야 한다
    assert set(sl.StrategyRow.model_fields) == {"side", "kind", "text"}


def test_표에_없는_갈래는_버린다() -> None:
    got = sl.StrategyRead(rows=[
        sl.StrategyRow(side="home", kind="없는갈래", text="버려야 한다"),
        sl.StrategyRow(side="xxx", kind="압박 높이", text="쪽이 틀렸다"),
    ])
    assert sl.vars_of(got, REF) == []


def test_배치표가_아는_유형으로_적는다() -> None:
    import yaml
    box = yaml.safe_load(open("config/variable_routing.yaml", encoding="utf-8"))
    rows = dict(box.get("types") or {})
    assert sl.VAR_TYPE in rows, f"🔴 `{sl.VAR_TYPE}` 이 배치표에 없다"


def test_deepseek_가_먼저다() -> None:
    """🔴 지시가 deepseek 를 지목했다 — 죽어 있으면 solar 가 받는다."""
    sig = inspect.signature(sl.ask)
    assert sig.parameters["providers"].default == ("deepseek", "solar")


def test_러너에_배선됐다() -> None:
    said = __import__("pathlib").Path("tools/run_collect.py").read_text()
    assert "strategy_llm" in said, "🔴 안 불린다"
    assert "⑤-b2 전략 전문가(LLM)" in said, "🔴 장부에 칸이 없다"
    assert "+ list(var_sl)" in said, "🔴 varset 묶음에 안 들어간다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **방향 표** — 딥서치로 채우고 **사용자가 승인**해야 쓴다
# ══════════════════════════════════════════════════════════════════


def test_승인_전_표는_방향을_안_준다() -> None:
    """⚠️ 실측 2026-10-15: 1차 딥서치가 **미식축구 기사**로 `수비 라인 → down`
    을 적었다. 승인 전 표가 확률에 닿으면 그 거짓이 그대로 들어간다."""
    assert sl._dir_of("수비 라인", "home") == ("both", "none",
                                            " · ⬜ 방향 표 **승인 전**(수비 라인)")


def test_승인된_줄만_방향을_준다(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(sl, "_DIRS", {
        "수비 라인": {"goals": "down", "favors": "subject", "approved": True,
                  "url": "https://x.example/a"}})
    fav, goals, tail = sl._dir_of("수비 라인", "away")
    assert (fav, goals) == ("away", "down"), (fav, goals)
    assert "근거" in tail
    # 🔴 `opponent` 는 **반대 쪽**으로 옮긴다(옮기는 것은 코드다)
    monkeypatch.setattr(sl, "_DIRS", {
        "압박 높이": {"favors": "opponent", "approved": True}})
    assert sl._dir_of("압박 높이", "home")[0] == "away"


def test_표에_없는_갈래는_방향_없음() -> None:
    assert sl._dir_of("없는갈래", "home")[:2] == ("both", "none")


def test_지금_표는_전부_승인_전이다() -> None:
    """🔴 1차 딥서치 결과는 근거가 나빠 **잠가 뒀다**(사용자 승인 대기)."""
    import yaml
    box = yaml.safe_load(open("config/strategy_dirs.yaml", encoding="utf-8"))
    rows = dict(box.get("rows") or {})
    assert rows, "🔴 표가 비었다"
    assert not any(r.get("approved") for r in rows.values()), \
        "🔴 승인되지 않은 값이 켜져 있다"


def test_표를_채우는_도구가_있다() -> None:
    said = __import__("pathlib").Path("tools/fit_strategy_dirs.py").read_text()
    assert "인용" in said and "문서에서" in said
    assert "config" in said and "strategy_dirs.yaml" in said
