"""[BAT-4] 자료3 을 이름에서 **이름+숫자**로 바꾼다.

🔴 **왜 (실측 2026-09-08).** 판정이 타자에 대해 아는 것은 자료3 의 이름
   아홉 개뿐이었다. 프롬프트가 그 빈자리를 "순서가 곧 정보다"로 메웠고,
   그래서 라인업 확정은 **판정을 개선할 재료를 주지 않으면서 판정을 다시
   열게** 만들었다. 경기 단위 실측: 잠정 70.4%(27) vs 확정 51.5%(130).

⚠️ **대원칙**(`app/engine/CLAUDE.md`): 최근 3~5경기만. 시즌 누적 금지.
   여기서 주는 것은 **최근 5경기 창의 합계**이지 시즌 집계표가 아니다.

⚠️ 이름 일치율 실측 2026-09-08 (크롤러 타순 이름 ↔ 박스스코어 이름):
   KBO 79/80(98.8%) · NPB 36/36(100%) · MLB 240/241(99.6%).
   미스 둘은 이적(박찬호)·콜업(Walker Jenkins)이었다. 그래서 **팀이 아니라
   `sport`+이름으로 조회한다** — 이적한 선수의 이력을 버리지 않는다.
"""
from __future__ import annotations

from datetime import UTC, datetime


class _Pool:
    def __init__(self, rows_by_name=None, fail=False):
        self.rows_by_name = rows_by_name or {}
        self.fail = fail
        self.calls = []

    async def fetch(self, sql, *a):
        if self.fail:
            raise RuntimeError("DB 가 죽었다")
        self.calls.append(a)
        return self.rows_by_name.get(a[1], [])


def _row(**kw):
    base = {"starts_at": datetime(2026, 9, 6, tzinfo=UTC), "opponent": "상대",
            "ab": 4, "h": 1, "r": 0, "rbi": 0, "hr": 0, "bb": 0, "so": 1}
    base.update(kw)
    return base


def _jg(names_home, names_away=("갑", "을")):
    return {
        "sport": "kbo",
        "starts_at": datetime(2026, 9, 8, tzinfo=UTC),
        "research": {"today_nine": {
            "home": {"order": [{"slot": i, "name": n, "pos": "지"}
                               for i, n in enumerate(names_home, 1)]},
            "away": {"order": [{"slot": i, "name": n, "pos": "지"}
                               for i, n in enumerate(names_away, 1)]},
        }},
    }


async def test_최근_창의_합계를_붙인다():
    from app.engine.batter_recent import attach_batter_recent

    jg = _jg(["박해민", "오스틴"])
    pool = _Pool({"박해민": [_row(ab=4, h=2, rbi=1), _row(ab=3, h=0, so=2, bb=1)]})
    await attach_batter_recent(jg, pool)
    got = jg["research"]["home_batter_recent"]
    assert got["박해민"] == {"경기": 2, "타수": 7, "안타": 2, "홈런": 0,
                             "타점": 1, "득점": 0, "볼넷": 1, "삼진": 3}
    # 자료가 없는 선수는 **키를 만들지 않는다** — 0으로 채우면 부진으로 읽힌다
    assert "오스틴" not in got


async def test_타율을_계산해_주지_않는다():
    """'수치는 있는 그대로, 분석만 AI' — 파생 지표를 우리가 만들지 않는다."""
    from app.engine.batter_recent import attach_batter_recent

    jg = _jg(["박해민"])
    await attach_batter_recent(jg, _Pool({"박해민": [_row()]}))
    got = jg["research"]["home_batter_recent"]["박해민"]
    assert not any(k in got for k in ("타율", "OPS", "출루율", "장타율"))


async def test_시즌이_아니라_최근_5경기다():
    from app.engine import batter_recent

    jg = _jg(["박해민"])
    pool = _Pool({"박해민": [_row()]})
    await batter_recent.attach_batter_recent(jg, pool)
    assert pool.calls, "조회하지 않았다"
    sport, name, before, limit = pool.calls[0]
    assert sport == "kbo" and name == "박해민"
    assert limit == batter_recent.RECENT_GAMES <= 5, "대원칙: 최근 3~5경기만"
    assert before == jg["starts_at"], "경기 시작 전 기록만 봐야 한다"


async def test_조회_실패는_판정을_막지_않는다():
    from app.engine.batter_recent import attach_batter_recent

    jg = _jg(["박해민"])
    await attach_batter_recent(jg, _Pool(fail=True))
    assert jg["research"]["home_batter_recent"] == {}


async def test_풀이_없으면_빈_객체다():
    from app.engine.batter_recent import attach_batter_recent

    jg = _jg(["박해민"])
    await attach_batter_recent(jg, None)
    assert jg["research"]["home_batter_recent"] == {}
    assert jg["research"]["away_batter_recent"] == {}


async def test_자료3_에_숫자가_실린다():
    """🔴 새 자료 번호를 만들지 않는다 — 자료3 을 채운다."""
    from app.engine.matchup import lineups_payload

    jg = _jg(["박해민", "오스틴"])
    jg["research"]["home_batter_recent"] = {
        "박해민": {"경기": 5, "타수": 20, "안타": 6, "홈런": 1,
                   "타점": 3, "득점": 4, "볼넷": 2, "삼진": 5}}
    out = lineups_payload(jg)
    first, second = out["home"]["타순"]
    assert first["이름"] == "박해민" and first["최근5"]["안타"] == 6
    # 자료가 없는 선수에게 빈 칸을 만들지 않는다
    assert "최근5" not in second


async def test_타순_없으면_아무것도_안_한다():
    from app.engine.batter_recent import attach_batter_recent

    jg = {"sport": "kbo", "research": {}}
    await attach_batter_recent(jg, _Pool())
    assert jg["research"]["home_batter_recent"] == {}
