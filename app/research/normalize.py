"""자유서술 픽 문자열 → 정규 포맷 변환.

정규 포맷 (grader와 공유):
  h2h:<팀명>  |  spreads:<팀명>:<라인>  |  totals:Over|Under:<라인>
"""

import re


def match_team(token: str, home: str, away: str) -> str | None:
    t = token.lower().strip()
    if not t:
        return None
    for team in (home, away):
        if t in team.lower() or team.lower() in t:
            return team
    return None


def normalize_pick(text: str, home: str, away: str) -> str | None:
    s = text.strip()
    m = re.search(r"\b(over|under)\s+(\d+(?:\.\d+)?)", s, re.I)
    if m:
        return f"totals:{m.group(1).title()}:{m.group(2)}"
    m = re.search(r"^(.*?)\s*([+-]\d+(?:\.\d+)?)$", s)
    if m:
        team = match_team(m.group(1), home, away)
        if team:
            return f"spreads:{team}:{m.group(2)}"
    team = match_team(re.sub(r"\bML\b|\bmoneyline\b", "", s, flags=re.I), home, away)
    if team:
        return f"h2h:{team}"
    return None
