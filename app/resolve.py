"""🔴🔴 **어느 리그인가** — 사용자가 경기를 물으면 밟는 **여섯 단**.

사용자 지시 2026-10-03:

> 사용자가 경기 질문을 하면 **어느 리그부터 검색을 해야 하는지 단계별로 세세하게**
> 봇이 찾아야 한다. **러프하게 코드 작성을 하지 말아라.**

══════════════════════════════════════════════════════════════════
🔴 근본 원인 (측정 2026-10-03) — 그 단계가 **아예 없었다**
══════════════════════════════════════════════════════════════════

```
aliases.find_team("감바 오사카")  →  ('soccer', 'Gamba Osaka')
                                     ^^^^^^^^ 🔴 **종목**이다. 리그가 아니다
```
그래서 매 질문이 `리그 미상` 으로 갔고, 그 하나에서 넷이 따라 무너졌다:

| 무너진 것 | 모양 |
|---|---|
| 언어 | 영어 고정 → `LG Twins 선발 라인업 Oct 3`(반쯤 한국어) |
| 어댑터 | KBO 어댑터가 있어도 `soccer` 라 못 닿는다 |
| 소스 | `kia.com`(자동차) · `nba.com` · `golf.com` 을 열었다 |
| 결과 | 사실 0~5건 → *"자료 부족"* |

🔴 **순서가 곧 규율이다** — 위 단이 답하면 **아래를 안 본다**. 확실한 것부터다.
⚠️ 각 단은 **사유를 남긴다.** 어느 단이 정했는지 모르면 틀렸을 때 못 고친다.
"""
from __future__ import annotations

import inspect
import json
import logging
import urllib.parse
from dataclasses import dataclass, field
from datetime import date

from app import league_index as LI

logger = logging.getLogger(__name__)

#: 🔴 팀 하나의 리그를 **직접** 묻는 길. ⚠️ 명단 받기와 다르다 — **안 잘린다**
#   (실측 2026-10-03: 명단은 열 팀에서 잘리는데 이 길은 그 팀의 리그를 그대로 준다).
ASK_TEAM = "https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t="

#: 🔴 대표팀 선언 — `press_langs` 예외표가 여기 있다(원본 하나)
NATIONS = "config/nations.yaml"


@dataclass
class Resolved:
    """🔴 어느 리그인가 — **그리고 어떻게 알았나**."""

    league: str = ""
    #: 그 리그 기사의 언어(명부가 정한다). 못 정하면 빈 tuple
    langs: tuple[str, ...] = ()
    sport: str = ""
    #: `ADAPTERS` 열쇠. 🔴 빈 문자열이면 **일정을 직접 못 받는다**(검색으로 간다)
    adapter: str = ""
    #: 🔴 밟은 단계들 — 맞은 단과 **빗나간 단**을 다 적는다(#3 조용한 0 금지)
    steps: list[str] = field(default_factory=list)
    #: 받은 현지 표기(`柏レイソル`) — 검색어가 여기서 나온다
    local: str = ""
    #: 🔴 ④단이 **별칭 보조로만** 받은 표기(§8-4). ⚠️ 리그를 아는 뒤에만 쓴다 —
    #  리그를 모르면 어느 언어가 현지어인지도 모른다(실측 2026-10-03).
    ask_local: str = ""
    #: 🔴 **그 경기가 속한 대회**(`League Cup`·`CONCACAF Nations League`).
    #
    #  ⚠️ 리그와 **다르다.** 컵·대륙대회는 명부에 없고 언어·어댑터를 못 준다.
    #     실측 2026-10-03: `Kashiwa Reysol` 이 표에서 `League Cup` 으로 잡혀
    #     **거기서 멈췄고**, 그 바람에 일본어가 안 붙었다(J리그면 `ja` 다).
    #  🔴 그래서 대회는 **적어 두되 사다리를 멈추지 않는다** — 리그는 계속 찾는다.
    competition: str = ""

    @property
    def known(self) -> bool:
        return bool(self.league)

    def note(self) -> str:
        """카드·로그에 적을 한 덩어리."""
        head = (f"리그 **{self.league}**(언어 {list(self.langs)}"
                + (f" · 어댑터 `{self.adapter}`" if self.adapter
                   else " · 🔴 어댑터 없음 — 일정은 검색으로 찾는다") + ")"
                if self.known else
                "🔴 **리그 미상** — 아래 단계가 전부 빗나갔다")
        if self.competition:
            head += f" · 대회 `{self.competition}`"
        return head + "\n" + "\n".join(f"   {i + 1}. {s}"
                                       for i, s in enumerate(self.steps))


def _local(got: Resolved, team: str) -> None:
    """🔴 그 리그의 **현지 표기**를 이름표에서 꺼내 채운다.

    ⚠️ 리그를 **모르면 꺼내지 않는다.** 실측 2026-10-03: 대표팀(`Croatia`)은
       리그가 없어 언어 목록이 비었는데 아무 언어나 집어 **포르투갈어 `Croácia`**
       가 현지 표기로 붙었다 — 그 글자로 검색하면 엉뚱한 데로 간다.
    🔴 어느 단이 리그를 정했든 **같은 자리에서** 꺼낸다 — ②단이 정하고 ③단을 안
       밟으면 표기가 비던 것이 그 때문이다(한 곳에서 하면 빠질 수가 없다).
    """
    if got.local:
        return
    # 🔴🔴 **리그가 없어도 언어를 알면 꺼낸다**(2026-10-04).
    #
    #  ⚠️ 종전 조건은 `not got.league` 였다 — 대표팀은 리그가 없어 **늘 건너뛰었고**,
    #     그래서 현지 표기가 비어 질의가 영어로 갔다. 그 조건이 막으려던 것은
    #     *"리그를 모르면 **아무 언어나** 집어 포르투갈어 `Croácia` 가 붙는 것"*
    #     이었다. 🔴 지금은 사다리 ②가 **그 나라의 언어**를 Babel 로 안다 —
    #     아무 언어가 아니다. 그래서 `got.langs` 가 있으면 그것을 쓴다.
    langs = tuple(got.langs or ()) or tuple(LI.langs_of(got.league) or ())
    if not langs:
        return
    from app import teamref
    key, _why = teamref.key_of(team)
    if not key:
        return
    for lang in langs:
        if lang == "en":
            continue
        lab = teamref.label_of(key, lang)
        if lab:
            got.local = lab
            return
    # 🔴 이름표가 그 언어를 모르면 ④단이 받아 둔 표기를 **대체로** 쓴다(§19-b-4).
    #    ⚠️ 여기까지 왔다는 것은 **리그·언어를 안다**는 뜻이다 — 그때만 안전하다.
    if got.ask_local and not got.local:
        got.local = got.ask_local


def _fill(got: Resolved, key: str) -> Resolved:
    got.league = key
    got.langs = LI.langs_of(key)
    got.sport = LI.sport_of(key)
    got.adapter = LI.adapter_of(key)
    return got


def _by_names(text: str, got: Resolved) -> bool:
    """① 질문에 **리그 이름**이 있나. 🔴 사용자가 말했으면 추측할 것이 없다."""
    low = f" {str(text or '').lower()} "
    for lg in LI.leagues():
        for nm in (lg.get("names") or []):
            if str(nm).lower() in low:
                _fill(got, str(lg["key"]))
                got.steps.append(f"① 질문에 `{nm}` 가 있다 → **{got.league}**")
                return True
    got.steps.append("① 질문에 리그 이름이 없다")
    return False


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **대표팀은 리그가 없다 — 그래도 종목·언어는 알 수 있다** (2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
#  사용자 지시 2026-10-04:
#
#  > A는 당연하고(**어댑터가 종목을 이미 선언했는데 안 물은 건 결함**) ... C는 손으로
#  > 안 적어도 된다 — 이미 넣은 Babel 이 그걸 한다.
#
#  ⚠️ 실측 2026-10-04(북마케도니아 vs 스코틀랜드): 사다리가 **리그 미상**으로 끝나
#     `sport=''`·`langs=('en',)` 이 됐다. 그 하나에서 검색이 통째로 무너졌다 —
#     `Scotland lineup Oct 3` 가 **드라마 출연진**(rottentomatoes)과 **럭비**를
#     끌어왔고, 쓰레기 76건이 LLM 예산을 다 먹어 진짜 프리뷰에 0초가 남았다.
#
#  🔴 **지어낼 것이 하나도 없다.** 둘 다 이미 저장소에 적혀 있다:
#
#      종목 ← `games.ext_id` 접두(`fotmob-5181780`) → 어댑터 → `SPORT = "soccer"`
#      언어 ← 이름표가 담아 둔 나라 코드(`iso:MK`) → Babel CLDR → `mk`
#
#  ⚠️ **리그는 여전히 미상이다.** 종목·언어만 채운다 — 리그를 고르면 그것이 추측이다.


def _sport_from_ext(ext_id: str) -> tuple[str, str]:
    """🔴 `ext_id` → 그 자료를 만든 어댑터 → 그 어댑터가 **선언한** 종목.

    ⚠️ 어댑터 고르는 규칙은 `collect.ingest.adapter_of` **하나**다 — 여기 또 적지
       않는다(#1 사본 금지). 그 함수가 `ext_id` 접두까지 본다.
    🔴 어댑터가 `SPORT` 를 안 적어 두면 **빈 값**이다(지어내지 않는다).
    """
    if not ext_id:
        return "", "`ext_id` 가 없다"
    try:
        from app.collect import ingest
        mod = ingest.adapter_of(ext_id=str(ext_id))
    except Exception as exc:                            # noqa: BLE001
        return "", f"어댑터를 못 찾았다 — {exc!r}"
    if mod is None:
        return "", f"`{ext_id}` 접두를 아는 어댑터가 없다"
    got = str(getattr(mod, "SPORT", "") or "")
    name = getattr(mod, "__name__", "?").rsplit(".", 1)[-1]
    if not got:
        return "", f"어댑터 `{name}` 이 `SPORT` 를 선언하지 않았다"
    return got, f"어댑터 `{name}` 이 `SPORT = {got!r}` 이라고 선언한다"


def nation_langs(team: str) -> tuple[tuple[str, ...], str]:
    """🔴🔴 **그 대표팀 기사의 언어** — 이름표의 나라 코드 + Babel CLDR.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 손으로 안 적나 (사용자 지시 2026-10-04)
    ══════════════════════════════════════════════════════════════════

    `Locale.parse('und_MK')` → `mk`. 나라 코드 하나로 CLDR 이 **가장 그럴듯한
    언어**를 준다. ⚠️ 그 코드는 이름표가 **이미 담고 있다** — `_from_cldr` 이
    `iso:MK` 를, `_from_nations` 이 `fa:SCO` 를 이름으로 붙여 뒀다.

    🔴 예외는 `config/nations.yaml` 의 `press_langs` **여섯 줄**뿐이고, 그 까닭이
       거기 적혀 있다(ISO 코드가 없는 축구협회 넷 · CLDR 언어 ≠ 기사 언어).
    ⚠️ 영어는 **늘 끝에 붙인다** — 어느 나라 경기든 영어 프리뷰가 있다. 🔴 그런데
       **맨 앞에 두지 않는다**: 현지어가 먼저여야 현지 매체가 손에 들어온다.
    """
    from app import rules, teamref
    key, why = teamref.key_of(team)
    if not key:
        return (), f"`{team}` 을 열쇠로 못 바꿨다 — {why}"
    ref = teamref.registry().teams.get(key)
    if ref is None:
        return (), f"`{key}` 가 이름표에 없다"
    # 🔴 이름표가 담아 둔 **코드**를 찾는다(`iso:MK`·`fa:SCO`). 라벨이 아니라
    #    이름 목록에 들어 있다 — `is_code()` 가 라벨에서만 뺀다.
    codes = [nm for box in ref.names.values() for nm in box
             if teamref.is_code(nm) and nm.split(":", 1)[0] in ("iso", "fa")]
    if not codes:
        return (), f"`{key}` 에 나라 코드가 없다 — 대표팀이 아닌 것 같다"
    table = dict(rules._load(NATIONS).get("press_langs") or {})
    out: list[str] = []
    hows: list[str] = []
    for code in sorted(set(codes)):
        said = [str(x) for x in (table.get(code) or [])]
        if said:
            hows.append(f"`{code}` → {said} (선언 · nations.yaml `press_langs`)")
        else:
            said, how = _babel_lang(code)
            hows.append(how)
        for lg in said:
            if lg and lg not in out:
                out.append(lg)
    if "en" not in out:
        out.append("en")                 # 🔴 끝에 — 현지어가 먼저다
    return tuple(out), " · ".join(hows)


def _babel_lang(code: str) -> tuple[list[str], str]:
    """🔴 `iso:MK` → CLDR likely-subtag → `['mk']`. 못 풀면 빈 목록."""
    cc = str(code).split(":", 1)[-1]
    if len(cc) != 2 or not cc.isalpha():
        # ⚠️ `fa:SCO` 는 세 글자다 — **두 글자로 줄이지 않는다**(`SC` 는 세이셸이다)
        return [], (f"`{code}` 는 두 글자 나라 코드가 아니다 — Babel 에 묻지 않는다"
                    f"(🔴 줄이면 `SC`=세이셸·프랑스어가 된다)")
    try:
        from babel import Locale
        lang = str(Locale.parse(f"und_{cc.upper()}").language or "")
    except Exception as exc:                            # noqa: BLE001
        return [], f"`{code}` — Babel 이 모른다({type(exc).__name__})"
    if not lang:
        return [], f"`{code}` — Babel 이 언어를 안 줬다"
    return [lang], f"`{code}` → `{lang}` (CLDR likely-subtag)"


async def _by_games(pool, team: str, got: Resolved) -> bool:
    """② **이미 쌓아 둔 경기**에 그 팀이 있나. 🔴 리그가 그 행에 적혀 있다."""
    if pool is None or not team:
        got.steps.append("② 표를 못 본다(연결 없음)")
        return False
    try:
        row = await pool.fetchrow(
            # 🔴 `ext_id` 도 받는다 — 리그가 명부에 없을 때 **종목이 거기 있다**
            #    (2026-10-04: `fotmob-5181780` → `fotmob.SPORT == "soccer"`)
            "SELECT league, ext_id FROM games WHERE home = $1 OR away = $1 "
            "ORDER BY starts_utc DESC LIMIT 1", team)
    except Exception as exc:                            # noqa: BLE001
        got.steps.append(f"② 표 조회 실패 — {exc!r}")
        return False
    if not row or not row["league"]:
        got.steps.append(f"② 쌓인 경기에 `{team}` 이 없다")
        return False
    key = str(row["league"])
    if any(str(lg["key"]) == key for lg in LI.leagues()):
        _fill(got, key)
        got.steps.append(f"② 쌓인 경기가 `{key}` 라고 한다 → **{got.league}**")
        return True
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **대회 이름은 리그가 아니다** — 멈추지 않는다(실측 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  표의 `league` 칸에는 **그 경기가 속한 대회**가 들어간다. 컵·대륙대회는
    #  명부에 없다: `League Cup` · `CONCACAF Nations League A Grp. 2` · `Friendlies`.
    #  ⚠️ 종전에 여기서 **멈췄다.** 그래서 가시와(J리그)가 `League Cup` 으로 잡혀
    #     **일본어가 안 붙었다** — 컵 경기도 기사는 일본 매체가 쓴다.
    #  🔴 대회는 **적어 두고**(카드가 그것을 보여 준다) 리그는 **계속 찾는다.**
    got.competition = key
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **리그는 몰라도 종목·언어는 안다** (사용자 지시 2026-10-04 보기 A·C)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전에는 여기서 **빈손으로** 내려갔다. 그래서 대표팀 경기가 전부
    #     `sport=''`·`langs=('en',)` 이 되고, 검색어가 나라 이름 하나가 됐다.
    #  🔴 둘 다 **선언에서** 온다 — 지어내는 것이 하나도 없다.
    # ⚠️ `ext_id` 칸이 없을 수도 있다(오래된 행·시험 대역) — **터지지 않는다.**
    #    🔴 없으면 사유로 남는다(조용히 빈손으로 가지 않는다).
    try:
        ext = str(dict(row).get("ext_id") or "")
    except Exception:                                   # noqa: BLE001
        ext = ""
    sp, how = _sport_from_ext(ext)
    if sp and not got.sport:
        got.sport = sp
        got.steps.append(f"② 🔴 리그는 몰라도 **종목은 `{sp}`** — {how}")
    else:
        got.steps.append(f"② 종목도 못 알았다 — {how}")
    langs, lhow = nation_langs(team)
    if langs and not got.langs:
        got.langs = langs
        got.steps.append(f"② 🔴 **기사 언어 {list(langs)}** — {lhow}")
    else:
        got.steps.append(f"② 언어를 못 알았다 — {lhow}")
    got.steps.append(f"② 쌓인 경기는 `{key}` — **대회 이름이지 리그가 아니다**. "
                     f"⚠️ 리그는 계속 찾는다(어댑터는 리그에서만 온다)")
    return False


async def _by_index(team: str, got: Resolved, *, net=None,
                    offline: bool = False) -> bool:
    """③ **이름표가 아는 팀**인가 — 🔴 **어느 언어로 물어도** 같은 열쇠로 푼다.

    ══════════════════════════════════════════════════════════════════
    🔴 1단계 — *"이름표는 ID 밑에 붙는다"*(사용자 지시 2026-10-03)
    ══════════════════════════════════════════════════════════════════

    ⚠️ 종전 이 단은 **받아 둔 명단의 글자**와 맞춰 봤다. 그래서 `크로아티아` 는
       못 찾고 `Croatia` 만 찾았다 — *"이름을 신원으로 쓴다"* 는 그 병이다.
    🔴 이제 `teamref` 가 **ID 로 모아 둔 이름표**를 본다: CLDR 나라 이름(ko·ja·
       en·es·zh) · 축구협회 넷 · 받아 둔 클럽 이름과 현지 표기 · 한국어 별칭.
    ⚠️ 모호하면(`Monaco` 가 나라와 클럽 둘) **고르지 않는다** — 사유를 남기고
       다음 단으로 간다(거짓 매칭보다 미상이 낫다).
    """
    from app import teamref
    # 🔴 명단 캐시가 비어 있으면 **받아 온다** — 이름표의 클럽 쪽이 거기서 온다.
    #    ⚠️ 캐시가 이미 있으면 통신하지 않는다(`_fresh` 가 TTL 을 본다).
    if offline is False:
        await LI.build(net=net)
    key, why = teamref.key_of(team)
    if not key:
        got.steps.append(f"③ 이름표: {why}")
        return False
    ref = teamref.registry().teams.get(key)
    if not ref or not ref.league:
        # ⚠️ 나라(대표팀)는 **리그가 없다** — 열쇠는 풀렸지만 리그는 아직 모른다.
        #    🔴 그 사실을 적고 다음 단으로 간다(④가 대회를 알 수 있다).
        got.steps.append(f"③ 이름표가 `{team}` 을 **`{key}`** 로 푼다 — "
                         f"⚠️ 그런데 리그가 없다(대표팀은 대회만 있다)")
        return False
    _fill(got, ref.league)
    _local(got, team)
    got.steps.append(f"③ 이름표가 `{team}` → **`{key}`** · 리그 **{got.league}**"
                     + (f" · 현지 표기 `{got.local}`" if got.local else ""))
    return True


async def _by_ask(team: str, got: Resolved, *, net=None) -> bool:
    """④ 🔴 **팀 이름으로 직접 물어본다** — ⚠️ **리그는 정하지 않는다**(§8-4).

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **v5 §8-4 로 이 단의 일이 줄었다** (2026-10-04)
    ══════════════════════════════════════════════════════════════════

    > TheSportsDB 는 **명단·리그 판정에 쓰지 않는다**(잘림·거짓 명단).
    > 팀 검색(`searchteams.php?t=`)**만 별칭 보조.** [#7]

    ⚠️ 종전 이 단은 응답의 `strLeague` 로 **리그를 확정했다.** 🔴 그 길을 걷는다 —
       같은 서비스가 명단은 열 개로 자르고 `lookup_all_teams` 는 id 를 무시해
       **영국 2부 24팀**을 준다(실측 2026-10-03). 그 응답의 리그를 믿을 근거가 없다.
    ✅ **남는 것은 현지 표기다** — `strTeamAlternate` 가 `柏レイソル` 을 준다.
       검색어 품질이 거기서 나온다(§4-1 사다리 ②).
    🔴 그래서 **언제나 `False`** 를 돌려준다 — 사다리가 ⑤·⑥으로 계속 간다.
    """
    from app.net import Net
    if not team:
        return False
    fetched = await (net or Net()).get(ASK_TEAM + urllib.parse.quote(team))
    if not getattr(fetched, "ok", False):
        got.steps.append(f"④ 팀 조회 실패 — {getattr(fetched, 'reason', '사유 없음')}")
        return False
    try:
        rows = (json.loads(fetched.text).get("teams") or [])
    except ValueError:
        got.steps.append("④ 팀 조회가 JSON 을 안 줬다")
        return False
    if not rows:
        got.steps.append(f"④ 팀 조회가 `{team}` 을 모른다(0건)")
        return False
    row = rows[0] if isinstance(rows[0], dict) else {}
    said = str(row.get("strLeague") or "")
    alt = str(row.get("strTeamAlternate") or "").split(",")[0].strip()
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **현지 표기만 받는다.** ⚠️ 리그를 아는 때만 그 표기를 쓴다 —
    #    리그를 모르면 **어느 언어가 현지어인지도 모른다**(실측 2026-10-03:
    #    `Croatia` 에 포르투갈어 `Croácia` 가 달라붙었다).
    #    🔴 그래서 여기서는 **적어 두고**, 쓰는 것은 `_local` 이 리그·언어를
    #       안 뒤에 정한다.
    if alt:
        got.ask_local = alt
    got.steps.append(
        f"④ 팀 조회가 `{said or '리그 미상'}` 이라는데 🔴 **§8-4 — 리그 판정에 "
        f"쓰지 않는다**(tsdb 는 명단을 열 개로 자르고 거짓 명단을 준다)"
        + (f" · 별칭 보조로 현지 표기 `{alt}` 만 받았다" if alt else ""))
    return False

def _by_sport(team: str, got: Resolved) -> bool:
    """⑤ **종목만이라도** 좁힌다. 🔴 리그를 고르지는 않는다.

    ⚠️ 야구 질문에 축구 리그를 보는 것을 막는다 — 그것만으로도 소스가 줄어든다.
    🔴 종목 하나로 리그를 **고르면 그것이 추측이다**(종목당 리그가 여럿이다).
    """
    from app.bot import aliases
    hit = aliases.find_team(team)
    if not hit:
        got.steps.append(f"⑤ 별칭표도 `{team}` 을 모른다")
        return False
    tag = str(hit[0])
    want = {"mlb": "baseball", "kbo": "baseball", "soccer": "soccer"}.get(tag, "")
    cands = [str(lg["key"]) for lg in LI.leagues()
             if not want or str(lg.get("sport")) == want]
    got.sport = want
    got.steps.append(f"⑤ 별칭표가 종목 `{tag}` 이라고 한다 — 후보 {cands} "
                     f"(🔴 하나를 고르지는 않는다)")
    return False


async def _by_openworld(got, *, team: str, opponent: str = "",
                        unresolved: tuple[str, ...] = (), net=None):
    """🔴🔴 ⑥ **오픈월드 단** — 모르는 팀을 공개 페이지로 배운다(지시서 §2).

    돌려주는 것: 확정했으면 `Resolved`, 아니면 `None`(호출부가 사유를 적는다).

    흐름: ⑥-1 철자 후보(Solar) → ⑥-2 후보 검색(코드) → ⑥-3 경기 페이지 확인
          (코드) → ⑥-4 임시 열쇠 → ⑥-5 리그·언어

    ⚠️ **밟은 단을 다 적는다**(#3) — 못 찾았을 때 *"⑥-1 후보가 무엇이었고
       ⑥-2 가 몇 건을 냈고 ⑥-3 이 왜 떨어뜨렸나"* 가 카드에 남아야, 사용자가
       철자를 바꿔 주면 풀릴지 **판단할 수 있다**(지시서 §4 자료 부족 카드).
    """
    from app import openworld
    from app.matchref import Reason
    asked = " vs ".join(x for x in (team, opponent) if str(x or "").strip())
    # ⚠️ `Lookup` 에는 팀 열쇠 칸이 없다 — 이름 해석이 **무엇을 못 풀었나**를
    #    호출부가 글로 넘긴다(`unresolved`). 🔴 빈 칸이 있으면 ⑥ 이 돈다.
    ok, why = openworld.may_run(resolved_names=list(unresolved) or ["", ""])
    got.steps.append(f"⑥ 오픈월드 — {why}")
    if not ok:
        return None
    # ⑥-1 철자 후보
    box, dropped, said = openworld.read_names(asked)
    got.steps.append(f"⑥-1 {said}")
    for d in dropped[:3]:
        got.steps.append(f"⑥-1 🔴 **버린 칸**(§5 M54 — 확정은 코드만): {d}")
    teams = box.get("teams") or []
    if len(teams) < 2:
        got.reason = Reason.OPENWORLD_NOT_FOUND
        got.steps.append("⑥-1 🔴 두 팀을 못 읽었다 — 철자를 다르게 적어 달라")
        return got
    # ══════════════════════════════════════════════════════════════════
    # ⑥-2 **후보 검색**(코드) — v5 §4 통로. 지시서 §2 ⑥-2
    # ══════════════════════════════════════════════════════════════════
    #
    #  > `{팀A 후보} {팀B 후보}` 조합으로 v5 §4 통로(SearXNG → GDELT → Bing
    #  > RSS)를 친다. 검색어 규칙(§4-1)은 이 단에서도 적용하되 **두 팀명이
    #  > 요소 둘로** 센다. — 지시서 §2 ⑥-2
    from app.search import build_chain
    a = (teams[0].get("latin_candidates") or [teams[0].get("ko") or ""])[:2]
    b = (teams[1].get("latin_candidates") or [teams[1].get("ko") or ""])[:2]
    country = str(teams[0].get("country_guess") or "")
    langs = openworld.langs_for(country)
    chain = build_chain()
    urls, tried = [], []
    for x in a:
        for y in b:
            # 🔴 §4-1 — **두 팀명이 요소 둘**이고 종목 낱말을 더해 셋이다
            from app import rules as _R
            word = _R.sport_word("soccer", langs[-1]) or "football"
            q = f"{x} {y} {word}"
            tried.append(q)
            try:
                hits = await chain.query(q, lang=langs[0])
            except Exception as exc:                    # noqa: BLE001
                got.steps.append(f"⑥-2 🔴 검색 실패 `{q}` — {exc!r}")
                continue
            urls += [str(getattr(h, "url", "") or "") for h in (hits or [])]
            got.steps.append(f"⑥-2 `{q}` → {len(hits or [])}건")
    seen, uniq = set(), []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            uniq.append(u)
    got.steps.append(f"⑥-2 주소 {len(uniq)}개(중복 제거)")
    # ⑥-3 **경기 페이지 확인**(코드) — 🔴 기존 파서를 쓴다(§3-1)
    pages, dropped = await openworld.pages_from(uniq[:12], net=net)
    got.steps.append(f"⑥-3 후보 경기 {len(pages)}개 · 탈락 {len(dropped)}건")
    for d in dropped[:3]:
        got.steps.append(f"⑥-3 탈락 — {d}")
    page, why3 = openworld.pick(pages, a, b)
    got.steps.append(f"⑥-3 {why3}")
    if page is None:
        got.reason = Reason.OPENWORLD_NOT_FOUND
        # 🔴 **시도한 검색어·URL 을 적는다**(지시서 ⑥-3: 0개면 그 목록을 카드에)
        got.steps.append(f"⑥-3 던진 검색어: {tried[:4]}")
        got.steps.append(f"⑥-3 본 주소: {[u[:60] for u in uniq[:4]]}")
        return got
    # ⑥-4 **임시 열쇠** · ⑥-5 리그·언어
    rows = openworld.provision(
        page, ko=[str(t.get("ko") or "") for t in teams],
        latin=[list(t.get("latin_candidates") or []) for t in teams],
        country=country)
    for r in rows:
        got.steps.append(
            f"⑥-4 임시 열쇠 `{r['key']}` ← {r['name']} · 별칭 {r['aliases']} "
            f"· learned_from {str(r['learned_from'])[:60]}")
    got.league = str(page.get("competition") or "")
    got.langs = tuple(rows[0]["langs"]) if rows else tuple(langs)
    got.steps.append(f"⑥-5 리그 `{got.league}` · 언어 {list(got.langs)} "
                     f"(🔴 `leagues.yaml` 에 **안 넣는다**)")
    got.reason = Reason.OK
    return got


#: 🔴🔴 **사다리의 마지막 단** — 지시서 §2 (2026-10-05).
#
#  > 지금 `resolve()` 는 이름표에 없으면 `name_unresolved` 로 멈춘다. 그 뒤에
#  > **사다리 한 단(⑥ 오픈월드)** 을 추가한다. **순서는 바꾸지 않는다** — 아는
#  > 팀은 지금처럼 빠르고 결정적으로 풀리고, **모를 때만** 이 단이 돈다.
#
#  ⚠️ 이름이 글자로 적혀 있는 까닭: 계약(§5 M53)이 *"⑥ 이 맨 뒤인가"* 를 **이
#     선언으로** 본다. 🔴 ⑥ 을 앞으로 옮기면 아는 팀 질문도 Solar 를 부른다.
LADDER_LAST = "openworld"


async def league_of(team: str, *, pool=None, text: str = "", net=None,
                    offline: bool = False) -> Resolved:
    """🔴🔴 **선언한 사다리를 그대로 밟는다.** 위 단이 답하면 아래를 안 본다.

    ══════════════════════════════════════════════════════════════════
    🔴 순서는 **`config/leagues.yaml` 의 `ladder:` 가 원본이다**
    ══════════════════════════════════════════════════════════════════

    ⚠️ 순서를 코드에도 적으면 **사본**이 되고, yaml 을 고쳐도 봇이 안 따라온다
       (CLAUDE.md #1). 그래서 여기서는 **선언을 읽어 돌린다.**
    🔴 선언에 모르는 단(`how`)이 있으면 **조용히 건너뛰지 않고** 사유를 적는다 —
       오타 하나가 단계를 통째로 없애는 자리다.

    `text` 는 사용자가 쓴 문장 전체다(리그 이름이 거기 들어 있을 수 있다).
    🔴 `offline=True` 면 **통신하는 단을 건너뛴다** — 시험·배치가 조용히
       네트워크에 나가는 것이 이 저장소가 다친 자리다. ⚠️ 건너뛴 사실을 적는다
       (안 밟은 단과 밟았는데 빗나간 단은 다르다).
    """
    got = Resolved()
    #: 🔴 `how` → 그 단을 밟는 함수. ⚠️ `online` 은 **통신하는 단**이라는 표시다.
    steps = {
        "names": (False, lambda: _by_names(text or team, got)),
        "games_table": (False, lambda: _by_games(pool, team, got)),
        # ══════════════════════════════════════════════════════════════
        # 🔴 **③단은 통신하는 단이 아니다**(실측 2026-10-03)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ `online=True` 로 뒀더니 `offline` 에서 **이름표 조회 자체가** 막혔다.
        #     이름표는 **캐시만 본다**(CLDR 은 라이브러리, 클럽은 받아 둔 파일) —
        #     통신하는 것은 *"캐시가 비었을 때 명단을 받는 것"* 뿐이다.
        #  🔴 그래서 `online=False` 로 두고, **그 안에서** `offline` 이면 받기만
        #     건너뛴다. 그러면 캐시가 있는 한 시험도 라이브와 같은 답을 낸다.
        "team_index": (False,
                       lambda: _by_index(team, got, net=net, offline=offline)),
        "ask_team": (True, lambda: _by_ask(team, got, net=net)),
        "sport_only": (False, lambda: _by_sport(team, got)),
        "unknown": (False, lambda: _unknown(got)),
    }
    for row in LI.ladder():
        how = str(row.get("how") or "")
        pair = steps.get(how)
        if pair is None:
            got.steps.append(f"⚠️ 선언에 모르는 단 `{how}` 가 있다 — 건너뛴다")
            continue
        online, fn = pair
        if online and offline:
            got.steps.append(f"`{how}` 건너뜀 — **통신하지 않는다**(`offline`)")
            continue
        done = fn()
        if inspect.isawaitable(done):
            done = await done
        if done:
            # 🔴 **어느 단이 정했든** 현지 표기를 같은 자리에서 꺼낸다
            #    (실측 2026-10-03: ②단이 정하면 표기가 비어 질의가 영어로 갔다)
            _local(got, team)
            return got
    _local(got, team)
    return got


def _unknown(got: Resolved) -> bool:
    """⑥ 🔴 **하나를 고르지 않는다** — 고르면 그것이 추측이다."""
    got.steps.append("🔴 **리그 미상으로 간다** — 하나를 고르면 그것이 추측이다. "
                     "⚠️ 언어가 영어로 고정되고 어댑터를 못 쓴다")
    return False


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **입구** — 이름을 ID 로 바꾸는 곳은 여기 하나다 (2단계)
# ══════════════════════════════════════════════════════════════════


def _label(team: str, lang: str) -> str:
    """🔴 그 팀을 **그 언어로** 뭐라 부르나. 1단계 이름표가 답한다."""
    from app import teamref
    key, _why = teamref.key_of(team)
    return teamref.label_of(key, lang) if key else ""


def canon(team: str, lang: str = "en") -> tuple[str, str]:
    """🔴🔴 **사용자가 쓴 말 → 그 언어의 표준 표기**와 사유.

    ⚠️ 이것이 *"입구에서 단 한 번"* 의 알맹이다. 뒤 단계는 **이 결과만** 쓴다 —
       사용자가 쓴 원문으로 다시 비교하면 그 순간 병이 돌아온다.
    🔴 못 풀면 **원문 그대로** 돌려주고 그 사실을 사유에 적는다(지어내지 않는다).
    """
    from app import teamref
    key, why = teamref.key_of(team)
    if not key:
        return team, f"🔴 `{team}` 를 열쇠로 못 바꿨다 — {why}"
    got = teamref.label_of(key, lang)
    return (got or team), f"`{team}` → `{key}` · {lang} 표기 `{got or team}`"


async def match_of(pool, *, team: str, opponent: str = "", day=None,
                   days: int = 2, league: str = "", look_up: bool = True,
                   net=None):
    """🔴🔴 **질문 → 경기 하나**(또는 왜 못 찾았나). 이름 해석은 **여기뿐**이다.

    ══════════════════════════════════════════════════════════════════
    🔴 순서 — 확실한 것부터
    ══════════════════════════════════════════════════════════════════

    ```
    ① 이름 → 열쇠·표준 표기   (1단계 이름표)
    ② 리그 → 언어·어댑터      (여섯 단 사다리)
    ③ 쌓아 둔 표에서 찾기      — 🔴 **표준 표기로** 찾는다
    ④ 어댑터로 일정 받기       — 리그에 어댑터가 있을 때만
    ⑤ 봇이 직접 찾기          — 자동완성 → 검색
    ⑥ 적은 **그 행의 이름**으로 되찾기
    ```
    🔴 실패하면 **enum** 을 돌려준다 — 사람이 사유 문장을 짓지 않는다.
    ⚠️ 경기를 **고르지 않는다** — 여럿이면 `AMBIGUOUS` 와 후보를 돌려준다.
    """
    from app import matchref, slate
    from app.matchref import Reason
    got = matchref.Lookup()
    asked_t, asked_o = team, opponent

    # ① 이름 → 열쇠·표준 표기
    team, why_t = canon(team)
    got.steps.append(f"① {why_t}")
    if opponent:
        opponent, why_o = canon(opponent)
        got.steps.append(f"① 상대 {why_o}")

    # ② 리그 → 언어·어댑터
    lg = await league_of(team, pool=pool, text=f"{asked_t} {asked_o}",
                         offline=not look_up)
    got.steps.append("② " + lg.note().replace("\n", "\n   "))
    key_lg = league or lg.league
    # 🔴 **언어를 싣고 간다** — 하류가 다시 계산하지 않는다(2026-10-04)
    got.langs = tuple(lg.langs or ())

    async def _find(a: str, b: str):
        return await slate.find(pool, team=a, league=league, day=day,
                                days=days, opponent=b or None)

    # ③ 쌓아 둔 표 — 🔴 **표준 표기로** 찾는다(사용자가 쓴 말이 아니다)
    found = await _find(team, opponent)
    if not found.games and asked_t != team:
        # ⚠️ 바꾼 것이 틀릴 수도 있다 — 원문으로 한 번 더(그 사실을 적는다)
        found = await _find(asked_t, asked_o)
        if found.games:
            got.steps.append("③ 표준 표기로는 없고 **원문으로** 찾았다")

    # ④ 어댑터로 일정 받기
    if not found.games and look_up and key_lg:
        from app import analyze
        want = LI.adapter_of(key_lg)
        if want and want in analyze._adapters():
            try:
                why = await analyze._fill_slate(pool, want,
                                                day or date.today())
                got.steps.append(f"④ {why}")
            except Exception as exc:                        # noqa: BLE001
                got.steps.append(f"④ 어댑터 수집 실패 — {exc!r}")
            found = await _find(team, opponent)

    # ⑤ 봇이 직접 찾기
    lookup = None
    if not found.games and look_up:
        from app import findgame
        lookup = await findgame.find_and_store(
            pool, team=team, opponent=opponent or "", day=day,
            league=key_lg or "")
        got.steps.append(f"⑤ 봇이 직접 찾았다 — {len(lookup.rows)}건")
        if lookup.rows:
            # ══════════════════════════════════════════════════════════
            # ⑥ 🔴🔴 **열쇠로 되찾는다**(3단계) — 이름으로 되찾지 않는다
            # ══════════════════════════════════════════════════════════
            #
            #  ⚠️ 종전에는 *"방금 적은 행의 이름"* 으로 되찾았다. 그것도 이름이다 —
            #     저장과 조회가 **같은 글자**라 우연히 맞았을 뿐이고, 한쪽이
            #     바뀌면 같은 병이 돌아온다.
            #  🔴 `games.ext_id` 에는 **언어가 없다.** 우리가 방금 그 열쇠로 적었다 —
            #     그 열쇠로 찾으면 갈릴 수가 없다.
            row0 = lookup.rows[0]
            found = await slate.by_key(pool, str(row0.get("ext_id") or ""))
            if found.games:
                got.steps.append(f"⑥ 열쇠 `{row0.get('ext_id')}` 로 되찾았다")
            if not found.games:
                # 🔴 적었는데 창에 없다 — **날짜 문제다**(이름 문제가 아니다)
                got.reason = Reason.OUT_OF_WINDOW
                got.candidates = list(lookup.rows)
                got.steps.append(
                    f"⑥ 적었는데 질문 창({days}일)에 없다 — 그 경기는 "
                    f"{row0.get('starts_kst')} 다")
                return got

    if not found.games:
        # ══════════════════════════════════════════════════════════════
        # 🔴 **무엇이 막았는지 가린다** — 처방이 전부 다르다(4단계)
        # ══════════════════════════════════════════════════════════════
        #
        #  이름 문제 → 이름표를 고친다      (다시 물어도 같다)
        #  안 쌓임   → 스케줄러를 돌린다    (다시 물어도 같다)
        #  자료 없음 → 자료를 더 찾는다
        #  ⚠️ 셋을 하나로 뭉치면 사용자가 **엉뚱한 쪽을** 고친다.
        #  🔴 `slate` 가 *"아직 안 쌓였다"* 라고 하면 **그 분류를 그대로** 쓴다 —
        #     여기서 다시 추측하지 않는다.
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **⑥ 오픈월드 — 사다리의 마지막 단**(지시서 §2 · 2026-10-05)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 봇은 사용자가 **묻는 모든 경기**를 예측해야 한다. … 선언된 일곱
        #  > 리그 밖의 경기도 **"이름표 문제"로 멈추지 않고** 분석까지 간다.
        #
        #  🔴 여기서만 돈다 — ①~⑤ 가 **다 빗나간 뒤**다(§5 M53: 아는 팀
        #     질문에서 Solar 호출 0회). ⚠️ 돈이 들기 때문이다.
        #  🔴 확정은 **코드**가 한다(⑥-3) — Solar 는 철자 후보만 낸다.
        if look_up:
            # 🔴 이름 해석이 못 푼 쪽을 **빈 문자열**로 넘긴다(§5 M53 의 조건)
            unres = ("" if "못 바꿨다" in why_t else team,
                     "" if "못 바꿨다" in why_t else (opponent or team))
            ow = await _by_openworld(got, team=team, opponent=opponent,
                                     unresolved=unres, net=net)
            if ow is not None:
                return ow
        if "못 바꿨다" in why_t:
            got.reason = Reason.NAME_UNRESOLVED
        elif found.reason is Reason.NOT_COLLECTED:
            got.reason = Reason.NOT_COLLECTED
        else:
            got.reason = Reason.MATCH_NOT_FOUND
        got.steps.append(f"🔴 못 찾았다 — {got.reason.value}")
        if lookup is not None:
            got.candidates = list(lookup.rows)
        return got
    if len(found.games) > 1:
        # 🔴 §17-g-3 · M14 — **남의 경기를 분석하면 그 카드는 통째로 거짓이다.**
        #    ⚠️ 여럿이면 **고르지 않는다** — 고르는 것은 사용자 몫이다.
        got.reason = Reason.AMBIGUOUS
        got.candidates = list(found.games)
        got.steps.append(f"🔴 맞는 경기가 {len(found.games)}건 — 고르는 것은 "
                         f"사용자 몫이다(§17-g-3)")
        return got

    row = found.games[0]
    # 🔴 **현지어는 영어가 아닌 첫 언어**다(실측 2026-10-03: 목록의 마지막을
    #    집었더니 `['ja','en']` 의 `en` 이 나와 현지 표기가 영어가 됐다).
    #    ⚠️ 리그를 모르면 현지어도 모른다 — 그때는 **비워 둔다**(지어내지 않는다).
    # 🔴🔴 **대표팀은 리그가 없다 — 사다리가 정한 언어를 쓴다**(2026-10-04).
    #
    #  ⚠️ 종전엔 `LI.langs_of(key_lg)` **하나**만 봤다. 대표팀은 리그 열쇠가 비어
    #     그것이 빈 목록이고, 그래서 현지 표기가 **양쪽 다 영문**으로 갔다:
    #
    #       `North Macedonia lineup Scotland фудбал`
    #        ^^^^^^^^^^^^^^^           ^^^^^^^^ 🔴 마케도니아어 낱말에 영문 팀명
    #
    #  🔴 사다리 ②가 Babel 로 `mk` 를 안다(`got.langs`) — **그것을 먼저** 본다.
    #     ⚠️ 리그 명부가 있으면 그쪽이 이긴다(실측으로 적은 언어다).
    local_lang = next(
        (x for x in ((LI.langs_of(key_lg) or ()) or tuple(got.langs or ()))
         if x != "en"), "")
    got.ref = matchref.ref_from_row(
        row, league=key_lg,
        home_local=(_label(str(row.get("home") or ""), local_lang)
                    if local_lang else ""),
        away_local=(_label(str(row.get("away") or ""), local_lang)
                    if local_lang else ""))
    got.steps.append(f"✅ `{got.ref.key}` · {got.ref.away} @ {got.ref.home}")
    return got
