"""🔴🔴 **안전장치** — 사용자 지시 2026-10-16.

> 봇이 fotmob 정보를 **우리 변수에 제대로 넣고 있는지**, **잘못된 경기**로 하고
> 있는지 확인하는 장치를 순서대로 전부 만들어라.

⚠️ 왜 생겼나 — 실사고 2026-10-16(코스타리카 Saprissa vs Sporting):
   · 팀 일정의 슬러그 주소가 **다른 맞대결**을 줘서 과거 5경기 중 4개가 남의
     경기였고(한 자리엔 **분석 대상 경기 자신**이 왔다), 골 목록이 없으니 득실이
     **조용히 0** 이 됐다 → 폼이 *"득점 0.0 · 실점 0.2"* 라는 거짓 수가 되고
     평·확률이 그 수로 갔다.
   · 같은 자료를 **다른 경로**(경기 페이지 `teamForm`)로 보면 1.6/2.0 이었다 —
     🔴 **두 경로를 맞춰 봤으면 그 자리에서 잡혔다.**

🔴 이 파일은 **재지 않는다 · 고치지 않는다** — 받은 두 수를 **대보고 말한다**.
   값을 만드는 곳은 `fotmob`·`s2e_matchup` 이고, 쓰는 곳은 `s5_verify` 다.
"""
from __future__ import annotations

#: 🔴 두 경로의 평균이 이만큼 넘게 다르면 **어긋났다**(골 수 기준)
TOL = 0.25
#: 🔴 폼 창 — 이보다 적은 경기로 센 평균은 믿지 않는다
MIN_GAMES = 3


def avg_of(seq: list, key: str) -> float | None:
    """🔴 수열에서 그 칸의 평균. ⚠️ 못 세면 `None`(0 이 아니다 · #3)."""
    got = [float(x[key]) for x in (seq or [])
           if isinstance(x, dict) and str(x.get(key, "")).lstrip("-").isdigit()]
    return round(sum(got) / len(got), 3) if got else None


def form_cross(ours: dict, theirs: dict) -> tuple[bool | None, str]:
    """🔴🔴 **층2 — 역산 대조**. `(맞나, 사유)`.

    `ours` 는 우리가 쓸 폼 칸(`sequence` 를 든 사전)이고 `theirs` 는 **다른
    경로**로 같은 팀을 센 폼 칸이다. 🔴 둘 다 있어야 비교한다 — 한쪽이 없으면
    `(None, 사유)` 이고 그것은 **실패가 아니라 못 쟀음**이다(#3).
    """
    a, b = list((ours or {}).get("sequence") or []), list(
        (theirs or {}).get("sequence") or [])
    if not a or not b:
        return None, ("⬜ 대조 못 함 — "
                      + ("우리 폼이 비었다" if not a else "다른 경로가 비었다"))
    said: list[str] = []
    for key, name in (("goals_for", "득점"), ("goals_against", "실점")):
        x, y = avg_of(a, key), avg_of(b, key)
        if x is None or y is None:
            said.append(f"{name} 한쪽을 못 셌다")
            continue
        if abs(x - y) > TOL:
            said.append(f"{name} **{x} ↔ {y}**")
    if said:
        return False, "🔴 **두 경로가 어긋난다** — " + " · ".join(said)
    return True, (f"✅ 두 경로가 같다(득점 {avg_of(a, 'goals_for')} · "
                  f"실점 {avg_of(a, 'goals_against')})")


def form_sane(box: dict) -> list[str]:
    """🔴🔴 **층3 — 말이 안 되는 값**. 걸린 사유 목록(없으면 빈 목록).

    ⚠️ 실측 2026-10-16 의 그 꼴이 전부 여기 걸린다 —
       `W D D D D · 득점 0.0 · 실점 0.2`(전부 무승부 · 득점 합 0).
    """
    seq = list((box or {}).get("sequence") or [])
    out: list[str] = []
    if not seq:
        return ["🔴 폼 수열이 **비었다**"]
    if len(seq) < MIN_GAMES:
        out.append(f"🔴 폼이 **{len(seq)}경기**뿐이다(<{MIN_GAMES})")
    gf = [float(x.get("goals_for") or 0) for x in seq]
    ga = [float(x.get("goals_against") or 0) for x in seq]
    if sum(gf) == 0:
        out.append(f"🔴 **{len(seq)}경기 득점 합이 0** 이다(파싱 실패를 의심한다)")
    if sum(ga) == 0:
        out.append(f"🔴 **{len(seq)}경기 실점 합이 0** 이다")
    res = [str(x.get("result") or "") for x in seq]
    if len(res) >= 4 and len(set(res)) == 1:
        out.append(f"🔴 최근 {len(res)}경기가 **전부 `{res[0]}`** 이다")
    # 🔴 스코어 글자와 득실이 어긋나는 줄(파서가 쪼갠 수가 거짓일 때)
    for one in seq:
        said = str(one.get("score") or "")
        if "-" not in said:
            continue
        try:
            a, b = (int(x) for x in said.split("-", 1))
        except ValueError:
            continue
        if (a, b) != (int(one.get("goals_for") or 0),
                      int(one.get("goals_against") or 0)):
            out.append(f"🔴 스코어 `{said}` 와 득실이 어긋난다")
            break
    return out


def leak_of(games: list, *, kickoff, home: str = "", away: str = "") -> list[str]:
    """🔴🔴 **층4 — 누설**. 폼 목록에 **분석 대상 경기(또는 그 뒤)** 가 있나.

    ⚠️ 실사고 2026-10-16: 과거 5경기 중 한 자리에 **그 경기 자신**이 들어왔다
       (슬러그 주소가 그 페이지를 줬다). 목록을 거를 때가 아니라 **쓰기 직전**에
       한 번 더 본다 — 거른 뒤에 섞여 들어오는 길이 있기 때문이다.
    """
    out: list[str] = []
    if kickoff is None:
        return out
    said_day = str(getattr(kickoff, "date", lambda: "")() or "")
    for one in list(games or []):
        got = dict(one) if isinstance(one, dict) else {}
        day = str(got.get("date") or str(got.get("utc") or "")[:10])
        if not day:
            continue
        if day > said_day:
            out.append(f"🔴 **킥오프 뒤 경기**가 폼에 있다 — {day} "
                       f"vs {got.get('opp') or got.get('opponent') or '?'}")
        elif day == said_day and home and away:
            said_opp = str(got.get("opp") or got.get("opponent") or "")
            if said_opp and (said_opp in (home, away)):
                out.append(f"🔴 **그 경기 자신**이 폼에 있다 — {day} "
                           f"vs {said_opp}")
    return out
