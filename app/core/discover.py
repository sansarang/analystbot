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

#: 🔴 §2 ① — 날짜가 없으면 **오늘~+2일**
WINDOW_DAYS = 2
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
    #: 🔴 어느 칸에서 찾았나 — 보고가 이것을 적는다(§4 "출처")
    rung: str = ""


def norm_name(said: object) -> str:
    """🔴🔴 **이름 정규화 — 한 곳**(§2 ② 마지막 줄).

    하는 일: 유니코드 분해 후 결합문자 제거(`Unión`→`union`) · 소문자 ·
    글자 아닌 것을 공백 · `_AFFIX` 의 클럽 표기 제거 · 공백 제거.

    ⚠️ **글자를 지어내 바꾸지 않는다** — 떼는 것은 `_AFFIX` 에 적힌 것뿐이다.
    🔴 한글↔로마자는 **여기서 잇지 않는다** — 그것은 이름표(`learn_names`)의 일이고
       여기서 억지로 이으면 엉뚱한 팀을 분석한다(M14).
    """
    low = unicodedata.normalize("NFKD", str(said or ""))
    low = "".join(c for c in low if not unicodedata.combining(c)).lower()
    low = re.sub(r"[^0-9a-z가-힣ぁ-んァ-ヴー一-龥]+", " ", low)
    for w in _AFFIX:
        low = re.sub(rf"(^|\s){w}(\s|$)", " ", low)
    return re.sub(r"\s+", "", low)


#: 🔴 떼는 접사 — 팀 이름의 **클럽·법인 표기**뿐이다(실측으로 늘린다).
#  ⚠️ `united`·`city` 는 **떼지 않는다** — `Adelaide City` ↔ `Adelaide United` 가
#     같은 팀이 돼 버린다(실사고가 될 자리였다 · 2026-10-10 에 잡았다).
_AFFIX: tuple[str, ...] = (
    "fc", "cf", "sc", "ac", "afc", "cd", "ca", "sv", "if", "bk", "fk",
    "club", "clube", "asd", "ssd", "us", "as", "ud", "cs",
    "futbol", "football", "calcio", "spor", "kulubu", "kulübü",
)


def same(a: object, b: object) -> bool:
    """🔴 두 이름이 같은 팀인가 — 정규화 뒤 **한쪽이 다른 쪽을 품으면** 같다.

    ⚠️ 품는 검사는 느슨하다. 🔴 그래서 **네 글자 미만은 품기를 안 쓴다** — `un` 이
       `union` 을, `cesena` 가 `ac cesena` 를 넘어 엉뚱한 데 붙는 것을 막는다.
    """
    x, y = norm_name(a), norm_name(b)
    if not x or not y:
        return False
    if x == y:
        return True
    if len(x) < 4 or len(y) < 4:
        return False
    return x in y or y in x


def window(day: date | None, *, today: date | None = None) -> list[date]:
    """🔴 §2 ① — 날짜가 없으면 **오늘~+2일**."""
    if day is not None:
        return [day]
    base = today or date.today()
    return [base + timedelta(days=i) for i in range(WINDOW_DAYS + 1)]


def _slug_hit(index: dict[str, str], name: str) -> list[tuple[str, str]]:
    """🔴 색인(`{id: 슬러그}`)에서 그 이름에 맞는 줄 — **정확 일치가 먼저**다.

    ⚠️ 품는 일치를 먼저 쓰면 `adelaide-city` 를 물을 때 `adelaide-united` 가
       앞에 설 수 있다. 🔴 정확 → 품음 순서로 돌려준다.
    """
    want = norm_name(name)
    if not want:
        return []
    exact = [(i, s) for i, s in index.items() if norm_name(s) == want]
    loose = [(i, s) for i, s in index.items()
             if norm_name(s) != want and same(s, name)]
    return [*sorted(exact), *sorted(loose)]


async def find(net, *, home: str, away: str, day: date | None = None,
               today: date | None = None) -> Found:
    """🔴🔴 §2 — 사다리 ②③ 을 순서대로. ⚠️ **리그를 묻지 않는다**.

    ④(검색 단)는 부르는 쪽이 잇는다(`app/findgame.py` 가 그 통로다) — 여기서
    검색을 다시 짜면 통로가 둘이 된다(사본 금지).
    """
    got = Found()
    days = window(day, today=today)
    out = await _by_team(net, home=home, away=away, days=days, got=got)
    if out.match:
        return out
    out = await _by_league(net, home=home, away=away, days=days, got=got)
    if out.match:
        return out
    got.why = miss_line(got)
    return got


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
                   got: Found) -> Found:
    """🔴 §2 ② — 팀 색인에서 id 를 풀고, **그 팀 일정**에서 상대를 맞춘다.

    🔴 **한쪽만 풀려도 된다** — 실측 2026-10-10: `union-santa-fe` 는 색인에 0건인데
       `defensa-y-justicia` 는 `161730` 으로 풀린다. 그 팀 일정에서 상대를 찾으면
       경기가 확정된다.
    """
    from app.collect import fotmob as fm
    index = await fm.team_index(net)
    got.tried.append(f"fotmob 팀 색인(sitemap) {len(index)}팀")
    want = {d.isoformat() for d in days}
    seen: set[str] = set()
    for term, other in ((home, away), (away, home)):
        if not str(term or "").strip():
            continue
        hits = _slug_hit(index, term)
        got.tried.append(f"색인에서 `{term}` → {len(hits)}건")
        if len(hits) > MAX_TEAMS:
            got.tried.append(f"⚠️ `{term}` 후보 {len(hits)}건 중 {MAX_TEAMS}건만 "
                             f"열었다(상한)")
        for tid, slug in hits[:MAX_TEAMS]:
            if tid in seen:
                continue
            seen.add(tid)
            got.candidates.append({"team": slug, "id": tid})
            page = await net.get(fm.team_fixtures_url(tid, slug))
            rows = team_fixtures(getattr(page, "text", "") or "", tid)
            got.tried.append(f"fotmob 팀일정 `{slug}` {len(rows)}경기")
            for m in rows:
                if str(m.get("utc") or "")[:10] not in want:
                    continue
                if not (same(m["home"], other) or same(m["away"], other)):
                    continue
                got.match, got.rung = m, "② 팀 색인 → 팀 일정"
                got.league_id = m.get("league_id")
                got.league_name = str(m.get("league_name") or "")
                got.why = (f"✅ 팀 색인 → 일정 — `{slug}` 의 "
                           f"{str(m.get('utc'))[:10]} 경기")
                return got
    return got


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
                     got: Found) -> Found:
    """🔴 §2 ③ 대체 — **리그 색인**에서 이름이 걸리는 리그의 일정을 본다.

    ⚠️ 리그 색인은 431개다 — 전부 열지 않는다. 🔴 질문의 **두 팀 이름 조각**이
       리그 슬러그에 걸리는 리그만 본다(`adelaide` → `australia-championship` 처럼
       도시 이름이 걸리는 일이 있다). 걸리는 것이 없으면 ③ 은 **아무것도 안 하고**
       그 사실을 적는다 — 없는 통로를 있는 척하지 않는다.
    """
    from app.collect import fotmob as fm
    index = await fm.league_index(net)
    got.tried.append(f"fotmob 리그 색인(sitemap) {len(index)}리그")
    words = [w for w in re.split(r"\s+", f"{home} {away}".strip()) if len(w) > 3]
    hits = sorted({(i, s) for i, s in index.items()
                   for w in words if norm_name(w) in norm_name(s)})
    if not hits:
        got.tried.append("리그 색인에 걸리는 이름이 없다 — ③ 을 건너뛴다")
        return got
    want = {d.isoformat() for d in days}
    for lid, slug in hits[:MAX_LEAGUES]:
        rows = await fm.league_matches(net, lid)
        got.tried.append(f"fotmob 리그일정 `{slug}` {len(rows)}경기")
        for m in rows:
            if str(m.get("utc") or "")[:10] not in want:
                continue
            if ((same(m["home"], home) and same(m["away"], away))
                    or (same(m["home"], away) and same(m["away"], home))):
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
    today = (when or date.today()).isoformat()
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
    rows = await fm.league_season_rows(net, league_id)
    # 🔴 **경기 페이지가 적은 글자**를 함께 담는다 — 카드 쪽이 그 글자만 받는다
    seen = [str(league_name or ""), str(meta.get("name") or "")]
    old_seen = load_seen(key)
    box, why = al.build(competition_key=key, meta=meta, teams=teams,
                        baseline=al.baseline_of(rows), seen=[*old_seen, *seen],
                        when=when)
    if not box:
        return {}, why
    p, said = al.save(box)
    return (box if p else {}), f"{why} · {said}"


def load_seen(key: str) -> list[str]:
    """🔴 이미 쌓인 **본 글자들** — 갱신이 그것을 지우지 않게(§2: *"이미 있으면
    갱신만"*). ⚠️ 덮어쓰면 어제 본 표기가 사라지고 같은 오진이 다시 난다."""
    from app.core import autoleague as al
    return [str(x) for x in (al.load(key).get("seen") or [])]
