"""🔴🔴 **리그를 몰라도 경기를 찾는다** — 사용자 결정 2026-10-10 §2.

> ① 질문에서 팀 이름·날짜를 뽑는다(날짜가 없으면 오늘~+2일).
> ② fotmob 검색(팀 검색) → 후보 팀 id들 → 각 팀의 일정에서 날짜 창 안 경기 →
>    두 팀이 맞는 경기.
> ③ ②가 실패하면 fotmob **날짜별 전체 경기 목록**(그날 모든 리그)에서 두 팀 이름
>    정규화 매칭.
> ④ 그래도 실패하면 ESPN 경기 HTML 검색 → 그래도 실패하면 **"못 찾음 — 시도한
>    출처·후보 3개"** 를 카드 대신 보낸다.
> 경기를 찾으면 그 경기의 리그 id로 **자동 등록**을 건다(이미 있으면 갱신만).

══════════════════════════════════════════════════════════════════
🔴🔴 **②③ 의 통로를 바꿨다 — 같은 지시서의 금지 조항이 이긴다**
══════════════════════════════════════════════════════════════════

지시서가 적은 *"fotmob 팀 검색"*·*"fotmob 날짜별 전체 경기 목록"* 은 fotmob 에서
**`/api/*` 뿐이다**. 🔴 실측 2026-10-10 `www.fotmob.com/robots.txt`:

    User-agent: *
    Allow: /
    Disallow: /api/*

그리고 같은 지시서의 금지 줄이 *"**robots 막힌 출처**"* 라고 적혀 있다(사용자 결정
2026-10-04 도 이미 *"API 경로는 dead 처리"* 라고 적어 뒀다 · `app/findgame.py`).
⚠️ 나는 2026-10-10 에 `/api/data/search/suggest`·`/api/data/matches` 로 이 사다리를
   한 번 짰다 — **그것이 금지를 어긴 것**이고 지웠다.

🔴 **그래서 robots 가 직접 광고하는 길로 같은 일을 한다**(`Sitemap:` 줄):

| 지시서가 적은 것 | 🔴 실제로 쓰는 것 | 실측 2026-10-10 |
|---|---|---|
| ② fotmob 팀 검색 | `/sitemap/en/teams.xml` **팀 색인** | 팀 6,028개(id+슬러그) |
| ② 팀 일정 | `/teams/{id}/fixtures/x` HTML | ✅ 허용 경로 |
| ③ 날짜별 전체 목록 | **리그 색인 + 리그 일정** HTML | 리그 431개 |
| ④ ESPN 경기 HTML | `findgame.find`(검색 → 경기 페이지) | 이미 있는 통로 |

⚠️ **색인은 부분이다** — `defensa-y-justicia`·`adelaide-city`·
   `lion-city-sailors-fc` 는 있고 `yesilyurt`·`terranuova`·`prato`·
   `union-santa-fe` 는 **0건**이다(실측). 🔴 그 경기들은 ④(검색 단)로 내려가고,
   거기서도 못 찾으면 **"못 찾음"** 을 카드 대신 낸다 — 조용히 끝내지 않는다.

🔴 이름 정규화는 **한 곳**이다(`norm_name`) — §2 가 *"same_person 처럼 이름 정규화
   한 곳"* 이라고 못 박았다. ⚠️ 두 곳에서 정규화하면 한쪽만 고쳐진다.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta

logger = logging.getLogger(__name__)

#: 🔴 §1-1 ② — 날짜가 없으면 **오늘~+3일**(사용자 지시 2026-10-10 재작성).
#  ⚠️ 종전 2일에서 늘렸다 — 그 지시가 "오늘~+3일"로 적었다.
WINDOW_DAYS = 3
#: 🔴 §1-1 ② — **보드 시각이 있으면 ±3시간** 안으로 좁힌다
BOARD_HOURS = 3
#: 🔴 §2 ④ — 못 찾았을 때 보일 후보 수(사용자가 적은 3)
SHOW_CANDS = 3
#: 🔴 색인에서 집어 올리는 팀 후보 상한 — 한 이름이 수십 팀에 걸릴 수 있다.
#  ⚠️ 상한에 걸려 **안 열어 본 후보가 있으면** 그 사실을 `tried` 에 적는다(#3).
MAX_TEAMS = 4
#: 🔴 리그 일정을 열어 보는 상한(③) — 리그 색인이 431개다.
MAX_LEAGUES = 3


@dataclass
class Found:
    """🔴 발견 결과 — **시도한 출처와 후보를 함께** 든다(§2 ④)."""

    match: dict | None = None
    candidates: list[dict] = field(default_factory=list)
    tried: list[str] = field(default_factory=list)
    why: str = ""
    league_id: object = None
    league_name: str = ""
    #: 🔴 그 경기의 나라 코드 — **컵대회는 순위표가 안 준다**(실측 2026-10-10)
    ccode: str = ""
    #: 🔴 §1-1 ① — 보드에서 읽은 경기 단서(없으면 `None`)
    hint: object = None
    #: 🔴 어느 칸에서 찾았나 — 보고가 이것을 적는다(§4 "출처")
    rung: str = ""


def norm_name(said: object) -> str:
    """🔴🔴 **이름 정규화 — 한 곳**(§2 ② 마지막 줄). 공백까지 **붙인** 꼴.

    하는 일: 유니코드 분해 후 결합문자 제거(`Unión`→`union`) · 소문자 ·
    글자 아닌 것을 공백 · `_AFFIX` 의 클럽 표기 제거 · **공백 제거**.

    🔴 공백을 붙이는 까닭: 같은 팀을 출처마다 다르게 띄운다 — 실측 2026-10-10
       `Ha Noi FC` ↔ `Hanoi` · `Công An Hà Nội` ↔ `Cong An Hanoi`.
    ⚠️ **글자를 지어내 바꾸지 않는다** — 떼는 것은 `_AFFIX` 뿐이다.
    🔴 한글↔로마자는 **여기서 잇지 않는다** — 그것은 이름표(`learn_names`)의 일이고
       여기서 억지로 이으면 엉뚱한 팀을 분석한다(M14).
    """
    return "".join(tokens(said))


def name_key(said: object) -> str:
    """🔴🔴 **사람 이름 열쇠 — 낱말 순서를 지운다**(정렬해 붙인다).

    ⚠️ 실사고 2026-10-10: fotmob 이 **같은 선수를 두 꼴로** 준다 —
       선수단 페이지는 `Park Man-Ho`(성 먼저), 경기 라인업은 `Man-Ho Park`.
       🔴 글자로 맞추니 **겹치는 이름이 0명**이었고, 선수단 기록이 통째로 버려져
       카드가 *"기록 없음"* 만 적었다(사용자가 잡은 `공격 기여 −100%` 의 뿌리다).
    🔴 팀 이름에는 쓰지 않는다(`Adelaide City` ↔ `City Adelaide` 는 다른 얘기다) —
       **사람 이름 전용**이다.
    """
    return "".join(sorted(tokens(said)))


def tokens(said: object) -> list[str]:
    """🔴 정규화한 **낱말들** — `covers` 가 이것으로 센다."""
    low = unicodedata.normalize("NFKD", str(said or ""))
    low = "".join(c for c in low if not unicodedata.combining(c)).lower()
    # 🔴🔴 **NFC 로 되붙인다** — ⚠️ 실사고 2026-10-10: `NFKD` 가 한글 음절을
    #    **자모**(U+1100 묶음)로 쪼개는데 아래 글자 묶음(`가-힣`)이 자모를 안 받아
    #    **한글 이름이 통째로 빈 글자**가 됐다(`norm_name("김천상무") == ""`).
    #    그래서 `same_team` 이 한글끼리 **절대 안 맞았다**(전역 주기 팀 표를
    #    한글로 적자 드러났다). 🔴 결합문자를 뗀 뒤 다시 합치면 `Unión`→`union`
    #    은 그대로이고 한글은 음절로 돌아온다.
    low = unicodedata.normalize("NFC", low)
    low = re.sub(r"[^0-9a-z가-힣ぁ-んァ-ヴー一-龥]+", " ", low)
    return [w for w in low.split() if w and w not in _AFFIX]


#: 🔴 떼는 접사 — 팀 이름의 **클럽·법인 표기**뿐이다(실측으로 늘린다).
#  ⚠️ `united`·`city` 는 **떼지 않는다** — `Adelaide City` ↔ `Adelaide United` 가
#     같은 팀이 돼 버린다(실사고가 될 자리였다 · 2026-10-10 에 잡았다).
_AFFIX: frozenset[str] = frozenset((
    "fc", "cf", "sc", "ac", "afc", "cd", "ca", "sv", "if", "bk", "fk",
    "club", "clube", "asd", "ssd", "us", "as", "ud", "cs",
    "futbol", "football", "calcio", "spor", "kulubu", "kulubu",
))


def covers(said: object, want: object) -> bool:
    """🔴🔴 `said`(출처가 적은 이름)가 `want`(사용자가 적은 이름)를 **담고 있나**.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **방향이 있다** — 양방향 품기는 엉뚱한 팀을 물어 온다
    ══════════════════════════════════════════════════════════════════

    ⚠️ 실측 2026-10-10 — 양방향으로 품게 했더니 **거짓 일치 둘**이 나왔다:

    | 사용자가 물은 것 | 잘못 붙은 것 | 왜 |
    |---|---|---|
    | `Cong An Hanoi` | `ha-noi-fc`(**다른 구단**) | `conganhanoi` 가 `hanoi` 를 품는다 |
    | `Union de Santa Fe` | `santa-fe`(**콜롬비아 팀**) | 낱말 집합이 부분집합이다 |

    🔴 그래서 **담는 쪽이 출처**여야 한다: 출처 이름이 사용자 낱말을 **전부**
       들고 있을 때만 같은 팀이다(`lion-city-sailors-fc` ⊇ `Lion City Sailors`).
    🔴 붙여 쓴 꼴이 **정확히 같으면** 그것도 같은 팀이다(띄어쓰기만 다른 경우).
    """
    a, b = tokens(said), tokens(want)
    if not a or not b:
        return False
    if "".join(a) == "".join(b):
        return True
    return set(b) <= set(a)


def alike(a: object, b: object) -> bool:
    """🔴🔴 **양쪽 중 한쪽이 다른 쪽을 담으면** 같은 팀으로 본다.

    ⚠️ 이것은 `covers` 보다 **느슨하다**. 🔴 그래서 **쓰는 자리를 좁힌다**: 날짜
       창과 **기준 팀**이 이미 좁혀 놓은 뒤에만 쓰고, 걸린 경기가 **둘 이상이면
       고르지 않는다**(§2: *"후보가 둘 이상이면 버튼으로 고르게 한다"*).

    🔴 왜 필요한가(실측 2026-10-10): fotmob 이 **더 짧게** 적는다 —
       `Unión`(fotmob) ↔ `Union de Santa Fe`(사용자). 방향을 강제하면 이 경기를
       놓친다. ⚠️ 그런데 느슨한 검사를 **넓은 목록**에 쓰면 `santa-fe`(콜롬비아)
       같은 엉뚱한 팀이 붙는다 — 그래서 좁은 자리에서만 쓴다.
    """
    return covers(a, b) or covers(b, a)


def window(day: date | None, *, today: date | None = None) -> list[date]:
    """🔴 §2 ① — 날짜가 없으면 **오늘~+2일**."""
    if day is not None:
        return [day]
    # 🔴 "지금"은 `app/window.now_utc` 하나다(§4 `--as-of`)
    from app import window as _w
    base = today or _w.now_utc().date()
    return [base + timedelta(days=i) for i in range(WINDOW_DAYS + 1)]


#: 🔴🔴 **다른 등급 팀을 가리키는 슬러그 조각**(실측 2026-10-10)
#
#  ⚠️ 실사고가 될 자리였다: `Gil Vicente` 를 물었는데 색인이 **`gil-vicente-u23`**
#     을 먼저 줬고, `Faroe Islands` 는 **`faroe-islands-u17`** 을 줬다. 🔴 남의
#     경기를 분석하면 그 카드는 통째로 거짓이다(M14).
#  🔴 그래서 **사용자가 그 등급을 적지 않았으면 뺀다**. 적었으면 그대로 본다.
TIER_WORDS: tuple[str, ...] = (
    "u15", "u16", "u17", "u18", "u19", "u20", "u21", "u22", "u23",
    "women", "womens", "feminino", "femenino", "femminile", "frauen",
    "reserves", "reserve", "youth", "juniors", "academy", "sub20", "sub23",
)


#: 🔴🔴 **2군 슬러그 꼬리**(실측 2026-10-11 · MLS)
#
#  ⚠️ `올랜도` 를 물으면 색인이 `orlando-city` 와 함께 **`orlando-city-b`**(2군)를
#     주고, `크루` 는 **`columbus-crew-2`**(MLS Next Pro)를 준다. 🔴 낱말로는 못
#     잡는다 — `b`·`2` 를 낱말로 넣으면 엉뚱한 팀이 걸린다. **꼬리로** 본다.
RESERVE_TAIL: tuple[str, ...] = ("-b", "-2", "-ii", "-iii")


def tier_of(said: object) -> set[str]:
    """🔴 그 이름이 말하는 **등급 낱말들**(없으면 빈 집합).

    🔴 2군 꼬리(`-b`·`-2`)도 등급으로 센다 — 사용자가 적지 않으면 뺀다.
    """
    low = {w for w in tokens(said)}
    said_s = "".join(low)
    got = {w for w in TIER_WORDS if w in low or w in said_s}
    # 🔴 **사용자가 2군을 적었으면 그대로 본다** — 그래서 `Orlando City B`(공백)도
    #    `orlando-city-b`(붙임표)와 **같은 꼬리**로 읽는다(한쪽만 읽으면 그 escape
    #    hatch 가 죽는다 · `_slug_hit` 의 `asked` 가 이 집합을 본다).
    raw = "-".join(str(said or "").strip().lower().split())
    got |= {tail for tail in RESERVE_TAIL if raw.endswith(tail)}
    return got


def _slug_hit(index: dict[str, str], name: str) -> list[tuple[str, str]]:
    """🔴 색인(`{id: 슬러그}`)에서 그 이름에 맞는 줄 — **정확 일치가 먼저**다.

    ⚠️ 품는 일치를 먼저 쓰면 `adelaide-city` 를 물을 때 `adelaide-united` 가
       앞에 설 수 있다. 🔴 정확 → 품음 순서로 돌려준다.
    🔴🔴 **등급이 다른 팀은 뺀다** — 사용자가 `U23`·`여자`를 적지 않았는데
       `gil-vicente-u23` 를 열면 **남의 경기**다(실측 2026-10-10).
    """
    # 🔴🔴 **별칭표를 지난다** — ⚠️ 실사고 2026-10-10: 사용자가 `제노아` 로 물었는데
    #    색인 슬러그는 `genoa` 다. `norm_name` 은 **한글↔로마자를 일부러 안 잇는다**
    #    (이으면 엉뚱한 팀이 섞인다) → 슬러그를 **못 찾아** `match_not_found` 로
    #    끝났다. 🔴 그 다리는 `config/entities.yaml`(별칭표)이고 `aliases_of` 가
    #    그것을 읽는다. 여기서 **별칭 전부**로 색인을 본다.
    names = [str(name), *aliases_of(name)]
    wants = {norm_name(x) for x in names if norm_name(x)}
    if not wants:
        return []
    asked = tier_of(name)
    exact = [(i, s) for i, s in index.items() if norm_name(s) in wants]
    loose = [(i, s) for i, s in index.items()
             if norm_name(s) not in wants
             and any(same_team(s, x) for x in names)]
    out = [*sorted(exact), *sorted(loose)]
    # 🔴 사용자가 등급을 적지 않았으면 등급 팀을 **뺀다**(뒤로 미루지 않는다 —
    #    상한에 걸려 열리는 일이 있다)
    return [(i, s) for i, s in out if asked or not tier_of(s)]


#: 🔴 등급을 가리려고 **일정을 열어 보는** 후보 수 상한(요청을 늘리지 않는다)
PICK_TRY = 3


def has_match(rows: list[dict], ref: object) -> bool:
    """🔴🔴 그 일정 목록에 **이 경기가 있나** — 등급을 가르는 유일한 확증.

    ⚠️ 실사고 2026-10-11(팰리스·스트라스부르): 색인이 **같은 슬러그를 두 번**
       준다(`crystal-palace` → 여자팀 614828 · 남자팀 9826 · `strasbourg` 도 같다).
       🔴 그래서 슬러그 낱말 필터(`TIER_WORDS`)가 **못 가르고** 첫 줄이 여자팀이
       됐다 — 폼·골 목록·상성 재료가 통째로 **WSL·여자 Premiere Ligue** 경기였고,
       그것이 축1 을 만들어 확률을 밀었다.
    🔴 가리는 재료는 **지어내지 않는다** — 분석 중인 경기의 킥오프와 상대 이름이
       그 팀 일정에 **함께** 있으면 그 팀이다(둘 다 요구한다).
    """
    want = str(getattr(ref, "kickoff_utc", "") or "").replace("T", " ")[:16]
    names = [str(getattr(ref, "home_name", "") or ""),
             str(getattr(ref, "away_name", "") or "")]
    if not want or not any(names):
        return False
    for one in rows or []:
        said = str(one.get("utc") or "").replace("T", " ")[:16]
        if said != want:
            continue
        if any(same_any(str(one.get(k) or ""), names, loose=True)
               for k in ("home", "away")):
            return True
    return False


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **색인에 없는 팀은 검색으로 번호를 뗀다** — 사용자 지시 2026-10-16
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고 2026-10-16(Gulf United FC vs Emirates Club · UAE 2부): 봇이
#     `openworld_not_found` 로 멈췄다. 그런데 fotmob 에는 **있었다** —
#     `Emirates Club` 팀 번호 **102121**, 일정 15경기, 경기 페이지까지 정상.
#     🔴 못 찾은 까닭은 팀 번호 풀이가 **sitemap 색인 하나에만** 기대서다
#        (`team_index` 6,027팀에 UAE 2부·남아공 2부·체코 2부는 없다).
#  🔴 그래서 색인이 0건이면 **검색으로 fotmob 팀 주소를 찾아 번호를 뗀다**.
#     ⚠️ 그 번호가 맞는지 **팀 페이지를 받아 이름으로 확인**한다(추측 금지).

#: 🔴 fotmob 팀 주소에서 번호·슬러그를 뗀다
_TEAM_URL = re.compile(r"fotmob\.com/(?:[a-z]{2}/)?teams/(\d+)/[a-z]+/([\w-]+)")


async def team_id_by_search(net, name: str, *, chain=None, state=None
                            ) -> tuple[str, str] | None:
    """🔴🔴 **검색으로 fotmob 팀 번호**를 찾는다. `(번호, 슬러그)` 또는 `None`.

    🔴 쓰는 곳은 `pick_team` 하나다(색인이 0건일 때만 · 사본 금지).
    """
    if chain is None:
        from app import search as _s
        chain = _s.build_chain()
    said = f"fotmob {name}".strip()
    try:
        hits = await chain.query(said, lang="en")
    except Exception as exc:                                # noqa: BLE001
        if state is not None:
            state.note(f"색인 밖 번호 풀이 — 검색 실패 `{said}`: {exc!r}")
        return None
    for h in list(hits)[:12]:
        got = _TEAM_URL.search(str(getattr(h, "url", "") or ""))
        if not got:
            continue
        tid, slug = got.group(1), got.group(2)
        # 🔴 **받아서 확인한다** — 그 팀 페이지가 그 이름인가
        try:
            page = await net.get(f"https://www.fotmob.com/teams/{tid}/overview")
        except Exception:                                   # noqa: BLE001
            continue
        text = str(getattr(page, "text", "") or "")
        if not text:
            continue
        if not same_any(name, [slug.replace("-", " ")], loose=True) and \
                norm_name(name) not in norm_name(text[:4000]):
            continue
        if state is not None:
            state.note(f"색인 밖 번호 풀이 — `{name}` → fotmob **{tid}**"
                       f"(`{slug}` · 검색으로 찾아 팀 페이지로 확인했다)")
        return tid, slug
    if state is not None:
        state.note(f"색인 밖 번호 풀이 — 🔴 `{name}` 을 검색으로도 못 찾았다")
    return None


async def pick_team(net, name: str, *, ref: object, state: object = None,
                    page_of=None) -> tuple[str, str] | None:
    """🔴🔴 색인 후보 중 **이 경기를 가진 팀**을 고른다. `(id, 슬러그)` 또는 `None`.

    🔴 왜 — 위 `has_match` 의 실사고. 후보가 하나면 그대로 쓴다(요청 0).
    ⚠️ 어느 후보도 이 경기를 안 가지면 **첫 줄을 쓰고 그 사실을 적는다**(#3) —
       일정 페이지를 못 받는 경우(캐시 미스·차단)와 구분해야 한다.
    """
    from app.collect import fotmob as fm
    if page_of is None:
        from app.core.stages.s2_facts import _day_page as page_of
    idx = await fm.team_index(net)
    hits = _slug_hit(idx, name)
    if not hits:
        # 🔴 **색인 밖 팀**(위 머리말) — 검색으로 번호를 뗀다
        got = await team_id_by_search(net, name, state=state)
        return got
    if len(hits) == 1:
        return hits[0]
    for tid, slug in hits[:PICK_TRY]:
        page = await page_of(net, fm.team_fixtures_url(tid, slug),
                             state=state, team=f"{name} 일정")
        rows = team_fixtures(getattr(page, "text", "") or "", tid)
        if has_match(rows, ref):
            if state is not None and (tid, slug) != hits[0]:
                state.note(f"색인 등급 가리기 — `{name}` 후보 {len(hits)}개 중 "
                           f"**이 경기를 가진** `{tid}` 를 골랐다"
                           f"(첫 줄 `{hits[0][0]}` 은 다른 등급이다)")
            return tid, slug
    if state is not None:
        state.note(f"🔴 색인 등급 가리기 — `{name}` 후보 {len(hits)}개 어디에도 "
                   f"이 경기가 없다 → 첫 줄 `{hits[0][0]}` 을 쓴다(가리지 못했다)")
    return hits[0]


def aliases_of(name: str, *, spell: dict | None = None) -> list[str]:
    """🔴🔴 §1-1 ② — *"팀 이름 한국어·영어·현지어 아무거나"*. **이름표가 안다.**

    `강원` → `['강원', 'Gangwon FC', '강원 FC']`. 🔴 fotmob 색인의 슬러그는
    **로마자**이므로 한글로는 닿지 않는다(실측 2026-10-10: `부천` → 0건).

    🔴 이름을 **여기서 짓지 않는다** — `app/teamref.py` 의 이름표가 원본이고
       (CLDR·리그 명부·사용자 별칭이 거기서 자란다) 우리는 **읽기만** 한다.
    ⚠️ 이름표가 모르면 **물은 이름 하나**다(그 사실이 `tried` 에 남는다).
    """
    said = str(name or "").strip()
    out = [said] if said else []
    if not said:
        return out
    # 🔴🔴 **철자 후보도 별칭이다**(§1-1 ②) — 이름표가 모르는 외국 구단의 한글
    #    음차(`우니온`)는 s1 의 철자 단계(로컬 LLM)가 로마자로 바꿔 준다.
    #  ⚠️ s1 의 `_respell` 은 **이름표가 아는 철자만** 받는다(그 경로의 규율이다).
    #     🔴 색인은 이름표와 **무관한 출처**이므로 그 가림이 필요 없다 — 그래서
    #        철자 후보를 여기로 따로 받는다(실측 2026-10-10: `우니온` 이 그래서
    #        끝까지 안 풀렸다).
    for one in (dict(spell or {}).get(said) or []):
        got = str(one).strip()
        if got and got not in out:
            out.append(got)
    try:
        from app import teamref
        key, _why = teamref.key_of(said)
        ref = teamref.registry().teams.get(key) if key else None
    except Exception:                                       # noqa: BLE001
        return out
    for lang, names in ((getattr(ref, "names", None) or {}).items()
                        if ref is not None else ()):
        for one in (names or []):
            got = str(one)
            # ⚠️ 이름표에는 **출처 열쇠**도 이름으로 들어 있다(`tsdb:138108`) —
            #    그것으로 색인을 뒤지면 늘 0건이다. 🔴 콜론이 든 것은 뺀다.
            if ":" in got or got in out:
                continue
            out.append(got)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **사용자 별칭표를 직접 읽는다** — 이름표가 그 팀을 몰라도
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고 2026-10-11: 사용자가 `올랜도`·`크루`(MLS)로 물었다. 별칭을
    #     `config/entities.yaml` 에 적었는데도 `aliases_of('올랜도')` 가
    #     **['올랜도']** 뿐이었다 — `teamref._from_entities` 는 **정식명이
    #     이름표에 이미 있을 때만** 별칭을 붙이고(`정식명을 못 찾아 건너뜀`),
    #     MLS 는 리그 명부에 없어 그 팀이 이름표에 **없다**.
    #  🔴 그런데 색인(fotmob sitemap)은 이름표와 **무관한 출처**다 — 등록 안 된
    #     리그의 클럽도 거기에 있다(실측: `orlando-city` 267810). 사용자가 적은
    #     별칭을 안 쓸 까닭이 없다. 🔴 **표를 직접 읽는다**(짓지 않는다).
    out.extend(_entity_aliases(said, skip=out))
    return out


def one_team(said: str) -> bool:
    """🔴🔴 그 글자가 **한 팀 이름 그대로**인가 — 두 팀으로 가르기 전에 본다.

    ⚠️ 실사고 2026-10-11: 사용자가 `시애틀 사운더스` 라고 물었고 입구가 그것을
       **팀 `시애틀` vs 상대 `사운더스`** 로 갈랐다(두 낱말이면 가른다).
    🔴 **정확 일치로만** 본다 — 품는 일치를 쓰면 `올랜도 크루`(두 팀!)가
       `올랜도` 를 품어 **한 팀**이 된다(실측: 그 질문이 바로 깨졌다).
    """
    want = norm_name(said)
    if not want:
        return False
    names: list[str] = []
    try:
        from app import teamref
        key, _why = teamref.key_of(said)
        ref = teamref.registry().teams.get(key) if key else None
        for _lang, got in ((getattr(ref, "names", None) or {}).items()
                           if ref is not None else ()):
            names += [str(x) for x in (got or [])]
    except Exception:                                       # noqa: BLE001
        pass
    try:
        from app import entities
        for team in entities._table():
            names += [str(team), *[str(x) for x in entities.names_of(team)]]
    except Exception:                                       # noqa: BLE001
        pass
    return any(norm_name(x) == want for x in names if x)


def _entity_aliases(said: str, *, skip: list[str]) -> list[str]:
    """🔴 `config/entities.yaml` 에서 그 이름이 걸리는 줄의 **다른 이름들**.

    🔴 걸리는 법: 정식명이거나 그 줄의 별칭 하나와 `same_team` 이다.
    ⚠️ 이름을 **짓지 않는다** — 표에 적힌 글자만 돌려준다.
    """
    try:
        from app import entities
        table = entities._table()
    except Exception:                                       # noqa: BLE001
        return []
    got: list[str] = []
    for team in table:
        names = [str(team), *entities.names_of(team)]
        if not any(same_team(said, one) for one in names if one):
            continue
        for one in names:
            if one and ":" not in one and one not in skip and one not in got:
                got.append(one)
    return got


async def find(net, *, home: str, away: str, day: date | None = None,
               league: str = "", board_text: str = "",
               spell: dict | None = None,
               today: date | None = None) -> Found:
    """🔴🔴 §1-1 — 사다리 ①②③. ⚠️ **리그를 묻지 않는다**.

    | 칸 | 무엇 |
    |---|---|
    | ① | **보드**가 있으면 보드의 날짜·시각·두 팀·리그 표기를 **먼저** 읽는다 |
    | ② | fotmob 팀 색인(sitemap) → 팀 일정 HTML |
    | ③ | fotmob 리그 색인 → 리그 일정 HTML |

    ④(ESPN 경기 HTML)·⑤(리그 공식)는 부르는 쪽이 잇는다(`app/findgame.py` 가 그
    통로다) — 여기서 검색을 다시 짜면 통로가 둘이 된다(사본 금지).
    """
    got = Found()
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 ① **보드가 가장 정확한 단서다**(§1-1 ①)
    # ══════════════════════════════════════════════════════════════════
    if str(board_text or "").strip():
        from app.core import board as _b
        hint = _b.hint_of(board_text, today=today)
        got.hint = hint
        got.tried.append(f"① 보드 단서 — {hint.why}")
        # 🔴 보드가 적은 것이 **질문보다 정확하다**(사용자가 그렇게 적었다)
        home = hint.home or home
        away = hint.away or away
        league = hint.league or league
        day = hint.day or day
    days = window(day, today=today)
    at = got.hint.hhmm if got.hint else ""
    out = await _by_team(net, home=home, away=away, days=days, got=got, at=at,
                         spell=spell)
    if out.match:
        return out
    out = await _by_league(net, home=home, away=away, days=days, got=got,
                           league=league, at=at, spell=spell)
    if out.match:
        return out
    got.why = miss_line(got)
    return got


def near_time(utc: str, at: str, *, hours: int = BOARD_HOURS) -> bool:
    """🔴 §1-1 ② — 보드 시각 `HH:MM`(KST)의 **±hours** 안인가.

    ⚠️ 보드 시각은 **사용자가 보는 시각**이므로 KST 다(절대규칙 2: 표시만 KST).
       🔴 경기 시각은 UTC 로 들고 있으므로 KST 로 바꿔 비교한다.
    ⚠️ 시각을 못 읽으면 **좁히지 않는다**(`True`) — 모르는 것으로 버리지 않는다.
    """
    if not at or not utc:
        return True
    from app import timefmt
    from datetime import datetime, timezone
    try:
        hh, mm = (int(x) for x in str(at).split(":"))
        when = datetime.fromisoformat(str(utc).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    k = timefmt.kst(when)
    gap = abs((k.hour * 60 + k.minute) - (hh * 60 + mm))
    gap = min(gap, 24 * 60 - gap)       # 🔴 자정을 넘는 차이도 짧은 쪽으로
    return gap <= hours * 60


def miss_line(got: Found) -> str:
    """🔴🔴 §2 ④ — **"못 찾음 — 시도한 출처·후보 3개"**. 카드 대신 이것을 보낸다."""
    said = f"🔴 **못 찾음** — 시도한 출처 {len(got.tried)}곳"
    if got.tried:
        said += "\n" + "\n".join(f"· {x}" for x in got.tried[:6])
    if got.candidates:
        said += (f"\n후보 {len(got.candidates)}건 중 {SHOW_CANDS}개: "
                 + " · ".join(f"`{c.get('team')}`(id {c.get('id')})"
                              for c in got.candidates[:SHOW_CANDS]))
    else:
        said += "\n후보 0건 — 팀 색인·리그 색인 어디에도 그 이름이 없다"
    return said


async def _by_team(net, *, home: str, away: str, days: list[date],
                   got: Found, at: str = "", spell: dict | None = None
                   ) -> Found:
    """🔴 §2 ② — 팀 색인에서 id 를 풀고, **그 팀 일정**에서 상대를 맞춘다.

    🔴 **한쪽만 풀려도 된다** — 실측 2026-10-10: `Union de Santa Fe` 는 색인에
       0건인데 `Defensa y Justicia` 는 `161730` 으로 풀린다. 그 팀 일정에서
       상대를 찾으면 경기가 확정된다.
    🔴 **둘 이상 걸리면 고르지 않는다** — 후보로 담아 두고 사용자가 고른다(§2).
    """
    from app.collect import fotmob as fm
    index = await fm.team_index(net)
    got.tried.append(f"fotmob 팀 색인(sitemap) {len(index)}팀")
    want = {d.isoformat() for d in days}
    seen: set[str] = set()
    for term, other in ((home, away), (away, home)):
        if not str(term or "").strip():
            continue
        # 🔴 §1-1 ② — **한국어·영어·현지어 아무거나**. 이름표가 로마자 이름을 안다
        names = aliases_of(term, spell=spell)
        # 🔴 **상대도 별칭으로** 본다 — 원문자만 보면 한글 상대가 안 맞는다
        theirs = aliases_of(other, spell=spell)
        hits: list[tuple[str, str]] = []
        for one in names:
            for row in _slug_hit(index, one):
                if row not in hits:
                    hits.append(row)
        got.tried.append(f"색인에서 `{term}`"
                         + (f"(별칭 {names[1:]})" if len(names) > 1 else "(별칭 없음)")
                         + f" → {len(hits)}건")
        if len(hits) > MAX_TEAMS:
            got.tried.append(f"⚠️ `{term}` 후보 {len(hits)}건 중 {MAX_TEAMS}건만 "
                             f"열었다(상한)")
        for tid, slug in hits[:MAX_TEAMS]:
            if tid in seen:
                continue
            seen.add(tid)
            page = await net.get(fm.team_fixtures_url(tid, slug))
            rows = team_fixtures(getattr(page, "text", "") or "", tid)
            got.tried.append(f"fotmob 팀일정 `{slug}` {len(rows)}경기")
            # 🔴 날짜 창 **안** 경기를 먼저 모은다(상대 조건은 그 다음)
            in_win = [m for m in rows
                      if str(m.get("utc") or "")[:10] in want
                      and near_time(str(m.get("utc") or ""), at)]
            # 🔴🔴 **상대를 모르면 상대로 걸러내지 않는다** — ⚠️ 실사고 2026-10-10:
            #    사용자가 `제노아` **한 팀만** 물었다. `theirs` 가 빈 목록이라
            #    `same_any(…, [])` 는 **언제나 거짓**이고, 그래서 ② 가 통째로
            #    막혀 `match_not_found` 로 끝났다(일정 45경기를 받아 놓고도).
            #    🔴 한쪽만 물으면 그 팀의 **다음 경기**를 찾는 것이 질문의 뜻이다.
            if theirs:
                fit = [m for m in in_win
                       if same_any(m["home"], theirs, loose=True)
                       or same_any(m["away"], theirs, loose=True)]
            else:
                # 🔴 한쪽만 물었으면 **킥오프가 지난 경기는 뺀다** — "다음 경기"를
                #    묻는 것이고, 시작한 경기는 분석(확정 XI·평소 XI)이 뜻이 없다.
                fit = [m for m in in_win if not _kicked(m)]
                if in_win and not fit:
                    got.tried.append(
                        f"🔴 `{slug}` 창 안 {len(in_win)}경기가 **전부 킥오프가 "
                        f"지났다** — " + " · ".join(
                            f"{x['home']} vs {x['away']} {str(x.get('utc'))[:16]}"
                            for x in in_win[:3]))
            # 🔴 **조용한 0 금지**(#3) — 창 안에 아무것도 없으면 그 사실과
            #    **다음 경기 날짜**를 적는다("못 찾았다"와 "창 밖이다"는 다른 일이다)
            if not in_win:
                nxt = _next_fixture(rows)
                got.tried.append(
                    f"🔴 `{slug}` 일정에 창({min(want)}~{max(want)}) 안 경기가 "
                    f"**0건**이다"
                    + (f" — 다음 경기는 {nxt['home']} vs {nxt['away']} "
                       f"{str(nxt.get('utc'))[:16]}" if nxt else " — 남은 경기도 없다"))
            for m in fit:
                got.candidates.append({"team": slug, "id": tid,
                                       "match": f"{m['home']} vs {m['away']}",
                                       "utc": m.get("utc")})
            if len(fit) > 1:
                # 🔴 §2 — **고르지 않는다.** 애매하면 사용자가 고른다.
                got.tried.append(
                    f"🔴 `{slug}` 일정에서 날짜 창 안 후보가 {len(fit)}건이다 — "
                    f"고르지 않는다(" + " · ".join(
                        f"{x['home']} vs {x['away']}" for x in fit[:3]) + ")")
                continue
            if fit:
                m = fit[0]
                got.match, got.rung = m, "② 팀 색인 → 팀 일정"
                got.league_id = m.get("league_id")
                got.league_name = str(m.get("league_name") or "")
                got.why = (f"✅ 팀 색인 → 일정 — `{slug}` 의 "
                           f"{str(m.get('utc'))[:10]} 경기")
                return got
    return got


async def fotmob_id(net, *, home: str, away: str, day: date | None = None,
                    ) -> tuple[str, str]:
    """🔴🔴 **fotmob 경기 번호를 이어 준다** — `(번호, 사유)`.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 이 함수가 생겼나 — 실사고 2026-10-10 (제노아 vs 피오렌티나)
    ══════════════════════════════════════════════════════════════════

    S0 가 그 경기를 **fdorg 슬레이트**로 확정했다(`ext_id = fdorg:558588`).
    그런데 fotmob 깊이(`fotmob.sources_context`)는 **`fotmob:` 접두만** 받는다 →
    `ingest.context_of` 가 `fdorg` 어댑터를 주고 그 어댑터에는 깊이 함수가 **없다**
    → `_depth` 가 **빈 목록**을 냈다. 카드 실측:

        XI 없음 · 결장 명단 미확보 · 감독 미확보 · 순위표 없음 · 폼 없음 ·
        맞대결 없음 · 직전 경기 XI 없음 → **축0 ⬜**(선수 가치 0명)

    🔴 축0 은 백필이 **유일하게 예측력을 잰 축**이다. 즉 fdorg 로 확정된 경기는
       (= 해외축구 슬레이트의 **거의 전부**) 상성 엔진의 그 축을 통째로 잃었다.
    ⚠️ 그런데 자료가 **없는 것이 아니었다** — fotmob 에 그 경기 페이지가 있고,
       봇은 같은 팀의 **과거** 경기 페이지를 11개나 열었다. 열쇠만 없었다(#2 배선).

    🔴 여기서 하는 일은 **번호를 푸는 것뿐**이다(② 사다리를 다시 쓴다 — 사본 금지).
    """
    out = await _by_team(net, home=home, away=away,
                         days=window(day), got=Found(), at="")
    mid = str((out.match or {}).get("id") or "")
    if mid:
        return mid, (f"✅ fotmob 경기 번호 `{mid}` — {out.rung}")
    return "", ("🔴 fotmob 경기 번호를 못 풀었다 — "
                + " · ".join(out.tried[-2:] or ["시도 기록 없음"]))


def _kicked(m: dict) -> bool:
    """🔴 그 경기는 **이미 킥오프가 지났나**. ⚠️ 시각을 못 읽으면 `False`(안 버린다).

    🔴 "지금"은 `app/window.now_utc` 하나다(사본 금지 · §4 `--as-of`).
    """
    from datetime import datetime, timezone
    from app import window as _w
    try:
        when = datetime.fromisoformat(str(m.get("utc") or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when <= _w.now_utc()


def _next_fixture(rows: list[dict]) -> dict | None:
    """🔴 #3 — 창 안이 0건일 때 **다음 경기**를 사유에 적기 위해서다."""
    later = [m for m in rows if m.get("utc") and not _kicked(m)]
    return min(later, key=lambda m: str(m.get("utc"))) if later else None


def team_fixtures(text: str, team_id: str) -> list[dict]:
    """🔴 팀 페이지의 **전체 일정**(끝난 것·남은 것) — 날짜 창으로 고르려면 둘 다."""
    from app.collect import fotmob as fm
    j = fm.payload(text)
    if not j:
        return []
    pp = ((j.get("props") or {}).get("pageProps") or {})
    box = (((pp.get("fallback") or {}).get(f"team-{team_id}") or {})
           .get("fixtures") or {})
    out: list[dict] = []
    for m in ((box.get("allFixtures") or {}).get("fixtures") or []):
        st = m.get("status") or {}
        tour = m.get("tournament")
        out.append({"id": str(m.get("id") or ""),
                    "home": str((m.get("home") or {}).get("name") or ""),
                    "away": str((m.get("away") or {}).get("name") or ""),
                    "utc": str(st.get("utcTime") or ""),
                    "finished": bool(st.get("finished")),
                    "league_name": (str(tour.get("name") or "")
                                    if isinstance(tour, dict)
                                    else str(tour or "")),
                    "league_id": (tour.get("id")
                                  if isinstance(tour, dict) else None),
                    "page": str(m.get("pageUrl") or "")})
    return out


async def _by_league(net, *, home: str, away: str, days: list[date],
                     got: Found, league: str = "", at: str = "",
                     spell: dict | None = None) -> Found:
    """🔴 §2 ③ 대체 — **리그 색인**에서 이름이 걸리는 리그의 일정을 본다.

    ⚠️ 리그 색인은 431개다 — 전부 열지 않는다. 🔴 질문의 **두 팀 이름 조각**이
       리그 슬러그에 걸리는 리그만 본다(`adelaide` → `australia-championship` 처럼
       도시 이름이 걸리는 일이 있다). 걸리는 것이 없으면 ③ 은 **아무것도 안 하고**
       그 사실을 적는다 — 없는 통로를 있는 척하지 않는다.
    """
    from app.collect import fotmob as fm
    index = await fm.league_index(net)
    got.tried.append(f"fotmob 리그 색인(sitemap) {len(index)}리그")
    # 🔴🔴 **질문의 대회 이름도 센다**(실측 2026-10-10: `turkish-cup` 은 리그
    #    색인에 **있는데** 예실유르트·겔레첵은 팀 색인에 **없다** — 그러면 ③ 만이
    #    길이고, ③ 이 리그를 찾는 재료는 질문의 대회 이름뿐이다).
    #  ⚠️ 한글 대회명(`터키컵`)은 여기서 안 걸린다 — fotmob 슬러그는 로마자다.
    #     그 한계를 `tried` 에 적는다(#3).
    words = [w for w in re.split(r"\s+", f"{league} {home} {away}".strip())
             if len(w) > 3]
    if league and not any(norm_name(w) for w in tokens(league)):
        got.tried.append(f"⚠️ 대회 힌트 `{league}` 는 로마자가 아니다 — 리그 "
                         f"색인(로마자 슬러그)에 못 맞춘다")
    hits = sorted({(i, s) for i, s in index.items()
                   for w in words if norm_name(w) in norm_name(s)})
    if not hits:
        got.tried.append("리그 색인에 걸리는 이름이 없다 — ③ 을 건너뛴다")
        return got
    want = {d.isoformat() for d in days}
    # 🔴 별칭으로 본다(§1-1 ②) — 한글로 물어도 로마자 일정과 맞는다
    ours = aliases_of(home, spell=spell)
    yours = aliases_of(away, spell=spell)
    for lid, slug in hits[:MAX_LEAGUES]:
        rows = await fm.league_matches(net, lid)
        got.tried.append(f"fotmob 리그일정 `{slug}` {len(rows)}경기")
        # 🔴 리그 전체는 **넓은 목록**이다 — 여기서는 `covers`(방향 있는 검사)만
        #    쓴다. ⚠️ 느슨하게 보면 같은 도시·같은 이름의 다른 팀이 붙는다.
        fit = [m for m in rows if str(m.get("utc") or "")[:10] in want
               and near_time(str(m.get("utc") or ""), at)
               and ((same_any(m["home"], ours) and same_any(m["away"], yours))
                    or (same_any(m["home"], yours)
                        and same_any(m["away"], ours)))]
        if len(fit) > 1:
            got.tried.append(f"🔴 `{slug}` 에서 후보 {len(fit)}건 — 고르지 않는다")
            continue
        if fit:
            m = fit[0]
            got.match, got.rung = m, "③ 리그 색인 → 리그 일정"
            got.league_id = lid
            got.league_name = slug
            got.why = f"✅ 리그 일정 — `{slug}` · {str(m.get('utc'))[:10]}"
            return got
    return got


async def register(net, *, league_id: object, league_name: str = "",
                   ccode: str = "", when: date | None = None,
                   ) -> tuple[dict, str]:
    """🔴🔴 §2 마지막 줄 — 찾은 경기의 **리그 id 로 자동 등록**을 건다.

    > 이미 있으면 **갱신만**.

    `(등록 표, 사유)` — 실패하면 `({}, 사유)` 이고 그 사유가 카드에 남는다(§1:
    *"필수 칸이 하나라도 없으면 등록 실패"*).
    """
    from app.collect import fotmob as fm
    from app.core import autoleague as al
    from app.core import competition as comp
    if not league_id:
        return {}, "🔴 등록 못 한다 — 리그 id 를 못 받았다"
    key, why_key = comp.key_of(competition=league_name, league_id=league_id)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **손 표의 열쇠로는 절대 쓰지 않는다**(실사고 2026-10-10)
    # ══════════════════════════════════════════════════════════════════
    #
    #  엘살바도르 리그가 **라리가 열쇠**(`league:PD`)로 등록돼 파일을 썼다.
    #  🔴 `config/competitions.yaml` 은 **사용자 영역**이고 거기엔 기준 모델·
    #     분할 규칙이 달려 있다 — 자동 등록이 그 열쇠를 덮으면 그 리그의 판정이
    #     통째로 거짓이 된다(M14).
    #  🔴 그래서: 손 표가 아는 대회면 **등록할 것이 없다**(이미 선언돼 있다).
    #     모르면 **리그 id 열쇠**로만 쓴다.
    if key and not key.startswith("league:fotmob"):
        return {}, f"등록 안 한다 — 손 표가 이미 아는 대회다({why_key})"
    key = f"league:fotmob{league_id}"
    # 🔴 **이미 오늘 확인했고 이 글자도 담겨 있으면 다시 받지 않는다**(§2: 갱신만).
    #    ⚠️ 분석마다 리그 표·일정을 다시 받으면 그 호스트에 실례다.
    from app import window as _w
    today = (when or _w.now_utc().date()).isoformat()
    have = al.load(key)
    if (have.get("checked_at") == today
            and str(league_name or "") in (have.get("seen") or [])):
        return have, f"이미 오늘 등록했다 — `{key}`"
    meta = await fm.league_meta(net, league_id)
    if not meta.get("ccode") and ccode:
        # 🔴🔴 **컵대회는 순위표가 없어서 나라 코드를 안 준다**(실측 2026-10-10:
        #    호주컵 `league:fotmob9471` → *"나라(ccode)를 못 받았다"*).
        #    🔴 경기 페이지의 `general.countryCode` 가 그것을 준다 — 부르는 쪽이
        #       넘겨준다(여기서 또 받지 않는다).
        meta = {**meta, "ccode": str(ccode)}
    if not meta.get("ccode"):
        return {}, (f"🔴 등록 실패 — `{key}` 의 나라(ccode)를 못 받았다"
                    f"(리그 표 페이지도·경기 페이지도 안 줬다)")
    page = await net.get(f"{fm.BASE}/leagues/{league_id}/table/x")
    teams = sorted(fm.team_ids(fm.payload(getattr(page, "text", "") or "")
                               or {}))
    whence = f"fotmob:{league_id}/table"
    if not teams:
        # 🔴🔴 **컵대회는 순위표가 없다** — 실측 2026-10-10: 호주컵 등록이
        #    *"필수 칸이 없다: ['teams']"* 로 실패했다. 🔴 그 대회의 **일정**이
        #    참가 팀을 전부 들고 있다(홈·원정 이름). 이름만 있고 번호는 없다 —
        #    그 사실을 `teams_from` 에 적는다(#3 조용히 메우지 않는다).
        fx = await fm.league_matches(net, league_id)
        teams = sorted({str(x[k]) for x in fx for k in ("home", "away")
                        if str(x.get(k) or "").strip()})
        whence = f"fotmob:{league_id}/matches (이름만 — 순위표가 없는 대회다)"
    rows = await fm.league_season_rows(net, league_id)
    # 🔴 **경기 페이지가 적은 글자**를 함께 담는다 — 카드 쪽이 그 글자만 받는다
    seen = [str(league_name or ""), str(meta.get("name") or "")]
    old_seen = load_seen(key)
    box, why = al.build(competition_key=key, meta=meta, teams=teams,
                        baseline=al.baseline_of(rows), seen=[*old_seen, *seen],
                        teams_from=whence, when=when)
    if not box:
        return {}, why
    p, said = al.save(box)
    return (box if p else {}), f"{why} · {said}"


def load_seen(key: str) -> list[str]:
    """🔴 이미 쌓인 **본 글자들** — 갱신이 그것을 지우지 않게(§2: *"이미 있으면
    갱신만"*). ⚠️ 덮어쓰면 어제 본 표기가 사라지고 같은 오진이 다시 난다."""
    from app.core import autoleague as al
    return [str(x) for x in (al.load(key).get("seen") or [])]


def same_team(said: object, want: object, *, loose: bool = False) -> bool:
    """🔴🔴 §1-2 — **팀 이름 대조의 입구 하나**. `(출처가 적은 이름, 사용자가 적은 이름)`.

    > 정규화 함수 하나(`same_team`). **방향 있는 대조**, 리그 id·나라·날짜로
    > 좁힌 자리에서만 **느슨한 대조**.

    | `loose` | 무엇 | 어디서 쓰나 |
    |---|---|---|
    | `False`(기본) | `covers` — **출처가 사용자 낱말을 전부 담을 때만** | 넓은 목록(리그 전체·색인) |
    | `True` | `alike` — 한쪽이 다른 쪽을 담으면 | 날짜·기준 팀이 **이미 좁힌** 자리 |

    🔴 왜 방향이 필요한가(실측 2026-10-10): 양방향으로 품게 하면
       `Cong An Hanoi`→`ha-noi-fc`(**다른 구단**) · `Union de Santa Fe`→
       `santa-fe`(**콜롬비아**)가 붙는다. 🔴 느슨한 쪽은 fotmob 이 **더 짧게**
       적는 경우(`Unión` ↔ `Union de Santa Fe`)를 잡으려고만 쓴다.
    ⚠️ 느슨한 자리에서 걸린 경기가 **둘 이상이면 고르지 않는다**(§1-3) — 그
       규율은 부르는 쪽(`_by_team`)이 지킨다.
    """
    return alike(said, want) if loose else covers(said, want)


def same_any(said: object, names: list[str], *, loose: bool = False) -> bool:
    """🔴🔴 §1-1 ② — 출처 이름이 그 팀의 **별칭 중 하나**와 맞나.

    ⚠️ 실사고가 될 자리였다(실측 2026-10-10): 상대 이름을 **원문자만** 대조해
       `부천`(한글)과 fotmob 의 `Bucheon FC 1995` 가 안 맞았고, 그래서 K리그·J리그
       경기를 **하나도 못 찾았다**. 🔴 질문은 *"한국어·영어·현지어 아무거나"* 다.
    🔴 별칭은 `aliases_of`(이름표)가 준다 — 여기서 짓지 않는다.
    """
    return any(same_team(said, one, loose=loose) for one in (names or []))
