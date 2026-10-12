"""🔴🔴 **§1 출전 시간 — 교체 시각**(라인업 지시서 2026-10-13 §1).

> 경기별 선수 출전 구간 `[in, out]` · 득점 분 · 퇴장 분(`before_as_of`) ·
> 신원표로 id 매칭(실패율 **경기별 기록**).

🔴🔴 **원천 사다리는 실측으로 정했다**(2026-10-13):
| 리그 | 통로 | 실측 |
|---|---|---|
| J리그 | `data.j-league.or.jp/SFMS02/?match_card_id=N` | ✅ **서버 렌더** ·
  `交代イベント情報エリア` 에 `▽ 나간 선수 / 61' / ▲ 들어온 선수` · robots 허용 |
| J리그(다른 길) | `www.jleague.jp/match/...` | 🔴 **SPA 껍데기** — 모든 경기에 같은
  HTML(637,224자)이 오고 `試合経過` 는 **i18n 글자**였다. 쓰지 않는다 |
| K리그 | `www.kleague.com/match` | 🔴 **빈 응답(len 0)** — 통로 없음 |
| 아무 리그 | fotmob 이벤트 | 🔴 `Substitution` 사건이 **없다**(세 번 확인) |

🔴 그래서 **J1 은 분 단위**, **K1·그 밖은 "거친 판"**(선발 90분)이고 그 사실을
   `intervals` 의 사유가 **이름으로** 적는다(#3 조용한 0 금지).
🔴 **MN1** — 다른 경기(킥오프 이후) 자료로 구간을 채우지 않는다(문은
   `fotmob.before_as_of` 하나다).
🔴 **MN2** — 매칭 실패·미출전 선수를 **0분으로 넣지 않는다**(칸 자체가 없다).
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

#: 🔴 경기 길이(분) — 연장은 안 센다(정규 시간만 · 그 사실을 사유가 적는다)
FULL = 90

#: 🔴 J리그 데이터 사이트 경기 페이지
JL_MATCH = "https://data.j-league.or.jp/SFMS02/?match_card_id={card}"
#: 🔴 그 시즌 경기 목록(검색 결과 · `match_card_id` 가 여기서 온다)
JL_LIST = ("https://data.j-league.or.jp/SFMS01/search?competition_years={year}"
           "&competition_frame_ids={frame}&tv_relay_station_name=")

#: 🔴 `▽ 나간 선수` · `61'` · `▲ 들어온 선수` 를 읽는 그물
_OUT = re.compile(r"▽\s*\|*\s*\|*\s*([^|]+?)\s*\|*\s*\|(\d{1,3})'")
_IN = re.compile(r"▲\s*\|*\s*\|*\s*([^|]+?)\s*\|")


def subs_of_jleague(said: str) -> list[dict]:
    """🔴 J리그 경기 페이지 글자 → `[{min, out, in}]`. 못 읽으면 빈 목록.

    ⚠️ 표는 `▽ 나간 선수 … 분' … ▲ 들어온 선수` 순서다 — **쌍으로** 읽는다.
    """
    text = _flat(said)
    i = text.find("交代")
    if i < 0:
        return []
    box = text[i:]
    outs = list(_OUT.finditer(box))
    out: list[dict] = []
    for m in outs:
        nxt = _IN.search(box, m.end())
        if not nxt:
            continue
        out.append({"min": int(m.group(2)), "out": m.group(1).strip(),
                    "in": nxt.group(1).strip()})
    return out


def intervals(*, starters: list[str], subs: list[dict] | None,
              bench: list[str] | None = None
              ) -> tuple[dict[str, tuple[int, int]], str]:
    """🔴🔴 선발·교체 → **구간** `{선수: (들어온 분, 나간 분)}` 과 사유.

    🔴 **MN2** — 뛰지 않은 벤치 선수는 **칸이 없다**(0 분으로 넣지 않는다).
    ⚠️ `subs` 가 `None`·빈 목록이면 **거친 판**이다(선발 90분) — 사유가 그렇게 적는다.
    """
    got: dict[str, tuple[int, int]] = {str(p): (0, FULL) for p in
                                       (starters or [])}
    said = list(subs or [])
    if not said:
        return got, (f"⚠️ **거친 판** — 교체 시각이 없다(선발 {len(got)}명을 "
                     f"{FULL}분으로 센다) · 벤치 "
                     f"{len(list(bench or []))}명은 **칸이 없다**(0분 금지)")
    unknown: list[str] = []
    for one in sorted(said, key=lambda s: int(s.get("min") or 0)):
        at = int(one.get("min") or 0)
        who_out = str(one.get("out") or "")
        who_in = str(one.get("in") or "")
        if who_out in got:
            lo, _hi = got[who_out]
            got[who_out] = (lo, at)
        elif who_out:
            unknown.append(who_out)
        if who_in:
            got[who_in] = (at, FULL)
    left = [str(p) for p in (bench or []) if str(p) not in got]
    why = (f"교체 {len(said)}건 · 구간 {len(got)}명"
           + (f" · 🔴 선발에서 못 찾은 교체 대상 {unknown[:3]}" if unknown else "")
           + (f" · ⬜ 안 뛴 벤치 {len(left)}명({', '.join(left[:5])})은 "
              f"**칸이 없다**(0분 금지)" if left else ""))
    return got, why


def before(rows: list[dict], *, as_of) -> list[dict]:
    """🔴🔴 **MN1** — `as_of` **이전** 경기만. 문은 `fotmob.before_as_of` 하나다."""
    from app.collect import fotmob as fm
    return fm.before_as_of(list(rows or []), as_of=as_of, key="utc")


#: 🔴 `POSITION | NUMBER | NAME` 한 줄 — 등번호와 이름을 **쌍으로** 읽는다
_SQUAD = re.compile(r"\|(\d{1,2})\|\s*\|?\s*([^|]{2,20}?)\s*\|")


def squad_of_jleague(said: str) -> dict[str, int]:
    """🔴 J리그 경기 페이지 → `{선수 이름: 등번호}`(선발·교체 명단 전부).

    🔴 왜 등번호인가 — J리그는 **일본어 이름**을, fotmob 은 **id·영어 이름**을 준다.
       등번호는 **둘 다 가진 수**다(`shirtNumber`) → 그것으로 잇는다(손 표 금지).
    """
    text = _flat(said)
    out: dict[str, int] = {}
    for m in _SQUAD.finditer(text):
        name = m.group(2).strip()
        if not name or name in ("POSITION", "NUMBER", "NAME", "TIME"):
            continue
        if any(c.isdigit() for c in name):
            continue
        out.setdefault(name, int(m.group(1)))
    return out


def _flat(said: str) -> str:
    """🔴 태그를 `|` 로 바꾸고 전각 공백을 보통 공백으로 — **양쪽을 같게** 만든다."""
    text = re.sub(r"<[^>]+>", "|", str(said or ""))
    return text.replace("&nbsp;", " ").replace("\u3000", " ")


def sides_of_jleague(said: str) -> tuple[dict, str]:
    """🔴🔴 한 경기 페이지 → **팀별** `{squad: {이름: 등번호}, subs: [...]}`.

    🔴 어느 팀의 교체인지는 **이름이 말한다** — `▽` 선수가 그 팀 명단에 있으면
       그 팀이다(블록 순서를 믿지 않는다 · 자기검사가 된다).
    ⚠️ 블록은 `先発`×2 · `控え`×2 · `交代`×2 다(홈 먼저 · 실측 2026-10-13).
    """
    text = _flat(said)
    st = [m.start() for m in re.finditer("先発", text)]
    bn = [m.start() for m in re.finditer("控え", text)]
    sb = [m.start() for m in re.finditer("交代", text)]
    if len(st) < 2 or len(bn) < 2:
        return {}, (f"🔴 명단 블록을 못 찾았다(先発 {len(st)} · 控え {len(bn)})")
    end = sb[0] if sb else len(text)
    sides = {
        "home": {"starters": squad_of_jleague(text[st[0]:st[1]]),
                 "bench": squad_of_jleague(text[bn[0]:bn[1]]), "subs": []},
        "away": {"starters": squad_of_jleague(text[st[1]:bn[0]]),
                 "bench": squad_of_jleague(text[bn[1]:end]), "subs": []},
    }
    lost: list[str] = []
    for one in subs_of_jleague(text[end:] if sb else ""):
        who = str(one.get("out") or "")
        for side in ("home", "away"):
            if who in sides[side]["starters"] or who in sides[side]["bench"]:
                sides[side]["subs"].append(one)
                break
        else:
            lost.append(who)
    why = (" · ".join(
        f"{side} 선발 {len(sides[side]['starters'])}명 · 벤치 "
        f"{len(sides[side]['bench'])}명 · 교체 {len(sides[side]['subs'])}건"
        for side in ("home", "away"))
        + (f" · 🔴 어느 팀인지 못 가린 교체 {len(lost)}건 {lost[:3]}"
           if lost else ""))
    return sides, why


def intervals_by_number(*, starters: dict[int, tuple[int, int]],
                        subs: list[dict], names: dict[str, int]
                        ) -> tuple[dict[int, tuple[int, int]], str]:
    """🔴 교체(이름) → **등번호 구간**. ⚠️ 번호를 못 찾은 교체는 **버리고 적는다**."""
    got = {int(k): tuple(v) for k, v in dict(starters or {}).items()}
    miss: list[str] = []
    for one in sorted(list(subs or []), key=lambda s: int(s.get("min") or 0)):
        at = int(one.get("min") or 0)
        n_out = dict(names or {}).get(str(one.get("out") or ""))
        n_in = dict(names or {}).get(str(one.get("in") or ""))
        if n_out is None or n_in is None:
            miss.append(f"{one.get('out')}→{one.get('in')}")
            continue
        if int(n_out) in got:
            lo, _hi = got[int(n_out)]
            got[int(n_out)] = (lo, at)
        got[int(n_in)] = (at, FULL)
    why = (f"교체 {len(list(subs or []))}건 · 구간 {len(got)}명"
           + (f" · 🔴 등번호를 못 찾은 교체 {len(miss)}건 {miss[:3]}"
              if miss else ""))
    return got, why


def learn_names(pairs: list[tuple[dict, dict]]) -> dict[str, str]:
    """🔴🔴 맞춘 경기에서 `{일본어 팀명: 영어 팀명}` 을 **배운다**(손 표 금지 · #1).

    🔴 한 일본어 이름이 **두 영어 이름**에 붙으면 그 이름은 **버린다**(추측 금지).
    """
    seen: dict[str, set[str]] = {}
    for card, row in list(pairs or []):
        for side in ("home", "away"):
            ja = str(dict(card).get(side) or "").strip()
            en = str(dict(row).get(side) or "").strip()
            if ja and en:
                seen.setdefault(ja, set()).add(en)
    return {ja: next(iter(en)) for ja, en in seen.items() if len(en) == 1}


def pick_card(*, rows: list[dict], day: str, home: str, away: str,
              score: tuple[int, int] | None = None,
              names: dict[str, str] | None = None) -> str | None:
    """🔴 fotmob 경기 ↔ J리그 `match_card_id` — **날짜 + 팀 이름**으로 맞춘다.

    🔴 이름은 J리그가 **줄여서** 적는다(`浦和`·`FC東京`) — 그래서 `discover.pick_team`
       과 같은 규율(부분 일치·별칭)으로 본다. ⚠️ **날짜가 다르면 안 맞춘다**(추측 금지).
    """
    from app.core import discover as _d
    said = [r for r in (rows or []) if str(r.get("day") or "") == str(day)]
    if not said:
        return None
    # 🔴🔴 **날짜 + 스코어**가 1순위 열쇠다(이름으로는 1.0% 밖에 못 맞췄다) —
    #    같은 날 같은 스코어가 **둘 이상이면 안 맞춘다**(추측 금지).
    if score is not None:
        hit = [r for r in said
               if tuple(r.get("score") or ()) == tuple(int(x) for x in score)]
        if len(hit) == 1:
            return str(hit[0].get("card_id") or "") or None
        if len(hit) > 1:
            # 🔴 충돌 — **배운 팀명**이 깬다. 표가 없으면 **안 맞춘다**.
            said_names = dict(names or {})
            if not said_names:
                return None
            same = [r for r in hit
                    if said_names.get(str(r.get("home") or "")) == str(home)
                    and said_names.get(str(r.get("away") or "")) == str(away)]
            return (str(same[0].get("card_id") or "") or None
                    if len(same) == 1 else None)
    want = (_d.name_key(home), _d.name_key(away))
    for one in said:
        got = (_d.name_key(str(one.get("home") or "")),
               _d.name_key(str(one.get("away") or "")))
        if all(a and b and (a in b or b in a) for a, b in zip(got, want,
                                                              strict=True)):
            return str(one.get("card_id") or "") or None
    # ⚠️ 같은 날 경기가 **하나뿐**이면 그것으로 본다(날짜가 이미 맞았다)
    if len(said) == 1:
        return str(said[0].get("card_id") or "") or None
    return None
