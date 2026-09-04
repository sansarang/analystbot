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


def _side_block(jg: dict, side: str, today: _date | None) -> dict:
    r = jg.get("research") or {}
    games = ((r.get(f"{side}_usage") or {}).get("games")) or []
    dates = [g.get("date") for g in games]
    flags = [g.get("home") for g in games]
    out: dict = {}
    n = consecutive_days(dates, today)
    if n is not None:
        out["연전"] = n
    t = travel(flags, side == "home")
    if t is not None:
        out["이동"] = t
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
    wx = ((jg.get("research") or {}).get("weather")
          or (jg.get("research") or {}).get("날씨"))
    if wx:
        out["날씨"] = wx
    # 오늘 선발의 투구 손 — **사실이지 스플릿이 아니다.**
    #   플래툰 "성적"은 시즌 스플릿이라 대원칙이 막는다. 손은 오늘 사실이므로
    #   싣고, 판정이 자료1(3경기)과 함께 읽게 한다.
    hands = {}
    for side in ("home", "away"):
        h = ((jg.get("research") or {}).get(f"{side}_starter") or {}).get("throws")
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
