"""🔴🔴 **선언·꼴이 바뀌면 캐시가 죽는다** — §8-4.

══════════════════════════════════════════════════════════════════
🔴 왜 이 계약이 생겼나 — 실측 2026-10-04
══════════════════════════════════════════════════════════════════

`var/leagues/mlb.json` 을 열어 보니 **금지된 출처의 이름이 아직 서비스 중**이었다:

```
teams 40 | ext 20
why  공식 API `mlb` 30팀 · TheSportsDB `MLB` 10팀 🔴 **열 팀에서 잘린다**
```

⚠️ `config/leagues.yaml` 의 MLB 줄에는 **`url:` 하나뿐**이다 — tsdb 대체는
   §8-4 를 적용할 때 **걷어 냈다**(커밋에 그 사유가 있다). 🔴 그런데 캐시가
   **옛 선언으로 받은 것을 7일 동안 그대로 낸다.**

🔴 같은 병이 방금 또 났다: `_SHAPES["mlb"]` 를 고쳐 짧은 이름을 받게 했는데,
   캐시가 신선해서 **고친 꼴이 한 번도 안 불린다.**

══════════════════════════════════════════════════════════════════
🔴 막는 것은 **모양**이다 (§11-1)
══════════════════════════════════════════════════════════════════

증상은 *"tsdb 이름이 남아 있다"* · *"짧은 이름이 안 들어온다"* 로 둘이지만
모양은 하나다 — **캐시가 자기를 만든 선언·코드를 모른다.**

🔴 그래서 캐시에 **도장**(`stamp`)을 찍는다: `teams_from` 선언 + 그 꼴 함수의
   코드. 둘 중 하나라도 바뀌면 캐시는 **묵은 것**이다.
⚠️ 사람이 `rm -rf var/leagues` 를 기억하는 것에 기대지 않는다 — 기억은 언제나
   한 발 늦는다(CLAUDE.md #1 이 손으로 유지하는 목록을 금지한 그 까닭).
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_v5_8_4_도장이_선언과_꼴을_함께_든다():
    """🔴 선언만 보면 **꼴 함수를 고친 것**을 못 잡는다(방금 그 일이 났다)."""
    from app import league_index as LI
    a = LI.cache_stamp("MLB")
    assert a, "🔴 도장이 비었다"
    # 🔴 **선언이 바뀌면** 도장이 바뀐다
    #  ⚠️ `leagues()` 가 **매번 새로 읽는다** — 돌려받은 줄을 고쳐도 다음 호출에
    #     안 남는다(처음 그렇게 재서 빗나갔다). 그래서 **바꿔 끼운다.**
    rows = [dict(x) for x in LI.leagues()]
    for r in rows:
        if r.get("key") == "MLB":
            r["teams_from"] = [*(r.get("teams_from") or []), "fdorg:PL"]
    old_leagues = LI.leagues
    try:
        LI.leagues = lambda: rows
        assert LI.cache_stamp("MLB") != a, (
            "🔴 `teams_from` 을 바꿨는데 도장이 **그대로**다 — 묵은 캐시가 산다")
    finally:
        LI.leagues = old_leagues
    # 🔴 **꼴 함수가 바뀌면** 도장이 바뀐다
    old = LI._SHAPES["mlb"]
    try:
        LI._SHAPES["mlb"] = lambda d: ["다른 꼴"]
        assert LI.cache_stamp("MLB") != a, (
            "🔴 꼴 함수를 바꿨는데 도장이 **그대로**다 — 고친 꼴이 안 불린다")
    finally:
        LI._SHAPES["mlb"] = old


def test_v5_8_4_도장이_다르면_묵은_것이다():
    """🔴 `_fresh` 가 **도장을 본다** — 날짜만 보면 7일을 버틴다."""
    from app import league_index as LI
    p = LI._cache_path("MLB")
    if not p.exists():
        return                      # ⚠️ 캐시가 없으면 잴 것이 없다
    box = json.loads(p.read_text(encoding="utf-8"))
    said = str(box.get("stamp") or "")
    now = LI.cache_stamp("MLB")
    # 🔴 **도장이 없거나 다르면 `_fresh` 가 거짓**이어야 한다
    if said != now:
        assert LI._fresh(p, "MLB") is False, (
            f"🔴 도장이 다른데(`{said[:12]}` ≠ `{now[:12]}`) 캐시를 **신선하다**고 "
            f"했다 — 옛 선언으로 받은 이름이 계속 나온다")


def test_v5_8_4_저장할_때_도장을_찍는다():
    """🔴 찍지 않으면 다음 판에서 **또** 못 알아본다.

    ⚠️ 처음엔 소스에 `stamp` 라는 글자가 있나만 봤다 — 🔴 `"stamp_X"` 로
       바꿔도 **통과했다**(M69 · §9-5 가 무효로 보는 꼴). 이제 **찍은 캐시를
       다시 읽어 `_fresh` 가 신선하다고 하나**를 본다.
    """
    import asyncio
    import pathlib as _pl
    import tempfile

    from app import league_index as LI

    class _Net:
        async def get(self, url, **kw):
            class R:
                ok = True
                text = json.dumps(
                    {"teams": [{"id": 1, "name": "Milwaukee Brewers",
                                "teamName": "Brewers"}]}, ensure_ascii=False)
            return R()

    tmp = _pl.Path(tempfile.mkdtemp()) / "mlb.json"
    old = LI._cache_path
    try:
        LI._cache_path = lambda key: tmp
        LI._EXT_IDS.clear()
        asyncio.run(LI.teams_of("MLB", net=_Net()))
        # 🔴🔴 **방금 찍은 캐시는 신선해야** 한다 — 도장이 안 찍히면 거짓이다
        assert LI._fresh(tmp, "MLB") is True, (
            f"🔴 방금 저장한 캐시를 **묵은 것**이라고 한다 — 도장을 안 찍었다. "
            f"칸: {sorted(json.loads(tmp.read_text(encoding='utf-8')))}")
    finally:
        LI._cache_path = old


def test_v5_8_4_금지_출처_이름은_이름표에_안_들어간다():
    """🔴🔴 **§8-4 를 이름 하나 단위로** 지킨다 — 통째로 버리지 않는다.

    ⚠️ 실측 2026-10-04: `var/leagues/mlb.json` 이 *"공식 API 30팀 ·
       TheSportsDB 10팀"* 을 들고 7일을 버텼다. 🔴 `_fresh` 는 그것을 막지만
       `teamref._from_league_index` 는 **`_fresh` 를 안 본다** — 파일을 바로 읽는다.
    🔴 통째로 지우면 **공식 API 30팀까지 버린다**(과잉 교정). 그래서 캐시가
       이름마다 출처(`by`)를 적고, 금지 것만 걷는다.
    """
    from app import league_index as LI
    # 🔴 금지 판정은 **한 곳**이다 — 목록을 손으로 적지 않는다(사본 금지)
    assert LI.spec_banned("tsdb:MLB"), "🔴 tsdb 를 금지로 안 본다"
    assert LI.spec_banned("url:https://statsapi.mlb.com/…|mlb") == ""
    assert LI.spec_banned("adapter:TEAM_IDS") == ""
    assert LI.spec_banned("fdorg:PL") == ""
    # ⚠️ 허용 목록이 **원본에서 자란다** — 새 출처를 더하면 저절로 따라온다
    for head in LI.ROSTER_SOURCES:
        assert LI.spec_banned(f"{head}:x") == "", head


def test_v5_8_4_캐시가_이름마다_출처를_적는다():
    """🔴 `by` 가 없으면 **가릴 수 없다** — 그래서 적는 것이 계약이다."""
    import inspect

    from app import league_index as LI
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(LI.teams_of))
    assert '"by"' in body, (
        "🔴 캐시가 **이름마다의 출처**를 안 적는다 — 그러면 §8-4 를 적용할 때 "
        "통째로 버리는 수밖에 없다(공식 API 30팀까지 버린다)")


def test_v5_8_4_걷은_것과_못_가린_것을_사유로_센다():
    """🔴🔴 **조용한 0 금지**(#3) — 못 가린 것을 "없다"로 적지 않는다.

    ⚠️ 옛 캐시는 `by` 가 없어 **가릴 수 없다.** 🔴 그것을 조용히 통과시키면
       다음 세션이 이름표를 믿는다. 사유에 **리그 이름으로** 남아야 한다.
    """
    import inspect

    from app import league_index as LI
    from app import teamref
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(teamref._from_league_index))
    assert "spec_banned" in body, (
        "🔴 이름표가 금지 출처를 **안 걷는다**(#2 배선)")

    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **금지 출처 이름이 실제로 안 들어오나**(M72 가 글자 검사를 뚫었다)
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ `if False:` 로 바꿔도 `spec_banned` 글자가 남아 **통과했다.**
    #  🔴 그래서 **금지 출처로 받은 캐시를 지어 넣고** 그 이름이 이름표에
    #     들어오나를 본다. ⚠️ 진짜 캐시는 건드리지 않는다.
    import pathlib as _pl
    import tempfile

    FAKE = "젠장말도안되는팀이름"
    d = _pl.Path(tempfile.mkdtemp())
    old_path, old_leagues = LI._cache_path, LI.leagues
    try:
        (d / "x.json").write_text(json.dumps(
            {"teams": [FAKE], "why": "지어낸 것", "locals": {}, "ext": {},
             "stamp": "x", "by": {LI.norm(FAKE): "tsdb:MLB"}},
            ensure_ascii=False), encoding="utf-8")
        LI._cache_path = lambda key: d / "x.json"
        LI.leagues = lambda: [{"key": "MLB", "sport": "baseball",
                               "langs": ["en"]}]
        reg, lines = teamref.build()
        got, _ = teamref.key_of(FAKE)
        assert not got, (
            f"🔴🔴 **§8-4 금지 출처(`tsdb:`)에서 온 이름이 이름표에 들어왔다** — "
            f"`{FAKE}` → `{got}`")
        assert any("금지 출처" in x for x in lines), lines
    finally:
        LI._cache_path, LI.leagues = old_path, old_leagues
        teamref._REG = None                 # 🔴 지어낸 이름표를 **버린다**

    for token in ("banned", "unverifiable"):
        assert token in body, (
            f"🔴 `{token}` 를 세지 않는다 — 걷은 수와 못 가린 리그를 사유로 "
            f"남겨야 한다(#3)")
    # 🔴 그리고 **실제로 글에 들어오나**
    said = teamref.build()[1]
    line = next((x for x in said if "클럽 이름" in x), "")
    assert line, said
    # ⚠️ 지금 저장소의 캐시는 **전부 `by` 가 없다** — 그 사실이 보여야 한다
    old = [str(lg.get("key")) for lg in LI.leagues()
           if (p := LI._cache_path(str(lg.get("key")))).exists()
           and not (json.loads(p.read_text(encoding="utf-8")).get("by"))]
    if old:
        assert "가릴 수 없는" in line, (
            f"🔴 출처를 못 가리는 옛 캐시가 {len(old)}개({old[:3]}) 있는데 "
            f"사유가 조용하다: {line}")
