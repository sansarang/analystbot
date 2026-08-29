"""[§9] 상태 대조 카드 — 1단 수집봇. **LLM 0회.**

다섯 칸의 **사실 층**만 채운다. 해석(▲▼)은 2단, 결론은 3단이 한다.

왜 층을 나누는가:
  한 번에 시키면 LLM은 **먼저 결론을 세우고 칸을 거기 맞춘다.** λ가 한쪽으로
  기울자 모든 서술이 그쪽으로 정렬됐던 실패가 그것이다. 프롬프트로는 못 막는다.
  → 사실 칸에 **LLM이 쓰기 접근을 갖지 않게** 한다. 권한으로 막는다.

⚠️ 여기서 값을 **해석하지 않는다.** "구원 6.33이닝 37타자"까지가 이 층의 일이고,
   "뒷문이 얇다 ▼"는 2단의 일이다. 사실과 판단이 한 층에 섞이면 3단이 판단을
   사실로 착각한다.

⚠️ 사실이 없으면 그 칸은 **모름**이다. 0으로 채우지 않는다 —
   "소모 0"은 "충분함 ▲"으로 오독된다. 모름이 셋 이상이면 판정하지 않는다.
"""

import re
from dataclasses import dataclass, field

# 칸 정의 — 순서가 카드 출력 순서다.
CELLS: tuple[tuple[str, str], ...] = (
    ("bullpen", "불펜 가용"),
    ("starter", "선발 상태"),
    ("batting", "타선"),
    ("recent3", "최근 3경기"),
    ("weight", "무게"),
)
CELL_KEYS = tuple(k for k, _ in CELLS)

# [§9-6번째 칸] **득점 환경** — 승패가 아니라 경기 전체의 성격을 답한다.
#   앞의 다섯 칸은 "누가 이기나"만 답하고 총득점·점수차를 다루지 않는다.
#   ⚠️ 팀 대조가 아니므로 **한 칸만** 있다. home/away로 나누지 않는다.
#   ⚠️ 부호도 ▲▼가 아니다 — 다득점/보통/저득점 3단이다. 득점이 많은 것은
#      어느 팀에게도 '유리'가 아니다.
SCORING_CELL = ("scoring", "득점 환경")
SCORING_LEVELS = ("다득점 예상", "보통", "저득점 예상")

# 모름이 이만큼이면 판정하지 않는다. 재료 없이 결론을 내는 것보다 침묵이 낫다.
MAX_UNKNOWN = 2


# [§9-2단] 칸별 **수치 지표와 방향** — 기계적 오독 검증의 근거.
#   (지표명, 클수록 유리한가)
# ⚠️ 2단은 상대를 못 본다(차단벽). 그래서 비교 기준은 상대가 아니라
#   **리그 기준선**이다 — "평소보다 유리한가"를 묻는 것과 같다.
CELL_METRICS: dict[str, tuple[tuple[str, bool], ...]] = {
    "bullpen": (("relief_batters_l3", False),      # 많이 던졌을수록 소모 = 불리
                ("back_to_back_count", False),
                ("pitchers_used_last", False)),
    "starter": (("era_season", False), ("whip", False), ("ip_avg_recent", True)),
    "batting": (("ops", True),),
    "recent3": (("run_diff_l3", True), ("runs_per_game_l3", True)),
    "weight":  (("games_behind_cut", False),),     # 컷과 가까울수록 경쟁 중 = 유리
}


# [득점 환경] 지표와 방향 — (지표명, 클수록 득점이 많아지는가)
#   ⚠️ 여기서 True/False는 "유리한가"가 아니라 **"득점이 늘어나는가"**다.
#      다섯 칸의 CELL_METRICS와 의미가 다르므로 섞어 쓰면 안 된다.
SCORING_METRICS: tuple[tuple[str, bool], ...] = (
    ("runs_per_game_both", True),      # 양 팀 최근 회당 득점 합
    ("starter_era_avg", True),         # 선발이 나쁠수록 점수가 난다
    ("starter_ip_avg", False),         # 선발이 짧을수록 불펜 노출이 커진다
    ("relief_batters_avg", True),      # 불펜이 소모됐을수록 뒤가 열린다
    ("park_factor", True),             # 타자친화 구장일수록 총득점이 는다
)


def scoring_metrics(research: dict) -> dict[str, float]:
    """득점 환경 칸의 수치 지표. **양 팀 값을 합치거나 평균 낸다.**

    ⚠️ 한쪽만 있으면 넣지 않는다 — 한 팀 값으로 경기 전체를 말할 수 없다.
    """
    r = research or {}
    out: dict[str, float] = {}

    def _pair(section: str, field: str):
        vals = [(r.get(f"{sd}_{section}") or {}).get(field) for sd in ("home", "away")]
        vals = [v for v in vals if isinstance(v, int | float)]
        return vals if len(vals) == 2 else []

    if (v := _pair("usage", "runs_per_game_l3")):
        out["runs_per_game_both"] = round(sum(v), 2)
    if (v := _pair("pitcher", "era_season")):
        out["starter_era_avg"] = round(sum(v) / 2, 2)
    if (v := _pair("pitcher", "ip_avg_recent")):
        out["starter_ip_avg"] = round(sum(v) / 2, 2)
    if (v := _pair("usage", "relief_batters_l3")):
        out["relief_batters_avg"] = round(sum(v) / 2, 1)
    pf = r.get("park_factor")
    if isinstance(pf, int | float):
        out["park_factor"] = float(pf)
    return out


def cell_metrics(research: dict, side: str, key: str) -> dict[str, float]:
    """그 칸의 수치 지표. 없는 값은 넣지 않는다."""
    u = research.get(f"{side}_usage") or {}
    p = research.get(f"{side}_pitcher") or {}
    o = research.get(f"{side}_offense") or {}
    st = research.get(f"{side}_standing") or {}
    src: dict[str, object] = {}
    if key == "bullpen":
        src = {k: u.get(k) for k in ("relief_batters_l3", "back_to_back_count",
                                     "pitchers_used_last", "bp_pitches_3d")}
    elif key == "starter":
        src = {k: p.get(k) for k in ("era_season", "whip", "ip_avg_recent",
                                     "xwoba_allowed")}
    elif key == "batting":
        src = {"ops": o.get("ops"), "xwoba_30d": o.get("xwoba_30d")}
    elif key == "recent3":
        r, ra = u.get("runs_l3"), u.get("runs_allowed_l3")
        src = {"runs_per_game_l3": u.get("runs_per_game_l3"),
               "run_diff_l3": (r - ra) if (r is not None and ra is not None) else None}
    elif key == "weight":
        src = {"games_behind_cut": st.get("games_behind_cut")}
    return {k: float(v) for k, v in src.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)}


def _quantile(vals: list[float], q: float) -> float:
    vals = sorted(vals)
    if len(vals) == 1:
        return vals[0]
    pos = q * (len(vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def league_baselines(research_by_side: list[dict]) -> dict[str, dict[str, float]]:
    """지표별 **사분위**. 기준선이 없으면 방향 검증을 못 한다.

    ⚠️ 평균이 아니라 중앙값·사분위다 — 한 팀의 이상치(한화 선발 ERA 13.5)가
       기준선을 밀어버리면 나머지 팀 판정이 전부 틀어진다.

    ⚠️ **중앙값 하나만으로는 부족하다.** 중앙값보다 크기만 하면 "불리"로 세면
       0.004 차이도 오독으로 잡힌다(실측 2026-08-27: OPS 0.760 vs 기준 0.756이
       "방향 오독"으로 폐기됐다 — 가드가 정상 판정을 버렸다).
       → 사분위 **밖**일 때만 "명백히 평소와 다르다"로 본다. 임의 여유값을
         만들지 않고 **데이터 자체의 산포**를 쓴다.
    """
    pool: dict[str, list[float]] = {}
    for res, side in research_by_side:
        for key in CELL_METRICS:
            for name, val in cell_metrics(res, side, key).items():
                pool.setdefault(name, []).append(val)
    out: dict[str, dict[str, float]] = {}
    for name, vals in pool.items():
        if len(vals) < 4:
            continue          # 사분위를 낼 표본이 아니다
        out[name] = {"q1": _quantile(vals, 0.25),
                     "median": _quantile(vals, 0.5),
                     "q3": _quantile(vals, 0.75)}
    return out


@dataclass
class Cell:
    """한 팀·한 칸. 사실 층만 채워진 상태."""

    key: str
    label: str
    facts: list[str] = field(default_factory=list)
    source: str = ""
    metrics: dict = field(default_factory=dict)

    @property
    def known(self) -> bool:
        return bool(self.facts)

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "facts": list(self.facts),
                "source": self.source, "known": self.known,
                "metrics": dict(self.metrics)}


def _f(v, digits: int = 2):
    """숫자를 사람이 읽는 형태로. None이면 None(0으로 바꾸지 않는다)."""
    if v is None:
        return None
    if isinstance(v, float):
        return f"{v:.{digits}f}".rstrip("0").rstrip(".")
    return str(v)


# ---------------------------------------------------------------- 칸별 사실 생성


def _bullpen_facts(r: dict, side: str) -> tuple[list[str], str]:
    u = r.get(f"{side}_usage") or {}
    if not u:
        return [], ""
    out = []
    if u.get("pitchers_used_last") is not None:
        out.append(f"직전 경기({u.get('last_game_date', '?')}) 투수 "
                   f"{u['pitchers_used_last']}명 투입 · 구원 "
                   f"{_f(u.get('relief_ip_last'))}이닝 "
                   f"{u.get('relief_batters_last', 0)}타자 상대")
    if u.get("relief_ip_l3") is not None:
        out.append(f"최근 {u.get('window_games', 3)}경기 구원 "
                   f"{_f(u['relief_ip_l3'])}이닝 "
                   f"{u.get('relief_batters_l3', 0)}타자")
    if u.get("bp_pitches_3d") is not None and u.get("pitchers_used_last") is None:
        out.append(f"최근 3경기 구원 {u['bp_pitches_3d']}구")
    b2b = u.get("back_to_back") or []
    if b2b:
        out.append(f"2경기 연속 등판 {len(b2b)}명: {', '.join(b2b)}")
    elif u.get("back_to_back_count") == 0:
        out.append("2경기 연속 등판 없음")
    if not out:
        return [], ""
    src = ("Statcast(LLM 0회)" if u.get("bp_pitches_3d") is not None
           and u.get("pitchers_used_last") is None
           else "네이버 기록(LLM 0회)")
    return out, src


def _starter_facts(r: dict, side: str) -> tuple[list[str], str]:
    p = r.get(f"{side}_pitcher") or {}
    name = (p.get("name") or "").strip()
    if not name:
        return [], ""
    bits = [name]
    hand = {"L": "좌완", "R": "우완"}.get(str(p.get("throws") or "")[:1])
    if hand:
        bits.append(hand)
    if p.get("era_season") is not None:
        bits.append(f"시즌 ERA {_f(p['era_season'])}")
    if p.get("whip") is not None:
        bits.append(f"WHIP {_f(p['whip'])}")
    if p.get("ip_avg_recent") is not None:
        bits.append(f"평균 {_f(p['ip_avg_recent'])}이닝")
    if p.get("xwoba_allowed") is not None:
        bits.append(f"허용 xwOBA {_f(p['xwoba_allowed'], 3)}")
    out = [" · ".join(bits)]
    if p.get("pitch_mix"):
        out.append(f"구종 {p['pitch_mix']}")
    # 예고인지 확정인지는 **섞으면 안 된다** — 예상을 확정으로 취급하면 안 된다
    if r.get("starter_status"):
        out.append(f"선발 발표: {r['starter_status']}")
    src = ("statsapi·Statcast(LLM 0회)" if p.get("xwoba_allowed") is not None
           or (p.get("era_season") is not None and not p.get("pitch_mix"))
           else "네이버·크롤러(LLM 0회)")
    return out, src


def _batting_facts(r: dict, side: str) -> tuple[list[str], str]:
    out = []
    lu = r.get(f"{side}_lineup") or {}
    if lu.get("order"):
        names = [n for n in str(lu["order"]).split("-") if n]
        out.append(f"타순 {len(names)}명 확정: {'-'.join(names)}")
        # ⚠️ 발표 시각·변경 이력은 **경기 단위** 값이다. 그 팀의 타순이 없는데
        #    이것만으로 칸을 '채워짐'으로 만들면, 팀 고유 사실이 하나도 없는
        #    칸이 대조에 올라간다(테스트가 실제로 잡았다).
        if r.get("lineup_announced_at"):
            out.append(f"라인업 발표 {r['lineup_announced_at']}")
        out += (r.get("lineup_changes") or [])[:3]
    # 결장은 리스트다. 그 팀 것만 넣는 분리는 performance._split_absences가 한다.
    for a in (r.get(f"{side}_absences") or [])[:4]:
        out.append(f"결장 {a}")
    t = r.get(f"{side}_offense") or {}
    if t.get("ops") is not None:
        out.append(f"팀 OPS {_f(t['ops'], 3)}")
    elif t.get("xwoba_30d") is not None:
        out.append(f"팀 xwOBA {_f(t['xwoba_30d'], 3)}")
    if not out:
        return [], ""
    src = ("Statcast(LLM 0회)" if t.get("xwoba_30d") is not None and t.get("ops") is None
           else "크롤러·공식기록(LLM 0회)")
    return out, src


def _recent3_facts(r: dict, side: str) -> tuple[list[str], str]:
    u = r.get(f"{side}_usage") or {}
    if not u.get("score_games"):
        # 승패 문자열만이라도 있으면 그것만 낸다 — 없는 것을 만들지 않는다
        form = ((r.get(f"{side}_recent_form") or {}).get("form") or "").strip()
        return ([f"최근 폼 {form}"] if form else []), "네이버(LLM 0회)"
    out = [f"최근 {u['score_games']}경기 {u.get('results_l3', '')} · "
           f"{u.get('runs_l3', 0)}득점 {u.get('runs_allowed_l3', 0)}실점 "
           f"(회당 {_f(u.get('runs_per_game_l3'))}득점)"]
    detail = []
    for key, word in (("comeback_wins_l3", "역전승"), ("blown_leads_l3", "역전패"),
                      ("shutout_losses_l3", "완봉패"), ("one_run_games_l3", "1점차")):
        n = u.get(key) or 0
        if n:
            detail.append(f"{word} {n}회")
    if detail:
        out.append(" · ".join(detail))
    return out, "statsapi(LLM 0회)" if u.get("score_games") and u.get("pitchers_used_last") is None \
        else "네이버 기록(LLM 0회)"


def _weight_facts(r: dict, side: str) -> tuple[list[str], str]:
    s = r.get(f"{side}_standing") or {}
    if not s.get("rank"):
        return [], ""
    bits = [f"{s['rank']}위"]
    if s.get("w") is not None:
        bits.append(f"{s['w']}승 {s['l']}패 {s.get('d', 0)}무")
    if s.get("games_behind") is not None:
        bits.append(f"선두와 {_f(s['games_behind'], 1)}게임차")
    if s.get("remaining") is not None:
        bits.append(f"잔여 {s['remaining']}경기")
    return [" · ".join(bits)], (
        "statsapi(LLM 0회)" if s.get("win_pct") is not None
        else "네이버 순위(LLM 0회)")


def _scoring_facts(r: dict, home_kr: str = "홈", away_kr: str = "원정") -> tuple[list[str], str]:
    """[득점 환경] 경기 전체의 사실. **팀별이 아니라 경기 단위다.**

    ⚠️ 여기서도 해석하지 않는다. "회당 10.33득점"까지가 이 층의 일이고,
       "다득점 예상"은 2단의 일이다.
    """
    out, srcs = [], []
    for side, name in (("away", away_kr), ("home", home_kr)):
        u = r.get(f"{side}_usage") or {}
        if u.get("score_games"):
            out.append(f"{name} 최근 {u['score_games']}경기 회당 "
                       f"{_f(u.get('runs_per_game_l3'))}득점 · "
                       f"{u.get('runs_allowed_l3', 0)}실점(누적)")
            srcs.append("네이버 기록")
    for side, name in (("away", away_kr), ("home", home_kr)):
        p = r.get(f"{side}_pitcher") or {}
        if p.get("era_season") is not None:
            bits = [f"{name} 선발 {p.get('name') or '?'} ERA {_f(p['era_season'])}"]
            if p.get("whip") is not None:
                bits.append(f"WHIP {_f(p['whip'])}")
            if p.get("ip_avg_recent") is not None:
                bits.append(f"평균 {_f(p['ip_avg_recent'])}이닝")
            out.append(" · ".join(bits))
            srcs.append("KBO 기록실")
    for side, name in (("away", away_kr), ("home", home_kr)):
        u = r.get(f"{side}_usage") or {}
        if u.get("relief_batters_l3") is not None:
            out.append(f"{name} 불펜 최근 3경기 구원 {u['relief_batters_l3']}타자 상대")
    if r.get("park"):
        out.append(str(r["park"]))
        srcs.append("자체 산출 파크팩터")
    if r.get("weather"):
        out.append(f"날씨 {r['weather']}")
        srcs.append("Open-Meteo")
    # [7] 라인업 변경은 승패보다 총득점에 더 크게 영향을 준다 — 득점 칸에도 싣는다.
    for side, name in (("away", away_kr), ("home", home_kr)):
        for cell_facts in (r.get(f"{side}_lineup_changes") or {}).values():
            for d in cell_facts:
                out.append(f"[{name} 라인업 변경] {d}")
                srcs.append("라인업 대조")
    return out, " · ".join(dict.fromkeys(srcs))


_BUILDERS = {
    "bullpen": _bullpen_facts,
    "starter": _starter_facts,
    "batting": _batting_facts,
    "recent3": _recent3_facts,
    "weight": _weight_facts,
}


# ---------------------------------------------------------------- 카드 조립


def build_side(research: dict, side: str) -> dict[str, Cell]:
    """한 팀의 다섯 칸(사실 층만).

    [§9-라인업 의도] 평소 대비 변경점은 **새 칸을 만들지 않고** 유형에 맞는
    칸의 사실로 덧붙인다(타순·결장 → 타선 / 불펜 엔트리 → 불펜 / 주전 휴식 → 무게).
    ⚠️ 이것은 코드가 만든 사실이다 — LLM은 여기에 쓰기 접근이 없다.
    """
    r = research or {}
    changes = r.get(f"{side}_lineup_changes") or {}
    out: dict[str, Cell] = {}
    for key, label in CELLS:
        facts, source = _BUILDERS[key](r, side)
        extra = list(changes.get(key) or [])
        if extra:
            facts = list(facts) + [f"[라인업 변경] {d}" for d in extra]
            source = " · ".join(x for x in (source, "라인업 대조(LLM 0회)") if x)
        out[key] = Cell(key=key, label=label, facts=facts, source=source,
                        metrics=cell_metrics(r, side, key))
    return out


def build_card(jg: dict, research: dict) -> dict:
    """양 팀 카드 + 판정 가능 여부.

    반환:
      {"home": {...}, "away": {...}, "unknown": [...], "judgeable": bool, "reason": str}
    """
    home = build_side(research, "home")
    away = build_side(research, "away")
    unknown = [k for k in CELL_KEYS if not (home[k].known and away[k].known)]
    judgeable = len(unknown) <= MAX_UNKNOWN
    # [§9-6번째 칸] 득점 환경 — 경기 단위라 home/away 밖에 따로 둔다.
    _sc_facts, _sc_src = _scoring_facts(
        research or {}, jg.get("home_kr") or jg.get("home") or "홈",
        jg.get("away_kr") or jg.get("away") or "원정")
    scoring = Cell(key=SCORING_CELL[0], label=SCORING_CELL[1],
                   facts=_sc_facts, source=_sc_src,
                   metrics=scoring_metrics(research or {}))
    return {
        "game_id": jg.get("game_id"),
        "home_team": jg.get("home"), "away_team": jg.get("away"),
        "home": {k: c.as_dict() for k, c in home.items()},
        "away": {k: c.as_dict() for k, c in away.items()},
        "scoring": scoring.as_dict(),
        "unknown": unknown,
        "unknown_labels": [dict(CELLS)[k] for k in unknown],
        "judgeable": judgeable,
        "reason": "" if judgeable else
                  f"모름 {len(unknown)}칸 (허용 {MAX_UNKNOWN}) — 판정하지 않는다",
    }


# ─────────────────────────────────────────────────────────── 카드 출력 (2단 결과)

def render_state_card(jg: dict) -> list[str]:
    """5칸 카드를 텔레그램 줄로 만든다. **사실 층은 항상, 부호는 있으면.**

    ⚠️ LLM이 전부 죽었을 때 부호 자리를 '='로 채우면 안 된다 — 판정한 것처럼
       보인다. 그럴 땐 부호를 '·'로 두고 "판정 미수행"을 머리에 명시한다
       (실사고 2026-08-27: 3중 폴백 전멸로 한화 사이드 5칸이 판정 불가였다).

    ⚠️ HTML parse_mode로 나가므로 꺾쇠(`<`, `>`)를 쓰지 않는다.
    """
    card = jg.get("card") or {}
    if not card.get("home") or not card.get("away"):
        return []
    cells = jg.get("cells") or {}
    home_kr = jg.get("home_kr") or jg.get("home") or "홈"
    away_kr = jg.get("away_kr") or jg.get("away") or "원정"
    status = jg.get("cells_status") or "판정 미수행"

    head = f"🃏 상태 카드 — {away_kr} vs {home_kr}"
    if status != "판정":
        head += "  ⚠️ 해석 판정 미수행 (사실만 표시)"
    lines = [head]

    for key, label in CELLS:
        marks = []
        for side, name in (("away", away_kr), ("home", home_kr)):
            cell = (card.get(side) or {}).get(key) or {}
            if not cell.get("facts"):
                marks.append("미수집")
                continue
            sym = ((cells.get(side) or {}).get(key) or {}).get("symbol")
            marks.append(sym or "·")
        lines.append(f"{label}: {away_kr} {marks[0]} | {home_kr} {marks[1]}")

    # 사유는 **판정이 있는 칸만** 한 줄씩. 인용을 통과한 문장이므로 그대로 쓴다.
    for side, name in (("away", away_kr), ("home", home_kr)):
        for key, label in CELLS:
            v = (cells.get(side) or {}).get(key) or {}
            why = (v.get("reason") or "").strip()
            if not why:
                continue
            lines.append(f"· {name} {label} {v.get('symbol')} — {why}")

    if card.get("unknown_labels"):
        lines.append("(미수집) " + ", ".join(card["unknown_labels"]))
    return lines


_CONF_ICON = {"높음": "🟢", "보통": "🟡", "낮음": "⚪"}
_NUM = re.compile(r"\d")

# 부호의 수치값 — 칸 기울기 계산의 유일한 정의. comparator도 이것을 쓴다.
SYM_VALUE = {"▲": 1, "=": 0, "▼": -1}


def tilt_by_cell(cells: dict) -> dict[str, str | None]:
    """칸별로 어느 쪽으로 기우는가. {cell: "home"|"away"|"even"|None}.

    ⚠️ 한쪽이라도 판정이 없으면 **None**이다 — 기울기를 모른다. 한쪽 ▼만 보고
       "상대가 우위"라고 쓰면 거짓이 된다(상대도 ▼일 수 있다).
    """
    out: dict[str, str | None] = {}
    for key, _ in CELLS:
        h = ((cells.get("home") or {}).get(key) or {}).get("symbol")
        a = ((cells.get("away") or {}).get(key) or {}).get("symbol")
        if h is None or a is None:
            out[key] = None
            continue
        diff = SYM_VALUE.get(h, 0) - SYM_VALUE.get(a, 0)
        out[key] = "home" if diff > 0 else "away" if diff < 0 else "even"
    return out


# 짝이 있어야 하는 기호 — 한쪽만 남으면 읽을 수 없는 조각이 된다.
_PAIRS = (("‘", "’"), ("“", "”"), ("[", "]"))
# 숫자 앞에 붙는 짧은 수식어는 함께 남긴다 ("ERA 3.89" · "팀 OPS .792")
_UNIT_HEAD = re.compile(r"^(?:팀|시즌|평균|직전|최근|리그)$|^[A-Za-z]{2,5}$")


def _snippet(reason: str, label: str = "", max_tokens: int = 4) -> str:
    """긴 사유에서 **숫자가 든 짧은 구절**만 뽑는다.

    3단·2단 사유는 한 문단이 되기 쉽다. 결론 줄에 문단을 실으면 결론이 파묻힌다
    — 사용자가 실제로 겪은 문제다. 숫자가 근거의 알맹이이므로 그것을 남긴다.

    ⚠️ **글자 수로 자르지 않는다.** 24자에서 끔었더니 "리그 상위권 수준의 타"처럼
       단어 중간에서 잘렸다(실측 2026-08-27). 토큰 경계로만 자른다.
    ⚠️ **숫자로 끝난다.** 마지막이 "득점이"·"소모가" 같은 문장 조각이면
       끝나지 않은 말처럼 읽힌다.
    ⚠️ 라벨과 겹치는 앞머리는 지운다 — "최근 3경기 최근 3경기 WWL"이 나갔다.
    """
    text = (reason or "").strip()
    if label and text.startswith(label):
        text = text[len(label):].lstrip(" :·-—")
    # 괄호 안은 부연 설명이다 — 통째로 버린다. 기호만 지우면
    # "득점력(회당 10.33점)" → "득점력회당"처럼 단어가 붙어버린다.
    text = re.sub(r"\([^)]*\)|（[^）]*）", " ", text)
    toks = text.replace("·", " ").split()
    at = next((i for i, t in enumerate(toks) if _NUM.search(t)), None)
    if at is None:
        picked = toks[:max_tokens]
    else:
        if at and _UNIT_HEAD.match(toks[at - 1]):
            at -= 1                       # "ERA"·"팀" 같은 수식어를 함께 남긴다
        picked = toks[at:at + max_tokens]
        # 숫자로 끝나게 다듬되, **두 토큰 아래로는 줄이지 않는다** —
        # "2경기 연속 등판 없음"이 "2경기"만 남으면 뜻이 사라진다.
        while len(picked) > 2 and not _NUM.search(picked[-1]):
            picked.pop()
    out = " ".join(picked)
    for lo, hi in _PAIRS:
        if out.count(lo) != out.count(hi):
            out = out.replace(lo, "").replace(hi, "")
    # 끝에 남은 조사는 뗀다 — "5실점으로"·"OPS .792로"가 말이 끊긴 것처럼 읽힌다.
    out = re.sub(r"(으로|로|와|과|이|가|은|는|을|를)$", "", out.strip())
    return out.strip(" ·,;.…-—→")


def _cells_for(jg: dict, side: str) -> list[str]:
    """`side`로 기운 칸들의 "라벨 짧은근거".

    ⚠️ **칸 기울기로 고른다.** 그 팀의 부호만 보고 고르면, 양쪽 다 ▼인 칸이
       "상대 우위"로 둔갑한다(실측 2026-08-27: 한화·SSG 선발이 둘 다 ▼인데
       "한화 우위"로 나갔다).
    """
    labels = dict(CELLS)
    tilt = tilt_by_cell(jg.get("cells") or {})
    out = []
    for key, _ in CELLS:
        if tilt.get(key) != side:
            continue
        v = ((jg.get("cells") or {}).get(side) or {}).get(key) or {}
        snip = _snippet(v.get("reason") or "", labels[key])
        out.append(f"{labels[key]} {snip}".strip())
    return out


def compare_lines(jg: dict) -> list[str]:
    """[§9-3단] 결론 **3줄**. 첫 줄이 결론이고, 긴 서술은 상세로 내려간다.

        KIA 타이거즈 우세  (3칸 대 1칸 · 확신 보통)
        ▲ 타선 OPS .792 · 최근 3경기 31득점
        ▼ 선발은 롯데 자이언츠 우위

    ⚠️ **확률을 쓰지 않는다.** 3단은 우세한 쪽과 칸 격차만 준다.
    ⚠️ 반대 방향 칸을 숨기지 않는다 — 짧게라도 셋째 줄에 남긴다.
    """
    v = jg.get("compare") or {}
    fav = v.get("favored")
    if not fav:
        return []
    conf = v.get("confidence") or "보통"
    icon = _CONF_ICON.get(conf, "🟡")
    c = v.get("counts") or {}
    gap = f"{c.get(fav, 0)}칸 대 {c.get('away' if fav == 'home' else 'home', 0)}칸 · " \
        if fav in ("home", "away") and c else ""
    if fav == "none":
        head = f"⚖️ 우열을 가리기 어렵다 ({gap}확신 {conf})"
        return [head]
    name = jg.get(f"{fav}_kr") or jg.get(fav) or fav
    other = "away" if fav == "home" else "home"
    other_name = jg.get(f"{other}_kr") or jg.get(other) or other
    lines = [f"{icon} {name} 우세 ({gap}확신 {conf})"]
    up = _cells_for(jg, fav)
    if up:
        lines.append("▲ " + " · ".join(up[:3]))
    # 반대 방향 — **상대 쪽으로 기운 칸**만. 숨기지 않되 짧게.
    down = _cells_for(jg, other)
    if down:
        lines.append(f"▼ {other_name} 우위 — " + " · ".join(down[:2]))
    return lines


def compare_line(jg: dict) -> str | None:
    """한 줄 요약 — 슬레이트 목록·판정 실패 경로용. 없으면 None."""
    lines = compare_lines(jg)
    return lines[0] if lines else None


def slate_compare_row(jg: dict) -> str:
    """슬레이트 첫 화면의 경기 1줄.

    ⚠️ **판정 못 한 경기도 남긴다.** 조용히 빠지면 분석된 것으로 오인된다
       — 몇 경기가 빠졌는지 사용자가 알 수 있어야 한다.
    """
    away = jg.get("away_kr") or jg.get("away") or "?"
    home = jg.get("home_kr") or jg.get("home") or "?"
    head = f"· {away} @ {home} — "
    v = jg.get("compare") or {}
    fav = v.get("favored")
    if not fav:
        why = ("LLM 응답 없음" if (jg.get("cells_status") or "") != "판정"
               else "카드 대조 실패")
        return head + f"판정 미수행 ({why})"
    conf = v.get("confidence") or "보통"
    c = v.get("counts") or {}
    if fav == "none":
        return head + f"우열 없음 ({c.get('home', 0)}:{c.get('away', 0)}, {conf})"
    name = jg.get(f"{fav}_kr") or jg.get(fav) or fav
    lose = c.get("away" if fav == "home" else "home", 0)
    return head + f"{name} 우세 ({c.get(fav, 0)}:{lose}, {conf})"


def card_summary_line(jg: dict) -> str | None:
    """기본층 한 줄 요약 — 어느 팀이 몇 칸에서 앞서는지.

    ⚠️ 이것은 **결론이 아니라 카드의 요약**이다. 어느 쪽이 이길지는 3단 대조봇의
       몫이고, 여기서는 판정된 칸을 세기만 한다. 세는 것과 결론짓는 것은 다르다.
    """
    cells = jg.get("cells") or {}
    if not (cells.get("home") or cells.get("away")):
        card = jg.get("card") or {}
        return ("🃏 상태 카드 — 해석 판정 미수행 (사실만 수집됨)"
                if card.get("home") else None)
    labels = dict(CELLS)
    home_kr = jg.get("home_kr") or jg.get("home") or "홈"
    away_kr = jg.get("away_kr") or jg.get("away") or "원정"
    up = {"home": [], "away": []}
    even = 0
    for key, _ in CELLS:
        h = ((cells.get("home") or {}).get(key) or {}).get("symbol")
        a = ((cells.get("away") or {}).get(key) or {}).get("symbol")
        if h == "▲" and a != "▲":
            up["home"].append(labels[key])
        elif a == "▲" and h != "▲":
            up["away"].append(labels[key])
        elif h and a:
            even += 1
    parts = []
    for side, name in (("away", away_kr), ("home", home_kr)):
        if up[side]:
            parts.append(f"{name} 우세 {len(up[side])}칸({'·'.join(up[side])})")
    if even:
        parts.append(f"대등 {even}칸")
    return "🃏 " + " · ".join(parts) if parts else "🃏 상태 카드 — 우세 칸 없음"
