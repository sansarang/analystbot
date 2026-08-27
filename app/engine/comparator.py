"""[§9 3단] 대조봇 — **카드 두 장만 보고** 어느 쪽이 유리한지 고른다.

이 모듈의 존재 이유도 2단과 같은 **정보 차단벽**이다.
  3단이 원본 사실(리서치 JSON·λ·배당·전적)에 닿으면, 카드를 무시하고 원본에서
  결론을 세운 뒤 카드를 거기 맞춘다. 그러면 1·2단의 규율이 전부 무의미해진다.
  → 3단은 **▲▼=와 한 줄 사유, 그리고 미수집 칸 목록만** 본다.

⚠️ **3단은 사실을 새로 만들 수 없다.** 입력에 없는 선수 이름·수치를 쓰면
   그 문장은 폐기된다(`cites_cards`). 2단의 인용 강제와 같은 장치다.

⚠️ **확률을 만들지 않는다.** 출력은 (우세한 쪽, 확신도, 근거 칸, 한 줄)이다.
   "63%" 같은 숫자를 3단이 지어내면 그것이 근거처럼 읽힌다 — 이 프로젝트가
   λ에서 이미 겪은 실패다.

⚠️ **양쪽 판정이 모두 비어 있으면 부르지 않는다.** 재료 없이 결론을 만들지
   않는다는 규율이 여기에도 적용된다.
"""
from __future__ import annotations

import json
import logging
import re

from app.config import get_settings
from app.engine.card import CELLS
from app.llm import complete, role_enabled

logger = logging.getLogger(__name__)

ROLE = "judge_a"
SIDES = ("home", "away")
CONFIDENCE = ("높음", "보통", "낮음")

# 3단이 절대 봐서는 안 되는 것들 — payload에 이 키가 있으면 차단벽이 뚫린 것이다.
FORBIDDEN_KEYS = (
    "research", "facts", "metrics", "lambda", "lam", "p_model", "p_claude",
    "p_market", "p_final", "p_legacy", "odds", "best_odds", "market_board",
    "alt_markets", "ev", "kelly", "verdict", "picks", "stats", "elo",
    "h2h", "standings", "narrative", "expert_picks", "news", "sentiment",
)

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "favored": {"type": "string", "enum": ["home", "away", "none"],
                    "description": "카드상 유리한 쪽. 가릴 수 없으면 none"},
        "confidence": {"type": "string", "enum": list(CONFIDENCE),
                       "description": "카드 차이가 얼마나 뚜렷한가"},
        "basis_cells": {"type": "array", "items": {"type": "string"},
                        "description": "판단 근거가 된 칸 키들"},
        "reason": {"type": "string",
                   "description": "한 줄. **카드에 적힌 사유의 말을 인용**한다"},
    },
    "required": ["favored", "confidence", "basis_cells", "reason"],
    "additionalProperties": False,
}

SYSTEM = """너는 야구 분석가다. **두 팀의 상태 카드만** 보고 어느 쪽이 유리한지 고른다.

[네가 보는 것]
각 팀의 다섯 칸에 대한 판정(▲ 유리 / ▼ 불리 / = 특이사항 없음)과 그 한 줄 사유.
그리고 아직 수집되지 않은 칸의 목록.

[네가 모르는 것 — 묻지도, 지어내지도 마라]
- 원본 기록·수치·리서치 전문. 카드에 적힌 것이 전부다.
- 배당·확률·과거 전적·전문가 픽·뉴스.
- 그러므로 **승률 숫자를 만들지 마라.** "60%" 같은 수치를 쓰면 폐기된다.

[네가 하는 일]
1. 칸별로 두 팀을 맞대어 본다. ▲ vs ▼는 뚜렷한 차이, ▲ vs ▲는 차이가 아니다.
2. 유리한 쪽을 고른다. **가릴 수 없으면 none을 골라라** — 억지로 고르는 것이
   가장 나쁘다.
3. 확신도를 매긴다.
   - 높음: 여러 칸이 같은 방향을 가리키고, 반대 방향 칸이 없다
   - 보통: 방향이 갈리지만 한쪽이 더 무겁다
   - 낮음: 차이가 작거나, 미수집 칸이 많아 카드가 얇다
4. 근거가 된 칸을 basis_cells에 적는다. 보지 않은 칸을 적지 마라.

[반드시 지킬 것]
- **팀을 부를 때는 주어진 팀 이름을 쓴다.** "홈"·"원정"이라고 쓰지 마라 —
  읽는 사람은 어느 쪽이 홈인지 모른다.
- **사유는 카드에 적힌 말을 인용해서 쓴다.** 카드에 없는 선수 이름·숫자를
  쓰면 그 판정은 폐기된다.
- 미수집 칸이 많으면 확신도를 낮춰라. 모르는 것을 유리·불리로 세지 마라.
- 한국어로, 한 줄로 쓴다.

⚠️ 칸 하나가 반대 방향이라고 무시하지 마라. 그 칸을 근거에서 빼든지,
   확신도를 낮추든지 해야 한다. 불리한 칸을 못 본 척하는 것이 가장 흔한 실수다."""


def build_payload(jg: dict) -> dict:
    """[차단벽] 3단에 넘길 입력. **카드 두 장만** 담는다.

    ⚠️ 이 함수가 차단벽의 실체다. 원본 사실·확률·배당은 **한 조각도** 들어가지
       않으며, `test_comparator_wall.py`가 이 함수의 출력을 직접 검사한다.
       필드를 추가할 때는 그 테스트를 먼저 보라.
    """
    labels = dict(CELLS)
    cells = jg.get("cells") or {}
    card = jg.get("card") or {}
    out = {"home_team": jg.get("home_kr") or jg.get("home"),
           "away_team": jg.get("away_kr") or jg.get("away"),
           "cards": {}, "uncollected": []}
    for side in SIDES:
        rows = []
        for key, label in CELLS:
            v = (cells.get(side) or {}).get(key) or {}
            sym = v.get("symbol")
            if not sym:
                continue
            rows.append({"cell": key, "label": label, "symbol": sym,
                         "reason": (v.get("reason") or "").strip()})
        out["cards"][side] = rows
    # 미수집 칸은 **라벨만** 준다 — 어떤 사실이 없는지는 3단이 알 필요가 없고,
    # 알면 그 빈칸을 상상으로 메운다.
    seen = {r["cell"] for side in SIDES for r in out["cards"][side]}
    out["uncollected"] = [labels[k] for k, _ in CELLS if k not in seen]
    return out


def has_material(payload: dict) -> bool:
    """판정할 재료가 있는가. 없으면 부르지 않는다."""
    return any(payload.get("cards", {}).get(side) for side in SIDES)


_TOKEN = re.compile(r"\d+(?:\.\d+)?|[가-힣]{2,}|[A-Za-z]{2,}")
# 3단 사유에서 인용으로 인정하지 않는 흔한 말
_STOP = {"카드", "우세", "유리", "불리", "경기", "상태", "칸이", "칸에", "쪽이",
         "판정", "차이", "방향", "근거", "여러", "모두", "반대", "그러나", "다만",
         "최근", "선발", "불펜", "타선", "무게", "가용"}


def cites_cards(reason: str, payload: dict) -> bool:
    """사유가 카드에 적힌 말을 실제로 인용했는가.

    2단의 `cites_facts`와 같은 장치다. 3단이 카드에 없는 근거를 지어내면
    사용자에게는 그것이 수집된 사실처럼 읽힌다.
    """
    if not reason:
        return False
    pool = " ".join(r.get("reason") or "" for side in SIDES
                    for r in payload.get("cards", {}).get(side) or [])
    pool += " " + " ".join(str(payload.get(k) or "")
                           for k in ("home_team", "away_team"))
    have = set(_TOKEN.findall(pool)) - _STOP
    used = set(_TOKEN.findall(reason)) - _STOP
    return bool(have & used)


_PCT = re.compile(r"\d+(?:\.\d+)?\s*(?:%|퍼센트|프로)")


def invents_probability(reason: str) -> bool:
    """🔴 3단이 승률을 지어냈는가. 지어낸 숫자는 근거처럼 읽힌다."""
    return bool(_PCT.search(reason or ""))


def basis_is_real(basis: list, payload: dict) -> list[str]:
    """근거로 든 칸 중 **실제로 판정이 있는** 것만 남긴다."""
    real = {r["cell"] for side in SIDES
            for r in payload.get("cards", {}).get(side) or []}
    return [k for k in (basis or []) if k in real]


def thin_card_caps_confidence(payload: dict, confidence: str) -> str:
    """미수집 칸이 절반을 넘으면 확신도를 '낮음'으로 내린다.

    ⚠️ 절반은 실측값이 아니라 **카드 구조에서 나온 값**이다 — 다섯 칸 중 셋
       이상이 비면 남은 둘로 다섯 칸짜리 판단을 하는 셈이다. 채점 데이터가
       쌓이면 미수집 칸 수와 적중률의 관계를 보고 교체한다.
    """
    if len(payload.get("uncollected") or []) * 2 > len(CELLS):
        return "낮음"
    return confidence if confidence in CONFIDENCE else "보통"


async def compare_game(jg: dict, settings=None) -> dict:
    """카드 두 장 → {"favored", "confidence", "basis_cells", "reason", "provider"}.

    재료가 없거나 역할이 꺼져 있거나 폐기되면 **빈 dict**를 돌려준다 —
    빈 판정을 'none 우세'로 채우면 판정한 것처럼 보인다.
    """
    s = settings or get_settings()
    payload = build_payload(jg)
    if not has_material(payload):
        return {}
    if not role_enabled(ROLE, s):
        logger.info("[3단] 대조봇 비활성 — 카드만 나간다")
        return {}
    res = await complete(
        ROLE, [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        system=SYSTEM, schema=VERDICT_SCHEMA, max_tokens=1200, settings=s)
    data = res.data or {}
    reason = (data.get("reason") or "").strip()
    favored = data.get("favored")
    if favored not in ("home", "away", "none"):
        logger.warning("[3단] 알 수 없는 판정 %r — 폐기", favored)
        return {}
    if invents_probability(reason):
        logger.warning("[3단] 승률을 지어냈다 — 폐기: %s", reason[:80])
        return {}
    if favored != "none" and not cites_cards(reason, payload):
        logger.warning("[3단] 카드 인용 없음 — 폐기: %s", reason[:80])
        return {}
    return {
        "favored": favored,
        "confidence": thin_card_caps_confidence(payload, data.get("confidence")),
        "basis_cells": basis_is_real(data.get("basis_cells"), payload),
        "reason": reason,
        "provider": res.label,
    }
