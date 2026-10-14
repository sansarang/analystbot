"""🔴🔴 **직전 경기 이름 맞추기 계약** — 실사고 2026-10-15.

> 안 나오는 것: 바뀐 자리 **못 쟀다** · ΔA · ΔD · 핵심 선수 표 · 자리별 교체
> (사용자 지적 2026-10-15)

🔴 그 연쇄의 **첫 칸**이 이것이었다:
```
mentions_team('Feyenoord', 'Feyenoord Rotterdam') → **False**   (한 방향만 본다)
  → prev_match_urls 가 그 팀 직전 경기를 **0개** 냈다(teamForm 에는 **5개**가 있었다)
  → 과거 XI 0경기 → 평소 XI 없음
  → 바뀐 자리 · ΔA · ΔD · 핵심 선수 표 · 자리별 교체 **전부 ⬜**
```
⚠️ 오늘 **네 번째** 같은 종류다(별칭 뽑기 · `need()` 표시 · 조 순위표 · 이것) —
   전부 *"짧은 이름 ↔ 긴 이름"* 이다.

지키는 것:
  PN1 **이름 대 이름 전용 문**을 쓴다(`verify.same_team`) — 자리마다 따로 짜지
      않는다. ⚠️ 같은 한 방향 검사가 fotmob 에 **14곳**이었다 — 하나씩 고치면
      또 놓친다(실측 2026-10-15: 내가 첫 고침을 엉뚱한 곳에 넣었다)
  PN2 긴 이름으로 물어도 짧은 이름 팀의 직전 경기가 **나온다**
  PN3 **남의 팀은 거부한다**(느슨하게 풀지 않았다)
  PN4 `continue` 가 **덤으로 남지 않았다**(그러면 모든 팀을 거부한다)
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = "app/collect/fotmob.py"


def _page_of(team_form: list) -> dict:
    """🔴 `prev_match_urls` 가 읽는 **실물 자리**로 가짜 응답을 짓는다.

    🔴 자리 둘 — `_box` → `content.matchFacts` · `_side` → **`content.lineup`**.
    ⚠️ 내가 두 번 짐작했다: 처음엔 `general.teamForm`·`matchDate`, 다음엔 팀
       이름을 `general.homeTeam` 에 뒀다. 🔴 둘 다 틀렸다 — 받아서 확인한 자리는
       `content.lineup.homeTeam.name` 이다(규율 #4).
    """
    return {"props": {"pageProps": {"content": {
        "matchFacts": {"teamForm": team_form},
        "lineup": {"homeTeam": {"name": "Feyenoord"},
                   "awayTeam": {"name": "Como"}}}}}}


def _body(name: str) -> str:
    """🔴 그 함수의 **코드만** — 주석·독스트링은 뺀다(규율 D46).

    ⚠️ 실사고 2026-10-15: 내가 주석까지 포함해 검사했더니 *"`teamname` 을 직접
       부른다"* 는 거짓 위반이 났다 — 그 글자가 **설명 주석**에만 있었다.
       🔴 *"문서가 금지어를 설명하는 것과 코드가 그것을 부르는 것은 다르다"*(D46).
    """
    said = (ROOT / MOD).read_text(encoding="utf-8")
    tree = ast.parse(said)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == name)
    rows = said.splitlines()[fn.lineno - 1:fn.end_lineno]
    # 🔴 독스트링을 뺀다
    body = list(getattr(fn, "body", []) or [])
    drop: set[int] = set()
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        one = body[0]
        drop = set(range(one.lineno, (one.end_lineno or one.lineno) + 1))
    out = []
    for i, t in enumerate(rows, fn.lineno):
        if i in drop or t.strip().startswith("#"):
            continue
        out.append(t)
    return "\n".join(out)


def test_pn1_uses_one_door() -> None:
    """PN1 — **이름 대 이름**은 `verify.same_team` 하나를 쓴다(사본 금지).

    ⚠️ 같은 한 방향 검사가 `fotmob` 에 **14곳**이었다. 하나씩 고치면 또 놓친다 —
       실측 2026-10-15: 내가 첫 고침을 **엉뚱한 함수**에 넣고 "고쳤다"고 말했다.
    🔴 그래서 payload 의 팀 이름과 견주는 자리는 **그 문 하나**로 모았다.
    """
    said = _body("prev_match_urls")
    assert "verify.same_team(" in said, (
        "PN1 🔴 `verify.same_team` 을 안 쓴다 — `mentions_team` 만으로는 "
        "`('Feyenoord','Feyenoord Rotterdam')` 을 못 맞춘다(실측)")
    assert "teamname" not in said, (
        "PN1 🔴 이 함수가 이름 맞추기를 **직접** 한다 — 그 일은 "
        "`verify.same_team` 안에 있다(사본 금지)")
    # 🔴 `parse_prev` 도 같은 문을 써야 한다(거기서 사실을 뽑는다)
    said2 = _body("parse_prev")
    assert "verify.same_team(" in said2, (
        "PN1 🔴 `parse_prev` 가 아직 한 방향 검사를 쓴다 — 주소는 맞게 따라가도 "
        "그 페이지에서 **사실 0건**이 된다(실측 2026-10-15)")


def test_pn4_no_stray_continue() -> None:
    """PN4 🔴🔴 — `continue` 가 덤으로 남으면 **모든 팀을 거부한다**.

    ⚠️ 실사고 2026-10-15: 내가 치환할 때 옛 줄의 `continue` 가 하나 남아
       이름이 맞아도 그 아래로 못 가게 됐다. 바꾼 줄을 **출력해 보고서야** 잡았다
       (규율 #8). 🔴 그 꼴을 기계가 막는다.
    """
    said = _body("prev_match_urls")
    i = said.find("same_team(")
    assert i > 0, "PN4 🔴 `same_team(` 을 못 찾았다"
    tail = said[i:i + 200]
    # 🔴 그 `if` 뒤의 `continue` 는 **하나**여야 한다
    assert tail.count("continue") == 1, (
        f"PN4 🔴🔴 `same_team` 뒤에 `continue` 가 {tail.count('continue')}개다 — "
        "둘이면 이름이 맞아도 **모든 팀이 거부된다**")


def test_pn2_long_name_finds_short_team() -> None:
    """PN2 — 긴 이름으로 물어도 짧은 이름 팀의 직전 경기가 나온다."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app import cells
    from app.collect import fotmob as fm

    # 🔴 실물 꼴의 가짜 응답 — `teamForm` 두 쪽 · 링크와 날짜가 있다
    # 🔴 **실물 자리** — `teamForm` 은 `content.matchFacts` 안이고 날짜는
    #    `date.utcTime` 이다(`fotmob._box`·`_when_of` 가 그렇게 읽는다).
    #    ⚠️ 내가 처음엔 `general.teamForm`·`matchDate` 로 적어 계약이 **0개**를
    #       받았다 — 짐작으로 가짜 응답을 지으면 계약이 거짓이 된다(규율 #4).
    def _g(slug: str, when: str) -> dict:
        return {"linkToMatch": f"/matches/{slug}/abc#1",
                "date": {"utcTime": when}}
    j = _page_of([[_g("nec-vs-feyenoord", "2026-09-05T14:30:00Z"),
                   _g("barcelona-vs-feyenoord", "2026-09-09T16:45:00Z")],
                  [_g("como-vs-genoa", "2026-09-04T18:45:00Z")]])
    q = cells.Question(cells.Q_LINEUP, "x", team="Feyenoord Rotterdam",
                       league="UCL", deadline=None)
    got = fm.prev_match_urls(j, q)
    assert len(got) == 2, (
        f"PN2 🔴🔴 긴 이름(`Feyenoord Rotterdam`)으로 물었을 때 짧은 이름 팀"
        f"(`Feyenoord`)의 직전 경기를 {len(got)}개 냈다 — 2개여야 한다")


def test_pn3_other_team_rejected() -> None:
    """PN3 — **남의 팀**은 거부한다(느슨하게 풀지 않았다)."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app import cells
    from app.collect import fotmob as fm
    j = _page_of([[{"linkToMatch": "/matches/a/b#1",
                    "date": {"utcTime": "2026-09-05T14:30:00Z"}}],
                  [{"linkToMatch": "/matches/c/d#2",
                    "date": {"utcTime": "2026-09-04T18:45:00Z"}}]])
    q = cells.Question(cells.Q_LINEUP, "x", team="Arsenal",
                       league="UCL", deadline=None)
    got = fm.prev_match_urls(j, q)
    assert got == [], (
        f"PN3 🔴🔴 남의 팀(`Arsenal`)에게 직전 경기 {len(got)}개를 줬다 — "
        "이름 맞추기를 **너무 느슨하게** 풀었다")
