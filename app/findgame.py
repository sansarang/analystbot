"""🔴🔴 **봇이 모르는 경기를 봇이 스스로 찾아 슬레이트에 올린다.**

사용자 지시 2026-10-02:

> 봇이 서치한다..봇이 가설세운다..봇이 변수 만든다..봇이 결과값은 준다..
> 너가 할거는 봇을 잘 만들어라 한다..

══════════════════════════════════════════════════════════════════
🔴 왜 이 파일이 생겼나
══════════════════════════════════════════════════════════════════

봇이 아는 경기는 **어댑터가 있는 리그**뿐이다(`collect.ingest.ADAPTERS`:
MLB·NPB·NHL·해외축구·K리그). 그래서 **국제 친선**(대표팀 친선)처럼 어댑터가 없는
경기는 `games` 표에 들어오지 않고, 질문하면 *"분석할 경기를 못 찾았다"* 가 돌아온다.

⚠️ 사람이 손으로 행을 넣으면 그것은 **봇이 한 것이 아니다.** 사용자 지시가 금지한
   바로 그것이다. 그래서 **봇이 찾는다.**

🔴 **새 소스를 들이지 않는다.** fotmob 경기 페이지에 필요한 것이 다 있고
   (킥오프 UTC·홈/원정·구장·대회명), 그 페이지는 봇이 **이미** 검색으로 찾아 열고
   있다(§19-c 라인업 깊이). robots 결정이 이미 서 있는 호스트다.
   ⚠️ ESPN 은 쓰지 않는다 — `docs/fable/questions/2026-10-01_espn_robots.md` 가
      **사용자 답을 기다리는 중**이다(⏳). 답이 없는 갈림길을 코드가 고르지 않는다.

🔴 **표를 두 길로 쓰지 않는다** — 행을 적는 SQL 은 `collect.ingest._UPSERT_GAME`
   하나다. 여기서 베끼지 않고 그것을 부른다(CLAUDE.md #1 사본 금지).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from app import queries, timefmt, window
from app.cells import Question
from app.collect import espn, fotmob
from app.net import Net, SearchUnavailable

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

#: 🔴 **열어 볼 상한.** 검색 결과에 경기 페이지가 아닌 것이 섞인다 — 상한 없이
#   열면 한 질문이 수십 번 통신한다. ⚠️ 숫자는 실제 테스트로 고친다(사용자 지시
#   2026-10-02). 6 으로 시작한다 — 실측에서 fotmob 경기 페이지는 상위 6건 안에 있었다.
MAX_OPEN = 6

#: 🔴 던질 질의 상한. 각 질의가 SearXNG 한 번이다.
MAX_QUERIES = 4

#: 🔴🔴 **경기 페이지를 읽는 어댑터들** — 순서가 곧 시도 순서다(§19-b-4 대체).
#
#  ⚠️ 하나로 두면 그 호스트가 막히는 날 봇이 경기를 **아예 못 찾는다.** 둘 다 같은
#     규약(`is_match_page`·`match_id`·`slate_row`)을 지키므로 분기가 생기지 않는다.
#  🔴 fotmob 이 먼저인 까닭: 깊이(맞대결·폼·기준 XI)를 **그 페이지가 들고 있다**.
#     ESPN 경기 페이지의 그 자료는 다른 탭이고 그 탭은 JS 로 받는다(안 쓰는 API).
#  ⚠️ ESPN 은 사용자 지시 2026-10-03 으로 열렸다
#     (`docs/fable/questions/2026-10-01_espn_robots.md`).
READERS = (fotmob, espn)


@dataclass
class Found:
    """🔴 **찾았나와 왜 못 찾았나를 함께** 들고 온다(#3 조용한 0 금지)."""

    rows: list[dict] = field(default_factory=list)
    #: 저장한 `games.id` 들
    ids: list[int] = field(default_factory=list)
    #: 던진 질의 · 연 주소 · 버린 사유 — 전부 이름으로 남는다
    tried: list[str] = field(default_factory=list)
    #: ⚠️ **곁들이는 설명**이다 — 무엇이 막았나는 아래 `reason` 이 정한다.
    why: str = ""
    #: 🔴🔴 **실패한 조건이 직접 넣는다**(4단계 · 사용자 설계 2026-10-03).
    reason: object = None


def _queries(team: str, opponent: str, day: date, league: str = "") -> list[str]:
    """🔴 무엇으로 찾나. **`app/queries.py` 의 언어 규칙을 그대로 쓴다.**

    ⚠️ 낱말을 여기서 새로 짓지 않는다 — fotmob 경기 페이지는 **영어 팀명**으로
       색인되므로 영어가 1순위다(`queries.langs_for` 가 늘 영어를 맨 앞에 둔다).
    """
    langs, why = queries.langs_for(league, team, opponent)
    logger.info("[findgame] 검색 언어 %s — %s", list(langs), why)
    both = f"{team} {opponent}".strip()
    one = both if opponent else team
    out = [f"fotmob {one}", f"{one} fotmob match"]
    # 🔴 날짜를 붙인 판도 던진다 — 같은 두 팀이 여러 번 만난다(친선·예선)
    md = queries.month_day(day, "en")
    out.append(f"fotmob {one} {md}")
    # 🔴 **ESPN 쪽 질의도 던진다**(§19-b-4 대체). 사용자 지시 2026-10-03.
    out.append(f"espn {one} match")
    if opponent:
        out.append(f"{team} vs {opponent} lineups fotmob")
    # ⚠️ 중복 제거 — 같은 질의를 두 번 던지면 엔진 정지를 부른다
    seen: set[str] = set()
    uniq = []
    for q in out:
        key = " ".join(q.split()).lower()
        if key and key not in seen:
            seen.add(key)
            uniq.append(" ".join(q.split()))
    return uniq[:MAX_QUERIES]


async def find(*, team: str, opponent: str = "", day: date | None = None,
               league: str = "", net: Net | None = None, search=None,
               ) -> Found:
    """🔴 **봇이 검색으로 경기 페이지를 찾아 슬레이트 행을 만든다.** 저장은 안 한다.

    ⚠️ 경기를 **고르지 않는다** — 맞는 것이 여럿이면 전부 돌려주고 고르는 것은
       사용자 몫이다(§17-g-3 · M14: 남의 경기를 분석하면 전부 거짓이 된다).
    """
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **창은 "지금부터 36시간(UTC)"다** — 사용자 지시 2026-10-04
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `day` 는 **검색어를 만드는 데만** 쓴다(`Oct 4` 같은 글자). 🔴 경기를
    #     **버릴지 말지는 `window.inside` 가** 정한다 — 두 일을 섞으면 유럽
    #     저녁 경기가 통째로 떨어진다(실측: 포르투갈 vs 노르웨이).
    #  🔴 창이 **이틀을 걸치므로** 검색어도 그 날짜들로 던진다 — 하루만 던지면
    #     *"내일 03:45(KST)"* 경기의 기사를 못 찾는다.
    wdays = window.days(tz=KST)
    day = day or wdays[0]
    net = net or Net(cache=True)
    if search is None:
        from app.search import build_chain
        search = build_chain()
    got = Found()
    if not str(team or "").strip():
        from app.matchref import Reason as _R
        got.reason = _R.NO_QUERY
        got.why = "팀 이름이 비었다 — 무엇을 찾을지 모른다"
        return got

    # 🔴 **그 경기 페이지인가**를 판정할 질문. `fotmob._not_our_match` 가 이것을 쓴다
    q = Question("lineup", f"{league}:{team}:{day}", team=team,
                 league=league or None, opponent=opponent or None)

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **fotmob API 는 안 쓴다** — robots 가 막는다(사용자 결정 2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > `www.fotmob.com/robots.txt` 는 일반 봇에게 `/` 는 허용, **`/api/*` 는
    #  > Disallow** 다. 열어 준 것은 Googlebot·Bingbot·Qwantbot 셋뿐이다. 즉
    #  > fotmob 의 의사는 분명하다 — *"페이지는 읽어도 되고, API 는 검색엔진
    #  > 아니면 치지 마라."* **API 경로(apigw, `/api/*`)는 dead 처리.**
    #
    #  ⚠️ `apigw.fotmob.com` 은 robots 가 **404**(없음)였다. 🔴 그래도 결론은
    #     같다 — 같은 서비스가 본 호스트에서 API 를 막아 놨는데 **다른 호스트로
    #     같은 API 를 치는 것**은 절대규칙 3 의 정신에 어긋난다(§14-12 우회 금지).
    #
    #  🔴 그래서 **허용된 HTML 페이지만** 쓴다(`/matches/…`). 잃는 것이 없다 —
    #     그 페이지에 경기 id·양 팀 id·현지 표기가 **이미 들어 있다**. 자동완성
    #     없이도 *"검색 → 결과 주소의 `/matches/…` 를 읽기"* 로 같은 id 를 얻는다.
    #  ⚠️ 종전에 여기 있던 자동완성 단(`app/namefind.py`)은 **지웠다** —
    #     꺼 두는 것이 아니라 지운다(안 이어진 코드는 없는 코드보다 나쁘다).
    opened = 0
    seen_ids: set[str] = set()
    from app import rules
    for text in _queries(team, opponent, day, league):
        try:
            hits = await search.query(text, lang="en",
                                      engines=list(rules.news_engines()))
        except SearchUnavailable as exc:
            got.tried.append(f"질의 `{text}`: 검색 수단 없음 — {exc}")
            continue
        # 🔴 **어느 어댑터가 읽을 수 있는 주소인가** — 하나로 묶어 본다
        cand = [h for h in (hits or [])
                if _reader_for(str(getattr(h, "url", "") or "")) is not None]
        got.tried.append(f"질의 `{text}` → {len(hits or [])}건 중 경기 페이지 "
                         f"{len(cand)}건")
        # 🔴 기사 호스트 순서표를 그대로 쓴다 — 순서가 결과를 정한다
        cand.sort(key=lambda h: rules.host_rank(str(getattr(h, "url", ""))))
        for h in cand:
            if opened >= MAX_OPEN:
                got.tried.append(f"열기 상한 {MAX_OPEN} 소진 — 남은 후보를 안 열었다")
                break
            url = str(getattr(h, "url", "") or "")
            reader = _reader_for(url)
            if reader is None:
                continue
            mid = f"{reader.EXT_PREFIX}{reader.match_id(url)}"
            if mid and mid in seen_ids:
                continue          # 같은 경기의 다른 주소 표기다
            opened += 1
            page = await net.get(url)
            if not page.ok:
                got.tried.append(f"{url} {page.reason}")
                continue
            j = reader.payload(page.text or "")
            if not j:
                got.tried.append(f"{url} 경기 자료를 못 읽었다(페이로드 없음)")
                continue
            # 🔴 **남의 경기를 저장하지 않는다**(§13-c ②). fotmob 은 남녀·연령
            #    표식까지 가른다 — ESPN 은 `slate_row` 뒤에 팀 이름으로 가른다.
            bad = (fotmob._not_our_match(j, q) if reader is fotmob else "")
            if bad:
                got.tried.append(f"{url} 건너뜀 — {bad}")
                continue
            row = reader.slate_row(page, day=day)
            if row is None:
                got.tried.append(f"{url} 슬레이트 행을 못 만들었다(사유는 로그)")
                continue
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **여기서 이름표가 자란다**(③ · 사용자 설계 2026-10-04)
            # ══════════════════════════════════════════════════════════
            #
            #  경기 페이지가 **두 팀을 함께 확인해 줬다.** 사용자가 물은 두 이름 중
            #  하나만 이름표가 알면, 나머지 하나의 짝이 **하나로 정해진다.**
            #  ⚠️ 조건을 못 채우면 `learn` 이 아무것도 안 적고 사유를 로그에 남긴다.
            #  🔴 **새 팀을 만들지 않는다** — 페이지 이름을 이름표가 모르면 배울 것이
            #     없다(그 팀 자체를 모르는 것이다).
            try:
                from app import learn_names
                learn_names.learn(
                    asked=(team, opponent),
                    page_names=(fotmob.team_names(j) if reader is fotmob
                                else [row["home"], row["away"]]),
                    match_key=str(row.get("ext_id") or ""))
            except Exception as exc:                    # noqa: BLE001
                # 🔴 **배우다 죽어서 경기를 잃지 않는다** — 학습은 곁다리다
                logger.info("[findgame] 이름 학습 실패(무시한다): %r", exc)
            # 🔴 **ESPN 경로의 §13-c ②** — 두 이름이 우리 두 팀인가
            if reader is not fotmob:
                names = [row["home"], row["away"]]
                if team and not any(
                        _mentions(n, team) for n in names):
                    got.tried.append(f"{url} 건너뜀 — 우리 팀({team})이 없다 {names}")
                    continue
                if opponent and not any(
                        _mentions(n, opponent) for n in names):
                    got.tried.append(
                        f"{url} 건너뜀 — 상대({opponent})가 없다 {names}")
                    continue
            if mid:
                seen_ids.add(mid)
            got.rows.append(row)
            logger.info("[findgame] 찾았다 — %s @ %s · %s · %s KST (%s)",
                        row["away"], row["home"], row["league"],
                        row["starts_kst"], url)
        if got.rows:
            break                 # 🔴 찾았으면 더 던지지 않는다(§19-b 예산)
    if not got.rows:
        from app.matchref import Reason as _R2
        got.reason = _R2.MATCH_NOT_FOUND
        got.why = (f"`{team}`"
                   + (f" vs `{opponent}`" if opponent else "")
                   + f" 의 {day} 경기 페이지를 못 찾았다 — 시도 "
                   + f"{len(got.tried)}건")
    return got


def _reader_for(url: str):
    """🔴 그 주소를 읽을 **어댑터**. 없으면 `None`(열지 않는다)."""
    for mod in READERS:
        if mod.is_match_page(url):
            return mod
    return None


def _mentions(name: str, want: str) -> bool:
    """🔴 팀 이름 대조는 `verify` 가 원본이다 — 여기서 규칙을 다시 쓰지 않는다."""
    from app import verify
    return verify.mentions_team(name, want, None)


async def find_and_store(pool, *, team: str, opponent: str = "",
                         day: date | None = None, league: str = "",
                         net: Net | None = None, search=None) -> Found:
    """찾아서 **`games` 표에 적는다.** 🔴 적는 SQL 은 `ingest` 가 원본이다.

    ⚠️ 한 행만 적지 않는다 — 여럿이면 전부 적는다. 고르는 것은 사용자 몫이고,
       표에 있으면 `slate.find` 가 그 목록을 보여 준다.
    """
    got = await find(team=team, opponent=opponent, day=day, league=league,
                     net=net, search=search)
    if not got.rows:
        return got
    from app.collect.ingest import _UPSERT_GAME
    for r in got.rows:
        gid = await pool.fetchval(
            _UPSERT_GAME, r["sport"], r["league"], r["ext_id"], r["home"],
            r["away"], r.get("venue"), r["starts_utc"], r["starts_kst"],
            r.get("starts_local"), r["status"], r.get("round_note"),
            r.get("home_score"), r.get("away_score"))
        if gid:
            got.ids.append(int(gid))
    logger.info("[findgame] %d경기를 슬레이트에 적었다 — id %s",
                len(got.ids), got.ids)
    return got
