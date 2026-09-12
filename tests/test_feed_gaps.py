"""SRCH-8 — 크롤러가 가져온 것을 DB 페이로드도 보게 한다. 그리고 못 채운
   DB 요청은 검색으로 넘긴다.

사용자 지시 2026-09-12: "재요청, 오늘 타순 불펜 폼까지 수정해라"

🔴 실측 2026-09-12 (운영 파이프라인 · ORDER_V3=1):

     [dbref] 있음 3 · 본것 ['오늘 타순']
     없음: 최근 3경기 박스스코어 · 불펜 최근 폼과 가용성 · 실력 레이팅 · …
     조사 결과: 원정/홈 선발 예고 · 16:08 라인업 변경     ← **타순 줄이 없다**

   같은 사실이 **두 갈래로 갈라져 있었다.**

   ① 타순 — 크롤러 스냅샷에 `lineup_home`/`lineup_away` 가 들어 있고,
      `lineups_payload` 에는 그것을 읽는 **폴백이 이미 있다**
      (`jg["lineup_{side}"]`). 그런데 `gather.enrich` 가 선발 이름만 채우고
      타순은 안 채워서 그 폴백이 영영 안 걸렸다.
   ② 불펜 — `gather._bullpen` 이 `pitcher_appearances` 에서 연투까지 읽어
      **문장으로만** 쓰고 버린다. `bullpen_payload` 는 `research` 를 보므로
      계속 `없음` 이다.
   ③ 2단계가 `DB요청: 불펜 최근 폼과 가용성` 을 냈는데 DB에 없으면
      **조용히 버려졌다.** 검색으로 넘길 길이 없었다.

⚠️ 반대 위험: 크롤러 값으로 **멀쩡한 값을 덮으면** 더 나쁘다.
   `enrich` 의 기존 규약대로 **비어 있을 때만** 채운다.
"""

import asyncio

import pytest

from app.engine import gather as G
from app.engine import matchup as MU


def _jg(**kw):
    jg = {"game_id": 1, "sport": "kbo", "league": "KBO",
          "home": "Doosan Bears", "away": "NC Dinos"}
    jg.update(kw)
    return jg


class _Redis:
    async def get(self, k):
        return None


# ═══════════════ ① 타순 — 크롤러 값을 jg 에 채운다

@pytest.mark.asyncio
async def test_크롤러_타순을_jg에_채운다(monkeypatch):
    """🔴 `lineups_payload` 폴백이 `jg["lineup_{side}"]` 를 읽는다 —
    그 칸을 아무도 안 채워서 폴백이 영영 안 걸렸다."""
    snap = {"lineup_home": "박찬호(유격수)-안재석(3루수)-박준순(2루수)",
            "lineup_away": "김주원(유격수)-권희동(좌익수)-블레인(1루수)",
            "home_pitcher": "잭로그", "away_pitcher": "구창모"}
    monkeypatch.setattr("app.collectors.crawler_feed.load_snapshot",
                        _async(lambda *a, **k: {}))
    monkeypatch.setattr("app.collectors.crawler_feed.snapshot_for_game",
                        lambda *a, **k: snap)
    jg = _jg()
    await G.enrich(jg, _Redis(), "2026-09-12")
    assert jg["lineup_home"].startswith("박찬호")
    assert jg["lineup_away"].startswith("김주원")


@pytest.mark.asyncio
async def test_이미_있는_타순을_덮지_않는다(monkeypatch):
    """🔴 반대 위험 — 멀쩡한 값을 크롤러로 덮으면 더 나쁘다.
    `enrich` 의 기존 규약(비었을 때만)을 그대로 따른다."""
    monkeypatch.setattr("app.collectors.crawler_feed.load_snapshot",
                        _async(lambda *a, **k: {}))
    monkeypatch.setattr("app.collectors.crawler_feed.snapshot_for_game",
                        lambda *a, **k: {"lineup_home": "크롤러값"})
    jg = _jg(lineup_home="원래값")
    await G.enrich(jg, _Redis(), "2026-09-12")
    assert jg["lineup_home"] == "원래값"


def test_타순이_채워지면_페이로드가_산다():
    """🔴 배선 확인 — `lineups_payload` 의 폴백이 실제로 걸린다."""
    jg = _jg(lineup_home="박찬호(유격수)-안재석(3루수)-박준순(2루수)")
    out = MU.lineups_payload(jg)
    order = (out.get("home") or {}).get("타순") or []
    assert len(order) == 3
    assert order[0]["이름"] == "박찬호" and order[0]["타순"] == 1


# ═══════════════ ② 불펜 — 읽은 것을 research 에 남긴다

@pytest.mark.asyncio
async def test_불펜_기록을_research에_남긴다(monkeypatch):
    """🔴 `pitcher_appearances` 에서 연투까지 읽어 놓고 문장으로만 쓰고
    버렸다. `bullpen_payload` 는 `research` 를 보므로 계속 `없음` 이었다."""
    data = {"투수": [{"이름": "김택연", "날짜": [], "연투": True,
                      "이닝": 2.33, "타자": 7}], "마지막적재": None}

    async def _recent(pool, sport, team, **k):
        return data

    monkeypatch.setattr("app.collectors.bullpen_usage.recent", _recent)
    monkeypatch.setattr("app.collectors.bullpen_usage.to_answer",
                        lambda team, d, **k: f"{team} 한 줄")
    jg = _jg()
    await G._bullpen(None, jg)
    r = jg.get("research") or {}
    assert (r.get("home_bullpen") or {}).get("최근") == data
    assert (r.get("away_bullpen") or {}).get("최근") == data


@pytest.mark.asyncio
async def test_기존_불펜_값을_덮지_않는다(monkeypatch):
    """🔴 `era` 는 스탯 수집기가 채운다 — 그 칸을 지우면 안 된다."""
    async def _recent(pool, sport, team, **k):
        return {"투수": [{"이름": "x"}], "마지막적재": None}

    monkeypatch.setattr("app.collectors.bullpen_usage.recent", _recent)
    monkeypatch.setattr("app.collectors.bullpen_usage.to_answer",
                        lambda team, d, **k: "한 줄")
    jg = _jg(research={"home_bullpen": {"era": 3.21}})
    await G._bullpen(None, jg)
    blk = jg["research"]["home_bullpen"]
    assert blk["era"] == 3.21 and "최근" in blk


@pytest.mark.asyncio
async def test_기록이_없으면_빈_칸을_만들지_않는다(monkeypatch):
    """🔴 빈 칸을 만들면 `bundle` 이 "있음"으로 센다 — 모르는 것이 아는 것이 된다."""
    async def _recent(pool, sport, team, **k):
        return {"투수": [], "마지막적재": None}

    monkeypatch.setattr("app.collectors.bullpen_usage.recent", _recent)
    monkeypatch.setattr("app.collectors.bullpen_usage.to_answer",
                        lambda team, d, **k: "")
    jg = _jg()
    await G._bullpen(None, jg)
    assert not (jg.get("research") or {}).get("home_bullpen")


def test_불펜_페이로드가_최근을_싣는다():
    jg = _jg(research={"home_bullpen": {"최근": {"투수": [{"이름": "김택연"}]}},
                       "away_bullpen": {"era": 4.0}})
    out = MU.bullpen_payload(jg)
    assert out["home"]["최근"]["투수"][0]["이름"] == "김택연"


# ═══════════════ ③ 못 채운 DB 요청을 검색으로 넘긴다

def test_DB로_못_채운_요청이_검색으로_간다():
    """🔴 실측: 2단계가 `DB요청: 불펜 최근 폼과 가용성` 을 냈는데 DB에 없어
    **조용히 버려졌다.** 사용자 지시: "없으면 안트로픽이나 퍼플릭스한테
    요청을 해서 받으라고 해야 한다"."""
    import inspect

    src = inspect.getsource(MU._judge_v3)
    i = src.index("verdict.decide")
    head = src[:i]
    assert "with_miss=True" in head, "판정 앞 DB 보충이 못 채운 것을 안 센다"
    assert "search" in head, "못 채운 요청이 검색으로 가지 않는다"


def test_검색은_여전히_경기당_한_라운드다():
    """🔴 보충이 늘었다고 유료 호출이 늘면 안 된다."""
    import inspect

    src = inspect.getsource(MU._judge_v3)
    assert src.count("gather.search") <= 2, "검색 라운드가 2회를 넘는다"


def test_보충_계측이_원장에_남는다():
    """🔴 조용한 0 금지 — "DB에 있었다"와 "검색으로 샀다"는 다르다."""
    import inspect

    src = inspect.getsource(MU._judge_v3)
    body = src[src.index('jg["order_v3"] = {'):]
    assert '"DB보충"' in body[:1200]
    assert "DB못채움" in body[:1200]


# ═══════════════ 보조

def _async(fn):
    async def _f(*a, **k):
        return fn(*a, **k)

    return _f
