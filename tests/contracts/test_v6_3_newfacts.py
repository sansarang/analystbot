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


# ⚠️ **걷은 시험** — `s9_audit`(최종 평 LLM **검열**)이 지시서
#    2026-10-12(셋째) §1 처분으로 지워졌다(그 평이 코드 템플릿이 되었다).
#    🔴 코드 계산이던 `top_scores`·`score_drivers`·`_names_in` 은 쓰는 곳
#    (`app/core/layer1.py`)으로 **옮겼다** — 사본이 아니다.
#    걷은 시험: `test_v6_새사실이_있으면_이유_문단이_쓴다`
