"""🔴🔴 계약 — **1단 기계 점검**(의심 검증 통합본 v2 · 2026-10-14i §2·§4).

| 조항 | 여기서 무엇을 본다 |
|---|---|
| §2 세 묶음 | 점검 칸이 **입력·버그·신선** 셋을 다 덮나 |
| §2 판정 | 버그 거짓 → **고장** · 필수 입력 빠짐 → **기계 보류** |
| §4 | 🔴 **기계 보류면 칠 표가 그 경기를 안 받는다**(다리도 금지) |
| CLAUDE.md #3 | **빠짐(🔴)과 못 쟀다(⬜)를 가른다** |
| MC4 | 🔴 **확률 경로가 이 모듈을 부르지 않는다**(등급·글자만) |
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core import machine as mc
from app.core import picks as pk

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


def _full(**over) -> dict:
    """🔴 전부 ✅ 인 묶음 — 거기서 한 칸씩 떨어뜨려 본다."""
    box = {k: True for k, _n, _g in mc.ROWS}
    box.update(over)
    return box


def test_세_묶음을_다_덮는다():
    groups = {g for _k, _n, g in mc.ROWS}
    assert groups == {"입력", "버그"}, groups
    names = {k for k, _n, _g in mc.ROWS}
    # 🔴 §2 가 이름으로 든 입력 칸이 **빠짐없이** 있다
    for want in ("elo_floor", "axis0", "axis1", "axis2", "axis3", "form_n",
                 "xi", "absence_rung", "coach", "league_offset",
                 "comp_history", "board_lines"):
        assert want in names, want
    # 🔴 버그 칸은 **설정 표**가 이름을 든다(사본 금지)
    bugs = dict(mc.table().get("bugs") or {})
    for key, _n, group in mc.ROWS:
        if group == "버그":
            assert key in bugs, f"`{key}` 의 이름이 설정 표에 없다"
    # 🔴 신선도 칸도 **설정 표**다
    assert dict(mc.table().get("fresh") or {}), "신선도 창이 비었다"


def test_전부_정상이면_정상이다():
    got = mc.check(_full(), now=NOW)
    assert got.verdict == mc.NORMAL
    assert not got.hold()
    assert "정상" in got.why


def test_버그_미반영은_고장이다():
    got = mc.check(_full(axis3_sign=False), now=NOW)
    assert got.verdict == mc.BROKEN, got.why
    assert got.hold(), "고장인데 보류가 아니다"
    assert got.broken and "축3" in " ".join(got.broken), got.broken


def test_필수_입력이_빠지면_기계_보류다():
    hard = set(mc.table().get("hard") or ())
    assert hard, "필수 칸 표가 비었다"
    for key in hard:
        got = mc.check(_full(**{key: False}), now=NOW)
        assert got.verdict == mc.HOLD, f"{key} → {got.verdict}"
        assert got.hold()
        assert "금지" in got.why
    # 🔴 **못 쟀다(⬜)도 필수 칸이면 보류**다 — 모르면 확신할 수 없다
    for key in hard:
        got = mc.check(_full(**{key: None}), now=NOW)
        assert got.verdict == mc.HOLD, f"{key}(⬜) → {got.verdict}"


def test_빠짐과_못_쟀다를_가른다():
    bad = mc.check(_full(coach=False), now=NOW)
    gap = mc.check(_full(coach=None), now=NOW)
    # 🔴 필수가 아닌 칸은 둘 다 **정상**이지만 **다른 목록**에 들어간다
    assert bad.verdict == mc.NORMAL and gap.verdict == mc.NORMAL
    assert bad.thin and not bad.unknown
    assert gap.unknown and not gap.thin
    assert "빠진 칸" in bad.why and "못 쟨 칸" in gap.why


def test_보드가_묵으면_보류_다른_칸은_표시만():
    old = (NOW - timedelta(hours=30)).isoformat()
    got = mc.check(_full(), ages={"board": old}, now=NOW)
    assert got.verdict == mc.HOLD, got.why
    assert any("board" in x for x in got.stale), got.stale
    # 🔴 XI 는 `hold: false` 다 — **적기만** 한다
    got2 = mc.check(_full(), ages={"xi": (NOW - timedelta(hours=30))},
                    now=NOW)
    assert got2.verdict == mc.NORMAL, got2.why
    assert any("xi" in x for x in got2.stale), got2.stale
    # 🔴 시간대 없는 값은 **안 받는다**(절대규칙 2) → 창을 안 센다
    assert mc.age_hours(datetime(2026, 10, 14, 1, 0)) is None
    assert mc.age_hours("쓰레기") is None
    assert mc.age_hours(None) is None


def test_기계_보류면_칠_표가_안_받는다():
    """🔴🔴 §4 — 보류 경기는 **단폴·역배·다리 전부** 금지다."""
    # 🔴 문턱은 `core/picks` 가 든다 — 여기서 숫자를 베끼지 않는다(사본 금지)
    high = max(pk.CUT_SINGLE, pk.CUT_LEG) + 0.02
    base = {"match": "A vs B", "league": "league:ELC", "kickoff": "20:00",
            "board_lines": ["홈 승"], "lines": {"홈 승": high}}
    out = pk.of([dict(base)])
    assert out.singles, "보드도 있고 문턱도 넘는데 단폴이 없다"
    out2 = pk.of([dict(base, machine_hold=True)])
    assert not out2.singles, "기계 보류인데 단폴이 섰다"
    assert not out2.parlays
    assert "기계 보류" in out2.why, out2.why
    # 🔴 다리로도 못 쓴다 — 보류 하나를 끼워 2폴을 만들 수 없다
    rows = [dict(base, machine_hold=True),
            dict(base, match="C vs D", lines={"원정 승": high},
                 board_lines=["원정 승"]),
            dict(base, match="E vs F", lines={"홈 승": high})]
    got = pk.of(rows)
    assert all("A vs B" not in x.match for got_one in got.parlays
               for x in got_one)


def test_확률_경로가_이_모듈을_안_부른다():
    """🔴 MC4 — 1단은 **글자와 보류 깃발**만 만든다(확률 불변)."""
    import ast
    import inspect
    from app.core import probmodel, probfloor, goals, sim
    for mod in (probmodel, probfloor, goals, sim):
        code = ast.unparse(ast.parse(inspect.getsource(mod)))
        assert "machine" not in code.replace("machinery", ""), (
            f"{mod.__name__} 가 1단 점검을 부른다 — 확률 경로다")


def test_버그_칸은_설정에서_읽는다():
    """🔴 §2 — 플래그 원본은 `config/m1v2.yaml` 이다(여기서 값을 안 적는다)."""
    import ast
    import inspect
    code = ast.unparse(ast.parse(inspect.getsource(mc.bug_box)))
    assert "m1v2" in code, "플래그를 설정에서 안 읽는다"
    got = mc.bug_box()
    assert set(got) <= {k for k, _n, g in mc.ROWS if g == "버그"}


def test_점검_전에_멈춘_카드도_보류라고_적는다():
    """🔴🔴 §2 — 신원 검문 퇴로는 점검 **앞**에서 돌아 나간다.

    ⚠️ 실측 2026-10-14: 그 카드에는 점검 줄이 **없었고**, 칠 표는 그 경기를
       *"보드 없음"* 으로만 뺐다 — 까닭이 달라진다(#3 조용한 0 금지).
    """
    got = mc.held("라인업 신원 미확정 — p:x 가 선발인데 결장 명단에도 있다")
    assert got.verdict == mc.HOLD and got.hold()
    assert "멈췄다" in got.why and "금지" in got.why
    # 🔴 칸은 **전부 ⬜** 다(못 쟨 것이지 통과한 것이 아니다)
    assert {r["state"] for r in got.rows} == {"⬜"}
    assert len(got.rows) == len(mc.ROWS)


def test_퇴로_카드가_점검_줄을_싣는다():
    """🔴 배선 — `pipeline._gate_card` 가 `machine`·`machine_hold` 를 채운다."""
    import ast
    import inspect
    from app.core import pipeline as _pl
    code = ast.unparse(ast.parse(inspect.getsource(_pl._gate_card)))
    assert "machine.held" in code or "_mc.held" in code, code[-400:]
    assert "machine_hold=True" in code


def test_해당_없음은_빠짐도_못_쟀다도_아니다():
    """🔴🔴 CLAUDE.md #3 — 세 가지를 **셋으로** 가른다.

    ⚠️ 실측 2026-10-14(챔피언십 카드): `리그 오프셋`·`대회 이력` 은 **대륙 대회
       에서만** 선다. 국내 리그 카드에서 그 둘을 ⬜ 로 적으니 모든 카드가
       *"못 쟨 칸 둘"* 을 달아 **진짜 못 잰 칸이 묻혔다**.
    """
    got = mc.check(_full(league_offset=mc.NA, comp_history=mc.NA,
                         comp_record_verified=mc.NA), now=NOW)
    assert got.verdict == mc.NORMAL, got.why
    assert len(got.na) == 3 and not got.unknown and not got.thin
    assert "해당 없음 3" in got.why, got.why
    # 🔴 분모에서도 빠진다 — `17/17` 이 아니라 `14/14` 다
    assert f"{len(mc.ROWS) - 3}/{len(mc.ROWS) - 3} 칸 ✅" in got.why, got.why
    # 🔴 **필수 칸은 해당 없음이 될 수 없다** — 되면 보류가 뚫린다
    hard = set(mc.table().get("hard") or ())
    for key in hard:
        said = mc.check(_full(**{key: mc.NA}), now=NOW)
        assert said.verdict == mc.HOLD, (
            f"필수 칸 `{key}` 를 ➖ 로 두니 {said.verdict} 가 됐다")


def test_국내_리그는_대륙_칸을_해당_없음으로_둔다():
    """🔴 배선 — `pipeline._machine_of` 가 `club_continental` 로 가른다."""
    import ast
    import inspect
    from app.core import pipeline as _pl
    code = ast.unparse(ast.parse(inspect.getsource(_pl._machine_of)))
    assert "club_continental" in code
    assert "NA" in code


def test_보류_경기는_보류로만_센다():
    """🔴 CLAUDE.md #3 — 까닭을 **한 번만** 적는다(보류가 먼저다).

    ⚠️ 실측 2026-10-14: 보류 경기가 *"보드 없어 뺀 경기"* 와 *"기계 보류로 뺀
       경기"* 에 **둘 다** 올라 까닭이 흐려졌다.
    🔴 **보드 없음은 이제 "뺀다" 가 아니다** — 사용자 지시 2026-10-14
       *"보드없이 진행해라"* 로 **표준 줄**로 간다. 그래서 보드 없는 경기는
       `보드 없음 — 표준 줄로 골랐다` 에만 올라가고, **기계 보류는 여전히 뺀다**.
    """
    high = max(pk.CUT_SINGLE, pk.CUT_LEG) + 0.02
    rows = [{"match": "A vs B", "league": "L", "kickoff": "1",
             "board_lines": [], "lines": {}, "machine_hold": True},
            {"match": "C vs D", "league": "L", "kickoff": "2",
             "board_lines": [], "lines": {"홈 승": high}},
            {"match": "E vs F", "league": "L", "kickoff": "3",
             "board_lines": ["홈 승"], "lines": {"홈 승": high}}]
    out = pk.of(rows)
    why = out.why
    assert "기계 보류로 뺀 경기 1개" in why and "A vs B" in why, why
    # 🔴 보드 없는 경기는 **표준 줄로 간다**(뺀 것이 아니다)
    assert "보드 없음 — 표준 줄로 골랐다" in why and "C vs D" in why, why
    assert {x.match for x in out.singles} == {"C vs D", "E vs F"}, out.singles
    # 🔴 **기계 보류는 여전히 빠진다** — 그 경기는 줄이 하나도 없다
    assert all(x.match != "A vs B" for x in out.singles)
    head = why.split("보드 없음 — 표준 줄로 골랐다")[1].split("·")[0]
    assert "A vs B" not in head, head


def test_보류_경기도_칠_표_줄을_낸다():
    """🔴🔴 조용한 0 금지 — 격자가 없어도 **깃발만 실은 줄**을 낸다.

    ⚠️ 실측 2026-10-14(노리치–사우샘프턴): `slate_queue.pick_row` 가 격자가
       없다고 `None` 을 돌려줘 칠 표가 *"경기 3개"* 라고만 적었고 **보류로 빠진
       경기가 어디에도 안 남았다**.
    """
    import ast
    import inspect
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__)
                           .resolve().parents[2] / "tools"))
    import slate_queue as sq
    code = ast.unparse(ast.parse(inspect.getsource(sq.pick_row)))
    assert "machine_hold" in code
    # 🔴 격자가 없을 때 **보류면** `None` 이 아니다
    assert "if not held" in code, code[:600]
