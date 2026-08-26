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


@dataclass
class Cell:
    """한 팀·한 칸. 사실 층만 채워진 상태."""

    key: str
    label: str
    facts: list[str] = field(default_factory=list)
    source: str = ""

    @property
    def known(self) -> bool:
        return bool(self.facts)

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "facts": list(self.facts),
                "source": self.source, "known": self.known}


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
        out[key] = Cell(key=key, label=label, facts=facts, source=source)
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
