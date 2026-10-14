"""🔴🔴 **큰 표본 평가 — 백필 as-of 재생**(사용자 지시 2026-10-12 3번).

> 백필 as-of 재생 — K1·J1 두 시즌(+계수 판 walk-forward)으로 수백 경기.
> 봇(득실판·xG판) vs **Elo만** vs **리그 기본률** vs **균등**. 리그별·시즌별.
> 카드 11장 결과는 참고로만 둔다.
> 4번(축별 예측력)은 **이 표본에서** 잰다 — 축0~3 단독, 축2·축3 연속값 투입 효과,
> "Elo만"에 축 하나씩 더하는 **전진 선택**.

🔴 재생 방식 — 경기마다 **킥오프 전**으로 되돌려 축0~3 을 만들고(`backfill.features`
   의 C11 규율) λ·시뮬로 확률을 낸다. ⚠️ 기사·변수는 **없다**(백필에 기사 통로가
   없다 — 그 사실을 보고가 적는다). 즉 이 평가는 **구조 특징만의 봇**이다.
🔴 누설 금지: 목록은 `fotmob.before_as_of` 로 자르고, 특징은 **그 경기 앞 경기**로만
   만든다(L1). Elo 는 **그 경기 전 등급**을 쓴다.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger("backfill_score")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **지표는 `app/core/metrics.py` 하나다**(지시서 §1 · 사본 금지)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 종전에는 브라이어·로그 손실·부트스트랩이 이 파일과 `score_cards.py`·
#     `judge_models.py` 에 **세 벌**이었다 — 한쪽만 고치면 두 보고가 다른 수를
#     말한다. 🔴 이름만 여기 두고 **몸은 한 곳**이다.
from app.core.metrics import boot_ci, brier, logloss, rps  # noqa: E402


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **옛 구조의 잔차 섞기**(손값 β) — §3 이 `probfloor` 에서 걷어 낸 식이다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 지시서 2026-10-12 §3: *"손값 β 삭제"*. 🔴 그런데 **비교 기준**으로는 아직
#     필요하다(§1: 후보를 **기준과** 견준다) — 그래서 `app/` 에서 걷고 **채점기**
#     안에 둔다. 운영 확률은 이 식을 쓰지 않는다.
def legacy_blend(floor: list[float] | None, *, gaps: dict, weights: dict,
                 beta: float) -> tuple[list[float] | None, str]:
    """🔴 바닥에 **축0·축1 잔차**를 얹는다(옛 구조 · 손값 β). 사유를 함께 돌려준다."""
    from app.core.probfloor import RESIDUAL_AXES
    if not floor:
        return None, "🔴 바닥이 없다 — 잔차를 얹지 않는다"
    tilt = 0.0
    said: list[str] = []
    for name in RESIDUAL_AXES:
        got = float(dict(gaps or {}).get(name) or 0.0)
        w = float(dict(weights or {}).get(name) or 0.0)
        if got and w:
            tilt += w * got
            said.append(f"{name} {got:+.3f}×{w:g}")
    if not tilt:
        return list(floor), "잔차 0 — 바닥 그대로(축0·축1 이 비었다)"
    move = float(beta) * tilt
    home = float(floor[0]) * math.exp(move)
    away = float(floor[2]) * math.exp(-move)
    draw = float(floor[1])
    tot = home + draw + away
    out = [home / tot, draw / tot, away / tot]
    return out, (f"잔차 {' · '.join(said)} → 합 {tilt:+.3f} × β {beta:g} = "
                 f"로그 오즈 {move:+.3f}")


def elo_probs(dr: float, *, kind: str) -> list[float]:
    """🔴 **Elo만** 기준 — 입구는 `app/core/base.triple_of` **하나다**(사본 금지).

    ⚠️ 내가 처음에 순서형 로짓을 **여기 베꼈다**(계수 이름도 틀렸다 — 실제는
       `c1·c2·b_dr`). 🔴 그 사본을 걷고 그 함수를 부른다.
    """
    from app.core import base as _base
    got, _why = _base.triple_of(kind, float(dr))
    if got is None:
        return [1 / 3, 1 / 3, 1 / 3]
    return [float(got.home), float(got.draw), float(got.away)]



def attack_box(j: dict, *, home: str, away: str, starters: dict) -> dict:
    """🔴🔴 그 경기에서 **공격 변수의 재료**만 뽑는다(측정 전용 · 확률 경로 밖).

    🔴 담는 것 —
      · `venue` 경기장 이름·좌표(**C3 이동 거리**)
      · `xg` 두 팀 xG(**B2 xG 차이**) · `sog` 유효 슈팅
      · `starters` 양 팀 선발 이름(**D4 로테이션**)
      · `goals` 골 시각·자책·운 요소(**F1 리드 유지력** · F3 · B3)
      · `attendance` 관중(**C5**) · `referee` 심판(**G2**) · `kickoff` 킥오프
    ⚠️ 수를 **만들지 않는다** — 그 경기 페이지에 적힌 것만 옮긴다(#3·#4).
    """
    from app.collect import fotmob as fm
    page = fm._page(j)
    info = ((page.get("content") or {}).get("matchFacts") or {}).get(
        "infoBox") or {}
    said_v = dict(info.get("Stadium") or {})
    stats = fm.stats_of(j)

    def _pair(*names) -> list:
        for nm in names:
            got = stats.get(nm)
            if got:
                return [((x or {}).get("n") if isinstance(x, dict) else x)
                        for x in got]
        return [None, None]

    rows = []
    for g in (fm.goals_of(j) or []):
        # ⚠️ 실측 2026-10-14: `kind`·`header`·`lucky` 는 `goals_of` 의 열쇠가
        #    아니다(**0건** 담겼다) — 실제 이름은 `situation`·`shot_type` 쪽이다.
        #    🔴 그래서 **있는 열쇠를 다 담는다**(골 한 줄은 작다).
        rows.append({k: (list(v) if isinstance(v, tuple) else v)
                     for k, v in dict(g).items()
                     if k not in ("player", "assist")})
    return {
        "venue": {"name": said_v.get("name"), "city": said_v.get("city"),
                  "lat": said_v.get("lat"), "lon": said_v.get("long"),
                  "capacity": said_v.get("capacity")},
        "xg": _pair("expected_goals", "Expected goals (xG)", "xG"),
        "sog": _pair("shots_on_target", "Shots on target"),
        "attendance": (info.get("Attendance") if not isinstance(
            info.get("Attendance"), dict) else
            (info.get("Attendance") or {}).get("value")),
        "referee": ((info.get("Referee") or {}).get("text")
                    if isinstance(info.get("Referee"), dict) else None),
        "kickoff": str((page.get("general") or {}).get("matchTimeUTCDate")
                       or (page.get("general") or {}).get("matchTimeUTC")
                       or ""),
        "starters": {"home": list(starters.get("home") or []),
                     "away": list(starters.get("away") or [])},
        "goals": rows,
    }

async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", action="append", required=True,
                    help="fotmob 리그 id (여러 번)")
    ap.add_argument("--name", action="append", required=True,
                    help="그 리그의 대회 유형 열쇠(예: league:J1)")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--seasons", type=int, default=1,
                    help="🔴 받을 시즌 수(1 이면 이번 시즌만)")
    ap.add_argument("--dump", default="",
                    help="🔴 재생한 줄을 JSON 으로 적는다(판정 시험이 읽는다 — "
                         "같은 재생을 두 번 돌리지 않는다)")
    args = ap.parse_args()
    from app.collect import fotmob as fm
    from app.core import backfill as bf
    from app.core import matchup as mu
    from app.core import sim as _sim
    from app.net import Net
    from app import rules
    net = Net(cache=True)
    rows_all: list[dict] = []
    for lid, name in zip(args.league, args.name, strict=True):
        rows = await fm.league_matches(net, lid)
        # 🔴 **여러 시즌** — 지시 3번(각 두 시즌). ⚠️ 받은 경기는 캐시에 남아
        #    다시 돌릴 때 재사용된다(`Net(cache=True)`).
        page0 = await net.get(fm.league_matches_url(lid, "x"))
        said_seasons = fm.league_seasons(
            fm.payload(getattr(page0, "text", "") or "") or {})
        # 🔴🔴 **시즌 꼬리표를 줄에 단다**(판정 시험 1번 · 시즌 교차).
        #  ⚠️ 실사고 2026-10-12: 달력 연도로 시즌을 가르니 J1 의 `2026/2027` 과
        #     `2026` 이 **둘 다 2026** 이 되어 교차 표본이 12경기로 쪼그라들었다.
        #  🔴 fotmob 이 말하는 **그 시즌 문자열**을 그대로 쓴다(짐작 금지).
        for r in rows:
            r["season"] = str(said_seasons[0] if said_seasons else "")
        for season in said_seasons[1:max(1, int(args.seasons))]:
            more = await net.get(fm.league_matches_url(lid, "x")
                                 + f"?season={season}")
            j_more = fm.payload(getattr(more, "text", "") or "") or {}
            pp = ((j_more.get("props") or {}).get("pageProps") or {})
            for m in (((pp.get("fixtures") or {}).get("allMatches")) or []):
                st = m.get("status") or {}
                rows.append({"season": str(season),
                             "id": str(m.get("id") or ""),
                             "home": str((m.get("home") or {}).get("name") or ""),
                             "away": str((m.get("away") or {}).get("name") or ""),
                             "utc": str(st.get("utcTime") or ""),
                             "finished": bool(st.get("finished"))})
        done = sorted([r for r in rows if r.get("finished") and r.get("utc")],
                      key=lambda r: str(r["utc"]))[-int(args.limit):]
        print(f"리그 {lid}({name}) — 끝난 경기 {len(done)}건 "
              f"· 시즌 {said_seasons[:max(1, int(args.seasons))]}", flush=True)
        prior: dict[str, list] = {}
        elo: dict[str, float] = {}
        mean = rules.goal_share(name)
        base_box = rules.goal_baseline(name)
        from app.core import probmodel as pm
        mul_h, _w = pm.away_mul(home_share=base_box.get("home_share"),
                                per_team=mean)
        home_share = base_box.get("home_share")
        mul_home = (float(home_share) / float(mean)
                    if (home_share and mean) else 1.0)
        conf = dict(mu.table().get("weights") or {})
        beta = float(dict(mu.table().get("lambda_model") or {}).get("beta")
                     or 0.25)
        for n_i, one in enumerate(done, 1):
            if n_i % 25 == 0:
                print(f"   … {n_i}/{len(done)}", flush=True)
            page = await net.get(fm.match_url(str(one.get("id") or "")))
            j = fm.payload(getattr(page, "text", "") or "")
            if not j:
                continue
            score = bf.score_of(j)
            if score is None:
                continue
            h, a = score
            home, away = str(one.get("home") or ""), str(one.get("away") or "")
            # 🔴🔴 **선발을 채운다**(공격형 검증 v2 · D4 로테이션의 재료) —
            #    ⚠️ 종전엔 `"starters": []` 였다(빈 칸) → 로테이션을 백필에서
            #    **못 셌다**. 경기 페이지에 이미 들어 있다.
            said_lu = ((fm._page(j).get("content") or {}).get("lineup") or {})
            said_xi = {}
            for side, which in (("home", "homeTeam"), ("away", "awayTeam")):
                said_xi[side] = [str(r.get("name") or "") for r in
                                 fm.players_of(dict(said_lu.get(which) or {}))]
            # ── 🔴 **그 경기 앞**의 자료로만 특징을 만든다(C11)
            gaps, why = bf.features(
                j, prior={"home": prior.get(home, []),
                          "away": prior.get(away, [])},
                league_mean=mean, home_mul=mul_home)
            dr = float(elo.get(home, 1500.0)) - float(elo.get(away, 1500.0))
            hit = 0 if h > a else (1 if h == a else 2)
            if gaps:
                tilt = sum(float(conf.get(k) or 0.0) * float(v)
                           for k, v in gaps.items())
                move = max(-0.35, min(0.35, beta * tilt))
                # 🔴🔴 **λ 를 적어 둔다**(라인업 지시서 §5·§6 · 2026-10-13) —
                #    라인업 보정은 M1 의 **λ 에** 거는 것이므로 비교 판이 그 수를
                #    받아야 한다(확률만 있으면 λ 를 되돌릴 수 없다).
                lam = [float(mean) * mul_home * math.exp(move),
                       float(mean) * mul_h * math.exp(-move)]
                out = _sim.run(lam[0], lam[1])
                ours = [out.home, out.draw, out.away]
            else:
                ours = None
                lam = None
            # 🔴🔴 **새 구조**(사용자 지시 2026-10-12 1번) — Elo 바닥 + 축0·축1 잔차
            from app.core import probfloor as _pf
            floor, _wf = _pf.floor_of(kind=name, dr=dr)
            fresh, _wb = legacy_blend(floor, gaps=gaps, weights=conf,
                                      beta=beta)
            rows_all.append({"season": str(one.get("season") or ""),
                             # 🔴 §7·§9 가 **팀별 지난 경기**를 쌓으려면 이름과
                             #    실제 스코어가 필요하다(승무패만으론 못 쌓는다).
                             "home": home, "away": away, "hg": h, "ag": a,
                             "floor": floor, "fresh": fresh,
                             "league": name, "day": str(one.get("utc"))[:10],
                             "hit": hit, "ours": ours, "dr": dr, "lam": lam,
                             "gaps": dict(gaps), "why": why,
                             "diff": h - a,
                             # 🔴🔴 **공격형 검증 v2 재료**(지시 2026-10-14f §5)
                             #    — 경기장 좌표(C3) · 팀 xG(B2) · 선발(D4) ·
                             #    골 시각·운 요소(F1·F3·B3) · 관중(C5) · 심판(G2)
                             "extra": attack_box(j, home=home, away=away,
                                                 starters=said_xi)})
            # ── 🔴 Elo 를 **경기 뒤** 굴린다(다음 경기의 "경기 전 등급")
            exp_h = 1.0 / (1.0 + 10 ** (-dr / 400.0))
            got = 1.0 if h > a else (0.5 if h == a else 0.0)
            elo[home] = float(elo.get(home, 1500.0)) + 20.0 * (got - exp_h)
            elo[away] = float(elo.get(away, 1500.0)) - 20.0 * (got - exp_h)
            # ── 🔴 앞 경기 목록에 **이 경기를 더한다**(다음 경기의 prior)
            for team, mine in ((home, True), (away, False)):
                prior.setdefault(team, []).append(
                    {"home_name": home, "away_name": away, "mine_home": mine,
                     "gf": (h if mine else a), "ga": (a if mine else h),
                     "opp": (away if mine else home),
                     "goals": fm.goals_of(j), "stats": fm.stats_of(j),
                     "starters": said_xi["home" if mine else "away"]})
    if args.dump:
        # 🔴🔴 **판정 시험은 같은 재생을 읽는다**(사용자 지시 2026-10-12 판정 시험).
        #    ⚠️ 다시 재생하면 Elo 굴림·난수가 미세하게 달라 두 모형 비교가
        #    **같은 표본**이 아니게 된다 — 그래서 **한 번 재생해 적어 둔다**.
        import json as _json
        Path(args.dump).write_text(
            _json.dumps(rows_all, ensure_ascii=False), encoding="utf-8")
        print(f"🔴 재생한 {len(rows_all)}줄을 적었다 — {args.dump}")
    scored = [r for r in rows_all if r.get("ours")]
    print()
    print(f"재생한 경기 **{len(rows_all)}건** · 확률을 만든 경기 "
          f"**{len(scored)}건**(앞 경기가 모자라면 못 만든다)")
    if not scored:
        return
    base = [sum(1 for r in scored if r["hit"] == i) / len(scored)
            for i in range(3)]
    print(f"그 표본 실제 비율 — 홈 {base[0]:.1%} · 무 {base[1]:.1%} · "
          f"원정 {base[2]:.1%}")
    even = [1 / 3, 1 / 3, 1 / 3]
    models = {
        "**새 구조**(Elo 바닥+축0·축1)": [(r["fresh"], r["hit"]) for r in scored
                                   if r.get("fresh")],
        "봇(옛 구조 · 네 축)": [(r["ours"], r["hit"]) for r in scored],
        "Elo만": [(elo_probs(r["dr"], kind=r["league"]), r["hit"])
                 for r in scored],
        "리그 기본률": [(base, r["hit"]) for r in scored],
        "균등 33/33/33": [(even, r["hit"]) for r in scored],
    }
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **방향 적중률** — 지표 고정(사용자 지시 2026-10-12) · 보고 첫 줄
    # ══════════════════════════════════════════════════════════════════
    from app.core import metrics as _me2
    print()
    print("| 모형 | n | **방향 적중률** |")
    print("|---|---|---|")
    for name, box in models.items():
        if not box:
            continue
        hit = sum(1 for p, h in box if _me2.direction_hit(list(p), h))
        print(f"| {name} | {len(box)} | **{hit / len(box):.1%}** |")
    print()
    # 🔴🔴 **주지표는 로그 손실**이다(지시서 2026-10-12 §1) — 브라이어는 참고다
    print("| 모형 | n | **로그 손실** | 95% 구간 | RPS | 브라이어 |")
    print("|---|---|---|---|---|---|")
    got_l: dict[str, list[float]] = {}
    for name, box in models.items():
        # 🔴 **빈 모형은 그 사실을 적는다**(0 으로 나누지 않는다 · #3).
        #  ⚠️ 실사고 2026-10-13(MLS 재생): 한 모형이 0건이어서 보고가 **터졌다**
        #     (덤프는 이미 적힌 뒤였다 — 그래서 자료는 남았다).
        if not box:
            print(f"| {name} | 0 | ⬜ **못 쟀다** | — | — | — |")
            got_l[name] = []
            continue
        b = [brier(p, hit) for p, hit in box]
        ll = [logloss(p, hit) for p, hit in box]
        rp = [rps(p, hit) for p, hit in box]
        lo, hi = boot_ci(ll)
        got_l[name] = ll
        print(f"| {name} | {len(box)} | **{sum(ll) / len(ll):.4f}** | "
              f"{lo:.4f}~{hi:.4f} | {sum(rp) / len(rp):.4f} | "
              f"{sum(b) / len(b):.4f} |")
    print()
    # 🔴 판정 규칙은 `metrics.verdict_of` **하나다**(결과를 보고 고치지 않는다)
    from app.core import metrics as _me
    print("| 짝지은 차이(봇 − 기준) | 로그 손실 차 | 95% 구간 | 판정 |")
    print("|---|---|---|---|")
    mine = got_l.get("**새 구조**(Elo 바닥+축0·축1)") or got_l["봇(옛 구조 · 네 축)"]
    for name in ("Elo만", "리그 기본률", "균등 33/33/33"):
        got = _me.paired(mine, got_l[name])
        print(f"| vs {name} | {got['mean']:+.4f} | "
              f"{got['lo']:+.4f}~{got['hi']:+.4f} | "
              f"**{_me.verdict_of(got)}** |")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **리그·시즌별**(지시 §1) + **하위 그룹 보정표**(§1 마지막 줄 · §8)
    # ══════════════════════════════════════════════════════════════════
    print()
    print("| 묶음 | n | 새 구조 로그손실 | Elo만 | 차 | 95% 구간 | 판정 |")
    print("|---|---|---|---|---|---|---|")
    for field in ("league", "season"):
        seen = sorted({str(r.get(field) or "?") for r in scored})
        for one in seen:
            sub = [r for r in scored if str(r.get(field) or "?") == one]
            if len(sub) < 20:
                print(f"| {field} {one} | {len(sub)} | 표본 부족(<20) | — | — "
                      f"| — | — |")
                continue
            a = [logloss(list(r["fresh"] or r["ours"]), r["hit"]) for r in sub]
            b2 = [logloss(elo_probs(r["dr"], kind=r["league"]), r["hit"])
                  for r in sub]
            got = _me.paired(a, b2)
            print(f"| {field} {one} | {len(sub)} | {sum(a) / len(a):.4f} | "
                  f"{sum(b2) / len(b2):.4f} | {got['mean']:+.4f} | "
                  f"{got['lo']:+.4f}~{got['hi']:+.4f} | "
                  f"**{_me.verdict_of(got)}** |")
    print()
    print("**하위 그룹 보정표**(홈 승 칸 · 평균 예측 − 실제 · 양수 = 과대평가)")
    print()
    print("| 그룹 | n | 편향 | 95% 구간 |")
    print("|---|---|---|---|")
    rows_c = [{"p": list(r["fresh"] or r["ours"]), "hit": r["hit"],
               "g": f"{r.get('league')}·{r.get('season') or '?'}"}
              for r in scored]
    for name, box in sorted(_me.calib(rows_c, group="g").items()):
        print(f"| {name} | {box['n']} | {box['bias']:+.4f} | "
              f"{box['lo']:+.4f}~{box['hi']:+.4f} |")
    # ── 🔴 4번 — 축별 단독 예측력(상관)과 "Elo만 + 축 하나" 전진 선택
    print()
    print("| 축 | n(≠0) | 득실차 상관 | Elo만+그 축 로그손실 | 개선 |")
    print("|---|---|---|---|---|")
    ll_elo = sum(logloss(elo_probs(r["dr"], kind=r["league"]), r["hit"])
                 for r in scored) / len(scored)
    for axis in ("axis0", "axis1", "axis2", "axis3"):
        vals = [(float(r["gaps"].get(axis) or 0.0), r["diff"], r)
                for r in scored]
        said = [v for v in vals if abs(v[0]) > 1e-9]
        if len(said) < 10:
            print(f"| {axis} | {len(said)} | 표본 부족 | — | — |")
            continue
        xs = [v[0] for v in said]
        ys = [float(v[1]) for v in said]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
        den = math.sqrt(sum((x - mx) ** 2 for x in xs)
                        * sum((y - my) ** 2 for y in ys))
        corr = (num / den) if den else float("nan")
        # 🔴 Elo만 + 그 축(연속값) — λ 이동에 그 축만 넣는다
        ll_one = []
        for r in scored:
            move = max(-0.35, min(0.35, beta * float(r["gaps"].get(axis) or 0.0)
                                  * float(conf.get(axis) or 0.0)))
            p_elo = elo_probs(r["dr"], kind=r["league"])
            out = _sim.run(float(mean) * mul_home * math.exp(move),
                           float(mean) * mul_h * math.exp(-move))
            mixed = [0.5 * (p_elo[i] + [out.home, out.draw, out.away][i])
                     for i in range(3)]
            tot = sum(mixed)
            ll_one.append(logloss([x / tot for x in mixed], r["hit"]))
        got_ll = sum(ll_one) / len(ll_one)
        print(f"| {axis} | {len(said)} | {corr:+.3f} | {got_ll:.4f} | "
              f"{ll_elo - got_ll:+.4f} |")
    print(f"(기준 — Elo만 로그손실 {ll_elo:.4f})")


if __name__ == "__main__":
    asyncio.run(main())
