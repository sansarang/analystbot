"""NPB — npb.jp. 🔴 **키 0건 · 검색 0건.**

§13-a: *"npb.jp 일정·予告先発, 스포츠나비 경기 페이지 예고 선발·試合中止 …
NPB 공시(登録・抹消)"*.

실측 2026-09-27:
  일정 표 `<tr id="date0927">` 5경기 · **양 팀 予告先発** (`先発：小笠原`)
  헤더 스코어 띠 — 진행 상태(`試合終了`·`5回表`)와 스코어
  등록 명단 `registered_<팀>.html` — **背番号와 포지션**이 있다(1b 재료)
  ⚠️ 일일 公示(登録・抹消) URL 은 **확인 못 했다** — 추측하지 않는다.
     `announcement_MMDD.html` 은 404 였다. 그 소스는 미확인으로 둔다.

robots.txt 자리에 HTML 을 준다 → robots 파일이 없다 = 제한 없음(`net` 이 그것을
판정한다). 우회가 아니라 확인이다.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone

from app import league, matchkey, rules, verify
from app.blackboard import Fact
from app.cells import Question, Source
from app.net import Fetched

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))
KST = JST                      # 같은 오프셋이지만 뜻이 다르다 — 둘 다 적는다

BASE = "https://npb.jp"
GAMES_IN_SEASON = 143

#: 🔴 이 어댑터가 맡는 종목. **상수로 밝힌다** — 행 안에만 적으면 "표에 어떤
#  종목이 있나"를 밖에서 못 읽는다(사용자 지시 2026-10-01: 다섯 종목을 쌓는다).
SPORT = "baseball"
#: 🔴 팀 약칭 → 정식명. 원본은 여기 하나다(일정 표는 약칭, 로고 title 은 정식명).
TEAMS = {
    "巨人": "読売ジャイアンツ", "ヤクルト": "東京ヤクルトスワローズ",
    "DeNA": "横浜DeNAベイスターズ", "広島": "広島東洋カープ",
    "阪神": "阪神タイガース", "中日": "中日ドラゴンズ",
    "ソフトバンク": "福岡ソフトバンクホークス", "日本ハム": "北海道日本ハムファイターズ",
    "オリックス": "オリックス・バファローズ", "楽天": "東北楽天ゴールデンイーグルス",
    "西武": "埼玉西武ライオンズ", "ロッテ": "千葉ロッテマリーンズ",
}
#: 등록 명단 페이지의 팀 코드.
ROSTER_CODE = {
    "福岡ソフトバンクホークス": "h", "北海道日本ハムファイターズ": "f",
    "オリックス・バファローズ": "b", "東北楽天ゴールデンイーグルス": "e",
    "埼玉西武ライオンズ": "l", "千葉ロッテマリーンズ": "m",
    "阪神タイガース": "t", "横浜DeNAベイスターズ": "db",
    "読売ジャイアンツ": "g", "中日ドラゴンズ": "d",
    "広島東洋カープ": "c", "東京ヤクルトスワローズ": "s",
}
#: 🔴 포지션 → 역할. §4 의 `line` 을 여기서 짓지 않는다 — 역할까지만.
ROLE = {"投手": "pitcher", "捕手": "batter", "内野手": "batter",
        "外野手": "batter"}

#: 진행 상태 표기 → 우리 규약. 🔴 사본 금지 — 읽는 쪽이 다시 적지 않는다.
STATE_FINAL = "試合終了"
STATE_CANCELLED = "中止"
_INNING = re.compile(r"\d+回[表裏]")


def schedule_url(year: int, month: int) -> str:
    return f"{BASE}/games/{year}/schedule_{month:02d}_detail.html"


def roster_url(year: int, team_full: str) -> str | None:
    code = ROSTER_CODE.get(team_full)
    return f"{BASE}/announcement/{year}/registered_{code}.html" if code else None


# ══════════════════════════════════════════════════════════════════
# STEP 0 슬레이트 + 予告先発
# ══════════════════════════════════════════════════════════════════

_ROW = re.compile(r'<tr id="date(\d{4})"[^>]*>(.*?)</tr>', re.S)
_DIV = r'<div class="{}">(.*?)</div>'


def parse_schedule(got: Fetched, day=None, *, year: int | None = None
                   ) -> list[dict]:
    """월간 일정 표 → 그 날짜의 경기 목록.

    🔴 **현지 시각(JST)과 KST 를 둘 다 만든다**(§2).
    🔴 予告先発이 비어 있으면 `None` 이다 — 지어내지 않는다.
    ⚠️ `(予備日)`·`中止` 는 경기가 아니다 — `postponed` 로 둔다.
    """
    if not got.ok:
        return []
    want = f"{day.month:02d}{day.day:02d}" if day else None
    year = year or (day.year if day else datetime.now(JST).year)
    out: list[dict] = []
    for mmdd, body in _ROW.findall(got.text):
        if want and mmdd != want:
            continue
        t1 = _one(body, "team1")
        t2 = _one(body, "team2")
        if not t1 or not t2:
            continue
        place = _one(body, "place")
        hhmm = _one(body, "time")
        cancel = _one(body, "cancel")
        pits = [_clean(p) for p in re.findall(_DIV.format("pit"), body, re.S)]
        # 🔴🔴 **날씨가 같은 칸에 있었다**(실측 2026-10-02 · `img alt`).
        #
        #  ⚠️ 사용자가 손으로 찾은 "확정 사실" 중 하나가 *"ZOZO마린 18:00, 흐리고
        #     한때 비"* 였다. 그 글자가 **우리가 이미 여는 페이지에** 있었고
        #     (`<div class="weather"><img alt="くもり時々雨">`) 파서가 버리고 있었다.
        #  🔴 `&nbsp;` 뿐이면 **없는 것이다** — 빈 문자열로 둔다(조용한 0 금지:
        #     "날씨가 맑다"와 "날씨를 안 적었다"는 다르다).
        weather = _weather_of(body)
        home, away = TEAMS.get(t1, t1), TEAMS.get(t2, t2)
        starts = None
        if hhmm and re.fullmatch(r"\d{1,2}:\d{2}", hhmm):
            hh, mm = (int(x) for x in hhmm.split(":"))
            starts = datetime(year, int(mmdd[:2]), int(mmdd[2:]), hh, mm,
                              tzinfo=JST)
        out.append({
            "sport": "baseball", "league": "NPB",
            # 🔴 §8-1 — `출처:경기ID`. ⚠️ npb 는 공식 경기 id 가 없어 **날짜+구단**으로
            #    짓는다(그 사실은 아래 주석이 적어 둔다) — 출처만 콜론으로 붙인다.
            "ext_id": "npb:" + f"{year}{mmdd}-{ROSTER_CODE.get(home, '?')}"
                      f"-{ROSTER_CODE.get(away, '?')}",
            "home": home, "away": away,
            "venue": place.replace("　", "") if place else None,
            "starts_local": starts, "starts_utc": starts.astimezone(
                timezone.utc) if starts else None,
            "starts_kst": starts.astimezone(KST) if starts else None,
            "status": "postponed" if cancel else "scheduled",
            "round_note": cancel or None,
            "probable": {
                "home": _pit(pits, 0), "away": _pit(pits, 1)},
            # 🔴 날씨 — 없으면 빈 문자열이고 그 사실이 그대로 올라간다
            "weather": weather,
            # 🔴 스코어 — 끝난 경기에만 있다(없으면 `None`)
            **_score_of(body),
        })
    logger.info("[npb] %s 일정 %d경기 · 예고 선발 양쪽 %d", want or "전체",
                len(out), sum(1 for r in out if all(r["probable"].values())))
    return out


def _pit(pits: list[str], i: int) -> dict | None:
    """🔴 **예고 선발만** 돌려준다.

    ⚠️ 실측 2026-10-02: 끝난 경기 칸에는 `勝：上沢`·`敗：ロング`·`分：石井`
       (승리/패전/무승부 투수)가 들어 있다. 종전 코드는 `先発` 접두만 떼고 나머지를
       그대로 이름으로 썼다 — 그러면 **지난 경기의 승리 투수가 오늘의 예고 선발로**
       저장된다. 접두가 `先発` 이 아니면 **예고가 아니다.**
    """
    if i >= len(pits):
        return None
    raw = (pits[i] or "").strip()
    if not raw:
        return None
    if re.match(r"^[勝敗分][:：]", raw):
        return None          # 🔴 결과 투수다 — 예고 선발이 아니다
    name = re.sub(r"^先発[:：]?", "", raw).strip()
    return {"name": name, "source": "npb.jp"} if name else None


def _weather_of(body: str) -> str:
    """`<div class="weather"><img alt="くもり時々雨">` → `"くもり時々雨"`.

    🔴 못 읽으면 **빈 문자열** — "날씨가 없다"를 "맑다"로 바꾸지 않는다.
    """
    m = re.search(_DIV.format("weather"), body, re.S)
    if not m:
        return ""
    alt = re.search(r'alt="([^"]*)"', m.group(1))
    return (alt.group(1).strip() if alt else "")


def _score_of(body: str) -> dict:
    """`<div class="score1">4</div>` → `{"home_score": 4, "away_score": 3}`.

    🔴 끝나지 않은 경기는 **`None`** 이다 — 0 으로 때우지 않는다.
    ⚠️ `team1` 이 홈이다(`parse_schedule` 이 그렇게 매핑한다) — `score1` 도 홈이다.
    """
    out: dict = {"home_score": None, "away_score": None}
    for key, cls in (("home_score", "score1"), ("away_score", "score2")):
        m = re.search(_DIV.format(cls), body, re.S)
        if not m:
            continue
        got = _clean(m.group(1))
        if got.isdigit():
            out[key] = int(got)
    return out


def _one(body: str, cls: str) -> str:
    m = re.search(_DIV.format(cls), body, re.S)
    return _clean(m.group(1)) if m else ""


def _clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+|&nbsp;", "", s).strip()


# ══════════════════════════════════════════════════════════════════
# 진행 상태 — 헤더 스코어 띠 (§2 중지·순연·진행중)
# ══════════════════════════════════════════════════════════════════

_BOX = re.compile(
    r'<a href="/scores/(\d{4})/(\d{4})/([a-z\-0-9]+)/".*?'
    r'alt="([^"]+)".*?alt="([^"]+)".*?'
    r'<div class="score">(.*?)</div>.*?<div class="state">(.*?)</div>', re.S)


def parse_live(got: Fetched, q: Question | None = None) -> list[Fact]:
    """헤더 스코어 띠 → 진행 상태·스코어.

    🔴 §19-d — 타 구장 라이브는 **판정에 걸린 경기만** 본다. 이 파서는 한 페이지
       에서 전 경기를 주므로 호출 한 번으로 끝난다.
    """
    if not got.ok:
        return []
    out: list[Fact] = []
    for year, mmdd, gid, t1, t2, score, state in _BOX.findall(got.text):
        st = _clean(state)
        score = _clean(score)
        status = ("final" if STATE_FINAL in st
                  else "postponed" if STATE_CANCELLED in st
                  else "inprogress" if _INNING.search(st) else "scheduled")
        out.append(Fact(
            question_id=f"live_score:npb-{year}{mmdd}-{gid}",
            value={"home": t1, "away": t2, "score": score or None,
                   "status": status, "state": st},
            hardness="hard", publisher="npb.jp",
            source=f"{BASE}/scores/{year}/{mmdd}/{gid}/", step=0))
    logger.info("[npb] 라이브 %d경기", len(out))
    return out


# ══════════════════════════════════════════════════════════════════
# 1b 선수 — 등록 명단 (背番号 + 포지션)
# ══════════════════════════════════════════════════════════════════

_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_TD = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)


#: 🔴 이 표지 **뒤**는 로스터가 아니다 — `選手登録公示以降の動き`(트레이드 전출·전입).
#   실측 2026-09-27: 표가 7개였고, 뒤 5개를 함께 읽어 등번호가 3건 겹쳤다
#   (#30·#39·#43 이 각각 다른 선수·다른 포지션). **그것이 내 결함이었다.**
MOVEMENT_MARK = "選手登録公示以降の動き"
#: 페이지가 스스로 적는 인원. `70名` 꼴 — 이것으로 자기검사한다(조용한 실패 금지).
#  ⚠️ 표기와 숫자 사이에 태그가 **여럿** 온다(`</h5>` + `<p class="right">`).
#     한 개만 허용하던 종전 정규식은 매치가 0이었고, 그래서 자기검사가 **조용히
#     죽어 있었다**(실측 2026-09-27 — 절단 픽스처가 그것을 잡았다).
_COUNT = re.compile(r"支配下選手一覧(?:\s|<[^>]*>)*?(\d+)\s*名")
_MOVE_IN = re.compile(r"(投\s*手|捕\s*手|内野手|外野手)\s*</[^>]*>\s*(?:<[^>]*>\s*)*"
                      r"([^<]+?)\s*</[^>]*>\s*(?:<[^>]*>\s*)*(←|→)")


def parse_roster(got: Fetched, team_full: str) -> tuple[list[dict], str]:
    """등록 명단 → `(players 행, 사유)`.

    🔴 **背番号가 있다** — 그래서 NPB 동명이인은 등번호로 갈린다(1b §7-3).
    🔴 **`MOVEMENT_MARK` 뒤는 읽지 않는다.** 그 뒤는 트레이드 이동 표이고,
       함께 읽으면 남의 팀 선수가 로스터에 섞인다(실측 3건).
    ⚠️ 표는 `[등록일, 포지션, 背番号, 이름]` 이다. 열 순서를 상수로 박지 않고
       **포지션 낱말로** 찾는다 — 순서가 바뀌면 조용히 어긋난다.
    ⚠️ 반환의 둘째 값은 **자기검사 결과**다. 페이지가 적은 인원과 다르면 그것을
       적어 돌려준다 — 조용히 넘기면 절반만 읽고도 성공처럼 보인다.
    """
    if not got.ok:
        return [], "열지 못했다"
    body = got.text.split(MOVEMENT_MARK)[0]
    out: list[dict] = []
    seen: set[str] = set()
    for tr in _TR.findall(body):
        cells = [_clean(c) for c in _TD.findall(tr)]
        if len(cells) < 2:
            continue
        pos = next((c for c in cells if c in ROLE), None)
        if not pos:
            continue
        i = cells.index(pos)
        if i + 2 >= len(cells):
            continue
        jersey, name = cells[i + 1], cells[i + 2]
        if not name or not re.fullmatch(r"\d{1,3}", jersey):
            continue
        if jersey in seen:
            continue                 # 같은 페이지에 같은 번호가 두 번 나오면 뒤를 버린다
        seen.add(jersey)
        out.append({"league": "NPB", "team": team_full, "jersey": jersey,
                    "name": name, "role": ROLE[pos]})

    said = _COUNT.search(got.text)
    note = ""
    if said and int(said.group(1)) != len(out):
        note = f"페이지는 {said.group(1)}명이라 적었는데 {len(out)}명을 읽었다"
        logger.warning("[npb] %s %s", team_full, note)
    logger.info("[npb] %s 등록 %d명%s", team_full, len(out),
                f" ⚠️ {note}" if note else "")
    return out, note


def parse_movement(got: Fetched, team_full: str) -> list[Fact]:
    """`選手登録公示以降の動き` → 이적(§4 basis `gone`).

    🔴 **전출(→)만 결장이다.** 전입(←)은 결장이 아니라 보강이다.
    """
    if not got.ok or MOVEMENT_MARK not in got.text:
        return []
    tail = got.text.split(MOVEMENT_MARK, 1)[1]
    out: list[Fact] = []
    for tr in _TR.findall(tail):
        cells = [_clean(c) for c in _TD.findall(tr)]
        if len(cells) < 3:
            continue
        pos = next((c for c in cells if c.replace(" ", "") in ROLE), None)
        arrow = next((c for c in cells if c in ("→", "←")), None)
        if not pos or arrow != "→":
            continue
        i = cells.index(pos)
        name = cells[i + 1] if i + 1 < len(cells) else ""
        if not name:
            continue
        out.append(Fact(question_id=f"absence:{team_full}",
                        value={"player_name": name, "basis": "gone",
                               "role": ROLE[pos.replace(" ", "")]},
                        hardness="hard", publisher="npb.jp", team=team_full,
                        step=2))
    logger.info("[npb] %s 전출 %d명", team_full, len(out))
    return out


# ══════════════════════════════════════════════════════════════════
# 세포가 쓸 소스 목록
# ══════════════════════════════════════════════════════════════════


def _slate_fact(got: Fetched, q: Question, day) -> list[Fact]:
    """🔴 파서는 `dict` 행을 낸다 — 세포 경계에서 `Fact` 로 감싼다(mlb 와 같다)."""
    rows = parse_schedule(got, day)
    if not rows:
        return []
    return [Fact(question_id=q.id, value=rows, hardness="hard",
                 publisher="npb.jp",
                 source=schedule_url(day.year, day.month), step=0)]


def sources_slate(day) -> list[Source]:
    return [Source("npb.jp 일정", "url",
                   url=schedule_url(day.year, day.month), tier=1,
                   parse=lambda got, q: _slate_fact(got, q, day))]


def sources_live(day) -> list[Source]:
    return [Source("npb.jp 스코어", "url",
                   url=schedule_url(day.year, day.month), tier=1,
                   parse=parse_live)]


# 🔴 `sources_roster` 는 두지 않는다 — `ingest.roster` 가 파서를 직접 부른다.
#    같은 일을 두 길로 두면 한쪽이 낡는다(안 이어진 코드는 없는 코드보다 나쁘다).

#: 🔴 일일 公示(登録・抹消) — **URL 미확인.** 추측해 붙이지 않는다.
#   `announcement_MMDD.html` 은 404(실측 2026-09-27). 이 칸이 비어 있는 동안
#   NPB 말소는 기사로만 잡힌다 → 검색 수단이 필요하다(갈림길).
KOJI_URL_UNKNOWN = ("npb.jp 일일 公示 URL 미확인 — "
                    "docs/fable/questions/2026-09-27_search_backend.md")


def sources_absence(year: int, team_full: str) -> list[Source]:
    """§4 결장 — `選手登録公示以降の動き`(전출). 🔴 `parse_movement` 의 호출부다.

    ⚠️ 로스터 페이지 **한 장**에 등록 명단과 이동 표가 같이 있다. 그래서 URL 은
       `roster_url` 과 같고 파서만 다르다 — 같은 페이지를 두 질문이 쓴다.
    🔴 공식 페이지(tier 1)이므로 `verify=False` 다. 발행 시각이 없어 fail-closed
       날짜 검증에 걸리지만, 그것은 검증기의 대상이 아니다(§12-c-5).
    """
    url = roster_url(year, team_full)
    if not url:
        return []
    return [Source(f"npb.jp 공시 이동({team_full})", "url", url=url, tier=1,
                   parse=lambda got, q: parse_movement(got, team_full))]


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **깊이 — 순위·홈/로드·맞대결** (사용자 지시 2026-10-02)
# ══════════════════════════════════════════════════════════════════
#
# > 깊이 어댑터는 수정해라...**변수 0건은 말이 안된다**
#
# 🔴 실측 2026-10-02(소프트뱅크–치바롯데): 사실 27건이 **전부 배경**이 됐다. 까닭은
#    `TYPES_OF_QTYPE` 가 `lineup`·`intent` 를 빈 tuple 로 두기 때문이고(설계상 맞다),
#    야구의 변수는 `:standings`·`:form`·`:h2h` 접미사에서 온다. 그 접미사를 만드는
#    **깊이 소스가 NPB 에 없었다**(`sources_context` 가 mlb·nhl 에만 있었다).
#
# ✅ **npb.jp 가 한 페이지에 다 들고 있었다**(실측으로 찾았다):
#      https://npb.jp/bis/{연}/stats/std_p.html   퍼시픽
#      https://npb.jp/bis/{연}/stats/std_c.html   센트럴
#    칸: 팀 · 試合 · 勝利 · 敗北 · 引分 · 勝率 · 差 · **ホーム 49-23** ·
#        **ロード 41-24** · **対ソ 14-11**(팀별 맞대결) · 交流戦
#
# ⚠️ **득점·실점이 없다.** 그래서 포아송 격자는 **못 만든다** — 무게가 §5-d 로
#    내려간다. 있는 척하지 않는다(`league_avg_goals` 칸을 비운다).

_STD = {"p": "パシフィック", "c": "セントラル"}
#: 🔴 순위표 머리글 → 우리 칸. **사본 금지** — 읽는 쪽이 다시 적지 않는다.
_COL = {"試合": "played", "勝利": "wins", "敗北": "losses", "引分": "draws"}


def standings_url(year: int, league: str = "p") -> str:
    """🔴 `p`(퍼시픽)·`c`(센트럴). 실측으로 찾은 주소다(`/standings/` 는 404)."""
    if league not in _STD:
        raise ValueError(f"모르는 리그 코드: {league!r} (있는 것: {sorted(_STD)})")
    return f"{BASE}/bis/{year}/stats/std_{league}.html"


def _rows_of(html: str) -> list[list[str]]:
    """표를 **머리글 포함** 줄 목록으로. 🔴 태그를 벗기고 공백만 정리한다."""
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", html or "", re.S):
        cells = [" ".join(re.sub(r"<[^>]+>", " ", c).split())
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
        if cells:
            out.append(cells)
    return out


def _wl(text: str) -> tuple[int, int] | None:
    """`"49-23"`·`"41-24 (3)"` → `(49, 23)`. 🔴 못 읽으면 `None`."""
    m = re.match(r"\s*(\d+)\s*-\s*(\d+)", str(text or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_standings(got, q: Question) -> list[Fact]:
    """순위표 → **우리 팀 줄** + 파생 측정. 🔴 축구·하키와 **같은 칸 이름**을 낸다.

    ⚠️ 야구 순위표에는 **득점·실점이 없다** → `goals_for`·`goals_against` 는 `None`,
       `league_avg_goals` 도 `None` 이다. 그러면 포아송 격자가 안 서고 무게가 §5-d 로
       내려간다 — 있는 척하지 않는다.
    """
    url = getattr(got, "url", "") or ""
    if "/stats/std_" not in url:
        return []
    rows = _rows_of(getattr(got, "text", "") or "")
    # 🔴🔴 **한 페이지에 표가 여럿이다**(勝敗表·交流戦·ファーム…). 실측 2026-10-02:
    #    `rows[0]` 을 머리글로 잡고 전부 몸통으로 세니 소프트뱅크가 **8위 18경기**로
    #    나왔다(실제 1위 140경기). → **머리글을 찾고, 그 표의 줄만** 센다.
    head_at = next((i for i, r in enumerate(rows)
                    if "ホーム" in r and "ロード" in r and "試合" in r), None)
    if head_at is None:
        return []
    head = rows[head_at]
    body = []
    for r in rows[head_at + 1:]:
        # 🔴 표가 끝나는 자리 — 칸 수가 줄거나 다음 머리글이 나온다
        if len(r) < len(head) - 2 or ("試合" in r and "ホーム" in r):
            break
        body.append(r)
    if not body:
        return []
    idx = {name: head.index(name) for name in _COL if name in head}
    i_home, i_road = head.index("ホーム"), head.index("ロード")
    team = (q.team or "").strip()
    homes, aways, allr = [], [], []
    mine = None
    for r in body:
        nm = r[0]
        row = {"team": nm, "table": None,
               "rank": body.index(r) + 1,
               **{v: _int(r[idx[k]]) for k, v in _COL.items() if k in idx},
               # 🔴 **득점·실점이 없다** — 0 으로 때우지 않는다
               "goals_for": None, "goals_against": None, "goal_diff": None,
               "points": None}
        allr.append(row)
        for side, i in (("home", i_home), ("away", i_road)):
            wl = _wl(r[i])
            if wl is None:
                continue
            (homes if side == "home" else aways).append(
                {"team": nm, "played": wl[0] + wl[1], "wins": wl[0],
                 "losses": wl[1], "draws": None,
                 "goals_for": None, "goals_against": None, "goal_diff": None})
        if team and verify.mentions_team(nm, team, q.local):
            mine = row
    if mine is None:
        return []
    val = dict(mine)
    val["league_tables"] = 1
    # 🔴 **홈 우위는 승률로만** 잰다(득점이 없다). `league.home_advantage` 가 그 꼴을
    #    이미 받아들인다 — `goals_delta` 는 `None` 이 된다.
    val["home_advantage"] = league.home_advantage(homes, aways)
    val["league_avg_goals"] = None
    val["total_baseline"] = None
    val["open_game_threshold"] = None
    val["venue_averages"] = None
    val["venue_rows"] = None
    val.update(_cut_npb())
    # 🔴 맞대결 칸(`対ソ` …)이 **있다는 사실**을 남긴다 — 아직 안 뽑는다
    val["h2h_columns"] = [h for h in head if h.startswith("対")]
    when = _std_as_of(got)
    out = [Fact(
        question_id=f"{q.id}:standings", value=val, hardness="soft",
        source=url, publisher="npb.jp", published_at=when,
        article_title=f"{mine['team']} 순위", tier=verify.TIER_OFFICIAL,
        extracted_by="rule:npb_standings", step=1, team=mine["team"])]
    # 🔴🔴 **맞대결이 같은 표에 있다**(`対ロ 16-6`). 사용자 지시 2026-10-02:
    #    *"변수 0건은 말이 안된다"*. 칸이 있는데 안 뽑는 것이 그 0건의 한 까닭이었다.
    #  ⚠️ **경기별 기록이 아니라 누적 승패**다 — 그 꼴을 그대로 적고, `_dir_h2h` 가
    #     누적 꼴을 받아들인다. 지어내 경기 목록을 만들지 않는다.
    h2h = _h2h_of(head, mine_row := [r for r in body if r[0] == mine["team"]][0],
                  q.opponent or "")
    if h2h:
        out.append(Fact(
            question_id=f"{q.id}:h2h", value=h2h, hardness="soft",
            source=url, publisher="npb.jp", published_at=when,
            article_title=f"{mine['team']} 맞대결", tier=verify.TIER_OFFICIAL,
            extracted_by="rule:npb_h2h", step=1, team=mine["team"]))
    return out


def _h2h_of(head: list[str], row: list[str], opponent: str) -> dict | None:
    """우리 팀 줄에서 **상대 칸**을 찾는다(`対ロ 16-6`). 🔴 못 찾으면 `None`.

    ⚠️ 머리글이 **약칭 한두 자**다(`対ソ`·`対ロ`). 정식명과 맞추려면 `TEAMS` 표를
       거쳐야 한다 — 그 표가 원본이고 여기서 약칭을 다시 적지 않는다.
    """
    if not opponent:
        return None
    short = next((k for k, full in TEAMS.items() if full == opponent), "")
    if not short:
        return None
    # 🔴 `対ソ` 는 `ソフトバンク` 의 **첫 글자**다. 머리글에서 그 꼴을 찾는다
    col = next((h for h in head
                if h.startswith("対") and short.startswith(h[1:])), "")
    if not col:
        return None
    wl = _wl(row[head.index(col)])
    if wl is None:
        return None
    w, lo = wl
    return {"h2h_wins": w, "h2h_losses": lo, "h2h_games": w + lo,
            "h2h_opponent": opponent, "column": col,
            # 🔴 **경기별 기록이 아니다** — 읽는 쪽이 그것을 알아야 한다
            "shape": "aggregate", "note": "npb.jp 순위표의 팀별 맞대결 누적 승패"}


def _int(text) -> int | None:
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return None


def _std_as_of(got):
    """🔴 순위표가 **"언제"의 표인가** — 페이지가 `2026年10月1日 現在` 로 적어 둔다.

    ⚠️ 못 읽으면 `None` 이고 날짜 없는 자료가 된다(지어내지 않는다).
    """
    t = " ".join(re.sub(r"<[^>]+>", " ", getattr(got, "text", "") or "").split())
    m = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日\s*現在", t)
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    return datetime(y, mo, d, tzinfo=JST)


def _cut_npb() -> dict:
    """🔴 NPB 의 **클라이맥스 시리즈 경계**. 규정은 선언이 원본이다."""
    cfg = rules.playoff_cut("NPB")
    if cfg.get("unknown"):
        return {"cut_lines": None, "playoff_cut": None,
                "cut_reason": cfg["unknown"]}
    top = cfg.get("division_top")
    if top is None:
        return {"cut_lines": None, "playoff_cut": None,
                "cut_reason": "NPB 경계 선언이 없다"}
    return {"cut_lines": {f"상위 {top}": int(top)}, "playoff_cut": int(top),
            "cut_reason": f"{cfg.get('rule')} (출처 {cfg.get('source')})"}


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 장소별 득점 — **월간 일정의 스코어로 쌓는다** (실측 2026-10-02)
# ══════════════════════════════════════════════════════════════════
#
# 🔴 왜 이 함수가 생겼나: 포아송 격자가 **야구에서 한 번도 선 적이 없다.** 그래서
#    시나리오가 템플릿 둘(홈·거울상)뿐이고, 생존이 `0.0/0.5/1.0` 세 값만 가능해
#    §6-b 가 이름을 적을 수 있는 자리(1.0)가 거의 안 나왔다.
#    사용자가 손으로 한 분석은 시나리오 **다섯**이었고 승 생존 **0.85** 였다.
#
# ⚠️ 어디서 구하나를 세 곳 실측으로 가렸다:
#      `std_p.html`  순위표      → ホーム/ロード **승패만**, 득점 없음
#      `tmb_p/tmp_p` 팀 성적표   → 得点·失点 있으나 **시즌 합계**(장소 안 갈림)
#      월간 일정                  → ✅ **모든 경기 스코어**(`score1`/`score2`)
# 🔴 그래서 일정을 읽는다 — **지어내지 않고** 장소별로 갈린 실제 득점이 나온다.


def runs_url(year: int, month: int) -> str:
    """🔴 득점 자료의 원본은 **일정 페이지와 같다** — 주소를 두 번 적지 않는다."""
    return schedule_url(year, month)


def parse_month_runs(got, q: Question) -> list[Fact]:
    """월간 일정 → **팀별 홈/원정 득점·실점 한 달치.**

    🔴 끝난 경기만 센다(`home_score` 가 `None` 이면 아직 안 끝났다).
    🔴 중지·순연은 세지 않는다 — 스코어가 없으므로 자연히 빠진다.
    ⚠️ 한 달치다. 여러 달을 합치는 것은 `analyze.context` 몫이다(세포는 사실만 낸다).
    """
    if not getattr(got, "ok", False):
        return []
    url = getattr(got, "url", "") or ""
    m = re.search(r"/games/(\d{4})/schedule_(\d{2})_detail", url)
    if not m:
        return []
    year, month = int(m.group(1)), int(m.group(2))
    rows = parse_schedule(got, year=year)
    home: dict[str, dict] = {}
    away: dict[str, dict] = {}
    n = 0
    for r in rows:
        hs, as_ = r.get("home_score"), r.get("away_score")
        if hs is None or as_ is None:
            continue
        n += 1
        for side, team, mine, theirs in (("home", r["home"], hs, as_),
                                         ("away", r["away"], as_, hs)):
            box = home if side == "home" else away
            cur = box.setdefault(team, {"team": team, "played": 0,
                                        "wins": None, "losses": None,
                                        "draws": None, "goals_for": 0,
                                        "goals_against": 0, "goal_diff": 0})
            cur["played"] += 1
            cur["goals_for"] += int(mine)
            cur["goals_against"] += int(theirs)
            cur["goal_diff"] = cur["goals_for"] - cur["goals_against"]
    if not n:
        return []
    val = {"month": f"{year}-{month:02d}", "games": n,
           "venue_rows_part": {"home": list(home.values()),
                               "away": list(away.values())}}
    # 🔴🔴 **달마다 다른 칸에 쓴다.** 같은 칸에 넣으면 블랙보드가 서로 다른 값을
    #    *모순*으로 읽는다(`reconcile`) — 8월과 9월 득점은 모순이 아니라 **둘 다
    #    사실**이다. ⚠️ 접미사는 **마지막 조각**이라 `:runs_month` 그대로 남는다
    #    (유형 판정이 그것으로 돈다).
    return [Fact(question_id=f"{q.id}:{year}-{month:02d}:runs_month",
                 value=val, hardness="hard",
                 source=url, publisher="npb.jp",
                 published_at=datetime(year, month, 1, tzinfo=JST),
                 article_title=f"{year}-{month:02d} 월간 스코어",
                 tier=verify.TIER_OFFICIAL, extracted_by="rule:npb_month_runs",
                 step=1)]


def pitchers_url(year: int, league: str = "p") -> str:
    """🔴 **투수 성적표**(규정 투구 이닝 도달 투수). 방어율이 여기 있다.

    ⚠️ 실측 2026-10-02: 개인 성적표가 `idp1_p.html`·`era_p.html` 이 아니라
       `pit_p.html` 이다(앞의 둘은 404). 추측으로 붙이지 않고 받아서 확인했다.
    ⚠️ **규정 미달 투수는 이 표에 없다** — 전前田悠伍(12승 1패)가 없었다. 그러면
       `pitcher_state` 는 미결정이고, 그 사실이 사유로 남는다(지어내지 않는다).
    """
    code = "p" if str(league).lower().startswith("p") else "c"
    return f"{BASE}/bis/{year}/stats/pit_{code}.html"


def parse_pitchers(got, q: Question) -> list[Fact]:
    """투수 성적표 → `{이름: {era, wins, losses}}` 한 묶음.

    🔴 **표 하나를 사실 하나로** 낸다 — 투수마다 사실을 내면 수십 건이 블랙보드에
       쌓이고 그중 둘만 쓴다. 이어 붙이는 것은 `classify._fill_pitchers` 다.
    """
    if not getattr(got, "ok", False):
        return []
    url = getattr(got, "url", "") or ""
    if "/stats/pit_" not in url:
        return []
    rows = _rows_of(getattr(got, "text", "") or "")
    head_at = next((i for i, r in enumerate(rows)
                    if "投手" in r and "防御率" in r), None)
    if head_at is None:
        return []
    head = rows[head_at]
    i_name, i_era = head.index("投手"), head.index("防御率")
    i_w = head.index("勝利") if "勝利" in head else None
    i_l = head.index("敗北") if "敗北" in head else None
    # 🔴 **기대 이닝의 재료**(딥서치 2026-10-03 · A): 投球回 ÷ 登板.
    #    ⚠️ 지어낸 수가 아니다 — 그 투수가 **실제로** 등판당 던진 이닝이다.
    i_g = head.index("登板") if "登板" in head else None
    i_ip = head.index("投球回") if "投球回" in head else None
    table: dict[str, dict] = {}
    for r in rows[head_at + 1:]:
        if len(r) <= max(i_name, i_era):
            continue
        # 🔴 이름 칸은 `レイエス(日)` 꼴 — 괄호 안이 팀 약칭이다
        raw = r[i_name]
        name = re.sub(r"[(（][^)）]*[)）]", "", raw).strip()
        team_mark = re.search(r"[(（]([^)）]*)[)）]", raw)
        era = _float(r[i_era])
        if not name or era is None:
            continue
        games = _int(r[i_g]) if i_g is not None and len(r) > i_g else None
        ip = _ip(r[i_ip]) if i_ip is not None and len(r) > i_ip else None
        table[name] = {
            "era": era, "team_mark": team_mark.group(1) if team_mark else "",
            "wins": _int(r[i_w]) if i_w is not None and len(r) > i_w else None,
            "losses": _int(r[i_l]) if i_l is not None and len(r) > i_l else None,
            "games": games, "innings": ip,
            # 🔴 **등판당 이닝** — 못 구하면 `None`(0 으로 때우지 않는다)
            "innings_per_game": round(ip / games, 2)
            if (ip is not None and games) else None}
    if not table:
        return []
    # 🔴 리그(퍼시픽·센트럴)마다 다른 칸 — 같은 칸이면 두 표가 모순으로 읽힌다
    code = "p" if "/pit_p" in url else "c"
    return [Fact(question_id=f"{q.id}:{code}:pitcher_table",
                 value={"pitchers": table, "source_table": url},
                 hardness="hard", source=url, publisher="npb.jp",
                 published_at=_std_as_of(got),
                 article_title="투수 성적", tier=verify.TIER_OFFICIAL,
                 extracted_by="rule:npb_pitchers", step=1)]


def _ip(text) -> float | None:
    """투구 이닝 표기 → 소수. 🔴 **`139.1` 은 139와 1/3이닝이다**(야구 표기).

    ⚠️ 그대로 `float` 로 읽으면 `139.1` 이 되어 **1/3 이닝이 0.1 로** 들어간다.
       작은 차이지만 기대 이닝(÷등판)에 그대로 실린다.
    🔴 소수 자리가 `1`·`2` 가 아니면 보통 소수로 본다(표기가 섞이는 판이 있다).
    """
    # 🔴 **셀 안의 공백을 먼저 지운다**(실측 2026-10-03). npb.jp 는 이닝을
    #    `1264 .2`·`166 .1` 로 낸다(정수와 분수 조각이 따로 그려진다). 공백을 두면
    #    아래 패턴이 전부 빗나가고 **기대 이닝이 통째로 `None`** 이 된다.
    s = re.sub(r"\s+", "", str(text or ""))
    m = re.fullmatch(r"(\d+)(?:[.](\d))?", s)
    if not m:
        return _float(s)
    whole = float(m.group(1))
    third = m.group(2)
    if third in ("1", "2"):
        return round(whole + int(third) / 3.0, 3)
    return _float(s)


def _float(text) -> float | None:
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return None


def team_pitching_url(year: int, league: str = "p") -> str:
    """🔴 **팀 투수 성적표** — 팀 ERA 가 여기 있다(남은 이닝의 기준).

    ⚠️ 실측 2026-10-02: `tmp_{p,c}.html` 이다(`tmb_` 는 타격표다).
    """
    code = "p" if str(league).lower().startswith("p") else "c"
    return f"{BASE}/bis/{year}/stats/tmp_{code}.html"


def parse_team_pitching(got, q: Question) -> list[Fact]:
    """팀 투수 성적표 → `{팀: {era, innings, games}}` 한 묶음.

    🔴 `league.starter_factor` 의 **분모**다 — 선발 ERA 를 팀 ERA 로 나눈다.
       그래서 선발이 평범하면 배수가 정확히 1 이 되고 모형을 건드리지 않는다.
    """
    if not getattr(got, "ok", False):
        return []
    url = getattr(got, "url", "") or ""
    if "/stats/tmp_" not in url:
        return []
    rows = _rows_of(getattr(got, "text", "") or "")
    head_at = next((i for i, r in enumerate(rows)
                    if "チーム" in r and "防御率" in r), None)
    if head_at is None:
        return []
    head = rows[head_at]
    i_t, i_era = head.index("チーム"), head.index("防御率")
    i_ip = head.index("投球回") if "投球回" in head else None
    i_g = head.index("試合") if "試合" in head else None
    out: dict[str, dict] = {}
    for r in rows[head_at + 1:]:
        if len(r) <= max(i_t, i_era):
            continue
        name = (r[i_t] or "").strip()
        era = _float(r[i_era])
        if not name or era is None:
            continue
        out[name] = {
            "era": era,
            "innings": _ip(r[i_ip]) if i_ip is not None and len(r) > i_ip else None,
            "games": _int(r[i_g]) if i_g is not None and len(r) > i_g else None}
    if not out:
        return []
    return [Fact(question_id=f"{q.id}:team_pitching",
                 value={"teams": out, "source_table": url},
                 hardness="hard", source=url, publisher="npb.jp",
                 published_at=_std_as_of(got),
                 article_title="팀 투수 성적", tier=verify.TIER_OFFICIAL,
                 extracted_by="rule:npb_team_pitching", step=1)]


def roster_ids_url(team_full: str) -> str | None:
    """🔴 **등록 명단 — 선수 페이지 주소가 여기 있다.**

    ⚠️ `roster_url`(공시) 과 다른 페이지다: 이쪽은 `/bis/teams/rst_{코드}.html` 이고
       선수 이름마다 `/bis/players/{번호}.html` 링크를 들고 있다.
    """
    code = ROSTER_CODE.get(team_full)
    return f"{BASE}/bis/teams/rst_{code}.html" if code else None


_PLAYER_LINK = re.compile(
    r'<a href="(/bis/players/\d+\.html)"[^>]*>([^<]+)</a>')


def parse_roster_ids(got, q: Question) -> list[Fact]:
    """등록 명단 → `player_pages: {선수 이름: 주소}` + `players: [이름…]`.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **칸을 갈랐다** — v5 §8-3 (실측 2026-10-04 · NPB 가 크래시했다)
    ══════════════════════════════════════════════════════════════════

    종전은 `players` 에 **dict**(이름 → 주소)를 넣었다. 🔴 그런데 `players` 는
    저장소 전체에서 **이름 목록**이다 — fotmob·MLB 어댑터가 목록을 넣고,
    카드가 `v["players"][:11]` 로 열한 명을 찍고, `classify` 가 XI 비교에 쓴다.

    ```
    File "app/analyze.py", line 856, in roster_of
        for nm in (val.get("squad") or []) + (val.get("players") or []):
    TypeError: can only concatenate list (not "dict") to list
    ```

    ⚠️ **`gather` 입구**라 경기 전체가 죽었다(게이트2 2판 NPB `exit 1`).
    🔴 사용자 결정 2026-10-04: *"어댑터 고유 모양(dict)은 **어댑터 안에서 list
       로 바꾸고 밖으로 내지 않는다.** `roster_of` 입력은 `list[str]` 만 받는다."*

    → 주소 표는 **`player_pages`** 라는 **이 어댑터만의 칸**으로 옮기고,
      공유 칸 `players` 에는 **이름 목록**을 넣는다.

    🔴 **선발 ERA 로 가는 길이다**(딥서치 2026-10-03 · A). 리더보드(`pit_*`)에는
       **규정 투구 이닝에 도달한 투수만** 실린다 — 실측 2026-10-03: 唐川·松本晴
       둘 다 없었고, 그러면 선발 보정이 영영 안 걸린다.
    ⚠️ 이 사실만으로는 ERA 를 모른다 — `sources_followup` 이 그 페이지를 한 번 더 연다.
    """
    if not getattr(got, "ok", False):
        return []
    url = getattr(got, "url", "") or ""
    if "/teams/rst_" not in url:
        return []
    ids = {}
    for href, name in _PLAYER_LINK.findall(getattr(got, "text", "") or ""):
        nm = " ".join(_clean(name).split())
        if nm:
            ids[nm] = BASE + href
    if not ids:
        return []
    return [Fact(question_id=f"{q.id}:roster_ids",
                 # 🔴 `player_pages` 는 **이 어댑터만** 읽는다(주소 표).
                 #    `players` 는 **공유 칸**이므로 `list[str]` 이다(§8-3).
                 value={"player_pages": ids, "players": sorted(ids),
                        "source_table": url},
                 hardness="hard", source=url, publisher="npb.jp",
                 published_at=None, article_title="등록 명단",
                 tier=verify.TIER_OFFICIAL, extracted_by="rule:npb_roster_ids",
                 step=1)]


def parse_player_pitching(got, q: Question) -> list[Fact]:
    """선수 페이지 → **그 해의 투수 성적**(ERA·등판·이닝).

    ══════════════════════════════════════════════════════════════════
    🔴 이 표는 **칸이 머리글보다 하나 많다**(실측 2026-10-03)
    ══════════════════════════════════════════════════════════════════

    npb.jp 는 `投球回` 를 **두 칸**으로 그린다 — 정수와 분수(⅓·⅔)를 따로 둔다.

    ```
    머리글 24칸 … 打者 投球回 安打 … 自責点 防御率
    몸통  26칸 … 21   5  ''  5    …  4     7.20   ''
                        └┬┘
                      두 칸이다
    ```

    🔴 그래서 **머리글 자리로 바로 읽으면 한 칸씩 밀린다** — 전 판이 그래서
       `防御率` 자리에서 **자책점 `4`** 를 읽었다(그리고 `_float` 가 4.0 을 냈다).
    ⚠️ `_rows_of` 도 쓸 수 없다 — 이 페이지에서는 한 논리 줄을 **두 `<tr>`** 로
       쪼개 돌려준다(15칸 + 나머지). 그래서 **평평한 칸 목록**으로 읽는다.
    """
    if not getattr(got, "ok", False):
        return []
    url = getattr(got, "url", "") or ""
    if "/bis/players/" not in url:
        return []
    html = getattr(got, "text", "") or ""
    cells = [" ".join(re.sub(r"<[^>]+>", " ", c).split())
             for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", html, re.S)]
    # 🔴 머리글을 **이름으로** 찾는다 — 자리를 세어 박지 않는다
    want_head = ("年度", "登板", "投球回", "防御率")
    start = None
    for i in range(len(cells)):
        if cells[i] == "年度" and all(
                w in cells[i:i + 30] for w in want_head):
            start = i
            break
    if start is None:
        return []
    head: list[str] = []
    for c in cells[start:]:
        if head and c == "年度":
            break
        head.append(c)
        if c == "防御率":
            break
    if "防御率" not in head:
        return []
    k = head.index("投球回")
    season = str((q.deadline or datetime.now(JST)).astimezone(JST).year)
    body = cells[start + len(head):]
    at = next((i for i, c in enumerate(body) if c == season), None)
    if at is None:
        return []
    # 🔴 **칸이 하나 더 많다** — `投球回` 가 두 칸이므로 그 뒤를 한 칸 밀어 읽는다
    row = body[at:at + len(head) + 1]
    if len(row) < len(head):
        return []

    def _at(name: str) -> str:
        j = head.index(name)
        return row[j + 1] if j > k else row[j]

    era = _float(_at("防御率"))
    games = _int(_at("登板"))
    # 🔴 이닝은 **두 칸을 합친다**(정수 + 분수). 분수 칸이 비면 0이다.
    #  ⚠️ 분수 칸이 `.1` 꼴로 **점을 달고** 온다(실측 2026-10-03: 松本晴 `117` + `.1`).
    #     그대로 이으면 `117..1` 이 되어 이닝이 통째로 `None` 이 된다.
    whole = re.sub(r"\s+", "", row[k])
    frac = re.sub(r"[^0-9]", "", row[k + 1] if len(row) > k + 1 else "")
    ip = _ip(f"{whole}.{frac}" if frac else whole)
    if era is None:
        return []
    name = _player_name(html)
    return [Fact(question_id=f"{q.id}:starter_stats",
                 value={"player": name, "era": era, "games": games,
                        "innings": ip, "season": season,
                        "innings_per_game": round(ip / games, 2)
                        if (ip is not None and games) else None},
                 hardness="hard", source=url, publisher="npb.jp",
                 published_at=None, article_title=f"{name} 성적",
                 tier=verify.TIER_OFFICIAL,
                 extracted_by="rule:npb_player_pitching", step=1)]


def _player_name(html: str) -> str:
    """선수 페이지의 이름. 🔴 못 읽으면 빈 문자열(지어내지 않는다).

    ⚠️ 실측 2026-10-03: `id="pc_v_name"` 선택자는 **등번호 `19`** 를 집었다.
       제목이 정확하다 — `唐川　侑己（千葉ロッテマリーンズ）| 個人年度別成績 | …`.
       🔴 전각 공백(`　`)이 들어 있어 `split()` 으로 지운다.
    """
    m = re.search(r"<title>([^<|（(]+)", html)
    if not m:
        return ""
    return "".join(_clean(m.group(1)).split())


def sources_followup(facts: list, ext_id: str) -> list[Source]:
    """🔴🔴 **한 바퀴 더** — 이미 모은 사실이 **다음 주소를 가리킨다**(§19-c).

    ══════════════════════════════════════════════════════════════════
    🔴 왜 두 바퀴인가 (실측 2026-10-03)
    ══════════════════════════════════════════════════════════════════

    선발 보정(딥서치 · A)은 **선발의 ERA** 를 요구한다. 그런데:

    - 리더보드(`pit_*`)에는 **규정 투구 투수만** 있다 → 唐川·松本晴 둘 다 없었다.
    - 선수 페이지에는 있다(唐川 2026 ERA **7.20**).
    - 🔴 그 페이지 **주소**는 등록 명단에 있고, **누가 선발인지**는 일정 페이지에 있다.

    즉 주소를 알려면 **두 사실을 먼저** 가져야 한다. `Source.follow` 는 자기가 연
    페이지만 보므로(그리고 §19-c 는 2단을 금지한다) 이 자리가 필요하다.

    ⚠️ **한 바퀴뿐이다** — 이 함수의 결과에 다시 `sources_followup` 을 걸지 않는다.
    🔴 선발을 못 찾으면 **빈 목록**이고, 그러면 보정이 안 걸리고 사유가 카드에 남는다.
    """
    # 🔴 §8-1 — `matchkey.mine` 이 *"내 것이냐"* 를 답한다(`npb:…` 도 읽는다)
    if not matchkey.mine(ext_id, "npb"):
        return []
    ids: dict[str, str] = {}
    want: list[str] = []
    for f in facts:
        v = f.value if isinstance(f.value, dict) else {}
        qid = str(getattr(f, "question_id", ""))
        if qid.endswith(":roster_ids"):
            # 🔴 주소 표는 이제 `player_pages` 다(`players` 는 이름 목록)
            ids.update(v.get("player_pages") or {})
        elif qid.endswith(":starter"):
            for key in ("player", "opponent_player"):
                nm = " ".join(str(v.get(key) or "").split())
                if nm and nm not in want:
                    want.append(nm)
    if not (ids and want):
        return []
    out: list[Source] = []
    seen: set[str] = set()
    for nm in want:
        # 🔴 **성만 아는 판이 있다**(`先発：田中`). 명단에는 성명이 있다 —
        #    성으로 시작하는 이름이 **하나일 때만** 쓴다(여럿이면 누구인지 모른다).
        hit = ids.get(nm)
        if hit is None:
            cand = [u for k, u in ids.items()
                    if k.replace(" ", "").startswith(nm.replace(" ", ""))]
            if len(cand) != 1:
                logger.info("[npb] 선발 `%s` 를 명단에서 못 특정했다 — 후보 %d명",
                            nm, len(cand))
                continue
            hit = cand[0]
        if hit in seen:
            continue
        seen.add(hit)
        out.append(Source(f"npb.jp 선발 성적({nm})", "url", url=hit,
                          tier=verify.TIER_OFFICIAL,
                          parse=parse_player_pitching))
    return out


def parse_game_context(got, q: Question) -> list[Fact]:
    """월간 일정에서 **이 경기 한 줄**을 찾아 예고 선발·날씨를 낸다.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 이 파서가 생겼나 (실측 2026-10-02)
    ══════════════════════════════════════════════════════════════════

    사람이 손으로 쓴 분석의 **확정 사실 두 줄**이 이 페이지에 있었다:
        선발  `先発：田中` · `先発：前田悠`
        날씨  `<div class="weather"><img alt="くもり時々雨">`
    🔴 그런데 DB `starters` 표는 **NPB 가 0줄**이었고(14줄 전부 MLB) 날씨는 파서가
       버리고 있었다. 즉 **이미 여는 페이지에서 두 사실을 흘리고 있었다.**

    ⚠️ 수집 경로(`ingest._slate`)와 **같은 파서를 쓴다**(`parse_schedule`) — 사본
       금지. 이 함수는 그 결과에서 *우리 경기 한 줄*을 고르고 사실로 감싸는 일만 한다.
    """
    if not getattr(got, "ok", False):
        return []
    team = (q.team or "").strip()
    rows = parse_schedule(got)
    mine = None
    for r in rows:
        if not (verify.mentions_team(r["home"], team, q.local)
                or verify.mentions_team(r["away"], team, q.local)):
            continue
        # 🔴 **그 날짜여야 한다** — 월간 표에는 한 팀의 경기가 여러 줄 있다
        if q.deadline is not None and r.get("starts_local") is not None:
            if r["starts_local"].date() != q.deadline.astimezone(JST).date():
                continue
        mine = r
        break
    if mine is None:
        return []
    side = "home" if verify.mentions_team(mine["home"], team, q.local) else "away"
    other = "away" if side == "home" else "home"
    when = mine.get("starts_utc")
    out: list[Fact] = []
    pit = (mine.get("probable") or {}).get(side)
    opp = (mine.get("probable") or {}).get(other)
    if pit and pit.get("name"):
        out.append(Fact(
            question_id=f"{q.id}:starter",
            value={"team": mine[side], "player": pit["name"],
                   "opponent_team": mine[other],
                   "opponent_player": (opp or {}).get("name"),
                   # 🔴 방어율은 **여기 없다** — `pitcher_table` 과 이어 붙인다
                   "era": None, "opponent_era": None},
            hardness="hard", source=getattr(got, "url", ""),
            publisher="npb.jp", published_at=when,
            article_title=f"{mine[side]} 예고 선발", tier=verify.TIER_OFFICIAL,
            extracted_by="rule:npb_probable", step=1, team=mine[side]))
    if mine.get("weather"):
        out.append(Fact(
            question_id=f"{q.id}:info",
            value={"team": mine[side], "venue": mine.get("venue"),
                   "weather": mine["weather"]},
            hardness="hard", source=getattr(got, "url", ""),
            publisher="npb.jp", published_at=when,
            article_title=f"{mine.get('venue')} 날씨", tier=verify.TIER_OFFICIAL,
            extracted_by="rule:npb_weather", step=1, team=mine[side]))
    return out


def runs_months(day: date, months: int) -> list[tuple[int, int]]:
    """🔴 **오늘부터 거꾸로** `months` 달. 시즌을 넘기지 않는다(같은 해만).

    ⚠️ 해를 넘기면 작년 자료가 올해 모형에 섞인다 — NPB 시즌은 한 해 안이다.
    """
    out: list[tuple[int, int]] = []
    y, m = day.year, day.month
    for _ in range(max(1, int(months))):
        if m < 1:
            break
        out.append((y, m))
        m -= 1
    return out


def sources_context(ext_id: str) -> list[Source]:
    """🔴 경기 하나의 **깊이 소스**. `ext_id` 는 `npb-{연월일}-{홈}-{원정}` 이다.

    ⚠️ 리그(퍼시픽·센트럴)를 ext_id 로는 모른다 → **둘 다 넣는다.** 파서가 우리 팀이
       없는 표에서 빈 목록을 내므로 틀린 자료가 들어오지 않는다(열기 두 번이 값이다).
    """
    # 🔴 §8-1 — 출처를 먼저 떼고 **남은 부분**을 읽는다. ⚠️ 종전 정규식은
    #    `npb-` 접두를 글자로 요구해 `npb:20261004-…` 를 거절했다.
    m = re.match(r"(\d{4})\d{4}-", matchkey.mine(ext_id, "npb"))
    if not m:
        return []
    year = int(m.group(1))
    out = [Source(f"npb.jp 순위({_STD[code]})", "url",
                  url=standings_url(year, code), tier=verify.TIER_OFFICIAL,
                  parse=parse_standings)
           for code in ("p", "c")]
    # 🔴 **장소별 득점** — 월간 일정의 스코어를 쌓는다(위 주석의 실측).
    #    ⚠️ 몇 달인지는 `config/league_rules.yaml` 이 정한다 — 코드가 박지 않는다.
    # 🔴 §8-1 — 출처를 떼고 **남은 부분**을 읽는다(접두를 글자로 요구하지 않는다)
    md = re.match(r"(\d{4})(\d{2})(\d{2})-", matchkey.mine(ext_id, "npb"))
    when = date(int(md.group(1)), int(md.group(2)), int(md.group(3))) if md \
        else date(year, 10, 1)
    months = int(rules.league_rule("NPB").get("runs_window_months") or 1)
    out += [Source(f"npb.jp 월간 스코어({y}-{mo:02d})", "url",
                   url=runs_url(y, mo), tier=verify.TIER_OFFICIAL,
                   parse=parse_month_runs)
            for y, mo in runs_months(when, months)]
    # 🔴 **예고 선발 + 날씨** — 같은 페이지지만 다른 질문이다(`Net` 이 받아 둔 것을
    #    다시 쓰므로 통신은 한 번이다). ⚠️ 파서를 하나로 묶지 않는다: 월간 득점은
    #    **열두 달 어느 것이나**이고 이것은 **이 경기 한 줄**이다.
    out.append(Source("npb.jp 예고선발·날씨", "url",
                      url=runs_url(when.year, when.month),
                      tier=verify.TIER_OFFICIAL, parse=parse_game_context))
    # 🔴 **등록 명단** — 선수 페이지 주소가 여기 있다(선발 ERA 로 가는 길).
    #    ⚠️ ext_id 의 팀 코드로 두 팀을 만든다(`npb-{연월일}-{홈}-{원정}`).
    codes = re.match(r"\d{8}-([a-z]+)-([a-z]+)$", matchkey.mine(ext_id, "npb"))
    if codes:
        rev = {v: k for k, v in ROSTER_CODE.items()}
        for code in codes.groups():
            full = rev.get(code)
            u = roster_ids_url(full) if full else None
            if u:
                out.append(Source(f"npb.jp 명단({full})", "url", url=u,
                                  tier=verify.TIER_OFFICIAL,
                                  parse=parse_roster_ids))
    # 🔴 **투수 방어율표** — `pitcher_state` 방향이 이것 없이는 미결정이다
    out += [Source(f"npb.jp 투수({_STD[code]})", "url",
                   url=pitchers_url(year, code), tier=verify.TIER_OFFICIAL,
                   parse=parse_pitchers)
            for code in ("p", "c")]
    # 🔴 **팀 투수 성적표** — `starter_factor` 의 분모(팀 ERA)다
    out += [Source(f"npb.jp 팀투수({_STD[code]})", "url",
                   url=team_pitching_url(year, code),
                   tier=verify.TIER_OFFICIAL, parse=parse_team_pitching)
            for code in ("p", "c")]
    return out
