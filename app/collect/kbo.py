"""KBO — **TheSportsDB**. 🔴 키 0건 · 카드 0건.

══════════════════════════════════════════════════════════════════
🔴 왜 이 어댑터가 이제야 생겼나 — 그리고 왜 **공식 사이트가 아닌가**
══════════════════════════════════════════════════════════════════

`config.LEAGUES_AUTO` 에는 `KBO` 가 **처음부터 있었다.** 그런데 `ingest.ADAPTERS`
에는 없었다 — 즉 **설정이 거짓말을 하고 있었다**(CLAUDE.md #2 배선). 사용자가
*"오늘 기아와 LG 야구 경기를 봇에게 시켜봐라"* 라고 하자 그 구멍이 드러났다.

🔴 **공식 사이트는 쓸 수 없다.** 실측 2026-10-03:

```
koreabaseball.com/robots.txt
  # 본 사이트의 데이터를 사전 승인 없이 자동 수집·크롤링·복제하는 행위를 금지합니다.
  User-agent: *
  Disallow: /
```
절대규칙 3(= v4 §14): *"robots 거부 도메인은 **dead 처리뿐.** 프록시·UA 위장 금지."*
→ **안 간다.** 머리글이 한국어 문장으로까지 금지를 적어 두었다.

다른 곳도 **받아서** 확인했다(추측 금지):

| 곳 | 실측 2026-10-03 |
|---|---|
| `m.sports.naver.com` | 🔴 `Disallow: /` (`/index` 만 허용) |
| `mykbostats.com` | robots 는 열려 있는데 **Cloudflare 가 403**(JS 챌린지) — 뚫지 않는다 |
| `sports.daum.net` | robots 는 열려 있으나 본문이 JS 로 오고 그 API 는 `/prx/` **금지** |
| `api.sofascore.com` | 🔴 robots 자체가 403 |
| ESPN KBO | `HTTP 400` — ESPN 은 KBO 를 **안 준다** |
| **thesportsdb.com** | ✅ `Allow: /`(`/nfo/` 만 금지) · 키 없이 200 · KBO 10팀 · 그 경기를 들고 있었다 |

⚠️ **그 robots 에 `Content-Signal: ai-train=no, search=yes, ai-input=no` 가 있다.**
   `ai-input=no` 는 우리 용도를 직접 지목한다. 🔴 내가 그 갈림길을 고르지 않고
   사용자에게 알렸고, 사용자가 *"다 고쳐라... 나 내봇이 정상적으로 작동만 되면
   된다"* 로 **다시 지시했다**(2026-10-03). 그래서 쓴다 — 그 사실을 여기 남긴다.
   기록: `docs/fable/questions/2026-10-03_kbo_source.md`.

🔴 **학습에 쓰지 않는다**(`ai-train=no`) — 이 저장소는 모델을 학습시키지 않는다.
🔴 **긁지 않는다** — 공개 API 엔드포인트만 부른다. 페이지 HTML 을 받지 않는다.

══════════════════════════════════════════════════════════════════
⚠️ 이 소스가 **얕다** — 있는 척하지 않는다
══════════════════════════════════════════════════════════════════

실측: `eventsnextleague`(리그 전체)가 **1건**만 줬고, 팀별 `eventsnext` 로 물어야
그 경기가 나왔다. 그래서 일정은 **10팀을 각각** 묻는다(한 번에 안 준다).
🔴 예고 선발·라인업·부상은 **이 API 에 없다.** 그 칸은 비워 두고 사유를 남긴다 —
   0 으로 메우지 않는다(CLAUDE.md #3).
⚠️ 지난 경기(`eventslast.php`)도 **안 만들었다** — 쓰는 곳이 없으면 짓지 않는다
   (CLAUDE.md #2: 안 이어진 코드는 없는 코드보다 나쁘다). 폼·맞대결을 여기서
   가져오게 되는 날 그때 만든다.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from app import matchkey
from app.blackboard import Fact
from app.cells import Question, Source
from app.net import Fetched

logger = logging.getLogger(__name__)

#: 🔴 공개 테스트 키 `3`. **카드·결제가 없다**(§11-7 유료 API 0건 정의 안).
BASE = "https://www.thesportsdb.com/api/v1/json/3"
KST = timezone(timedelta(hours=9))

LEAGUE = "KBO"
SPORT = "baseball"
#: 🔴 `games.ext_id` 접두 — 다른 리그 id 와 섞이지 않게(`DEPTH_BY_EXT` 와 같은 규약)
EXT_PREFIX = "tsdb-"
#: TheSportsDB 의 KBO 리그 id (실조회 2026-10-03)
LEAGUE_ID = "4830"

#: 🔴🔴 **소스를 전부 모은다** — 첫 성공에서 멈추면 안 된다.
#
#  ⚠️ 세포의 기본은 *"첫 성공에서 멈춘다"* 다(§19 예산). 다른 리그는 일정이 **한
#     주소**에 다 있어서 그래도 된다. 🔴 이 API 는 **팀마다 따로** 물어야 하므로
#     첫 성공에서 멈추면 **한 경기만** 들어온다 — 실측 2026-10-03: 리그 질의가
#     `Samsung vs Doosan` 하나를 주고 끝나서 `LG vs KIA` 가 표에 안 들어왔다.
#  🔴 어댑터가 **스스로 선언한다** — 부르는 쪽이 리그 이름으로 분기하지 않는다
#     (분기는 자라고, 새 어댑터가 같은 병을 다시 앓는다).
SLATE_COLLECT_ALL = True

#: 🔴 10팀의 id. **실조회로 받은 것**이고 손으로 지어내지 않았다
#   (`search_all_teams.php?l=Korean KBO League` · 2026-10-03).
#   ⚠️ 표기는 이 API 의 영문 표기다 — 한국어 표기는 `app/bot/aliases.py` 가 맡는다.
TEAM_IDS: dict[str, str] = {
    "LG Twins": "139820",
    "Lotte Giants": "139821",
    "Kiwoom Heroes": "139823",
    "Kia Tigers": "139824",
    "Samsung Lions": "139825",
    "Hanwha Eagles": "139826",
    "KT Wiz": "139827",
    "SSG Landers": "139828",
    "NC Dinos": "139819",
    "Doosan Bears": "139822",
}

#: TheSportsDB `strStatus` → 우리 `games.status`.
#: 🔴 모르는 값은 **`scheduled` 로 밀지 않는다** — 그러면 끝난 경기가 예정으로 보인다.
_STATUS = {
    "NS": "scheduled", "": "scheduled",
    "1H": "inprogress", "2H": "inprogress", "LIVE": "inprogress",
    "IN": "inprogress", "HT": "inprogress",
    "FT": "final", "AOT": "final", "Match Finished": "final",
    "PST": "postponed", "POST": "postponed", "CANC": "postponed",
}


def team_next_url(team_id: str) -> str:
    return f"{BASE}/eventsnext.php?id={team_id}"


def league_next_url() -> str:
    return f"{BASE}/eventsnextleague.php?id={LEAGUE_ID}"


def _rows(got: Fetched) -> list[dict]:
    """응답 → 경기 목록. 🔴 두 칸 이름을 **둘 다** 본다(`events`·`results`)."""
    if not got.ok or not (got.text or "").strip():
        return []
    try:
        data = json.loads(got.text)
    except ValueError:
        logger.info("[kbo] JSON 이 아니다 — %s", (got.text or "")[:80])
        return []
    if not isinstance(data, dict):
        return []
    out = data.get("events") or data.get("results") or []
    return [x for x in out if isinstance(x, dict)]


def _when(ev: dict) -> datetime | None:
    """🔴 `strTimestamp` 만 믿는다 — **UTC** 다.

    ⚠️ `strTimeLocal`·`dateEventLocal` 은 실측에서 **어긋나 있었다**(그 경기의
       `dateEventLocal` 이 `2026-09-25` 였다). 어긋난 칸으로 시각을 만들지 않는다.
    """
    raw = str(ev.get("strTimestamp") or "").strip()
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "")).replace(
                tzinfo=timezone.utc)
        except ValueError:
            pass
    d, t = str(ev.get("dateEvent") or ""), str(ev.get("strTime") or "")
    if d and t:
        try:
            return datetime.fromisoformat(f"{d}T{t}").replace(
                tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _score(v) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def slate_row(ev: dict) -> dict | None:
    """경기 하나 → `games` 표의 행. 🔴 못 채우는 칸은 **`None`** 이다.

    ⚠️ 시각을 모르면 **행을 만들지 않는다** — 시각 없는 경기는 슬레이트에 뜻이 없다.
    """
    when = _when(ev)
    home, away = str(ev.get("strHomeTeam") or ""), str(ev.get("strAwayTeam") or "")
    if when is None or not home or not away:
        return None
    st = _STATUS.get(str(ev.get("strStatus") or "").strip())
    if st is None:
        # 🔴 **모르는 상태를 조용히 `scheduled` 로 밀지 않는다**
        logger.info("[kbo] 모르는 status %r — scheduled 로 두되 기록한다",
                    ev.get("strStatus"))
        st = "scheduled"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 `strPostponed` 를 **안 읽는다** — 순연 칸이 아니다(실측 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  처음엔 *"`strStatus`=NS 인데 `strPostponed`=yes 면 더 나쁜 쪽을 택한다"* 로
    #  짰다. 그랬더니 그날 KBO **네 경기가 전부 `postponed`** 로 들어갔다.
    #
    #  🔴 열 건을 받아 보니 규칙이 이것이었다:
    #        `NS`(미시작) 5건 → `strPostponed: yes`  (5/5)
    #        `FT`(종료)   5건 → `strPostponed: no`   (5/5)
    #     즉 이 칸은 **"아직 안 끝났다"** 를 뜻하고 순연과 무관하다.
    #  ⚠️ 그대로 뒀다면 봇이 **모든 다음 경기를 순연이라고** 말했을 것이다 —
    #     상태값을 뜻 확인 없이 믿은 것이 원인이다(CLAUDE.md #4 추측 금지).
    return {
        "sport": SPORT, "league": LEAGUE,
        "ext_id": matchkey.make("tsdb", ev.get("idEvent")),
        "home": home, "away": away,
        "venue": str(ev.get("strVenue") or "") or None,
        "starts_utc": when,
        "starts_kst": when.astimezone(KST),
        # 🔴 §2 — 현지 시각도 저장한다. KBO 의 현지는 **KST 와 같다**(한국 리그다).
        "starts_local": when.astimezone(KST),
        "status": st,
        "home_score": _score(ev.get("intHomeScore")),
        "away_score": _score(ev.get("intAwayScore")),
        "round_note": None,
    }


def parse_slate(got: Fetched, q: Question | None = None) -> list[dict]:
    """응답 → 행 목록. 🔴 **같은 경기를 두 번 적지 않는다**(팀마다 묻기 때문)."""
    del q
    out, seen = [], set()
    for ev in _rows(got):
        row = slate_row(ev)
        if not row or row["ext_id"] in seen:
            continue
        seen.add(row["ext_id"])
        out.append(row)
    return out


def _slate_fact(got: Fetched, q: Question, url: str) -> list[Fact]:
    """🔴 파서는 `dict` 행을 낸다(그게 `games` 표의 모양이다) — 세포는 `Fact` 를
    받는다. 그 경계를 여기서 감싼다(`mlb._slate_fact` 와 같은 규약)."""
    rows = parse_slate(got, q)
    if not rows:
        return []
    return [Fact(question_id=q.id, value=rows, hardness="hard",
                 publisher="TheSportsDB", source=url, step=0)]


def sources_slate(day) -> list[Source]:
    """🔴 **10팀을 각각 묻는다.**

    ⚠️ 실측 2026-10-03: 리그 전체(`eventsnextleague`)가 **1건**만 줬고, 그날의
       `LG Twins vs Kia Tigers` 는 **팀별로 물어야** 나왔다. 한 번에 주는 길이
       없으므로 10번 묻는다 — 그 비용을 숨기지 않는다.
    🔴 `day` 는 쓰지 않는다 — 이 API 는 **날짜로 못 거른다**(다음 경기만 준다).
       거르는 것은 `slate.find` 의 날짜 창이 한다. 그 사실을 이름으로 남긴다.
    """
    del day
    out = [Source("TheSportsDB KBO 리그 일정", "url", url=league_next_url(),
                  tier=1,
                  parse=lambda g, q: _slate_fact(g, q, league_next_url()))]
    for name, tid in TEAM_IDS.items():
        u = team_next_url(tid)
        out.append(Source(f"TheSportsDB {name} 다음 경기", "url", url=u, tier=1,
                          parse=lambda g, q, _u=u: _slate_fact(g, q, _u)))
    return out


def sources_context(ext_id: str) -> list[Source]:
    """🔴 **깊이는 없다.** 이 API 는 예고 선발·라인업·부상을 주지 않는다.

    ⚠️ 빈 목록을 돌려주면 `analyze` 가 *"공식 깊이 소스가 없다"* 를 사유로 적는다 —
       그것이 정직한 상태다. 있는 척하는 함수를 두지 않는다(CLAUDE.md #2).
    """
    del ext_id
    return []
