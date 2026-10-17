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


def test_변화가_작아도_묻는다() -> None:
    """🔴🔴 **바뀐 규칙**(사용자 지시 2026-10-16) — 변화가 작아도 **묻는다**.

    > 포메이션 **변화가 없다고 해서 분석 자체를 하지 않으면 안 된다**

    ⚠️ 종전 규칙은 *"트리거(핵심 결장·포메이션 바뀜·자리 ≥ 문턱)가 없으면 안
       묻는다 — 늘 부르면 예산을 태운다"* 였다. 실사고 2026-10-16(Saprissa
       4-4-2 vs Sporting 4-2-3-1): XI 를 받았는데 양 팀이 평소 그대로라
       전략 분석이 **통째로 빠졌다**. 🔴 이제 XI 가 있으면 돈다.
    """
    ok, why = sl.may_ask(REF, _Facts(), _Plan(
        {"L2": {"kind": "rotation", "text": "바뀐 자리 1개", "value": 1.0}}))
    assert ok, f"🔴 변화가 작다고 안 묻는다 — {why}"
    assert "트리거 없음" not in why, why


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


def test_운영_파이프라인에_배선됐다() -> None:
    """🔴🔴 사용자 지시 2026-10-15 — *"전략 변수까지 **운영 파이프라인에
    배선해라**"*. 러너만 부르면 봇 카드에는 그 변수가 **없다**."""
    said = __import__("pathlib").Path("app/core/pipeline.py").read_text()
    assert "strategy_llm" in said, "🔴 운영이 안 부른다"
    assert "_sl.ask(ref, facts, plan" in said, "🔴 전략 판정 뒤에서 안 부른다"
    assert "recent=_sl.recent_of(variables)" in said, "🔴 최근 5경기를 안 넘긴다"


def test_운영이_배치를_다시_세운다() -> None:
    """🔴 묶음이 둘로 갈리면 배치와 축이 어긋난다(실사고 2026-10-15)."""
    said = __import__("pathlib").Path("app/core/pipeline.py").read_text()
    i = said.index("_sl.ask(ref, facts, plan")
    j = said.index("s2e_matchup as _s2e")
    assert "varset = _routing.place(variables)" in said[i:j], \
        "🔴 전략 변수를 더하고 **배치를 다시 세우지 않는다**"


def test_상성_앞에서_부른다() -> None:
    """🔴 상성(S2)이 그 변수를 써야 하므로 **그 앞**이어야 한다."""
    said = __import__("pathlib").Path("app/core/pipeline.py").read_text()
    assert said.index("_sl.ask(ref, facts, plan") < said.index("_s2e.run("), \
        "🔴 상성 뒤에서 부르면 축이 그 변수를 못 본다"


def test_recall_상한이_deepseek_를_안_자른다() -> None:
    """⚠️ 실측 2026-10-15: ⑤-b2 가 **세 경기 연속 `LLM_TRUNCATED`** 로 끊기고
    solar 퇴로가 받았다 — deepseek 는 `reasoning_effort` 를 무시하고 추론으로
    상한을 쓴다. 🔴 그 용도의 출력 상한을 2,000 → **4,000** 으로 올렸다."""
    from app.core import llm
    got = int(dict(llm.purpose_cfg("recall")).get("max_tokens") or 0)
    assert got >= 4000, got


def test_sl9_변화_없어도_돈다() -> None:
    """🔴🔴 SL9 — 사용자 지시 2026-10-16:

    > b2 전략 전문가는 **포메이션에 따른 전술**을 말하는 거다 ·
    > **포메이션 변화가 없다고 해서 분석 자체를 하지 않으면 안 된다**

    ⚠️ 실사고 2026-10-16(Saprissa 4-4-2 vs Sporting 4-2-3-1): XI 2/2 를
       받았는데 양 팀이 평소 그대로라 `⬜ 트리거 없음` 으로 **안 돌았다**.
    🔴 이제 **XI 가 있으면 돈다** — 변화는 사유에 적는 맥락일 뿐이다.
    """
    class _XI:
        def __init__(self, form: str) -> None:
            self.formation = form
            self.players: list = []

    class _F:
        xi = {"h": _XI("4-4-2"), "a": _XI("4-2-3-1")}

    class _Plan:
        facts: dict = {}          # 🔴 변화 사실이 **하나도 없다**

    ok, why = sl.may_ask(None, _F(), _Plan())
    assert ok, f"SL9 🔴 변화가 없다고 안 돈다 — {why}"
    assert "4-4-2" in why and "변화 없음" in why, why
    # 🔴 XI 가 아예 없으면 여전히 안 돈다(읽을 판이 없다)

    class _F0:
        xi: dict = {}

    ok0, why0 = sl.may_ask(None, _F0(), _Plan())
    assert not ok0 and "XI 가 없다" in why0, why0


def test_sl10_포메이션_맞붙기_프롬프트() -> None:
    """🔴 SL10 — 프롬프트가 **두 포메이션이 맞붙는 모양**을 읽으라고 말한다."""
    src = inspect.getsource(sl.ask)
    assert "두 포메이션이 맞붙는 모양" in src, "SL10 🔴 그 규칙이 없다"
    assert "중원 숫자" in src and "변화가 " in src, src[-600:]


def test_sl11_피로도_변수() -> None:
    """🔴🔴 SL11 — 사용자 지시 2026-10-16:

    > 그 일정이 나오면 LLM 전략분석가가 그 팀의 **피로도**를 변수에 넣게 한다

    🔴 수는 **코드가 센다**(`rest_of`) — 모델은 **부등호만** 낸다(절대규칙 5).
    """
    class _R:
        home, away = "h", "a"
        home_name, away_name = "A팀", "B팀"

    class _F:
        recent = {"h": {"rest_days": 3, "last_match_utc": "2026-10-11T18:00",
                        "sequence": [{}] * 5},
                  "a": {"rest_days": 7, "last_match_utc": "2026-10-07T18:00",
                        "sequence": [{}] * 5}}
        schedule = {"h": {"games_14d": 4}, "a": {"games_14d": 2}}

    rows = sl.rest_of(_R(), _F())
    assert len(rows) == 2, rows
    assert "휴식 3일" in rows[0] and "14일 4경기" in rows[0], rows[0]
    assert "휴식 7일" in rows[1], rows[1]

    # 🔴 못 잰 칸은 **이름으로** 남긴다(#3 조용한 0 금지)
    class _F0:
        recent: dict = {}
        schedule: dict = {}

    assert all("⬜ 휴식일 못 쟀다" in x for x in sl.rest_of(_R(), _F0()))
    # 🔴 갈래 목록과 프롬프트에 들어 있다
    assert "일정·피로도" in sl.KINDS
    src = inspect.getsource(sl.ask)
    assert "일정·피로도 재료" in src and "휴식일이 **짧은 " in src, src[-700:]
    assert "rest" in inspect.signature(sl.ask).parameters
    # 🔴 러너가 그 재료를 넘긴다(배선)
    said = (ROOT / "tools/run_collect.py").read_text(encoding="utf-8") \
        if (ROOT := __import__("pathlib").Path(__file__).resolve().parents[2]) \
        else ""
    assert "rest=_sl.rest_of(ref, facts)" in said, "SL11 🔴 러너가 안 넘긴다"
