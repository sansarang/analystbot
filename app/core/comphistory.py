"""🔴🔴 **대회 이력의 깊이**(예측 지시 2026-10-13 23:10 KST) — **표시 전용**.

> 대회 이력 칸: … + **"그때 선발 중 오늘 명단 남은 수 / 11"** · **감독 같음/
> 다름** · 남은 선발 < 6 또는 감독 바뀜이면 🟡 **이력 근거 약함**.

🔴 판은 `data/comp_history/<경기 id>.yaml` 이고 `tools/comp_history_depth.py`
   가 적는다(`app/` 은 yaml 을 쓰지 않는다).
🔴 **확률에 닿지 않는다** — 글자만 만든다(계약 CH5 가 확률 모듈에서 호출 0건).
⚠️ 판을 **두 팀 이름으로** 찾는다(경기 id 를 카드가 안 들고 있다).
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
BOX = ROOT / "data/comp_history"

#: 🔴 남은 선발이 이보다 적으면 🟡(지시의 6)
LEFT_CUT = 6.0


def plate_for(home: str, away: str) -> tuple[dict, str]:
    """🔴 두 팀 이름이 다 적힌 판. 없으면 `({}, 사유)`."""
    if not BOX.is_dir():
        return {}, "⬜ **대회 이력 깊이 판이 없다**(도구가 아직 안 돌았다)"
    import yaml
    # 🔴 **이름 맞춤은 `core/teamname` 하나다**(사본 금지) — 판은 fotmob 약칭
    #    (`Slavia Prague`)이고 카드는 우리 이름(`SK Slavia Praha`)이다.
    from app.core import teamname as _tn
    for path in sorted(BOX.glob("*.yaml"), reverse=True):
        got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rows = dict(got.get("teams") or {})
        pair = [_tn.pick(str(x or ""), rows.keys()) for x in (home, away)]
        if all(k for k, _w in pair):
            # 🔴 **우리 이름으로 다시 적어 돌려준다** — 카드가 그 이름으로 묻는다
            got["teams"] = {str(nm): rows[k] for nm, (k, _w)
                            in zip((home, away), pair)}
            return dict(got), (f"판 `{path.stem}`"
                               + ("" if all(w == "글자 그대로"
                                            for _k, w in pair)
                                  else " · " + " · ".join(
                                      w for _k, w in pair
                                      if w != "글자 그대로")))
    return {}, (f"⬜ 두 팀(`{home}`·`{away}`)이 적힌 이력 깊이 판이 없다"
                f"(판 {len(list(BOX.glob('*.yaml')))}개)")


def said_of(home: str, away: str) -> str:
    """🔴 카드 한 줄 — 팀마다 `남은 선발/11` · 감독 · 🟡 판정."""
    box, why = plate_for(home, away)
    if not box:
        return f"⬜ {why}"
    out = []
    for name, one in dict(box.get("teams") or {}).items():
        said = dict(one)
        n = int(said.get("n") or 0)
        if not n:
            out.append(f"**{name}** 🟡 **이력 없음**(그 대회 과거 경기 0건)")
            continue
        avg = float(said.get("avg_left") or 0.0)
        same = bool(said.get("same_coach"))
        weak = (avg < LEFT_CUT) or (not same)
        out.append(
            f"**{name}** 과거 {n}경기 · 그때 선발 중 오늘 명단 **{avg:.1f}/11** · "
            f"감독 " + ("**같다**" if same else "🔴 **바뀜**")
            + (f"({said.get('coach_now')})" if said.get("coach_now") else "")
            + (" · 🟡 **이력 근거 약함**" if weak else " · ✅ 근거 있다"))
    return " / ".join(out) + f" · {why} · ⚠️ **표시만**(확률 불변)"
