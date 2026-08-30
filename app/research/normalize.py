"""자유서술 픽 문자열 → 정규 포맷 변환.

정규 포맷 (grader와 공유):
  h2h:<팀명>  |  spreads:<팀명>:<라인>  |  totals:Over|Under:<라인>
"""

import re


def canonical_pick(market: str, side: str | None, line: float | None = None) -> str:
    """보드·DB에 넣는 픽 키."""
    if line is not None:
        return f"{market}:{side}:{line:g}"
    return f"{market}:{side}"


def match_team(token: str, home: str, away: str) -> str | None:
    t = token.lower().strip()
    if not t:
        return None
    raw = token.strip()
    from app.bot.aliases import kr_team

    for team in (home, away):
        if t in team.lower() or team.lower() in t:
            return team
        kr = kr_team(team)
        if kr and (kr in raw or raw in kr):
            return team
    return None


def normalize_pick(text: str, home: str, away: str) -> str | None:
    s = (text or "").strip()
    if not s:
        return None
    if s.startswith(("h2h:", "dc:", "totals:", "spreads:", "f5:")):
        return s
    m = re.search(r"(오버|언더|over|under)\s*(\d+(?:\.\d+)?)", s, re.I)
    if m:
        side = "Over" if re.search(r"오버|\bover\b", m.group(1), re.I) else "Under"
        return f"totals:{side}:{m.group(2)}"
    m = re.search(r"^(.+?)\s*런라인\s*([+-]?\d+(?:\.\d+)?)$", s)
    if m:
        team = match_team(m.group(1), home, away)
        if team:
            return f"spreads:{team}:{m.group(2)}"
    m = re.search(r"^(.*?)\s*([+-]\d+(?:\.\d+)?)$", s)
    if m:
        team = match_team(m.group(1), home, away)
        if team:
            return f"spreads:{team}:{m.group(2)}"
    if "F5" in s:
        return None
    m = re.search(r"^(.+?)\s*승$", s)
    if m:
        team = match_team(m.group(1), home, away)
        if team:
            return f"h2h:{team}"
    team = match_team(re.sub(r"\bML\b|\bmoneyline\b", "", s, flags=re.I), home, away)
    if team:
        return f"h2h:{team}"
    return None
