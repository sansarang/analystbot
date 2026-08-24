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


async def calibrated_lambda(pool, league: str) -> float:
    """채점 데이터 ≥300픽이면 리그별 λ를 Brier 최소화 그리드로 실측 재추정.

    미달이면 성숙도 기본값. (p_market·p_ensemble 컬럼은 지금부터 적재된다.)
    """
    rows = await pool.fetch(
        """
        SELECT p.p_market, p.p_ensemble, (p.result = 'win')::int AS y
        FROM predictions p JOIN games g ON g.id = p.game_id
        WHERE p.result IN ('win', 'loss') AND g.league = $1
          AND p.p_market IS NOT NULL AND p.p_ensemble IS NOT NULL
        """,
        league,
    )
    if len(rows) < CALIBRATION_MIN_PICKS:
        return shrink_lambda(league)
    best_lam, best_brier = shrink_lambda(league), float("inf")
    for i in range(0, 21):
        lam = i / 20
        brier = sum(
            (lam * float(r["p_market"]) + (1 - lam) * float(r["p_ensemble"]) - r["y"]) ** 2
            for r in rows
        ) / len(rows)
        if brier < best_brier:
            best_lam, best_brier = lam, brier
    logger.info("[markets] λ 재추정 %s: %.2f (Brier %.4f, n=%d)",
                league, best_lam, best_brier, len(rows))
    return best_lam


# ---------------------------------------------------------------- 합성 배당

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


def _season_edge(jg: dict) -> float | None:
    """올 시즌 실데이터 기준 홈팀 우위 점수 (>0 홈 우세). 데이터 없으면 None."""
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
    return None


def has_season_data(jg: dict) -> bool:
    """판정 입력에 올 시즌 실데이터가 1건이라도 있는가 ([4d] 데이터 제로 강등 기준)."""
    return _season_edge(jg) is not None


def _expected_total(jg: dict) -> float | None:
    """양 팀 순위표 득실로 예상 총득점 추정 (축구 토탈 실데이터 축)."""
    st = jg.get("stats") or {}
    vals = []
    for key in ("home_season", "away_season"):
        s = st.get(key)
        if not s or not s.get("played"):
            return None
        vals.append((s.get("gf", 0) + s.get("ga", 0)) / s["played"])
    return sum(vals) / 2


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
    """후보 픽의 독립 근거 축 4종 판정."""
    return {
        "data": _axis_data(jg, market, side, line),
        "expert": _axis_expert(jg, market, side, line),
        "model": _axis_model(jg, market, side),
        "market": p_market_side is not None and p_market_side > 0.5,
    }


AXIS_KR = {"data": "실데이터", "expert": "전문가", "model": "모델", "market": "시장"}


def axes_label(axes: dict) -> str:
    on = [AXIS_KR[k] for k, v in axes.items() if v]
    return "+".join(on) if on else "지지 축 없음"


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
    label = "런라인" if sport == "mlb" else "핸디"
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


def grade_candidate(c: dict, ev_threshold: float = 0.05) -> tuple[str, str]:
    """[A-1] 마켓 1건의 등급과 한 줄 사유 — **경기 단위가 아니라 마켓 단위로** 판정한다.

    승패에 가치가 없어도 언더/핸디캡이 살아 있으면 그 마켓은 🟢일 수 있다.
    🟢 승인 + EV 기준 초과 / 🟡 승인이나 이득이 얇음 / 🔴 미승인 또는 이득 없음.
    """
    ev = c.get("ev")
    if not c.get("odds"):
        return GRADE_BLANK, "배당 확보 시 재평가"
    if ev is None or c.get("p") is None:
        return GRADE_RED, c.get("reject_reason") or "근거 부족"
    if not c.get("approved"):
        return GRADE_RED, c.get("reject_reason") or "제외"
    if ev <= 0:
        return GRADE_RED, f"이득 {ev:+.1%} — 가치 없음"
    if ev >= ev_threshold:
        return GRADE_GREEN, f"이득 {ev:+.1%}, 근거 {c.get('axes_kr') or '?'}"
    low_var = c["market"] in ("dc", "totals") or (
        c["market"] == "spreads" and (c.get("line") or 0) > 0)
    kind = "저분산 대안" if low_var else "소액"
    return GRADE_YELLOW, f"{kind}, 이득 {ev:+.1%}"


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

    def add(market, side, line, desc, odds, p, basis):
        if not odds:
            return                       # 배당이 없는 마켓은 build_board가 placeholder로 채운다
        if stale:
            desc = f"{desc} (개장 배당)"
        if p is None:
            # 배당은 있는데 확률 추정 근거가 없다 — 행은 남기고 '근거 부족'으로 표기
            out.append({
                "market": market, "side": side, "line": line, "desc": desc,
                "odds": round(float(odds), 2), "p": None, "ev": None, "basis": basis,
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
            "odds": round(float(odds), 2), "p": round(p, 4),
            "ev": round(p * float(odds) - 1, 4), "basis": basis,
            "axes": axes, "axes_n": sum(axes.values()), "axes_kr": axes_label(axes),
        })

    # 1) 승패 (h2h) — 판정을 못 받아 p_final이 없어도 배당이 있으면 행은 남긴다
    h2h_sides = [jg["home"], jg["away"]]
    if sport == "soccer" and best_odds.get("Draw"):
        h2h_sides.insert(1, "Draw")
    for side in h2h_sides:
        if not best_odds.get(side):
            continue
        desc = "무승부" if side == "Draw" else f"{kr_team(side)} 승"
        add("h2h", side, None, desc, best_odds[side], p_final.get(side), "앙상블")

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

    # 3) 핸디캡·토탈 (수집 배당 디빅 — 시장 기준)
    for alt in jg.get("alt_markets", []):
        m, side, line = alt["market"], alt["side"], alt["line"]
        if m == "spreads":
            desc = spread_desc(sport, kr_team(side), line)
        else:
            desc = f"{'오버' if side == 'Over' else '언더'} {line:g}"
        basis = "시장 기준"
        if _axis_expert(jg, m, side, line):
            basis = "시장+전문가"
        add(m, side, line, desc, alt["odds"], alt["p"], basis)

    # 승인/제외 판정 + 등급 (마켓 단위)
    for c in out:
        _approve(jg, c, sport)
        c["grade"], c["grade_note"] = grade_candidate(c)

    return out


# ---------------------------------------------------------------- 전 마켓 보드

def _required_specs(jg: dict, sport: str) -> list[tuple]:
    """[2] 경기마다 반드시 행으로 나와야 하는 마켓 목록 (market, side, line, desc)."""
    from app.bot.aliases import kr_team

    home, away = jg["home"], jg["away"]
    if sport == "mlb":
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
    if c.get("ev") is None or c.get("p") is None:
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
    flags = []
    if c["ev"] > 0.20:
        flags.append(f"EV {c['ev']:+.1%} > +20% (배당 데이터 이상 의심)")
    implied = 1 / c["odds"]
    if abs(c["p"] - implied) > 0.25:
        flags.append(f"확률 {c['p']:.0%} vs 배당 암시 {implied:.0%} 괴리 >25%p")
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
    # [2] 모델-시장 괴리 검증 — 모델 엣지에 의존하는 승패 단식만.
    #     (더블찬스는 무승부 쿠션이 있어 [9]의 저분산 대체 취지대로 살린다)
    if c["market"] == "h2h" and jg.get("model_valid") and jg.get("p_market") is not None:
        gap = abs(jg["p_model"] - jg["p_market"])
        if gap >= GAP_UNVERIFIED and not c["axes"]["expert"]:
            return reject(
                f"시장이 아는 정보가 있을 가능성 (모델-시장 괴리 {gap * 100:.0f}%p 원인 미검증)")
    # [1] 2-소스 룰 — 모델 단독은 EV 무관 금지
    if c["axes_n"] < 2:
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
