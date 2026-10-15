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


def test_부등호가_방향이_된다() -> None:
    """🔴🔴 사용자 지시 2026-10-15 — *"딥시크는 … **부등호 표시**를 해서 어느
    값이 크다는 것을 **변수에 제공**해야 한다"*.

    `cmp` 는 **홈 기준**이다: `>` 면 홈이 크다 → 홈 유리.
    """
    got = sl.StrategyRead(rows=[
        sl.StrategyRow(kind="수비 라인", cmp="<", goals_cmp="<",
                       text="원정이 5백으로 내려선다"),
        sl.StrategyRow(kind="압박 높이", cmp=">", goals_cmp="=",
                       text="홈이 전방 압박을 올린다")])
    rows = sl.vars_of(got, REF)
    assert [(v.favors, v.goals) for v in rows] == [("away", "down"),
                                                   ("home", "none")]
    # 🔴 **확률에 닿는 변수**다(변수를 더하는 것이 목적이다)
    assert all(v.weight > 0 and v.usable_as_basis for v in rows)
    # 🔴 카드에 부등호가 그대로 보인다
    assert "홈<원정" in rows[0].claim and "총골<기준" in rows[0].claim


def test_모델은_수를_적을_칸이_없다() -> None:
    """🔴 크기(가중)는 코드가 넣는다 — 모델은 **어느 쪽이 큰지**만 말한다."""
    assert set(sl.StrategyRow.model_fields) == {"kind", "cmp", "goals_cmp",
                                                "text"}
    from app.core.stages import s5_verify as _s5
    assert sl._weight() == float(_s5._sample_weight(5)[1]), "🔴 새 수를 지었다"


def test_둘_다_같음이면_변수가_아니다() -> None:
    got = sl.StrategyRead(rows=[sl.StrategyRow(
        kind="세트피스", cmp="=", goals_cmp="=", text="비슷하다")])
    assert sl.vars_of(got, REF) == []


def test_표에_없는_갈래나_부등호는_버린다() -> None:
    got = sl.StrategyRead(rows=[
        sl.StrategyRow(kind="없는갈래", cmp=">", goals_cmp=">", text="x"),
        sl.StrategyRow(kind="세트피스", cmp="크다", goals_cmp=">", text="y")])
    assert sl.vars_of(got, REF) == []


def test_승인된_표가_모델을_덮는다(monkeypatch) -> None:  # noqa: ANN001
    """🔴 사람이 정한 값이 모델 판단보다 **위**다."""
    monkeypatch.setattr(sl, "_DIRS", {
        "수비 라인": {"goals": "up", "favors": "opponent", "approved": True,
                  "url": "https://x.example/a"}})
    got = sl.StrategyRead(rows=[sl.StrategyRow(
        kind="수비 라인", cmp="<", goals_cmp="<", text="원정이 내려선다")])
    one = sl.vars_of(got, REF)[0]
    assert (one.favors, one.goals) == ("home", "up"), (one.favors, one.goals)
    assert "표가 덮었다" in one.claim


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


def test_최근_5경기_재료를_추린다() -> None:
    """🔴 사용자 지시 2026-10-15 — *"갈래도 찾아서 넣어야 한다 · **최근 5경기
    기준으로**"*. ⚠️ 폼을 다시 세지 않고 `s5_verify` 가 센 변수를 그대로 쓴다."""
    class V:
        def __init__(self, i: str, c: str) -> None:
            self.id, self.claim = i, c
    got = sl.recent_of([V("S01-home", "최근 5경기 L L D L L"),
                        V("R1", "결장"), V("IR12-away", "무패 4경기"),
                        V("S02", "맞대결 3경기")])
    # ⚠️ `R1` 로 세면 안 된다 — `IR12-away` 안에 그 글자가 들어 있다(실측)
    assert len(got) == 3, got
    assert not any("`R1`" in x for x in got), got


def test_프롬프트가_최근_5경기를_요구한다() -> None:
    import inspect
    src = inspect.getsource(sl.ask)
    assert "최근 5경기" in src and "said_recent" in src
    assert "재료에 없는 갈래는 내지 마라" in src, "🔴 지어내기를 안 막는다"


def test_러너가_최근_재료를_넘긴다() -> None:
    said = __import__("pathlib").Path("tools/run_collect.py").read_text()
    assert "recent=_sl.recent_of(variables)" in said, "🔴 안 넘긴다"
