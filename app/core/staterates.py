"""🔴🔴 **상태별 득점률 표** — 수정 지시서 2026-10-12 [2-오프라인]·[2a].

> 팀마다 상태(앞섬/동점/뒤짐)별 분당 득점률·실점률 ÷ 그 팀 평균 → 배율.
> 리그 평균 쪽으로 수축(표본 분 수 가중). 리그 단위 배율(동점 후반 강도 포함).
> **표본 부족 팀 = 리그 배율 + 🔴.**

🔴 이 파일은 **읽기만** 한다 — 수를 만드는 곳은 `tools/fit_state_rates.py` 이고
   저장 자리는 `data/state_rates/<league>.yaml` 이다.
⚠️ **기본값을 코드에 박지 않는다**(#4) — 표가 없으면 빈 표와 사유를 돌려준다.
   계약 `test_no_invented_numbers` 가 그것을 센다.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

#: 🔴 저장 자리 — 리그마다 한 파일
STORE = Path(__file__).resolve().parents[2] / "data" / "state_rates"

#: 🔴 상태 이름 — `sim.STATES` 와 **같은 글자**여야 한다(사본 금지: 그쪽이 원본)
#  ⚠️ 여기서 다시 적지 않고 그 모듈에서 읽는다.


def states() -> tuple[str, ...]:
    from app.core.sim import STATES
    return tuple(STATES)


def load(league: str, *, as_of) -> dict:
    """🔴🔴 그 리그의 표 — **as_of 이전 최신 판**(L3). 없으면 빈 표.

    🔴 판 고르기는 `versions.pick` 하나다(사본 금지) — 운영은 오늘 이전 판,
       재현·백필은 **그 경기 날짜 이전** 판을 본다.
    ⚠️ 옛 자리(`data/state_rates/<리그>.yaml`)는 **판이 없을 때만** 본다 —
       그 파일은 as-of 가 없어 **누설 의심**이므로 사유에 그렇게 적는다.
    """
    from app.core import versions as _vz
    key = str(league or "").replace("/", "_").replace(":", "_")
    if not key:
        return {}
    got, said = _vz.pick(_vz.path_of("state_rates", league), as_of=as_of)
    if got:
        logger.info("[staterates] %s — %s", key, said)
        return dict(got)
    path = STORE / f"{key}.yaml"
    if not path.exists():
        logger.info("[staterates] %s — %s · 옛 파일도 없다", key, said)
        return {}
    import yaml
    try:
        old = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        logger.info("[staterates] %s 를 못 읽었다: %s", path.name, exc)
        return {}
    logger.info("[staterates] %s — 🔴 **판이 없어 옛 파일**을 썼다(as-of 없음 · "
                "누설 의심): %s", key, said)
    return dict(old)


def for_team(*, league: str, team: str, table: dict | None = None,
             as_of=None) -> tuple[dict, str]:
    """🔴🔴 [2a] — 그 팀의 **상태 배율**과 사유. `({상태: {for, against}}, 사유)`.

    🔴 차례: ① 그 팀 칸 → ② **리그 칸 + 🔴**(표본 부족) → ③ 빈 표 + 사유.
    ⚠️ 리그 칸을 쓸 때 **그 사실을 숨기지 않는다** — 카드가 🔴 를 그대로 적는다.
    """
    box = dict(table if table is not None else load(league, as_of=as_of))
    if not box:
        return {}, f"🔴 상태 배율 표가 **없다**(리그 `{league}`) — 상태를 안 쓴다"
    rows = dict(box.get("teams") or {})
    one = dict(rows.get(str(team)) or {})
    if one:
        n = one.pop("minutes", None)
        return ({k: dict(v) for k, v in one.items() if k in states()},
                f"팀 표(분 표본 {n})" if n else "팀 표")
    said = dict(box.get("league") or {})
    if said:
        return ({k: dict(v) for k, v in said.items() if k in states()},
                f"🔴 **리그 배율로 갈음했다** — `{team}` 표본 부족")
    return {}, f"🔴 리그 칸도 비었다(`{league}`) — 상태를 안 쓴다"


def pair(*, league: str, home: str, away: str, table: dict | None = None,
         as_of=None) -> tuple[dict, dict]:
    """🔴 ⑪ 이 쓰는 꼴 — `({"home": …, "away": …}, {"home": 사유, …})`."""
    got_h, why_h = for_team(league=league, team=home, table=table,
                            as_of=as_of)
    got_a, why_a = for_team(league=league, team=away, table=table,
                            as_of=as_of)
    out = {}
    if got_h:
        out["home"] = got_h
    if got_a:
        out["away"] = got_a
    return out, {"home": why_h, "away": why_a}


def said_of(box: dict, why: dict) -> str:
    """🔴 카드·근거 줄 — *"리드 후 내려앉음(실점률 ×1.10)"* 꼴로 적는다."""
    out: list[str] = []
    for side in ("home", "away"):
        one = dict(dict(box or {}).get(side) or {})
        if not one:
            out.append(f"{side} ⬜ {dict(why or {}).get(side) or '없다'}")
            continue
        said = []
        for name, label in (("lead", "앞섬"), ("level", "동점"),
                            ("trail", "뒤짐")):
            got = dict(one.get(name) or {})
            if not got:
                continue
            said.append(f"{label} 득 ×{float(got.get('for', 1.0)):.2f}"
                        f"·실 ×{float(got.get('against', 1.0)):.2f}")
        out.append(f"{side} " + " · ".join(said)
                   + f" ({dict(why or {}).get(side) or ''})")
    return " / ".join(out)
