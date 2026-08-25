"""기대득점(λ) 기반 확률 엔진 — 포아송(야구)·스켈람(축구).

학술 근거:
- Wharton MLB 예측 연구: 최고 수준 모델도 정확도 61.77%. 변수 중요도는
  ①OBP ②ISO ③WHIP/FIP 순으로 **타선 지표가 투수 지표보다 예측력이 높다.**
  선발 ERA 차이만 보던 기존 조정 방식은 근본적으로 약했다.
- 분데스리가 xG 연구: xG 기반 스켈람 모델이 시장 대비 log-loss 우위.
- MLB 모델링 표준: 팀별 기대득점 λ를 만들고 포아송으로 스코어 분포를 세운다.

설계 원칙:
- ERA는 운(수비·구장·시퀀싱)에 오염된 지표다. **SIERA > xFIP > FIP > ERA** 순으로 쓴다.
- 최근 30일 지표를 우선하고 시즌 누적은 보조로만 쓴다.
- 전 마켓(승패·런라인·토탈·F5 / 승무패·핸디·토탈·더블찬스·BTTS) 확률을 **같은 분포**에서
  뽑는다. 마켓마다 따로 근거를 만들지 않으므로 "근거 부족" 탈락이 사라진다.
- 과분산이 관찰되면 음이항으로 바꿀 수 있게 분포 생성을 한 곳(score_pmf)에 모았다.

계수는 전부 config에 있다. 임의로 바꾸지 말 것 — DISCIPLINE 5-1.
"""

import logging
import math
from dataclasses import dataclass, field

from app.config import get_settings

logger = logging.getLogger(__name__)

MAX_RUNS = 20          # 포아송 절단 지점 (야구 한 팀 20득점이면 사실상 상한)
MAX_GOALS = 10         # 축구


# ---------------------------------------------------------------- 분포

def poisson_pmf(lam: float, k: int) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam**k / math.factorial(k)


def negbin_pmf(lam: float, k: int, dispersion: float) -> float:
    """음이항 — 과분산(분산 > 평균)일 때 포아송 대신 쓴다.

    dispersion r이 클수록 포아송에 수렴한다. var = lam + lam^2/r.
    """
    r = max(1e-6, dispersion)
    p = r / (r + lam)
    return (math.gamma(k + r) / (math.factorial(k) * math.gamma(r))) * (p**r) * ((1 - p) ** k)


def score_pmf(lam: float, max_n: int, dispersion: float | None = None) -> list[float]:
    """득점 분포 — dispersion이 주어지면 음이항, 아니면 포아송.

    분포 생성을 여기 한 곳에 모아 두어야 과분산 관찰 시 전환이 한 줄로 끝난다.
    """
    fn = (lambda k: negbin_pmf(lam, k, dispersion)) if dispersion else (lambda k: poisson_pmf(lam, k))
    pmf = [fn(k) for k in range(max_n + 1)]
    total = sum(pmf)
    return [x / total for x in pmf] if total else pmf


# ---------------------------------------------------------------- λ 산출 (야구)

@dataclass
class LambdaResult:
    """기대득점과 산출 과정."""

    home: float
    away: float
    trace: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)   # 수집 실패로 건너뛴 보정
    usable: bool = True                                # 핵심 지표가 전무하면 False


def _ratio(value: float | None, league: float, exponent: float,
           lo: float = 0.75, hi: float = 1.35) -> float | None:
    """지표를 리그 평균 대비 계수로. 없으면 None(보정 건너뜀)."""
    if value is None or league <= 0:
        return None
    return max(lo, min(hi, (value / league) ** exponent))


def _suppression(pitcher: dict, s) -> tuple[float | None, str]:
    """상대 선발 억제력 계수 — SIERA > xFIP > FIP > ERA 순.

    값이 클수록(=투수가 나쁠수록) 우리 팀 기대득점이 올라간다.
    """
    for key, label in (("siera", "SIERA"), ("xfip", "xFIP"), ("fip", "FIP"),
                       ("era_recent", "최근5 ERA"), ("era_season", "시즌 ERA")):
        val = pitcher.get(key)
        if val is None:
            continue
        coef = _ratio(float(val), s.league_era, s.exp_pitcher,
                      lo=s.pit_coef_min, hi=s.pit_coef_max)
        return coef, f"{label} {float(val):.2f}"
    return None, ""


def _offense(block: dict, s) -> tuple[float | None, str]:
    """타선 계수 — Wharton 변수 중요도대로 wOBA > OBP > ISO 순."""
    for key, label, league in (("woba_30d", "wOBA", s.league_woba),
                               ("obp_30d", "OBP", s.league_obp),
                               ("woba", "wOBA(시즌)", s.league_woba),
                               ("obp", "OBP(시즌)", s.league_obp)):
        val = block.get(key)
        if val is not None:
            coef = _ratio(float(val), league, s.exp_offense,
                          lo=s.off_coef_min, hi=s.off_coef_max)
            return coef, f"{label} {float(val):.3f}"
    return None, ""


def mlb_lambdas(jg: dict, research: dict, settings=None) -> LambdaResult:
    """양 팀 기대득점 λ와 산출 과정.

    순서: 기본 λ → 타선 → 상대 선발 억제력 → 구장 → 날씨 → 불펜 → 좌우 스플릿 → 홈 이점
    """
    s = settings or get_settings()
    base = s.league_runs_per_game
    lam = {"home": base, "away": base}
    trace: list[str] = [f"기본 λ {base:.2f} (리그 평균 득점)"]
    missing: list[str] = []
    have_core = {"home": False, "away": False}

    off = {"home": research.get("home_offense") or {}, "away": research.get("away_offense") or {}}
    pit = {"home": research.get("home_pitcher") or {}, "away": research.get("away_pitcher") or {}}

    # ① 타선 (Wharton 변수 중요도 1·2위)
    for side in ("home", "away"):
        coef, label = _offense(off[side], s)
        if coef is None:
            missing.append(f"{side} 타선 지표(wOBA/OBP)")
            continue
        lam[side] *= coef
        have_core[side] = True
        trace.append(f"{side} 타선 {label} → ×{coef:.3f}")

    # ② 상대 선발 억제력 (SIERA/xFIP/FIP 우선, ERA는 최후)
    for side, opp in (("home", "away"), ("away", "home")):
        coef, label = _suppression(pit[opp], s)
        if coef is None:
            missing.append(f"{opp} 선발 억제 지표")
            continue
        lam[side] *= coef
        have_core[side] = True
        trace.append(f"{side} 상대 선발 {label} → ×{coef:.3f}")

    # ③ 구장 계수 (양 팀 공통)
    park = _park_factor(research, s)
    if park is None:
        missing.append("파크팩터")
    else:
        for side in ("home", "away"):
            lam[side] *= park
        trace.append(f"구장 파크팩터 → ×{park:.3f}")

    # ④ 날씨 (기온·바람)
    weather = _weather_factor(research, s)
    if weather is None:
        missing.append("날씨")
    else:
        for side in ("home", "away"):
            lam[side] *= weather
        trace.append(f"날씨 → ×{weather:.3f}")

    # ⑤ 불펜 — 선발이 짧으면 불펜 노출이 커진다
    for side, opp in (("home", "away"), ("away", "home")):
        coef, label = _bullpen_factor(pit[opp], research, opp, s)
        if coef is None:
            continue
        lam[side] *= coef
        trace.append(f"{side} 상대 불펜 {label} → ×{coef:.3f}")

    # ⑥ 좌우 스플릿 — 상대 선발 손잡이에 대한 우리 타선 최근 30일 성적
    for side, opp in (("home", "away"), ("away", "home")):
        coef, label = _handedness_factor(off[side], pit[opp], s)
        if coef is None:
            continue
        lam[side] *= coef
        trace.append(f"{side} 좌우 스플릿 {label} → ×{coef:.3f}")

    # ⑦ 홈 이점
    lam["home"] *= 1 + s.home_run_edge
    trace.append(f"홈 이점 → ×{1 + s.home_run_edge:.3f}")

    # 팀 기대득점을 현실 범위로 묶는다 — 단일 경기 λ 6.2 초과·2.8 미만은 모델 오류다
    for side in ("home", "away"):
        raw = lam[side]
        lam[side] = max(s.lam_min, min(s.lam_max, raw))
        if abs(lam[side] - raw) > 1e-9:
            trace.append(f"{side} λ 범위 절사 ({raw:.2f} → {lam[side]:.2f})")

    trace.append(f"최종 λ — {jg.get('home', '홈')} {lam['home']:.2f} / "
                 f"{jg.get('away', '원정')} {lam['away']:.2f}")
    usable = have_core["home"] and have_core["away"]
    if not usable:
        logger.warning("[scoring] 핵심 지표 부족으로 λ 산출 불가 game=%s missing=%s",
                       jg.get("game_id"), missing[:4])
    return LambdaResult(home=round(lam["home"], 3), away=round(lam["away"], 3),
                        trace=trace, missing=missing, usable=usable)


def _park_factor(research: dict, s) -> float | None:
    pf = research.get("park_factor")
    if pf is not None:
        try:
            return max(0.85, min(1.20, float(pf)))
        except (TypeError, ValueError):
            pass
    text = str(research.get("park") or "")
    if "타자" in text and "친화" in text:
        return s.park_hitter
    if "투수" in text and "친화" in text:
        return s.park_pitcher
    return None


def _weather_factor(research: dict, s) -> float | None:
    text = str(research.get("weather") or "")
    if not text:
        return None
    coef = 1.0
    import re

    m = re.search(r"(-?\d{1,2})\s*(?:도|℃|C)\b", text)
    if m:  # 기온이 높을수록 비거리 증가
        coef *= 1 + (int(m.group(1)) - 20) * s.weather_temp_per_deg
    if "맞바람" in text or "역풍" in text:
        coef *= 1 - s.weather_wind
    elif "뒷바람" in text or "순풍" in text:
        coef *= 1 + s.weather_wind
    return round(max(0.88, min(1.15, coef)), 4) if coef != 1.0 else None


def _bullpen_factor(opp_pitcher: dict, research: dict, opp_side: str, s) -> tuple[float | None, str]:
    """상대 선발이 짧으면 불펜 노출↑. 상대 불펜이 소모됐으면 우리 득점 기대↑."""
    coef, notes = 1.0, []
    ip = opp_pitcher.get("ip_avg_recent")
    if ip is not None and float(ip) < 5.0:
        coef *= 1 + s.bullpen_short_start
        notes.append(f"선발 평균 {float(ip):.1f}이닝")
    worn = str(research.get("bullpen_overused") or "")
    if worn in ("홈", "원정"):
        worn_side = "home" if worn == "홈" else "away"
        if worn_side == opp_side:
            coef *= 1 + s.bullpen_overuse_runs
            notes.append("상대 불펜 과소모")
    return (round(coef, 4), ", ".join(notes)) if notes else (None, "")


def _handedness_factor(offense: dict, opp_pitcher: dict, s) -> tuple[float | None, str]:
    """상대 선발 손잡이에 대한 우리 타선 최근 30일 성적."""
    hand = str(opp_pitcher.get("throws") or "").upper()
    key = {"L": "vs_lhp_woba", "R": "vs_rhp_woba"}.get(hand[:1] if hand else "")
    if not key:
        return None, ""
    val = offense.get(key)
    if val is None:
        return None, ""
    coef = _ratio(float(val), s.league_woba, s.exp_offense, lo=0.85, hi=1.20)
    label = f"vs {'좌완' if hand.startswith('L') else '우완'} wOBA {float(val):.3f}"
    return coef, label


# ---------------------------------------------------------------- 마켓 확률 (야구)

def mlb_market_probs(lam_home: float, lam_away: float, lines: dict | None = None,
                     dispersion: float | None = None, settings=None) -> dict:
    """[6] 같은 포아송 분포에서 전 마켓 확률을 **일괄** 산출.

    마켓마다 따로 근거를 만들 필요가 없어진다 — "근거 부족" 탈락의 원인이 사라진다.
    반환: {"h2h": {...}, "totals": {line: {...}}, "spreads": {...}, "f5": {...}}
    """
    s = settings or get_settings()
    ph = score_pmf(lam_home, MAX_RUNS, dispersion)
    pa = score_pmf(lam_away, MAX_RUNS, dispersion)

    win_h = tie = 0.0
    diff_pmf: dict[int, float] = {}
    total_pmf: dict[int, float] = {}
    for h, p_h in enumerate(ph):
        for a, p_a in enumerate(pa):
            joint = p_h * p_a
            if joint <= 0:
                continue
            if h > a:
                win_h += joint
            elif h == a:
                tie += joint
            diff_pmf[h - a] = diff_pmf.get(h - a, 0.0) + joint
            total_pmf[h + a] = total_pmf.get(h + a, 0.0) + joint

    # 야구는 무승부가 없다 — 연장 승부를 반반으로 배분
    p_home = win_h + tie / 2
    out: dict = {
        "h2h": {"home": round(p_home, 4), "away": round(1 - p_home, 4)},
        "totals": {}, "spreads": {}, "f5": {},
    }

    for line in (lines or {}).get("totals", []) or _default_total_lines(lam_home + lam_away):
        over = sum(p for t, p in total_pmf.items() if t > line)
        out["totals"][line] = {"Over": round(over, 4), "Under": round(1 - over, 4)}

    for line in (lines or {}).get("spreads", []) or (1.5,):
        # 홈 -1.5 = 홈이 2점 이상 차로 이김 / 원정 +1.5 = 그 여집합
        home_cover = sum(p for d, p in diff_pmf.items() if d > line)
        away_cover = sum(p for d, p in diff_pmf.items() if -d > line)
        out["spreads"][line] = {
            "home_minus": round(home_cover, 4), "away_plus": round(1 - home_cover, 4),
            "away_minus": round(away_cover, 4), "home_plus": round(1 - away_cover, 4),
        }

    # F5 — 선발이 던지는 5이닝까지의 부분 분포 (득점의 5/9)
    f5_h, f5_a = lam_home * s.f5_share, lam_away * s.f5_share
    ph5, pa5 = score_pmf(f5_h, MAX_RUNS, dispersion), score_pmf(f5_a, MAX_RUNS, dispersion)
    w5 = t5 = 0.0
    for h, p_h in enumerate(ph5):
        for a, p_a in enumerate(pa5):
            j = p_h * p_a
            if h > a:
                w5 += j
            elif h == a:
                t5 += j
    out["f5"] = {"home": round(w5, 4), "away": round(1 - w5 - t5, 4), "draw": round(t5, 4),
                 "lambda": {"home": round(f5_h, 3), "away": round(f5_a, 3)}}
    out["lambda"] = {"home": lam_home, "away": lam_away}
    return out


def _default_total_lines(expected_total: float) -> list[float]:
    """수집 라인이 없을 때 기대 총득점 주변 라인을 만든다."""
    center = round(expected_total * 2) / 2
    return [center - 1.0, center - 0.5, center, center + 0.5, center + 1.0]


# ---------------------------------------------------------------- 축구 (xG · 스켈람)

def soccer_lambdas(jg: dict, research: dict, settings=None) -> LambdaResult:
    """팀별 기대 xG = 공격 xG(최근 6경기) × 상대 수비 xGA × 홈/원정 계수."""
    s = settings or get_settings()
    base = s.league_goals_per_team
    lam = {"home": base, "away": base}
    trace = [f"기본 λ {base:.2f} (리그 평균 팀 득점)"]
    missing: list[str] = []
    have = {"home": False, "away": False}

    src = {"home": research.get("home_recent_form") or {}, "away": research.get("away_recent_form") or {}}
    for side, opp in (("home", "away"), ("away", "home")):
        xg = src[side].get("xg6")
        xga = src[opp].get("xga6")
        if xg is None and xga is None:
            missing.append(f"{side} xG/상대 xGA")
            continue
        if xg is not None:
            coef = _ratio(float(xg), base, 1.0, lo=0.5, hi=1.8)
            lam[side] *= coef
            have[side] = True
            trace.append(f"{side} 공격 xG {float(xg):.2f} → ×{coef:.3f}")
        if xga is not None:
            coef = _ratio(float(xga), base, 1.0, lo=0.5, hi=1.8)
            lam[side] *= coef
            have[side] = True
            trace.append(f"{side} 상대 수비 xGA {float(xga):.2f} → ×{coef:.3f}")

    lam["home"] *= 1 + s.home_goal_edge
    trace.append(f"홈 이점 → ×{1 + s.home_goal_edge:.3f}")
    trace.append(f"최종 λ — {jg.get('home', '홈')} {lam['home']:.2f} / "
                 f"{jg.get('away', '원정')} {lam['away']:.2f}")
    return LambdaResult(round(lam["home"], 3), round(lam["away"], 3), trace, missing,
                        have["home"] and have["away"])


def soccer_market_probs(lam_home: float, lam_away: float, lines: dict | None = None,
                        dispersion: float | None = None) -> dict:
    """스켈람(두 포아송의 차)에서 승·무·패를 **자연 산출**한다.

    무승부를 따로 추정하지 않는다 — 분포에서 P(diff == 0)로 나온다.
    """
    ph = score_pmf(lam_home, MAX_GOALS, dispersion)
    pa = score_pmf(lam_away, MAX_GOALS, dispersion)
    diff: dict[int, float] = {}
    total: dict[int, float] = {}
    btts = 0.0
    for h, p_h in enumerate(ph):
        for a, p_a in enumerate(pa):
            j = p_h * p_a
            if j <= 0:
                continue
            diff[h - a] = diff.get(h - a, 0.0) + j
            total[h + a] = total.get(h + a, 0.0) + j
            if h >= 1 and a >= 1:
                btts += j

    p_home = sum(p for d, p in diff.items() if d > 0)
    p_draw = diff.get(0, 0.0)
    p_away = sum(p for d, p in diff.items() if d < 0)
    out: dict = {
        "h2h": {"home": round(p_home, 4), "draw": round(p_draw, 4), "away": round(p_away, 4)},
        "dc": {
            "home": round(p_home + p_draw, 4),      # 1X
            "away": round(p_away + p_draw, 4),      # X2
            "12": round(p_home + p_away, 4),        # 12
        },
        "btts": {"Yes": round(btts, 4), "No": round(1 - btts, 4)},
        "totals": {}, "spreads": {},
        "lambda": {"home": lam_home, "away": lam_away},
    }
    for line in (lines or {}).get("totals", []) or (1.5, 2.5, 3.5):
        over = sum(p for t, p in total.items() if t > line)
        out["totals"][line] = {"Over": round(over, 4), "Under": round(1 - over, 4)}
    for line in (lines or {}).get("spreads", []) or (0.5, 1.5):
        home_cover = sum(p for d, p in diff.items() if d > line)
        away_cover = sum(p for d, p in diff.items() if -d > line)
        out["spreads"][line] = {
            "home_minus": round(home_cover, 4), "away_plus": round(1 - home_cover, 4),
            "away_minus": round(away_cover, 4), "home_plus": round(1 - away_cover, 4),
        }
    return out


# ---------------------------------------------------------------- [1] 상한/하한

def prob_bounds(sport: str, settings=None) -> tuple[float, float]:
    """§0 종목별 승률 상·하한. 축구는 3-way라 하한이 비대칭이다."""
    s = settings or get_settings()
    if sport == "mlb":
        return s.min_win_prob_mlb, s.max_win_prob_mlb
    return s.min_win_prob_soccer, s.max_win_prob_soccer


def cap_probability(p: float, sport: str, settings=None) -> tuple[float, str | None]:
    """§0 승률 절사 — 계산 오류를 화면에 내보내지 않는다.

    근거: 운의 비중이 MLB 27.8%, EPL 31.4%다. 완벽한 정보를 가져도 MLB 단일 경기
    예측 상한은 약 72%이고 학계 최고 모델은 61.77%다. 상한 초과는 '강한 픽'이 아니라
    **모델이 틀렸다는 신호**다.
    반환: (절사된 확률, 표기 문구 또는 None)
    """
    lo, hi = prob_bounds(sport, settings)
    if p > hi:
        return hi, f"추정 상한 적용(원값 {p:.0%})"
    if p < lo:
        return lo, f"추정 하한 적용(원값 {p:.0%})"
    return p, None


def edge_vs_market(p: float | None, odds: float | None) -> float | None:
    """§0 시장 대비 엣지 = 우리 확률 − 배당 환산 확률."""
    if p is None or not odds:
        return None
    return round(p - 1.0 / float(odds), 4)


def edge_exceeds_limit(p: float | None, odds: float | None, settings=None) -> tuple[bool, float | None]:
    """§0 엣지가 현실 상한(5%)을 넘는가.

    Starlizard(분석가 200명)의 시장 대비 엣지가 1~2%다. 5% 초과는 우리가 더 똑똑한
    것이 아니라 데이터가 틀린 것이다 — 추천에서 빼고 검증 대상으로 분리한다.
    """
    s = settings or get_settings()
    e = edge_vs_market(p, odds)
    return (e is not None and e > s.max_edge_vs_market), e


async def record_cap_hit(redis, date: str, game_id, raw: float, sport: str) -> int:
    """[1] 상한 초과를 일자별로 집계. 하루 임계 이상이면 로직 점검 경고를 띄운다."""
    s = get_settings()
    key = f"prob_cap_hits:{date}"
    n = await redis.incr(key)
    await redis.expire(key, 86400 * 14)
    logger.warning("[scoring] 승률 상한 초과 game=%s sport=%s 원값=%.1f%% (금일 %d건)",
                   game_id, sport, raw * 100, n)
    if n == s.prob_cap_alert_n:
        logger.error("[scoring] ⚠️ 승률 상한 초과 %d건 — 확률 계산 로직 점검 필요", n)
    return n


async def cap_alert_count(redis, date: str) -> int:
    v = await redis.get(f"prob_cap_hits:{date}")
    return int(v) if v else 0


# ---------------------------------------------------------------- [4] 홈/원정 비대칭

def away_penalty_applies(market: str, side: str, jg: dict) -> bool:
    """원정팀을 사는 픽인가 — 승패·더블찬스·핸디캡에서 원정 사이드."""
    return market in ("h2h", "dc", "spreads") and side == jg.get("away")


def required_prob(market: str, side: str, jg: dict, settings=None) -> float:
    """[4] 이 픽에 요구되는 승률 하한.

    분데스리가 연구: 홈 승 베팅 ROI +10~15%, 원정 베팅 ROI -17%로 일관 손실.
    원정 픽은 같은 승률이어도 실현 수익이 나빴으므로 임계를 5%p 높인다.
    """
    s = settings or get_settings()
    base = s.min_win_prob
    return base + s.away_prob_penalty if away_penalty_applies(market, side, jg) else base


def is_away_underdog(market: str, side: str, jg: dict, odds: float | None) -> bool:
    """[4] 원정 언더독 — 통계적으로 가장 불리한 유형."""
    if not away_penalty_applies(market, side, jg) or not odds:
        return False
    home_odds = (jg.get("best_odds") or {}).get(jg.get("home"))
    return bool(home_odds and odds > home_odds)


# ---------------------------------------------------------------- 파이프라인 진입점

def game_distribution(jg: dict, research: dict, sport: str, settings=None) -> dict | None:
    """경기 1건의 λ와 전 마켓 확률. 핵심 지표가 없으면 None(=데이터 부족).

    반환: {"lam": LambdaResult, "probs": {...}, "capped": str|None, "raw_home": float}
    """
    s = settings or get_settings()
    lam = mlb_lambdas(jg, research, s) if sport == "mlb" else soccer_lambdas(jg, research, s)
    if not lam.usable:
        return None
    lines = {
        "totals": sorted({a["line"] for a in jg.get("alt_markets") or []
                          if a["market"] == "totals" and a.get("line") is not None}),
        "spreads": sorted({abs(a["line"]) for a in jg.get("alt_markets") or []
                           if a["market"] == "spreads" and a.get("line") is not None}),
    }
    probs = (mlb_market_probs if sport == "mlb" else soccer_market_probs)(
        lam.home, lam.away, lines or None, s.score_dispersion,
        **({"settings": s} if sport == "mlb" else {}))
    raw_home = probs["h2h"]["home"]
    capped_home, note = cap_probability(raw_home, sport, s)
    if note:
        # 절사분을 반대편에 되돌려 합이 유지되게 한다 (축구는 무승부 질량 보존)
        shift = capped_home - raw_home
        probs["h2h"]["home"] = round(capped_home, 4)
        away_key = "away"
        probs["h2h"][away_key] = round(max(0.02, probs["h2h"][away_key] - shift), 4)
    return {"lam": lam, "probs": probs, "capped": note, "raw_home": raw_home}


def market_probability(dist: dict, market: str, side: str, line: float | None,
                       jg: dict) -> float | None:
    """[6] 분포에서 해당 마켓·사이드 확률을 꺼낸다. 없으면 None.

    마켓마다 별도 근거를 만들 필요가 없다 — 전부 같은 분포에서 나온다.
    """
    if not dist:
        return None
    probs = dist["probs"]
    home, away = jg.get("home"), jg.get("away")
    if market == "h2h":
        if side == home:
            return probs["h2h"].get("home")
        if side == away:
            return probs["h2h"].get("away")
        if side == "Draw":
            return probs["h2h"].get("draw")
        return None
    if market == "dc":
        dc = probs.get("dc") or {}
        return dc.get("home") if side == home else dc.get("away") if side == away else dc.get("12")
    if market == "btts":
        return (probs.get("btts") or {}).get("Yes" if side in ("Yes", "예") else "No")
    if market == "totals" and line is not None:
        block = probs.get("totals", {}).get(line) or _nearest_line(probs.get("totals"), line)
        return block.get(side) if block else None
    if market == "spreads" and line is not None:
        block = (probs.get("spreads", {}).get(abs(line))
                 or _nearest_line(probs.get("spreads"), abs(line)))
        if not block:
            return None
        if side == home:
            return block["home_minus"] if line < 0 else block["home_plus"]
        if side == away:
            return block["away_minus"] if line < 0 else block["away_plus"]
        return None
    if market == "f5":
        f5 = probs.get("f5") or {}
        return f5.get("home") if side == home else f5.get("away") if side == away else None
    return None


def _nearest_line(table: dict | None, line: float) -> dict | None:
    if not table:
        return None
    key = min(table, key=lambda k: abs(float(k) - line))
    return table[key] if abs(float(key) - line) <= 0.5 else None
