"""🔴🔴 **§3 S1 — `old_engine` 폼 입력 어댑터**(통합 지시서 2026-10-13 밤).

> 이번 시즌 리그 경기가 `k_min` 이상이면 **이번 시즌 경기만** · 미만이면 이번 시즌
> 전부 + **지난 시즌 최근 경기로 채움**(채운 경기 표시).

🔴 **M1 은 K0 고정**이다 — 그래서 이 모듈은 **목록만** 만들고 얼린 코드를 부르지
   않는다(계약 S1-1). 🔴 **S1-2** — `as_of` 이후 경기는 문 하나
   (`fotmob.before_as_of`)로 자른다.
⚠️ **가중 0.5 판은 이산 근사다** — `form.form_of` 에 가중 인자가 없으므로
   보충분을 **절반만** 넣는다. 그 사실을 사유가 **매번** 적는다(#4 추측 금지).

🔴🔴 **실측 한 줄**(2026-10-13) — 운영이 받는 **팀 일정 페이지는 이번 시즌만**
   담는다(울산 34경기 전부 `2026`). 그래서 이 어댑터가 **운영에서 바꾸는 것은
   거의 없다**(백필의 리그 목록은 두 시즌을 덮으므로 거기서 뜻이 있다).
   ⚠️ 운영에서 실제로 섞이는 것은 **컵**이다(창 5경기 중 J1 0.84 · K1 0.21).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def pick(rows: list[dict], *, as_of, league: str, k_min: int,
         weak: bool = False, drop_cup: bool = False
         ) -> tuple[list[dict], str]:
    """🔴🔴 폼용 경기 목록. `(목록, 사유)` — 못 만들면 **빈 목록 + 🔴**.

    `rows` 한 줄은 백필·운영이 쓰는 그 꼴이다(`{utc, gf, ga, …}`).
    돌려주는 줄에는 **지난 시즌에서 채운 경기**에 `filled=True` 가 붙는다.
    """
    from app.collect import fotmob as fm
    from app.core import season as _se
    want, why_season = _se.id_of(league=league, when=as_of)
    if not want:
        return [], f"🔴 **폼 목록 못 만들었다** — {why_season}"
    said = _se.tag(fm.before_as_of(list(rows or []), as_of=as_of, key="utc"),
                   league_key="league", when_key="utc")
    for one in said:                       # 🔴 리그가 줄에 없으면 인자로 채운다
        if not str(one.get("season_id") or ""):
            got, _w = _se.id_of(league=league, when=one.get("utc"))
            one["season_id"] = got
    bad = _se.require(said)
    if bad:
        return [], f"🔴 **폼 목록 못 만들었다** — {bad}"
    # 🔴🔴 **§1 "리그 경기만"**(지시서 2026-10-13 밤 셋째)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 가리는 문은 **`competition.key_of` 하나**다(사본 금지) — 그 경기의
    #     대회 표기를 **리그 열쇠**로 바꿔 **분석 대상 리그와 같은지** 본다.
    #  ⚠️ `level.is_cup` 만으로는 모자랐다(실측 2026-10-13): `Korean FA Cup` 은
    #     잡지만 **`AFC Champions League` 는 못 잡는다**(컵이 아니라 대륙 대회다).
    #     🔴 §1 이 말한 것은 *"리그 경기만"* 이므로 **둘 다 빼야** 한다.
    #  ⚠️ 기본값은 **끈 상태**다 — 판정이 끝나기 전에는 운영이 바뀌지 않는다.
    cups = 0
    cup_names: list[str] = []
    if drop_cup:
        from app.core import competition as _cp
        from app.core import level as _lv
        keep = []
        for one in said:
            comp = str(one.get("league_name") or one.get("comp") or "")
            if not comp:
                keep.append(one)          # ⬜ 표기가 없으면 **버리지 않는다**
                continue
            got_key, _w = _cp.key_of(competition=comp)
            if got_key == str(league) and not _lv.is_cup(comp):
                keep.append(one)
                continue
            cups += 1
            if comp not in cup_names:
                cup_names.append(comp)
        said = keep
    now = [r for r in said if str(r.get("season_id")) == want]
    old = [r for r in said if str(r.get("season_id")) < want]
    said_cup = (f" · **리그 밖 {cups}경기를 뺐다**"
                + (f"({', '.join(cup_names[:3])})" if cup_names else "")
                if drop_cup else "")
    if len(now) >= int(k_min):
        return now, (f"**이번 시즌만** {len(now)}경기(`{want}` · k_min "
                     f"{k_min} 이상) · 지난 시즌 {len(old)}경기는 **안 쓴다**"
                     + said_cup)
    need = int(k_min) - len(now)
    if weak:
        need = max(1, need // 2)
    fill = [dict(r, filled=True) for r in old[-need:]]
    return (fill + now), (
        f"이번 시즌 {len(now)}경기(k_min {k_min} 미만) + 지난 시즌 "
        f"**{len(fill)}경기로 채웠다**"
        + (" · ⚠️ **가중 축소 판**(보충분을 **절반만** — `form_of` 에 가중 인자가"
           " 없어 이산 근사다)" if weak else "")
        + said_cup
        + f" · 채운 경기는 `filled` 로 표시한다")
