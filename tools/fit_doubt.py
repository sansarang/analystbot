"""🔴🔴 **2단 의심 변수 시험 + 조건부 보정표**(의심 검증 v2 §3-2·3-3 · 인계 §2-3).

```
PYTHONPATH=. uv run python tools/fit_doubt.py              # 둘 다
PYTHONPATH=. uv run python tools/fit_doubt.py --only vars  # 시험만
PYTHONPATH=. uv run python tools/fit_doubt.py --only cal   # 보정표만
```

## §3-2 시험 — 아직 **안 잰** 의심 변수
`config/doubt_vars.yaml` 의 `의심.측정_대기` 가 그 목록이다(B1 · A2 · B3) ·
거기에 **J1 시장 괴리**를 더한다(2-1 백필 보드가 들어와 이제 잴 수 있다).
방법은 **체급(Elo 차) 3구간 통제 + 95% 구간**이다(`tools/fit_attack2` 와 같은 잣대).
  · (가) 걸리면 봇 실측 **낮아짐** → **유효**
  · (나) 차이 없음 → 제거 · (다) 봇이 **더 맞음** → 제거 + "봇 확신" 근거

## §3-3 조건부 보정표
줄 종류(**승무패 방향 · 보드 핸디 · 보드 언오버**) × 봇 확률 구간 7개 ×
**유효 불리 의심 개수**(0·1·2+). 칸마다 경기 수 · 봇 평균 · 실측 · 95% 구간 ·
반대쪽 실측 · 실보드/근사. 칸 <100 이면 **이웃 합침**, 그래도 <100 이면 **보류**.
판은 `data/doubt_cal/<줄종류>.yaml`.

🔴 **누설 금지**(C11) — 변수는 그 경기 **앞**의 자료로만 만든다.
🔴 봇 확률은 `probfloor.score_grid` + `markets_of` **그 함수**가 센다(사본 금지).
🔴 보드는 2-1 이 만든 `data/board_hist` 다 — **실보드와 근사를 섞어 적지 않는다**.
⚠️ 재료가 덤프에 없는 변수는 **그 사실을 적고 넘긴다**(지어내지 않는다 · #3).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

BOARD = ROOT / "data/board_hist"
OUT = ROOT / "data/doubt_cal"

#: 🔴 체급 통제 — `tools/fit_attack2.TIERS` 와 **같은 구간**이다(사본 금지로 가져온다)
#: 🔴 봇 확률 구간(§3-3 의 그 목록)
BANDS = ((0.40, 0.45), (0.45, 0.50), (0.50, 0.55), (0.55, 0.60),
         (0.60, 0.70), (0.70, 0.80), (0.80, 1.01))
#: 🔴 칸 최소 경기 수 — 이보다 적으면 이웃을 합치고, 그래도 적으면 **보류**
CELL_MIN = 100
#: 🔴 줄 종류 셋
KINDS = ("승무패 방향", "보드 핸디", "보드 언오버")
#: 🔴 J1 — 보드와 봇이 이만큼 벌어지고 **방향이 반대**면 걸린다(그 표의 10%p)
J1_GAP = 0.10
#: 🔴 B1 — 그 시즌 치른 경기가 이보다 적으면 **폼 표본이 얇다**(시즌 초 수축)
B1_GAMES = 5
#: 🔴 B3 — 앞선 10경기에서 **운 요소 골 비중**이 이보다 크면 걸린다
B3_SHARE = 0.25
#: 🔴 C2 — 그 팀의 **홈 득실/경기**를 보려면 앞선 홈 경기가 이만큼 있어야 한다
C2_HOME_MIN = 5
BACK = 10


def ci(a: list[int], b: list[int]) -> tuple[float, float, float]:
    """🔴 두 비율 차와 95% 구간 — `tools/fit_attack2.ci` 와 같은 식이다."""
    from fit_attack2 import ci as _ci
    return _ci(a, b)


def wilson(hits: int, n: int) -> tuple[float, float, float]:
    """🔴🔴 한 칸의 실측과 **95% 구간**(Wilson) — `(비율, 하한, 상한)`.

    ⚠️ 정규 근사는 칸이 작거나 비율이 0·1 에 붙으면 구간이 **범위를 벗어난다**.
       Wilson 은 그 자리에서도 [0, 1] 안에 있다.
    """
    if n <= 0:
        return (float("nan"),) * 3
    z = 1.96
    p = hits / n
    d = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, mid - half), min(1.0, mid + half)


def boards() -> dict:
    """🔴 2-1 이 만든 백필 보드 — `{(리그, 시즌, 홈, 원정): 줄}`."""
    import yaml
    out: dict[tuple, dict] = {}
    for path in sorted(BOARD.glob("*/*.yaml")) if BOARD.is_dir() else []:
        got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        meta = dict(got.get("meta") or {})
        for one in list(got.get("lines") or []):
            key = (str(meta.get("league")), str(meta.get("season")),
                   str(one.get("home")), str(one.get("away")))
            out[key] = dict(one)
    return out


def grid_of(lam: list) -> dict | None:
    """🔴 그 경기의 **스코어 격자** — 봇 λ 에서. `probfloor` 그 함수다."""
    from app.core import probfloor as _pf
    got = [x for x in (lam or []) if isinstance(x, (int, float))]
    if len(got) < 2 or min(got) <= 0:
        return None
    return _pf.score_grid(lam_home=float(got[0]), lam_away=float(got[1]))


def wide_rows() -> list[dict]:
    """🔴🔴 **승무패 방향 칸을 넓은 표본으로** — 재생본 전부(6,985경기).

    ## 왜 넓히나 — 실측 2026-10-14(§5 검증)
    1,470경기로 적합한 `승무패 방향` 의 맨 위 칸은 `50%~100%` **하나**(228경기)로
    뭉쳤고, 그 값 **67.1%** 가 표본 밖에서 이렇게 갈렸다:
    ```
    봇 50~54% → 실측 62.3%   봇 55~59% → 72.2%   봇 60~69% → 81.4%
    ```
    🔴 칸이 **포화**해 위쪽을 못 가른다 — 그래서 확신 줄의 의심 후 확률이
    체계적으로 **낮게** 나온다(§5 보정 곡선의 그 줄).

    🔴 **승무패 방향은 보드가 필요 없다** — 봇이 앞세운 쪽이 맞았나뿐이다.
       그래서 백필 보드가 없는 리그·시즌도 **그대로 쓸 수 있다**.
    ⚠️ `보드 핸디`·`보드 언오버` 는 **보드 기준선이 있어야** 하므로 넓히지 않는다.
    ⚠️ 재생본에는 `extra`(골 시각·선발·xG)가 없어 **의심 깃발을 못 센다** →
       넓힌 줄은 **묶음 0** 칸에만 들어간다(그 사실을 판에 적는다).
    """
    import replays
    rows, why = replays.load()
    out = []
    for r in rows:
        if not (r.get("lam") and r.get("ours") and r.get("hit") is not None):
            continue
        out.append(dict(r))
    return out, why


def line_rows(r: dict, board: dict | None) -> list[dict]:
    """🔴🔴 그 경기의 **줄 종류별 한 줄** — `{kind, p, hit, side, real}`.

    `p` 는 **봇이 고른 쪽**의 확률이고 `hit` 은 그 쪽이 맞았나다.
    ⚠️ 푸시(정수 핸디 무 · 총점 적중)는 **버린다** — 맞음도 틀림도 아니다.
    🔴 `real` 은 그 보드가 **실보드**였나(근사와 따로 집계한다 · §1-4).
    """
    from app.core import probfloor as _pf
    out: list[dict] = []
    hg, ag = int(r.get("hg") or 0), int(r.get("ag") or 0)
    ours = [float(x) for x in (r.get("ours") or [])]
    kind_real = str((board or {}).get("kind") or "")
    real = kind_real.startswith("실보드")
    # ── ① 승무패 방향 — 봇이 앞세운 쪽
    if len(ours) == 3 and r.get("hit") is not None:
        pick = max(range(3), key=lambda i: ours[i])
        out.append({"kind": "승무패 방향", "p": ours[pick],
                    "hit": int(pick == int(r["hit"])),
                    "side": ("홈", "무", "원정")[pick], "real": real,
                    "season": str(r.get("season") or "")})
    grid = grid_of(list(r.get("lam") or []))
    if grid is None or not board:
        return out
    # ── ② 보드 핸디(보드 왼쪽 = 홈 기준)
    point = (dict(board.get("ah") or {})).get("point")
    if point is not None:
        hp = float(point)
        mk = _pf.markets_of(grid, ah_lines=(hp, -hp))
        a = float(dict(mk.get("ah") or {}).get(f"home{hp:+.1f}") or 0.0)
        b = float(dict(mk.get("ah") or {}).get(
            f"away{(-hp) if hp else 0.0:+.1f}") or 0.0)
        margin = (hg - ag) + hp
        if abs(margin) > 1e-9 and max(a, b) > 0:
            side = "홈" if a >= b else "원정"
            out.append({"kind": "보드 핸디", "p": max(a, b),
                        "hit": int((margin > 0) == (side == "홈")),
                        "side": f"{side} {hp:+g}", "real": real,
                        "season": str(r.get("season") or "")})
    # ── ③ 보드 언오버
    t = (dict(board.get("ou") or {})).get("point")
    if t is not None:
        tp = float(t)
        mk = _pf.markets_of(grid, total_lines=(tp,))
        over = float(dict(mk.get("over") or {}).get(tp) or 0.0)
        tot = hg + ag
        if abs(tot - tp) > 1e-9 and 0.0 < over < 1.0:
            side = "오버" if over >= 0.5 else "언더"
            p = over if side == "오버" else 1.0 - over
            out.append({"kind": "보드 언오버", "p": p,
                        "hit": int((tot > tp) == (side == "오버")),
                        "side": f"{side} {tp:g}", "real": real,
                        "season": str(r.get("season") or "")})
    return out


# ══════════════════════════════════════════════════════════════════
# §3-2 — 아직 안 잰 의심 변수의 깃발(누설 금지 · 그 경기 **앞**만)
# ══════════════════════════════════════════════════════════════════

def flags_of(rows: list[dict], book: dict) -> list[dict]:
    """🔴🔴 경기마다 깃발 묶음. 돌려주는 것은 원래 줄 + `flag`·`dr`·`tier`."""
    from app.core import devig as _dv
    from app.core import goals as _gl
    prior: dict[tuple, list] = {}
    seen_league: dict[tuple, set] = {}     # (리그, 시즌) → 그 시즌 본 팀
    played: dict[tuple, int] = {}          # (리그, 시즌, 팀) → 치른 경기 수
    out: list[dict] = []
    for r in rows:
        lg, se = str(r.get("league")), str(r.get("season"))
        home, away = str(r.get("home")), str(r.get("away"))
        ours = [float(x) for x in (r.get("ours") or [])]
        if len(ours) != 3 or r.get("hit") is None:
            continue
        pick = max(range(3), key=lambda i: ours[i])
        side = "home" if pick == 0 else ("away" if pick == 2 else "")
        mine = home if side == "home" else (away if side == "away" else "")
        flag: dict = {}
        # ── B1 폼 표본 — 그 시즌 치른 경기가 얇다(시즌 초 수축)
        if mine:
            n_played = int(played.get((lg, se, mine)) or 0)
            flag["B1"] = n_played < B1_GAMES
        # ── A2 축0 착시 — **지난 시즌 이 리그에 없던 팀**(승격·강등)
        #    🔴 앞선 시즌 목록으로만 본다(누설 금지) · 첫 시즌은 **못 쟀다**(⬜)
        if mine:
            seasons = sorted({s for (l, s) in seen_league if l == lg
                              and s < se})
            if seasons:
                flag["A2"] = mine not in (seen_league.get((lg, seasons[-1]))
                                          or set())
        # ── B3 운 요소 골 — 앞선 10경기에서 **운 섞인 골 비중**이 크다
        if mine:
            past = (prior.get((lg, mine)) or [])[-BACK:]
            if len(past) >= BACK:
                n_goal = n_luck = 0
                for one in past:
                    mine_home = str(one.get("home")) == mine
                    for g in (dict(one.get("extra") or {}).get("goals")
                              or []):
                        if bool(g.get("home")) != mine_home:
                            continue
                        n_goal += 1
                        if _gl.is_lucky(dict(g))[0]:
                            n_luck += 1
                if n_goal >= 5:
                    flag["B3"] = (n_luck / n_goal) >= B3_SHARE
        # ── J1 시장 괴리 — 보드 승무패를 디빅해 **봇과 10%p 반대**인가
        got_board = book.get((lg, se, home, away))
        prices = [x for x in list((got_board or {}).get("win") or [])
                  if isinstance(x, (int, float)) and float(x) > 1.0]
        if side and len(prices) == 3:
            fair, _vig = _dv.proportional([float(x) for x in prices])
            if fair:
                mine_i = 0 if side == "home" else 2
                flag["J1"] = (float(fair[mine_i]) + J1_GAP
                              <= float(ours[mine_i]))
        got = dict(r)
        got["flag"] = flag
        got["dr"] = abs(float(r.get("dr") or 0.0))
        got["side"] = side
        got["ok"] = int(pick == int(r["hit"]))
        # 🔴 C2 는 4분위 문턱이 필요해서 **값만** 싣고 깃발은 뒤에 세운다
        if side:
            host = home
            got_h = [x for x in (prior.get((lg, host)) or [])
                     if str(x.get("home")) == host]
            if len(got_h) >= C2_HOME_MIN:
                got["c2_gd"] = sum(int(x.get("hg") or 0) - int(x.get("ag") or 0)
                                   for x in got_h) / len(got_h)
        out.append(got)
        # ── 지난 목록 갱신(**이 줄 뒤에** 갱신한다 — 누설 금지)
        for team in (home, away):
            prior.setdefault((lg, team), []).append(r)
            seen_league.setdefault((lg, se), set()).add(team)
            played[(lg, se, team)] = int(played.get((lg, se, team)) or 0) + 1
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **C2 팀별 홈 효과** — 4분위 문턱은 **표본 전체**에서 잡는다
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 홈을 골랐으면 **그 집주인의 홈 득실/경기**가 **하위 4분위**일 때 걸린다
    #     (봇이 기대는 홈 이점이 그 팀에는 없다). 원정을 골랐으면 **상위 4분위**
    #     일 때 걸린다(강한 홈을 상대로 원정을 골랐다).
    #  ⚠️ 문턱은 표본 전체 분포에서 잡으므로 **그 경기 결과를 쓰지 않는다**
    #     — 깃발 재료(`c2_gd`)는 전부 **그 경기 앞**의 홈 경기들이다(C11).
    vals = sorted(x["c2_gd"] for x in out if x.get("c2_gd") is not None)
    if len(vals) >= 40:
        lo_cut = vals[int(0.25 * len(vals))]
        hi_cut = vals[int(0.75 * len(vals))]
        for x in out:
            if x.get("c2_gd") is None or not x.get("side"):
                continue
            x["flag"]["C2"] = (x["c2_gd"] <= lo_cut if x["side"] == "home"
                               else x["c2_gd"] >= hi_cut)
    return out


def test_vars(box: list[dict]) -> dict:
    """🔴🔴 §3-2 — 변수마다 체급별 차이와 95% 구간.

    ## 유효 판정 규칙 — **H1 을 올릴 때 쓴 그 잣대 그대로**
    등록표의 H1 이 적고 있다: *"구간이 0 을 품지 않고 **중 체급에서도 남는다**"*.
    그래서 **유효**는 둘을 다 넘어야 한다:
      (a) **전체** 95% 구간이 0 을 품지 않고 차이가 **음수**(봇이 덜 맞는다)
      (b) **체급 한 구간에서도** 같은 조건이 남는다(표본이 잰 구간 안에서)

    🔴 (a) 만으로 올리지 않는다 — ⚠️ 실측 2026-10-14: A2(승격·강등 착시)가
       전체 −15.9%p [−31.7, **−0.1**] 로 (a)를 **턱걸이로** 넘었는데 체급을
       통제하면 약 −2.2%p [−23.4, +19.1] 로 **사라졌다**(걸린 경기 41건뿐).
       체급이 섞인 차이는 *"그 변수"* 가 아니라 **체급**일 수 있다.
    """
    from fit_attack2 import TIERS
    print("## §3-2 의심 변수 시험 — 체급 통제 + 95% 구간")
    print()
    print("| 변수 | 구간 | 걸림 | 걸림 적중 | 안 걸림 적중 | 차이 | 95% 구간 | 읽기 |")
    print("|---|---|---|---|---|---|---|---|")
    out: dict = {}
    for key in ("B1", "A2", "B3", "C2", "J1"):
        said: dict = {"체급": {}}
        for name, lo, hi in (("전체", 0.0, 1e9), *TIERS):
            part = [x for x in box if lo <= x["dr"] < hi
                    and x["flag"].get(key) is not None]
            on = [x["ok"] for x in part if x["flag"][key]]
            off = [x["ok"] for x in part if not x["flag"][key]]
            if len(on) < 20 or len(off) < 20:
                print(f"| {'**' + key + '**' if name == '전체' else ''} | "
                      f"{name} | {len(on)} | ⬜ | ⬜ | ⬜ | 표본 부족 | — |")
                if name != "전체":
                    said["체급"][name] = "표본 부족"
                continue
            d, l2, h2 = ci(on, off)
            sure = h2 < 0 or l2 > 0
            read = ("(가) 유효" if (sure and d < 0)
                    else ("(다) 봇이 더 맞음" if (sure and d > 0)
                          else "(나) 차이 없음"))
            print(f"| {'**' + key + '**' if name == '전체' else ''} | {name} "
                  f"| {len(on)} | {100 * sum(on) / len(on):.1f}% | "
                  f"{100 * sum(off) / len(off):.1f}% | **{100 * d:+.1f}%p** | "
                  f"[{100 * l2:+.1f}, {100 * h2:+.1f}] | "
                  f"{read if name == '전체' else ''} |")
            if name == "전체":
                said.update({"n_on": len(on), "n_off": len(off),
                             "hit_on": round(sum(on) / len(on), 4),
                             "hit_off": round(sum(off) / len(off), 4),
                             "diff": round(d, 4), "lo": round(l2, 4),
                             "hi": round(h2, 4), "읽기": read,
                             "전체유효": bool(sure and d < 0)})
            else:
                said["체급"][name] = round(d, 4)
                # 🔴 (b) — **체급 한 구간에서도** 같은 조건이 남나
                if sure and d < 0:
                    said["체급유효"] = (said.get("체급유효") or []) + [name]
        # ── 🔴 유효 = (a) 전체 **그리고** (b) 체급 한 구간
        said["유효"] = bool(said.get("전체유효") and said.get("체급유효"))
        if said.get("전체유효") and not said.get("체급유효"):
            said["읽기"] = ("(나) 체급을 통제하면 사라진다 — 전체만 유효"
                           f"(걸린 경기 {said.get('n_on')}건) → 제거")
        out[key] = said
    print()
    print("- ⬜ **재료 없음** — **E1 확정 XI 핵심 빠짐**: 결장 사다리·축0 상위 3 이 "
          "덤프(`var/judge/atk_*.json`)에 **없다**(그 칸은 카드 실행 때만 선다) → "
          "이번 표본으로는 못 잰다(지어내지 않는다 · #3).")
    print("- 🔴 **J1 은 2-1 백필 보드가 들어와 처음 잰다** — 실보드가 있는 경기만 "
          "센다(근사 보드에는 배당이 없다).")
    print()
    print("### 유효 판정 — (a) 전체 **그리고** (b) 체급 한 구간")
    print()
    print("| 변수 | (a) 전체 | (b) 체급 | 유효 | 읽기 |")
    print("|---|---|---|---|---|")
    for key, said in out.items():
        print(f"| **{key}** | {'✅' if said.get('전체유효') else '—'} | "
              + (" · ".join(said.get("체급유효") or []) or "—")
              + f" | {'🔴 **유효**' if said.get('유효') else '—'} | "
              + f"{said.get('읽기') or '표본 부족'} |")
    return out


# ══════════════════════════════════════════════════════════════════
# §3-3 — 조건부 보정표
# ══════════════════════════════════════════════════════════════════

def eff_bad(flag: dict, live: list[str]) -> int:
    """🔴 그 경기의 **유효 불리 의심 개수** — 유효로 판정된 변수만 센다."""
    return sum(1 for k in live if flag.get(k) is True)


def band_of(p: float) -> tuple | None:
    for lo, hi in BANDS:
        if lo <= float(p) < hi:
            return (lo, hi)
    return None


def cells(box: list[dict], book: dict, live: list[str], *,
          wide: list[dict] | None = None) -> dict:
    """🔴 줄 종류 × 구간 × 의심 개수 → 그 칸의 줄들."""
    out: dict = {}
    seen: set = set()
    for x in box:
        r_board = book.get((str(x.get("league")), str(x.get("season")),
                            str(x.get("home")), str(x.get("away"))))
        n_bad = eff_bad(dict(x.get("flag") or {}), live)
        bucket = "0" if n_bad == 0 else ("1" if n_bad == 1 else "2+")
        seen.add((str(x.get("league")), str(x.get("day")),
                  str(x.get("home")), str(x.get("away"))))
        for one in line_rows(x, r_board):
            band = band_of(one["p"])
            if band is None:
                continue
            out.setdefault((one["kind"], band, bucket), []).append(one)
    # ── 🔴 넓힌 표본은 **승무패 방향 · 묶음 0** 에만 더한다
    for x in (wide or []):
        key = (str(x.get("league")), str(x.get("day")),
               str(x.get("home")), str(x.get("away")))
        if key in seen:
            continue        # 🔴 **같은 경기를 두 번 세지 않는다**
        for one in line_rows(x, None):
            if one["kind"] != "승무패 방향":
                continue
            band = band_of(one["p"])
            if band is None:
                continue
            one["real"] = None      # 🔴 승무패는 **보드와 무관**하다
            out.setdefault((one["kind"], band, "0"), []).append(one)
    return out


def merged(box: dict, kind: str, bucket: str) -> list[dict]:
    """🔴 칸이 작으면 **이웃 구간을 합친다**(§3-3). 돌려주는 것은 합친 줄 목록."""
    rows = []
    for band in BANDS:
        got = list(box.get((kind, band, bucket)) or [])
        rows.append({"band": band, "rows": got})
    # 🔴 작은 칸을 **위 이웃**으로 밀어 붙인다(확률이 높은 쪽으로)
    out: list[dict] = []
    carry: list[dict] = []
    span: list[tuple] = []
    for one in rows:
        carry += one["rows"]
        span.append(one["band"])
        if len(carry) >= CELL_MIN:
            out.append({"bands": list(span), "rows": list(carry)})
            carry, span = [], []
    if carry:
        if out:
            out[-1]["bands"] += span
            out[-1]["rows"] += carry
        else:
            out.append({"bands": list(span), "rows": list(carry)})
    return out


def say_cell(got: dict) -> dict:
    """🔴 한 칸 — 경기 수 · 봇 평균 · 실측 · 95% 구간 · 반대쪽 · 실보드/근사."""
    rows = list(got["rows"])
    n = len(rows)
    hits = sum(int(x["hit"]) for x in rows)
    p, lo, hi = wilson(hits, n)
    mean = sum(float(x["p"]) for x in rows) / n if n else float("nan")
    real = sum(1 for x in rows if x["real"] is True)
    # 🔴 `None` = **보드 무관**(승무패 방향) — 실보드도 근사도 아니다
    free = sum(1 for x in rows if x["real"] is None)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **시즌 교차**(§4·§5) — 역배는 **다른 시즌에서도 유지**돼야 한다
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 그 칸 안에서 시즌으로 쪼개 **봇 대비 편차 부호**가 같나 본다.
    #     시즌이 둘 미만이거나 한쪽이 30경기 미만이면 **확인 못 했다**(`None`).
    #  ⚠️ `core/doubt` 는 이 칸이 참이 아니면 **역배를 내지 않는다**(추측 금지).
    by_season: dict = {}
    for x in rows:
        by_season.setdefault(str(x.get("season") or ""), []).append(x)
    parts = [(k, v) for k, v in by_season.items() if len(v) >= 30]
    cross = None
    detail: dict = {}
    if len(parts) >= 2:
        signs = set()
        for k, v in parts:
            got_p = sum(int(y["hit"]) for y in v) / len(v)
            got_b = sum(float(y["p"]) for y in v) / len(v)
            signs.add(1 if got_p >= got_b else -1)
            # 🔴 **시즌마다의 수를 적어 둔다** — "뒤집힌다" 가 무너짐인지
            #    잡음인지는 이 수를 봐야 정한다(§5 *"무너지는 칸 폐기"*).
            detail[str(k)] = {"n": len(v), "실측": round(got_p, 4),
                              "봇평균": round(got_b, 4)}
        cross = len(signs) == 1
    band = got["bands"]
    return {"구간": f"{band[0][0]:.0%}~{band[-1][1] - 0.01:.0%}",
            # 🔴 **기계가 읽는 경계**도 같이 적는다 — `core/doubt` 가 그 경기의
            #    봇 확률로 칸을 찾아야 한다(글자를 되파싱하지 않는다 · 사본 금지).
            "p_lo": round(float(band[0][0]), 4),
            "p_hi": round(float(band[-1][1]), 4),
            "n": n, "봇평균": round(mean, 4), "실측": round(p, 4),
            "lo": round(lo, 4), "hi": round(hi, 4),
            "반대쪽실측": round(1.0 - p, 4),
            "실보드": real, "근사": n - real - free, "보드무관": free,
            "시즌교차": cross,
            "시즌": {k: len(v) for k, v in sorted(by_season.items())},
            "시즌별": dict(sorted(detail.items())),
            "보류": n < CELL_MIN}


def build_cal(box: dict, live: list[str], *,
              holdout: list[str] | None = None) -> dict:
    """🔴 §3-3 — 판 셋을 만든다. 돌려주는 것은 `{줄종류: 묶음}`."""
    import yaml
    OUT.mkdir(parents=True, exist_ok=True)
    out: dict = {}
    print("## §3-3 조건부 보정표")
    print()
    print(f"- 유효 불리 의심 변수 — **{', '.join(live) or '없다'}**")
    print(f"- 칸 최소 {CELL_MIN}경기 · 모자라면 **이웃 합침** → 그래도 모자라면 "
          f"**보류**")
    for kind in KINDS:
        print()
        print(f"### {kind}")
        print()
        print("| 의심 | 구간 | 경기 | 봇 평균 | 실측 | 95% 구간 | 반대쪽 | "
              "실보드/근사 | 시즌교차 | 판정 |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        said: dict = {}
        for bucket in ("0", "1", "2+"):
            got = merged(box, kind, bucket)
            rows = []
            for one in got:
                cell = say_cell(one)
                rows.append(cell)
                mark = "🔴 보류" if cell["보류"] else "✅"
                print(f"| {bucket} | {cell['구간']} | {cell['n']} | "
                      f"{cell['봇평균']:.1%} | **{cell['실측']:.1%}** | "
                      f"[{cell['lo']:.1%}, {cell['hi']:.1%}] | "
                      f"{cell['반대쪽실측']:.1%} | "
                      f"{cell['실보드']}/{cell['근사']}"
                      + (f"/보드무관 {cell['보드무관']}"
                         if cell["보드무관"] else "") + " | "
                      + ("✅" if cell["시즌교차"] is True
                         else ("🔴 뒤집힌다" if cell["시즌교차"] is False
                               else "⬜ 못 쟀다"))
                      + f" | {mark} |")
            if not got:
                print(f"| {bucket} | — | 0 | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | "
                      f"🔴 줄이 없다 |")
            said[bucket] = rows
        out[kind] = said
        path = OUT / f"{kind.replace(' ', '_')}.yaml"
        path.write_text(yaml.safe_dump(
            {"meta": {"줄종류": kind, "유효_의심": list(live),
                      "칸_최소": CELL_MIN, "구간": [list(x) for x in BANDS],
                      # 🔴 적합에서 **뺀 시즌** — 검증·문턱은 거기서만 센다
                      "홀드아웃": list(holdout or [])},
             "칸": said}, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    print()
    print(f"판은 `{OUT.relative_to(ROOT)}/<줄종류>.yaml` 이다.")
    return out


def live_vars(fits: dict) -> list[str]:
    """🔴 **유효**로 판정된 의심 변수 — 이미 올라간 것(`의심.유효`) + 이번 판정."""
    import yaml
    path = ROOT / "config/doubt_vars.yaml"
    got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = [str(x) for x in (dict(got.get("의심") or {}).get("유효") or [])]
    for key, said in dict(fits or {}).items():
        if said.get("유효") and key not in out:
            out.append(key)
    return out


def save_fits(fits: dict) -> None:
    """🔴 시험 결과를 **등록표에 적는다**(손으로 올리지 않는다 · 그 파일 머리말)."""
    import yaml
    path = ROOT / "config/doubt_vars.yaml"
    got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = dict(got.get("vars") or {})
    for key, said in dict(fits or {}).items():
        if key not in rows or "diff" not in said:
            continue
        rows[key]["fit"] = {k: v for k, v in said.items() if k != "읽기"}
        rows[key]["시험"] = (
            f"{said['읽기']} — 걸린 경기 적중 {said['hit_on']:.1%} ↔ "
            f"{said['hit_off']:.1%}({said['diff'] * 100:+.1f}%p · "
            f"[{said['lo'] * 100:+.1f}, {said['hi'] * 100:+.1f}])")
    got["vars"] = rows
    box = dict(got.get("의심") or {})
    box["유효"] = live_vars(fits)
    box["측정_대기"] = [k for k in (box.get("측정_대기") or [])
                     if k not in fits]
    got["의심"] = box
    path.write_text(yaml.safe_dump(got, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    print(f"- 🔴 등록표를 갱신했다 — `config/doubt_vars.yaml`"
          f"(유효 {box['유효']} · 측정 대기 {box['측정_대기'] or '없다'})")


def main(argv: list[str]) -> int:
    from fit_attack2 import rows_all
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=("vars", "cal"))
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--wide", action="store_true",
                    help="승무패 방향 칸을 **재생본 전부**로 넓힌다(위 `wide_rows`)")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **홀드아웃** — 적합에서 **뺀 시즌**(§5 검증이 그 시즌만 센다)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `--wide` 는 보정표를 **재생본으로** 적합한다. 그 재생본으로 문턱을
    #     고르고 검증까지 하면 **표본 안**이다(누설). 🔴 그래서 한 시즌을 빼고
    #     적합하고, 검증·문턱은 **그 시즌에서만** 센다.
    ap.add_argument("--holdout", action="append", default=[],
                    help="적합에서 뺄 시즌(여러 번 줄 수 있다 · 예 `2026/2027`)")
    args = ap.parse_args(argv[1:])
    rows = rows_all()
    book = boards()
    if not book:
        print("🔴 백필 보드가 없다 — `tools/fit_board_hist.py` 를 먼저 돌려라")
        return 1
    box = flags_of(rows, book)
    print(f"# 🔴🔴 2단 의심 — **{len(box)}경기** · 백필 보드 {len(book)}줄")
    print()
    fits: dict = {}
    if args.only != "cal":
        fits = test_vars(box)
        if not args.no_save:
            save_fits(fits)
    live = live_vars(fits)
    if args.only != "vars":
        wide = None
        if args.wide:
            wide, why_w = wide_rows()
            cut_out = {str(x) for x in (args.holdout or [])}
            if cut_out:
                before = len(wide)
                wide = [x for x in wide
                        if str(x.get("season") or "") not in cut_out]
                why_w += (f" · 🔴 **홀드아웃 {sorted(cut_out)} 를 뺐다**"
                          f"({before - len(wide)}경기)")
            print()
            print(f"- 🔴 **승무패 방향 칸을 넓혔다** — {why_w}")
            print("  ⚠️ 재생본에는 `extra` 가 없어 **의심 깃발을 못 센다** → "
                  "넓힌 줄은 **묶음 0** 칸에만 들어간다.")
        print()
        build_cal(cells(box, book, live, wide=wide), live,
                  holdout=sorted(str(x) for x in (args.holdout or [])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
