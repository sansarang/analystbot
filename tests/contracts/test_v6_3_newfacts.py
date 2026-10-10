"""🔴🔴 **새 사실(72시간)** — 사용자 지시 2026-10-10(재작성) §3.

> 원칙 ③ 새 뉴스(72시간)는 **판단에 반드시 들어간다.**
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_v6_하위_F_가_표에_있고_창이_72시간이다():
    """🔴 §3-1 — 하위 과제 **F** · 킥오프 기준 **72시간**.

    ⚠️ 돌연변이: `window_hours` 를 지우면 F 가 **7일 창**으로 돌고 *"새 사실"* 이
       아니게 된다(그 경기 일주일 전 기사가 섞인다).
    """
    from app.research import subtasks
    rows = {g["key"]: g for g in subtasks.groups()}
    assert "F" in rows, f"🔴 하위 과제 F 가 표에 없다 — {sorted(rows)}"
    got = rows["F"]
    assert int(got.get("window_hours") or 0) == 72, got.get("window_hours")
    # 🔴 §3-5 — *"일반 변수와 **같은 무게표**"* → 새 유형을 만들지 않았다
    import yaml
    cat = yaml.safe_load((ROOT / "config" / "variable_types.yaml")
                         .read_text(encoding="utf-8"))
    known = set((cat.get("types") or {}))
    miss = [k for k in got["kinds"] if k not in known]
    assert not miss, (
        f"🔴 F 의 유형 {miss} 가 카탈로그에 **없다** — 방향·무게를 지어내게 된다"
        f"(§3-5 는 '같은 무게표'라고 적었다)")


def test_v6_F_창이_s3_에_닿는다():
    """🔴 §3-1 — 표의 `window_hours` 가 **실제로 문서 창을 좁히는가**.

    ⚠️ 돌연변이: `s3_docs._window_of` 가 하위를 무시하면 — 표에 72가 적혀 있어도
       7일로 돈다(설정이 **안 이어진 코드**가 된다 · CLAUDE.md #2).
    """
    from datetime import timedelta
    from app.core.stages.s3_docs import _window_of

    class _F:
        window_hours = 72

    class _Other:
        window_hours = 0

    assert _window_of(_F()) == timedelta(hours=72)
    assert _window_of(_Other()) > timedelta(hours=72)


def test_v6_변수가_자기_하위를_들고_간다():
    """🔴 §3-4 — 🆕 블록이 **F 에서 온 변수**를 골라야 한다.

    ⚠️ `Card` 에 `docs` 칸이 없어 문서를 거쳐 셀 길이 없다 → `Variable.subtask`.
    🔴 돌연변이: s5 가 `subtask` 를 안 실으면 🆕 블록이 **영원히 0건**이다.
    """
    import ast
    from app.core.schema import Variable
    assert "subtask" in Variable.model_fields
    said = (ROOT / "app" / "core" / "stages"
            / "s5_verify.py").read_text(encoding="utf-8")
    assert '"subtask": str(c.subtask or "")' in said, (
        "🔴 s5 가 후보의 하위를 변수에 안 싣는다 — 🆕 블록이 늘 0건이 된다")
    assert 'subtask=str(row.get("subtask") or "")' in said, (
        "🔴 s5 가 `Variable(subtask=…)` 을 안 채운다")
    # 🔴 F 가 **스키마에서 허용**돼야 한다(아니면 그 하위의 문서가 거부된다)
    from app.core.schema import SubtaskId
    assert "F-home" in SubtaskId.__args__ and "F-away" in SubtaskId.__args__


def test_v6_카드가_새사실_블록을_낸다():
    """🔴 §3-4 — 블록이 **1겹과 긴 카드 둘 다**에 있어야 한다.

    > 0건이면 *"새 사실 0건 — …"* 과 운영자 알림.

    ⚠️ 돌연멘이: 1겹에서 빼면 사용자가 **그 사실을 못 본다**(1겹이 기본 카드다).
    """
    import ast
    for path, want in ((ROOT / "app" / "core" / "render.py", "new_facts_block"),
                       (ROOT / "app" / "core" / "layer1.py", "_new_facts")):
        said = ast.parse(path.read_text(encoding="utf-8"))
        calls = {ast.unparse(n.func) for n in ast.walk(said)
                 if isinstance(n, ast.Call)}
        assert want in calls or f"render.{want}" in calls, (
            f"🔴 `{path.name}` 이 `{want}` 를 안 부른다 — 블록이 **안 이어졌다**")


def test_v6_새사실이_있으면_이유_문단이_쓴다():
    """🔴🔴 §3-5 — *"최소 한 문장은 새 사실을 쓴다(검열 항목 추가)"*.

    ⚠️ 돌연변이 ①: `(o)` 검열을 지우면 새 사실이 카드에 **적히기만** 하고 판단에
       안 들어간다(지시서 원칙 ③ 위반).
    ⚠️ 돌연변이 ②: `fact_refs` 만 보면 모델이 번호를 빼먹은 **멀쩡한 문장**을
       위반으로 센다 — 그래서 **글자도** 본다. 둘 다 센다.
    """
    from app.core.stages.s9_audit import new_fact_check
    from app.core.schema import ReasonLine

    class _V:
        def __init__(self, vid, claim, target, subtask="F-home"):
            self.id, self.claim, self.target = vid, claim, target
            self.subject, self.subtask, self.from_rule = "", subtask, ""
            self.doc_ids = ["D1"]

    class _Card:
        variables = [_V("R3", "황문기가 병역을 마치고 복귀했다", "absence:황문기")]

    got = _Card()
    # 🔴 번호로 쓴 문장 → 통과
    assert not new_fact_check([ReasonLine(text="아무 말", fact_refs=["R3"])],
                              card=got)
    # 🔴 글자로 쓴 문장 → 통과(번호를 안 적어도)
    assert not new_fact_check([ReasonLine(text="황문기가 돌아왔다",
                                          fact_refs=[])], card=got)
    # 🔴 하나도 안 쓰면 → 위반
    bad = new_fact_check([ReasonLine(text="날씨가 좋다", fact_refs=[])],
                         card=got)
    assert bad and "(o)" in bad[0], bad
    # 🔴 새 사실이 **0건이면** 아무것도 세지 않는다

    class _Empty:
        variables = []

    assert not new_fact_check([ReasonLine(text="x", fact_refs=[])],
                              card=_Empty())
