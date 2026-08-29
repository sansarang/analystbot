"""가치 계산: implied prob, EV, 하프 켈리(5% 상한), 앙상블."""


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
