"""마켓 풀 엔진 — 전 마켓 후보 생성 + 2-소스 룰 + 괴리 검증 + 시장 수축(λ).

적중 품질 패치의 핵심 규칙 (2026-08-24):
- 추천 자격 = 서로 독립인 근거 축 2개 이상 지지
  (①올 시즌 실데이터 ②검증된 전문가 픽 ③모델 확률 ④시장 방향)
  → "모델 단독" 픽은 어떤 EV가 나와도 추천 금지.
- 모델-시장 괴리 ≥10%p + 원인 미검증(전문가 미지지) → "시장이 아는 정보가 있을
  가능성" 라벨로 제외.
- 축구 추천 기본 마켓은 저분산(더블찬스·+1.5 핸디캡). 승패 단식은 신뢰도 high +
  2-소스 충족 시에만.
- p_final = λ*p_market + (1-λ)*p_ensemble. λ는 리그 데이터 성숙도 연동
  (스탯 풍부 0.3 / 빈약·시즌 초 0.6), 채점 300픽부터 리그별 실측 재추정.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- 시장 수축(λ)

RICH_LEAGUES = {"MLB", "EPL", "라리가", "세리에A", "분데스리가"}
LAMBDA_RICH, LAMBDA_POOR = 0.3, 0.6
GAP_UNVERIFIED = 0.10          # 모델-시장 괴리 검증 임계 (10%p)
CALIBRATION_MIN_PICKS = 300    # 리그별 λ 실측 재추정에 필요한 채점 픽 수


def shrink_lambda(league: str | None) -> float:
    return LAMBDA_RICH if league in RICH_LEAGUES else LAMBDA_POOR


def shrink(p_ensemble: float, p_market: float | None, league: str | None) -> float:
    """앙상블 확률을 시장 쪽으로 수축 — 시장 확률이 없으면 수축 불가(원값)."""
    if p_market is None:
        return p_ensemble
    lam = shrink_lambda(league)
    return lam * p_market + (1 - lam) * p_ensemble



def synth_dc_odds(o_side: float, o_draw: float) -> float:
    """3-way 배당에서 더블찬스 배당 합성: 1/o_dc = 1/o1 + 1/oX."""
    return round((o_side * o_draw) / (o_side + o_draw), 2)


# ---------------------------------------------------------------- 근거 축 판정

def _form_score(season: dict | None) -> float | None:
    """순위표 폼 점수 = 최근 5경기 승점 + 경기당 승점*2."""
    if not season:
        return None
    form = season.get("form") or ""
    fp = sum({"W": 3, "D": 1}.get(c, 0) for c in form.upper())
    played = season.get("played") or 0
    ppg = (season.get("points") or 0) / played if played else 0.0
    pos_bonus = (20 - season["position"]) * 0.3 if season.get("position") else 0.0
    if not form and not played and not season.get("position"):
        return None  # 빈 딕셔너리는 데이터로 치지 않는다
    return fp + ppg * 2 + pos_bonus


def _standing_win_pct(row: dict | None) -> float | None:
    """순위표 승률 = 승/(승+패). 무승부는 분모에서 뺀다 (KBO 공식과 같음)."""
    if not row:
        return None
    w, l = row.get("w"), row.get("l")
    if w is None or l is None:
        return None
    den = w + l
    if den <= 0:
        return None
    return w / den


def _research_pitcher_era(research: dict, side: str) -> float | None:
    blk = (research or {}).get(f"{side}_pitcher") or {}
    era = blk.get("era_season")
    if era is None:
        era = blk.get("era_recent")
    try:
        return float(era) if era is not None else None
    except (TypeError, ValueError):
        return None


def _research_form_season(research: dict, side: str) -> dict | None:
    """크롤링 순위·최근 폼을 축구 순위표 폼 점수와 같은 모양으로 맞춘다."""
    st = (research or {}).get(f"{side}_standing") or {}
    form = ((research or {}).get(f"{side}_recent_form") or {}).get("form")
    played = st.get("played")
    if played is None and st.get("w") is not None and st.get("l") is not None:
        played = st["w"] + st["l"] + (st.get("d") or 0)
    row = {
        "form": form or "",
        "position": st.get("rank") or ((research or {}).get(f"{side}_recent_form") or {}).get("rank"),
        "played": played or 0,
        "points": None,
    }
    if not row["form"] and not row["played"] and not row["position"]:
        return None
    return row


def _season_edge(jg: dict) -> float | None:
    """올 시즌 실데이터 기준 홈팀 우위 점수 (>0 홈 우세). 데이터 없으면 None.

    MLB는 stats.win_pct, 축구는 stats 순위표, KBO·NPB는 research의 크롤링
    순위표(승패)·선발 ERA. λ 입력(OBP·분포)은 쓰지 않는다 — 같은 숫자로
    모델 축과 실데이터 축을 만들면 2-소스 룰이 붕괴한다.
    """
    st = jg.get("stats") or {}
    hw, aw = st.get("home_win_pct"), st.get("away_win_pct")
    if hw is not None and aw is not None:  # MLB: 팀 승률 + 선발 ERA
        edge = (hw - aw) * 10
        he, ae = st.get("home_pitcher_era"), st.get("away_pitcher_era")
        if he is not None and ae is not None:
            edge += (ae - he)  # 상대 ERA가 높을수록 홈 우세
        return edge
    hs, as_ = _form_score(st.get("home_season")), _form_score(st.get("away_season"))
    if hs is not None and as_ is not None:
        return hs - as_
    rs = jg.get("research") or {}
    hw = _standing_win_pct(rs.get("home_standing"))
    aw = _standing_win_pct(rs.get("away_standing"))
    if hw is not None and aw is not None:
        edge = (hw - aw) * 10
        he = _research_pitcher_era(rs, "home")
        ae = _research_pitcher_era(rs, "away")
        if he is not None and ae is not None:
            edge += (ae - he)
        return edge
    sport = (jg.get("sport") or "").lower()
    if sport in ("kbo", "npb"):
        hs = _form_score(_research_form_season(rs, "home"))
        as_ = _form_score(_research_form_season(rs, "away"))
        if hs is not None and as_ is not None:
            return hs - as_
    return None


def _research_has_team_numbers(jg: dict) -> bool:
    """순위 우위를 못 내도, 타선·선발 숫자가 양쪽에 있으면 '실데이터 0건'이 아니다."""
    rs = jg.get("research") or {}

    def offense(side: str) -> bool:
        blk = rs.get(f"{side}_offense") or {}
        return any(blk.get(k) is not None for k in
                   ("obp_30d", "obp", "avg", "ops", "xwoba_30d"))

    def pitcher(side: str) -> bool:
        return _research_pitcher_era(rs, side) is not None

    return (offense("home") and offense("away")) or (pitcher("home") and pitcher("away"))


def has_season_data(jg: dict) -> bool:
    """판정 입력에 올 시즌 실데이터가 1건이라도 있는가 ([4d] 데이터 제로 강등 기준)."""
    return _season_edge(jg) is not None or _research_has_team_numbers(jg)


def _expected_total(jg: dict) -> float | None:
    """양 팀 순위표 득실로 예상 총득점 추정 (축구 토탈 실데이터 축).

    야구는 시즌 경기당 득점(크롤링) 합. λ 분포의 기대득점과는 다른 숫자다.
    """
    st = jg.get("stats") or {}
    vals = []
    for key in ("home_season", "away_season"):
        s = st.get(key)
        if not s or not s.get("played"):
            break
        vals.append((s.get("gf", 0) + s.get("ga", 0)) / s["played"])
    else:
        if len(vals) == 2:
            return sum(vals) / 2
    rs = jg.get("research") or {}
    rpg = []
    for side in ("home", "away"):
        v = (rs.get(f"{side}_offense") or {}).get("runs_per_game")
        if v is None:
            return None
        try:
            rpg.append(float(v))
        except (TypeError, ValueError):
            return None
    return sum(rpg)


def _axis_data(jg: dict, market: str, side: str, line: float | None) -> bool:
    edge = _season_edge(jg)
    if market in ("h2h", "dc"):
        if edge is None:
            return False
        is_home = side == jg["home"]
        if market == "dc":  # 더블찬스는 열세만 아니면 지지
            return edge > -1.0 if is_home else edge < 1.0
        return edge > 0.5 if is_home else edge < -0.5
    if market == "totals" and line is not None:
        exp = _expected_total(jg)
        if exp is None:
            return False
        return exp > line + 0.3 if side == "Over" else exp < line - 0.3
    if market == "spreads" and line is not None:
        if edge is None:
            return False
        is_home = side == jg["home"]
        team_edge = edge if is_home else -edge
        if line > 0:   # +1.5 언더독 커버: 큰 열세만 아니면 지지
            return team_edge > -2.0
        return team_edge > 2.0  # -1.5 는 강한 우위 필요
    return False


def _predicted_totals(jg: dict) -> list[int]:
    """전문가 스코어 예측('2-1' 등) → 총득점 목록 (토탈 마켓 지지 판정용)."""
    out = []
    for s in (jg.get("stats") or {}).get("predicted_scores") or []:
        m = re.match(r"\s*(\d+)\s*[-:]\s*(\d+)", str(s))
        if m:
            out.append(int(m.group(1)) + int(m.group(2)))
    return out


EXPERT_STRONG_N = 3   # [4] 같은 방향 전문가가 이 수 이상이면 독립 축 2개로 계산


def expert_support_count(jg: dict, market: str, side: str, line: float | None) -> int:
    """[4] 이 마켓·사이드를 지지하는 전문가 수.

    전문가가 몰리면 그 자체로 독립적인 근거가 된다 — 8명이 같은 방향을 봤는데
    '전문가 단독 1축'으로 탈락시키면 실제 신호를 버리게 된다.
    """
    n = 0
    for ep in jg.get("expert_picks", []):
        if ep.get("adopted") is False:      # 해당 마켓 전적 마이너스는 세지 않는다
            continue
        parts = (ep.get("pick") or "").split(":")
        if len(parts) < 2:
            continue
        m, s = parts[0], parts[1]
        try:
            ln = float(parts[2]) if len(parts) > 2 else None
        except ValueError:
            ln = None
        if m == "h2h" and s == side and (
            market in ("h2h", "dc")
            or (market == "spreads" and line is not None and line > 0)
        ):
            n += 1
        elif m == market == "totals" and s == side and (
            line is None or ln is None or abs(ln - line) <= 0.5
        ):
            n += 1
        elif m == market == "spreads" and s == side and (
            ln is None or line is None or abs(ln - line) <= 0.5
        ):
            n += 1
    return n


def _axis_expert(jg: dict, market: str, side: str, line: float | None) -> bool:
    # 토탈은 전문가 스코어 예측(2건 이상 같은 방향)도 지지 근거로 인정
    if market == "totals" and line is not None:
        totals = _predicted_totals(jg)
        over_n = sum(1 for x in totals if x > line)
        under_n = sum(1 for x in totals if x < line)
        if side == "Over" and over_n >= 2 and over_n > under_n:
            return True
        if side == "Under" and under_n >= 2 and under_n > over_n:
            return True
    for ep in jg.get("expert_picks", []):
        parts = (ep.get("pick") or "").split(":")
        if len(parts) < 2:
            continue
        m, s = parts[0], parts[1]
        ln = float(parts[2]) if len(parts) > 2 else None
        if m == "h2h" and s == side:
            # 승 픽은 같은 팀 더블찬스·+1.5 커버도 지지한다
            if market in ("h2h", "dc"):
                return True
            if market == "spreads" and line is not None and line > 0:
                return True
        if m == market == "totals" and s == side and (
            line is None or ln is None or abs(ln - line) <= 0.5
        ):
            return True
        if m == market == "spreads" and s == side and (
            ln is None or line is None or abs(ln - line) <= 0.5
        ):
            return True
    return False


def _axis_model(jg: dict, market: str, side: str) -> bool:
    # [6] 기대득점 분포에서 확률이 나온 마켓은 모델이 실제로 평가한 것이다.
    #     (분포 도입 전에는 핸디캡·토탈에 모델 축이 없어 전 마켓이 "2-소스 미달"로 탈락했다)
    if jg.get("distribution") is not None:
        return True
    if not jg.get("model_valid"):
        return False
    p3 = jg.get("p_model3")
    is_home = side == jg["home"]
    if market == "h2h":
        if p3:
            return (p3[0] if is_home else p3[2]) > 0.5
        return jg["p_model"] > 0.5 if is_home else jg["p_model"] < 0.5
    if market == "dc" and p3:
        return (p3[0] + p3[1] if is_home else p3[2] + p3[1]) >= 0.60
    return False  # 핸디캡·토탈은 모델(승무패 Elo/휴리스틱) 범위 밖


def support_axes(jg: dict, market: str, side: str, line: float | None,
                 p_market_side: float | None) -> dict:
    """후보 픽의 독립 근거 축 판정.

    [4] 전문가가 EXPERT_STRONG_N명 이상 같은 방향이면 expert_strong을 세워
    축 수를 2로 계산한다 (전문가 쏠림 자체가 독립 신호다).
    시장 축은 판정 철학 교체(시장 배제)로 더 이상 세지 않는다.
    """
    n_expert = expert_support_count(jg, market, side, line)
    return {
        "data": _axis_data(jg, market, side, line),
        "expert": bool(n_expert) or _axis_expert(jg, market, side, line),
        "expert_strong": n_expert >= EXPERT_STRONG_N,
        "model": _axis_model(jg, market, side),
    }


AXIS_KR = {"data": "실데이터", "expert": "전문가", "model": "모델", "market": "시장"}


def axes_label(axes: dict) -> str:
    on = [AXIS_KR[k] for k, v in axes.items() if v and k in AXIS_KR]
    if axes.get("expert_strong"):
        on = [f"전문가 다수({EXPERT_STRONG_N}명+)" if x == "전문가" else x for x in on]
    return "+".join(on) if on else "지지 축 없음"


def axes_count(axes: dict) -> int:
    """독립 축 수 — 전문가 다수 지지는 2축으로 센다 ([4])."""
    n = sum(1 for k in ("data", "expert", "model") if axes.get(k))
    if axes.get("expert_strong"):
        n += 1
    return n


# ---------------------------------------------------------------- 후보 생성·승인

# [4] 종목별 마켓 용어 — 야구엔 더블찬스가 없고, 핸디캡은 '런라인'이라 부른다
REVIEWED_MARKETS_KR = "승패·더블찬스·핸디캡·언더오버"
REVIEWED_MARKETS_BY_SPORT = {
    "mlb": "승패·런라인·언더오버",
    "soccer": "승패·더블찬스·핸디캡·언더오버",
}


def reviewed_markets_kr(sport: str | None = None) -> str:
    """검토 대상 마켓 표기 — 종목 미상(혼합 슬레이트)이면 전체 표기."""
    return REVIEWED_MARKETS_BY_SPORT.get(sport or "", REVIEWED_MARKETS_KR)


def spread_desc(sport: str, side_kr: str, line: float) -> str:
    """핸디캡 마켓 표기 — 야구는 런라인, 축구는 핸디."""
    from app.engine.scoring import BASEBALL_SPORTS

    label = "런라인" if sport in BASEBALL_SPORTS else "핸디"
    return f"{side_kr} {label} {line:+g}"


GRADE_GREEN, GRADE_YELLOW, GRADE_RED, GRADE_BLANK = "🟢", "🟡", "🔴", "⚪"
GRADE_RANK = {GRADE_GREEN: 3, GRADE_YELLOW: 2, GRADE_RED: 1, GRADE_BLANK: 0}

# 마켓 보드는 **항상 전 마켓을 행으로** 출력한다. 배당이 없으면 행을 지우는 대신
# '배당 미수집'으로 남긴다 — "평가 가능한 마켓 없음"이라는 출력은 금지다.
STARS_BY_GRADE = {GRADE_GREEN: 4, GRADE_YELLOW: 3, GRADE_RED: 1, GRADE_BLANK: 0}


def row_stars(c: dict, confidence: str | None = None) -> int:
    """[3] 마켓별 신뢰도 ★ 개수 (0~5). 판정 신뢰도가 높으면 한 칸 올린다."""
    stars = STARS_BY_GRADE.get(c.get("grade"), 0)
    if stars and confidence == "high":
        stars = min(5, stars + 1)
    elif stars > 1 and confidence == "low":
        stars -= 1
    return stars


def grade_candidate(c: dict, settings=None) -> tuple[str, str]:
    """[§8-18] 마켓 1건의 등급 — **승률만으로** 판정한다.

    🟢 승률 62%↑ / 🟡 58~62% / 🔴 58% 미만 / ⚪ 확률 미산출

    제거된 것과 이유:
      - 배당 하한(min_odds) → 시장 기준이다. 우리가 답할 질문이 아니다.
      - 시장 괴리 상한(5%)   → **우리 판단을 시장으로 재단했다.** 실사고: 판정이
        구체적 근거로 지바 롯데 70%를 냈는데 시장 환산 37%와 어긋난다는 이유로
        '데이터 오류'로 삭제됐다. 그러면 시장을 넘어설 방법이 영원히 없다.
      - 1만원당 수익 표기     → 봇은 돈 얘기를 하지 않는다.
    ⚠️ 라인(핸디 ±1.5·토탈 8.5)은 남는다 — 가격이 아니라 **질문**이다.
    """
    from app.config import get_settings

    s = settings or get_settings()
    prob = c.get("p")
    if prob is None:
        return GRADE_BLANK, c.get("reject_reason") or "확률 미산출"
    if not c.get("approved"):
        return GRADE_RED, c.get("reject_reason") or "제외"

    # [4] 원정 픽은 임계를 5%p 높게 — 분데스리가 연구: 원정 승률 실현이 나빴다
    need = c.get("required_prob") or s.min_win_prob
    away_tag = " (원정 픽 — 임계 +5%p)" if need > s.min_win_prob else ""
    if prob < need:
        return GRADE_RED, f"승률 {prob:.0%} < 하한 {need:.0%}{away_tag}"

    dog = " ⚠️원정 언더독 — 통계적으로 가장 불리한 유형" if c.get("away_underdog") else ""
    axes_note = "" if c.get("two_source", True) else f" (근거 {c.get('axes_kr')} 1축)"
    if prob >= s.signal_green_prob + (need - s.min_win_prob):
        grade = GRADE_YELLOW if axes_note else GRADE_GREEN
        return grade, f"승률 {prob:.0%}{away_tag}{dog}{axes_note}"
    return GRADE_YELLOW, f"승률 {prob:.0%}{away_tag}{dog}{axes_note}"


def board_grade(board: list[dict]) -> str:
    """[A-1] 경기 신호등 = 전 마켓 중 최고 등급. 보드가 비면 🔴."""
    if not board:
        return GRADE_RED
    return max((c.get("grade") or GRADE_RED for c in board), key=lambda g: GRADE_RANK.get(g, 0))


def best_market(board: list[dict]) -> dict | None:
    """[A-1][A-4] 기본층이 인용할 대표 마켓 — 등급 우선, 같은 등급이면 EV 최대."""
    if not board:
        return None
    return max(board, key=lambda c: (GRADE_RANK.get(c.get("grade"), 0), c.get("ev") or -9))


def rejection_summary(board: list[dict], unpriced: list[str] | None = None) -> str:
    """[A-1] 전 마켓 탈락 시 검토 목록과 사유를 한 줄로.

    예: "승패 EV -12% / 언더 8.5 근거 부족 / 핸디 배당 미수집"
    보드가 이미 배당 미수집 행을 포함하므로 unpriced는 보조 인자다(하위호환).
    """
    parts = []
    for c in board[:6]:
        note = "배당 미수집" if c.get("placeholder") else (c.get("grade_note") or "제외")
        parts.append(f"{c['desc']} {note}")
    seen = {c["desc"] for c in board}
    parts += [f"{m} 배당 미수집" for m in (unpriced or []) if m not in seen]
    return " / ".join(parts) if parts else "평가한 마켓 없음"


def build_candidates(jg: dict, sport: str, p_final: dict[str, float]) -> list[dict]:
    """한 경기의 전 마켓 후보 목록. p_final: h2h 사이드별 수축 완료 앙상블 확률.

    각 후보: {market, side, line, desc, odds, p, ev, basis, axes, approved, reject_reason}
    승인/제외는 마켓 단위로 독립 판정한다.
    """
    from app.bot.aliases import kr_team

    market_probs = jg.get("market_probs") or {}
    best_odds = jg.get("best_odds") or {}
    p_draw_m = market_probs.get("Draw")
    out: list[dict] = []

    stale = bool(jg.get("odds_stale"))   # [A-3] 오래된 스냅샷 폴백은 라벨을 붙인다
    dist = jg.get("distribution")        # [6] 포아송/스켈람 분포 — 전 마켓 확률의 단일 소스

    def add(market, side, line, desc, odds, p, basis):
        # [§8-27] **배당이 없어도 행을 만든다.**
        #   돈·시장을 판정에서 뺐으므로(§8-18) 배당은 더 이상 마켓 존재의 전제가
        #   아니다. 종전에는 `if not odds: return`이라 Odds API가 죽으면 마켓 보드가
        #   통째로 비었다 — 우리가 확률을 낼 수 있는데도 아무것도 못 보여줬다.
        #   배당은 "라인이 어디 그어졌나"를 알려줄 뿐이며, 없으면 λ 기본 라인을 쓴다.
        # [6] 토탈·핸디는 분포가 단일 소스. 승패(h2h)는 이미 p_final =
        #     0.5*분포 + 0.5*판정 으로 들어온다. 여기서 분포로 덮으면
        #     Claude가 승률에 안 섞인다 (KBO는 배당이 없어 이 경로가 전부다).
        if dist is not None:
            from app.engine.scoring import market_probability

            p_dist = market_probability(dist, market, side, line, jg)
            if p_dist is not None and (p is None or market != "h2h"):
                p, basis = p_dist, "기대득점 분포"
        if stale and odds:
            desc = f"{desc} (개장 배당)"
        if p is None:
            # 확률 추정 근거가 없다 — 행은 남기고 '근거 부족'으로 표기
            out.append({
                "market": market, "side": side, "line": line, "desc": desc,
                "odds": round(float(odds), 2) if odds else None,
                "p": None, "ev": None, "basis": basis,
                "axes": {}, "axes_n": 0, "axes_kr": "없음",
                "reject_reason": "근거 부족 — 확률 추정 불가",
            })
            return
        p = max(0.02, min(0.98, p))
        pm_side = None
        if market == "h2h":
            pm_side = market_probs.get(side)
        elif market == "dc" and side in market_probs and p_draw_m is not None:
            pm_side = market_probs[side] + p_draw_m
        elif market in ("spreads", "totals"):
            pm_side = p if basis == "시장 기준" else None
        axes = support_axes(jg, market, side, line, pm_side)
        out.append({
            "market": market, "side": side, "line": line, "desc": desc,
            "odds": round(float(odds), 2) if odds else None, "p": round(p, 4),
            # ev는 배당이 있어야 계산된다 — 판정에는 쓰지 않는 참고값이다(§8-18)
            "ev": round(p * float(odds) - 1, 4) if odds else None,
            "basis": basis,
            "axes": axes, "axes_n": axes_count(axes), "axes_kr": axes_label(axes),
        })

    # 1) 승패 (h2h) — 판정을 못 받아 p_final이 없어도 배당이 있으면 행은 남긴다
    h2h_sides = [jg["home"], jg["away"]]
    if sport == "soccer" and best_odds.get("Draw"):
        h2h_sides.insert(1, "Draw")
    for side in h2h_sides:
        desc = "무승부" if side == "Draw" else f"{kr_team(side)} 승"
        # [§8-27] 배당이 없어도 확률은 낼 수 있다 — 행을 만든다
        # λ 변별이 없어 승패를 판정 단독으로 쓴 경기는 근거 라벨을 숨기지 않는다.
        h2h_basis = "판정" if jg.get("h2h_lambda_unused") else "앙상블"
        add("h2h", side, None, desc, best_odds.get(side), p_final.get(side), h2h_basis)

    # 2) 더블찬스 3종 (축구, 3-way 배당에서 합성) — 1X · X2 · 12
    if sport == "soccer" and best_odds.get("Draw"):
        for side in (jg["home"], jg["away"]):
            if best_odds.get(side):
                pf = p_final.get(side)
                p_dc = (min(0.98, pf + p_draw_m)
                        if pf is not None and p_draw_m is not None else None)
                label = "승/무" if side == jg["home"] else "무/승"
                add("dc", side, None, f"{kr_team(side)} 더블찬스({label})",
                    synth_dc_odds(best_odds[side], best_odds["Draw"]), p_dc, "앙상블+합성배당")
        if best_odds.get(jg["home"]) and best_odds.get(jg["away"]):
            ph, pa = p_final.get(jg["home"]), p_final.get(jg["away"])
            p_12 = min(0.98, ph + pa) if ph is not None and pa is not None else None
            add("dc", "12", None, "더블찬스(홈/원정 — 무승부만 제외)",
                synth_dc_odds(best_odds[jg["home"]], best_odds[jg["away"]]), p_12,
                "앙상블+합성배당")

    # 3) 핸디캡·토탈
    #   [§8-27] 수집 라인이 있으면 **그 라인**을 쓴다(시장이 던진 질문이 더 정확하다).
    #   없으면 **분포에서 라인을 만든다** — 배당이 없다고 마켓이 사라지면 안 된다.
    seen_alt: set[tuple] = set()
    for alt in jg.get("alt_markets", []):
        m, side, line = alt["market"], alt["side"], alt["line"]
        seen_alt.add((m, side, line))
        if m == "spreads":
            desc = spread_desc(sport, kr_team(side), line)
        else:
            desc = f"{'오버' if side == 'Over' else '언더'} {line:g}"
        # 야구 토탈은 라인 숫자만 온다(가격 없음). 확률은 λ 분포가 채운다.
        if alt.get("odds") is None and alt.get("p") is None:
            basis = "기대득점 분포"
        else:
            basis = "시장 기준"
            if _axis_expert(jg, m, side, line):
                basis = "시장+전문가"
        add(m, side, line, desc, alt.get("odds"), alt.get("p"), basis)

    if dist is not None:
        probs = dist.get("probs") or {}
        for line in sorted((probs.get("totals") or {})):
            for side in ("Over", "Under"):
                if ("totals", side, line) in seen_alt:
                    continue
                desc = f"{'오버' if side == 'Over' else '언더'} {line:g}"
                add("totals", side, line, desc, None, None, "기대득점 분포")
        for line in sorted((probs.get("spreads") or {})):
            for side, key in ((jg["home"], "home_minus"), (jg["away"], "away_plus"),
                              (jg["away"], "away_minus"), (jg["home"], "home_plus")):
                signed = -abs(line) if key.endswith("minus") else abs(line)
                if ("spreads", side, signed) in seen_alt:
                    continue
                add("spreads", side, signed,
                    spread_desc(sport, kr_team(side), signed), None, None, "기대득점 분포")

    # 승인/제외 판정 + 등급 (마켓 단위)
    from app.engine.scoring import is_away_underdog, required_prob

    for c in out:
        c["required_prob"] = required_prob(c["market"], c["side"], jg)
        c["away_underdog"] = is_away_underdog(c["market"], c["side"], jg, c.get("odds"))
        # [§8-18] 시장 대비 엣지 계산·판정 제거
        c["edge"] = None
        c["edge_excess"] = False
        _approve(jg, c, sport)
        c["grade"], c["grade_note"] = grade_candidate(c)

    return out


# ---------------------------------------------------------------- 전 마켓 보드

def _required_specs(jg: dict, sport: str) -> list[tuple]:
    """[2] 경기마다 반드시 행으로 나와야 하는 마켓 목록 (market, side, line, desc)."""
    from app.bot.aliases import kr_team

    home, away = jg["home"], jg["away"]
    # [§8-14] KBO·NPB도 야구다 — **무승부 행이 없어야 한다.**
    #   종목 문자열만 보고 축구로 흘려보내면 "무승부" 행이 생겨 야구에 없는 마켓을 낸다.
    from app.engine.scoring import BASEBALL_SPORTS

    if sport in BASEBALL_SPORTS:
        return [
            ("h2h", home, None, f"{kr_team(home)} 승"),
            ("h2h", away, None, f"{kr_team(away)} 승"),
            ("spreads", home, -1.5, spread_desc("mlb", kr_team(home), -1.5)),
            ("spreads", away, 1.5, spread_desc("mlb", kr_team(away), 1.5)),
            ("totals", "Under", None, "언더오버"),
            ("f5", home, None, f"{kr_team(home)} F5(5이닝) 승"),
            ("f5", away, None, f"{kr_team(away)} F5(5이닝) 승"),
        ]
    return [
        ("h2h", home, None, f"{kr_team(home)} 승"),
        ("h2h", "Draw", None, "무승부"),
        ("h2h", away, None, f"{kr_team(away)} 승"),
        ("spreads", home, -0.5, spread_desc("soccer", kr_team(home), -0.5)),
        ("spreads", away, 0.5, spread_desc("soccer", kr_team(away), 0.5)),
        ("spreads", home, -1.5, spread_desc("soccer", kr_team(home), -1.5)),
        ("spreads", away, 1.5, spread_desc("soccer", kr_team(away), 1.5)),
        ("totals", "Under", None, "언더오버"),
        ("dc", home, None, f"{kr_team(home)} 더블찬스(승/무)"),
        ("dc", away, None, f"{kr_team(away)} 더블찬스(무/승)"),
        ("dc", "12", None, "더블찬스(홈/원정 — 무승부만 제외)"),
        ("btts", "Yes", None, "양팀 득점(BTTS)"),
    ]


def _placeholder(market, side, line, desc) -> dict:
    """[2] 배당 미수집 마켓 행 — 지우지 않고 남겨 '무엇을 못 봤는지'를 드러낸다."""
    return {
        "market": market, "side": side, "line": line, "desc": desc,
        "odds": None, "p": None, "ev": None, "basis": "배당 미수집",
        "axes": {}, "axes_n": 0, "axes_kr": "없음",
        "approved": False, "reject_reason": "배당 미수집",
        "grade": GRADE_BLANK, "grade_note": "배당 확보 시 재평가", "placeholder": True,
    }


def build_board(jg: dict, sport: str, p_final: dict[str, float]) -> list[dict]:
    """[2] 전 마켓 보드 — 판정 유무·배당 유무와 무관하게 **항상** 전 마켓을 행으로 낸다.

    가격이 붙은 마켓은 평가 결과를, 배당이 없는 마켓은 '배당 미수집' 행을 남긴다.
    "평가 가능한 마켓 없음"이라는 출력은 이 함수를 쓰는 한 나올 수 없다.
    """
    priced = build_candidates(jg, sport, p_final)
    have = {(c["market"], c["side"]) for c in priced}
    have_market = {c["market"] for c in priced}

    rows = list(priced)
    for market, side, line, desc in _required_specs(jg, sport):
        if market == "totals":
            if "totals" not in have_market:      # 라인은 수집분으로 채워지므로 마켓 단위로 판단
                rows.append(_placeholder(market, side, line, desc))
            continue
        if (market, side) not in have:
            rows.append(_placeholder(market, side, line, desc))

    jg["markets_unpriced"] = [r["desc"] for r in rows if r.get("placeholder")]
    return rows


def _approve(jg: dict, c: dict, sport: str) -> None:
    """후보 1건의 승인/제외 판정 — 사유를 한국어로 남긴다."""
    if c.get("p") is None:
        c["approved"] = False
        c.setdefault("reject_reason", "근거 부족 — 확률 추정 불가")
        c["flags"] = []
        return
    # 판정을 못 받은 경기는 어떤 마켓도 추천하지 않는다 (보드에는 남긴다)
    if jg.get("judge_missing"):
        c["approved"] = False
        c["reject_reason"] = "판정 미수신 — 추천 불가"
        c["flags"] = []
        return
    # [3] EV 기반 이상치 플래그는 제거했다 — EV를 판정에서 뺐으므로 플래그도 함께 뺀다.
    #     (실사고: 배당 1.59가 하한에 0.01 미달해 탈락했는데 사유가 "수익률 이상치"로
    #      잘못 표기됐다. EV 플래그가 먼저 걸려 진짜 사유를 가린 것이다)
    #     배당 데이터 자체가 깨진 경우만 남긴다 — 승률과 배당 환산값의 괴리.
    #     괴리 검사는 **승패(h2h)에만** 적용한다. 핸디캡·토탈은 모델과 시장이 다른 것이
    #     정상이며(모델을 갖는 이유가 그것이다), 여기서 걸면 정상 픽을 지운다.
    flags = []
    if c.get("odds"):
        implied = 1 / c["odds"]
        if c["market"] in ("h2h", "dc") and abs(c["p"] - implied) > 0.30:
            flags.append(f"승률 {c['p']:.0%} vs 배당 환산 {implied:.0%} 괴리 >30%p (배당 데이터 확인 필요)")
    c["flags"] = flags

    def reject(reason):
        c["approved"] = False
        c["reject_reason"] = reason

    if flags:
        return reject("플래그 — " + "; ".join(flags))
    if jg.get("judge_pass"):
        return reject("판정 패스 권장 경기")
    if jg.get("judge_confidence") == "low":
        return reject("판정 저신뢰 경기")
    # [1-2 폐기] 모델-시장 괴리 검증 — 시장 배제 전환(2026-08-25)으로 삭제됐다.
    #   시장 확률을 기준점으로 쓰는 규칙이라 시장을 판정에서 빼면 성립하지 않는다.
    #   남는 위험(시장이 아는 정보를 우리가 못 봄)은 경기력 정보 수집으로 대체 방어한다.
    # [6] 2-소스 룰은 **추천 자격**에만 적용한다 — 확률 산출 가능 여부와 무관하다.
    #     분포에서 확률이 나온 마켓을 "근거 부족"으로 보드에서 지우면, 실제로 평가된
    #     마켓을 화면에서 없애는 셈이다. 보드에는 남기고 추천 풀에서만 뺀다.
    # [A-4단계] 종목마다 **살아 있는 축의 수가 다르다.**
    #   KBO·NPB는 전문가 픽을 수집하지 않으므로(실측: KBO 0/5) 축이 2개뿐이고,
    #   축이 줄었으면 문턱이 높아져야 한다 — 살아 있는 축이 **전부** 같은
    #   방향일 때만 추천 자격을 준다.
    #   ⚠️ 종전 `axes_n >= 2`는 KBO에서 **우연히** data+model을 요구했다.
    #     우연에 기대면 나중에 전문가 축이 살아났을 때 조용히 느슨해진다.
    from app.engine.coverage import qualifies_axes

    c["two_source"] = qualifies_axes(sport, c["axes"])
    if not c["two_source"] and jg.get("distribution") is None:
        # 분포조차 없으면 확률 근거 자체가 없다 — 이때만 보드에서도 제외
        only = axes_label(c["axes"])
        return reject(f"근거 부족 — 2-소스 미달 ({only} 단독)" if c["axes_n"] == 1
                      else "근거 부족 — 지지 축 없음")
    # [3] 축구 승패 단식은 저분산 우선 원칙 — 신뢰도 high에서만
    if sport == "soccer" and c["market"] == "h2h" and jg.get("judge_confidence") != "high":
        return reject("저분산 우선 — 승패 단식은 판정 신뢰도 '상'에서만 허용")
    # 이길 확률 자체가 열세인 마켓(저분산 취지 위배) 컷: dc·+핸디는 60% 미만이면 무의미
    if c["market"] == "dc" and c["p"] < 0.55:
        return reject("더블찬스인데 합산 확률 55% 미만 — 실익 없음")
    c["approved"] = True
    c["reject_reason"] = None
