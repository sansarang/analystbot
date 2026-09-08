"""[BAT-8] 분기점 타자 매칭이 `Jr.` 에 걸린다 — BAT-5 의 구멍.

🔴 **배포 전 재검토에서 실데이터로 나왔다(2026-09-09).** BAT-5 는 이름을
   못 찾으면 **마지막 토큰**으로 다시 찾는다(`_nm.split()[-1] in question`).
   운영 표본으로 그 토큰들을 세어 보니:

       mlb  타자 384명 · 투수와 같은 토큰 63 · **타자끼리 같은 토큰 28**
              충돌 토큰 'Jr.'  → BJ Murray Jr. · Bobby Witt Jr. · Fernando Tatis Jr.
              충돌 토큰 'Soto' → Juan Soto (투수 Soto 와도 겹친다)
       npb  타자 237명 · 투수와 같은 토큰 64 · 타자끼리 같은 토큰 12
       kbo  타자 181명 · 투수와 같은 토큰 3 · 타자끼리 0

   `Jr.` 는 **어떤 질문에도** 걸린다. 그리고 셋 중 누구를 고를지는 타순
   순서가 정한다 — 답이 질문과 무관한 선수의 기록이 된다. BRR-1·2·3 이
   고친 병("답이 질문과 다른 영역에서 왔다")과 같은 종류다.

⚠️ 반대 위험: 성만 적는 표기("Judge 가 살아나는가")는 실제로 흔하다. 성
   매칭을 통째로 없애면 그 질문이 다시 `사유` 로 끝난다. 그래서 **토큰이
   오늘 라인업 안에서 유일하고 투수와 겹치지 않을 때만** 허용한다.
"""
from __future__ import annotations

from datetime import UTC, datetime


class _Pool:
    def __init__(self, own=()):
        self.own = list(own)

    async def fetch(self, sql, *a):
        return [] if "pitcher_appearances" in sql else self.own

    async def fetchrow(self, sql, *a):
        return None


def _own(n=5):
    return [{"d": f"2026-09-0{i+1}", "opponent": "상대", "ab": 4, "h": 1,
             "hr": 0, "rbi": 1, "r": 0, "bb": 0, "so": 1} for i in range(n)]


def _jg(home_names, away_names=("Shohei Ohtani",), pitcher="Gregory Soto"):
    return {
        "sport": "mlb", "home": "H팀", "away": "A팀",
        "starts_at": datetime(2026, 9, 9, tzinfo=UTC),
        "home_pitcher": pitcher, "away_pitcher": "Zack Wheeler",
        "research": {"today_nine": {
            "home": {"order": [{"slot": i, "name": n, "pos": "DH"}
                               for i, n in enumerate(home_names, 1)]},
            "away": {"order": [{"slot": i, "name": n, "pos": "DH"}
                               for i, n in enumerate(away_names, 1)]}}},
    }


async def test_Jr_은_사람을_가리키지_않는다():
    """🔴 셋이 같은 토큰이면 그 토큰으로 사람을 고를 수 없다.

    ⚠️ 이 파일의 질문은 전부 **기록형으로 분류되는 문구**여야 한다. 처음에
       "장타가 터지는가"로 썼더니 `미분류`라 매칭까지 가지도 않고 통과했다 —
       엉뚱한 이유로 통과하는 테스트는 없는 테스트보다 나쁘다.
    """
    from app.engine.branch_resolve import RECORD, classify, resolve

    jg = _jg(["Bobby Witt Jr.", "Fernando Tatis Jr."])
    q = "Witt Jr. 가 최근 침체에서 반등하는가"
    assert classify(q) == RECORD, "질문이 기록형으로 분류되지 않으면 이 테스트는 무의미하다"
    out = await resolve(_Pool(_own()), jg, q)
    ans = (out.get("답") or {}).get("타자") or {}
    assert not ans, f"모호한 토큰으로 한 명을 골랐다: {out}"
    assert out.get("사유"), out


async def test_성이_투수와_겹치면_타자로_보지_않는다():
    """⚠️ 오늘 선발이 Gregory Soto 인데 'Soto' 로 Juan Soto 를 부르면 안 된다."""
    from app.engine.branch_resolve import resolve

    jg = _jg(["Juan Soto", "Aaron Judge"], pitcher="Gregory Soto")
    out = await resolve(_Pool(_own()), jg, "Soto 가 최근 침체에서 반등하는가")
    assert "타자" not in (out.get("답") or {}), out


async def test_유일한_성은_그대로_받는다():
    """⚠️ 반대 위험 — 성만 적는 표기는 흔하다. 유일하면 받아야 한다."""
    from app.engine.branch_resolve import resolve

    jg = _jg(["Aaron Judge", "Juan Soto"], pitcher="Zack Wheeler")
    out = await resolve(_Pool(_own()), jg, "Judge 가 최근 침체에서 반등하는가")
    ans = (out.get("답") or {}).get("타자") or {}
    assert ans.get("본인"), out
    assert "Judge" in ans["질문"], ans["질문"]


async def test_전체_이름은_모호해도_받는다():
    """이름을 다 적었으면 토큰 규칙과 무관하게 그 사람이다."""
    from app.engine.branch_resolve import resolve

    jg = _jg(["Bobby Witt Jr.", "Fernando Tatis Jr."])
    out = await resolve(_Pool(_own()), jg, "Bobby Witt Jr. 가 최근 침체에서 반등하는가")
    ans = (out.get("답") or {}).get("타자") or {}
    assert ans.get("본인"), out
    assert "Bobby Witt Jr." in ans["질문"]
