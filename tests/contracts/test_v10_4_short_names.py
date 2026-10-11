"""🔴🔴 **짧은 이름 별칭 · 연패 간절함** — 사용자 지시 2026-10-11.

> 1번 해라 — 짧은 이름(`Kawasaki`·`Nagoya`)을 신원 선필터가 모른다.
> 그리고 **연패한 팀일수록 승리에 더 간절하다**도 가설에 추가해라.

⚠️ 손실 표가 준 증거(2026-10-11): `Kawasaki vs. Nagoya (Oct 11, 2026) Live Score
   - ESPN` 이 `identity_mismatch` 로 버려졌다 — **두 팀 이름이 다 있는데** 우리가
   아는 이름은 `Kawasaki Frontale`·`Nagoya Grampus` 뿐이었다.
"""
from __future__ import annotations

import ast
import inspect


def _src(fn) -> str:
    tree = ast.parse(inspect.getsource(fn))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Module)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


# ══════════════════════════════════════════════════════════════════
# 1 — 짧은 이름(도시·첫·끝 토막)
# ══════════════════════════════════════════════════════════════════

def test_short_forms_add_city_tokens() -> None:
    """🔴 `Kawasaki Frontale` → `Kawasaki` · `Albirex Niigata` → `Niigata`."""
    from app.core.stages import s3_docs
    got = s3_docs.short_forms(["Kawasaki Frontale", "Albirex Niigata"])
    assert "Kawasaki" in got and "Niigata" in got, got


def test_short_forms_skip_generic_words() -> None:
    """🔴🔴 **흔한 낱말은 넣지 않는다** — 남의 경기를 분석하는 길이다."""
    from app.core.stages import s3_docs
    got = s3_docs.short_forms(["Manchester United", "FC Seoul",
                               "New York City FC", "Real Sociedad"])
    for bad in ("United", "City", "FC", "Real", "New", "York"):
        assert bad not in got, (bad, got)
    assert "Manchester" in got and "Sociedad" in got, got


def test_short_forms_need_length() -> None:
    """🔴 라틴은 **4글자 이상**만(짧은 토막은 아무 글에나 걸린다)."""
    from app.core.stages import s3_docs
    got = s3_docs.short_forms(["AS Roma", "Ajax"])
    assert "AS" not in got, got
    #: ⚠️ 한 낱말 이름은 그대로 쓰면 되므로 **추가하지 않는다**
    assert "Ajax" not in got, got


def test_identity_passes_the_espn_title() -> None:
    """🔴🔴 고정물 — 그 ESPN 제목이 **통과한다**."""
    from app.core.schema import MatchRef
    from app.core.stages.s3_docs import identity_ok, names_of
    ref = MatchRef(id="m", sport="soccer", competition="J. League",
                   competition_short="J1", home="team:000277",
                   away="team:000280", home_name="Kawasaki Frontale",
                   away_name="Nagoya Grampus",
                   kickoff_utc="2026-10-11T07:00:00Z")
    who = names_of(ref)
    ok, said = identity_ok("Kawasaki vs. Nagoya (Oct 11, 2026) Live Score "
                           "- ESPN", "", who)
    assert ok, (said, who)


# ══════════════════════════════════════════════════════════════════
# 연패 간절함 — 가설 근거로만(확률에 닿지 않는다)
# ══════════════════════════════════════════════════════════════════

def test_losing_streak_becomes_a_hypothesis_fact() -> None:
    """🔴🔴 **연패한 팀일수록 승리에 더 간절하다** — 그 사실을 변수로 낸다."""
    from app.core.stages import s5_verify
    src = _src(s5_verify)
    assert "연패" in src, "연패를 세지 않는다"
    assert "간절" in src, "그 뜻(간절함)을 적지 않는다"


def test_losing_streak_counts_from_the_one_list() -> None:
    """🔴 연패는 **그 한 경기 목록**에서 센다(사본 금지)."""
    from app.core.stages import s2_facts
    got = s2_facts._recent_from_games(
        [{"date": "d", "league": "L", "side": "home", "score": "0-1",
          "gf": 0, "ga": 1}] * 4, kickoff=None)
    assert got["streak_losing"] == 4, got
    mix = s2_facts._recent_from_games(
        [{"gf": 0, "ga": 1}, {"gf": 1, "ga": 1}, {"gf": 0, "ga": 2}],
        kickoff=None)
    #: 🔴 **최신부터** 연속인 것만 센다(가운데 무승부에서 끊긴다)
    assert mix["streak_losing"] == 1, mix


def test_losing_streak_never_touches_probability() -> None:
    """🔴 그 변수는 `stakes` 다 — 자리는 **V2·가설**뿐(확률 금지)."""
    from app.core import routing
    box = dict(dict(routing.table().get("types") or {}).get("stakes") or {})
    assert sorted(box.get("places") or []) == ["V2", "hypo"], box
    #: 🔴 그래서 축(axis0~3)·λ 상수 자리가 **없다**
    assert not [p for p in (box.get("places") or [])
                if str(p).startswith("axis") or p == "lambda_const"]


def test_short_forms_skip_country_fragments() -> None:
    """🔴🔴 실사고 2026-10-11 — **나라 조각·대표팀 꼬리말**은 넣지 않는다.

    재생 고정물(South Korea vs Uzbekistan)에서 `South Korea` → `Korea`,
    한글 별칭에서 `대표팀` 이 나와 **남의 글**을 들여보냈고 **기사 변수가 0개**가
    됐다(e2e 불변식17·2 가 잡았다).
    """
    from app.core.stages import s3_docs
    assert s3_docs.short_forms(["South Korea"]) == []
    assert "대표팀" not in s3_docs.short_forms(["한국 대표팀"])
    assert "한국" in s3_docs.short_forms(["한국 대표팀"])


def test_short_forms_only_in_identity_filter() -> None:
    """🔴 짧은 이름은 **신원 선필터만** 쓴다(본문 검사로 새지 않는다).

    ⚠️ 실사고: `names_of` 에 넣었더니 `verify.ended_this_match` 가 멀쩡한 기사를
       *"끝난 경기"* 로 읽었다.
    """
    from app.core.stages import s3_docs
    assert "short_forms" not in _src(s3_docs.names_of)
    assert "short_forms" in _src(s3_docs.identity_ok)
