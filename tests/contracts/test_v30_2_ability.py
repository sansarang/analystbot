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
    #  🔴🔴 **교체 짝 행은 하나다** — 나머지는 상한을 채운 `xi` 행이다
    #     (사용자 지시 2026-10-19 ③ · `test_ab10c` 가 그 행을 센다).
    swaps = [r for r in rows if r["kind"] == "swap"]
    assert len(swaps) == 1, (rows, why)
    # 🔴 `Rana` 를 **따로 세지 않는다**(긴 이름 안에 든 짧은 이름)
    assert dict(swaps[0]["players"]) == {"Sohel Rana": 11, "B": 2}, swaps[0]
    # 🔴 아는 이름이 없으면 **그 사실을 적는다**(#3)
    rows0, why0 = ab.targets(_R(), _F(), _Plan(
        {"L9": {"side": "home", "kind": "swap", "text": "빠짐 ['X']"}}))
    #  ⚠️ XI 가 **아예 없는** 대역이라 채울 선발도 없다 → 빈 목록이 맞다
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


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **③ 고침 + 안전장치** — 사용자 지시 2026-10-19
#
#  > 3 고치고 안전장치를 만들어라 **선발 11명 능력치를 받지 못하면 분석은
#  > 무의미하다**
#
#  실측이 이 둘을 불렀다(하르키우 2-1 리비 베레흐 · fotmob 5909177):
#    ① ⑤-b1 이 6명을 받고 ⑤-b1b 가 **같은 선발 22명**을 또 받았다(겹침 중복)
#    ② 그 6명은 `traits: null` 이었고, 능력치가 **있는 선발 둘**(홈 GK·LB)은
#       **대상이 아니어서** 한 명도 안 썼다 → *"능력치 0명"*
#    ③ 원정이 **0명**인데도 카드가 확률을 **냈다**(홈 32.9 · 무 32.2 · 원정 34.9)
# ══════════════════════════════════════════════════════════════════


class _XIB(_XI):
    """🔴 벤치까지 있는 XI(운영 모양) — `bench` 는 **이름 글자**다."""

    def __init__(self, rows: list, bench: list | None = None) -> None:
        super().__init__(rows)
        self.bench = list(bench or [])


def _eleven(side_key: int) -> list:
    """🔴 선발 11명 — 번호는 팀마다 다르게."""
    return [_P(f"p{side_key}_{i}", side_key * 100 + i) for i in range(11)]


def test_ab17_이미_받은_선수를_다시_받지_않는다() -> None:
    """🔴🔴 ③ — `have=` 로 넘긴 선수는 **통신 0건**이다(행동으로 센다).

    ⚠️ 글자 검사로는 못 센다 — `net` 을 **아예 안 주고**(None) 부른다. 다시
       받으려 들면 그 자리에서 터진다.
    """
    rows = [{"id": "L9", "side": "home", "kind": "swap", "text": "x",
             "players": [("A", 1), ("B", 2)]}]
    have = {"A": {"pid": 1, "group": "g", "items": DUK["items"]},
            "B": {"pid": 2, "group": "g", "items": GK["items"]}}
    got, why = asyncio.run(ab.fetch(None, rows, have=have))
    assert set(got) == {"A", "B"}, (got, why)
    assert got["A"]["items"] == DUK["items"]
    # 🔴 재사용한 수를 **사유에 적는다**(#3 · 조용한 재사용 금지)
    assert "이미 받은 것 2명" in why, why


def test_ab18_상한이_남으면_오늘_선발로_채운다() -> None:
    """🔴🔴 ③ — 교체·핵심 선수가 상한을 안 채우면 **오늘 선발**이 들어온다.

    ⚠️ 하르키우 판: 결장 0건이라 대상이 공격 쪽 6명뿐이었고 그 6명이 전부
       `traits: null` 이었다. 능력치가 **있는 선발**은 대상이 아니었다.
    """
    facts = _F(xi={"team:000001": _XIB(_eleven(1)),
                   "team:000002": _XIB(_eleven(2))})
    rows, why = ab.targets(_R(), facts, _Plan({}))
    assert rows, why
    assert {r["kind"] for r in rows} == {"xi"}, rows
    # 🔴 양 팀이 **고르게** 들어간다(팀별 상한)
    assert {r["side"] for r in rows} == {"home", "away"}, rows
    n = sum(len(r["players"]) for r in rows)
    assert n == ab.MAX_PLAYERS, (n, why)
    assert "오늘 선발" in why, why
    # 🔴 교체 짝이 상한을 **다 채우면** 선발을 안 넣는다(종전 동작 그대로)
    full: dict = {}
    book: list = []
    for side, key in (("home", 1), ("away", 2)):
        for i in range(3):
            full[f"{side[0]}{i}"] = {"side": side, "kind": "swap",
                                     "text": f"빠짐 ['{side}{i}']"}
            book.append(_P(f"{side}{i}", key * 10 + i))
    f2 = _F(xi={"team:000001": _XIB(book), "team:000002": _XIB(book)})
    rows2, why2 = ab.targets(_R(), f2, _Plan(full))
    assert "xi" not in {r["kind"] for r in rows2}, (rows2, why2)


def test_ab19_선발_능력치_검문() -> None:
    """🔴🔴 **안전장치** — 양 팀 각각 `xi_ability_min_per_side` 명이어야 간다."""
    facts = _F(xi={"team:000001": _XIB(_eleven(1)),
                   "team:000002": _XIB(_eleven(2))})
    #  🔴 문턱 값에 **묶지 않는다** — 사용자가 바꾸는 손값이다(11 → 8 ·
    #     2026-10-19). 계약은 *"그 수대로 가른다"* 만 센다.
    need = ab.xi_min()
    assert 1 <= need <= 11, f"🔴 문턱이 꼴이 아니다({need})"
    box_full = {f"p{k}_{i}": {"group": "g", "items": DUK["items"]}
                for k in (1, 2) for i in range(11)}
    ok = ab.xi_gate(facts, _R(), box_full)
    assert ok.ok and ok.card() == "", ok
    assert "11/11" in ok.why, ok.why
    #  🔴 **문턱 바로 아래는 걸린다**(경계 · 절제로 잡는다)
    edge = {f"p{k}_{i}": {"group": "g", "items": DUK["items"]}
            for k in (1, 2) for i in range(need - 1)}
    assert not ab.xi_gate(facts, _R(), edge).ok, (need, "문턱-1 이 통과했다")
    #  🔴 **문턱 딱 그만큼은 통과한다**
    just = {f"p{k}_{i}": {"group": "g", "items": DUK["items"]}
            for k in (1, 2) for i in range(need)}
    assert ab.xi_gate(facts, _R(), just).ok, (need, "문턱만큼인데 걸렸다")
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **하르키우 판** — 홈 2명 · 원정 **0명** → 확률을 내지 않는다
    # ══════════════════════════════════════════════════════════════
    box_ukr = {f"p1_{i}": {"group": "g", "items": GK["items"]}
               for i in range(2)}
    bad = ab.xi_gate(facts, _R(), box_ukr)
    assert not bad.ok, bad
    assert "2/11" in bad.why and "0/11" in bad.why, bad.why
    # 🔴 "누구"를 적는다(#3) — 양 팀 모두
    assert any(x.startswith("home") for x in bad.names), bad.names
    assert any(x.startswith("away") for x in bad.names), bad.names
    assert "선발 능력치 미확보" in bad.card()
    # 🔴 한쪽만 차도 **안 된다**(비교가 못 선다)
    half = dict(box_full)
    for i in range(11):
        half.pop(f"p2_{i}")
    assert not ab.xi_gate(facts, _R(), half).ok
    # 🔴 `traits` 가 **빈 묶음**은 받은 것이 아니다
    empty = {nm: {"group": "g", "items": []} for nm in box_full}
    assert not ab.xi_gate(facts, _R(), empty).ok


def test_ab19c_동등한_조건에서만_센다() -> None:
    """🔴🔴 **양쪽 인원 차** — 사용자 지시 2026-10-19.

    > 그리고 **동등한 조건에서 측정을 해야 한다** .. 양팀 조건을 맞았을때

    🔴 허용값은 저장소가 이미 든 `count_slack` 하나다(사본 금지) — 갈래 판정·
       `AB1`·`AB3`·`DV3` 가 쓰는 그 수다.
    ⚠️ 왜 — 르아브르 1-3: 0.50(**8명**) ↔ 0.37(10명) 을 견주다 틀렸다.
    """
    facts = _F(xi={"team:000001": _XIB(_eleven(1)),
                   "team:000002": _XIB(_eleven(2))})
    need, slack = ab.xi_min(), ab.count_slack()
    assert slack >= 0, slack

    def _box(n_home: int, n_away: int) -> dict:
        got = {}
        for k, n in ((1, n_home), (2, n_away)):
            for i in range(n):
                got[f"p{k}_{i}"] = {"group": "g", "items": DUK["items"]}
        return got

    # 🔴 **둘 다 문턱을 넘겨도** 차가 허용값보다 크면 걸린다
    big = ab.xi_gate(facts, _R(), _box(11, need))
    if 11 - need > slack:
        assert not big.ok, (need, slack, big.why)
        assert f"양쪽 차 {11 - need}명" in big.why, big.why
    # 🔴 차가 허용값 안이면 통과한다(그 사실도 사유에 적는다)
    fine = ab.xi_gate(facts, _R(), _box(need + slack, need))
    assert fine.ok, (need, slack, fine.why)
    assert f"양쪽 차 {slack}명(허용 {slack}명)" in fine.why, fine.why
    # ══════════════════════════════════════════════════════════════
    # 🔴 **실측 판 둘이 이 규칙대로 갈린다**(2026-10-19)
    # ══════════════════════════════════════════════════════════════
    #   이집트(home 9 · away 8) — 능력치를 주는 리그 → 통과해야 한다
    #   우크라이나(home 2 · away 0) — 안 주는 리그 → 걸려야 한다
    assert ab.xi_gate(facts, _R(), _box(9, 8)).ok, "🔴 이집트 판이 걸렸다"
    assert not ab.xi_gate(facts, _R(), _box(2, 0)).ok, "🔴 우크라 판이 통과했다"


def test_ab19b_문턱_0_이면_검문이_꺼진다(monkeypatch) -> None:  # noqa: ANN001
    """🔴 사용자가 0 으로 두면 끈다(§13-7) — 코드가 제 값을 쥐지 않는다."""
    monkeypatch.setattr(ab, "_CUTS", {"xi_ability_min_per_side": 0})
    got = ab.xi_gate(_F(), _R(), {})
    assert got.ok and "검문 꺼짐" in got.why, got


def test_ab20_검문이_확률_앞에_배선됐다() -> None:
    """🔴🔴 **배선** — 검문이 운영 경로에서 **확률 앞**에 있어야 한다.

    🔴 그리고 걸리면 **확률 칸을 비운 채** 퇴로 카드로 나간다(숫자를 낸 채
       🔴만 다는 것 금지 · 라인업 신원 검문과 같은 규율).
    ⚠️ **XI 가 아예 없는 판**(T−24h 기본 카드)은 건너뛴다 — 없는 것은 모순이
       아니다. 그 예외가 없으면 라인업 전 카드가 통째로 막힌다.
    """
    said = (ROOT / "app/core/pipeline.py").read_text(encoding="utf-8")
    assert "_ab3.xi_gate(" in said, "🔴 검문을 안 부른다"
    assert "선발 능력치 미확보" in said, "🔴 퇴로 머리글이 없다"
    assert "said_xi_rows == 0" in said, "🔴 XI 없는 판 예외가 없다"
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **수집은 라인업보다 먼저** — 사용자 지시 2026-10-19
    #
    #  > 사용자가 경기를 물으면 **우선 능력치부터 수집한다** .. 라인업이 안
    #  > 떴어도 .. 라인업 확정이 되면 **능력치만 가져다가 쓴다**
    #
    #  🔴 실측이 그 길을 열었다(이집트 1부): 발표 전 경기 페이지가
    #     `lineupType='lastStarting11'` 로 **11+11 + 자리·측면·번호**를 준다 →
    #     `facts.xi` 에 이미 들어온다(`parse_lineup` 이 꼴을 안 가린다).
    # ══════════════════════════════════════════════════════════════
    i_sq = said.index("_ab3.squad_fetch(")
    assert i_sq < said.index("_s2d.run("), \
        "🔴 능력치 수집이 전략 판정(⑦) **뒤**다 — 예상 XI 판에서 못 받는다"
    #  🔴🔴 **문서·검색보다도 앞이다** — 사용자 지시 *"물으면 **우선** 능력치부터"*
    #     ⚠️ 실측 2026-10-19(클루지): 전략 판정 앞에만 뒀을 때 `s4_extract` 가
    #        먼저 돌았다. 카드 상한(15분)을 검색이 먹으면 `fetch` 가 *"카드 상한을
    #        넘겨 멈췄다"* 로 능력치를 **못 받는다**.
    assert i_sq < said.index("s4_extract.run("), \
        "🔴 능력치 수집이 ③ 문서 추출 **뒤**다 — 카드 상한을 검색이 먼저 먹는다"
    #  🔴 재료(`facts`)가 생긴 **바로 뒤**여야 한다 — 그 사이에 다른 await 가
    #     끼면 또 뒤로 밀린다(실측으로 두 번 밀렸다)
    assert i_sq < said.index("s2b_base.run("), \
        "🔴 능력치 수집이 ② 바닥 확률 **뒤**다"
    assert i_sq < said.index("said_gate = "), \
        "🔴 능력치 수집이 라인업 신원 검문 **뒤**다"
    #  🔴 그런데 **검문은 신원 검문 뒤**다 — 모순 입력이 먼저 걸려야 한다
    i_gate = said.index("_ab3.xi_gate(")
    assert said.index("said_gate = ") < i_gate, \
        "🔴 능력치 검문이 라인업 신원 검문 **앞**이다 — 까닭이 섞인다"
    #  🔴 확률은 `probmodel` 을 **처음 부르는 자리**다(이름이 바뀌어도 모듈은
    #     그대로다 · 사본 금지)
    i_prob = said.index("import probmodel")
    assert i_gate < i_prob, "🔴 검문이 확률 **뒤**에 있다"
    #  🔴 ⑤-b1 이 ⑤-b1b **뒤**다(그래야 `have=` 로 다시 안 받는다)
    assert said.index("_ab3.squad_fetch(") < said.index("_ab3.fetch("), \
        "🔴 ⑤-b1 이 선발 전원보다 **먼저** 받는다(중복 통신)"
    assert "have=said_sq" in said, "🔴 받은 묶음을 재사용하지 않는다"
    #  🔴 그 글자를 **버리지 않는다**(CLAUDE.md #2 배선)
    assert "st.note(f\"⑤-b1 {line}\")" in said, "🔴 글자를 만들고 버린다"


class _P2(_P):
    """🔴 자리·측면까지 있는 선수(과거 XI 행의 모양)."""

    def __init__(self, name: str, pid: int | None, pos: str = "",
                 flank: str = "") -> None:
        super().__init__(name, pid)
        self.pos, self.flank = pos, flank


def test_ab22_오늘_XI_가_없으면_평소_XI_로_되물린다() -> None:
    """🔴🔴 **3번** — 라인업 블록이 통째로 없는 판(2026-10-19 사용자 설계).

    > 사용자가 경기를 물으면 우선 능력치부터 수집한다 .. **라인업이 안 떴어도**
    > .. 기존에 **예상 라인업 수집하는 로직**이 있다 .. 거기에 선수들을 적용한다

    ⚠️ 실측 2026-10-19(이란 `Mes Shahr Babak vs Persepolis`): 경기 페이지의
       `content.lineup` 이 **`None`** 이었다(`weather`·`table`·`h2h` 는 왔다).
    🔴 빈도 규칙은 `s2b_base.usual_xi` 가 원본이다(#1 사본 금지) — 여기서는
       **자리 최빈값**과 **되물린 사실이 사유에 남는가**를 센다.
    """
    #  🔴 세 경기: A·B 는 3회 · C 는 2회 · D 는 1회 → 빈도 순서가 정해진다
    #     A 의 자리는 CB 두 번 · RB 한 번 → **CB**(최빈값)
    past = [
        _XI([_P2("A", 1, "CB", "중앙"), _P2("B", 2, "ST", "중앙"),
             _P2("C", 3, "DM", "중앙")]),
        _XI([_P2("A", 1, "CB", "중앙"), _P2("B", 2, "ST", "중앙"),
             _P2("C", 3, "DM", "중앙")]),
        _XI([_P2("A", 1, "RB", "오른"), _P2("B", 2, "ST", "중앙"),
             _P2("D", None, "LW", "왼")]),
    ]
    facts = _F(past={"team:000001": past})
    got, why = ab.squad_of(facts, _R(), "home")
    #  🔴 ① 오늘 XI 가 없는데 **빈 목록이 아니다**(종전엔 `[]` 였다)
    assert got, why
    assert [x["name"] for x in got] == ["A", "B", "C"], got
    #  🔴 ② 자리는 **최빈값**이다(CB 2회 > RB 1회)
    assert dict((x["name"], x["pos"]) for x in got) == \
        {"A": "CB", "B": "ST", "C": "DM"}, got
    assert dict((x["name"], x["flank"]) for x in got)["A"] == "중앙", got
    #  🔴 ③ **되물린 사실이 사유에 남는다**(#3 조용한 대입 금지)
    assert "평소 XI" in why and "오늘 XI 가 없다" in why, why
    #  🔴 ④ 번호 없는 선수는 **안 담고 수를 적는다**
    assert "번호 없는 선수 1명" in why, why
    #  🔴 ⑤ 오늘 XI 가 **있으면** 그것을 쓴다(되물리지 않는다)
    f2 = _F(xi={"team:000001": _XI([_P2("Z", 9, "GK", "중앙")])}, past=
            {"team:000001": past})
    got2, why2 = ab.squad_of(f2, _R(), "home")
    assert [x["name"] for x in got2] == ["Z"], got2
    assert "평소 XI" not in why2, why2
    #  🔴 ⑥ 과거도 없으면 **그 사실을 적는다**(0 으로 때우지 않는다)
    got3, why3 = ab.squad_of(_F(), _R(), "home")
    assert got3 == [] and "과거 선발이 없다" in why3, why3


def test_ab21_카드_경로는_하루_캐시를_켠다() -> None:
    """🔴🔴 **판을 건너 능력치를 가져다 쓴다** — 사용자 지시 2026-10-19(2번).

    > 라인업 확정이 되면 **능력치만 가져다가 쓴다**

    🔴 그 저장소는 **하루 캐시**다 — `/players/` 가 `Net.DAY_CACHE` 에 있어서
       예상 XI 판(T−3h)에서 받은 선수 페이지를 확정 XI 판이 디스크에서 읽는다.
       ⚠️ 그러니 켜지지 않은 Net 으로 카드를 내면 그 재사용이 **안 된다**.
    ⚠️ 실측 2026-10-19: 운영(`app/bot/main.py`)은 켰는데 `tools/v6_run.py` ·
       `tools/layer1_review.py` 는 `Net()` 맨몸이었다 — 둘 다 **카드를 내는
       길**(`pipeline.analyze`)이다. 손으로 맞추는 세 자리는 갈린다(#1) →
       🔴 **한 곳**(`net.card_net`)에서 만든다.
    """
    from app import net as _net
    #  🔴 ① 그 한 곳이 실제로 켜 준다(행동으로 센다 · 글자 검사 아님)
    got = _net.card_net()
    assert got._day_path("https://www.fotmob.com/players/1/x", "") is not None, \
        "🔴 `/players/` 가 하루 캐시에 안 담긴다 — 판을 건너 못 쓴다"
    #  🔴 ② `/match/` 는 **담지 않는다**(라인업이 굳으면 확정 XI 가 와도 안 바뀐다)
    assert got._day_path("https://www.fotmob.com/match/1", "") is None, \
        "🔴 경기 페이지가 하루 캐시에 담긴다 — 예상 XI 가 굳는다"
    #  🔴 ③ **카드를 내는 길은 전부** 그 한 곳을 쓴다
    #     ⚠️ **D46** — 주석·독스트링을 빼고 **코드만** 본다. 주석이 옛 `Net()` 을
    #        *설명하는* 것과 코드가 그것을 *부르는* 것은 다르다(한 번 걸렸다).
    from tests._helpers import strip_docs
    for rel in ("app/bot/main.py", "tools/v6_run.py", "tools/layer1_review.py"):
        code = strip_docs((ROOT / rel).read_text(encoding="utf-8"))
        assert "card_net(" in code, f"🔴 {rel} 가 카드용 Net 을 안 쓴다"
        #  ⚠️ 맨몸 `Net()` 으로 카드를 내면 판을 건너는 재사용이 깨진다
        assert "Net()" not in code.replace("card_net()", ""), \
            f"🔴 {rel} 에 맨몸 `Net()` 이 남아 있다"


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
    #  🔴 **표가 또 자랐다**(2026-10-19 · 사용자 지시 *"안전장치를 만들어라"*) —
    #     `xi_ability_min_per_side`(선발 능력치 최소 인원)가 더해졌다.
    #     ⚠️ 그것도 **사용자가 정한 손값**이다: *"선발 11명 능력치를 받지
    #        못하면 분석은 무의미하다"*. 0 으로 두면 검문이 꺼진다.
    assert set(box) == {"strong", "weak", "branches", "branch_gap",
                        "branch_min", "squad_cap_per_side",
                        "count_slack", "xi_ability_min_per_side"}, sorted(box)
    #  🔴 그 값은 **정수**이고 음수가 아니다(0 이면 검문 꺼짐)
    said_min = box["xi_ability_min_per_side"]
    assert isinstance(said_min, int) and 0 <= said_min <= 11, said_min
    assert "선발 11명 능력치를 받지 못하면" in said
    #  🔴 **값을 바꿀 때는 까닭을 적는다**(#3) — 11 → 8 은 실측에서 왔다
    #     (이집트 1부는 능력치를 주는데도 팀별 9/11 · 8/11 이었다).
    if said_min != 11:
        assert "이집트" in said and "우크라이나" in said, \
            "🔴 문턱을 내렸는데 그 까닭(실측)이 파일에 없다"
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
