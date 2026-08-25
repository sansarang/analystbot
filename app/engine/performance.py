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
        p = base_p
        trace = [f"기준 {base_p:.0%}"]
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

        # ④ 불펜 소모 (양 팀 공통 서술이면 홈 기준으로만 반영)
        step(self.bullpen_overuse(research.get("bullpen")), "불펜 과소모")

        # ⑤ 최근 폼
        step(self.recent_form((research.get("home_recent_form") or {}).get("form")), "홈 최근 폼")
        step(-self.recent_form((research.get("away_recent_form") or {}).get("form")),
             "원정 최근 폼(반대 방향)")

        trace.append(f"최종 {p:.0%}")
        unused = _unused_material(research, applied)
        return {"p": round(p, 4), "trace": trace, "applied": applied, "unused": unused}


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


def _era5(block: dict) -> tuple[float | None, str]:
    """선발 ERA — 최근 5경기 우선, 없으면 시즌."""
    if block.get("era_recent") is not None:
        return float(block["era_recent"]), "recent"
    if block.get("era_season") is not None:
        return float(block["era_season"]), "season"
    return None, "none"


def _ip_avg(block: dict) -> float | None:
    """last5 서술에서 '평균 N이닝'을 읽어낸다 (없으면 None)."""
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


def _unused_material(research: dict, applied: list[dict]) -> list[str]:
    """[4-3] 서술에는 있으나 확률에 반영되지 않은 재료 — '(확률 미반영)' 표기용."""
    labels = " ".join(a["label"] for a in applied)
    out = []
    if research.get("absences") and "결장" not in labels:
        out.append("결장 정보")
    if research.get("bullpen") and "불펜" not in labels:
        out.append("불펜 소모")
    if research.get("splits"):
        out.append("홈/원정 스플릿")
    if research.get("h2h_history"):
        out.append("상대전적")
    return out
