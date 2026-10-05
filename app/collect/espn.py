"""ESPN 어댑터 — **사용자 지시 2026-10-03**: *"espn 소스로 쓰고"*.

══════════════════════════════════════════════════════════════════
🔴 왜 쓰는가 — 갈림길이 닫혔다
══════════════════════════════════════════════════════════════════

`docs/fable/questions/2026-10-01_espn_robots.md` 가 **사용자 답을 기다리고** 있었고
2026-10-03 에 *"쓴다"* 로 닫혔다. 근거는 그 문서에 있다:

- `www.espn.com/robots.txt` 의 `*` 규칙이 **우리를 허용한다**(기사·일정 경로).
- 우리 UA 는 **봇이라고 밝힌다** — 절대규칙 3 이 금지한 프록시·UA 위장이 아니다.

🔴 **`site.api.espn.com` 은 그대로 안 쓴다** — robots 가 Access Denied 로 답한다.
   우리 규약의 *"읽을 수 없으면 허용"* 은 robots 가 **없는** 경우를 뜻하고, **거부로
   답하는** 자리는 아니다.

══════════════════════════════════════════════════════════════════
🔴🔴 **배당을 읽지 않는다** (절대규칙 6)
══════════════════════════════════════════════════════════════════

ESPN 경기 페이지 HTML 에는 `Open/ML/Total/Spread` 가 들어 있고, 페이로드에도
`betConfigSettings`·`wllClck` 같은 칸이 있다. 🔴 **이 파일은 그 칸을 읽지 않는다** —
배당은 `research` 스키마에만 들어가고 판정 경로·카드에는 **0건**이다.
⚠️ 계약이 이 파일의 코드에서 그 낱말을 찾아 막는다.

══════════════════════════════════════════════════════════════════
🔴 무엇을 읽나 — 실측 2026-10-03
══════════════════════════════════════════════════════════════════

일정(`/soccer/scoreboard/_/date/…`) 페이지는 **목록을 JS 로 받는다**(페이로드의
`evts` 가 0건이다). 그 목록은 `site.api.espn.com` 에서 오고 그것은 안 쓴다.
→ 🔴 **경기 페이지만** 읽는다. 거기엔 필요한 것이 다 들어 있다:

```
gamepackage.gmStrp.gid      경기 번호(열쇠)
gamepackage.gmStrp.dt       킥오프 UTC
gamepackage.gmStrp.nm       종목 이름("soccer"·"baseball"…)
gamepackage.gmStrp.status   진행 상태(`Full Time`·`post`…)
gamepackage.prsdTms.home/away  홈·원정 + 스코어
gamepackage.gmInfo.loc      구장 이름
gamepackage.lg              대회 코드("fifa.friendly")
```

실측: `gameId/401914141` → `China 0 - 5 Palestine · Full Time ·
Chongqing Longxing Football Stadium · 2026-10-02T11:35Z`.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta, timezone

from app import matchkey, timefmt, verify, window
from app.blackboard import Fact
from app.cells import Question, Source

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))
BASE = "https://www.espn.com"

#: 🔴 `games.ext_id` 의 접두 — **이 어댑터가 만든 행**이라는 표시다.
#   ⚠️ `fotmob.EXT_PREFIX` 와 같은 규약이다(`analyze.depth_sources` 가 둘을 본다).
EXT_PREFIX = "espn-"

#: 페이로드가 실리는 자리. 🔴 주소가 아니라 **문서 안**이다.
_FITT = re.compile(r"window\['__espnfitt__'\]\s*=\s*(\{.*?\});</script>", re.S)

#: 진행 상태 → 우리 규약. 🔴 모르는 값은 **이름으로 남긴다**(아래 `_status`).
STATE = {"pre": "scheduled", "in": "inprogress", "post": "final"}


def is_match_page(url: str) -> bool:
    """ESPN **경기** 페이지인가. 🔴 팀·리그 페이지에는 경기 자료가 없다.

    ⚠️ 종목마다 경로가 갈린다(`/soccer/match/`·`/mlb/game/`·`/nhl/game/`) —
       공통은 `gameId` 다. 그것으로 가른다.
    """
    u = url or ""
    return "espn.com" in u and "gameid/" in u.lower()


def match_id(url: str) -> str:
    """경기 주소에서 **ESPN 경기 번호**. 🔴 못 읽으면 빈 문자열."""
    m = re.search(r"gameid/(\d+)", str(url or ""), re.I)
    return m.group(1) if m else ""


def match_url(mid: str, sport: str = "soccer") -> str:
    """🔴 번호로 경기 페이지에 닿는다. ⚠️ 종목 조각이 주소에 들어간다."""
    kind = "game" if str(sport) in ("baseball", "hockey", "basketball") \
        else "match"
    return f"{BASE}/{sport}/{kind}/_/gameId/{str(mid or '').strip()}"


def payload(html: str) -> dict | None:
    """`window['__espnfitt__']` 를 꺼낸다. 🔴 없거나 JSON 이 아니면 `None`."""
    m = _FITT.search(html or "")
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError as exc:
        logger.info("[espn] __espnfitt__ 가 JSON 이 아니다: %s", exc)
        return None


def _pack(j: dict) -> dict:
    return (((j.get("page") or {}).get("content") or {})
            .get("gamepackage") or {})


def _status(strip: dict) -> tuple[str, str]:
    """`(우리 상태, 사람이 읽을 표기)`. 🔴 모르는 값은 **이름으로 남긴다**."""
    st = strip.get("status") or {}
    state = str(strip.get("statusState") or st.get("state") or "").strip()
    shown = str(st.get("desc") or st.get("statusPrimary") or "").strip()
    got = STATE.get(state)
    if got is None:
        logger.info("[espn] 모르는 진행 상태 %r(%r) — scheduled 로 두고 남긴다",
                    state, shown)
        return "scheduled", shown or state
    return got, shown


def _score(v) -> int | None:
    """🔴 스코어를 못 읽으면 `None` — 0 으로 때우지 않는다."""
    s = str(v if v is not None else "").strip()
    return int(s) if s.isdigit() else None


def slate_row(got, *, day: date | None = None) -> dict | None:
    """🔴 **경기 페이지 → 슬레이트 한 줄.** `ingest._slate` 가 받는 그 모양이다.

    ⚠️ `fotmob.slate_row` 와 **같은 규약**이다 — `findgame` 이 둘을 같은 자리에서
       쓴다(§19-b-4: 막히면 **대체**). 규약이 갈리면 그 자리에 분기가 생긴다.
    🔴 킥오프를 못 읽으면 **행을 만들지 않는다**(`ingest._slate` 가 시각 없는 행을
       버리므로 거기에 맞춘다).
    """
    if not getattr(got, "ok", False):
        return None
    url = str(getattr(got, "url", "") or "")
    if not is_match_page(url):
        return None
    j = payload(getattr(got, "text", "") or "")
    if not j:
        return None
    gp = _pack(j)
    strip = gp.get("gmStrp") or {}
    tms = gp.get("prsdTms") or {}
    home = str(((tms.get("home") or {}).get("displayName") or "")).strip()
    away = str(((tms.get("away") or {}).get("displayName") or "")).strip()
    when = verify.parse_when(str(strip.get("dt") or "").replace("Z", "+00:00"))
    mid = str(strip.get("gid") or "").strip() or match_id(url)
    if not (home and away and when and mid):
        logger.info("[espn] 슬레이트 행을 못 만들었다 — 홈=%r 원정=%r 시각=%s "
                    "번호=%r (%s)", home, away, when, mid, url)
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
        logger.info("[espn] 창 밖이라 안 싣는다 — %s (%s)", said_out, url[:70])
    if said_out:
        logger.info("[espn] 날짜가 다르다 — 페이지 %s vs 물은 날짜 %s (%s)",
                    when.astimezone(KST).date(), day, url)
        return None
    state, shown = _status(strip)
    info = gp.get("gmInfo") or {}
    return {
        # 🔴 종목을 **페이지가 말한다** — 주소에서 추측하지 않는다
        "sport": str(strip.get("nm") or "").strip() or "soccer",
        # 🔴 대회 코드를 못 읽으면 **빈칸이 아니라 이름으로** 남긴다
        "league": str(gp.get("lg") or "").strip() or "대회명 미상",
        "ext_id": matchkey.make("espn", mid),
        "home": home, "away": away,
        "venue": str(info.get("loc") or "").strip() or None,
        "starts_utc": when,
        # 🔴 `timestamptz` 는 **순간**이다 — `.astimezone(KST)` 는 이 칸에
        #    아무 효과가 없었다(실측 2026-10-05: 라이브 52행 전부
        #    `starts_kst = starts_utc`). 🔴 그 거짓 믿음을 입구에서 끊는다 —
        #    표시 KST 는 `timefmt.kst_label`, KST 날짜 질의는
        #    `timefmt.sql_kst_day` **하나씩**이다.
        "starts_kst": timefmt.db_instant(when),
        # 🔴 현지 시각대를 페이지가 안 준다 — 지어내지 않는다
        "starts_local": None,
        "status": state,
        "round_note": shown or None,
        "home_score": _score((tms.get("home") or {}).get("score")),
        "away_score": _score((tms.get("away") or {}).get("score")),
        "probable": {},
    }


def parse_context(got, q: Question, *, day=None) -> list[Fact]:
    """경기 페이지 → **구장·관중** 사실. 🔴 배당 칸은 읽지 않는다(절대규칙 6).

    ⚠️ fotmob 만큼 깊지 않다 — ESPN 경기 페이지의 맞대결·폼은 **다른 탭**이고
       그 탭은 JS 로 받는다(그 API 는 안 쓴다). 있는 척하지 않고 있는 것만 낸다.
    """
    url = str(getattr(got, "url", "") or "")
    if not is_match_page(url):
        return []
    j = payload(getattr(got, "text", "") or "")
    if not j:
        return []
    gp = _pack(j)
    strip = gp.get("gmStrp") or {}
    when = verify.parse_when(str(strip.get("dt") or "").replace("Z", "+00:00"))
    want = day or (q.deadline.astimezone(KST).date() if q.deadline else None)
    # 🔴 **창으로 본다**(지시 2026-10-04) — KST 달력 날짜가 아니다.
    #    ⚠️ `q.deadline` 은 그 경기의 킥오프다. 창 밖이면 **남의 경기**이거나
    #       이미 지난 경기다 — `window.why_out` 이 어느 쪽인지 말한다(§8-6).

    if when is None or (want is not None
                        and q.deadline
                        and not window.same_match_time(when, q.deadline)):
        return []                       # 🔴 §13-c ① — 다른 날 경기다
    # 🔴 §13-c ② — 이 페이지가 **우리 팀** 것인가
    tms = gp.get("prsdTms") or {}
    names = [str(((tms.get(s) or {}).get("displayName") or "")).strip()
             for s in ("home", "away")]
    names = [n for n in names if n]
    mine = (q.team or "").strip()
    if mine and not any(verify.mentions_team(n, mine, q.local) for n in names):
        logger.info("[espn] §13-c ② 거부 — 우리 팀(%s)이 없다 %s (%s)",
                    mine, names, url)
        return []
    info = gp.get("gmInfo") or {}
    val = {k: v for k, v in (
        ("Stadium", str(info.get("loc") or "").strip()),
        ("City", str((info.get("locAddr") or {}).get("city") or "").strip()),
        ("Attendance", info.get("attnd") or None),
        ("Tournament", str(gp.get("lg") or "").strip()),
    ) if v}
    if not val:
        return []
    return [Fact(question_id=f"{q.id}:info", value=val, hardness="hard",
                 source=url, publisher="espn.com", published_at=when,
                 article_title="경기 정보", tier=verify.TIER_PREVIEW,
                 extracted_by="rule:espn_info", step=1, team=q.team)]


def sources_context(ext_id: str) -> list[Source]:
    """🔴 이 경기의 깊이. ⚠️ **얕다** — 구장·관중뿐이고 그 사실을 숨기지 않는다.

    🔴 접두를 요구한다 — 안 요구하면 다른 어댑터의 숫자 `ext_id` 도 통과한다.
    """
    # 🔴 §8-1 — `matchkey.mine` 이 *"내 것이냐"* 까지 답한다. ⚠️ 종전
    #    `startswith("espn-")` 은 `espn:401` 을 거절했다(실측 2026-10-04).
    mid = matchkey.mine(ext_id, "espn")
    if not mid.isdigit():
        return []
    return [Source("espn 경기 정보", "url", url=match_url(mid),
                   tier=verify.TIER_PREVIEW, parse=parse_context,
                   dateless_ok=True)]
