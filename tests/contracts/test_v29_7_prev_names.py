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
  PN1 양방향 맞추기를 **쓴다**(`teamname.pick`)
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
    said = (ROOT / MOD).read_text(encoding="utf-8")
    tree = ast.parse(said)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == name)
    rows = said.splitlines()
    return "\n".join(rows[fn.lineno - 1:fn.end_lineno])


def test_pn1_uses_bidirectional_matcher() -> None:
    """PN1 — `teamname.pick` 을 쓴다(새 비교를 짓지 않는다)."""
    said = _body("prev_match_urls")
    assert "teamname" in said and ".pick(" in said, (
        "PN1 🔴 `core/teamname.pick` 을 안 쓴다 — `mentions_team` 만으로는 "
        "`('Feyenoord','Feyenoord Rotterdam')` 을 못 맞춘다(실측)")


def test_pn4_no_stray_continue() -> None:
    """PN4 🔴🔴 — `continue` 가 덤으로 남으면 **모든 팀을 거부한다**.

    ⚠️ 실사고 2026-10-15: 내가 치환할 때 옛 줄의 `continue` 가 하나 남아
       이름이 맞아도 그 아래로 못 가게 됐다. 바꾼 줄을 **출력해 보고서야** 잡았다
       (규율 #8). 🔴 그 꼴을 기계가 막는다.
    """
    said = _body("prev_match_urls")
    i = said.find("pick(")
    assert i > 0, "PN4 🔴 `pick(` 을 못 찾았다"
    tail = said[i:i + 260]
    # 🔴 `pick` 뒤의 `continue` 는 **하나**여야 한다(그 if 의 몸통)
    assert tail.count("continue") == 1, (
        f"PN4 🔴🔴 `pick` 뒤에 `continue` 가 {tail.count('continue')}개다 — "
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
