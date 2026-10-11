"""🔴🔴 **이름 대조·손실 감사** — 사용자 지시 2026-10-11(앞에서부터 고친다) ②.

> 새 사실 손실 감사: 광주–울산 hits 17 → docs 0. 17건 각각 버린 단계·사유·제목을 표로.
> 이름 대조에 config/names_ko.yaml(팀·선수 한글명·약칭)을 쓴다 — **영어 표기만으로
> identity 판정 금지**. 고정물: 한글 기사 "광주FC … 울산" 제목이 identity 통과.

🔴 실측으로 찾은 뿌리(2026-10-11): 울산이 **두 열쇠로 갈려** 있었다 —
   `Ulsan HD`(teams_54 · 한글 별칭 있음) → `team:000311`
   `Ulsan HD FC`(fotmob 표기) → `team:000620` · **이름이 하나도 없다**
   그 경기의 원정 열쇠가 000620 이었으므로 신원 선필터가 쓸 이름은 `Gwangju FC`
   계열 + `Ulsan HD FC` 한 글자뿐이었다 — **한글 기사가 통과할 길이 없었다.**
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
# 열쇠 갈림 — 이름 없는 임시 열쇠를 **이름 있는 팀으로 합친다**
# ══════════════════════════════════════════════════════════════════

def test_org_mark_split_is_healed() -> None:
    """🔴🔴 `Ulsan HD FC` 와 `Ulsan HD` 는 **같은 열쇠**다."""
    from app import teamref
    a, _ = teamref.key_of("Ulsan HD FC", sport="soccer", league="K-League 1")
    b, _ = teamref.key_of("Ulsan HD", sport="soccer", league="K-League 1")
    c, _ = teamref.key_of("울산", sport="soccer", league="K-League 1")
    assert a and a == b == c, (a, b, c)


def test_healed_key_keeps_the_korean_names() -> None:
    """🔴 합친 뒤 그 열쇠는 **한글 이름**을 들고 있다(신원 선필터가 쓴다)."""
    from app.core import adapt
    from app import teamref
    key, _ = teamref.key_of("Ulsan HD FC", sport="soccer",
                            league="K-League 1")
    got = adapt.names_of_key(key)
    assert any("울산" in str(x) for x in got), got


def test_heal_only_when_one_named_team_matches() -> None:
    """⚠️ 걷어서 **둘 이상**이면 합치지 않는다(남의 팀과 섞이는 길)."""
    from app import teamref
    import textwrap
    src = textwrap.dedent(inspect.getsource(teamref.Registry.find))
    assert "merge" in src and "len(cand) == 1" in src


# ══════════════════════════════════════════════════════════════════
# 신원 선필터 — 한글 제목이 통과한다
# ══════════════════════════════════════════════════════════════════

def test_korean_title_passes_identity() -> None:
    """🔴🔴 고정물 — *"광주FC … 울산"* 제목이 identity 를 통과한다."""
    from app import teamref
    from app.core.schema import MatchRef
    from app.core.stages.s3_docs import identity_ok, names_of
    home, _ = teamref.key_of("Gwangju FC", sport="soccer",
                             league="K-League 1")
    away, _ = teamref.key_of("Ulsan HD FC", sport="soccer",
                             league="K-League 1")
    ref = MatchRef(id="m", sport="soccer", competition="K League 1",
                   competition_short="KL1", home=home, away=away,
                   home_name="Gwangju FC", away_name="Ulsan HD FC",
                   kickoff_utc="2026-10-11T05:00:00Z")
    who = names_of(ref)
    ok, said = identity_ok("광주FC, 울산 상대로 홈 3연전 마감", "", who)
    assert ok, (said, who)
    #: 🔴 원정 팀 한글 이름 하나만 있는 제목도 통과한다(결장 기사는 한 팀만 말한다)
    ok2, said2 = identity_ok("울산 HD, 주앙 페드로 결장", "", who)
    assert ok2, (said2, who)


def test_names_ko_is_read_and_adds_nothing_fake() -> None:
    """🔴 `config/names_ko.yaml` 을 **읽어서** 이름 대조에 더한다.

    ⚠️ 팀 한글명의 원본은 `teams_54.yaml`·`entities.yaml` 이다 — 이 파일은 그
       둘이 **말하지 않는 것**(선수 한글명·추가 약칭)만 든다(#1 사본 금지).
    """
    from app import rules
    got = rules.names_ko()
    assert isinstance(got, dict)
    from app.core.stages import s3_docs
    #: 🔴 이름 대조가 그 표를 **부른다**(`rules.ko_of` 하나를 거친다)
    assert "ko_of" in _src(s3_docs.names_of)
    assert "names_ko" in _src(__import__("app.rules", fromlist=["x"]).ko_of)


# ══════════════════════════════════════════════════════════════════
# 손실 감사 — 버린 것 하나하나를 **단계·사유·제목**으로
# ══════════════════════════════════════════════════════════════════

def test_drop_carries_stage_and_title() -> None:
    """🔴🔴 ② — 버린 줄이 **단계·사유·제목**을 들고 있다."""
    from app.core.schema import Drop, DropReason
    got = Drop(what="s3/A-home/https://x", reason=DropReason.IDENTITY_MISMATCH,
               detail="신원 ✗", stage="s3", title="광주FC, 울산 상대로")
    assert got.stage == "s3" and "광주" in got.title


def test_identity_drop_records_the_title() -> None:
    """🔴 배선 — 신원으로 버릴 때 **제목을 넘긴다**."""
    from app.core.stages import s3_docs
    src = _src(s3_docs)
    assert "title=" in src and "stage=" in src


def test_card_prints_the_loss_table() -> None:
    """🔴 카드가 **손실 표**를 적는다(단계·사유·제목)."""
    from app.core import render
    assert hasattr(render, "loss_table")
    src = _src(render.loss_table)
    assert "stage" in src and "title" in src and "reason" in src
