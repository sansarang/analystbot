"""[§9-라인업 전적] NPB Yahoo `/top` 打順 백필 — 라이브 HTTP 없음."""
from datetime import date

from app.collectors.npb_boxscore import backfill

def _tbl(rows):
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table>{body}</table>"


def _dasen(rows):
    body = [["打順", "位置", "選手名"]]
    body += [[str(i), p, n] for i, (n, p) in enumerate(rows, 1)]
    return _tbl(body)


_CL9 = [
    ("山田 哲人", "捕"), ("塩見 泰隆", "中"), ("村上 宗隆", "三"),
    ("サンタナ", "右"), ("オスナ", "一"), ("西川 輝矢", "左"),
    ("長岡 秀樹", "遊"), ("山野 太一", "投"), ("山崎 晃大朗", "二"),
]
_PL9 = [
    ("藤原 恭大", "中"), ("藤岡 裕大", "遊"), ("ソト", "一"),
    ("山口 航輝", "左"), ("ポランコ", "右"), ("安田 尚憲", "三"),
    ("佐藤 都志也", "捕"), ("茶谷 健太", "二"), ("石川 慎吾", "指"),
]

_DAY = '''
<div id="gm_card">
  <a href="/npb/game/2021039331/index">神宮 ヤクルト 巨人 6 - 8 試合終了</a>
</div>
<div id="week_table">
  <a href="/npb/game/2021039200/index">ZOZOマリン ロッテ ソフトバンク 3 - 1 試合終了</a>
</div>
'''
_GAME = _dasen(_CL9) + _dasen(_PL9)


class _Client:
    def __init__(self):
        self.games = []

    async def schedule(self, day):
        if day == "2026-08-26":
            return _DAY
        return '<div id="gm_card"></div>'

    async def game(self, gid):
        self.games.append(gid)
        if gid == "2021039200":
            raise AssertionError("주간 표 경기를 오늘 날짜로 조회하면 안 된다")
        return _GAME


class _Pool:
    def __init__(self, ext_id_hit=True):
        self.ext_id_hit = ext_id_hit
        self.find = []

    async def fetchval(self, sql, *a):
        if "ext_id" in sql:
            return 42 if self.ext_id_hit else None
        self.find.append(a)
        return 42


async def test_backfill_records_boxscore_source(monkeypatch):
    recorded = []

    async def fake_record(pool, gid, side, team, order, source="crawler", **_):
        recorded.append((source, side, team, gid, order))
        return True

    monkeypatch.setattr("app.collectors.lineup_history.record", fake_record)
    client = _Client()
    stats = await backfill(_Pool(), as_of=date(2026, 8, 26), days=1,
                           limit_per_team=10, client=client)
    assert stats["games"] == 1 and stats["rows"] == 2
    assert client.games == ["2021039331"]
    assert {r[0] for r in recorded} == {"boxscore"}
    home = next(r for r in recorded if r[1] == "home")
    assert home[2] == "Tokyo Yakult Swallows"
    assert len(home[4]) == 9
    assert any(x.endswith("(投)") for x in home[4])


async def test_backfill_matches_by_teams_not_date_only(monkeypatch):
    """같은 날 6경기 중 아무거나 잡히면 남의 타순이 평소가 된다."""
    async def fake_record(pool, gid, side, team, order, source="crawler", **_):
        return True

    monkeypatch.setattr("app.collectors.lineup_history.record", fake_record)
    pool = _Pool(ext_id_hit=False)
    await backfill(pool, as_of=date(2026, 8, 26), days=1,
                   limit_per_team=10, client=_Client())
    assert pool.find, "ext_id 미스 시 _FIND로 홈/원정 매칭해야 한다"
    sport, home, away, _starts, window = pool.find[0]
    assert sport == "npb" and window == 20
    assert home == "Tokyo Yakult Swallows"
    assert away == "Yomiuri Giants"


async def test_in_progress_is_not_backfilled():
    class Live:
        async def schedule(self, day):
            return '''<div id="gm_card">
              <a href="/npb/game/1/index">横浜 DeNA 中日 0 - 0 試合中</a>
            </div>'''

        async def game(self, gid):
            raise AssertionError("진행 중 경기를 백필하면 오늘 타순이 이력에 샌다")

    stats = await backfill(_Pool(), as_of=date(2026, 8, 28), days=1,
                           limit_per_team=10, client=Live())
    assert stats["games"] == 0
