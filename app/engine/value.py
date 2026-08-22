"""가치 계산: implied prob, EV, 하프 켈리(5% 상한), 앙상블, 휴리스틱 모델 확률."""


def implied_prob(odds: float) -> float:
    return 1.0 / odds


def devig(probs: list[float]) -> list[float]:
    """북 마진 제거 — 합이 1이 되도록 정규화."""
    total = sum(probs)
    return [p / total for p in probs]


def ev(p: float, odds: float) -> float:
    """Expected value: ev = p * odds - 1."""
    return p * odds - 1.0


def kelly(p: float, odds: float, fraction: float = 0.5, cap: float = 0.05) -> float:
    """하프 켈리, 뱅크롤 5% 상한. 음수면 0."""
    b = odds - 1.0
    if b <= 0:
        return 0.0
    full = (p * b - (1.0 - p)) / b
    return max(0.0, min(cap, full * fraction))


def ensemble(
    p_model: float, p_market: float, p_claude: float,
    w_model: float = 0.45, w_market: float = 0.30, w_claude: float = 0.25,
) -> float:
    """p_final = 0.45*p_model + 0.30*p_market + 0.25*p_claude (가중치는 config)."""
    return w_model * p_model + w_market * p_market + w_claude * p_claude


def heuristic_model_prob(
    home_wp: float, away_wp: float,
    home_era: float | None = None, away_era: float | None = None,
) -> float:
    """홈팀 승리 확률 휴리스틱 (플레이스홀더 모델).

    승률 차 + 홈 어드밴티지(+0.04) + 선발 ERA 차 보정. [0.05, 0.95]로 클램프.
    """
    p = 0.54 + 0.5 * (home_wp - away_wp)
    if home_era is not None and away_era is not None:
        p += 0.03 * (away_era - home_era)
    return max(0.05, min(0.95, p))
