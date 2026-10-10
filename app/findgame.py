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

#: 🔴🔴 §2 ④ — 못 찾았을 때 **시도한 출처를 몇 줄 보일까**. 숫자만 적지 않는다.
SHOW_TRIED = 8

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
               board_text: str = "") -> Found:
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **먼저 색인으로 찾는다 — 리그를 몰라도**(사용자 결정 2026-10-10 §2)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 리그 수동 선언·상한 방식을 **자동 등록으로 바꾼다.** … 모든 경기를 찾아
    #  > 분석까지 해야 한다.
    #
    #  🔴 사다리 ②③ 은 `app/core/discover.py` 다(팀 색인 → 팀 일정 · 리그 색인 →
    #     리그 일정 · 전부 robots 허용 경로). 🔴 **여기 아래의 검색 단이 ④** 다.
    #  ⚠️ 색인이 찾아도 **행은 같은 곳에서 만든다**(`reader.slate_row`) — 행 만드는
    #     길을 둘로 두면 한쪽만 고쳐진다(사본 금지).
    found = await _by_index(net, team=team, opponent=opponent, day=day,
                           league=league, got=got, board_text=board_text)
    if found is not None:
        got.rows.append(found)
        return got

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
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **같은 경기는 출처가 달라도 하나다**(지시 2026-10-09(4차) §1)
            # ══════════════════════════════════════════════════════════
            #
            #  ⚠️ 실사고 2026-10-09(가시마–감바): fotmob 이 `J. League` 로,
            #     ESPN 이 `jpn.1` 로 **같은 경기**를 줬고 경기 id 가 달라
            #     `seen_ids` 가 못 걸렀다 → 후보 2건 → `ambiguous` 로 멈췄다.
            #  🔴 같은 경기인지는 **두 팀과 킥오프 순간**이 말한다 — 대회 글자가
            #     아니다(글자는 출처마다 다르다 · 그래서 이 지시가 왔다).
            twin = _same_match(got.rows, row)
            if twin is not None:
                got.tried.append(
                    f"{url} 묶었다 — 같은 경기가 다른 출처로 왔다"
                    f"(`{twin.get('league')}` ↔ `{row.get('league')}`)")
                logger.info("[findgame] 같은 경기 묶음 — %s ↔ %s",
                            twin.get("league"), row.get("league"))
                continue
            got.rows.append(row)
            logger.info("[findgame] 찾았다 — %s @ %s · %s · %s KST (%s)",
                        row["away"], row["home"], row["league"],
                        row["starts_kst"], url)
        if got.rows:
            break                 # 🔴 찾았으면 더 던지지 않는다(§19-b 예산)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 §1-3 — **0개인데 보드가 있으면 보드로 경기를 만든다**
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 0개인데 보드가 있다 → 보드로 경기를 만든다(`source=user_board`):
    #  > 대회명은 **보드 표기 그대로**, 공식 일정 출처 **없음 표시**, 분석은
    #  > 그대로 진행.
    #
    #  🔴 터키컵·세리에D 처럼 fotmob 에 **자료가 없는** 경기가 이 길로 돈다
    #     (실측 2026-10-10: 그 둘은 팀 색인·리그 색인 어디에도 없다).
    if not got.rows and str(board_text or "").strip():
        row = _board_row(board_text, day=day)
        if row is not None:
            got.rows.append(row)
            got.tried.append(f"🟡 **보드로 경기를 만들었다**(`user_board`) — "
                             f"{row['home']} vs {row['away']} · "
                             f"`{row['league']}` · {row['starts_kst']} KST")
            logger.info("[findgame] 보드로 경기를 만들었다 — %s vs %s · %s",
                        row["home"], row["away"], row["league"])
    if not got.rows:
        from app.matchref import Reason as _R2
        got.reason = _R2.MATCH_NOT_FOUND
        # 🔴🔴 §2 ④ — **"못 찾음 — 시도한 출처·후보 3개"를 카드 대신** 보낸다.
        #    ⚠️ 전에는 *"시도 N건"* 숫자만 적었다 — 사용자가 **무엇을 돌았는지**
        #       보게 하라고 했다(#3 조용한 0 금지).
        got.why = (f"🔴 **못 찾음** — `{team}`"
                   + (f" vs `{opponent}`" if opponent else "")
                   + f" · {day} 창\n"
                   + "\n".join(f"· {x}" for x in got.tried[:SHOW_TRIED])
                   + (f"\n⚠️ 시도 {len(got.tried)}건 중 {SHOW_TRIED}건만 적었다"
                      if len(got.tried) > SHOW_TRIED else "")
                   # 🔴 §1-3 — **사용자에게 한 번 물어서라도 찾는다**
                   + "\n\n🙋 **보드 캡처나 날짜·시각·리그를 보내 달라** — "
                   + "그것으로 다시 찾는다(추측해서 다른 경기를 붙이지 않는다)")
    return got


def _board_row(board_text: str, *, day: date) -> dict | None:
    """🔴🔴 §1-3 — **보드 → 슬레이트 한 줄**(`source=user_board`). 못 만들면 `None`.

    🔴 **대회명은 보드 표기 그대로** 쓴다(사용자가 그렇게 적었다) — 우리가 리그를
       고르지 않는다. ⚠️ 그래서 기준 모델이 없고, 그 사실이 카드에 적힌다.
    🔴 킥오프는 보드의 날짜+시각을 **KST 로** 읽는다(사용자가 보는 시각이다) —
       절대규칙 2 대로 UTC 와 KST 를 **둘 다** 담는다.
    ⚠️ 시각이 없으면 **만들지 않는다** — 시각 없는 행은 `ingest._slate` 가 버리고,
       무엇보다 *"이미 시작했나"* 를 셀 수 없다.
    """
    from app.core import board as _b
    hint = _b.hint_of(board_text)
    if not (hint.has_match() and hint.hhmm):
        logger.info("[findgame] 보드로 경기를 못 만든다 — %s", hint.why)
        return None
    hh, mm = (int(x) for x in hint.hhmm.split(":"))
    when_kst = datetime(
        (hint.day or day).year, (hint.day or day).month, (hint.day or day).day,
        hh, mm, tzinfo=KST)
    return {
        "sport": "soccer",
        # 🔴 **보드 표기 그대로** — 대회를 우리가 고르지 않는다(§1-3)
        "league": hint.league or "보드(대회 표기 없음)",
        # 🔴 열쇠에 **출처를 적는다** — 카드·원장이 공식 일정이 아님을 안다
        "ext_id": f"user_board-{when_kst:%Y%m%d%H%M}-"
                  f"{_slug(hint.home)}-{_slug(hint.away)}",
        "home": hint.home, "away": hint.away, "venue": None,
        "starts_utc": when_kst.astimezone(timezone.utc),
        "starts_kst": when_kst, "starts_local": None,
        "status": "scheduled", "round_note": None,
        "home_score": None, "away_score": None,
        # 🔴 §1-3 — *"공식 일정 출처 없음 표시"*
        "source": "user_board",
        "source_note": f"🟡 **보드로 만든 경기** — 공식 일정 출처 없음 · {hint.why}",
    }


def _slug(said: str) -> str:
    """🔴 열쇠에 넣을 꼴 — 이름 정규화는 `discover.norm_name` 하나다(사본 금지)."""
    from app.core import discover
    return discover.norm_name(said)[:20] or "x"


def _reader_for(url: str):
    """🔴 그 주소를 읽을 **어댑터**. 없으면 `None`(열지 않는다)."""
    for mod in READERS:
        if mod.is_match_page(url):
            return mod
    return None


def _same_match(rows: list[dict], row: dict) -> dict | None:
    """🔴 이미 담은 줄 중 **같은 경기**가 있나 — 두 팀과 킥오프 순간으로 센다.

    ⚠️ 대회 글자로 세지 않는다 — 출처마다 다르다(`J. League` ↔ `jpn.1`).
    🔴 킥오프는 **분까지** 본다(출처가 초를 다르게 줄 수 있다).
    """
    def _sig(r: dict):
        pair = tuple(sorted(" ".join(str(r.get(k) or "").lower().split())
                            for k in ("home", "away")))
        when = str(r.get("starts_utc") or r.get("starts_kst") or "")[:16]
        return pair, when

    mine = _sig(row)
    if not all(mine[0]) or not mine[1]:
        return None            # ⚠️ 못 재는 줄은 **묶지 않는다**(#3)
    for got in rows:
        if _sig(got) == mine:
            return got
    return None


def _mentions(name: str, want: str) -> bool:
    """🔴 팀 이름 대조는 `verify` 가 원본이다 — 여기서 규칙을 다시 쓰지 않는다."""
    from app import verify
    return verify.mentions_team(name, want, None)


async def find_and_store(pool, *, team: str, opponent: str = "",
                         day: date | None = None, league: str = "",
                         net: Net | None = None, search=None,
                         board_text: str = "") -> Found:
    """찾아서 **`games` 표에 적는다.** 🔴 적는 SQL 은 `ingest` 가 원본이다.

    ⚠️ 한 행만 적지 않는다 — 여럿이면 전부 적는다. 고르는 것은 사용자 몫이고,
       표에 있으면 `slate.find` 가 그 목록을 보여 준다.
    """
    got = await find(team=team, opponent=opponent, day=day, league=league,
                     net=net, search=search, board_text=board_text)
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
    # 🔴 **중복을 지운다** — 실사고 2026-10-05: 같은 경기를 두 URL
    #    (`1b-vs-indonesia`·`thailand-vs-indonesia`)로 찾아 `id [117, 117]` 로
    #    적었다. DB 는 upsert 라 하나인데 **수가 거짓**이었다(#3).
    #    ⚠️ 순서를 지킨다(`dict.fromkeys`) — 첫 것이 호출부의 기본 선택이다.
    got.ids[:] = list(dict.fromkeys(got.ids))
    logger.info("[findgame] %d경기를 슬레이트에 적었다 — id %s",
                len(got.ids), got.ids)
    return got


async def _by_index(net, *, team: str, opponent: str, day: date,
                    got: Found, league: str = "",
                    board_text: str = "") -> dict | None:
    """🔴🔴 §2 ②③ — **색인으로 찾는다**. 찾으면 슬레이트 한 줄, 못 찾으면 `None`.

    🔴 자동 등록도 **여기서 건다**(§2 마지막 줄: *"경기를 찾으면 그 경기의 리그
       id로 자동 등록을 건다 — 이미 있으면 갱신만"*).
    ⚠️ 등록이 실패하면 **경기를 버리지 않는다** — 사유만 `tried` 에 적는다.
       (리그를 못 등록한 것과 경기를 못 찾은 것은 다른 일이다 · #3)
    """
    from app.core import discover
    try:
        out = await discover.find(net, home=team, away=opponent, day=None,
                                  league=league, board_text=board_text)
    except Exception as exc:                            # noqa: BLE001
        got.tried.append(f"색인 사다리가 죽었다(검색 단으로 간다) — {exc!r}")
        return None
    got.tried.extend(out.tried)
    if not out.match:
        got.tried.append("색인 사다리 ②③ 에 없다 — 검색 단(④)으로 간다")
        return None
    page_url = str(out.match.get("page") or "")
    if page_url.startswith("/"):
        page_url = fotmob.BASE + page_url
    if not fotmob.is_match_page(page_url):
        got.tried.append(f"색인이 준 주소가 경기 페이지가 아니다 — `{page_url}`")
        return None
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 §1-3 — **찾았는데 이미 시작했으면 그렇게 말한다**
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 이미 킥오프 지남 → *"이미 시작한 경기 — 예측 아님"*(등급 없음).
    #  > 결과가 나왔으면 결과를 보여 준다.
    #
    #  ⚠️ 종전에는 창 검사가 조용히 버려 *"못 찾았다"* 가 됐다 — 실측 2026-10-10
    #     (우니온–데펜사: 사다리가 **찾았는데** 18분 전에 킥오프했다). 🔴 찾은
    #     것과 못 찾은 것은 다른 말이다.
    said_when = str(out.match.get("utc") or "")
    if _started(said_when):
        from app.matchref import Reason as _R3
        got.reason = _R3.ALREADY_STARTED
        got.why = _started_line(out.match)
        got.tried.append(f"⏱ 이미 시작했다 — {said_when}")
        logger.info("[findgame] 찾았지만 이미 시작했다 — %s", got.why)
        return None
    page = await net.get(page_url)
    row = fotmob.slate_row(page, day=day) if page.ok else None
    if row is None:
        got.tried.append(f"{page_url} 슬레이트 행을 못 만들었다({page.reason})")
        return None
    # 🔴🔴 **리그 id 는 경기 페이지에서 읽는다** — 팀 일정은 글자만 준다.
    #    ⚠️ 실사고 2026-10-10: `tournament` 가 `"Serie B"` 글자라 `league_id` 가
    #       `None` 이었고, 자동 등록이 *"리그 id 를 못 받았다"* 로 실패했다.
    #       카드는 *"대회를 알아보지 못했다"* 를 띄웠다 — 등록이 안 됐으니 맞는
    #       말이었지만 **까닭이 로그에 없었다**(#3). 둘 다 고쳤다.
    j = fotmob.payload(page.text or "") or {}
    if not out.ccode:
        out.ccode = fotmob.ccode_of(j)
    if not out.league_id:
        said = fotmob.league_id_of(j)
        if said:
            out.league_id = said
            got.tried.append(f"리그 id 를 경기 페이지에서 읽었다 — `{said}`")
        else:
            got.tried.append("🔴 리그 id 를 경기 페이지도 안 준다 — 등록 못 한다")
    logger.info("[findgame] 색인으로 찾았다(%s) — %s @ %s · %s",
                out.rung, row["away"], row["home"], row["league"])
    # 🔴 §2 마지막 줄 — **리그 자동 등록**
    box, why = await _register(net, out)
    got.tried.append(f"자동 등록 — {why}")
    # 🔴 **사유를 로그에도 적는다** — 실사고 2026-10-10: 등록이 실패했는데
    #    `tried` 에만 있어서 로그를 봐도 **왜 실패했는지 안 보였다**(#3).
    logger.info("[findgame] 자동 등록 — %s", why)
    if box:
        row["auto_league"] = box.get("competition_key")
    return row


async def _register(net, out) -> tuple[dict, str]:
    """🔴 자동 등록을 건다 — **등록 규칙은 `core.discover.register` 가 원본**이다."""
    from app.core import discover
    try:
        return await discover.register(net, league_id=out.league_id,
                                       league_name=out.league_name,
                                       ccode=str(out.ccode or ""))
    except Exception as exc:                            # noqa: BLE001
        return {}, f"🔴 등록 중 죽었다 — {exc!r}"


def _started(utc: str) -> bool:
    """🔴 그 경기가 **이미 시작했나**. ⚠️ "지금"은 `window.now_utc` 하나다(§4)."""
    from app import window as _w
    if not str(utc or "").strip():
        return False
    try:
        when = datetime.fromisoformat(str(utc).replace("Z", "+00:00"))
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return _w.now_utc() >= when


def _started_line(match: dict) -> str:
    """🔴 §1-3 — *"이미 시작한 경기 — 예측 아님"* + **결과가 있으면 결과**."""
    said = (f"⏱ **이미 시작한 경기 — 예측 아님**(등급 없음) · "
            f"{match.get('home')} vs {match.get('away')}")
    try:
        when = datetime.fromisoformat(str(match.get("utc") or "")
                                      .replace("Z", "+00:00"))
        # 🔴 절대규칙 2 — **tz 없는 시각은 쓰지 않는다**(조용히 UTC 로 보지 않는다)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        said += f" · 킥오프 {timefmt.kst_label(when)}"
    except ValueError:
        pass
    # 🔴 결과가 왔으면 **그것을 보여 준다**(지시서가 그렇게 적었다)
    score = str(match.get("score") or match.get("scoreStr") or "").strip()
    if match.get("finished") and score:
        said += f"\n🏁 **결과** {score}"
    elif match.get("finished"):
        said += "\n🏁 **끝난 경기**다 — 스코어는 그 페이지가 안 줬다"
    else:
        said += "\n⏳ **진행 중**이다"
    return said
