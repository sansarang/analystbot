"""🔴🔴 **배치표 여섯 집안 판**(`types_v2`) — 사용자 지시 2026-10-15.

> 지금은 변수들이 각양각색이다 … **라우팅 고치고** 제안대로 해라 · 배선도 확인해라

🔴 집안마다 **확률 통로 하나** — ① 전력→축0 · ② 흐름→축1 · ③ 전술→축2 ·
   ④ 골 성향→축3 · ⑤ 조건→λ · ⑥ 표시 전용→없음.
⚠️ 기본은 **꺼짐**이다(확률 경로 변경이라 백필 판정 전에는 운영을 안 바꾼다).
"""
from __future__ import annotations

import yaml

from app.core import m1v2, routing as rt

AX = ("axis0", "axis1", "axis2", "axis3", "lambda_const")


def _box() -> dict:
    return yaml.safe_load(open("config/variable_routing.yaml", encoding="utf-8"))


def test_기본은_꺼짐이다() -> None:
    """🔴 플래그를 켜지 않았으면 **옛 표**가 돈다(운영 불변)."""
    assert m1v2.on("route_v2") is False
    assert rt.table()["types"]["team_stats"]["places"] == ["axis1", "axis2",
                                                           "hypo"]


def test_켜면_여섯_집안_판이_돈다(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(m1v2, "on", lambda name: name == "route_v2")
    got = dict(rt.table()["types"])
    assert got["team_stats"]["places"] == ["axis1", "hypo"], got["team_stats"]
    assert got["def_absence"]["places"] == ["axis0", "hypo"]
    assert got["lineup_intent"]["places"] == ["axis2", "hypo"]


def test_켠_판은_확률_통로가_하나다(monkeypatch) -> None:  # noqa: ANN001
    """🔴🔴 이중 계산 금지 — 한 변수가 두 축에 걸리지 않는다."""
    monkeypatch.setattr(m1v2, "on", lambda name: name == "route_v2")
    bad = {}
    for kind, row in dict(rt.table()["types"]).items():
        axes = [p for p in (row.get("places") or []) if p in AX]
        if len(axes) > 1:
            bad[kind] = axes
    assert not bad, f"🔴 두 축에 걸린 유형 — {bad}"


def test_옛_판에는_이중_계산이_있었다() -> None:
    """⚠️ 고치는 까닭을 **시험이 증언한다** — 옛 표는 두 축에 걸렸다."""
    old = dict(_box()["types"])
    doubles = {k: [p for p in v["places"] if p in AX]
               for k, v in old.items()
               if len([p for p in v["places"] if p in AX]) > 1}
    assert "team_stats" in doubles and "def_absence" in doubles, doubles


def test_쪼갠_유형이_두_표에_다_있다() -> None:
    """🔴 배선 — 꺼짐이든 켜짐이든 **배치 실패가 나면 안 된다**(C6)."""
    box = _box()
    for name in ("types", "types_v2"):
        got = dict(box.get(name) or {})
        for kind in ("form_streak", "standing_motive", "mood", "goal_profile"):
            assert kind in got, f"🔴 `{name}` 에 `{kind}` 가 없다"


def test_규칙_표의_유형이_전부_배치표에_있다() -> None:
    """🔴 **원본에서 자라는 검사**(#1) — 규칙이 쓰는 유형을 손으로 안 적는다."""
    rules = yaml.safe_load(open("config/interpret_rules.yaml", encoding="utf-8"))
    kinds = {str(r.get("type")) for r in (rules.get("rules") or [])
             if r.get("type")}
    box = _box()
    for name in ("types", "types_v2"):
        got = dict(box.get(name) or {})
        missing = sorted(k for k in kinds if k not in got)
        assert not missing, f"🔴 `{name}` 에 없는 규칙 유형 — {missing}"


def test_쪼갠_유형이_실제로_쓰인다() -> None:
    """🔴 배선 — 표만 바꾸고 변수를 안 바꾸면 집안이 비어 있다."""
    said = open("config/interpret_rules.yaml", encoding="utf-8").read()
    assert "type: form_streak" in said, "🔴 IR12 가 아직 team_stats 다"
    assert "type: standing_motive" in said, "🔴 IR14 가 아직 stakes 다"
    s5 = open("app/core/stages/s5_verify.py", encoding="utf-8").read()
    assert '"mood", row, key' in s5, "🔴 연패 간절함이 아직 stakes 다"
