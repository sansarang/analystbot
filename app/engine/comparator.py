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
3. 근거가 된 칸을 basis_cells에 적는다. 보지 않은 칸을 적지 마라.

⚠️ **확신도는 네가 정하지 않는다.** 칸 격차와 미수집 칸 수를 보고 코드가
   계산한다. confidence 필드는 형식상 필요하니 아무 값이나 넣어도 되고,
   그 값은 쓰이지 않는다. 대신 **어느 쪽이 유리한지와 그 이유**에 집중하라.

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


from app.engine.card import SYM_VALUE as _SYM_VALUE   # 부호 수치값의 정의는 한 곳


def cell_counts(payload: dict) -> dict:
    """칸별로 두 팀 부호를 맞대어 어느 쪽으로 기우는지 센다.

    한 칸은 **양쪽 부호를 비교해야** 기울기를 안다. 한쪽만 ▲인 것과 양쪽 다
    ▲인 것은 다르다 — 후자는 차이가 아니다.

    ⚠️ 한쪽이라도 판정이 없는 칸은 어느 쪽으로도 세지 않는다(`unknown`).
       모르는 것을 유리·불리로 세면 얇은 카드가 두꺼운 카드처럼 보인다.
    """
    rows = {side: {r["cell"]: r["symbol"]
                   for r in payload.get("cards", {}).get(side) or []}
            for side in SIDES}
    out = {"home": 0, "away": 0, "even": 0, "unknown": 0}
    for key, _ in CELLS:
        h, a = rows["home"].get(key), rows["away"].get(key)
        if h is None or a is None:
            out["unknown"] += 1
            continue
        diff = _SYM_VALUE.get(h, 0) - _SYM_VALUE.get(a, 0)
        out["home" if diff > 0 else "away" if diff < 0 else "even"] += 1
    return out


# [확신도] **코드가 정한다.** LLM에 맡기면 같은 격차를 매번 다르게 부른다.
#   기준은 우세한 쪽이 가져간 칸 수다.
#   ⚠️ 이 경계(4 / 2~3 / 1)는 사용자가 정한 운용 규칙이지 실측이 아니다.
#      `cell_ledger`에 칸별 적중률이 쌓이면 "몇 칸 차이부터 실제로 잘 맞는가"를
#      보고 교체한다. 그 전까지 이 숫자로 "확신도가 정확하다"고 말하지 마라.
CONF_HIGH_CELLS = 4        # 이만큼 가져가면 높음
CONF_MID_CELLS = 2         # 이만큼부터 보통 (그 아래는 낮음)


def confidence_from(counts: dict, favored: str) -> str:
    """칸 격차 → 확신도. 미수집이 절반을 넘으면 한 단계 내린다.

    ⚠️ 격차만 보면 5칸 중 3칸이 미수집인데 남은 2칸이 갈려 "2:0 = 높음"이 된다.
       채워진 칸이 얼마나 되는지를 함께 봐야 한다.
    """
    if favored not in SIDES:
        return "낮음"
    won = counts.get(favored, 0)
    level = ("높음" if won >= CONF_HIGH_CELLS
             else "보통" if won >= CONF_MID_CELLS else "낮음")
    if counts.get("unknown", 0) * 2 > len(CELLS):
        level = {"높음": "보통", "보통": "낮음"}.get(level, "낮음")
    return level


def thin_card_caps_confidence(payload: dict, confidence: str) -> str:
    """[구버전 호환] 미수집이 절반을 넘으면 '낮음'. 새 경로는 `confidence_from`."""
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
    counts = cell_counts(payload)
    conf = confidence_from(counts, favored)
    # LLM이 고른 쪽과 칸 셈이 어긋나면 **확신도를 낮춘다.** 어느 한쪽을 무조건
    # 믿지 않는다 — LLM은 칸의 무게를 다르게 볼 수 있고(그게 3단의 일이다),
    # 그렇더라도 셈과 어긋난다는 사실 자체가 확신을 낮출 이유다.
    lead = ("home" if counts["home"] > counts["away"]
            else "away" if counts["away"] > counts["home"] else "none")
    if favored in SIDES and lead in SIDES and favored != lead:
        logger.warning("[3단] 판정(%s)과 칸 셈(%s)이 어긋남 %s — 확신도 낮음",
                       favored, lead, counts)
        conf = "낮음"
    return {
        "favored": favored,
        "confidence": conf,
        "counts": counts,
        "basis_cells": basis_is_real(data.get("basis_cells"), payload),
        "reason": reason,
        "provider": res.label,
    }
