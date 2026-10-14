"""🔴🔴 **국내 리그 Elo — 적합과 운영이 같이 쓰는 한 곳**(수정 지시 2026-10-14 1번).

> `fit_offsets.domestic_elo()` 를 `app/` 으로 옮겨 **적합·런타임이 같은 함수
> 하나**를 쓴다(경기일 기준 값 · 누설 금지).

## 🔴🔴 왜 옮겼나 — 실측 2026-10-14
`tools/` 의 적합과 `app/` 의 운영이 **각자 Elo 를 굴리고 있었다.** 단위는 같았지만
(J1 표준편차 57.5 ↔ 57.5) **같은 팀에 다른 수**가 붙었다:
```
FC Tokyo  적합 1577.3 ↔ 운영 1553.2 (+24.1)   J1 최대 |차| **73.1**
```
적합된 기울기가 `b_dr ≈ 0.81`(100점당)이고 이 모형이 잡으려는 리그 간 격차가
J1 +72.8 ↔ KL1 +3.7 ≈ **70점**이다 — 즉 **입력 오차가 신호보다 컸다.**
🔴 그래서 둘을 한 함수로 모은다. `app/` 은 `tools/` 를 import 할 수 없으므로
   **이 파일이 원본**이고 `tools/` 가 이것을 부른다(사본 금지).

## 🔴🔴 그리고 **누설을 고친다**
옛 함수는 덤프 전체를 굴려 **마지막 값**을 돌려줬다 — 2024년 경기를 2026년
등급으로 채점한 셈이다(수정 지시 1번: *"경기일 기준 값 · 누설 금지"*).
🔴 `ratings_at(day)` 는 **그 날짜 앞 경기만** 굴린다.
⚠️ 그래서 같은 팀도 날짜마다 값이 다르다 — 그것이 맞는 것이다.

⚠️ 리그 **안에서만** 비교할 수 있는 값이다(리그마다 1500 에서 시작한다) —
   리그 간 비교는 `core/offsets` 의 오프셋이 맞춘다.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOX = ROOT / "var/judge"

#: 🔴 Elo K — `tools/fit_offsets.K_ELO` 와 **같은 수여야 한다**(계약이 센다)
K_ELO = 20.0
#: 🔴 시작 등급
START = 1500.0


def files() -> list[Path]:
    """🔴 `var/judge/replay_*.json` — **줄이 많은 덤프가 먼저**(그쪽이 이긴다)."""
    out: list[tuple[int, Path]] = []
    for path in sorted(BOX.glob("replay_*.json")):
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if isinstance(rows, list):
            out.append((len(rows), path))
    return [p for _n, p in sorted(out, key=lambda kv: (-kv[0], kv[1].name))]


def load(*, league: str = "") -> tuple[list[dict], str]:
    """🔴 서로 다른 경기만 담은 재생 줄 + **어느 덤프가 몇 줄을 보탰나**.

    🔴 같은 경기를 두 번 세지 않는다 — 열쇠는 `(리그, 날짜, 홈, 원정)` 이다.
    ⚠️ **큰 덤프가 이긴다**(그쪽이 더 최근 재생이고 시즌 꼬리표·λ 가 찼다).
    """
    seen: set[tuple] = set()
    out: list[dict] = []
    said: list[str] = []
    for path in files():
        rows = json.loads(path.read_text(encoding="utf-8"))
        add = 0
        for r in rows:
            if not isinstance(r, dict):
                continue
            key = str(r.get("league") or "")
            if league and key != str(league):
                continue
            box = (key, str(r.get("day")), str(r.get("home")),
                   str(r.get("away")))
            if box in seen:
                continue
            seen.add(box)
            out.append(r)
            add += 1
        if add:
            said.append(f"{path.stem} +{add}")
    return out, (f"재생 **{len(out)}경기**(서로 다른 경기) — "
                 + (" · ".join(said) if said else "🔴 **덤프가 없다**"))


def auto_plates() -> tuple[dict, list[str]]:
    """🔴 백필이 없는 리그의 팀별 Elo 판(`data/league_elo_auto/*.yaml`).

    ⚠️ 재생으로 굴린 값과 **같은 잣대가 아니다**(리그 안에서만 비교) — 잣대
       맞추기는 오프셋이 한다.
    """
    import yaml
    out: dict[str, float] = {}
    said: list[str] = []
    box = ROOT / "data/league_elo_auto"
    if not box.is_dir():
        return out, said
    for path in sorted(box.glob("*.yaml")):
        got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        teams = dict(got.get("teams") or {})
        for k, v in teams.items():
            try:
                out.setdefault(str(k), float(v))
            except (TypeError, ValueError):
                continue
        said.append(f"{got.get('league')} {len(teams)}팀")
    return out, said


def league_of(name: str) -> tuple[str, str]:
    """🔴🔴 그 클럽의 **국내 리그 키**(`league:J1` 꼴). 모르면 `("", 사유)`.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 이 표인가 — 실측 2026-10-14
    ══════════════════════════════════════════════════════════════════

    `league_index.league_of_team` 은 **사람이 읽는 이름**(`J리그`)을 돌려준다 —
    오프셋 판의 열쇠는 `league:J1`·`league:fotmob8984` 라서 **안 맞는다**(그리고
    비셀 고베는 그 캐시에 아예 없었다).
    🔴 **적합이 쓴 그 표를 쓴다** — 대륙 대회 수집 줄(`var/judge/offsets_*.json`)
       이 경기마다 `home`/`home_league` 짝을 들고 있고, 그 `*_league` 가 바로
       오프셋 판의 열쇠다(같은 수집에서 나왔다). 그래서 **적합과 운영이 같은
       매핑**을 본다(사본 금지).
    ⚠️ 그 표에 없는 클럽은 **모른다**고 말한다(지어내지 않는다 · #4).
    """
    box = _league_index()
    got = box.get(str(name or "").strip())
    if got:
        return got, f"수집 줄에서 찾았다(클럽 {len(box)}개)"
    return "", (f"⬜ `{name}` 이 대륙 대회 수집 줄에 없다"
                f"(클럽 {len(box)}개 · `var/judge/offsets_*.json`)")


_LEAGUE: dict | None = None


def _league_index() -> dict:
    """🔴 `클럽 이름 → league:*` — 대륙 대회 수집 줄에서 **한 번만** 짓는다."""
    global _LEAGUE
    if _LEAGUE is not None:
        return _LEAGUE
    out: dict[str, str] = {}

    def _nm(one) -> str:
        return str(one.get("name") or "") if isinstance(one, dict) \
            else str(one or "")
    for path in sorted(BOX.glob("offsets_*.json")):
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for r in rows if isinstance(rows, list) else []:
            if not isinstance(r, dict):
                continue
            for side, key in (("home", "home_league"), ("away", "away_league")):
                nm, lg = _nm(r.get(side)), str(r.get(key) or "")
                if nm and lg:
                    out.setdefault(nm, lg)
    _LEAGUE = out
    return out


def ratings_at(day: str = "") -> tuple[dict, str]:
    """🔴🔴 **그 날짜 앞** 경기만으로 굴린 국내 Elo. `(등급, 사유)`.

    `day` 가 빈 글자면 **전부** 굴린다(지금 값) — ⚠️ 과거 경기를 채점할 때는
    **반드시 그 경기 날짜**를 넘긴다(안 넘기면 미래를 본다 · C11).
    """
    rows, why = load()
    cut = str(day or "")
    elo: dict[str, float] = {}
    n = 0
    for r in sorted(rows, key=lambda x: str(x.get("day"))):
        if r.get("hg") is None or r.get("ag") is None:
            continue
        # 🔴🔴 **누설 금지** — 그 날짜 **이전** 경기만 굴린다(같은 날은 뺀다)
        if cut and str(r.get("day") or "") >= cut:
            continue
        home, away = str(r.get("home")), str(r.get("away"))
        dr = float(elo.get(home, START)) - float(elo.get(away, START))
        exp = 1.0 / (1.0 + 10 ** (-dr / 400.0))
        got = (1.0 if int(r["hg"]) > int(r["ag"])
               else (0.5 if int(r["hg"]) == int(r["ag"]) else 0.0))
        elo[home] = float(elo.get(home, START)) + K_ELO * (got - exp)
        elo[away] = float(elo.get(away, START)) - K_ELO * (got - exp)
        n += 1
    # 🔴 **재생 Elo 가 먼저**(같은 잣대의 표본이 크다) · 없는 팀만 자동 판으로
    auto, said_auto = auto_plates()
    more = 0
    for k, v in auto.items():
        if k not in elo:
            elo[k] = v
            more += 1
    return elo, (f"{why} → **국내 Elo** {n}경기로 굴렸다"
                 + (f"(as-of **{cut} 이전**)" if cut else "(전부 · 지금 값)")
                 + f" · 팀 {len(elo)}개(자동 등록 판에서 **{more}팀** 보탰다 — "
                 + " · ".join(said_auto[:6])
                 + (f" 외 {len(said_auto) - 6}" if len(said_auto) > 6 else "")
                 + ")")
