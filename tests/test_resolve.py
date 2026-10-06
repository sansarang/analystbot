"""🔴🔴 **어느 리그인가** — 여섯 단 사다리(사용자 지시 2026-10-03).

> 사용자가 경기 질문을 하면 **어느 리그부터 검색을 해야 하는지 단계별로 세세하게**
> 봇이 찾아야 한다. **러프하게 코드 작성을 하지 말아라.**

══════════════════════════════════════════════════════════════════
🔴 근본 원인 (측정 2026-10-03) — 그 단계가 **아예 없었다**
══════════════════════════════════════════════════════════════════

```
aliases.find_team("감바 오사카")  →  ('soccer', 'Gamba Osaka')
                                     ^^^^^^^^ 🔴 **종목**이다. 리그가 아니다
```
그 하나에서 넷이 따라 무너졌다 — 언어 영어 고정 · 어댑터 못 고름 ·
`kia.com`(자동차)·`nba.com`·`golf.com` 을 염 · 사실 0~5건.
"""
from __future__ import annotations

import pytest

from app import league_index as LI
from app import resolve


def test_명부와_사다리가_맞물린다():
    """🔴 CLAUDE.md #2 — 선언만 있고 **읽는 코드가 없으면** 그것은 없는 코드다.

    ⚠️ `config/leagues.yaml` 의 `ladder:` 가 *"어느 순서로 좁히나"* 를 적는다.
       코드의 단계가 그 선언과 어긋나면 **문서가 거짓이 된다.**
    """
    want = [str(x["how"]) for x in LI.ladder()]
    assert want == ["names", "games_table", "team_index", "ask_team",
                    "sport_only", "unknown"], want
    # 🔴 단마다 **왜**가 적혀 있어야 한다 — 순서의 근거가 없으면 못 고친다
    for row in LI.ladder():
        assert str(row.get("why") or "").strip(), row
    # 🔴 코드가 그 여섯을 **실제로 밟는지** — 함수 이름으로 대조한다
    import inspect
    src = inspect.getsource(resolve.league_of)
    for fn in ("_by_names", "_by_games", "_by_index", "_by_ask", "_by_sport"):
        assert fn in src, fn


def test_리그마다_언어와_종목이_선언돼_있다():
    """🔴 리그를 알아도 **언어를 모르면** 검색이 영어로만 간다 — 그것이 뿌리였다."""
    assert LI.leagues(), "명부가 비었다"
    for lg in LI.leagues():
        key = str(lg["key"])
        assert LI.langs_of(key), f"{key} 에 언어 선언이 없다"
        assert LI.sport_of(key), f"{key} 에 종목 선언이 없다"
        # ⚠️ 어댑터는 **없을 수 있다**(J리그) — 없다고 거짓말만 안 하면 된다
        assert "en" in LI.langs_of(key), f"{key}: 영어가 빠졌다(공통 언어다)"


def test_팀_이름을_손으로_적지_않는다():
    """🔴 이적·승강 때마다 손 목록은 한 발 늦고, 늦은 목록은 **조용히 틀린 리그**를
    고르게 한다(0건보다 나쁘다). 명부는 *"어디서 받나"* 만 적는다."""
    import yaml
    from pathlib import Path
    raw = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "config/leagues.yaml")
        .read_text(encoding="utf-8"))
    #: 🔴 **v5 §8-4 로 명단 출처가 빈 리그 셋**(2026-10-04). ⚠️ 이름으로 적는다 —
    #   조용히 비면 그 리그가 명단 없이 도는 것을 아무도 모른다(#3).
    #
    #   v5 §8-4: *"TheSportsDB 는 **명단·리그 판정에 쓰지 않는다**(잘림·거짓
    #   명단)."* 🔴 J1 은 20팀인데 tsdb 가 **10팀**만 줬고, `lookup_all_teams` 는
    #   id 를 무시해 **영국 2부 24팀**을 매번 줬다(실측 2026-10-03).
    #   ⚠️ 그래서 이 셋은 **명단 없이** 돈다 — 리그 판정은 ②(쌓인 경기)와
    #      ③(이름표 · 54팀 YAML)가 한다.
    NO_ROSTER = {"NPB", "J리그", "K리그1"}
    for lg in raw["leagues"]:
        assert "teams" not in lg, f"{lg['key']} 에 팀 이름이 박혀 있다"
        key = str(lg["key"])
        if key in NO_ROSTER:
            assert lg.get("teams_from") == [], (
                f"🔴 `{key}` 가 명단 출처를 **되찾았다** — tsdb 라면 §8-4 위반이고, "
                f"온전한 길을 찾았다면 `NO_ROSTER` 에서 빼라: {lg.get('teams_from')}")
            continue
        assert lg.get("teams_from"), f"{key} 에 `teams_from` 이 없다"
        # 🔴 §8-4 — 남은 출처에 `tsdb:` 가 섞이면 안 된다
        assert not [x for x in lg["teams_from"] if str(x).startswith("tsdb:")], \
            (f"🔴 `{key}` 가 tsdb 명단을 쓴다(§8-4)")


def test_이름_맞추기는_지우기만_한다():
    """🔴 `norm` 은 **글자를 바꾸지 않는다** — 음차·치환은 추측이다.

    ⚠️ 실측: `Júbilo Iwata`/`Jubilo Iwata`, `Kyoto Sanga F.C.`/`Kyoto Sanga` 가
       다른 문자열이라 색인이 못 맞췄다. 악센트·점·공백만 걷는다.
    """
    assert LI.norm("Júbilo Iwata") == LI.norm("Jubilo Iwata")
    assert LI.norm("Kyoto Sanga F.C.") == LI.norm("kyoto sanga fc")
    assert LI.norm("LG Twins") == "lgtwins"
    # 🔴 **다른 팀을 같게 만들지 않는다**
    assert LI.norm("Kashiwa Reysol") != LI.norm("Kashima Antlers")


@pytest.mark.asyncio
async def test_통신_없이도_단계를_적는다():
    """🔴 `offline` 이면 ③④ 를 **건너뛰되 건너뛴 사실을 적는다.**

    ⚠️ 안 밟은 단과 밟았는데 빗나간 단은 **다르다** — 섞으면 고칠 곳을 못 찾는다.
    🔴 그리고 시험이 조용히 네트워크에 나가지 않는다.
    """
    got = await resolve.league_of("Nowhere United", offline=True)
    assert not got.known
    joined = " ".join(got.steps)
    assert "건너뜀" in joined and "통신하지 않는다" in joined
    assert "리그 미상" in joined
    # 🔴 **하나를 고르지 않는다** — 고르면 그것이 추측이다
    assert got.league == ""


@pytest.mark.asyncio
async def test_질문에_리그_이름이_있으면_그것이_이긴다():
    """① 사용자가 말했으면 추측할 것이 없다 — 통신도 안 한다."""
    got = await resolve.league_of("아무개", text="오늘 KBO 경기", offline=True)
    assert got.league == "KBO" and got.langs == ("ko", "en")
    assert got.steps[0].startswith("①")


@pytest.mark.asyncio
async def test_대회_이름은_리그가_아니다():
    """🔴🔴 실측 2026-10-03 — 여기서 **멈춰서** 일본어가 안 붙었다.

    표의 `league` 칸에는 **그 경기가 속한 대회**가 들어간다(`League Cup`·
    `Friendlies`·`CONCACAF Nations League A Grp. 2`). 명부에 없는 이름이다.
    ⚠️ 종전에는 거기서 멈춰 `언어 []` 로 끝났다 — 컵 경기도 기사는 일본 매체가 쓴다.
    🔴 대회는 **적어 두고** 리그는 **계속 찾는다.**
    """
    class _Pool:
        async def fetchrow(self, *a):
            # 🔴 `ext_id` 를 함께 준다 — 2026-10-04 부터 **종목이 거기서** 온다
            return {"league": "League Cup", "ext_id": "fotmob-5181780"}

    got = await resolve.league_of("Kashiwa Reysol", pool=_Pool(), offline=True)
    assert got.competition == "League Cup"
    # 🔴 멈추지 않았다 — 아래 단까지 내려갔다
    assert len(got.steps) > 2, got.steps
    assert "대회 이름이지 리그가 아니다" in " ".join(got.steps)
    # 🔴🔴 **리그는 몰라도 종목은 안다**(사용자 지시 2026-10-04 보기 A).
    #    ⚠️ 어댑터가 `SPORT` 를 선언해 두고도 사다리가 **묻지 않던** 자리다.
    assert got.sport == "soccer", got.steps
    assert "종목은 `soccer`" in " ".join(got.steps)


def test_대회로_들어와도_팀으로_리그를_되묻는다():
    """🔴🔴 한 겹 아래의 같은 병(실측 2026-10-03).

    세포는 `league` 로 **대회 이름**을 받는다(`League Cup`·`Friendlies`). 그
    이름은 어느 언어표에도 없어 **영어로만** 갔다 — 가시와 vs 감바가 그래서
    일본 매체 기사를 못 집었다.
    🔴 그런데 **팀 이름은 안다** — 색인이 `Kashiwa Reysol → J리그 → ja` 를 들고 있다.
    ⚠️ 캐시가 없으면 종전 길로 간다(있는 척하지 않는다) — 그래서 이 시험은
       캐시가 있을 때만 뜻이 있고, 없으면 **건너뛴다**.
    """
    from app import queries
    if not LI.cached_index():
        pytest.skip("리그 명단 캐시가 없다 — 통신 없이 검사할 수 없다")
    langs, why = queries.langs_for("League Cup", "Kashiwa Reysol")
    assert "ja" in langs, (langs, why)
    assert "되물은" in why


def test_캐시_조회는_통신하지_않는다():
    """🔴 `langs_for` 는 **동기**다 — 거기서 통신하면 질의마다 멈춘다."""
    import inspect
    src = inspect.getsource(LI.cached_index) + inspect.getsource(LI.league_of_team)
    for bad in ("await", "Net(", "urlopen", "httpx"):
        assert bad not in src, bad




def test_색인이_현지_표기를_짝지어_둔다():
    """🔴🔴 ③단이 리그를 맞혀도 **현지 표기를 안 꺼내면** 질의가 영어로 나간다.

    실측 2026-10-03: 리그는 `J리그` 로 맞혔는데 질의가 `Kashiwa Reysol スタメン`
    이었다 — 일본 매체는 `柏レイソル` 이라고 쓴다.
    ⚠️ 종전 색인은 이름을 **평평하게** 담아 `柏レイソル → J리그` 는 알아도
       *"`Kashiwa Reysol` 의 현지 표기"* 는 몰랐다.
    """
    if not LI.cached_index():
        pytest.skip("리그 명단 캐시가 없다 — 통신 없이 검사할 수 없다")
    got = LI.local_of_team("Kashiwa Reysol")
    assert got, "현지 표기를 못 꺼낸다"
    assert got != "Kashiwa Reysol"
    # 🔴 모르는 팀은 **빈 문자열** — 지어내지 않는다
    assert LI.local_of_team("Nowhere United") == ""




#: 🔴 같은 팀의 여러 언어 표기 — **같은 리그·같은 현지 표기**로 풀려야 한다.
SAME = [
    ("J리그", ["가시와 레이솔", "Kashiwa Reysol", "柏レイソル"]),
    ("KBO", ["LG 트윈스", "LG Twins"]),
    ("KBO(기아)", ["기아 타이거즈", "Kia Tigers"]),
]


@pytest.mark.parametrize("what,names", SAME, ids=[x[0] for x in SAME])
@pytest.mark.asyncio
async def test_어느_언어로_물어도_같은_자리로_간다(what, names):
    """🔴🔴 1단계의 불변식(사용자 지시 2026-10-03).

    > 같은 경기를 한국어·영어·일본어·현지어로 넣으면 `resolve()` 가 **전부 같은
    > key** 를 돌려야 한다.

    ⚠️ 리그만 같아서는 모자란다 — **현지 표기도 같아야** 질의가 같아진다.
       실측 2026-10-03: `LG Twins` 는 리그가 맞았는데 표기가 비어 **영어로만**
       검색했다(②단이 정하면 ③단을 안 밟아 표기를 못 꺼냈다).
    """
    if not LI.cached_index():
        pytest.skip("리그 명단 캐시가 없다 — 통신 없이 검사할 수 없다")
    seen = {}
    for n in names:
        got = await resolve.league_of(n, offline=True)
        seen[n] = (got.league, got.local)
    assert len(set(seen.values())) == 1, f"{what}: 갈렸다 {seen}"
    assert seen[names[0]][0], f"{what}: 리그를 못 풀었다 {seen}"


@pytest.mark.asyncio
async def test_리그를_모르면_현지_표기를_짓지_않는다():
    """🔴🔴 실측 2026-10-03 — `Croatia` 에 **포르투갈어 `Croácia`** 가 붙었다.

    ⚠️ 리그를 모르면 **어느 언어가 현지어인지도 모른다.** 그때 받아 온 표기를
       아무거나 붙이면 그 글자로 검색해 엉뚱한 데로 간다.
    🔴 모르면 **비워 둔다** — 지어내지 않는다.
    """
    got = await resolve.league_of("Croatia", offline=True)
    if got.league:
        pytest.skip("명부가 대표팀 리그를 알게 됐다 — 이 시험의 전제가 바뀌었다")
    assert got.local == "", f"리그를 모르는데 표기를 붙였다: {got.local!r}"


def test_현지_표기를_꺼내는_곳이_하나다():
    """🔴 어느 단이 리그를 정했든 **같은 자리**에서 꺼낸다.

    ⚠️ ③단 안에서만 꺼내면 ②단이 정했을 때 표기가 빈다(실측). 한 곳에서 하면
       **빠질 수가 없다**(사본 금지와 같은 뿌리).
    """
    import ast
    import inspect
    import textwrap
    code = ast.unparse(ast.parse(textwrap.dedent(
        inspect.getsource(resolve.league_of))))
    assert "_local(" in code
    body = inspect.getsource(resolve)
    assert body.count("def _local(") == 1
