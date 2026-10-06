"""fotmob 경기 페이지 — **확정/예상 XI 를 구조로 읽는다.**

## 왜 이 파일이 생겼나 (실측 2026-10-01)

단계 4 녹음에서 봇이 이 페이지에 **닿았는데 사실 0건**이었다:

```
www.fotmob.com/matches/sacramento-republic-fc-vs-las-vegas-lights-fc/d66zlwfw
  → 열었는데 사실 0건(검증거부·파서)
```

🔴 **도달은 됐고 변환이 안 됐다** — 사용자 승인으로 가른 4a/4b 중 **4b** 다.
   그런데 그 페이지에는 선수 이름이 **15/23명**, `Lineup` 이 **296회** 있었다.
   규칙 파서가 HTML 본문을 글자로 훑어서 못 읽은 것이고, 자료는 **JSON** 에 있었다.

페이지가 `<script id="__NEXT_DATA__">` 에 전부 싣는다:

```
props.pageProps.general.matchTimeUTCDate   경기 시각(UTC)
props.pageProps.general.started/finished   시작/종료
props.pageProps.content.lineup.homeTeam
    .name · .formation · .starters[11] · .coach · .subs · .rating
```

## 🔴 이 파일이 지키는 것

| 규칙 | 어떻게 |
|---|---|
| §13-c ① **그 경기 것인지** | `matchTimeUTCDate` 의 KST 날짜를 질문 날짜와 맞춘다 |
| §13-c ② **양 팀 11명** | `starters` 가 11명이 아니면 사실로 올리지 않는다 |
| §17-g-3 **귀속** | `homeTeam.name`·`awayTeam.name` 과 질문 팀을 `verify.mentions_team` 으로 맞춘다 |
| §12-c-5 층 | fotmob 은 집계 매체다 — **2층**(1차 소스가 아니다) |
| 🔴 **확정 XI 와 예상 XI 를 구분한다** | 경기가 시작됐으면 확정(hard), 아니면 **기준 XI**(soft) |

🔴 **마지막 칸이 이 파일의 핵심이다.** 사용자가 쓴 글의 첫 문장이 그 구분이다:

> 확정 XI는 아직 색인에 안 잡힌다(킥오프 11:00, 발표는 보통 1시간 전).
> 잡힌 건 양 팀 **"직전 경기 선발 XI"** 라 그걸 **기준 XI** 로 놓고 재작성한다.

경기 전에는 fotmob 도 **예상**을 보여 준다. 그것을 확정이라고 적으면 거짓이다 —
`lineup_kind` 로 갈라 싣고, 카드가 그대로 적는다(결정 C).

⚠️ robots: `www.fotmob.com` 은 `User-agent: *` 에 `Allow: /` 이고 **`/api/*` 만
   금지**다. 우리는 **페이지를 읽는다** — API 를 부르지 않는다.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone

from app import league, timefmt, verify, window
from app import matchkey
from app.blackboard import Fact
from app.cells import SUB_QUESTIONS, Question, Source

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

#: 🔴 이 어댑터가 맡는 종목. `slate_row` 가 그 이름으로 행을 만든다.
#   ⚠️ `kleague`·`npb` 와 **같은 규약**이다(상수로 밝힌다) — 행 안에만 적으면
#      "표에 어떤 종목이 있나"를 밖에서 못 읽는다.
SPORT = "soccer"

#: 축구 선발은 11명이다(§13-c ②). 🔴 모자라면 사실로 올리지 않는다.
XI = 11

#: 🔴 접미사의 원본은 `app/cells.SUB_QUESTIONS` 다 — 여기 베끼지 않는다.
#   축구만의 것이 아니다: 야구(statsapi)·하키(api-web)가 같은 접미사를 쓴다.
SUFFIXES = SUB_QUESTIONS

#: 페이지가 자료를 싣는 자리. 🔴 주소가 아니라 **문서 안**이다.
_NEXT = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def is_match_page(url: str) -> bool:
    """fotmob **경기** 페이지인가. 🔴 팀·리그 페이지는 라인업이 없다.

    🔴 두 꼴을 다 받는다(실측 2026-10-02):
        `/matches/china-vs-palestine/17zll3`   검색이 내는 꼴(슬러그 포함)
        `/match/6280453`                        **번호만으로 닿는 꼴**
    ⚠️ 두 번째가 중요하다 — `games.ext_id` 에 번호만 남으므로, 그 꼴을 못 읽으면
       저장된 경기의 깊이를 **다시 열 수 없다**(축구가 깊이 0이던 까닭).
    """
    u = url or ""
    return "fotmob.com" in u and ("/matches/" in u or "/match/" in u)


def match_id(url: str) -> str:
    """경기 주소에서 **fotmob 경기 번호**. 🔴 못 읽으면 빈 문자열.

    ⚠️ `ext_id` 의 재료다 — 번호가 없으면 같은 경기가 주소 표기마다 새 행이 된다
       (실측 2026-10-02: fotmob 이 같은 경기를 `/matches/…` 와 `/en-GB/matches/…`
       둘로 준다).
    """
    u = str(url or "")
    m = (re.search(r"/matches/[^/]+/([A-Za-z0-9]+)", u)
         or re.search(r"/match/([A-Za-z0-9]+)", u))
    # 🔴🔴 **숫자만 찾으면 안 된다**(실측 2026-10-02). fotmob 경기 id 는
    #    `17zll3` 처럼 **영숫자**다. 숫자만 뽑던 종전 코드는 빈 문자열을 냈고,
    #    그래서 같은 경기의 두 주소(`/matches/…` 와 `/ko/matches/…`)를 **다른
    #    경기로 보고 두 번 열었다** — 열기 예산을 한 번 더 썼다.
    #  ⚠️ 언어 조각(`/ko/`·`/en-GB/`)은 `/matches/` 앞이라 여기 안 걸린다.
    return m.group(1) if m else ""


#: 🔴 `games.ext_id` 의 접두. **이 어댑터가 만든 행**이라는 표시다.
#   ⚠️ `findgame` 이 행을 적을 때 쓰고(`f"{EXT_PREFIX}{matchId}"`), 깊이를 고를 때
#      다시 읽는다 — 두 곳이 같은 상수를 본다(사본 금지).
EXT_PREFIX = "fotmob-"


def match_url(mid: str) -> str:
    """🔴 **번호만으로 경기 페이지에 닿는다**(실측 2026-10-02: 200 · 같은 자료).

    ⚠️ 슬러그(`china-vs-palestine`)는 표기라서 바뀔 수 있다. 번호가 열쇠다.
    """
    return f"{BASE}/match/{str(mid or '').strip()}"


def sources_context(ext_id: str) -> list[Source]:
    """🔴🔴 **이 경기의 공식 깊이** — 맞대결·폼·선수·경기정보 + 직전 경기·리그 표.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 이 함수가 생겼나 (실측 2026-10-02)
    ══════════════════════════════════════════════════════════════════

    `analyze.depth_sources` 는 어댑터의 `sources_context` 를 찾는데, **fotmob 에
    그 함수가 없었다.** 그래서 **축구는 깊이가 통째로 0** 이었다 — 순위표·맞대결·
    폼이 한 건도 안 들어오고, 라인업 세포가 검색으로 우연히 경기 페이지를 열 때만
    그 자료가 섞여 들어왔다.

    라이브(중국 vs 팔레스타인 친선): 사실 6건 · 변수 **0건** · §7 R5 자료 부족.
    🔴 그런데 그 경기 페이지는 **봇이 이미 찾아서 `ext_id` 에 번호를 적어 뒀다.**

    ⚠️ 파서는 이미 있었다(`parse_context`·`follow_links`·`parse_followed`) —
       **부르는 곳이 없었을 뿐이다**(CLAUDE.md #2 배선).
    🔴 `dateless_ok` 를 켠다 — 경기 페이지에는 발행 시각이 없고, 그 대신
       `parse_context` 가 §13-c ①(날짜)·②(두 팀)를 **이미 집행한다**. 그것이
       `Source.dateless_ok` 가 요구하는 조건이다.
    """
    # 🔴 **접두를 요구한다.** 안 요구하면 MLB 의 숫자 `ext_id`(`849844`)도 통과해
    #    야구 경기에 fotmob 축구 페이지를 붙인다 — 남의 경기다(§17-g-3).
    # 🔴 §8-1 — `matchkey.mine` 이 *"내 것이냐"* 까지 답한다. ⚠️ 종전
    #    `startswith("fotmob-")` 은 `fotmob:5181853` 을 거절했다(실측 2026-10-04).
    mid = matchkey.mine(ext_id, "fotmob")
    if not mid or not re.fullmatch(r"[A-Za-z0-9]{2,}", mid):
        return []
    return [Source("fotmob 경기 맥락", "url", url=match_url(mid),
                   tier=verify.TIER_PREVIEW, parse=parse_context,
                   # 🔴 §19-c — 직전 경기(기준 XI)와 리그 표를 가리킨다
                   follow=follow_links, parse_follow=parse_followed,
                   # ══════════════════════════════════════════════════
                   # 🔴🔴 **§4-6 — `follow_max` 를 선언한다**(실측 2026-10-04)
                   # ══════════════════════════════════════════════════
                   #
                   #  > 어댑터 깊이 소스는 소스마다 `follow_max` 를 선언하고
                   #  > 공유 예산을 쓰지 않는다. **선언 없는 소스는 계약 실패.**
                   #
                   #  ⚠️ 이 소스에 그 선언이 **없었다** — 깊이 세포의 열기 예산이
                   #     `1 + follow_max` 로 계산되므로 0 이면 따라가기가 **조용히
                   #     끊긴다**(실측 2026-10-04: MLB 가 같은 병으로
                   #     `예고 선발:예산소진` 을 냈다).
                   #  🔴 `follow_links` 가 **몇 개를 내나**로 정한다 — 직전 경기
                   #     둘(양 팀) + 리그 표 하나다.
                   follow_max=3,
                   dateless_ok=True)]


def slate_row(got, *, day: date | None = None) -> dict | None:
    """🔴 **경기 페이지 → 슬레이트 한 줄.** `ingest._slate` 가 받는 그 모양이다.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 이 함수가 생겼나 (사용자 지시 2026-10-02)
    ══════════════════════════════════════════════════════════════════

    > 봇이 서치한다..봇이 가설세운다..봇이 변수 만든다..봇이 결과값은 준다

    봇이 아는 리그는 어댑터가 있는 것뿐이다(`ADAPTERS`). 그래서 **국제 친선**처럼
    어댑터가 없는 경기는 `games` 표에 없고, 질문하면 *"분석할 경기를 못 찾았다"* 가
    돌아온다. 사람이 손으로 행을 넣으면 그것은 봇이 한 것이 아니다.

    🔴 그런데 fotmob **경기 페이지에 필요한 것이 다 있다** — 킥오프(UTC)·홈/원정·
       구장·대회명. 그 페이지는 봇이 이미 검색으로 찾아 열고 있다(§19-c 라인업 깊이).
    ⚠️ 새 소스를 들이지 않는다 — **이미 쓰는 호스트**다(robots 결정이 이미 서 있다).
    🔴 못 읽는 칸은 `None` 이고, 킥오프를 못 읽으면 **행을 만들지 않는다**
       (`ingest._slate` 가 시각 없는 행을 버린다 — 거기에 맞춘다).
    """
    if not getattr(got, "ok", False):
        return None
    url = str(getattr(got, "url", "") or "")
    if not is_match_page(url):
        return None
    j = payload(getattr(got, "text", "") or "")
    if not j:
        return None
    g = _page(j).get("general") or {}
    home = str(((g.get("homeTeam") or {}).get("name") or "")).strip()
    away = str(((g.get("awayTeam") or {}).get("name") or "")).strip()
    when = kickoff(j)
    # 🔴🔴 **열쇠는 `matchId` 다 — 주소 꼬리가 아니다**(실측 2026-10-02).
    #    주소 꼬리(`17zll3`)는 **표기**이고, 표기는 바뀔 수 있다. 바뀌면 같은 경기가
    #    `games` 에 **두 행**이 된다(ON CONFLICT 열쇠가 `ext_id` 다).
    #    ⚠️ `match_id(url)` 은 **중복 열기 방지**에만 쓴다(같은 경기의 다른 주소).
    ext = str(g.get("matchId") or "").strip() or match_id(url)
    if not (home and away and when and ext):
        logger.info("[fotmob] 슬레이트 행을 못 만들었다 — 홈=%r 원정=%r 시각=%s "
                    "번호=%r (%s)", home, away, when, ext, url)
        return None
    # 🔴 **그 날짜 경기인가** — 물은 날짜와 다르면 남의 경기다(§13-c ①)
    # ══════════════════════════════════════════════════════════
    # 🔴🔴 **창으로 거른다** — 지금부터 36시간(UTC) · 지시 2026-10-04
    # ══════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전엔 **KST 달력 날짜**가 같아야 통과였다. 🔴 유럽·북미 저녁
    #     경기는 KST 로 **내일**이라(유럽 20:45 = KST 03:45) *"오늘의 경기"*
    #     가 **구조적으로 전부** 떨어졌다(실측: 포르투갈 vs 노르웨이).
    #  🔴 수는 `app/window.py` **한 곳**에 있다(사본 금지).
    said_out = window.why_out(when)
    if said_out:
        logger.info("[fotmob] 창 밖이라 안 싣는다 — %s (%s)", said_out, url[:70])
    if said_out:
        logger.info("[fotmob] 날짜가 다르다 — 페이지 %s vs 물은 날짜 %s (%s)",
                    when.astimezone(KST).date(), day, url)
        return None
    box = _box(j).get("infoBox") or {}
    # 🔴🔴 **칸이 dict 로 온다 — 문자열로 캐스팅하면 사전이 그대로 저장된다.**
    #    실측 2026-10-02: `venue` 칸에 `{'name': 'Chongqing Longxing Football
    #    Stadium', 'city': …, 'lat': …}` 가 **글자로** 들어갔다. CLAUDE.md §5 가
    #    적어 둔 그 병이다 — *"JSONB 가 문자열로 오고…"*.
    league = _name_of(box.get("Tournament")) or _name_of(g.get("leagueName"))
    return {
        "sport": SPORT,
        # 🔴 대회명을 못 읽으면 **빈칸이 아니라 이름으로** 남긴다
        "league": league or "대회명 미상",
        "ext_id": matchkey.make("fotmob", ext),
        "home": home, "away": away,
        "venue": _name_of(box.get("Stadium")) or None,
        "starts_utc": when,
        # 🔴 `timestamptz` 는 **순간**이다 — `.astimezone(KST)` 는 이 칸에
        #    아무 효과가 없었다(실측 2026-10-05: 라이브 52행 전부
        #    `starts_kst = starts_utc`). 🔴 그 거짓 믿음을 입구에서 끊는다 —
        #    표시 KST 는 `timefmt.kst_label`, KST 날짜 질의는
        #    `timefmt.sql_kst_day` **하나씩**이다.
        "starts_kst": timefmt.db_instant(when),
        "starts_local": None,       # 🔴 현지 시각대를 페이지가 안 준다 — 지어내지 않는다
        "status": "final" if _started(j) and g.get("finished") else (
            "inprogress" if _started(j) else "scheduled"),
        # 🔴🔴 **라운드 표기를 읽는다** — 실측 2026-10-05: 종전에 `None` 을
        #    박아 두고 *"못 읽는다"* 고 적어 뒀는데, 페이지는 `roundName` 을
        #    **명시한다**(인도네시아–태국 `6232991` → `"final"`). 그 한 칸이
        #    §3-3 `match_format` 의 재료다 — 안 읽어서 90분 무승부 필수형이
        #    발동할 재료가 **있는데도** 없었다.
        "round_note": round_note(j) or None,
        "home_score": None, "away_score": None,
        "probable": {},
    }


def round_note(j: dict) -> str:
    """🔴 그 경기의 **라운드 표기** — `games.round_note` 에 그대로 들어간다.

    자리는 `content.matchFacts.infoBox.Tournament` 다(실측 2026-10-05):

    ```
    "Tournament":{… ,"leagueName":"FIFA ASEAN Cup …","roundName":"final","round":"final"}
    ```

    ⚠️ 리그 경기는 `roundName` 이 **라운드 번호**다(`"2"`) — 그것도 사실이므로
       그대로 싣는다. 번호를 형식으로 바꾸는 것은 `scenarios.match_format` 이고,
       그 표가 못 맞추면 `unknown` 이다(지어내지 않는다 · §3-3).
    🔴 못 읽으면 **빈 문자열** — `null` 을 `"None"` 이라는 글자로 만들지 않는다.
    """
    t = ((_box(j).get("infoBox") or {}).get("Tournament") or {})
    if not isinstance(t, dict):
        return ""
    for k in ("roundName", "round"):
        got = t.get(k)
        if isinstance(got, str) and got.strip():
            return got.strip()
        if isinstance(got, int):
            return str(got)
    return ""


def _name_of(v) -> str:
    """🔴 `dict`·`list`·문자열 어느 것으로 와도 **사람이 읽을 이름**만 꺼낸다.

    ⚠️ 실측 2026-10-02: fotmob `infoBox.Stadium` 이 사전이다
       (`{'name': …, 'city': …, 'lat': …}`). `str()` 로 감싸면 그 사전이 통째로
       `games.venue` 에 글자로 들어간다.
    🔴 이름 칸을 못 찾으면 **빈 문자열** — 사전을 글자로 만들지 않는다.
    """
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        for k in ("name", "leagueName", "shortName", "stadiumName", "text"):
            got = v.get(k)
            if isinstance(got, str) and got.strip():
                return got.strip()
        return ""
    if isinstance(v, (list, tuple)):
        for x in v:
            got = _name_of(x)
            if got:
                return got
    return ""


def payload(html: str) -> dict | None:
    """`__NEXT_DATA__` 를 꺼낸다. 🔴 없거나 JSON 이 아니면 `None` — 지어내지 않는다."""
    m = _NEXT.search(html or "")
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError as exc:
        logger.info("[fotmob] __NEXT_DATA__ 가 JSON 이 아니다: %s", exc)
        return None


def _page(j: dict) -> dict:
    return ((j.get("props") or {}).get("pageProps") or {})


def kickoff(j: dict) -> datetime | None:
    """경기 시각(UTC). 🔴 §13-c ① 을 이것으로 집행한다."""
    raw = ((_page(j).get("general") or {}).get("matchTimeUTCDate") or "")
    return verify.parse_when(str(raw).replace("Z", "+00:00"))


def _started(j: dict) -> bool:
    g = _page(j).get("general") or {}
    return bool(g.get("started") or g.get("finished"))


def _side(j: dict, which: str) -> dict:
    return ((_page(j).get("content") or {}).get("lineup") or {}).get(which) or {}


def _names(team: dict) -> list[str]:
    out = []
    for p in team.get("starters") or []:
        if isinstance(p, dict) and str(p.get("name") or "").strip():
            out.append(str(p["name"]).strip())
    return out


def players_of(team: dict) -> list[dict]:
    """🔴🔴 **선발 11명을 이름+포지션+등번호로**(축구 완성 지시서 §2).

    ⚠️ 기존 `_names` 는 **이름만** 냈다 — 그래서 결장 유형(수비/공격)을 포지션으로
       정할 수 없었고, 카드 블록 2 도 포지션 약자를 못 찍었다.
    🔴 fotmob 이 쓰는 칸 이름이 판마다 다르다(`role`·`positionId`·`position`·
       `shirtNumber`·`shirt`). **있는 것을 쓰고 없으면 빈칸**이다(지어내지 않는다).
    """
    out: list[dict] = []
    for p in team.get("starters") or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        pos = ""
        for key in ("role", "position", "positionStringShort", "positionString"):
            got = p.get(key)
            if isinstance(got, str) and got.strip():
                pos = got.strip()
                break
        num = p.get("shirtNumber", p.get("shirt"))
        try:
            number = int(num) if num is not None else None
        except (TypeError, ValueError):
            number = None
        out.append({"name": name, "pos": pos, "number": number})
    return out


#: 🔴 fotmob `unavailability.type` → 우리 사유 열거값(§2). ⚠️ 모르면 `other`
_MISS_REASON = {"injury": "injury", "suspension": "suspension",
                "suspended": "suspension", "doubtful": "doubtful",
                "international": "international_duty",
                "international_duty": "international_duty"}


def missing_of(team: dict) -> list[dict]:
    """🔴🔴 **결장 명단**(§2) — `lineup.{home,away}Team.unavailable` 이 원본이다.

    🔴 실측 2026-10-06(한국–우즈베키스탄 경기 페이지):

    ```
    unavailable[0] = {'name': 'Jens Castrop', 'age': 23,
                      'unavailability': {'injuryId': 32, 'type': 'injury',
                                         'expectedReturn': 'Mid October 2026'}}
    ```

    ⚠️ **파서가 이 칸을 버리고 있었다** — 그래서 결장이 기사에서만 왔고, 같은 사실이
       기사마다 다른 유형으로 셌다. 🔴 구조 사실로 받으면 그 병이 사라진다.
    ⚠️ 포지션 칸은 이 꼴에 **없다**(실측) — 빈칸으로 두고 `player_pos` 가 채운다.
    """
    out: list[dict] = []
    for p in team.get("unavailable") or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        box = dict(p.get("unavailability") or {})
        said = str(box.get("type") or "").strip().lower()
        out.append({"name": name,
                    "pos": str(p.get("role") or p.get("position") or "").strip(),
                    "reason": _MISS_REASON.get(said, "other"),
                    "returns": str(box.get("expectedReturn") or "").strip()})
    return out


def lineup_kind_of(j: dict) -> str:
    """🔴🔴 **확정이냐 예상이냐 — 경기 페이지의 표식만 본다**(§2 · 금지 항목).

    > 확정은 **경기 페이지의 확정 표식만**(기사로 XI 를 확정 상태로 표시 금지).

    🔴 실측 2026-10-06: 라인업이 아직 없으면 `lineupType: "unavailable"` 이다.
       발표되면 fotmob 이 `lineupType` 을 바꾼다(`confirmed`·`lineup`).
    ⚠️ 모르면 `predicted` 다 — **확정이라고 적지 않는다**(fail-closed).
    """
    lu = ((_page(j).get("content") or {}).get("lineup") or {})
    said = str(lu.get("lineupType") or "").strip().lower()
    if said in ("unavailable", ""):
        return "none"
    if "confirm" in said or said in ("lineup", "official", "starting"):
        return "confirmed"
    return "predicted"


def squad_names(team: dict) -> list[str]:
    """🔴🔴 **그 경기의 스쿼드 전원**(선발 + 교체). 명단 대조의 재료다.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 넓히나 (실측 2026-10-03)
    ══════════════════════════════════════════════════════════════════

    명단 검사(`ids.squad_check`)가 쓰던 명단이 **선발 11명뿐**이었다. 그러면
    교체 명단 선수가 기사에 나오면 *"우리 명단에 없다"* 로 **멀쩡한 사실을 버린다**.
    ⚠️ 거꾸로도 위험하다 — 명단이 좁으면 `in_roster` 가 `False` 를 내고, 그 `False`
       가 주체 귀속 검사의 두 번째 문을 닫는다.

    🔴 fotmob 라인업은 `starters`(11) + `subs`(15) 를 **둘 다** 준다 — 그것이
       경기일 스쿼드다. 새 소스가 필요 없다.
    """
    out = list(_names(team))
    for p in (team or {}).get("subs") or []:
        if isinstance(p, dict) and str(p.get("name") or "").strip():
            nm = str(p["name"]).strip()
            if nm not in out:
                out.append(nm)
    return out


def value_sum(team: dict) -> tuple[int | None, int]:
    """선발 **시장가치 합**과 **읽은 인원**. 🔴 한 명도 못 읽으면 `(None, 0)`.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 이 함수가 생겼나 — 딥서치 2026-10-03 (사용자 지시)
    ══════════════════════════════════════════════════════════════════

    > 축구 라인업 시장가치 소스를 쓰나? **딥서치해서 찾아서 넣어라.**

    ✅ **새 소스가 필요 없었다.** fotmob 경기 페이지의 라인업 선수마다
    `marketValue` 칸이 있다(실측: 선발 11 + 교체 15 **전원**). 그 페이지는 봇이
    이미 열고 있다 — robots 결정도 이미 서 있다.
    ⚠️ Transfermarkt 도 `User-agent: * Allow: /` 라 **쓸 수는 있었다**. 쓰지 않는다 —
       같은 자료를 이미 받는데 호스트를 늘리면 막히는 자리가 늘어난다.

    🔴 **이 수를 λ 에 넣지 않는다**(아래 `league.expected_goals` 참조). 가치를
       **골 단위로 바꾸는 계수가 발표된 적이 없다** — 발표된 모형(Peeters 와 후속)은
       `(log 가치차)` 에 걸린 **순서 프로빗**이고 그 계수는 논문에 실려 있지 않다.
       그래서 가치는 **변수**가 되고(§4 `lineup_value`), λ 는 안 건드린다.
    """
    got, n = 0, 0
    for p in (team or {}).get("starters") or []:
        if not isinstance(p, dict):
            continue
        v = p.get("marketValue")
        if isinstance(v, (int, float)) and v > 0:
            got += int(v)
            n += 1
    return (got, n) if n else (None, 0)


def _coach(team: dict) -> str | None:
    c = team.get("coach")
    if isinstance(c, dict):
        return str(c.get("name") or "").strip() or None
    return str(c).strip() or None if c else None


def parse_match(got, q: Question, *, day: date | None = None) -> list[Fact]:
    """fotmob 경기 페이지 → 라인업 사실. 🔴 **질문한 팀의 것만** 돌려준다.

    ⚠️ 한 페이지에 **두 팀**이 있다. 둘 다 올리면 §17-g-3 가 금지한 귀속 혼동이
       된다(M14: 阪神 선수를 소프트뱅크 명단에 저장). 질문의 팀을 가려 그쪽만 싣는다.
    """
    url = getattr(got, "url", "") or ""
    if not is_match_page(url):
        return []
    j = payload(getattr(got, "text", "") or "")
    if j is None:
        return []

    # 🔴 §13-c ① — **그 경기 것인가.** 날짜가 다르면 다른 경기다.
    when = kickoff(j)
    if when is None:
        logger.info("[fotmob] 경기 시각이 없다 — 올리지 않는다 %s", url[:90])
        return []
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **신원은 순간으로 본다** — 창이 아니다(지시 2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전은 **KST 달력 날짜**였다 — 유럽 저녁 경기가 KST 로 내일이라
    #     *"날짜가 다르다"* 로 버려졌다(포르투갈 vs 노르웨이).
    #  🔴 그렇다고 **창**으로 보면 안 된다: 창은 *"분석 범위인가"* 이고 여기는
    #     *"이 페이지가 그 경기인가"* 다. 섞으면 **지난 경기 페이지를 못 읽는다**
    #     (실측: 섞었다가 고정물 58건이 터졌다).
    #  🔴 그래서 **물은 킥오프와 같은 순간인가**(UTC)를 본다.
    want = q.deadline if q.deadline else None
    if want is not None and not window.same_match_time(when, want):
        logger.info("[fotmob] §13-c 거부 — 다른 날 경기다(%s ≠ %s) %s",
                    when.astimezone(KST).date(), want, url[:80])
        return []

    team = (q.team or "").strip()
    out: list[Fact] = []
    for which in ("homeTeam", "awayTeam"):
        side = _side(j, which)
        name = str(side.get("name") or "").strip()
        if not name:
            continue
        # 🔴 §17-g-3 — 질문한 팀만. 둘 다 올리면 귀속이 섞인다
        if team and not verify.mentions_team(name, team, q.local):
            continue
        names = _names(side)
        gone = missing_of(side)
        coach_name = _coach(side)
        if len(names) != XI and not (gone or coach_name):
            # 🔴 §13-c ② — 11명도 아니고 **결장·감독도 없다** → 올릴 것이 없다
            logger.info("[fotmob] %s 선발 %d명(11 아님) · 결장 0 · 감독 없음 — "
                        "올리지 않는다", name, len(names))
            continue
        if len(names) != XI:
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **XI 가 없어도 결장·감독은 올린다** — 축구 완성 지시서 §2
            # ══════════════════════════════════════════════════════════
            #
            #  > 결장 · 징계 명단이 **구조 사실로** 들어온다(기사에서만 건지지 않는다)
            #
            #  ⚠️ 실측 2026-10-06: 이 자리에서 `continue` 해서 **결장 명단
            #     (`unavailable`)과 감독을 통째로 버렸다** — 라인업이 아직 안 나온
            #     경기(킥오프 4시간 전)에서는 그것이 **전부**였다.
            #  🔴 XI 는 빈 목록으로 두고(그 사실이 `lineup_state` 에 남는다) 나머지를
            #     올린다. §2: *"어느 칸이든 못 받으면 None 과 사유."*
            logger.info("[fotmob] %s 선발 %d명 — XI 는 비우고 결장 %d·감독 %s 올린다",
                        name, len(names), len(gone), bool(coach_name))
            names = []
        # 🔴 **확정이냐 기준이냐.** 경기 전 fotmob 은 예상을 보여 준다 —
        #    그것을 확정이라고 적으면 거짓이다(사용자 글 첫 문장이 이 구분이다).
        started = _started(j)
        kind = "confirmed" if started else "baseline"
        out.append(Fact(
            question_id=q.id,
            value={"team": name, "formation": side.get("formation"),
                   "players": names, "coach": coach_name,
                   # 🔴 축구 완성 지시서 §2 — 포지션·등번호·결장 명단을 **함께** 싣는다
                   "lineup": players_of(side),
                   "missing": gone,
                   "lineup_state": lineup_kind_of(j),
                   "subs": len(side.get("subs") or []),
                   # 🔴 카드가 **이 칸을 그대로 적는다**(결정 C)
                   "lineup_kind": kind,
                   # 🔴 **경기일 스쿼드 전원**(선발+교체) — 명단 대조의 재료다
                   "squad": squad_names(side),
                   # 🔴 **라인업 시장가치 합**(딥서치 2026-10-03). 못 읽으면 `None`
                   **dict(zip(("value_sum", "value_players"),
                              value_sum(side), strict=True)),
                   "lineup_type_raw": ((_page(j).get("content") or {})
                                       .get("lineup") or {}).get("lineupType")},
            # 🔴 경기 전 예상은 **soft** 다 — 바뀔 수 있다(방아쇠가 그것을 본다)
            hardness="hard" if started else "soft",
            source=url, publisher="fotmob",
            published_at=when,
            article_title=f"{name} XI ({kind})",
            # 🔴 §12-c-5 — fotmob 은 1차 소스가 아니라 **집계 매체**다.
            #    `verify` 의 층 상수가 원본이다(여기 숫자를 적지 않는다).
            tier=verify.TIER_PREVIEW,
            extracted_by="rule:fotmob_next_data", step=1, team=name))
    if out:
        logger.info("[fotmob] %s → %d팀 · %s", url[:70], len(out),
                    [f.value["lineup_kind"] for f in out])
    return out


# ══════════════════════════════════════════════════════════════════
# 🔴 같은 페이지의 나머지 블록 — **한 번 열고 다 읽는다**
# ══════════════════════════════════════════════════════════════════
#
# 측정 2026-10-01 이 이것을 요구했다:
#
#     도달 7/15  ← 자료는 봇이 가져온 페이지 안에 있었다
#     변환 0/15  ← 그런데 사실로 뽑지 못했다
#
# 🔴 R2·R4·R5·R7 이 **전부 이 한 페이지의 같은 JSON** 에 있었다. 파서가 `lineup`
#    블록만 읽고 나머지를 버렸다. 열기 예산은 이미 썼으므로 **읽는 것은 공짜다.**
#
# ⚠️ **§19-a 에 이 질문들의 타입이 없다.** `Q_TYPES` 는 여덟이고 거기에 맞대결·
#    경기통계·폼이 없다. 🔴 타입을 **지어내지 않는다** — `source_score` 의 CHECK 가
#    그 목록을 강제하고, 늘리는 것은 규칙 변경이라 사용자 결정이다(단계 5).
#    그래서 질문 **id 에 접미사**를 붙여 가른다(`…:h2h`). 저장소가 이미 쓰는 방식이고
#    (`searchcells.coach_cell` 의 `:coach`), 블랙보드가 그 꼴을 읽는다.
#    → `docs/fable/questions/2026-10-01_question_types.md`


def _box(j: dict) -> dict:
    return ((_page(j).get("content") or {}).get("matchFacts") or {})


def _when_of(entry: dict):
    """경기 시각. 🔴 **자리가 블록마다 다르다** — 셋을 다 본다.

    ⚠️ 실측 2026-10-02: `teamForm` 은 `date.utcTime` 에 싣고 **`h2h` 는 `date` 가
       `null` 이고 `status.utcTime`·`time.utcTime` 에 싣는다.** 한 자리만 보다가
       맞대결 33경기 전부가 "날짜 없음"이 되어 **창이 안 잘렸다**(§4 창 10경기).
    """
    for holder in ("date", "status", "time"):
        raw = ((entry.get(holder) or {}) or {}).get("utcTime")
        got = verify.parse_when(str(raw or "").replace("Z", "+00:00"))
        if got is not None:
            return got
    return None


def parse_h2h(j: dict, q: Question, *, url: str, when) -> list[Fact]:
    """맞대결 기록. 🔴 사용자 R5 가 이것이다 — *"직전 대결 5-0, 올해 1차전 1-1"*.

    ⚠️ **제목에 스코어를 쓰지 않는다.** `verify.not_post_game` 이 제목의 `5-0` 을
       경기 결과로 읽어 *"경기 후 기사"* 로 거부한다(§12-c-2). 실측으로 한 번 그랬다.
    """
    h = ((_page(j).get("content") or {}).get("h2h") or {})
    rows = []
    for m in (h.get("matches") or []):
        mw = _when_of(m)
        st = m.get("status") or {}
        score = str(st.get("scoreStr") or "").strip()
        home = (m.get("home") or {}).get("name") if isinstance(m.get("home"), dict) else None
        away = (m.get("away") or {}).get("name") if isinstance(m.get("away"), dict) else None
        if not (score and home and away):
            continue
        # 🔴 **스코어를 숫자로 쪼갠다.** fotmob 은 `"5 - 0"`(공백 포함)으로 준다 —
        #    표시용 문자열이다. 단계 6·7 은 **숫자**가 필요하고(총점·핸디 계산),
        #    대조도 숫자로 해야 맞는다.
        #    ⚠️ 실측 2026-10-01: 측정이 `"5-0"` 을 찾는데 자료는 `"5 - 0"` 이라
        #       R5 가 떨어졌다. 표기 차이로 사실이 없는 것처럼 보였다.
        gm = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*$", score)
        hg, ag = (int(gm.group(1)), int(gm.group(2))) if gm else (None, None)
        rows.append({"date": mw.date().isoformat() if mw else None,
                     "home": home, "away": away,
                     # 🔴 **정규화한 꼴과 원문을 함께** 싣는다
                     "score": f"{hg}-{ag}" if gm else score,
                     # 🔴 **정본 이름**(§8-3) — 종전 `home_goals`/`away_goals`
                     #    는 fotmob 하나만 쓰던 **어댑터 고유 칸**이었고, 그것이
                     #    밖으로 새서 야구·하키 맞대결이 **0승 0패**로 세졌다(#6).
                     #    ⚠️ 변환은 **여기서** 끝난다 — 읽는 쪽에 분기가 없다.
                     "score_raw": score, "home_score": hg, "away_score": ag,
                     # 🔴 **그 경기 페이지 주소** — 전반 스코어가 거기에만 있다
                     #    (`sources_followup` 이 이것으로 한 바퀴 더 돈다)
                     "matchUrl": str(m.get("matchUrl") or "")})
    if not rows:
        return []
    # 🔴 **창을 자르고 표본 수로 weight 를 정한다**(§4 `h2h_pattern.sample_weight`).
    #
    #  ⚠️ 실측 2026-10-02: 같은 맞대결 30경기를 창만 바꿔 재니 3경기 창은 상대
    #     승률을 **0%** 로 말했다(실제 36.7%) — 경기당 총골도 4.67↔2.73 으로
    #     1.93골 흔들렸다. 2026-10-01 에 그 함정으로 낙첨했다.
    #  🔴 창 안의 경기 수로 weight 가 정해진다 — 단계 5 가 그 값을 쓴다.
    win = league.h2h_window(rows)
    used = win or rows
    tot = sum((m["home_score"] or 0) + (m["away_score"] or 0) for m in used
              if m.get("home_score") is not None)
    n_scored = sum(1 for m in used if m.get("home_score") is not None)
    return [Fact(question_id=f"{q.id}:h2h",
                 value={
                        # ══════════════════════════════════════════════
                        # 🔴🔴 **정본 이름**(§8-3) — `matches` 는 *"규칙이 세는
                        #    것"*, 즉 **창 안의 경기**다
                        # ══════════════════════════════════════════════
                        #
                        #  ⚠️ 종전에는 `matches` 가 **전체**이고 창이 `window`·
                        #     `window_games` 라는 **fotmob 고유 칸**에 있었다.
                        #     그래서 그 두 이름을 모르는 어댑터(mlb·nhl)의 맞대결은
                        #     표본이 **0경기**로 세졌다(#6 · 실측 2026-10-04).
                        #  🔴 §7 R7 의 *"두 창"* 은 그대로다 — 전체는 `all_games`
                        #     에 남는다. 이름만 정본으로 바꿨다.
                        "matches": used, "count": len(used),
                        "all_games": len(rows),
                        "sample_weight": league.h2h_weight(len(used)),
                        "window_avg_goals": (round(tot / n_scored, 3)
                                             if n_scored else None),
                        "summary": h.get("summary")},
                 hardness="hard", source=url, publisher="fotmob",
                 published_at=when, article_title="맞대결 기록",
                 tier=verify.TIER_PREVIEW,
                 extracted_by="rule:fotmob_h2h", step=1, team=q.team)]


def parse_form(j: dict, q: Question, *, url: str, when) -> list[Fact]:
    """최근 폼 + 🔴 **직전 경기 날짜 → 휴식일.**

    사용자 R1 이 이것이다 — *"라스베이거스 11일 휴식 vs 새크라멘토 … 4일 간격"*.
    🔴 휴식일은 **계산한다.** 기사에 적혀 있지 않아도 날짜가 있으면 나온다.
    """
    tf = _box(j).get("teamForm")
    if not isinstance(tf, list) or len(tf) < 2:
        return []
    out: list[Fact] = []
    for side, which in (("homeTeam", 0), ("awayTeam", 1)):
        team = str((_side(j, side) or {}).get("name") or "").strip()
        if not team:
            continue
        if q.team and not verify.mentions_team(team, q.team, q.local):
            continue
        games = [g for g in (tf[which] or []) if isinstance(g, dict)]
        if not games:
            continue
        dates = sorted([d for d in (_when_of(g) for g in games) if d])
        # 🔴 **휴식일은 날짜를 센다 — 시간을 빼지 않는다.**
        #
        #  ⚠️ 실측 2026-10-01: 시간 차로 재니 라스베이거스가 `10일` 이 나왔다.
        #     사용자는 `11일 휴식` 이라고 적었고 **사용자가 맞다** —
        #       직전 경기 2026-09-20 02:35 UTC = 현지 **09-19** 저녁
        #       킥오프   2026-10-01 02:00 UTC
        #     사람은 **날짜를 센다**(9/19 → 9/30 = 11일). 시간을 빼면 10.98일 →
        #     `.days` 가 10 으로 버린다.
        #  🔴 이 저장소가 같은 병으로 두 번 다쳤다(NHL 날짜 버킷·fdorg 경계 경기).
        #  ⚠️ 그래도 시간 차를 **버리지 않는다** — 둘을 이름으로 함께 싣는다.
        rest_days = rest_hours = None
        if when and dates:
            delta = when - dates[-1]
            rest_hours = round(delta.total_seconds() / 3600)
            rest_days = (when.date() - dates[-1].date()).days
        # 🔴 §5-c-1 ② 가 요구하는 **최근 평균 총득점**. 없으면 그 OR 가 못 걸린다
        #    (실측 2026-10-02: 이 칸이 비어 난타전 신호 하나가 통째로 죽어 있었다).
        #    ⚠️ 점수를 못 읽는 경기는 평균에서 **뺀다** — 0 으로 세면 평균이 내려간다.
        tots = []
        for g in games:
            m = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*$", str(g.get("score") or ""))
            if m:
                tots.append(int(m.group(1)) + int(m.group(2)))
        seq = _form_sequence(games, team, q)
        out.append(Fact(
            question_id=f"{q.id}:form", value={
                "team": team,
                "last5": [str(g.get("resultString") or "") for g in games],
                "recent_avg_goals": (round(sum(tots) / len(tots), 3)
                                     if tots else None),
                # 🔴 **팀이 넣은 골** 평균 — 난타전 판정이 쓰는 수다(결정
                #    2026-10-05). ⚠️ 위 칸은 **총득점**이라 이름이 다르다.
                "recent_scored_avg": scored_avg(seq),
                # 🔴🔴 **이상치를 뺀 보정 평균**(지시서 §3-2) — 한 경기 대승이
                #    평균을 끌어올린 것을 가른다. ⚠️ 사유를 **함께** 싣는다 —
                #    카드가 *"평균 3.6골(9-2 제외 시 1.75)"* 를 적어야 한다(#3).
                "recent_trimmed_avg": _trim_of(seq)[0],
                "trimmed_why": _trim_of(seq)[1],
                "recent_scored_games": len(tots),
                "last_match_utc": dates[-1].isoformat() if dates else None,
                # ⚠️ 이름을 그대로 — 조용한 0 금지. 못 재면 `None` 이다
                "rest_days": rest_days,
                "rest_hours": rest_hours,
                "matches": len(games),
                # 🔴🔴 **스코어 수열**(사용자 지적 2026-10-03) — 아래 주석 참조
                "sequence": seq,
                **_form_streaks(seq)},
            hardness="hard", source=url, publisher="fotmob",
            published_at=when, article_title=f"{team} 최근 폼",
            tier=verify.TIER_PREVIEW,
            extracted_by="rule:fotmob_form", step=1, team=team))
    return out


#: 🔴 **이상치로 보는 배수** — 지시서 §3-2: *"한 경기 득점이 나머지 평균의
#  **2배 이상**이면 그 경기를 뺀 평균을 함께 계산한다."*
OUTLIER_X = 2.0


def _trim_of(seq: list) -> tuple[float | None, str]:
    """🔴 폼 수열 → `(보정 평균, 사유)`. ⚠️ 못 재면 `(None, "")`(#3)."""
    got = [int(g["goals_for"]) for g in (seq or [])
           if isinstance(g, dict) and str(g.get("goals_for")).isdigit()]
    if not got:
        return None, ""
    avg, why = trimmed_avg(got)
    return avg, why


def trimmed_avg(goals: list) -> tuple[float, str]:
    """🔴🔴 **이상치를 뺀 평균** — 지시서 §3-2 (2026-10-05). `(평균, 사유)`.

    ⚠️ 실사고: 인도네시아 평균 **3.6골**이 `hard` 변수로 서서 득점형 시나리오에
       쏠렸다. 🔴 그 수는 **방글라데시전 9-2** 한 경기가 끌어올린 것이다 —
       보정하면 **1.75** 다. 그것이 "회귀"를 가리킨다.
    🔴 사유를 **글로** 돌려준다(#3) — 카드가 *"평균 3.6골(9-2 제외 시 1.75)"*
       처럼 적어야 독자가 그 수를 믿을지 판단할 수 있다.
    ⚠️ 표본이 2개 미만이면 **안 깎는다** — 깎을 나머지가 없다.
    """
    rows = [float(x) for x in (goals or [])
            if isinstance(x, (int, float))]
    if not rows:
        return 0.0, ""
    base = sum(rows) / len(rows)
    if len(rows) < 2:
        return round(base, 3), ""
    top = max(rows)
    rest = [x for x in rows if x != top] or rows
    # ⚠️ 같은 값이 여럿이면 **하나만** 뺀다
    if len(rest) == len(rows):
        rest = rows[:]
        rest.remove(top)
    rest_avg = (sum(rest) / len(rest)) if rest else base
    if rest_avg <= 0 or top < rest_avg * OUTLIER_X:
        return round(base, 3), ""
    return round(rest_avg, 3), (
        f"⚠️ **{top:g}골 경기 하나를 뺐다** — 나머지 평균({rest_avg:.2f})의 "
        f"{OUTLIER_X:g}배 이상이다. 원 평균 {base:.2f} → 보정 {rest_avg:.2f}")


def scored_avg(seq: list) -> float | None:
    """🔴🔴 **그 팀이 넣은 골의 평균** — 사용자 결정 2026-10-05 (난타전 지표).

    ⚠️ 종전엔 난타전 판정이 `recent_avg_goals`(**경기 총득점** = 홈골+원정골)를
       **두 팀 것 더해서** 썼다. 실측 프랑스–벨기에: `3.2 + 2.8 = 6.0 ≥ 4.0`
       → 총득점을 **두 번 센다.** 🔴 그러면 양 팀이 각각 평균 2골 경기만 해도
       합 4.0 이 되어 **거의 모든 축구 경기**가 난타전 필수가 됐다
       (축구 경기 평균 총득점은 보통 2.5~3.0).
    🔴 사용자 결정: *"팀 득점 평균으로 바꾼다(지시 원문대로)"* — 문턱 4.0·3.0 은
       그대로. 그러면 합 4골 = **경기에 4골 기대**라는 뜻이 선다.

    ⚠️ 새 자료는 필요 없다 — `_form_sequence` 가 `goals_for` 를 **이미** 든다.
    🔴 **못 재면 `None`**(#3) — 0 으로 때우면 난타전이 통째로 면제된다.
    """
    got = [int(g["goals_for"]) for g in (seq or [])
           if isinstance(g, dict) and str(g.get("goals_for")).isdigit()]
    return round(sum(got) / len(got), 3) if got else None


def _form_sequence(games: list, team: str, q: Question) -> list[dict]:
    """🔴🔴 최근 경기를 **스코어 수열**로. `W/D/L` 다섯 글자로는 못 세는 것이 있다.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 필요한가 — 사용자 분석 2026-10-03
    ══════════════════════════════════════════════════════════════════

    > 파라과이 **원정 8경기 연속 득점**

    `last5 = ['W','D','D','L','W']` 로는 **장소도 득점도** 알 수 없다. 그런데
    fotmob `teamForm` 항목이 그것을 **이미 들고 있었다**(실측 2026-10-03):

    ```
    {"resultString": "L", "score": "2 - 0", "home": {...}, "away": {...},
     "tooltipText": {"homeTeam": "Cameroon", "homeScore": "2",
                     "awayTeam": "China",    "awayScore": "0"}}
    ```

    🔴 그래서 새 소스가 필요 없다 — **버리고 있던 칸**이다.
    ⚠️ 못 읽는 경기는 **넣지 않는다**(0 으로 때우면 연속 계산이 거짓이 된다).
    """
    out: list[dict] = []
    for g in games:
        tip = g.get("tooltipText") or {}
        hs, as_ = tip.get("homeScore"), tip.get("awayScore")
        hn = str(tip.get("homeTeam") or "").strip()
        an = str(tip.get("awayTeam") or "").strip()
        if not (str(hs).isdigit() and str(as_).isdigit() and hn and an):
            continue
        # 🔴 **우리가 홈인가** — 이름으로 가린다(`verify` 가 원본이다)
        mine_home = verify.mentions_team(hn, team, q.local)
        mine_away = verify.mentions_team(an, team, q.local)
        if mine_home == mine_away:
            continue          # 둘 다거나 둘 다 아니면 귀속을 못 한다
        side = "home" if mine_home else "away"
        gf = int(hs) if mine_home else int(as_)
        ga = int(as_) if mine_home else int(hs)
        when_ = _when_of(g)
        out.append({"date": when_.date().isoformat() if when_ else None,
                    "side": side, "opponent": an if mine_home else hn,
                    "goals_for": gf, "goals_against": ga,
                    "result": "W" if gf > ga else ("D" if gf == ga else "L"),
                    "score": f"{gf}-{ga}"})
    # 🔴 **최신이 앞**이다 — 연속 계산이 그 순서를 쓴다
    out.sort(key=lambda r: r["date"] or "", reverse=True)
    return out


def _streak(rows: list[dict], ok) -> int:
    """🔴 **최신부터 끊길 때까지** 센다. 수열이 비면 0."""
    n = 0
    for r in rows:
        if not ok(r):
            break
        n += 1
    return n


def _form_streaks(seq: list[dict]) -> dict:
    """🔴 수열에서 **연속 패턴**을 센다(사용자 R8: *"원정 8경기 연속 득점"*).

    ⚠️ 수열이 비면 **전부 `None`** — 0 으로 적으면 *"연속 0경기"* 와
       *"못 쟀다"* 가 구분되지 않는다(#3 조용한 0 금지).
    """
    if not seq:
        return {"streak_scored": None, "streak_away_scored": None,
                "streak_unbeaten": None, "streak_winless": None,
                "streak_clean_sheet": None, "away_games": None}
    away = [r for r in seq if r["side"] == "away"]
    return {
        "streak_scored": _streak(seq, lambda r: r["goals_for"] > 0),
        # 🔴 **원정만** 이어서 센다 — 사용자가 쓴 패턴이 그것이다
        "streak_away_scored": _streak(away, lambda r: r["goals_for"] > 0),
        "streak_unbeaten": _streak(seq, lambda r: r["result"] != "L"),
        "streak_winless": _streak(seq, lambda r: r["result"] != "W"),
        "streak_clean_sheet": _streak(seq, lambda r: r["goals_against"] == 0),
        "away_games": len(away)}


#: 🔴 전반이 끝나는 분. ⚠️ 추가시간 골은 `time` 이 45 이고 `overloadTime` 이 붙는다 —
#   그래서 `<= 45` 가 전반 전체를 덮는다(실측 2026-10-03).
FIRST_HALF_MIN = 45








def parse_stats(j: dict, q: Question, *, url: str, when) -> list[Fact]:
    """경기 통계 — 점유율·유효슛. 사용자 R7·R8 의 재료다.

    🔴 **경기 전에는 비어 있다.** 그때는 사실을 만들지 않는다 — 0 으로 채우면 거짓이다.
    """
    per = ((_page(j).get("content") or {}).get("stats") or {}).get("Periods") or {}
    blk = per.get("All") or next(iter(per.values()), {})
    flat: dict[str, object] = {}
    for grp in (blk.get("stats") or []):
        for s in (grp.get("stats") or []):
            title, vals = s.get("title"), s.get("stats")
            if title and isinstance(vals, list) and any(v is not None for v in vals):
                flat[str(title)] = vals
    if not flat:
        return []
    home = str((_side(j, "homeTeam") or {}).get("name") or "")
    away = str((_side(j, "awayTeam") or {}).get("name") or "")
    return [Fact(question_id=f"{q.id}:stats",
                 value={"home": home, "away": away, "stats": flat},
                 hardness="hard", source=url, publisher="fotmob",
                 published_at=when, article_title="경기 통계",
                 tier=verify.TIER_PREVIEW,
                 extracted_by="rule:fotmob_stats", step=1, team=q.team)]


def parse_info(j: dict, q: Question, *, url: str, when) -> list[Fact]:
    """구장·심판·대회·관중 + 날씨. §4 `venue_weather` 의 재료다."""
    box = _box(j).get("infoBox") or {}
    w = (_page(j).get("content") or {}).get("weather") or {}
    val = {k: box.get(k) for k in ("Tournament", "Stadium", "Referee",
                                   "Attendance") if box.get(k)}
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **중립 구장을 잰다** (사용자 지적 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 콜롬비아 vs 파라과이 (**미국 해리슨** SI스타디움) … **중립 구장이다**
    #
    #  종전에는 중립 여부를 `config/league_rules.yaml` **선언**으로만 알았다
    #  (아시안게임에만 적혀 있었다). 친선 경기는 선언이 없으니 봇이 **콜롬비아를
    #  홈으로** 읽었다 — `home_field` 가 거짓 변수를 만들 수 있는 자리다.
    #
    #  🔴 페이로드가 이미 답을 들고 있었다(실측 2026-10-03):
    #      `countryCode: "INT"`          → 대표팀 경기다
    #      `infoBox.Stadium.country`     → 구장이 있는 나라
    #      `general.homeTeam.name`       → 대표팀은 **이름이 곧 나라**다
    #    `INT` 이고 구장 나라가 홈팀 이름과 안 맞으면 **중립**이다.
    #  ⚠️ `INT` 가 아니면(클럽 경기) **판정하지 않는다** — 리버풀과 England 는
    #     이름이 안 맞지만 그것이 중립을 뜻하지 않는다.
    gen = _page(j).get("general") or {}
    stad = box.get("Stadium") if isinstance(box.get("Stadium"), dict) else {}
    vc = str((stad or {}).get("country") or "").strip()
    home_name = str(((gen.get("homeTeam") or {}).get("name") or "")).strip()
    if str(gen.get("countryCode") or "").upper() == "INT" and vc and home_name:
        same = verify.mentions_team(vc, home_name, None) or \
            verify.mentions_team(home_name, vc, None)
        val["venue_country"] = vc
        val["neutral_venue"] = not same
        val["neutral_why"] = (
            f"대표팀 경기(countryCode INT)인데 구장이 `{vc}` 다 — 홈팀 "
            f"`{home_name}` 의 나라가 아니다" if not same else
            f"구장 `{vc}` 가 홈팀 `{home_name}` 의 나라다")
    if w:
        val["weather"] = {k: w.get(k) for k in
                          ("temperature", "windSpeed", "precipitation",
                           "description") if w.get(k) is not None}
    if not val:
        return []
    return [Fact(question_id=f"{q.id}:info", value=val, hardness="hard",
                 source=url, publisher="fotmob", published_at=when,
                 article_title="경기 정보", tier=verify.TIER_PREVIEW,
                 extracted_by="rule:fotmob_info", step=1, team=q.team)]


def team_names(j: dict) -> list[str]:
    """🔴 그 경기 페이지의 **두 팀 이름**(홈, 원정). 못 읽으면 빈 목록.

    ⚠️ `_not_our_match` 가 쓰던 자리를 **그대로** 꺼낸 것이다 — 두 곳에서 칸을
       파헤치면 한쪽이 바뀔 때 다른 쪽이 조용히 틀린다(사본 금지).
    🔴 부르는 곳: `findgame` 이 **자동완성이 집은 경기**를 그 페이지의 이름으로
       다시 확인할 때 쓴다(사용자가 쓴 말과 페이지의 말이 다를 수 있다 —
       실측 2026-10-03: `크로아티아` vs `Croatia`).
    """
    g = _page(j).get("general") or {}
    out = [str(((g.get(k) or {}).get("name") or "")).strip()
           for k in ("homeTeam", "awayTeam")]
    return [n for n in out if n]


def _not_our_match(j: dict, q: Question) -> str:
    """🔴 이 경기 페이지가 **우리 두 팀**의 것이 아니면 사유를 돌려준다.

    빈 문자열이면 우리 경기다. ⚠️ 상대를 모르면 **우리 팀만** 확인하고, 검사가 약한
    것을 사유로 알린다(조용히 통과시키지 않는다).
    """
    names = team_names(j)
    if len(names) < 2:
        return "경기 페이지가 두 팀 이름을 안 준다"
    mine = (q.team or "").strip()
    if mine and not any(verify.mentions_team(n, mine, q.local) for n in names):
        return f"우리 팀({mine})이 이 경기에 없다 — {names}"
    # 🔴🔴 **남녀·연령 표식이 다르면 다른 팀이다**(라이브 2026-10-02).
    #    `South Korea` 와 `South Korea W` 는 글자가 겹쳐 `mentions_team` 을 통과한다.
    #    그래서 **표식**으로 한 번 더 가른다 — 안 가르면 남자 자료가 여자 경기에 붙는다.
    if mine and not any(verify.same_squad_kind(n, mine) for n in names
                        if verify.mentions_team(n, mine, q.local)):
        return (f"남녀·연령 표식이 다르다 — 물은 팀 {mine}"
                f"{sorted(verify.squad_marks(mine))} vs 페이지 {names}")
    other = (q.opponent or "").strip()
    if not other:
        # 🔴 상대를 모르면 **막지 못한다** — 그 사실을 남긴다
        logger.info("[fotmob] §13-c ② 약한 검사 — 상대를 몰라 우리 팀만 봤다 %s",
                    names)
        return ""
    if not any(verify.mentions_team(n, other, q.opponent_local) for n in names):
        return f"상대({other})가 이 경기에 없다 — {names}"
    return ""


def parse_lineup(j: dict, q: Question, *, url: str, when) -> list[Fact]:
    """🔴🔴 **같은 페이지의 라인업 블록**(축구 완성 지시서 §2) — XI·결장·감독.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 이 함수가 생겼나 — 실측 2026-10-06
    ══════════════════════════════════════════════════════════════════

    s2 가 부르는 것은 `parse_context` 다(`sources_context` 가 그것을 가리킨다).
    ⚠️ 그런데 그 함수는 **맞대결·폼·통계·정보·선수**만 읽고 **라인업 블록을 건너뛰었다**
       — `parse_match` 가 그 일을 하지만 **아무도 부르지 않았다**(CLAUDE.md #2 배선).
    🔴 그래서 한국–우즈베키스탄 카드가 *"XI 0팀"* 이었고 **결장 명단이 통째로 없었다**
       (그 페이지 JSON 에 `unavailable` 이 들어 있었는데도).

    🔴 **두 팀을 다 낸다** — s2 가 `team` 으로 열쇠를 가린다(`parse_match` 는 세포용이라
       질문한 팀만 냈다). ⚠️ 귀속은 `Fact.team` 에 적힌 이름으로 한다.
    """
    out: list[Fact] = []
    state = lineup_kind_of(j)
    for which in ("homeTeam", "awayTeam"):
        side = _side(j, which)
        name = str(side.get("name") or "").strip()
        if not name:
            continue
        names = _names(side)
        gone = missing_of(side)
        coach_name = _coach(side)
        if not (names or gone or coach_name):
            continue
        out.append(Fact(
            question_id=f"{q.id}:lineup",
            value={"team": name, "formation": side.get("formation"),
                   "players": names, "lineup": players_of(side),
                   "missing": gone, "coach": coach_name,
                   "lineup_state": state,
                   "squad": squad_names(side),
                   "subs": len(side.get("subs") or [])},
            # 🔴 확정이면 `hard` — 예상은 바뀔 수 있다(방아쇠가 그것을 본다)
            hardness=("hard" if state == "confirmed" else "soft"),
            source=url, publisher="fotmob", published_at=when,
            article_title=f"{name} XI ({state})",
            tier=verify.TIER_PREVIEW,
            extracted_by="rule:fotmob_lineup", step=1, team=name))
    return out


def parse_context(got, q: Question, *, day=None) -> list[Fact]:
    """🔴 **한 번 열고 다 읽는다.** 열기 예산은 이미 썼으므로 읽는 것은 공짜다."""
    url = getattr(got, "url", "") or ""
    if not is_match_page(url):
        return []
    j = payload(getattr(got, "text", "") or "")
    if j is None:
        return []
    when = kickoff(j)
    want = day or (q.deadline.astimezone(KST).date() if q.deadline else None)
    if when is None or (want is not None
                        and q.deadline
                        and not window.same_match_time(when, q.deadline)):
        return []                       # 🔴 §13-c ① — 다른 날 경기다
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 §13-c ② — **이 페이지가 우리 두 팀의 경기인가** (라이브 2026-10-02)
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 날짜만 봤다. 그래서 **같은 날 같은 이름의 다른 경기**가 통째로 들어왔다:
    #
    #    실측: 아시안게임 **여자** 한국 vs 중국을 물었는데 검색이 **남자** 대표팀
    #    (손흥민·김민재) vs **우루과이** 페이지를 열었고, 날짜가 같아서 통과했다.
    #    → 기준 XI·선수 기록이 **남의 경기**에서 들어왔다.
    #
    #  🔴 **0건보다 나쁘다.** 0건은 "자료 부족"으로 멈추지만, 틀린 자료는 카드를
    #     만들어 버린다 — §17-g-3 · M14 가 막으려는 바로 그 사고다.
    #  🔴 상대를 모르면 **우리 팀만** 보고, 그 사실(검사가 약하다)을 로그에 남긴다.
    bad = _not_our_match(j, q)
    if bad:
        logger.info("[fotmob] §13-c ② 거부 — %s (%s)", bad, url)
        return []
    out: list[Fact] = []
    for fn in (parse_h2h, parse_form, parse_stats, parse_info, parse_lineup,
               lambda jj, qq, *, url, when: parse_players(jj, qq, url=url,
                                                          when=when)):
        try:
            out += fn(j, q, url=url, when=when)
        except Exception as exc:                            # noqa: BLE001
            logger.warning("[fotmob] %s 실패: %s", fn.__name__, exc)
    if out:
        logger.info("[fotmob] 맥락 %d건 · %s", len(out),
                    [f.question_id.rsplit(":", 1)[-1] for f in out])
    return out


# ══════════════════════════════════════════════════════════════════
# 🔴 §19-c — **직전 경기를 따라가 기준 XI 를 얻는다**
# ══════════════════════════════════════════════════════════════════
#
# 사용자가 손으로 한 일이 이것이다:
#
#   > 확정 XI는 아직 색인에 안 잡힌다 … 잡힌 건 양 팀 **"직전 경기 선발 XI"** 라
#   > 그걸 **기준 XI** 로 놓고 재작성한다
#
# 경기 페이지가 그 링크를 **이미 들고 있다** — `matchFacts.teamForm[].linkToMatch`.
# 🔴 실측 2026-10-01: 새크라멘토의 직전 경기가 `09-27 01:00 UTC` = 현지 09-26
#    **토요일** 저녁 — 사용자가 쓴 *"토요 3-2 승"* 과 같은 경기다.
#
# ⚠️ 파서는 동기 함수라 네트워크에 못 간다. 그래서 **가리키기(`follow`)와
#    열기(세포)를 가른다** — `cells.Source.follow` / `Cell._follow`.

BASE = "https://www.fotmob.com"


def prev_match_urls(j: dict, q: Question) -> list[str]:
    """질문한 팀의 **직전 경기** 주소. 🔴 한 팀에 하나다(가장 최근 것).

    ⚠️ 상대 팀 것도 함께 내지 않는다 — 세포는 **한 팀을 묻고** 있고, 상대 팀 기준
       XI 는 상대 팀 세포가 가져온다(§19-a: 세포 하나 = 질문 하나).
    """
    box = _box(j)
    tf = box.get("teamForm")
    if not isinstance(tf, list) or len(tf) < 2:
        return []
    out: list[str] = []
    for side, which in (("homeTeam", 0), ("awayTeam", 1)):
        team = str((_side(j, side) or {}).get("name") or "").strip()
        if not team:
            continue
        if q.team and not verify.mentions_team(team, q.team, q.local):
            continue
        games = [g for g in (tf[which] or []) if isinstance(g, dict)]
        dated = sorted(((_when_of(g), g) for g in games),
                       key=lambda x: (x[0] is not None, x[0]))
        for when, g in reversed(dated):
            link = str(g.get("linkToMatch") or "").strip()
            if when is None or not link:
                continue
            # 🔴 `#5109918` 같은 앵커를 뗀다 — 같은 페이지다
            out.append(BASE + link.split("#")[0])
            break
    return out


def follow_prev(got, q: Question) -> list[str]:
    """`Source.follow` 가 부르는 문. 🔴 경기 페이지가 아니면 아무것도 안 낸다."""
    if not is_match_page(getattr(got, "url", "") or ""):
        return []
    j = payload(getattr(got, "text", "") or "")
    return prev_match_urls(j, q) if j else []


def parse_prev(got, q: Question) -> list[Fact]:
    """직전 경기 페이지 → **기준 XI**(결정 C).

    🔴 **확정 XI 가 아니다.** 다른 경기의 선발이고, 그래서 `lineup_kind:
       "baseline"` 과 `hardness: "soft"` 로 싣는다. 카드가 그대로 적는다.
       ⚠️ 이것을 확정으로 적으면 거짓이다 — 사용자 글 첫 문장이 그 구분이다.
    🔴 **날짜 검사를 하지 않는다.** 일부러다 — 이 페이지는 *다른 날* 경기이고,
       그것이 기준 XI 의 정의다. 대신 **어느 경기에서 왔는지** 싣는다.
    """
    url = getattr(got, "url", "") or ""
    if not is_match_page(url):
        return []
    j = payload(getattr(got, "text", "") or "")
    if j is None:
        return []
    when = kickoff(j)
    team = (q.team or "").strip()
    out: list[Fact] = []
    for which in ("homeTeam", "awayTeam"):
        side = _side(j, which)
        name = str(side.get("name") or "").strip()
        if not name:
            continue
        if team and not verify.mentions_team(name, team, q.local):
            continue
        names = _names(side)
        if len(names) != XI:
            logger.info("[fotmob] 기준 XI 거부 — %s 선발 %d명", name, len(names))
            continue
        g = _page(j).get("general") or {}
        out.append(Fact(
            question_id=f"{q.id}:baseline", value={
                "team": name, "formation": side.get("formation"),
                "players": names, "coach": _coach(side),
                "lineup_kind": "baseline",
                # 🔴 **그 경기의 스쿼드 전원** — 명단 대조의 재료다
                "squad": squad_names(side),
                # 🔴 **기준 라인업의 시장가치 합** — 오늘과 비교할 분모다
                **dict(zip(("value_sum", "value_players"),
                           value_sum(side), strict=True)),
                # 🔴 **어느 경기의 XI 인지** 적는다 — 없으면 카드가 거짓이 된다
                "from_match": f"{g.get('homeTeam', {}).get('name')} vs "
                              f"{g.get('awayTeam', {}).get('name')}",
                "from_date": when.date().isoformat() if when else None},
            # 🔴 다른 경기의 선발이다 — **soft** 이고, 기사 검증기의 대상이 아니다
            #    (§12-c-1 신선도 검사가 *"4일 지난 기사"* 로 떨어뜨렸다)
            hardness="soft", from_past_match=True,
            source=url, publisher="fotmob",
            published_at=when, article_title=f"{name} 기준 XI (직전 경기)",
            tier=verify.TIER_PREVIEW,
            extracted_by="rule:fotmob_baseline", step=1, team=name))
    # 🔴 **같은 페이지의 통계도 읽는다** — 사용자 R7·R8 이 직전 경기 통계다.
    #    *"하트퍼드전도 점유 지배"* · *"하트퍼드전 상대 유효슛 2개"*
    #    실측 2026-10-01: 그 페이지가 점유 69-31, 유효슛 5-2 를 준다 — 둘 다 일치.
    out += _past_stats(j, q, url=url, when=when)
    # 🔴 **선수 기록도 같은 페이지에 있다** — R3(*"2골 1도움"*)·R6(*"교체 득점"*)
    out += parse_players(j, q, url=url, when=when, past=True)
    if out:
        logger.info("[fotmob] 기준 XI·과거 통계·선수 %d건 ← %s", len(out), url[-56:])
    return out


#: 🔴 뽑는 통계와 그 이름. 원본은 fotmob 의 `title` 이고 여기 **우리 이름**을 맞춘다.
#   ⚠️ `[홈, 원정]` 두 칸으로 온다 — 어느 쪽이 우리 팀인지 가려 숫자를 돌린다.
_STAT_KEYS = {
    "Ball possession": "possession",
    "Total shots": "shots",
    "Shots on target": "shots_on_target",
    "Corners": "corners",
    "Big chances": "big_chances",
}


def _past_stats(j: dict, q: Question, *, url: str, when) -> list[Fact]:
    """직전 경기의 **팀별 숫자**. 🔴 `[홈, 원정]` 을 우리 팀 기준으로 돌린다.

    ⚠️ 단계 5·6 은 *"점유 우위"*·*"유효슛 2"* 같은 **숫자**로 변수를 만든다 —
       `[69, 31]` 배열을 그대로 두면 어느 쪽이 우리인지 매번 다시 풀어야 한다.
    🔴 **상대가 기록한 값도 이름으로** 싣는다(`*_conceded`) — 사용자 R8 이
       *"상대 유효슛 2개"* 이고, 그것은 우리 팀 칸이 아니다.
    """
    per = ((_page(j).get("content") or {}).get("stats") or {}).get("Periods") or {}
    blk = per.get("All") or next(iter(per.values()), {})
    flat: dict[str, list] = {}
    for grp in (blk.get("stats") or []):
        for st in (grp.get("stats") or []):
            name = _STAT_KEYS.get(str(st.get("title") or ""))
            vals = st.get("stats")
            if name and isinstance(vals, list) and len(vals) == 2 \
                    and all(isinstance(v, (int, float)) for v in vals):
                flat[name] = list(vals)
    if not flat:
        return []
    g = _page(j).get("general") or {}
    home = str((_side(j, "homeTeam") or {}).get("name") or "")
    away = str((_side(j, "awayTeam") or {}).get("name") or "")
    out: list[Fact] = []
    for name, idx, opp in ((home, 0, away), (away, 1, home)):
        if not name:
            continue
        if q.team and not verify.mentions_team(name, q.team, q.local):
            continue
        val = {"team": name, "opponent": opp,
               "from_match": f"{home} vs {away}",
               "from_date": when.date().isoformat() if when else None}
        for k, pair in flat.items():
            val[k] = pair[idx]
            val[f"{k}_conceded"] = pair[1 - idx]
        out.append(Fact(
            question_id=f"{q.id}:past_stats", value=val,
            # 🔴 다른 경기의 기록이다 — soft · 기사 검증기 대상 아님
            hardness="soft", from_past_match=True,
            source=url, publisher="fotmob", published_at=when,
            article_title=f"{name} 직전 경기 통계", tier=verify.TIER_PREVIEW,
            extracted_by="rule:fotmob_past_stats", step=1, team=name))
    return out


# ══════════════════════════════════════════════════════════════════
# 🔴 리그 순위표 — **콘퍼런스가 여럿일 수 있다**
# ══════════════════════════════════════════════════════════════════
#
# 측정 2026-10-01: R2(*"새크라멘토 4위, 라스베이거스 11위"*)가 도달은 됐으나
# 변환이 0 이었다. 순위표는 경기 페이지에 **없다** — `leagueId` 만 있다.
#
# ⚠️ **두 길이 있고 하나만 쓸 수 있다**:
#   · `data.fotmob.com/tables.ext.8972.fot.gz` — 🔴 robots.txt 가 **AccessDenied** 다.
#     허가를 확인할 수 없는 자리는 쓰지 않는다(`site.api.espn.com` 과 같은 판정).
#   · `www.fotmob.com/leagues/{id}/table/{slug}` — robots `*` 가 허용한다. **이쪽.**
#
# 🔴 **USL 은 콘퍼런스가 둘이다**(동부 13팀·서부 12팀). 표를 하나로 가정하면
#    순위가 틀린다 — 실측에서 새크라멘토는 **서부 2위**였다.
#    ⚠️ 몇 개인지 세지 않는다. 응답이 주는 표를 **전부** 훑어 우리 팀을 찾는다.


def league_table_url(j: dict) -> str | None:
    """경기 페이지의 `content.table` 로 **리그 표 주소**를 만든다.

    🔴 `url` 칸은 `data.fotmob.com` 을 가리킨다 — 그 자리는 robots 를 못 읽어
       쓰지 않는다. `leagueId` 와 대회 이름으로 **www 주소**를 만든다.
    """
    tb = ((_page(j).get("content") or {}).get("table") or {})
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **부모 리그가 먼저다** — 실측 2026-10-05 (프랑스–벨기에)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고: `leagueId` 를 먼저 써서
    #     `/leagues/920741/table/uefa-nations-league-a-grp-1` → **404**.
    #     그 결과 포아송 격자가 전멸하고 생존 수가 확률이 아니라 **strength
    #     개수**로만 섰다(*"확률 격자를 못 만들었다 ×2"*).
    #  🔴 받아서 확인했다(2026-10-05): `920741`(조별 하위) 404 ·
    #     `9806`(`parentLeagueId` = 대회) **200 이고 두 팀 이름이 있다.**
    #  ⚠️ 부모가 **없는** 리그(프리미어리그 등)는 `leagueId` 가 곧 대회다 —
    #     그때는 그것으로 간다.
    lid = str(tb.get("parentLeagueId") or tb.get("leagueId") or "").strip()
    name = str(tb.get("tournamentNameForUrl") or "").strip()
    if not lid or not name:
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{BASE}/leagues/{lid}/table/{slug}"


def is_table_page(url: str) -> bool:
    return "fotmob.com" in (url or "") and "/table/" in (url or "")


def _tables(j: dict) -> list[dict]:
    """응답의 표들. 🔴 **몇 개인지 가정하지 않는다** — 콘퍼런스가 여럿일 수 있다."""
    out = []
    for blk in ((_page(j).get("table") or []) or []):
        for tb in (((blk.get("data") or {}).get("tables")) or []):
            if isinstance(tb, dict) and isinstance(tb.get("table"), dict):
                out.append(tb)
    return out


def _scores(s) -> tuple[int | None, int | None]:
    """`"36-24"` → `(36, 24)`. 🔴 못 읽으면 `(None, None)` — 0 으로 때우지 않는다."""
    m = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*$", str(s or ""))
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def _row_of(r: dict) -> dict:
    """순위표 한 줄 → `league.TABLE_FIELDS` 공통 꼴."""
    gf, ga = _scores(r.get("scoresStr"))
    return {"team": r.get("name"), "played": r.get("played"),
            "wins": r.get("wins"), "draws": r.get("draws"),
            "losses": r.get("losses"), "points": r.get("pts"),
            "goals_for": gf if gf is not None else r.get("goalsScored"),
            "goals_against": ga, "goal_diff": r.get("goalConDiff")}


def _derived(j: dict) -> dict:
    """§5-c-1 문턱 · §6-c-3 기준선 · §4 `home_field` 의 재료.

    🔴 **대회 전체의 모든 표를 합쳐** 센다(`league_avg_scope: 대회 전체`).
       콘퍼런스·조로 쪼개면 같은 리그 두 경기가 다른 문턱을 받는다.
    """
    allr: list[dict] = []
    homes: list[dict] = []
    aways: list[dict] = []
    for tb in _tables(j):
        inner = tb.get("table") or {}
        allr += [_row_of(r) for r in (inner.get("all") or [])]
        homes += [_row_of(r) for r in (inner.get("home") or [])]
        aways += [_row_of(r) for r in (inner.get("away") or [])]
    return {
        "league_avg_goals": league.avg_goals(allr),
        "total_baseline": league.baseline_total(allr),
        "open_game_threshold": league.open_game_threshold(allr),
        "home_advantage": league.home_advantage(homes, aways),
        # 🔴 §5-c-1 ① **포아송 모형의 기준값**(사용자 지시 2026-10-02 2차).
        #    장소를 섞으면 안 된다 — 실측 USL 홈 1.526 · 원정 1.206.
        "venue_averages": league.venue_averages(homes, aways),
        # 🔴 **두 팀의 홈/원정 줄을 찾으려면 표가 필요하다.** 파서는 우리 팀만
        #    알고 상대는 모를 수 있으므로 줄을 싣고 고르는 것은 호출부에 맡긴다.
        #    ⚠️ 필요한 칸만 싣는다 — 표 전체를 사실 값에 넣지 않는다.
        "venue_rows": {
            "home": [{"team": r["team"], "played": r["played"],
                      "goals_for": r["goals_for"],
                      "goals_against": r["goals_against"]} for r in homes],
            "away": [{"team": r["team"], "played": r["played"],
                      "goals_for": r["goals_for"],
                      "goals_against": r["goals_against"]} for r in aways],
        } if homes and aways else None,
        # 🔴 **몇 표에서 셌나** — 쪼개진 리그인지 보이게 남긴다(조용한 0 금지)
        "league_tables": len(_tables(j)),
    }


def cut_lines(tb: dict) -> dict:
    """§4 `stakes` 가 요구하는 **경계 순위**(플레이오프·강등).

    🔴 fotmob 이 `legend` 로 준다 — `[{title, indices}]` 의 `indices` 는 **0부터**인
       순위 자리다. `max+1` 이 그 구간의 마지막 순위다.
       실측 2026-10-02: MLS 는 `Championship playoff · indices [0..8]` → 경계 **9위**.
    ⚠️ **없는 리그가 있다.** USL 은 `legend: null` 이다 — 그때는 경계를 **모른다**.
       순위만으로 "걸렸다"고 판단하지 않는다(리그마다 진출 수가 다르다).
    """
    out: dict[str, int] = {}
    for lg in (tb.get("legend") or []):
        if not isinstance(lg, dict):
            continue
        idx = [int(i) for i in (lg.get("indices") or []) if i is not None]
        title = str(lg.get("title") or lg.get("tKey") or "").strip()
        if idx and title:
            out[title] = max(idx) + 1
    return out


def table_as_of(j: dict) -> datetime | None:
    """🔴 **순위표가 "언제"의 표인가** — 표가 스스로 말해 준다.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **이 함수가 없어서 게이트에 구멍이 있었다** (사용자 지시 2026-10-02)
    ══════════════════════════════════════════════════════════════════

    `parse_league_table` 의 독스트링은 *"순위표는 '지금' 이다 … 그래서 `as_of` 를
    싣는다"* 고 **적어 놓고 싣지 않았다.** 그 결과:

      · 순위표 사실의 `published_at` 이 `None` 이었다 → 날짜 없는 자료 예외로 들어갔다
      · 🔴 그러면 **§12-c-2(경기 후 기사 배제)가 순위표에 영영 닿지 않는다**
      · 실측 2026-10-02: 경기(3-2 승) **뒤**의 표를 경기 **전** 사실로 쓰고 있었다 —
        순위가 2위로 들어왔고 경기 전에는 4위였다

    🔴 **표는 자기 시점을 들고 있다.** 행마다 `ongoing` 이 있고, 끝난 경기
       (`status == "S"`)는 종료 시각(`shs`)을 적어 둔다. 그중 **가장 늦은 시각**이
       *"이 표는 최소한 그때까지의 결과를 담았다"* 는 뜻이다 — 그것이 `as_of` 다.
    ⚠️ 못 읽으면 `None` — 지어내지 않는다. 그때는 전처럼 날짜 없는 자료로 남는다.
    """
    best: datetime | None = None
    for tb in _tables(j or {}):
        inner = tb.get("table") or {}
        for key in ("all", "home", "away"):
            for r in (inner.get(key) or []):
                og = (r or {}).get("ongoing") or {}
                # 🔴 끝난 경기만 센다 — 진행 중인 경기는 아직 표에 안 들어갔다
                if str(og.get("status") or "") != "S":
                    continue
                for field in ("shs", "gs", "time"):
                    when = _dmy(og.get(field))
                    if when and (best is None or when > best):
                        best = when
                    if when:
                        break
    return best


def _dmy(text) -> datetime | None:
    """`"01.10.2026 05:13:35"` → UTC datetime. 🔴 못 읽으면 `None`.

    ⚠️ fotmob 의 `ongoing` 시각은 **UTC** 다(경기 페이지의 `utcTime` 과 같은 축).
    """
    one = str(text or "").strip()
    if not one:
        return None
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(one, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_league_table(got, q: Question) -> list[Fact]:
    """리그 표 → **우리 팀 순위**. 🔴 홈/원정 쪼갠 표도 함께 싣는다.

    ⚠️ 사용자 R4 가 *"원정 13경기 중 12경기 득점"* 이다 — 원정 표가 그 재료다.
    🔴 **순위표는 "지금" 이다.** 경기가 끝나면 숫자가 바뀐다 — 그래서 `as_of` 를
       싣는다. 측정이 *"못 찾았다"* 와 *"시점이 다르다"* 를 가를 수 있어야 한다.
    """
    url = getattr(got, "url", "") or ""
    if not is_table_page(url):
        return []
    j = payload(getattr(got, "text", "") or "")
    if j is None:
        return []
    team = (q.team or "").strip()
    as_of = table_as_of(j)
    out: list[Fact] = []
    for tb in _tables(j):
        inner = tb.get("table") or {}
        rows = inner.get("all") or []
        mine = next((r for r in rows if isinstance(r, dict)
                     and verify.mentions_team(str(r.get("name") or ""),
                                              team, q.local)), None) if team else None
        if mine is None:
            continue
        gf, ga = _scores(mine.get("scoresStr"))
        val = {
            "team": str(mine.get("name") or ""),
            # 🔴 **어느 표인가** — 콘퍼런스 이름이 없으면 순위가 무슨 뜻인지 모른다
            "table": str(tb.get("leagueName") or "") or None,
            "rank": mine.get("idx"), "played": mine.get("played"),
            "wins": mine.get("wins"), "draws": mine.get("draws"),
            "losses": mine.get("losses"), "points": mine.get("pts"),
            "goals_for": gf, "goals_against": ga,
            "goal_diff": mine.get("goalConDiff"), "scores": mine.get("scoresStr"),
        }
        # 🔴 **규칙이 요구하는 파생 측정**(사용자 지시 2026-10-02 로 바뀐 네 규칙).
        #
        #  ⚠️ **대회 전체로 센다** — yaml 의 `league_avg_scope: 대회 전체` 다.
        #     처음 판은 우리 팀이 든 **표 하나**(콘퍼런스)로 셌고, 그것은 선언과
        #     어긋났다. 그러면 같은 리그 두 경기가 다른 문턱을 받는다.
        #     실측 2026-10-02: USL 동부 2.71 · 서부 2.76 · 전체 2.73.
        #  🔴 못 구하면 칸이 **`None`** 이다 → 호출부가 그 규칙을 발동하지 않는다.
        val.update(_derived(j))
        # 🔴 §4 `stakes` 의 재료 — **경계 순위.** 없으면 칸이 비고, 그러면
        #    `classify._dir_stakes` 가 *"경계를 모른다"* 로 미결정을 낸다.
        cuts = cut_lines(tb)
        val["cut_lines"] = cuts or None
        # ⚠️ 어느 경계를 쓸지는 하나뿐일 때만 자동이다 — 여럿이면 고르지 않는다
        val["playoff_cut"] = (next(iter(cuts.values())) if len(cuts) == 1
                              else None)
        for split in ("home", "away"):
            r = next((x for x in (inner.get(split) or [])
                      if isinstance(x, dict)
                      and verify.mentions_team(str(x.get("name") or ""),
                                               team, q.local)), None)
            if r:
                # 🔴 **실점을 싣는다** — 전 판에 없었고, 그래서 §5-c-1 ① 의
                #    수비비를 계산할 수 없었다(사용자 지시 2026-10-02 2차).
                sf, sa = _scores(r.get("scoresStr"))
                val[split] = {"rank": r.get("idx"), "played": r.get("played"),
                              "wins": r.get("wins"), "draws": r.get("draws"),
                              "losses": r.get("losses"),
                              "goals": r.get("goalsScored"),
                              "goals_for": sf, "goals_against": sa,
                              "scores": r.get("scoresStr")}
        val["as_of"] = as_of.isoformat() if as_of else None
        out.append(Fact(
            question_id=f"{q.id}:standings", value=val,
            # 🔴 순위표는 **과거 경기 기록이 아니다** — "지금"의 표이고, 다만
            #    **발행 시각이 없다.** 그것은 §12-c-1 의 `dateless` 자리이고
            #    `Source.dateless_ok` 가 soft 로 남긴다.
            #    ⚠️ 실측 2026-10-01: 처음에 `from_past_match=True` 로 적었더니
            #       그 예외의 조건(`from_match` 필수)을 못 채워 **거부됐다** —
            #       가드가 옳게 물었고 분류가 틀렸던 것이다.
            hardness="soft",
            source=url, publisher="fotmob",
            # 🔴 **표가 말한 시점을 그대로 싣는다**(사용자 지시 2026-10-02).
            #    그러면 §12-c-2 경기 후 배제가 **순위표에도 닿는다** — 전에는
            #    `None` 이라 날짜 없는 자료 예외로 빠져나갔다.
            #    ⚠️ 못 읽으면 `None` 이고 전처럼 예외로 남는다(지어내지 않는다).
            published_at=as_of,
            article_title=f"{val['team']} 순위",
            tier=verify.TIER_PREVIEW,
            extracted_by="rule:fotmob_table", step=1, team=val["team"]))
    if out:
        logger.info("[fotmob] 순위 %d건 · %s", len(out),
                    [(f.value["table"], f.value["rank"]) for f in out])
    return out


def follow_links(got, q: Question) -> list[str]:
    """🔴 `Source.follow` — **직전 경기 + 리그 표.** 둘 다 이 페이지가 가리킨다.

    ⚠️ 순서가 뜻을 가진다: 직전 경기가 먼저다. 예산이 모자라면 기준 XI 를 먼저
       얻는 것이 낫다 — 순위는 바뀌지만 기준 XI 는 그 경기의 사실이다.
    """
    urls = follow_prev(got, q)
    j = payload(getattr(got, "text", "") or "")
    tbl = league_table_url(j) if j else None
    if tbl:
        urls.append(tbl)
    return urls


def parse_followed(got, q: Question) -> list[Fact]:
    """🔴 따라간 자료를 **생김새로 가른다.** 주소가 무엇인지 보고 파서를 고른다."""
    url = getattr(got, "url", "") or ""
    if is_table_page(url):
        return parse_league_table(got, q)
    if is_match_page(url):
        return parse_prev(got, q)
    return []


# ══════════════════════════════════════════════════════════════════
# 🔴 선수 기록 — **경기 페이지가 이미 들고 있다**
# ══════════════════════════════════════════════════════════════════
#
# 측정 2026-10-01: R3(*"메모 … 토요 2골 1도움"*)·R6(*"에드워즈 후반 교체 득점"*)이
# 변환 0 이었다. 🔴 **선수 페이지를 따로 열 필요가 없었다** — 라인업의 선수마다
# `performance` 가 붙어 있다:
#
#     Memo Rodríguez  rating 9.3 · events [goal, goal, assist]   ← 2골 1도움
#     Kyle Edwards    교체 · events [goal]                        ← 교체 득점
#     (이번 경기)      seasonGoals 5 · seasonAssists 6 · seasonRating 7.65
#
# ⚠️ **없는 것**: 통산 기록(사용자의 *"USL 역대 1위 19골"*)은 경기 페이지에 없다.
#    시즌 숫자와 통산 숫자를 섞지 않는다 — 섞으면 거짓이다.

#: 세는 이벤트. 🔴 fotmob 의 `type` 이 원본이고 여기 **우리 이름**을 맞춘다.
_EVENTS = {"goal": "goals", "assist": "assists",
           "yellowCard": "yellow_cards", "redCard": "red_cards",
           "ownGoal": "own_goals", "penaltyMiss": "penalty_misses"}


def _perf(p: dict) -> dict:
    perf = p.get("performance") or {}
    out = {k: 0 for k in _EVENTS.values()}
    for e in (perf.get("events") or []):
        name = _EVENTS.get(str((e or {}).get("type") or ""))
        if name:
            out[name] += 1
    out["rating"] = perf.get("rating")
    # 🔴 **시즌 숫자는 시즌 이름으로** — 통산과 섞으면 거짓이다
    out["season_goals"] = perf.get("seasonGoals")
    out["season_assists"] = perf.get("seasonAssists")
    out["season_rating"] = perf.get("seasonRating")
    return out


def parse_players(j: dict, q: Question, *, url: str, when,
                  past: bool = False) -> list[Fact]:
    """선수별 기록. 🔴 **이 경기에 기록을 남긴 선수만** 사실로 올린다.

    ⚠️ 18~36명을 전부 올리면 블랙보드가 이름으로 뒤덮인다. 기록이 없는 선수는
       **라인업 사실이 이미 담고 있다**(§19-a: 사실 하나 = 질문 하나).
    🔴 `is_sub` 를 싣는다 — 사용자 R6 이 *"교체 출전 득점"* 이고, 선발인지 교체인지가
       그 변수의 전부다.
    """
    g = _page(j).get("general") or {}
    home = str((_side(j, "homeTeam") or {}).get("name") or "")
    away = str((_side(j, "awayTeam") or {}).get("name") or "")
    out: list[Fact] = []
    for which in ("homeTeam", "awayTeam"):
        side = _side(j, which)
        name = str(side.get("name") or "").strip()
        if not name:
            continue
        if q.team and not verify.mentions_team(name, q.team, q.local):
            continue
        for is_sub, group in ((False, side.get("starters") or []),
                              (True, side.get("subs") or [])):
            for p in group:
                if not isinstance(p, dict) or not str(p.get("name") or "").strip():
                    continue
                perf = _perf(p)
                scored = any(perf[k] for k in _EVENTS.values())
                has_season = perf["season_goals"] is not None
                if not (scored or has_season):
                    continue        # 🔴 라인업 사실이 이미 담았다
                val = {"team": name, "player": str(p["name"]).strip(),
                       "player_id": p.get("id"),
                       "shirt": p.get("shirtNumber"),
                       "is_sub": is_sub, **perf,
                       "from_match": f"{home} vs {away}",
                       "from_date": when.date().isoformat() if when else None}
                out.append(Fact(
                    question_id=f"{q.id}:player", value=val,
                    hardness="soft", from_past_match=past,
                    source=url, publisher="fotmob", published_at=when,
                    article_title=f"{val['player']} 경기 기록",
                    tier=verify.TIER_PREVIEW,
                    extracted_by="rule:fotmob_player", step=1, team=name))
    return out
