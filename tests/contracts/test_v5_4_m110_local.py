"""🔴🔴 **§4-2 현지어 · §4-3 비용(M110)**.

지시서 `docs/fable/archive/2026-10-05_workorder_idn_tha_fixes.md` §4-2·§4-3.

> **4-2 출처 쏠림과 현지어** — 한 도메인이 검증 변수 근거의 **50% 초과**면
> 카드에 경고(기존)와 함께, 리드의 2차 보충을 **그 도메인을 제외한 현지어
> 질의**로 1회 돌린다(2차 1회 안에서 — 횟수 추가 아님).
> 🔴 **국가대표 경기의 현지어는 양 팀 각각의 언어다**(인도네시아어 `id`,
> 태국어 `th`). Babel likely-subtag 로 구하고, 하위 과제 **2차 질의 언어를
> 팀별로 다르게** 쓴다.
>
> **4-3 비용 상한** — 하루 상한이 $5 로 바뀐 커밋을 찾아 보고한다. 사용자
> 결정 기록(`decisions/`)이 **없으면 $3 로 되돌린다.** 🔴 상한 값은
> `config/llm.yaml` **한 곳에서만** 읽는다(M110).
"""
from __future__ import annotations

import ast
import inspect
import pathlib


# ══════════════════════════════════════════════════════════════════
# §4-2 — 쏠림이면 그 도메인을 빼고 현지어로
# ══════════════════════════════════════════════════════════════════
def test_r42_쏠린_도메인을_찾는다():
    from app import analyze
    assert hasattr(analyze, "skewed_host"), (
        "🔴 `analyze.skewed_host(변수들)` 이 없다 — 50% 초과를 셀 곳")
    rows = [{"source_url": "https://fotmob.com/1"},
            {"source_url": "https://fotmob.com/2"},
            {"source_url": "https://fotmob.com/3"},
            {"source_url": "https://a.com/1"}]
    got, said = analyze.skewed_host(rows)
    assert got == "fotmob.com", (got, said)
    assert "75" in said or "3/4" in said, said
    # 🔴 정확히 50% 면 **아니다**(초과여야 한다)
    half = [{"source_url": "https://a.com/1"}, {"source_url": "https://b.com/1"}]
    assert analyze.skewed_host(half)[0] is None


def test_r42_팀별_현지어가_다르다():
    """🔴 *"국가대표 경기의 현지어는 **양 팀 각각의 언어**"*."""
    from app.research import subtasks
    assert hasattr(subtasks, "team_lang"), (
        "🔴 `subtasks.team_lang(팀 이름)` 이 없다 — 팀별 언어를 구할 곳")
    assert subtasks.team_lang("Indonesia") == "id", subtasks.team_lang("Indonesia")
    assert subtasks.team_lang("Thailand") == "th", subtasks.team_lang("Thailand")
    # ⚠️ 못 구하면 **빈 글**(지어내지 않는다)
    assert subtasks.team_lang("") == ""


def test_r42_하위가_자기_팀_언어를_든다():
    from app.research import subtasks
    got = subtasks.split({"home": "Indonesia", "away": "Thailand",
                          "home_id": "team:000108", "away_id": "team:000111",
                          "sport": "soccer", "league": "FIFA ASEAN Cup",
                          "langs": ("en", "id")})
    homes = [t for t in got if t.side == "home"]
    aways = [t for t in got if t.side == "away"]
    assert all(t.local_lang == "id" for t in homes), [t.local_lang for t in homes]
    assert all(t.local_lang == "th" for t in aways), [t.local_lang for t in aways]


def test_r42_2차가_쏠린_도메인을_뺀다():
    from app import analyze
    tree = ast.parse(inspect.getsource(analyze))
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "skewed_host" in called, (
        "🔴 카드가 `skewed_host` 를 **안 부른다** — 쏠려도 2차가 같은 곳을 본다")


# ══════════════════════════════════════════════════════════════════
# §4-3 · M110 — 상한은 한 곳에서만
# ══════════════════════════════════════════════════════════════════
def test_M110_상한을_한_곳에서만_읽는다():
    """🔴 `config/llm.yaml` 이 원본이다 — 코드가 **그 칸으로만** 읽는다.

    ⚠️ **한 글자 수로 찾으면 안 된다**(실측 2026-10-05): 상한이 `5` 가 되자
       `app/` 의 거의 모든 파일이 걸렸다(`[:5]`·`range(5)`…). 🔴 그래서
       *"수가 코드에 있나"* 가 아니라 **"읽는 자리가 하나인가"** 를 본다.
    """
    from tests._helpers import strip_docs
    bad: list[str] = []
    for f in sorted(pathlib.Path("app").rglob("*.py")):
        body = strip_docs(f.read_text(encoding="utf-8"))
        # 🔴 **그 칸을 읽는 자리**(첨자·`get`)만 본다 — 주석의 글자는 아니다.
        #    ⚠️ M110 돌연변이가 `DAY_CAP = 5.0  # per_day_usd` 로 통과했다:
        #       `strip_docs` 는 **줄 끝 주석**을 안 걷는다(실측 2026-10-05).
        import re as _re
        hit = _re.search(r"""per_day_usd["']\s*\]|get\(\s*["']per_day_usd""",
                         body)
        if not hit:
            continue
        if f.name not in ("solar.py", "rules.py"):
            bad.append(str(f))
    assert not bad, (
        f"🔴 `per_day_usd` 를 **여러 곳**에서 읽는다{bad} — 한 곳에서만 "
        f"읽어라(M110). 다른 코드는 `solar.budget_cfg()` 를 거쳐라")


def test_M110_설정_두_곳이_같은_수다():
    """🔴 `stage_gates.yaml` 의 칸이 `llm.yaml` 과 **같아야** 한다."""
    from app import rules
    import yaml
    cap = float(rules.llm_budget()["per_day_usd"])
    box = yaml.safe_load(
        pathlib.Path("config/stage_gates.yaml").read_text(encoding="utf-8"))
    said = None
    for _k, v in (box.get("gates") or box).items():
        if isinstance(v, dict) and isinstance(v.get("numbers"), dict):
            if "usd_per_day_max" in v["numbers"]:
                said = float(v["numbers"]["usd_per_day_max"])
    assert said is not None, "🔴 `usd_per_day_max` 를 못 찾았다"
    assert said == cap, (
        f"🔴 게이트 표는 ${said:g}, 예산은 ${cap:g} — **두 곳이 갈렸다**(M110)")


def test_M110_상한_변경이_기록되어_있다():
    """🔴 *"사용자 결정 기록(`decisions/`)이 없으면 $3 로 되돌린다"*.

    ⚠️ 사용자가 2026-10-05 에 *"$5로 해라"* 라고 **직접 지시**했다 —
       그 기록을 `decisions/` 에 남겼는지 본다(§11-1: 파일에 없는 지시는
       인용하지 않는다).
    """
    box = pathlib.Path("docs/fable/decisions")
    hits = [f for f in box.glob("*.md")
            if "per_day_usd" in f.read_text(encoding="utf-8")
            or "하루 상한" in f.read_text(encoding="utf-8")]
    assert hits, (
        "🔴 하루 상한 변경이 `decisions/` 에 **없다** — 지시서 §4-3 은 기록이 "
        "없으면 $3 로 되돌리라고 한다")
    said = "\n".join(f.read_text(encoding="utf-8") for f in hits)
    assert "$5" in said or "5.0" in said, (
        "🔴 기록에 **바뀐 수**가 없다 — 무엇으로 바꿨는지 적어야 한다")
