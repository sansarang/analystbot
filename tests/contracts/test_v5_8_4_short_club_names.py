"""🔴🔴 **공식 API 가 주는 짧은 이름을 흘리지 않는다** — §8-4 · §4-1.

══════════════════════════════════════════════════════════════════
🔴 왜 이 계약이 생겼나 — 실측 2026-10-04 (게이트 2 · MLB)
══════════════════════════════════════════════════════════════════

깔때기의 가장 큰 폐기가 **검색어 거부**였다:

```
queries 탈락: query_too_bare 26        ← 에이전트 질의의 **절반**
```

까닭을 좁혔다 — **이름표에 짧은 이름이 없다**:

```
_names_of_key("team:000338") → ['Milwaukee Brewers', '밀워키 브루어스']
                                🔴 'Brewers' 가 **없다**

'Brewers Padres NLDS Game 1 2026 MLB.com recap' → (1, ['team']) → 🔴 거부
  ✅ 짧은 이름이 들어오면 team + opponent + competition = 3 → 통과
```

🔴 공식 API 는 **이미 주고 있다**(`teamName`·`clubName`) — 우리가 `name` 하나만
받아 흘렸다. ⚠️ `fdorg` 쪽은 같은 파일에서 `name`+`shortName` 을 **둘 다** 받는다
— **같은 모양의 구멍이 한쪽만 메워져** 있었다.

══════════════════════════════════════════════════════════════════
🔴 막는 것은 *증상*이 아니라 **모양**이다 (§11-1)
══════════════════════════════════════════════════════════════════

증상은 *"`Brewers` 가 없다"* 다. 🔴 모양은 **"공식 응답이 들고 있는 팀 표기를
꼴 함수가 버린다"** 다. 그래서 이 계약은 `Brewers` 를 찾지 않고 **고정물 응답이
들고 있는 표기가 결과에 다 들어왔나**를 본다.

⚠️ `abbreviation`(`SD`·`PIT`)은 **일부러 뺀다** — `fdorg` 의 `tla` 를 뺀 까닭과
   같다(세 글자가 다른 리그 팀과 부딪친다 · `league_index.py` 가 그 사유를
   적어 두었다). 🔴 그 사실도 계약이 든다(넣으면 빨개진다).
"""
from __future__ import annotations

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures" / "statsapi_teams_2026-10-04.json"


@pytest.fixture(autouse=True)
def _clean_globals():
    """🔴🔴 **전역을 치운다** — `_EXT_IDS` 는 프로세스 전역이다.

    ⚠️ 실측: 이 파일은 **혼자 돌면 통과하고 전체 스위트에서 빨갰다.** 까닭은
       다른 시험(그리고 이 파일의 배선 시험)이 `_EXT_IDS["padres"]` 에 남을
       것을 넣어, 꼴 함수가 *"부딪친다"* 로 **짧은 이름을 버렸기** 때문이다.
    🔴 그것은 코드 결함이 아니라 **시험이 남긴 쓰레기**다 — 운영에서는
       `build()` 가 한 번 돌고 같은 리그면 같은 id 라 부딪치지 않는다.
    ⚠️ 그래도 **조용히 넘기지 않는다** — 치우는 자리를 한 곳에 둔다.
    """
    from app import league_index as LI
    before_e, before_d = dict(LI._EXT_IDS), list(LI._SHORT_DROPPED)
    LI._EXT_IDS.clear(); LI._SHORT_DROPPED.clear()
    yield
    LI._EXT_IDS.clear(); LI._EXT_IDS.update(before_e)
    LI._SHORT_DROPPED[:] = before_d


def _body() -> dict:
    return json.loads(FIX.read_text(encoding="utf-8"))


def test_v5_8_4_고정물이_실제로_받은_것이다():
    """🔴 지어낸 모양으로 계약을 세우지 않는다 — 출처와 날짜가 적혀 있어야 한다."""
    box = _body()
    assert box["_출처"].startswith("https://statsapi.mlb.com/")
    assert box["_받은날"] == "2026-10-04"
    assert len(box["teams"]) >= 3


def test_v5_8_4_꼴_함수가_짧은_이름을_안_버린다():
    """🔴🔴 **모양을 막는다** — 응답이 들고 있는 표기가 결과에 다 들어와야 한다.

    ⚠️ `name` 하나만 받으면 빨개진다(그것이 게이트 2 에서 다친 자리다).
    """
    from app import league_index as LI
    got = {str(x) for x in LI._SHAPES["mlb"](_body())}
    for row in _body()["teams"]:
        for field in ("name", "teamName", "clubName"):
            want = str(row.get(field) or "")
            assert want in got, (
                f"🔴 공식 응답의 `{field}` = `{want}` 를 **버렸다** — "
                f"`_SHAPES['mlb']` 가 낸 것: {sorted(got)}")


def test_v5_8_4_약어는_안_담는다():
    """🔴 `SD`·`PIT` 는 **담지 않는다** — `fdorg` 의 `tla` 를 뺀 까닭과 같다."""
    from app import league_index as LI
    got = {str(x) for x in LI._SHAPES["mlb"](_body())}
    for row in _body()["teams"]:
        for field in ("abbreviation", "teamCode"):
            bad = str(row.get(field) or "")
            assert bad not in got, (
                f"🔴 세 글자 약어 `{bad}`({field}) 를 담았다 — 다른 리그 팀과 "
                f"부딪친다(`league_index.py` 가 `tla` 를 뺀 그 까닭이다)")


def test_v5_8_4_같은_팀의_표기들이_한_팀으로_묶인다():
    """🔴🔴 **두 표기가 두 팀이 되면 안 된다**(실측 2026-10-03 교토 사고).

    ⚠️ `fdorg` 가 이미 그렇게 한다 — 같은 `id` 를 단 표기를 `_EXT_IDS` 로
       묶으면 `teamref._from_league_index` 가 한 열쇠로 합친다.
    🔴 묶지 않으면 `San Diego Padres` 와 `Padres` 가 **다른 두 팀**이 된다.
    """
    from app import league_index as LI
    LI._EXT_IDS.clear()
    LI._SHAPES["mlb"](_body())
    for row in _body()["teams"]:
        # ⚠️ **`None` 을 버리지 않는다** — 처음 그렇게 짰고, 짧은 이름에 id 를
        #    안 달아도 `name` 하나만 남아 `len == 1` 로 **통과했다**(M64).
        #    🔴 못 묶인 표기는 `None` 으로 **드러나야** 한다.
        ids = {LI._EXT_IDS.get(LI.norm(str(row.get(f) or "")))
               for f in ("name", "teamName", "clubName") if row.get(f)}
        assert None not in ids, (
            f"🔴 `{row['name']}` 의 표기 중 **외부 id 가 안 달린 것**이 있다 — "
            f"그 표기는 **다른 팀**이 된다(교토 사고와 같은 모양)")
        assert len(ids) == 1, (
            f"🔴 `{row['name']}` 의 표기들이 **같은 외부 id 로 묶이지 않았다**: "
            f"{ids} — 두 팀이 된다(교토 사고와 같은 모양)")
        assert ids == {f"mlb:{row['id']}"}, ids




def test_v5_8_4_부딪치는_짧은_이름은_버리고_사유를_남긴다():
    """🔴🔴 **그냥 넣으면 거짓 귀속을 만든다** — 부딪치면 버린다.

    ⚠️ `Giants` 는 SF·요미우리·롯데가 다 쓰고 `Tigers` 는 디트로이트·한신·기아가
       쓴다. 🔴 영어 기사 속 `Tigers` 를 디트로이트로 **귀속**하면 그것은
       0건보다 나쁘다(거짓 변수를 만든다 · `config/entities.yaml` 머리글).
    🔴 CLAUDE.md 가 같은 사고를 적어 뒀다 — *"맨이름 `롯데` 는 넣지 않는다"*.

    ⚠️ **조용히 버리지 않는다**(#3) — 버린 이름을 사유로 센다.
    """
    from app import league_index as LI
    drop, why = LI.short_name_ok("Tigers", mine="mlb:116",
                                 taken={"tigers": "npb:hanshin"})
    assert drop is False
    assert "Tigers" in why and "부딪" in why, why
    # ✅ 아무도 안 쓰는 짧은 이름은 들어간다
    ok, why2 = LI.short_name_ok("Padres", mine="mlb:135", taken={})
    assert ok is True, why2
    # 🔴 **제 팀이 이미 쓰는 것**은 부딪친 것이 아니다
    ok2, _ = LI.short_name_ok("Padres", mine="mlb:135",
                              taken={"padres": "mlb:135"})
    assert ok2 is True


def test_v5_8_4_버린_이름이_사유에_남는다():
    """🔴🔴 **배선**(CLAUDE.md #2) — 만든 문은 **부르는 곳**이 있어야 한다.

    ⚠️ `short_name_ok` 를 짓고 끝내면 버린 사실이 **아무 데도 안 남는다**.
       🔴 그러면 다음 세션이 *"왜 `Tigers` 가 없나"* 를 물을 때 답이 없다(#3).
    """
    import asyncio
    import inspect

    from app import league_index as LI
    # 🔴 **사유를 엮는 코드가 `teams_of` 안에 있나** — 글자로 확인한다
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(LI.teams_of))
    assert "_SHORT_DROPPED" in body, (
        "🔴 `teams_of` 가 버린 짧은 이름을 **사유로 엮지 않는다** — "
        "안 이어진 코드는 없는 코드보다 나쁘다(#2)")

    # 🔴 그리고 **실제로 글에 들어오나** — 꼴 함수를 부딪치게 만들어 본다
    LI._EXT_IDS.clear(); LI._SHORT_DROPPED.clear()
    LI._EXT_IDS["padres"] = "npb:somebodyelse"       # ⚠️ 남이 먼저 쓴 꼴
    LI._SHAPES["mlb"](_body())
    assert LI._SHORT_DROPPED, "🔴 부딪쳤는데 **버린 기록이 없다**"
    assert any("Padres" in x for x in LI._SHORT_DROPPED), LI._SHORT_DROPPED

    async def _go():
        got, why = await LI.roster_from("url:x|mlb", net=_Net())
        return got, why

    class _Net:
        async def get(self, url, **kw):
            class R:
                ok = True
                text = json.dumps(_body(), ensure_ascii=False)
            return R()

    LI._EXT_IDS.clear(); LI._SHORT_DROPPED.clear()
    got, why = asyncio.run(_go())
    # ✅ 아무도 안 쓰는 상태에서는 짧은 이름이 **다 들어온다**
    assert "Brewers" in got and "Padres" in got, got

    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **사유에 글자가 들어오나** — 글자 검사로는 M66 이 통과했다
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 처음엔 `teams_of` 소스에 `_SHORT_DROPPED` 가 있나만 봤다. 🔴 그래서
    #     `dropped = []` 로 바꿔도 **통과했다**(§9-5 가 무효로 보는 꼴).
    #  🔴 이제 **부딪치게 만들고 그 사유가 돌아오나**를 본다.
    async def _collide():
        LI._EXT_IDS.clear(); LI._SHORT_DROPPED.clear()
        LI._EXT_IDS["padres"] = "npb:somebodyelse"   # ⚠️ 남이 먼저 쓴 꼴
        LI._EXT_IDS["brewers"] = "npb:somebodyelse"
        return await LI.teams_of("MLB", net=_Net())

    import json as _json
    import tempfile
    old_path = LI._cache_path
    try:
        # 🔴 **진짜 캐시를 건드리지 않는다** — 임시 자리로 돌린다
        tmp = pathlib.Path(tempfile.mkdtemp()) / "mlb.json"
        LI._cache_path = lambda key: tmp
        names, said = asyncio.run(_collide())
    finally:
        LI._cache_path = old_path
    assert "Padres" not in names and "Brewers" not in names, names
    assert "버렸다" in said, (
        f"🔴 짧은 이름을 버렸는데 **사유가 조용하다**(#3): {said}")
    assert "Padres" in said or "Brewers" in said, said
    # 🔴 그리고 캐시에 **이름마다의 출처**가 적혀 있나
    box = _json.loads(tmp.read_text(encoding="utf-8"))
    assert box.get("by"), "🔴 캐시가 이름마다의 출처를 안 적었다"
    assert box.get("stamp"), "🔴 캐시에 **도장**이 없다"
