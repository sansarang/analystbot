"""[1-2] 경기력 기반 승률 조정 — 수집한 정보가 **실제로 확률을 움직이게** 한다.

실사고(2026-08-25): 파드리스전에서 "애덤·머스그로브·피베타·지올리토 이탈"을 서술에
써놓고 승률은 58.7% 그대로였다. 결장·불펜 소모·선발 최근 폼이 서술에만 쓰이고 확률에
반영되지 않았기 때문이다. 이 모듈은 그 연결을 담당한다.

기준 승률(선발·팀 성적)에서 시작해 조정을 **순차 적용**하고, 모든 단계를 trace로 남긴다.
  "기준 55% → 선발 최근폼 우위 +3%p → 핵심 불펜 3명 이탈 -6%p → 최종 52%"

조정 계수는 전부 config에 있다 (adj_*). 임의로 바꾸지 말 것 — DISCIPLINE 5-1.
"""

import logging
import re

from app.config import get_settings

logger = logging.getLogger(__name__)

# 결장자 문장에서 역할을 읽어내는 표지
_CLOSER_MARKERS = ("마무리", "클로저", "closer", "셋업", "setup", "불펜", "bullpen", "구원")
_TOP_HITTER_MARKERS = ("주포", "간판", "최다", "핵심 타자", "중심 타선", "4번", "리드오프",
                       "팀 내 최고", "에이스 타자")
_STARTER_MARKERS = ("선발", "로테이션", "starter", "rotation")


def _pp(v: float) -> str:
    return f"{v * 100:+.0f}%p"


def trace_for(adjust: dict, side: str) -> list[str]:
    """[1] 조정 과정을 **대상팀 기준**으로 다시 쓴다.

    adjust()의 계산은 홈 기준이다. 마켓 보드가 원정팀 승률을 표시하는데 조정 과정만
    홈 기준이면 같은 화면에 두 기준이 섞여 읽을 수 없다 — 여기서 뒤집는다.
    상대팀 승률은 (100 - 대상팀)이므로 따로 계산하지 않는다.
    """
    if not adjust or not adjust.get("trace"):
        return []
    home, away = adjust.get("home"), adjust.get("away")
    if side == home or side is None:
        return list(adjust["trace"])

    out = [f"{away} 기준 {1 - _base_of(adjust):.0%}"]
    for step in adjust.get("applied") or []:
        label = step["label"]
        # 홈 기준 라벨의 방향 주석을 대상팀 관점으로 정리
        label = label.replace("(홈에 유리)", "").strip()
        out.append(f"{label} {_pp(-step['delta'])}")
    if adjust.get("capped"):
        out.append("추정 상한 적용")
    out.append(f"최종 {away} {adjust['p_away']:.0%} / {home} {adjust['p_home']:.0%}")
    return out


def _base_of(adjust: dict) -> float:
    """조정 전 기준 확률(홈 기준) 복원."""
    return adjust.get("p_home", 0.5) - (adjust.get("net_delta") or 0.0)


class WinProbAdjuster:
    """경기력 정보를 승률 조정으로 옮기는 계산기. 계수는 config에서만 온다."""

    def __init__(self, settings=None):
        self.s = settings or get_settings()

    # ------------------------------------------------------------ 개별 요소

    def starter_matchup(self, home_era5: float | None, away_era5: float | None) -> float:
        """선발 최근 5경기 ERA 차 1.00당 ±3%p (시즌이 아니라 **최근 폼** 기준)."""
        if home_era5 is None or away_era5 is None:
            return 0.0
        raw = (away_era5 - home_era5) * self.s.adj_starter_era_per_run
        cap = self.s.adj_starter_era_cap
        return max(-cap, min(cap, raw))

    def short_outings(self, ip_avg: float | None) -> float:
        """최근 평균 5이닝 미만이면 -2%p (불펜 조기 노출)."""
        if ip_avg is None or ip_avg >= 5.0:
            return 0.0
        return -self.s.adj_short_start

    def absences(self, items: list[str], team: str = "") -> tuple[float, list[str]]:
        """결장자 목록 → (조정치, 사유들). 역할별로 계수가 다르다."""
        total, notes = 0.0, []
        for raw in items or []:
            text = str(raw)
            low = text.lower()
            if any(m in text or m in low for m in _TOP_HITTER_MARKERS):
                delta, label = -self.s.adj_top_batter_out, "팀 최다 기여 타자 결장"
            elif any(m in text or m in low for m in _CLOSER_MARKERS):
                delta, label = -self.s.adj_key_reliever_out, "핵심 불펜 결장"
            elif any(m in text or m in low for m in _STARTER_MARKERS):
                delta, label = -self.s.adj_key_reliever_out, "선발 자원 이탈"
            else:
                delta, label = -self.s.adj_key_batter_out, "주전 결장"
            total += delta
            notes.append(f"{label}({_name_of(text, team)})")
        cap = self.s.adj_absence_cap
        if total < -cap:
            notes.append(f"결장 보정 상한 {_pp(-cap)} 적용")
            total = -cap
        return total, notes

    def bullpen_overuse(self, text: str | None) -> float:
        """최근 3일 불펜 소모가 과다하면 -3%p."""
        if not text:
            return 0.0
        low = str(text)
        if any(k in low for k in ("과부하", "혹사", "소모가 크", "과소모", "연투", "피로 누적")):
            return -self.s.adj_bullpen_overuse
        return 0.0

    def recent_form(self, form: str | None) -> float:
        """최근 5경기 4승 이상 +2%p / 4패 이상 -2%p."""
        if not form:
            return 0.0
        seq = [c for c in str(form).upper() if c in "WLD"][:5]
        if len(seq) < 5:
            return 0.0
        if seq.count("W") >= 4:
            return self.s.adj_form_hot
        if seq.count("L") >= 4:
            return -self.s.adj_form_cold
        return 0.0

    def home_edge(self, sport: str) -> float:
        return self.s.adj_home_mlb if sport == "mlb" else self.s.adj_home_soccer

    # ------------------------------------------------------------ 순차 적용

    def adjust(self, base_p: float, jg: dict, research: dict, sport: str) -> dict:
        """기준 승률 → 조정 순차 적용 → {p, trace, applied, unused}.

        p는 홈 승리 확률. trace는 화면에 그대로 찍을 수 있는 문자열 목록이다.
        """
        home_kr = jg.get("home", "홈")
        p = base_p
        trace = [f"{home_kr} 기준 {base_p:.0%}"]
        applied: list[dict] = []

        def step(delta: float, label: str) -> None:
            nonlocal p
            if abs(delta) < 1e-9:
                return
            p = max(0.05, min(0.95, p + delta))
            trace.append(f"{label} {_pp(delta)}")
            applied.append({"label": label, "delta": round(delta, 4)})

        hp = research.get("home_pitcher") or {}
        ap = research.get("away_pitcher") or {}

        # ① 선발 매치업 (최근 5경기 ERA 우선, 없으면 시즌으로 폴백하되 표기)
        h_era, h_src = _era5(hp)
        a_era, a_src = _era5(ap)
        delta = self.starter_matchup(h_era, a_era)
        if delta:
            src = "최근5" if h_src == a_src == "recent" else "시즌(최근5 미수집)"
            step(delta, f"선발 매치업({src}) {h_era:.2f} vs {a_era:.2f}")

        # ② 이닝 소화력
        step(self.short_outings(_ip_avg(hp)), "홈 선발 5이닝 미만")
        step(-self.short_outings(_ip_avg(ap)), "원정 선발 5이닝 미만(홈에 유리)")

        # ③ 결장 — 팀별로 나눠 적용 (홈 결장은 홈 승률에 마이너스)
        home_out, away_out = _split_absences(research.get("absences") or [], jg)
        h_delta, h_notes = self.absences(home_out, jg.get("home", ""))
        a_delta, a_notes = self.absences(away_out, jg.get("away", ""))
        if h_delta:
            step(h_delta, "홈 " + ", ".join(h_notes))
        if a_delta:
            step(-a_delta, "원정 " + ", ".join(a_notes) + "(홈에 유리)")

        # ④ 불펜 소모 — 전용 필드(bullpen_overused)가 있으면 어느 쪽인지까지 반영
        side_flag = str(research.get("bullpen_overused") or "").strip()
        pen = self.s.adj_bullpen_overuse
        if side_flag == "홈":
            step(-pen, "홈 불펜 과소모")
        elif side_flag == "원정":
            step(pen, "원정 불펜 과소모(홈에 유리)")
        elif side_flag == "양팀":
            trace.append("양 팀 불펜 과소모 — 상쇄, 조정 없음")
        else:
            step(self.bullpen_overuse(research.get("bullpen")), "불펜 과소모")

        # ⑤ 최근 폼
        step(self.recent_form((research.get("home_recent_form") or {}).get("form")), "홈 최근 폼")
        step(-self.recent_form((research.get("away_recent_form") or {}).get("form")),
             "원정 최근 폼(반대 방향)")

        # [3] 승률 추정 상한 — MLB 단일 경기 77%는 비현실적이다(리그 최강팀도 65% 안팎).
        cap = self.s.prob_cap_mlb if sport == "mlb" else self.s.prob_cap_soccer
        capped = False
        if p > cap:
            trace.append(f"추정 상한 적용 ({p:.0%} → {cap:.0%})")
            p, capped = cap, True
        elif p < 1 - cap:
            trace.append(f"추정 상한 적용 ({p:.0%} → {1 - cap:.0%})")
            p, capped = 1 - cap, True

        # [1] 홈/원정 혼동 방지 — 최종 줄에 양 팀 승률을 함께 적는다.
        away_kr = jg.get("away", "원정")
        trace.append(f"최종 {home_kr} {p:.0%} / {away_kr} {1 - p:.0%}")
        unused = _unused_material(research, applied)
        return {
            "p": round(p, 4), "trace": trace, "applied": applied, "unused": unused,
            "basis": "home",                       # trace의 확률은 홈 기준이다
            "home": home_kr, "away": away_kr,
            "p_home": round(p, 4), "p_away": round(1 - p, 4), "capped": capped,
            "net_delta": round(p - base_p, 4),     # 조정 총량 (홈 기준)
        }


# ---------------------------------------------------------------- 헬퍼

def _name_of(text: str, team: str = "") -> str:
    """결장 문장에서 **선수** 이름만 뽑는다 (팀명은 제외)."""
    s = str(text)
    if team:
        s = s.replace(team, " ")
    for m in re.finditer(r"[A-Z][a-z]+(?:[ -][A-Z][a-z]+)+", s):
        return m.group(0)
    m = re.search(r"([가-힣A-Za-z]+)\s*(?:의)?\s*(?:부상|결장|이탈|징계)", s)
    return m.group(1) if m else s.strip()[:18]


# 서술에서 최근 ERA 숫자를 건져내는 패턴 ("최근 5경기 ERA 2.41", "최근5 4.35")
_RECENT_ERA_RE = re.compile(
    r"최근\s*\d*\s*(?:경기|등판|선발)?\s*(?:평균\s*)?ERA\s*([0-9]+\.[0-9]+)|"
    r"최근\s*\d+\s*[:：]?\s*([0-9]+\.[0-9]+)\s*(?:ERA|자책)"
)


def _era_from_prose(text) -> float | None:
    """last5 서술에 숫자가 있으면 건져낸다 — era_recent가 비어도 최근 폼을 쓰기 위해.

    "2점대 중후반" 같은 서술형은 숫자가 아니므로 쓰지 않는다 (추정 금지).
    """
    m = _RECENT_ERA_RE.search(str(text or ""))
    if not m:
        return None
    val = m.group(1) or m.group(2)
    try:
        era = float(val)
    except (TypeError, ValueError):
        return None
    return era if 0.0 <= era <= 15.0 else None


def _era5(block: dict) -> tuple[float | None, str]:
    """선발 ERA — 최근 5경기 우선, 서술에서 추출 시도, 마지막이 시즌.

    [1-2]는 '시즌이 아니라 최근 폼 우선'이다. era_recent가 비면 서술에서 숫자를 건져
    최근 폼을 살리고, 그것도 없을 때만 시즌으로 폴백한다(폴백은 trace에 표기된다).
    """
    if block.get("era_recent") is not None:
        return float(block["era_recent"]), "recent"
    prose = _era_from_prose(block.get("last5"))
    if prose is not None:
        return prose, "recent"
    if block.get("era_season") is not None:
        return float(block["era_season"]), "season"
    return None, "none"


def _ip_avg(block: dict) -> float | None:
    """선발 최근 평균 이닝 — 전용 필드 우선, 없으면 last5 서술에서 읽어낸다."""
    if block.get("ip_avg_recent") is not None:
        try:
            return float(block["ip_avg_recent"])
        except (TypeError, ValueError):
            pass
    m = re.search(r"평균\s*([0-9]+(?:\.[0-9])?)\s*이닝", str(block.get("last5") or ""))
    return float(m.group(1)) if m else None


def _split_absences(items: list[str], jg: dict) -> tuple[list[str], list[str]]:
    """결장 문장을 홈/원정으로 가른다. 팀명이 없으면 어느 쪽인지 몰라 버린다."""
    from app.collectors.football import similar_team

    home, away = jg.get("home", ""), jg.get("away", "")
    h_keys = {home.lower(), home.split()[-1].lower()} if home else set()
    a_keys = {away.lower(), away.split()[-1].lower()} if away else set()
    home_out, away_out = [], []
    for raw in items:
        low = str(raw).lower()
        if any(k and k in low for k in h_keys) or similar_team(home, str(raw)[:40]):
            home_out.append(raw)
        elif any(k and k in low for k in a_keys) or similar_team(away, str(raw)[:40]):
            away_out.append(raw)
    return home_out, away_out


# [4-3] 수집 정보 → 조정 계수 매핑표. 여기 없는 필드는 확률에 반영되지 않는다.
FIELD_TO_COEFFICIENT = {
    "home_pitcher.era_recent": "선발 매치업 (adj_starter_era_per_run)",
    "away_pitcher.era_recent": "선발 매치업 (adj_starter_era_per_run)",
    "home_pitcher.ip_avg_recent": "이닝 소화력 (adj_short_start)",
    "away_pitcher.ip_avg_recent": "이닝 소화력 (adj_short_start)",
    "absences": "결장 (adj_key_batter_out / adj_top_batter_out / adj_key_reliever_out)",
    "bullpen_overused": "불펜 소모 (adj_bullpen_overuse)",
    "bullpen": "불펜 소모 (adj_bullpen_overuse, 서술에서 추출)",
    "home_recent_form.form": "최근 폼 (adj_form_hot / adj_form_cold)",
    "away_recent_form.form": "최근 폼 (adj_form_hot / adj_form_cold)",
}

# 서술에는 쓰이지만 확률 계수가 없는 필드 — 반드시 '(확률 미반영)'으로 표기한다
UNMAPPED_FIELDS = {
    "splits": "홈/원정 스플릿",
    "h2h_history": "상대전적",
    "rotation_plan": "로테이션 계획",
    "park": "구장 특성",
    "weather": "날씨",
    "predicted_scores": "예상 스코어",
    # [§8-7] 신규 맥락 필드 — 측정된 계수가 없으므로 λ를 건드리지 않는다.
    #   판정(p_claude)은 이 값들을 보고 확률을 움직이지만, 순차 조정 계수는 없다.
    #   계수를 임의로 만들면 측정되지 않은 튜닝이 된다(DISCIPLINE 5-1).
    #   → 계수를 붙이려면 먼저 백테스트로 방향과 크기를 측정하라.
    "motivation": "동기·경기 중요도",
    "schedule_load": "일정 부담·이동",
    "umpire": "주심 스트라이크존 성향",
    "line_move_reason": "라인 무브 사유",
    # [§8-21] 팬 여론 — 계수를 만들지 않는다. 동조 신호인지 역행 신호(팬심 편향)인지
    #   측정된 적이 없다. 판정이 읽되 λ는 건드리지 않으므로 '(확률 미반영)'이다.
    "fan_sentiment": "팬 여론·목격담",
}


def _unused_material(research: dict, applied: list[dict]) -> list[str]:
    """[4-3] 서술에는 있으나 확률에 반영되지 않은 재료 — '(확률 미반영)' 표기용.

    ①매핑 계수가 아예 없는 필드 ②매핑은 있으나 이번에 적용되지 않은 필드 둘 다 잡는다.
    """
    labels = " ".join(a["label"] for a in applied)
    out = [name for key, name in UNMAPPED_FIELDS.items() if research.get(key)]
    if research.get("absences") and "결장" not in labels:
        out.append("결장 정보(소속 불명으로 미적용)")
    if (research.get("bullpen") or research.get("bullpen_overused")) and "불펜" not in labels:
        out.append("불펜 소모")
    return out
