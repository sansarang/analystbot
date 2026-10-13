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


def latest(key: str):
    """🔴 그 대회의 **가장 최근 판 경로**(없으면 `None`) — `plate` 와 같은 고름."""
    box = BOX / str(key or "").replace(":", "_")
    rows = sorted(box.glob("*.yaml")) if box.exists() else []
    return rows[-1] if rows else None


def plate(key: str) -> tuple[dict, str]:
    """🔴 그 대회의 가장 최근 판. 없으면 `({}, 사유)`."""
    # 🔴 판 **고르기는 `latest` 하나다**(사본 금지) — 기록을 덧쓰는 도구도 그것을 쓴다
    path = latest(key)
    if path is None:
        return {}, (f"⬜ **대회 성적 판이 없다**(`{key}`) — "
                    f"`tools/fit_comp_record.py` 가 아직 안 돌았다")
    import yaml
    got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return dict(got), (f"판 `{path.stem}`(대회 일정 {got.get('n')}경기 · "
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
    # 🔴 **이름 맞춤은 `core/teamname` 하나다**(사본 금지) — 판은 fotmob 약칭
    #    (`Lens`)이고 카드는 정식명(`Racing Club de Lens`)이다.
    from app.core import teamname as _tn
    pick, said_pick = _tn.pick(said, rows.keys())
    if not pick:
        return {}, f"{said_pick}(· {why})"
    return dict(rows[pick]), (why if said_pick == "글자 그대로"
                              else f"{why} · {said_pick}")


def _said_box(box: dict) -> str:
    """🔴 성적 한 덩이 — 없으면 `—`."""
    if not int((box or {}).get("n") or 0):
        return "—"
    return (f"{int(box['w'])}승 {int(box['d'])}무 {int(box['l'])}패"
            f"({int(box['n'])}경기 · 득 {int(box['gf'])}·실 {int(box['ga'])})")


def verified_of(key: str) -> tuple[bool, str]:
    """🔴🔴 그 판이 **외부 공식 결과와 대조**됐나(수정 지시 2026-10-14c ③).

    🔴 불일치가 0 이 될 때까지 카드는 **"검증 전 — 판단에 쓰지 말 것"** 을 적는다.
    """
    box, why = plate(key)
    if not box:
        return False, why
    if box.get("verified") is True:
        return True, f"✅ 외부 공식 결과와 대조 끝({box.get('verified_why') or why})"
    return False, ("🔴 **검증 전 — 판단에 쓰지 말 것**"
                   f"(외부 공식 결과 대조 전 · {why})")


def said_of(key: str, *, home: str, away: str) -> str:
    """🔴 카드 줄 — 두 팀의 대회 성적. **시즌별**로 나눠 적는다(표시 전용).

    🔴 집계 기간(수정 지시 2026-10-14c ②) — *지금 시즌을 뺀 직전 두 시즌*이
       `home`·`away` 고, **지금 시즌 진행분**은 따로, **중립 경기**(결승 등)도
       따로다. 시즌별 줄은 판의 `by_season` 이 든다.
    🔴 꼬리표 — 외부 대조가 끝나지 않았으면 **검증 전**이라고 적는다(③).
    """
    out = []
    for name, side in ((home, "home"), (away, "away")):
        got, why = team_of(key, name)
        if not got:
            out.append(f"{name} ⬜ {why}")
            continue
        tag = "홈" if side == "home" else "원정"
        other = "away" if side == "home" else "home"
        mine = [f"**{name}** 직전 두 시즌 {tag} {_said_box(got.get(side))}"
                f" / 반대쪽 {_said_box(got.get(other))}"]
        now = dict(got.get("now") or {})
        if now:
            mine.append(f"지금 시즌 {tag} {_said_box(now.get(side))}"
                        f" / 반대쪽 {_said_box(now.get(other))}")
        said_n = dict(got.get("neutral") or {})
        if int(said_n.get("n") or 0) or int(
                dict(now.get("neutral") or {}).get("n") or 0):
            mine.append("중립(결승 등) "
                        + _said_box({
                            k: int(said_n.get(k) or 0)
                            + int(dict(now.get("neutral") or {}).get(k) or 0)
                            for k in ("w", "d", "l", "gf", "ga", "n")}))
        for season, one in sorted(dict(got.get("by_season") or {}).items(),
                                  reverse=True):
            # ⚠️ 그 시즌에 그쪽 경기가 **없으면 줄을 안 적는다**(빈 `—` 는 소음이다)
            if not int((dict(one).get(side) or {}).get("n") or 0):
                continue
            mine.append(f"{season} {tag} {_said_box(dict(one).get(side))}")
        out.append(" · ".join(mine))
    said_comp, why_comp = comp_of(key)
    tail = (f" · 대회 전체 홈 승 {said_comp.get('home_win_pct')}% · 무 "
            f"{said_comp.get('draw_pct')}% · 원정 승 "
            f"{said_comp.get('away_win_pct')}%(홈 우위 "
            f"**{said_comp.get('win_pct_delta'):+}%p** · 중립 제외)" if said_comp
            else f" · ⬜ 대회 전체 수치 없음({why_comp})")
    ok, said_ok = verified_of(key)
    return " · ".join(out) + tail + ("" if ok else f" · {said_ok}")
