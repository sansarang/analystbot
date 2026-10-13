"""🔴🔴 **§5-1 대회별 준비 점검**(지시서 2026-10-13 밤 셋째).

```
PYTHONPATH=. python tools/comp_ready.py
```

> 등록 · 결과 2시즌 재생(0-0 포함) · 홈 이점 실측 판 · 레이팅 · 팀 신원표 ·
> 라인업 사다리 원천 · 결장 사다리 원천 · 6절 검색 원천 표.
> 빠진 칸 → 🔴 + **그 칸 미산출**(손값 금지).

🔴 **CP1** — `kind` 없는 대회는 **분석하지 않는다**(`competition.kind_require`).
🔴 각 칸은 **그 표를 실제로 읽어** 센다(있다고 적지 않는다).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def _yaml(rel: str) -> dict:
    import yaml
    path = ROOT / rel
    if not path.exists():
        return {}
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def replay_count(key: str) -> int:
    """🔴 그 대회의 **0-0 포함 재생**이 몇 경기 적혀 있나(없으면 0)."""
    path = ROOT / "var/judge/replay_big2.json"
    if not path.exists():
        return 0
    rows = json.loads(path.read_text(encoding="utf-8"))
    return sum(1 for r in rows if str(r.get("league")) == key)


def main(argv: list[str]) -> int:
    from app import rules
    from app.core import competition as cp
    from app.core.search import sources as _sr
    rows = cp.rows()
    lineup = _yaml("config/lineup_sources.yaml")
    disc = _yaml("config/league_discipline.yaml")
    ents = _yaml("config/entities.yaml")
    base_fits = set(_yaml("config/base_model.yaml").get("models") or {})
    print("# 🔴🔴 §5-1 대회별 준비 점검")
    print()
    print("| 대회 | 유형 | 등록 | 재생(0-0 포함) | 홈 이점 판 | 레이팅 | "
          "신원표 | 라인업 원천 | 결장 원천 | 검색 원천 표 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    want = ("league:ELC", "league:UCL", "league:ACLE", "league:ACL2",
            "national_friendly", "league:J1", "league:KL1")
    for key in want:
        kind, why_kind = cp.kind_require(key)
        if not kind:
            print(f"| `{key}` | 🔴 미등록 | — | — | — | — | — | — | — | — |")
            print(f"  · {why_kind}")
            continue
        one = dict(rows.get(key) or {})
        ids = list((one.get("sources") or {}).get("fotmob_ids") or [])
        n_replay = replay_count(key)
        said_base = rules.goal_baseline(key)
        home = said_base.get("home_share")
        elo = dict(cp.elo_source(key) or {})
        fit = str(elo.get("fit") or "")
        # 🔴 **실측**: `entities.yaml` 은 `teams:` 아래 **팀 이름별 별칭**이고
        #    리그로 갈려 있지 않다 → 리그별 ✅/🔴 로 적을 수 없다(그 사실을 적는다).
        n_ents = len(dict(dict(ents).get("teams") or {}))
        src_path = ROOT / f"config/sources/{key.replace(':', '_')}.yaml"
        cells = [
            f"`{key}`",
            kind,
            ("✅ id " + ",".join(str(x) for x in ids)) if ids
            else ("⬜ id 없다(친선은 id 로 안 가린다)"
                  if kind == "national_friendly" else "🔴 fotmob id 없다"),
            (f"✅ {n_replay}경기" if n_replay >= 100
             else (f"🔴 {n_replay}경기(2시즌 재생 미완)" if n_replay
                   else "🔴 **재생 0** — 미산출")),
            (f"✅ 홈 몫 {float(home):.3f}" if home else "🔴 **홈 이점 판 없다**"),
            (f"✅ {elo.get('elo')}·적합 `{fit}`"
             if (elo.get("elo") and fit in base_fits)
             else (f"🔴 적합 `{fit or '없다'}`"
                   + ("(모형 표에 없다)" if fit else "") + " — 레이팅 미산출")),
            (f"⬜ 리그별로 안 갈린다(팀 별칭 {n_ents}개 · 공통 표)"
             if n_ents else "🔴 **신원표가 비었다**"),
            # 🔴 **실측**: `lineup_sources.yaml` 은 **공통 규칙**(금지 호스트·
            #    공개 시각)만 든다 — 리그별 원천 목록이 없다.
            ("⬜ 공통 규칙만(금지 호스트 "
             + str(len(list(dict(lineup).get("banned_for_lineup") or [])))
             + "개 · 리그별 목록 없다)"),
            ("✅" if str(key) in dict(dict(disc).get("leagues") or {})
             else "🔴 **결장(징계) 원천 없다** — `league_discipline.yaml` 의 "
                  "`leagues` 가 비었다"),
            (("✅ " + " · ".join(
                f"{g} {len(_sr.rows_of(key, g))}"
                for g in ("S", "A", "B")))
             if src_path.exists() else "🔴 **검색 원천 표 없다**(§6-1)"),
        ]
        print("| " + " | ".join(cells) + " |")
    print()
    print("🔴 **빠진 칸은 그 칸 미산출**이다 — 손값으로 메우지 않는다. 대회 백필이"
          " 끝나기 전에는 카드가 *\"대회 백필 미완 — 참고용\"* 을 적고 등급 상한은"
          " **조건부**다(§5-6).")
    # 🔴 중립 규칙은 표에서 읽는다(CC3 의 재료)
    print()
    for key in ("league:UCL", "league:ACLE", "league:ACL2"):
        for stage in ("League phase", "Final"):
            got, why = cp.neutral_of(key, stage=stage)
            print(f"- `{key}` 단계 `{stage}` → 중립 "
                  + ("**예**" if got else ("아니오" if got is False else "⬜"))
                  + f" · {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
