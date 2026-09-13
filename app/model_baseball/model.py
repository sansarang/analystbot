"""[MBM-1] 야구 기본 모델 — 선발·불펜·타선·환경을 합쳐 승률을 만든다.

야구 모델 지시문 3단계. **전부 코드가 계산한다. LLM 개입 없음.**

⚠️ 판정 입력은 최근 폼 전용이지만 모델의 **사전값(prior)** 은 시즌 누적을 써도
   된다(지시문 5번 예외). 용도는 "최근 3~5경기를 얼마나 믿을지 정하는 축소
   계수"뿐이고, Gemini 에게는 사전값이 아니라 **합쳐진 확률만** 간다.
🔴 리그 평균을 **상수로 적지 않는다** — DB 에서 계산해 인자로 받는다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 피타고리안 지수. 야구의 득실↔승률 관계에서 쓰는 값(지시문 3-6).
PYTHAG_EXP = 1.83

#: 축소 계수 초기값. **단위는 이닝**이다(지시문 3-1: 초기 30이닝).
K_SP = 30.0
K_BP = 60.0

#: 선발 최근 창(등판 수)과 기대 이닝 상한.
SP_WINDOW = 5
SP_IP_CAP = 7.0
#: 기록이 없을 때 쓸 선발 소화 이닝. 리그 관행값이고 4단계에서 적합한다.
SP_IP_PRIOR = 5.2

#: 필승조 1명이 최근 3일 투구했을 때의 불펜 RA9 가산(초기값).
BP_TIRED_PENALTY = 0.3

#: wOBA → 경기당 득점 환산. 🔴 [MBM-2] **표준 환산식으로 적는다.**
#  wRAA/PA = (wOBA − lg) / wOBA_scale(1.25) · 경기당 타석 약 38
#  → 계수 ≈ 30. 종전에 1/0.0125 = 80 을 쓰자 2024시즌 확률이
#    0.0400~1.0000 으로 폭주했다(실측 2026-09-13).
WOBA_SCALE = 1.25
PA_PER_GAME = 38.0
WOBA_TO_RPG = PA_PER_GAME / WOBA_SCALE      # ≈ 30.4

#: 승률 상하한. 🔴 숫자를 두 곳에 적지 않는다 — `config.max_win_prob_mlb` 가 원본.
#  근거(그 설정의 주석): 완벽한 정보를 가져도 MLB 단일 경기 예측 상한은 약 72%,
#  학계 최고 모델은 61.77%. 상한 초과는 "강한 픽"이 아니라 계산 오류다.
def _p_cap() -> float:
    from app.config import get_settings

    return float(get_settings().max_win_prob_mlb)


P_CAP = _p_cap()


def shrink(recent, n, prior, k=K_SP) -> float:
    """최근값과 사전값의 축소 결합. `n` 단위는 **이닝**이다.

    `(n·recent + k·prior) / (n + k)` — 표본이 없으면 사전값 그대로다.
    """
    if recent is None or not n:
        return float(prior)
    n = float(n)
    return (n * float(recent) + float(k) * float(prior)) / (n + float(k))


def _ra9(rows) -> tuple[float | None, float]:
    ip = sum(float(r.get("ip") or 0.0) for r in rows)
    runs = sum(float(r.get("r") or 0.0) for r in rows)
    if ip <= 0:
        return None, 0.0
    return runs * 9.0 / ip, ip


def sp_axis(starts, prior, k=K_SP, window=SP_WINDOW) -> dict:
    """선발 축. `starts` 는 **최근순**(첫 원소가 가장 최근)."""
    use = list(starts or [])[:window]
    recent, ip = _ra9(use)
    exp_ip = (sum(float(r.get("ip") or 0.0) for r in use) / len(use)) if use else SP_IP_PRIOR
    return {"ra9": shrink(recent, ip, prior, k),
            "ip": min(float(exp_ip), SP_IP_CAP),
            "n_ip": ip}


def bp_axis(apps, prior, k=K_BP, tired=0) -> dict:
    """불펜 축. `tired` = 최근 3일 투구한 필승조 인원 수."""
    recent, ip = _ra9(apps or [])
    base = shrink(recent, ip, prior, k)
    return {"ra9": base + BP_TIRED_PENALTY * float(tired or 0),
            "n_ip": ip, "tired": int(tired or 0)}


def off_axis(woba, league) -> float:
    """타선 wOBA → 팀 기대 득점(경기당). 리그 평균 대비로만 움직인다."""
    lg_w = float((league or {}).get("woba") or 0.320)
    lg_r = float((league or {}).get("rpg") or 4.40)
    if woba is None:
        return lg_r
    return lg_r + (float(woba) - lg_w) * WOBA_TO_RPG


def team_offense(order_woba, fallback_woba, league) -> dict:
    """오늘 타순 기준 득점. 타순이 없으면 최근 경기 평균으로 대체하고 표시한다."""
    missing = order_woba is None
    w = fallback_woba if missing else order_woba
    return {"rpg": off_axis(w, league), "lineup_missing": bool(missing)}


def expected_runs(sp_ra9, sp_ip, bp_ra9, innings=9.0) -> float:
    """선발이 남긴 이닝을 불펜이 메운다 — 이닝 배분 가중 평균."""
    sp_ip = max(0.0, min(float(sp_ip), innings))
    return (float(sp_ra9) * sp_ip + float(bp_ra9) * (innings - sp_ip)) / innings


def pythag(rs, ra, exp=PYTHAG_EXP) -> float:
    rs, ra = max(float(rs), 1e-6), max(float(ra), 1e-6)
    return rs ** exp / (rs ** exp + ra ** exp)


def win_prob(rs_h, ra_h, rs_a, ra_a, hfa=0.04) -> float:
    """홈 승률. 양 팀 피타고리안을 맞붙이고 홈 이점을 더한다.

    ⚠️ 4단계에서 로지스틱 보정(`p = σ(a + b·(exp_rs − exp_ra))`)으로 갈아탄다.
       여기 값은 그 적합의 **출발점**이다.
    """
    h = pythag(rs_h, ra_h)
    a = pythag(rs_a, ra_a)
    # 두 팀 강도를 log-odds 로 합친다(빌 제임스 로그5와 같은 형태)
    num = h * (1.0 - a)
    den = num + a * (1.0 - h)
    p = 0.5 if den <= 0 else num / den
    # 🔴 [MBM-2] 상·하한으로 절사한다. 4단계 로지스틱 적합은 절사 **전** 값을
    #    쓰도록 `predict` 가 `p_raw` 를 함께 낸다.
    return min(max(p + float(hfa), 1.0 - P_CAP), P_CAP)


def predict(home: dict, away: dict, park=1.0, hfa=0.04) -> dict:
    """축 → 승률·총득점·기여값. 입력은 `sp_axis`·`bp_axis`·`team_offense` 결과."""
    # 🔴 [MBM-3 2026-09-13] `ra_h` 는 **홈이 내주는 점수** = 홈 투수진이다.
    #    종전에는 원정 투수진을 넣어 부호가 통째로 뒤집혀 있었다 —
    #    선발·불펜이 다 나은 팀의 승률이 0.364 로 나왔다.
    ra_h = expected_runs(home["sp"]["ra9"], home["sp"]["ip"], home["bp"]["ra9"])
    ra_a = expected_runs(away["sp"]["ra9"], away["sp"]["ip"], away["bp"]["ra9"])
    # 구장은 양쪽 득점에 같은 방향으로 작용한다
    rs_h = float(home["off"]["rpg"]) * float(park)
    rs_a = float(away["off"]["rpg"]) * float(park)
    ra_h *= float(park)
    ra_a *= float(park)
    p = win_prob(rs_h, ra_h, rs_a, ra_a, hfa=hfa)
    raw = pythag(rs_h, ra_h) * (1.0 - pythag(rs_a, ra_a))
    den2 = raw + pythag(rs_a, ra_a) * (1.0 - pythag(rs_h, ra_h))
    return {
        "p_home": round(p, 4),
        # 절사 전 값 — 4단계 로지스틱 적합의 입력이다
        "p_raw": round((0.5 if den2 <= 0 else raw / den2) + float(hfa), 4),
        "exp_total": round((rs_h + ra_h + rs_a + ra_a) / 2.0, 3),
        "components": {
            "sp_home": round(home["sp"]["ra9"], 3), "sp_away": round(away["sp"]["ra9"], 3),
            "bp_home": round(home["bp"]["ra9"], 3), "bp_away": round(away["bp"]["ra9"], 3),
            "off_home": round(rs_h, 3), "off_away": round(rs_a, 3),
            "park": float(park), "hfa": float(hfa),
        },
    }


# ── 시즌 실행 (누수 없이 walk-forward) ─────────────────────────────────
#   🔴 경기 t 의 입력은 t **이전** 행만 쓴다. 4단계가 이것을 assert 한다.

def league_means(con, season: int) -> dict:
    """리그 평균 wOBA·RPG. 🔴 상수로 적지 않는다 — DB 에서 계산한다."""
    row = con.execute("""
        SELECT sum(b.bb), sum(b.hbp), sum(b.h - b.b2 - b.b3 - b.hr),
               sum(b.b2), sum(b.b3), sum(b.hr), sum(b.ab), sum(b.pa)
          FROM bat_app b JOIN games g ON g.game_id = b.game_id
         WHERE g.season = ?""", (season,)).fetchone()
    bb, hbp, b1, b2, b3, hr, ab, pa = [float(x or 0) for x in row]
    # 표준 wOBA 선형 가중(2020년대 계수)
    num = 0.69*bb + 0.72*hbp + 0.89*b1 + 1.27*b2 + 1.62*b3 + 2.10*hr
    den = max(pa, 1.0)
    runs = con.execute(
        "SELECT sum(home_runs + away_runs), count(*) FROM games WHERE season = ?",
        (season,)).fetchone()
    total, n = float(runs[0] or 0), max(int(runs[1] or 0), 1)
    return {"woba": num / den, "rpg": total / n / 2.0}


def _woba(rows) -> float | None:
    bb = sum(float(r["bb"] or 0) for r in rows)
    hbp = sum(float(r["hbp"] or 0) for r in rows)
    b2 = sum(float(r["b2"] or 0) for r in rows)
    b3 = sum(float(r["b3"] or 0) for r in rows)
    hr = sum(float(r["hr"] or 0) for r in rows)
    h = sum(float(r["h"] or 0) for r in rows)
    pa = sum(float(r["pa"] or 0) for r in rows)
    if pa <= 0:
        return None
    b1 = h - b2 - b3 - hr
    return (0.69*bb + 0.72*hbp + 0.89*b1 + 1.27*b2 + 1.62*b3 + 2.10*hr) / pa


def season_frame(con, season: int, *, hfa=0.04, park=1.0):
    """한 시즌을 시간순으로 예측한다. 반환: [(game_id, p_home, res, out)]."""
    con.row_factory = None
    lg = league_means(con, season)
    prior_ra9 = lg["rpg"]
    games = con.execute("""
        SELECT game_id, kickoff_utc, home, away, home_sp, away_sp,
               home_runs, away_runs
          FROM games WHERE season = ? AND home_runs IS NOT NULL
         ORDER BY kickoff_utc, game_id""", (season,)).fetchall()
    out = []
    for gid, ts, home, away, hsp, asp, hr_, ar_ in games:
        sides = {}
        for side, team, sp in (("home", home, hsp), ("away", away, asp)):
            starts = [dict(zip(("ip", "r"), r)) for r in con.execute("""
                SELECT p.ip, p.r FROM pitch_app p JOIN games g ON g.game_id = p.game_id
                 WHERE p.pitcher_id = ? AND p.role = 'SP' AND g.kickoff_utc < ?
                 ORDER BY g.kickoff_utc DESC LIMIT ?""",
                (sp, ts, SP_WINDOW)).fetchall()] if sp else []
            pen = [dict(zip(("ip", "r"), r)) for r in con.execute("""
                SELECT p.ip, p.r FROM pitch_app p JOIN games g ON g.game_id = p.game_id
                 WHERE p.team = ? AND p.role = 'RP' AND g.kickoff_utc < ?
                   AND g.kickoff_utc >= date(?, '-30 day')""",
                (team, ts, ts)).fetchall()]
            bats = [dict(zip(("bb", "hbp", "b2", "b3", "hr", "h", "pa"), r))
                    for r in con.execute("""
                SELECT b.bb, b.hbp, b.b2, b.b3, b.hr, b.h, b.pa
                  FROM bat_app b JOIN games g ON g.game_id = b.game_id
                 WHERE b.team = ? AND g.kickoff_utc < ?
                   AND g.kickoff_utc >= date(?, '-30 day')""",
                (team, ts, ts)).fetchall()]
            sides[side] = {
                "sp": sp_axis(starts, prior_ra9),
                "bp": bp_axis(pen, prior_ra9),
                "off": team_offense(_woba(bats), lg["woba"], lg),
            }
        pred = predict(sides["home"], sides["away"], park=park, hfa=hfa)
        out.append((gid, pred["p_home"], 1 if hr_ > ar_ else 0, pred))
    return out, lg
