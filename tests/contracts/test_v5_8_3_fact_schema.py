"""🔴🔴 **v5 §8-3 — 어댑터 통일 스키마.** #6 을 닫는 자리다.

§8-3 원문:

> 모든 어댑터는 **같은 꼴**로 낸다. 어댑터 고유 칸
> (`home_goals/home_score`, `last5/recent`, `matches/window_games`)은
> **어댑터 안에서 변환하고 밖으로 나오지 않는다.**
> 계약: **어댑터 밖 코드에서 어댑터 고유 칸 이름이 보이면 실패.** [#6]

══════════════════════════════════════════════════════════════════
🔴 왜 — **같은 꼴 버그를 세 번** 맞았다
══════════════════════════════════════════════════════════════════

```
2026-10-04 ①  last5 를 내는 것은 fotmob 하나 → 야구·하키 폼 변수 **0**
2026-10-04 ②  home_goals 를 쓰는 것은 fotmob 하나 → 야구·하키 맞대결 **0승 0패**
2026-10-04 ③  window_games 만 세고 count·matches 를 안 봐 13경기가 **0경기**
```
⚠️ 셋 다 **읽는 쪽**(`classify`)에 `or` 를 덧대 고쳤다. §11-1 이 금지한 그것이다:

> **증상 수정 금지** — 같은 꼴 버그가 두 번째로 나오면 그 자리를 고치지 말고
> **그 꼴을 막는 계약부터** 쓴다(칸 이름 불일치 → `Fact` 스키마 계약).

🔴 그래서 이 계약은 *"어댑터가 변환해서 내보낸다"* 를 잠근다 — 읽는 쪽에 분기가
   남아 있으면 **빨개진다.**

🔴 **§10-4 M37** — 어댑터 칸 불일치 3건(10-04) — Fact 통일 스키마 · 고유 칸 외부 노출 금지
   ⚠️ 이 계약이 그 줄을 집행한다(`tests/test_contract_coverage.py` 가 번호로 대조한다).
"""
from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
COLLECT = ROOT / "app" / "collect"


def _code_only(path: pathlib.Path) -> str:
    """🔴 **D46** — 독스트링·주석을 뺀 **코드만** 본다.

    ⚠️ 문서가 금지어를 *설명하는* 것과 코드가 그것을 *부르는* 것은 다르다.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(
                    first.value, ast.Constant) and isinstance(
                    first.value.value, str):
                node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_v5_8_3_정본_칸_선언이_있다():
    """🔴 무엇이 정본이고 무엇이 어댑터 고유인지 **한 곳**에 적혀 있어야 한다."""
    from app.factspec import ADAPTER_ONLY, CANON
    # 🔴 §8-3 의 `Fact` 가 이름 댄 칸들
    for k in ("kind", "team", "opponent", "date_utc", "home_score",
              "away_score", "state", "payload", "source", "url", "hardness"):
        assert k in CANON, f"🔴 §8-3 이 이름 댄 `{k}` 가 정본 목록에 없다"
    # 🔴 §8-3 이 이름 댄 **어댑터 고유 칸** 셋
    for k in ("home_goals", "away_goals", "window", "window_games"):
        assert k in ADAPTER_ONLY, f"🔴 `{k}` 가 어댑터 고유 목록에 없다"
    # ⚠️ 정본과 고유가 **겹치면** 그 선언이 뜻을 잃는다
    assert not (set(CANON) & set(ADAPTER_ONLY))


#: 🔴 **열어 둔 자리 — 하나다.** ⚠️ 늘리려면 까닭을 여기 적어야 한다.
#
#  `app/league.py` 의 `cfg.get("window")` 는 **yaml 설정 키**다
#  (`league_rules.yaml: h2h.window: 최근 10경기`) — 어댑터 사실의 칸이 아니고
#  **다른 이름 공간**이다. 🔴 글자가 같을 뿐이다.
ALLOW: frozenset[tuple[str, str]] = frozenset({("app/league.py", "window")})


def test_v5_8_3_어댑터_고유_칸이_밖으로_안_나온다_M37():
    """🔴🔴 §8-3 의 계약 그 자체 — *"어댑터 밖 코드에서 보이면 실패."*"""
    from app.factspec import ADAPTER_ONLY
    bad: list[str] = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        if COLLECT in p.parents or p.name == "factspec.py":
            continue
        rel = str(p.relative_to(ROOT))
        code = _code_only(p)
        for k in ADAPTER_ONLY:
            if (rel, k) in ALLOW:
                continue
            if f'"{k}"' in code or f"'{k}'" in code:
                bad.append(f"{rel} — `{k}`")
    assert not bad, (
        "🔴 어댑터 고유 칸이 어댑터 **밖**에 보인다(§8-3 · #6). 어댑터 안에서 "
        "정본 이름으로 바꿔 내보내라:\n  " + "\n  ".join(bad))


def test_v5_8_3_열어_둔_자리가_하나다():
    """🔴 예외가 늘면 계약이 뜻을 잃는다 — **수를 잠근다.**"""
    assert len(ALLOW) == 1, sorted(ALLOW)
    # ⚠️ 그 자리가 실제로 **yaml 설정 키**인지 본다(사실의 칸이 아닌지)
    src = (ROOT / "app" / "league.py").read_text(encoding="utf-8")
    assert 'cfg.get("window")' in src, (
        "🔴 열어 둔 자리가 더 이상 yaml 설정 키가 아니다 — 예외를 걷어라")


def test_v5_8_3_어댑터가_정본_이름으로_낸다():
    """🔴 반대 방향 — 어댑터가 **고유 이름만** 내보내면 밖에서 못 읽는다.

    ⚠️ 고유 이름을 어댑터 **안에서 쓰는 것은 괜찮다**(그쪽 원본이 그 글자다).
       🔴 그런데 **내보내는 사실**에는 정본 이름이 있어야 한다.
    """
    from app.factspec import CANON
    for p in sorted(COLLECT.glob("*.py")):
        code = _code_only(p)
        if "home_score" not in code and "home_goals" not in code:
            continue
        # 🔴 **`Fact` 를 내보내는 파일만** 본다(2026-10-06 좁혔다). ⚠️ `collect/elo.py`
        #    는 사실을 안 만든다 — 적합용 줄(`NamedTuple`)만 돌려주고 그 칸 이름이
        #    이미 정본(`home_score`)이다. 사실을 안 내보내는 파일에 "정본 글자를
        #    따옴표로 써라"를 요구하면 계약이 **뜻 없는 글자 검사**가 된다(D46).
        if "Fact(" not in code:
            continue
        assert '"home_score"' in code or "'home_score'" in code, (
            f"🔴 {p.name} 이 점수를 내는데 정본 `home_score` 가 없다")
    assert "home_score" in CANON


# ══════════════════════════════════════════════════════════════════
# §8-3 `Fact` 꼴
# ══════════════════════════════════════════════════════════════════


def test_v5_8_3_Fact가_frozen이고_칸이_맞는다():
    """🔴 `frozen` — 중간 단계가 슬그머니 고치면 그 자체가 이 병의 재발이다."""
    import dataclasses

    from app.factspec import Fact
    assert dataclasses.is_dataclass(Fact)
    assert Fact.__dataclass_params__.frozen, "🔴 `frozen` 이 아니다"
    names = {f.name for f in dataclasses.fields(Fact)}
    for k in ("kind", "team", "opponent", "date_utc", "home_score",
              "away_score", "state", "payload", "source", "url", "hardness"):
        assert k in names, (k, sorted(names))


def test_v5_8_3_naive_시각은_안_받는다():
    """🔴 §8-3: *"`date_utc`: 반드시 tz 포함 — **naive 면 실패**."*"""
    from datetime import datetime, timezone

    from app.factspec import Fact
    ok = Fact(kind="result", team="team:000338", opponent="team:000325",
              date_utc=datetime(2026, 10, 4, tzinfo=timezone.utc),
              home_score=5, away_score=3, state="final",
              payload={}, source="statsapi", url=None, hardness=2)
    assert ok.date_utc.tzinfo is not None
    with pytest.raises(ValueError, match="시간대"):
        Fact(kind="result", team=None, opponent=None,
             date_utc=datetime(2026, 10, 4),      # 🔴 naive
             home_score=None, away_score=None, state="final",
             payload={}, source="x", url=None, hardness=0)


def test_v5_8_3_kind는_선언한_것만():
    """🔴 §8-3 이 여덟을 이름 댔다 — 오타로 새 `kind` 가 생기면 그 사실이 샌다."""
    from datetime import datetime, timezone

    from app.factspec import KINDS, Fact
    assert set(KINDS) == {"result", "standing", "h2h", "starter",
                          "starter_stats", "lineup", "absence", "schedule"}, \
        sorted(KINDS)
    with pytest.raises(ValueError, match="kind"):
        Fact(kind="오타", team=None, opponent=None,
             date_utc=datetime(2026, 10, 4, tzinfo=timezone.utc),
             home_score=None, away_score=None, state="final",
             payload={}, source="x", url=None, hardness=0)


def test_v5_8_3_team은_열쇠여야_한다():
    """🔴 §8-3: *"`team`: **team:ID**(양 팀 공통 사실은 None)."*

    ⚠️ 이름이 들어오면 1~3단계가 고친 그 병이 **데이터 모델에서** 되살아난다.
    """
    from datetime import datetime, timezone

    from app.factspec import Fact
    with pytest.raises(ValueError, match="열쇠"):
        Fact(kind="result", team="Milwaukee Brewers",   # 🔴 이름이다
             opponent=None,
             date_utc=datetime(2026, 10, 4, tzinfo=timezone.utc),
             home_score=1, away_score=0, state="final",
             payload={}, source="x", url=None, hardness=0)




# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **어댑터가 실제로 내는 것을 본다** (2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 위 계약들은 **읽는 쪽**(`classify`)과 **스키마**(`Fact`)만 봤다. 그래서
#     돌연변이 넷이 통과했다:
#
#        A fotmob 이 다시 `home_goals` 로 낸다      → ⚠️ 초록
#        B fotmob 이 다시 `window` 로 낸다          → ⚠️ 초록
#        D mlb 가 `last5` 를 안 낸다                → ⚠️ 초록
#        H `last5_from` 이 예정 경기도 센다          → ⚠️ 초록
#
#  🔴 §8-3 의 요구는 *"어댑터가 **내보내는 것**"* 이다 — 그것을 봐야 한다.


def _fact_value_keys(tree: ast.AST) -> list[tuple[int, set[str]]]:
    """🔴 `Fact(... value={...})` 의 **그 dict 리터럴**의 키들(줄 번호와 함께).

    ⚠️ 어댑터 안에서 고유 이름을 **쓰는 것**은 괜찮다(그쪽 원본이 그 글자다).
       🔴 금지되는 것은 **내보내는 사실의 칸**이다 — 그래서 `value=` 만 본다.
    """
    out: list[tuple[int, set[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not str(ast.unparse(node.func)).endswith("Fact"):
            continue
        for kw in node.keywords:
            if kw.arg != "value" or not isinstance(kw.value, ast.Dict):
                continue
            keys = {k.value for k in kw.value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            out.append((node.lineno, keys))
    return out


def test_v5_8_3_어댑터가_내보내는_사실에_고유_칸이_없다():
    """🔴🔴 §8-3 — *"어댑터 안에서 변환하고 **밖으로 나오지 않는다**."*

    ⚠️ 돌연변이 A·B 가 이 자리를 뚫었다 — 파일에 정본 이름이 **어딘가** 있으면
       통과하는 느슨한 검사였다. 🔴 이제 `Fact(value={...})` 의 **그 dict** 를 본다.
    """
    from app.factspec import ADAPTER_ONLY
    bad: list[str] = []
    for p in sorted(COLLECT.glob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for line, keys in _fact_value_keys(tree):
            for k in sorted(keys & set(ADAPTER_ONLY)):
                bad.append(f"{p.name}:{line} — 내보내는 사실에 `{k}`")
    assert not bad, (
        "🔴 어댑터가 **고유 칸 이름으로 내보낸다**(§8-3 · #6). 어댑터 안에서 "
        "정본 이름으로 바꿔라:\n  " + "\n  ".join(bad))


def test_v5_8_3_행_안의_점수도_정본이다():
    """🔴 `recent`·`matches` **행 안의** 점수 칸까지 정본이어야 한다.

    ⚠️ 돌연변이 A 는 `Fact(value=)` 가 아니라 **행을 만드는 `rows.append`** 를
       건드렸다 — 그래서 위 계약도 못 잡는다. 🔴 어댑터 안의 **모든 dict 리터럴**
       중 `home`·`away`·`date` 를 함께 든 것(= 경기 행)을 본다.
    """
    from app.factspec import ADAPTER_ONLY
    bad: list[str] = []
    for p in sorted(COLLECT.glob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if not ({"home", "away"} <= keys):
                continue          # 경기 행이 아니다
            for k in sorted(keys & set(ADAPTER_ONLY)):
                bad.append(f"{p.name}:{node.lineno} — 경기 행에 `{k}`")
    assert not bad, (
        "🔴 경기 행이 **고유 칸 이름**을 쓴다(§8-3 · #6):\n  " + "\n  ".join(bad))


def test_v5_8_3_폼_사실이_last5를_낸다():
    """🔴🔴 §8-3 — `last5` 변환이 **어댑터 안에서** 끝나야 한다.

    ⚠️ 돌연변이 D(`mlb` 가 `last5` 를 안 낸다)가 통과했다 — 아무 계약도 어댑터의
       **폼 사실**을 보지 않았다. 🔴 실측 꼴로 **실제로 돌려** 본다(통신 없음).
    """
    from datetime import datetime, timezone

    from app.cells import Question
    from app.collect import mlb

    class _Got:
        ok = True
        url = ("https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId=158"
               "&startDate=2026-09-13&endDate=2026-10-04")
        #: 🔴 실측 응답의 모양 그대로(2026-10-04)
        text = """
        {"dates": [
          {"date": "2026-09-25", "games": [{"status": {"abstractGameState": "Final"},
            "teams": {"home": {"team": {"name": "Milwaukee Brewers"}, "score": 5},
                      "away": {"team": {"name": "San Diego Padres"}, "score": 3}}}]},
          {"date": "2026-09-26", "games": [{"status": {"abstractGameState": "Final"},
            "teams": {"home": {"team": {"name": "San Diego Padres"}, "score": 2},
                      "away": {"team": {"name": "Milwaukee Brewers"}, "score": 7}}}]},
          {"date": "2026-09-27", "games": [{"status": {"abstractGameState": "Final"},
            "teams": {"home": {"team": {"name": "Milwaukee Brewers"}, "score": 0},
                      "away": {"team": {"name": "Chicago Cubs"}, "score": 4}}}]}
        ]}"""

    q = Question("lineup", "MLB:Milwaukee Brewers:2026-10-04",
                 team="Milwaukee Brewers", league="MLB",
                 deadline=datetime(2026, 10, 4, 20, 0, tzinfo=timezone.utc))
    facts = mlb.parse_schedule_facts(_Got(), q)
    form = [f for f in facts if str(f.question_id).endswith(":form")]
    assert form, f"폼 사실이 없다: {[f.question_id for f in facts]}"
    v = form[0].value
    assert "last5" in v, (
        f"🔴 폼 사실에 `last5` 가 없다 — §8-3 은 어댑터가 변환하라고 한다: "
        f"{sorted(v)}")
    # 🔴 **값까지 맞는다** — 5-3 홈 승 · 7-2 원정 승 · 0-4 홈 패
    assert v["last5"] == ["W", "W", "L"], v["last5"]
    # ⚠️ 어떻게 셌나도 남는다(#3 조용한 0 금지)
    assert str(v.get("last5_how") or "").strip(), v


def test_v5_8_3_last5_from_이_예정_경기를_안_센다():
    """🔴 돌연변이 H 가 통과했다 — 변환기를 **직접** 치는 계약이 없었다.

    ⚠️ 예정 경기를 승패로 읽으면 거짓이다(점수가 `None` 이거나 0-0 으로 온다).
    """
    from app.factspec import last5_from
    rows = [
        {"home": "A", "away": "B", "home_score": 3, "away_score": 1,
         "state": "Final"},
        {"home": "A", "away": "B", "home_score": None, "away_score": None,
         "state": "Preview"},
        # 🔴 **점수가 0-0 으로 오는 예정 경기** — 상태를 안 보면 무승부로 센다
        {"home": "A", "away": "B", "home_score": 0, "away_score": 0,
         "state": "Scheduled"},
    ]
    got, why = last5_from(rows, team_name="A")
    assert got == ["W"], (got, why)
    assert "건너뜀 2행" in why, why


