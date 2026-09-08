"""[BAT-5] 분기점 해결사에 **개별 타자**를 더한다.

🔴 **왜 (실측 2026-09-07~08).** 기록형 변수의 해결사가 전부 투수 쪽이었다 —
   불펜 42.9% · 선발 30% · 타선 9%, 그리고 타선 해결사조차 **팀 단위**
   (`offense_outlook`)라 "이 타자가 살아나는가" 에는 답할 도구가 없었다.
   그래서 개별 타자 질문은 팀 득점 회귀로 바꿔치기되거나
   `사유: 질문에서 대상 선발을 특정하지 못했다` 로 끝났다.

⚠️ **투수 질문을 빼앗지 않는다.** BRR-1·BRR-2·BRR-3 이 고친 자리 바로 옆이다.
   오늘 타순에 있는 이름일 때만, 그리고 그 이름이 오늘 선발투수가 아닐 때만
   타자 해결사로 간다.
"""
from __future__ import annotations

from datetime import UTC, datetime


class _Pool:
    def __init__(self, own=(), peers=None, fail=False):
        self.own, self.peers, self.fail = list(own), peers, fail
        self.sql = []

    async def fetch(self, sql, *a):
        self.sql.append(sql)
        if self.fail:
            raise RuntimeError("DB")
        # 투수표를 묻는 쿼리에 타자 행을 돌려주지 않는다 — 하네스가 거짓말하면
        # 테스트가 통과해도 아무것도 증명하지 못한다.
        return [] if "pitcher_appearances" in sql else self.own

    async def fetchrow(self, sql, *a):
        self.sql.append(sql)
        if self.fail:
            raise RuntimeError("DB")
        return self.peers


def _jg():
    return {
        "sport": "kbo", "home": "LG Twins", "away": "Doosan Bears",
        "starts_at": datetime(2026, 9, 8, 9, 0, tzinfo=UTC),
        "home_pitcher": "손주영", "away_pitcher": "곽빈",
        "research": {"today_nine": {
            "home": {"order": [{"slot": 1, "name": "홍창기", "pos": "우익수"},
                               {"slot": 2, "name": "신민재", "pos": "2루수"}]},
            "away": {"order": [{"slot": 1, "name": "정수빈", "pos": "중견수"}]}}},
    }


def _own(n=5):
    return [{"d": "2026-09-0%d" % (i + 1), "ab": 4, "h": 1, "hr": 0,
             "rbi": 1, "r": 0, "bb": 0, "so": 1, "opponent": "상대"}
            for i in range(n)]


async def test_타자_이름이면_타자_해결사로_간다():
    from app.engine.branch_resolve import resolve

    pool = _Pool(own=_own(), peers={"n": 120, "next_avg": 0.271, "next_h": 1.02})
    out = await resolve(pool, _jg(), "홍창기가 최근 침체에서 반등하는가")
    from app.engine.branch_resolve import RECORD

    assert out["유형"] == RECORD
    ans = (out.get("답") or {}).get("타자") or {}
    assert "본인" in ans, out
    assert ans["본인"]["경기"] == 5 and ans["본인"]["타수"] == 20
    assert ans["같은처지"]["표본"] == 120


async def test_투수_질문을_빼앗지_않는다():
    """⚠️ BRR-1·2·3 이 고친 자리다 — 타자 해결사가 다시 가로채면 안 된다."""
    from app.engine.branch_resolve import resolve

    pool = _Pool(own=_own(), peers={"n": 5, "ip": 5.1, "deep": 1})
    out = await resolve(pool, _jg(),
                        "손주영이 5이닝 이상을 소화하며 버텨주는가")
    assert "타자" not in (out.get("답") or {}), out


async def test_타순에_없는_이름은_타자로_보지_않는다():
    """오늘 뛰지 않는 사람의 기록을 답으로 내면 그것은 다른 경기의 사실이다."""
    from app.engine.branch_resolve import resolve

    pool = _Pool(own=_own(), peers=None)
    out = await resolve(pool, _jg(), "김현수가 반등하는가")
    assert "타자" not in (out.get("답") or {}), out


async def test_표본이_없으면_사유를_적는다():
    """조용히 빠지지 않는다 — 답이 없으면 왜 없는지 남긴다."""
    from app.engine.branch_resolve import resolve

    out = await resolve(_Pool(own=[], peers=None), _jg(),
                        "홍창기가 반등하는가")
    assert not out.get("답")
    assert out.get("사유"), out


async def test_창은_최근_5경기다():
    """대원칙: 최근 3~5경기만. 창 길이는 `batter_recent` 가 원본이다."""
    from app.engine import batter_recent, branch_resolve

    pool = _Pool(own=_own(), peers=None)
    await branch_resolve.batter_outlook(pool, "kbo", "홍창기",
                                        datetime(2026, 9, 8, tzinfo=UTC))
    assert batter_recent.RECENT_GAMES <= 5


async def test_조회_실패는_판정을_막지_않는다():
    from app.engine.branch_resolve import batter_outlook

    got = await batter_outlook(_Pool(fail=True), "kbo", "홍창기",
                               datetime(2026, 9, 8, tzinfo=UTC))
    assert got == {}


async def test_카드에_타자_답이_실린다():
    """🔴 "물음표는 없어야 한다" — 답을 찾아 놓고 질문만 내보내지 않는다."""
    from app.engine.card import branch_lines

    verdict = {"전개": {"분기점": "홍창기가 반등하는가"}}
    probe = {"항목": [{"질문": "홍창기가 반등하는가",
             "답": {"타자": {
                 "본인": {"경기": 5, "타수": 20, "안타": 6, "홈런": 1,
                          "타석": [{"날짜": "2026-09-07", "타수": 4, "안타": 2}]},
                 "같은처지": {"표본": 120, "다음경기_평균타율": 0.271}}}}]}
    out = "\n".join(branch_lines(verdict, probe))
    assert "본인 최근 5경기 20타수 6안타 1홈런" in out, out
    assert "0.271" in out and "120" in out, out


async def test_타자_이름이_든_투수_질문을_빼앗지_않는다():
    """🔴 가장 위험한 형태다 — 타자 이름이 있지만 묻는 것은 투수 결과다.

    "손주영이 정수빈을 상대로 버티는가" 에서 `정수빈` 은 오늘 타순에 있고
    선발도 아니다. 이름만 보면 타자 질문처럼 보인다.
    """
    from app.engine.branch_resolve import resolve

    pool = _Pool(own=_own(), peers=None)
    out = await resolve(pool, _jg(), "손주영이 정수빈을 상대로 5이닝을 버티는가")
    assert "타자" not in (out.get("답") or {}), out


async def test_불펜_질문도_빼앗지_않는다():
    from app.engine.branch_resolve import resolve

    pool = _Pool(own=_own(), peers=None)
    out = await resolve(pool, _jg(), "홍창기 타석에서 홈 불펜이 조기 가동되는가")
    assert "타자" not in (out.get("답") or {}), out
