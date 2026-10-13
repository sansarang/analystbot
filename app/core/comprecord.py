"""🔴🔴 **대회 홈/원정 성적**(사용자 지시 2026-10-13 ①) — **표시 전용**.

> ① 대륙 대회 카드에 "그 팀의 대회 홈/원정 성적(직전 2시즌)" 칸 추가 —
>   S03 홈 승률 ⬜ 를 **대회 일정 표**로 채운다.

🔴 판은 `data/comp_record/<대회>/<as-of>.yaml` 이고 `tools/fit_comp_record.py`
   가 적는다(`app/` 은 yaml 을 쓰지 않는다).
🔴 **확률은 안 바뀐다** — λ 홈 배율은 `goal_baselines.home_share`(득점 실측)
   하나가 정한다. 이 판이 채우는 것은 **S03 의 승률 글자**와 카드의 성적 줄이다
   (계약 CR1 이 λ 쪽에서 호출 0건을 센다).
⚠️ 이름은 fotmob 표기 그대로다 — 못 찾으면 **그 사실을 적는다**(지어내지 않는다).
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
BOX = ROOT / "data/comp_record"


def plate(key: str) -> tuple[dict, str]:
    """🔴 그 대회의 가장 최근 판. 없으면 `({}, 사유)`."""
    box = BOX / str(key or "").replace(":", "_")
    rows = sorted(box.glob("*.yaml")) if box.exists() else []
    if not rows:
        return {}, (f"⬜ **대회 성적 판이 없다**(`{key}`) — "
                    f"`tools/fit_comp_record.py` 가 아직 안 돌았다")
    import yaml
    got = yaml.safe_load(rows[-1].read_text(encoding="utf-8")) or {}
    return dict(got), (f"판 `{rows[-1].stem}`(대회 일정 {got.get('n')}경기 · "
                       f"{got.get('seasons') or '시즌 미상'})")


def comp_of(key: str) -> tuple[dict, str]:
    """🔴 **대회 전체** 홈 우위 — `s5` 의 S03 이 읽는 그 꼴(`home_advantage`)."""
    box, why = plate(key)
    if not box:
        return {}, why
    got = dict(box.get("competition") or {})
    if got.get("win_pct_delta") is None:
        return {}, f"⬜ 그 판에 `win_pct_delta` 가 없다({why})"
    return got, why


def team_of(key: str, name: str) -> tuple[dict, str]:
    """🔴 **그 팀**의 홈/원정 성적. 못 찾으면 `({}, 사유)`."""
    box, why = plate(key)
    if not box:
        return {}, why
    rows = dict(box.get("teams") or {})
    said = str(name or "")
    got = rows.get(said)
    if got is None:
        # 🔴 느슨한 대조 — fotmob 표기와 우리 이름이 한 글자 다를 수 있다
        low = said.strip().lower()
        for k, v in rows.items():
            if str(k).strip().lower() == low:
                got = v
                break
    if got is None:
        return {}, (f"⬜ `{said}` 가 대회 성적 판에 없다(적힌 팀 "
                    f"{len(rows)}개 · {why})")
    return dict(got), why


def said_of(key: str, *, home: str, away: str) -> str:
    """🔴 카드 한 줄 — 두 팀의 홈/원정 성적(직전 2시즌). 표시 전용."""
    out = []
    for name, side in ((home, "home"), (away, "away")):
        got, why = team_of(key, name)
        if not got:
            out.append(f"{name} ⬜ {why}")
            continue
        mine = dict(got.get(side) or {})
        other = dict(got.get("away" if side == "home" else "home") or {})
        tag = "홈" if side == "home" else "원정"
        out.append(
            f"**{name}** {tag} {int(mine.get('w') or 0)}승 "
            f"{int(mine.get('d') or 0)}무 {int(mine.get('l') or 0)}패"
            f"({int(mine.get('n') or 0)}경기 · 득 {int(mine.get('gf') or 0)}"
            f"·실 {int(mine.get('ga') or 0)})"
            f" / 반대쪽 {int(other.get('w') or 0)}승 "
            f"{int(other.get('d') or 0)}무 {int(other.get('l') or 0)}패"
            f"({int(other.get('n') or 0)}경기)")
    said_comp, why_comp = comp_of(key)
    tail = (f" · 대회 전체 홈 승 {said_comp.get('home_win_pct')}% · 무 "
            f"{said_comp.get('draw_pct')}% · 원정 승 "
            f"{said_comp.get('away_win_pct')}%(홈 우위 "
            f"**{said_comp.get('win_pct_delta'):+}%p**)" if said_comp
            else f" · ⬜ 대회 전체 수치 없음({why_comp})")
    return " · ".join(out) + tail
