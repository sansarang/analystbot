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


def cell_metrics(research: dict, side: str, key: str) -> dict[str, float]:
    """그 칸의 수치 지표. 없는 값은 넣지 않는다."""
    u = research.get(f"{side}_usage") or {}
    p = research.get(f"{side}_pitcher") or {}
    o = research.get(f"{side}_offense") or {}
    st = research.get(f"{side}_standing") or {}
    src: dict[str, object] = {}
    if key == "bullpen":
        src = {k: u.get(k) for k in ("relief_batters_l3", "back_to_back_count",
                                     "pitchers_used_last")}
    elif key == "starter":
        src = {k: p.get(k) for k in ("era_season", "whip", "ip_avg_recent")}
    elif key == "batting":
        src = {"ops": o.get("ops")}
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
    b2b = u.get("back_to_back") or []
    if b2b:
        out.append(f"2경기 연속 등판 {len(b2b)}명: {', '.join(b2b)}")
    elif u.get("back_to_back_count") == 0:
        out.append("2경기 연속 등판 없음")
    return out, "네이버 기록(LLM 0회)"


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
    out = [" · ".join(bits)]
    if p.get("pitch_mix"):
        out.append(f"구종 {p['pitch_mix']}")
    # 예고인지 확정인지는 **섞으면 안 된다** — 예상을 확정으로 취급하면 안 된다
    if r.get("starter_status"):
        out.append(f"선발 발표: {r['starter_status']}")
    return out, "네이버·크롤러(LLM 0회)"


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
    return out, "크롤러·공식기록(LLM 0회)"


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
    return out, "네이버 기록(LLM 0회)"


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
    return [" · ".join(bits)], "네이버 순위(LLM 0회)"


_BUILDERS = {
    "bullpen": _bullpen_facts,
    "starter": _starter_facts,
    "batting": _batting_facts,
    "recent3": _recent3_facts,
    "weight": _weight_facts,
}


# ---------------------------------------------------------------- 카드 조립


def build_side(research: dict, side: str) -> dict[str, Cell]:
    """한 팀의 다섯 칸(사실 층만)."""
    out: dict[str, Cell] = {}
    for key, label in CELLS:
        facts, source = _BUILDERS[key](research or {}, side)
        out[key] = Cell(key=key, label=label, facts=facts, source=source,
                        metrics=cell_metrics(research or {}, side, key))
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
    return {
        "game_id": jg.get("game_id"),
        "home_team": jg.get("home"), "away_team": jg.get("away"),
        "home": {k: c.as_dict() for k, c in home.items()},
        "away": {k: c.as_dict() for k, c in away.items()},
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


def compare_line(jg: dict) -> str | None:
    """[§9-3단] 대조 결론 한 줄. 판정이 없으면 None(빈말을 만들지 않는다).

    ⚠️ **확률을 쓰지 않는다.** 3단은 우세한 쪽과 확신도만 준다 — 여기서
       "63%" 같은 숫자를 붙이면 3단이 말하지 않은 것을 말한 것이 된다.
    """
    v = jg.get("compare") or {}
    fav, why = v.get("favored"), (v.get("reason") or "").strip()
    if not fav:
        return None
    conf = v.get("confidence") or "보통"
    if fav == "none":
        return f"⚖️ 카드로는 우열을 가리기 어렵다 (확신 {conf})" + (f" — {why}" if why else "")
    name = jg.get(f"{fav}_kr") or jg.get(fav) or fav
    icon = {"높음": "🟢", "보통": "🟡", "낮음": "⚪"}.get(conf, "🟡")
    return f"{icon} 카드 우세: {name} (확신 {conf})" + (f" — {why}" if why else "")


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
