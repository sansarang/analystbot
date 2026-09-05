"""[변수체계 C2] 자료11 — 이동·연전·날씨. **전부 최근 경기와 오늘 값에서만.**

🔴 대원칙(2026-09-04): 판정에 들어가는 모든 데이터는 최근 3~5경기(불펜은
   최근 3일)만. 시즌 누적·통산·상대전적 금지. 예외 없음.
   이 모듈이 만드는 세 값은 그 선 안에 있다 —
     연전  최근 경기 **날짜 배열**에서 센다 (오늘까지 며칠 연속인가)
     이동  최근 경기의 **홈/원정 전환**에서 본다 (원정 뒤 홈인가, 그 반대인가)
     날씨  **오늘** 예보 (이미 `collectors/weather` 가 research 에 넣어둔 값)

🔴 **새로 수집하지 않는다.** 세 값 모두 이미 research 에 있는 것을 읽어 센다.
🔴 **없으면 만들지 않는다.** 날짜가 없으면 연전은 `None` 이다 — 0 이 아니다.
   "휴식 충분"과 "모른다"를 같은 값으로 적으면 판정이 없는 사실을 읽는다.
⚠️ 이 블록은 **변수의 크기를 뒷받침하는 참조**다. 우세를 정하는 근거가 아니다 —
   프롬프트가 그렇게 못 박는다(자료10 과 같은 취급).
"""
from __future__ import annotations

import logging
from datetime import date as _date
from datetime import datetime

logger = logging.getLogger(__name__)


def _as_date(v) -> _date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, _date):
        return v
    if isinstance(v, str):
        for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%m.%d"):
            try:
                d = datetime.strptime(v.strip()[:10], fmt)
            except ValueError:
                continue
            return d.date()
    return None


def consecutive_days(dates: list, today: _date | None = None) -> int | None:
    """오늘까지 **며칠 연속** 경기인가. 날짜를 못 읽으면 None.

    ⚠️ 오늘 경기를 1 로 센다. 어제도 있었으면 2, 그제도 있었으면 3.
       휴식일이 하루라도 끼면 거기서 끊는다.
    """
    days = sorted({d for d in (_as_date(x) for x in dates or []) if d},
                  reverse=True)
    if not days or today is None:
        return None
    n = 1                                    # 오늘 경기
    cur = today
    for d in days:
        if (cur - d).days == 1:
            n += 1
            cur = d
        elif d >= cur:                       # 같은 날 중복·미래 값은 건너뛴다
            continue
        else:
            break
    return n


def travel(recent_home_flags: list, today_is_home: bool | None) -> str | None:
    """직전 경기 대비 홈/원정이 바뀌었는가. 못 읽으면 None.

    ⚠️ **거리를 계산하지 않는다.** `games` 에 구장이 없어 실제 이동 거리는
       모른다. 아는 것만 적는다 — "원정→홈" 같은 전환 사실뿐이다.
       모르는 것을 추정해 넣으면 그 추정이 변수 크기의 근거가 된다.
    """
    flags = [bool(x) for x in recent_home_flags or [] if x is not None]
    if not flags or today_is_home is None:
        return None
    prev = flags[0]
    if prev == bool(today_is_home):
        return "홈 연속" if today_is_home else "원정 연속"
    return "원정→홈" if today_is_home else "홈→원정"


def away_streak(recent_home_flags: list) -> int | None:
    """**연속 원정 차수.** 오늘 포함이 아니라 직전까지 몇 경기 연속 원정이었나.

    ⚠️ 못 읽으면 None — 0 이 아니다. "원정 연전 아님"과 "모른다"는 다르다.
    """
    flags = [x for x in recent_home_flags or [] if x is not None]
    if not flags:
        return None
    n = 0
    for f in flags:                      # 최신순 배열이다
        if bool(f):
            break
        n += 1
    return n


def venue_of(game: dict, team_is_home: bool) -> str | None:
    """그 경기가 열린 **구장의 주인 팀**.

    🔴 `games` 에 구장 컬럼이 없다(전수 확인). 좌표·거리는 모른다.
       다만 "홈이면 우리 구장, 원정이면 상대 구장"은 **사실**이므로
       구장이 바뀌었는지는 이것으로 알 수 있다. 거리는 여전히 모른다.
    """
    if game.get("home") is None:
        return None
    return "OURS" if game.get("home") else (game.get("opponent") or None)


def venue_changed(recent: list[dict], today_is_home: bool | None) -> bool | None:
    """전일 구장 ≠ 금일 구장인가. 못 읽으면 None."""
    if not recent or today_is_home is None:
        return None
    prev = venue_of(recent[0], bool(recent[0].get("home")))
    if prev is None:
        return None
    today = "OURS" if today_is_home else None      # 오늘 상대는 이 블록에 없다
    if today_is_home:
        return prev != "OURS"
    #: 원정이면 오늘 구장은 상대 구장이다. 직전이 우리 구장이었으면 바뀐 것이고,
    #  직전도 원정이었으면 **상대가 같은지 알 수 없다** — 모르는 것은 None.
    return True if prev == "OURS" else None


#: 날씨 라벨. 🔴 임계를 여기서 만들지 않는다 — `scoring._weather_factor` 가
#  원본이다. 그것이 1보다 크면 득점이 늘고(타자 유리), 작으면 준다.
#  ⚠️ 계수가 없으면(기온 파싱 실패·바람 정보 없음) **라벨을 붙이지 않는다.**
BATTER, PITCHER, NEUTRAL = "타자 유리", "투수 유리", "중립"


def weather_label(research: dict, settings=None) -> tuple[str, float] | None:
    """(라벨, 계수). 계수를 못 내면 None — 없는 판단을 만들지 않는다."""
    from app.config import get_settings
    from app.engine.scoring import _weather_factor

    coef = _weather_factor(research or {}, settings or get_settings())
    if coef is None:
        return None
    if coef > 1.0:
        return BATTER, coef
    if coef < 1.0:
        return PITCHER, coef
    return NEUTRAL, coef


def _side_block(jg: dict, side: str, today: _date | None) -> dict:
    r = jg.get("research") or {}
    games = ((r.get(f"{side}_usage") or {}).get("games")) or []
    dates = [g.get("date") for g in games]
    flags = [g.get("home") for g in games]
    # 🔴 **전일 연장 여부는 넣지 않는다.** `usage.games` 에 이닝 수가 없다
    #    (kbo_usage·npb_form·mlb 전수 확인 — runs·hits·errors·starter_ip 뿐).
    #    없는 것을 추정해 넣으면 그 추정이 변수 크기의 근거가 된다.
    out: dict = {}
    n = consecutive_days(dates, today)
    if n is not None:
        out["연전"] = n
    t = travel(flags, side == "home")
    if t is not None:
        out["이동"] = t
    a = away_streak(flags)
    if a:                                    # 0 은 싣지 않는다 — 원정 연전이 아니다
        out["원정연전"] = a
    vc = venue_changed(games, side == "home")
    if vc is not None:
        out["구장변경"] = vc
    return out


def build(jg: dict, *, today: _date | None = None) -> dict:
    """자료11 페이로드. **빈 dict 이면 프롬프트에 아무것도 안 붙는다.**"""
    if today is None:
        sa = jg.get("starts_at")
        today = _as_date(sa) if sa is not None else None
    out: dict = {}
    for side in ("home", "away"):
        blk = _side_block(jg, side, today)
        if blk:
            out[side] = blk
    r = jg.get("research") or {}
    wx = r.get("weather") or r.get("날씨")
    if wx:
        blk: dict = {"수치": wx}
        lab = weather_label(r)
        if lab:
            blk["라벨"], blk["계수"] = lab[0], lab[1]
        out["날씨"] = blk
    # 오늘 선발의 투구 손 — **사실이지 스플릿이 아니다.**
    #   플래툰 "성적"은 시즌 스플릿이라 대원칙이 막는다. 손은 오늘 사실이므로
    #   싣고, 판정이 자료1(3경기)과 함께 읽게 한다.
    #  🔴 [2026-09-05] 키 이름이 틀려 **선발손이 영원히 안 붙었다.**
    #     읽던 키 `{side}_starter` 는 코드베이스 어디에도 없다(전수 grep 확인).
    #     실제 키는 `{side}_pitcher` 다 — `naver_kbo.merge_into_research` 가
    #     `research.setdefault(f"{side}_pitcher", {})` 로 만든다.
    #     자료11 을 만든 그날(2026-09-04) 실측이 0건이라 아무도 못 봤다.
    hands = {}
    for side in ("home", "away"):
        h = ((jg.get("research") or {}).get(f"{side}_pitcher") or {}).get("throws")
        if h:
            hands[side] = h
    if hands:
        out["선발손"] = hands
    return out


def attach(jg: dict, *, today: _date | None = None) -> bool:
    """`jg["material11"]` 에 얹는다. 붙였으면 True."""
    payload = build(jg, today=today)
    jg["material11"] = payload
    jg["material11_status"] = "Y" if payload else "해당없음"
    return bool(payload)
