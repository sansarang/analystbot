"""🔴🔴 **선수 능력치** — 사용자 지시 2026-10-17.

> 핵심선수 결장 · 후보선수로 대체했을때 가설제공(**숫자가 아닌 능력치**) …
> 이거는 전략분석가한테 줘야 하는거다

🔴 잠금 넷(`app/core/ability.py` 머리말):
  ① **수는 안 넘긴다** — 문턱으로 `강점/보통/약점` 글자를 만들고 그것만 준다
  ② **대상을 고른다** — 선수 한 명이 2.09초다(실측) · 상한을 둔다
  ③ **이름으로 찾지 않는다** — 열쇠는 `Player.pid`
  ④ **못 받은 것은 이름으로** 남긴다(네 가지로 갈라서 · #3)

⚠️ 어제 절제에서 배운 것 — **글자 검사로는 못 센다**. 그래서 행동으로 센다.
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib

from app.collect import fotmob as fm
from app.core import ability as ab

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: 🔴 실측 2026-10-17(`/players/935033` Duk) 그 꼴 — 대역은 **운영 모양**이다
DUK = {"key": "stats_comparison_att_mid_wingers",
       "title": "Stats compared to other attacking midfielders/wingers",
       "items": [{"key": "chances_created", "title": "Chances created",
                  "value": 0.36},
                 {"key": "aerials_won", "title": "Aerial duels", "value": 0.8},
                 {"key": "defensive_actions", "title": "Defensive actions",
                  "value": 0.68},
                 {"key": "goals", "title": "Goals", "value": 0.34}]}
#: 🔴 실측 — **골키퍼는 지표가 다르다**(비교 묶음을 출처가 고른다)
GK = {"key": "stats_comparison_goalkeepers",
      "title": "Stats compared to other goalkeepers",
      "items": [{"key": "save_percentage", "title": "Save percentage",
                 "value": 0.88},
                {"key": "clean_sheet", "title": "Clean sheets", "value": 0.1}]}


def _page(traits: dict) -> dict:
    """🔴 `fotmob.payload()` 가 주는 그 틀(실측: `props.pageProps.data`)."""
    return {"props": {"pageProps": {"data": {"traits": traits}}}}


# ══════════════════════════════════════════════════════════════════
# 🔴 통로 — 주소와 파서
# ══════════════════════════════════════════════════════════════════


def test_ab1_선수_페이지_주소() -> None:
    """🔴 #4 — 번호가 아니면 **빈 글자**다(지어낸 주소를 던지지 않는다)."""
    assert fm.player_url(935033) == "https://www.fotmob.com/players/935033"
    assert fm.player_url("abc") == "" and fm.player_url(None) == ""
    # 🔴 주소 뿌리는 **그 표 하나**다(사본 금지)
    assert fm.player_url(1).startswith(fm.BASE)


def test_ab2_능력치_파서가_출처_꼴을_읽는다() -> None:
    """🔴 실측 2026-10-17 그 꼴. ⚠️ 칸이 없으면 **빈 꼴**이다(0 이 아니다)."""
    title, items = fm.traits_of(_page(DUK))
    assert "attacking midfielders" in title
    assert [x["key"] for x in items][:2] == ["chances_created", "aerials_won"]
    assert items[1]["value"] == 0.8
    # 🔴 빈 페이지·빈 칸 → 빈 꼴(#3)
    assert fm.traits_of({}) == ("", [])
    assert fm.traits_of(_page({})) == ("", [])
    # 🔴 **수가 없는 줄은 버린다**(지어내지 않는다) · 이름이 없으면 `key` 로
    #    떨어진다 — `key` 는 **출처의 글자**이지 지어낸 이름이 아니다.
    bad = {"title": "t", "items": [{"key": "x", "title": "X"},
                                   {"key": "y", "value": 0.5}]}
    got = fm.traits_of(_page(bad))[1]
    assert [x["key"] for x in got] == ["y"], got     # 수 없는 `x` 는 버렸다
    assert got[0]["title"] == "y"                    # 이름은 `key` 로 떨어졌다


def test_ab3_선수_번호가_XI_까지_살아온다() -> None:
    """🔴🔴 ③ **이름으로 찾지 않는다** — 열쇠는 번호다.

    ⚠️ 종전 `players_of` 는 `id` 를 **버렸다** — 그래서 선수 한 명을 다시 찾을
       길이 없었다(동명이인·표기 변형이 있다 · 어제 `Sohel Rana` 그 병).
    """
    from app.core import adapt
    from app.core.schema import Player
    assert "pid" in Player.model_fields, "🔴 스키마에 칸이 없다"
    rows = fm.players_of({"starters": [
        {"id": 935033, "name": "Duk", "shirtNumber": 11},
        {"name": "No Id", "shirtNumber": 7}]})
    assert [r.get("pid") for r in rows] == [935033, None], rows
    # 🔴 `adapt` 가 그 칸을 **싣는다**(안 실으면 통로가 끊긴다)
    xi = adapt.xi_of("team:000001", {"players": ["Duk", "No Id"],
                                     "lineup": rows, "lineup_state": "confirmed"})
    assert [p.pid for p in xi.lineup] == [935033, None], xi.lineup


# ══════════════════════════════════════════════════════════════════
# 🔴 ① 수는 안 넘긴다 — 문턱으로 글자를 만든다
# ══════════════════════════════════════════════════════════════════


def test_ab4_백분위가_글자가_된다() -> None:
    strong, weak = ab.cuts()
    assert 0 < weak < strong < 1, (strong, weak)
    assert ab.word_of(strong) == "강점" and ab.word_of(0.99) == "강점"
    assert ab.word_of(weak) == "약점" and ab.word_of(0.01) == "약점"
    assert ab.word_of((strong + weak) / 2) == "보통"


def test_ab5_문턱_표가_없으면_등급을_안_낸다(monkeypatch) -> None:  # noqa: ANN001
    """🔴 ① 표는 `config/ability.yaml` 이 든다 — **코드에 박지 않는다**.

    ⚠️ 표가 없으면 `강점` 을 지어내지 않고 **빈 글자**다(부르는 쪽이 그 사실을
       적는다 · #3).
    """
    monkeypatch.setattr(ab, "_CUTS", {})
    assert ab.word_of(0.99) == "" and ab.word_of(0.01) == ""
    # 🔴 그때 글에는 **등급 못 냄**이 적힌다(조용히 비지 않는다)
    rows = [{"id": "L1", "side": "home", "kind": "swap", "text": "x",
             "players": [("Duk", 935033)]}]
    said = ab.said_of(rows, {"Duk": {"group": "g", "items": DUK["items"]}})
    assert any("등급 못 냄" in x for x in said), said


def test_ab6_글자에_수가_없다() -> None:
    """🔴🔴 ① **모델에게 수를 주지 않는다** — 받은 것은 글자뿐이어야 한다.

    ⚠️ 수를 주면 모델이 그 수를 근거로 말하고, 그 수가 틀리면 평도 틀린다
       (이 저장소가 `0.85` 를 정답으로 보고 다친 그 결).
    """
    import re
    rows = [{"id": "L1", "side": "home", "kind": "swap",
             "text": "FW 자리 — 빠짐 ['Duk'] · 들어옴 ['Zaldívar']",
             "players": [("Duk", 935033), ("Zaldívar", 766852)]}]
    box = {"Duk": {"group": DUK["title"], "items": DUK["items"]},
           "Zaldívar": {"group": DUK["title"], "items": GK["items"]}}
    said = "\n".join(ab.said_of(rows, box, ref=None))
    assert "강점" in said and "약점" in said
    # 🔴 **백분위 수가 한 글자도 없다**(`0.8`·`80%` 금지)
    assert not re.search(r"0\.\d|\d+\s?%", said), said
    for x in ("Aerial duels", "Save percentage"):
        assert x in said, said                     # 지표 이름은 출처 글자대로


def test_ab7_비교_묶음을_함께_적는다() -> None:
    """🔴 **골키퍼와 윙은 다른 지표로 잰다** — 나란히 세워 *누가 더 세다*고 말할
    수 없다. 그래서 묶음 제목을 글에 **함께** 싣는다(출처가 그렇게 준다)."""
    rows = [{"id": "L1", "side": "away", "kind": "swap", "text": "GK 자리",
             "players": [("Nagai", 431791)]}]
    said = "\n".join(ab.said_of(
        rows, {"Nagai": {"group": GK["title"], "items": GK["items"]}}))
    assert "other goalkeepers" in said, said
    # ⚠️ 프롬프트가 그 함정을 **말로** 막는다
    from app.core import strategy_llm as sl
    src = inspect.getsource(sl.ask)
    assert "비교 묶음이 다른 선수를 나란히 세우지 마라" in src, "🔴 안 막는다"
    assert "수를 쓰지 마라" in src


def test_ab8_못_받은_선수는_이름으로_남는다() -> None:
    """🔴 ④ #3 — 조용한 0 금지. 능력치가 없으면 **그 이름과 사유**가 남는다."""
    rows = [{"id": "L1", "side": "home", "kind": "swap", "text": "x",
             "players": [("있는 선수", 1), ("없는 선수", 2)]}]
    said = "\n".join(ab.said_of(
        rows, {"있는 선수": {"group": "g", "items": DUK["items"]}}))
    assert "`없는 선수` ⬜ 능력치 없음" in said, said
    assert ab.NONE_MARK == "⬜"


# ══════════════════════════════════════════════════════════════════
# 🔴 ② 대상을 고른다 — 한 명이 2.09초다(실측)
# ══════════════════════════════════════════════════════════════════


class _P:
    def __init__(self, name: str, pid: int | None) -> None:
        self.name, self.pid = name, pid


class _XI:
    def __init__(self, rows: list) -> None:
        self.lineup = list(rows)


class _R:
    home, away = "team:000001", "team:000002"
    home_name, away_name = "A팀", "B팀"


class _F:
    def __init__(self, xi=None, past=None) -> None:  # noqa: ANN001
        self.xi = dict(xi or {})
        self.past_xi = dict(past or {})
        self.last_xi: dict = {}


class _Plan:
    def __init__(self, facts: dict) -> None:
        self.facts = dict(facts)


def test_ab9_빠진_선수_번호는_평소_XI_에서_온다() -> None:
    """🔴🔴 빠진 선수는 **오늘 XI 에 없다** — 그 번호는 `past_xi` 가 든다.

    ⚠️ 오늘 XI 만 보면 *"빠진 선수 번호를 못 찾았다"* 가 되어 능력치가 **늘
       절반**만 선다(대체의 한쪽만 보고 비교하는 꼴이다).
    """
    facts = _F(xi={"team:000001": _XI([_P("들어온 선수", 222)])},
               past={"team:000001": [_XI([_P("빠진 선수", 111)])]})
    book = ab.pid_book(facts, _R())
    assert book == {"들어온 선수": 222, "빠진 선수": 111}, book
    # 🔴 번호 없는 선수는 **안 담는다**(③)
    f2 = _F(xi={"team:000001": _XI([_P("번호 없음", None)])})
    assert ab.pid_book(f2, _R()) == {}


def test_ab10_대상은_교체_짝과_핵심_선수뿐이다() -> None:
    facts = _F(xi={"team:000001": _XI([_P("B", 2)])},
               past={"team:000001": [_XI([_P("A", 1)])]})
    plan = _Plan({
        "L9": {"side": "home", "kind": "swap",
               "text": "A팀 LB 자리 — 빠짐 ['A'] · 들어옴 ['B']"},
        "L6": {"side": "home", "kind": "key_player",
               "text": "A팀 핵심 선수 B — 벤치"},
        # 🔴 이 셋은 **대상이 아니다**(능력치와 무관하다)
        "L1": {"side": "home", "kind": "formation", "text": "포메이션 4-4-2"},
        "L2": {"side": "home", "kind": "rotation", "text": "바뀐 자리 3개"},
        "L7": {"side": "home", "kind": "delta_def", "text": "수비 자리 가치"}})
    rows, why = ab.targets(_R(), facts, plan)
    assert [r["id"] for r in rows] == ["L9", "L6"], (rows, why)
    assert dict(rows[0]["players"]) == {"A": 1, "B": 2}, rows[0]
    assert "대상" in why


def test_ab10b_이름을_글에서_파싱하지_않고_명부에서_찾는다() -> None:
    """🔴🔴 실측 2026-10-17 — 처음 판은 따옴표 사이를 긁다가 **한 글자 이름**을
    건너뛰고 `] · 들어옴 [` 를 이름으로 잡았다. 🔴 꾸민 글을 되파싱하면 글
    모양이 바뀔 때 또 깨진다 — **아는 이름이 그 글에 있나**를 본다.

    ⚠️ **긴 이름부터** 본다 — `Rana` ⊂ `Sohel Rana` 면 긴 쪽 하나로 센다
       (어제 이름 변형으로 선발을 결장 처리한 그 병의 사촌).
    """
    facts = _F(xi={"team:000001": _XI([_P("Sohel Rana", 11), _P("Rana", 22),
                                       _P("B", 2)])})
    plan = _Plan({"L9": {"side": "home", "kind": "swap",
                         "text": "A팀 CM 자리 — 빠짐 ['Sohel Rana'] · 들어옴 ['B']"}})
    rows, why = ab.targets(_R(), facts, plan)
    assert len(rows) == 1, (rows, why)
    # 🔴 `Rana` 를 **따로 세지 않는다**(긴 이름 안에 든 짧은 이름)
    assert dict(rows[0]["players"]) == {"Sohel Rana": 11, "B": 2}, rows[0]
    # 🔴 아는 이름이 없으면 **그 사실을 적는다**(#3)
    rows0, why0 = ab.targets(_R(), _F(), _Plan(
        {"L9": {"side": "home", "kind": "swap", "text": "빠짐 ['X']"}}))
    assert rows0 == [] and "아는 선수 이름이 없다" in why0, why0
    # ⚠️ 파싱 흔적이 남아 있지 않다(되파싱 금지)
    src = inspect.getsource(ab.targets)
    assert "re.findall" not in src, "🔴 아직 글을 되파싱한다"


def test_ab11_상한이_있다() -> None:
    """🔴🔴 ② 선수 한 명이 **2.09초 · 880KB**다(실측 2026-10-17).

    22명을 다 받으면 46초다 — 카드 20분 상한 안에서 돌아야 한다.
    """
    assert 1 <= ab.MAX_PLAYERS <= 10 and 1 <= ab.MAX_PER_SIDE <= 5
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **전체 상한이 혼자 걸리는 대역**이어야 한다(절제로 잡았다)
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 처음 대역은 한 팀에만 교체를 뒀다 — 그러면 **팀별 상한**이 먼저 걸려
    #     전체 상한을 지워도 **초록**이었다(계약이 그 줄을 안 쥐었다).
    #  🔴 그래서 **양 팀에** 교체를 두고 한 자리에 **두 명씩** 둔다 — 팀별
    #     상한만으로는 8명까지 가므로 **전체 상한이 혼자** 걸린다.
    rows_in: dict = {}
    book: list = []
    for side, key in (("home", 1), ("away", 2)):
        for i in range(2):
            rows_in[f"{side[0].upper()}{i}"] = {
                "side": side, "kind": "swap",
                "text": f"빠짐 ['{side}out{i}', '{side}out{i}b'] · "
                        f"들어옴 ['{side}in{i}']"}
            book += [_P(f"{side}out{i}", key * 1000 + i),
                     _P(f"{side}out{i}b", key * 1000 + 50 + i),
                     _P(f"{side}in{i}", key * 2000 + i)]
    facts = _F(xi={"team:000001": _XI(book), "team:000002": _XI(book)})
    rows, why = ab.targets(_R(), facts, _Plan(rows_in))
    n = sum(len(r["players"]) for r in rows)
    assert n <= ab.MAX_PLAYERS, (n, why)
    # 🔴 **전체 상한이 실제로 걸렸다**(팀별 상한만으로는 더 갔다)
    assert n > ab.MAX_PER_SIDE, (n, why)
    # 🔴 **상한에 걸린 것을 이름으로** 남긴다(#3)
    assert "전체 상한" in why, why

    # ══════════════════════════════════════════════════════════════
    # 🔴 **팀별 상한도 혼자 걸리는 자리**가 있어야 한다(절제로 잡았다)
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 위 대역은 전체 상한이 먼저 걸려 **팀별 상한을 지워도 초록**이었다.
    #  🔴 그래서 **한 팀에만** 자리를 많이 두고 본다 — 한 팀이 상한을 넘으면
    #     그 자리는 **건너뛰고 사유가 남아야** 한다(양 팀이 고르게 들어간다).
    rows_h: dict = {}
    book_h: list = []
    for i in range(4):
        rows_h[f"H{i}"] = {"side": "home", "kind": "swap",
                           "text": f"빠짐 ['h{i}'] · 들어옴 ['j{i}']"}
        book_h += [_P(f"h{i}", 300 + i), _P(f"j{i}", 400 + i)]
    got2, why2 = ab.targets(_R(), _F(xi={"team:000001": _XI(book_h)}),
                            _Plan(rows_h))
    n2 = sum(len(r["players"]) for r in got2)
    assert n2 <= ab.MAX_PER_SIDE + 1, (n2, why2)   # 자리 하나는 통째로 든다
    assert "한 팀 상한" in why2, why2


def test_ab12_카드_상한이_바닥이면_멈추고_사유를_남긴다() -> None:
    """🔴 ② 조용히 적게 받지 않는다 — 멈춘 사실이 사유에 남는다."""
    class _Clock:
        def over(self) -> bool:
            return True

    rows = [{"id": "L1", "side": "home", "kind": "swap", "text": "x",
             "players": [("A", 1)]}]
    got, why = asyncio.run(ab.fetch(None, rows, clock=_Clock()))
    assert got == {} and "카드 상한" in why, why


def test_ab13_통로는_기존_net_이다(monkeypatch) -> None:  # noqa: ANN001
    """🔴 새 fetch 경로를 만들지 않는다 — robots·캐시·UA 를 `net.get` 이 지킨다.

    🔴 그리고 **행동으로** 센다(글자 검사로는 호출을 꺼도 통과한다 · 어제 절제).
    """
    class _Page:
        def __init__(self, text: str) -> None:
            self.text = text

    seen: list[str] = []

    class _Net:
        async def get(self, url: str, **kw):  # noqa: ANN001, ANN201
            seen.append(url)
            if "935033" in url:
                import json
                return _Page("<script id=\"__NEXT_DATA__\" "
                             "type=\"application/json\">"
                             + json.dumps(_page(DUK)) + "</script>")
            raise RuntimeError("못 받았다")

    rows = [{"id": "L1", "side": "home", "kind": "swap", "text": "x",
             "players": [("Duk", 935033), ("Dead", 999)]}]
    got, why = asyncio.run(ab.fetch(_Net(), rows))
    assert seen == ["https://www.fotmob.com/players/935033",
                    "https://www.fotmob.com/players/999"], seen
    assert list(got) == ["Duk"], got
    assert got["Duk"]["items"][1]["value"] == 0.8
    # 🔴 ④ **못 받은 것을 갈라서** 적는다
    assert "능력치 **1명**" in why and "못 받은 선수 1명" in why, why
    src = inspect.getsource(ab.fetch)
    assert "net.get(" in src and "aiohttp" not in src


# ══════════════════════════════════════════════════════════════════
# 🔴 배선 — 안 이은 코드는 없는 코드보다 나쁘다(#2)
# ══════════════════════════════════════════════════════════════════


def test_ab14_전략분석가가_그_재료를_받는다() -> None:
    from app.core import strategy_llm as sl
    assert "ability" in inspect.signature(sl.ask).parameters, "🔴 안 받는다"
    src = inspect.getsource(sl.ask)
    assert "said_ability" in src and "선수 능력치(자리별 비교" in src


def test_ab15_운영과_러너에_배선됐다() -> None:
    """🔴🔴 **자료는 계속 모은다** — 사용자 지시 2026-10-18.

    > llm 은 **서치용**으로 사용한다 .. **llm 전략분석만 지워라** ..
    > **자료는 놔둬라** · **능력치 갈래모듈, 직전5경기 등은 변수에 사용될거다**

    ⚠️ 종전 어림은 *"`_ab3.fetch(` 가 `_sl.ask(` **앞**에 있어야 한다"* 였다 —
       그 재료가 **⑤-b2 프롬프트**에 들어가야 했기 때문이다. 🔴 ⑤-b2 를
       지웠으니 그 순서는 뜻이 없다. 대신 **능력치를 계속 받는지**를 센다
       (받기를 멈추면 그 자료로 변수를 만들 수 없다).
    """
    for rel in ("app/core/pipeline.py", "tools/run_collect.py"):
        said = (ROOT / rel).read_text(encoding="utf-8")
        assert "ability as _ab3" in said, f"🔴 {rel} 가 안 부른다"
        assert "_ab3.fetch(" in said, f"🔴 {rel} 가 능력치를 안 받는다"
        assert "_ab3.said_of(" in said, f"🔴 {rel} 가 글자를 안 만든다"
    said_run = (ROOT / "tools/run_collect.py").read_text(encoding="utf-8")
    assert "⑤-b1 선수 능력치" in said_run, "🔴 장부에 칸이 없다"


def test_ab16_문턱_표가_설정에_있다() -> None:
    """🔴 ① 값은 `config/` 에 두고 **사용자만** 바꾼다(§13-7)."""
    import yaml
    said = (ROOT / ab.CONF).read_text(encoding="utf-8")
    box = yaml.safe_load(said)
    #  🔴 **표가 자랐다**(2026-10-17) — 전술 갈래를 능력치로 가리는 칸이 더해졌다.
    #     ⚠️ 그래도 *"우리가 고르는 수만 여기 있다"* 는 규율은 같다 — 지표
    #        이름·비교 묶음은 **출처가 준다**(여기 안 적는다 · #1).
    #  🔴 **표가 또 자랐다**(2026-10-19) — `count_slack`(양쪽 인원 차 허용값)이
    #     더해졌다. ⚠️ 그것도 **사용자가 정한 손값**이다(측정값이 아니다):
    #     르아브르 1-3 에서 8명 ↔ 10명 평균을 견주다 틀렸고, 완전 일치(0)로
    #     막으니 즈볼러의 쓸 만한 갈래(10↔11)까지 버려져 **1** 로 두었다.
    assert set(box) == {"strong", "weak", "branches", "branch_gap",
                        "branch_min", "squad_cap_per_side",
                        "count_slack"}, sorted(box)
    #  🔴 그 값은 **정수**이고 음수가 아니다(0 이면 완전 일치)
    assert isinstance(box["count_slack"], int) and box["count_slack"] >= 0
    #  🔴 갈래 표는 **지표 이름만** 적는다(값·계수가 아니다)
    for kind, rule in dict(box["branches"]).items():
        assert set(rule) == {"pos", "flank", "traits", "why"}, (kind, rule)
        assert rule["traits"], f"🔴 `{kind}` 에 지표가 없다"
        assert str(rule["why"]).strip(), f"🔴 `{kind}` 에 **왜**가 없다(#3)"
    assert 0.0 < float(box["branch_gap"]) < 1.0, box["branch_gap"]
    # ⚠️ 그 수가 **확률 계수가 아니라는 것**을 파일이 말한다
    assert "확률 계수가 아니다" in said
    assert "원장으로 맞추지 않는다" in said
