"""[ANL-1] 분석 LLM — 추출·계산과 서술 **사이**의 추론 자리 (Part 3 / Phase 4.5).

지금 봇은 추출(위성)·계산(코드)·서술(Gemini)만 있고 추론 자리가 없다.
"60%는 과대"는 확률 계산이 아니라 **사실 두 개를 시장 가격과 대조한 추론**이다.
LLM 은 이 대조를 잘 하고 **숫자 생성은 못 한다**(원장 실측 AUC 0.5151).

🔴 ② 출력은 `p_code`·확신·pick 을 **바꾸지 않는다.** 구조 후보는 Phase 5-2
   규칙에 제출될 뿐이고 채택(+6%p)은 코드가 한다.
🔴 **배당 원값은 입력에 없다.** 확률 %p 가공값만 간다(지시문 공통 원칙 3).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

#: 출력 스키마(지시문 4.5-3). 이 칸 **외에는 반려**한다.
SCHEMA = ("결정축", "결정축_근거", "결정축_방향", "반대축",
          "시장_판단", "시장_판단_이유", "구조_후보", "불확실", "근거_수")

DIRECTIONS = ("홈 하향", "홈 상향", "판단불가")
MARKET_VIEWS = ("과대", "적정", "과소")

#: 🔴 [ANL-2] **숫자를 쓸 수 없는 칸.** `l1` 이 이 목록으로 반려하고,
#   `output_spec` 이 같은 목록으로 미리 말해 준다 — 두 곳에 손으로 적으면 사본이다.
#   실측 2026-09-17: 지시문을 붙이자 JSON 은 왔는데 L1 이 "결정축_근거 에
#   확률·배당 숫자가 있다"로 반려했다. 금지를 **말하지 않고** 반려하고 있었다.
NO_NUM_KEYS = ("결정축", "결정축_근거", "반대축")

#: 🔴 [ANL-2] `시장_판단_이유` 에서 금지하는 말. `l1` 이 이 목록으로 반려하고
#   `output_spec` 이 같은 목록으로 미리 말한다. 실측 2026-09-17: 숫자 금지를
#   말해 준 뒤 다음 반려가 "시장_판단_이유 에 배당이 있다" 였다 — 반려 사유를
#   하나씩 말해 주지 않으면 통과할 수 없는 시험이었다.
REASON_BANNED = ("배당",)

#: 🔴 **실측이 지시문을 뒤집었다**(2026-09-13).
#     지시문 1순위 gemini-pro 무료 → 429 "prepayment credits are depleted"
#                                    (무료 티어가 아니라 유료 선불, 잔액 0)
#     지시문 2순위 nvidia nemotron → 404(계정 미할당) 또는 45초 타임아웃
#     실측 가능    groq 0.14s · 한도 헤더 가시 · openrouter :free 0.33s
#  ⚠️ groq `gpt-oss-120b` 는 **추론 토큰을 먼저 쓴다.** max_tokens 가 작으면
#     추론에 다 쓰여 content 가 빈 문자열로 온다(24토큰 → '', 256 → 정상).
#  ⚠️ `qwen/qwen3.6-27b` 는 `<think>` 를 content 에 섞는다 — 넣지 않는다.
#  ⚠️ 유료는 어느 자리에도 없다(지시문 4.5-9).
MODEL_CHAIN = (
    ("groq", "openai/gpt-oss-120b"),
    ("openrouter", "nex-agi/nex-n2.5-pro:free"),
    ("groq", "openai/gpt-oss-20b"),
)

#: 하루 호출 상한(지시문 4.5-9). 게이트 대상 6~8 × 스왑 2 + T-60 재실행.
DAILY_CAP = 32
#: 추론 토큰까지 담을 넉넉한 상한. 작으면 content 가 빈다(위 실측).
MAX_TOKENS = 2048
#: L1 반려 이 횟수를 넘으면 ② 없이 ③ 으로 간다.
MAX_REJECT = 2

PROMPT_DIR = Path("prompts")

#: 숫자·퍼센트·배당이 문장에 섞였는가. 🔴 LLM 은 숫자를 만들지 않는다.
_NUM = re.compile(r"\d+\s*%|\d+\.\d+|\b0\.\d+\b|배당")
_WORD = re.compile(r"[A-Za-z가-힣]{2,}")


def prompt_for(sport: str) -> str:
    name = "analyze_baseball.md" if (sport or "").lower() != "soccer" \
        else "analyze_soccer.md"
    p = PROMPT_DIR / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _pct3(t) -> str:
    if not t:
        return "—"
    return "/".join(str(round(float(x) * 100)) for x in t)


#: 🔴 [ANL-2 2026-09-17] 되고 있는 판정 프롬프트에서 **그대로 베낀 문장**이다
#   (`prompts.py` :29 :104 :338). 계약이 그 문장이 실재하는지 대조한다 —
#   거기서 바뀌면 여기가 사본으로 남는 것을 막는다.
JSON_ONLY = "아래 JSON만 출력한다. 다른 텍스트, 마크다운 백틱 금지."


def output_spec() -> str:
    """출력 지시. 🔴 칸 이름·라벨을 **손으로 적지 않는다** — 스키마에서 만든다.

    🔴 **숫자를 한 글자도 쓰지 않는다.** `l1` 이 "시장_판단_이유의 숫자가 입력
       블록에 있는가"를 재는데, 지시문에 숫자가 있으면 그 기준이 넓어진다.
    """
    return "\n".join([
        "[출력] " + JSON_ONLY,
        "칸: " + " · ".join(SCHEMA),
        "결정축_방향: " + " | ".join(DIRECTIONS),
        "시장_판단: " + " | ".join(MARKET_VIEWS),
        "구조_후보: 목록. 없으면 빈 목록",
        "근거_수: 정수",
        # 🔴 `l1` 이 반려하는 규칙을 **미리 말한다.** 목록은 `NO_NUM_KEYS` 가
        #    원본이다 — 여기서 칸 이름을 다시 적지 않는다.
        " · ".join(NO_NUM_KEYS) + ": 확률·배당 숫자를 쓰지 않는다. 사실만 쓴다",
        # 🔴 `l1` 의 나머지 반려 사유도 미리 말한다. 목록 원본은 위 상수다.
        "시장_판단_이유: 위 [숫자] 에 있는 값만 인용한다. "
        + "·".join(REASON_BANNED) + " 이라는 말은 쓰지 않는다",
    ])


def build_input(blk: dict, *, with_schema: bool = False) -> str:
    """코드가 조립하는 입력 블록(지시문 4.5-2). **이 외에는 넣지 않는다.**

    🔴 배당 원값 없음. 전적·BvP·시즌 누적 없음.
    🔴 [ANL-2] `with_schema` 는 **기본이 거짓**이다. `l1` 이 이 함수를 검사
       기준으로도 쓰기 때문이다 — 지시문이 섞이면 "근거가 입력의 사실인가"를
       스키마 이름으로 때워도 통과하고, 숫자 검사의 기준도 넓어진다.
       그래서 **실제 호출만** 참으로 부른다(:run).
    """
    b = blk or {}
    pp = b.get("p_prior")
    pm = b.get("p_market")
    lines = [
        f"[경기] {b.get('home')} vs {b.get('away')} · {b.get('league')} "
        f"· KST {b.get('kickoff_kst')}",
        "[숫자 — 변경 불가]",
        f"p_prior {_pct3(pp) if isinstance(pp, (tuple, list)) else pp} · "
        f"p_market(open) {_pct3(pm) if isinstance(pm, (tuple, list)) else pm} · "
        f"gap {b.get('gap_pp')} · 게이트 \"{b.get('gate')}\"",
    ]
    adj = b.get("adj_pp") or {}
    if adj:
        lines.append("adj(코드): "
                     + " · ".join(f"{k} {v:+g}" for k, v in adj.items())
                     + f" → p_code {b.get('p_code')}")
    der = b.get("derived") or []
    if der:
        lines.append("파생 디빅: "
                     + " · ".join(f"{d['시장']} {round(float(d['확률']) * 100)}%"
                                  for d in der))
    for side, label in (("home_facts", "홈"), ("away_facts", "원정")):
        f = b.get(side) or {}
        bits = []
        out = f.get("out") or []
        bits.append("결장 " + ("·".join(out) if out else "없음"))
        if f.get("last3"):
            bits.append("최근3 " + ", ".join(f["last3"]))
        if f.get("xi_status"):
            bits.append(f"XI {f['xi_status']}")
        if f.get("midweek"):
            bits.append(str(f["midweek"]))
        lines.append(f"[{label} 사실] " + " · ".join(bits))
    reg = b.get("regulars") or {}
    if reg:
        lines.append("[주전 판정] "
                     + " · ".join(f"{k} = 최근 10경기 {v}회 선발"
                                  for k, v in reg.items()))
    if b.get("notes"):
        lines.append(f"[notes] {b['notes']}")
    miss = b.get("missing") or []
    lines.append("[missing] " + ("·".join(miss) if miss else "없음"))
    if with_schema:
        lines.append(output_spec())
    return "\n".join(lines)


def _nouns(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(str(text or ""))}


def l1(out: dict, blk: dict) -> tuple[bool, str]:
    """L1 검사(지시문 4.5-7). 통과하면 `(True, "")`.

    🔴 셋을 본다: 숫자 금지 · 근거가 입력에 있는가 · 구조 후보가 실재하는가.
    """
    if not isinstance(out, dict):
        return False, "출력이 객체가 아니다"
    missing = [k for k in SCHEMA if k not in out]
    if missing:
        return False, f"칸 누락 {missing}"
    if out.get("결정축_방향") not in DIRECTIONS:
        return False, f"방향 라벨이 표 밖이다: {out.get('결정축_방향')!r}"
    if out.get("시장_판단") not in MARKET_VIEWS:
        return False, f"시장_판단 라벨이 표 밖이다: {out.get('시장_판단')!r}"
    blk_text = build_input(blk)
    # 🔴 **사실 칸은 숫자를 못 쓴다.** LLM 이 확률을 지어내는 것을 막는 자리다.
    for key in NO_NUM_KEYS:
        if _NUM.search(str(out.get(key) or "")):
            return False, f"{key} 에 확률·배당 숫자가 있다"
    # ⚠️ `시장_판단_이유` 만 예외다 — 지시문 규칙("% 출력 금지")과 지시문 예시
    #    ("60%는 브랜드 가격")가 서로 모순이라 **목적으로 갈랐다.** 금지의
    #    목적은 LLM 이 숫자를 **만드는** 것이고, 주어진 값을 인용하는 것은
    #    다른 일이다. 그래서 **입력 블록에 있는 숫자만** 허용한다.
    for m in _NUM.finditer(str(out.get("시장_판단_이유") or "")):
        tok = m.group(0).replace(" ", "")
        bare = tok.rstrip("%")
        if tok in REASON_BANNED:
            return False, f"시장_판단_이유 에 {tok}이 있다"
        if bare not in blk_text.replace(" ", ""):
            return False, f"시장_판단_이유 에 입력에 없는 숫자가 있다: {tok}"
    src = _nouns(blk_text)
    words = {w for w in _nouns(out.get("결정축_근거")) if len(w) >= 3}
    if words and not (words & src):
        return False, "결정축_근거가 입력 블록에 없는 사실이다"
    names = {str(d.get("시장") or "") for d in (blk or {}).get("derived") or []}
    for c in out.get("구조_후보") or []:
        if str(c.get("시장") or "") not in names:
            return False, f"구조_후보가 파생 디빅에 없는 시장이다: {c.get('시장')!r}"
    return True, ""


def swap(a: dict | None, b: dict | None) -> dict | None:
    """사이드 스왑 2회 대조(지시문 4.5-4).

    🔴 `결정축_방향` 이 갈리면 **판단불가로 강제**하고 확신을 낮춘다.
       한쪽만 있으면 그것도 불일치다 — 한 번밖에 못 물은 것이기 때문이다.
    """
    if not a and not b:
        return None
    base = dict(a or b or {})
    agree = bool(a and b and a.get("결정축_방향") == b.get("결정축_방향"))
    if not agree:
        base["결정축_방향"] = "판단불가"
    base["swap_agree"] = agree
    return base


def gate_vs_llm(gate_label: str | None, market_view: str | None) -> str | None:
    """코드 게이트와 LLM 판단이 같은 방향인가. **이 불일치 자체가 측정 대상**이다."""
    if not gate_label or not market_view:
        return None
    same = {"시장 과대": "과대", "가치 의심": "과소", "동의": "적정"}
    return "same" if same.get(gate_label) == market_view else "diff"


def to_ledger(out: dict | None, *, model: str | None,
              gate_label: str | None, failed: bool = False) -> dict:
    """원장 칸으로. ⚠️ 확률·확신·pick 은 **건드리지 않는다.**"""
    o = out or {}
    return {
        "main_axis": o.get("결정축"),
        "counter_axis": o.get("반대축"),
        "market_view": o.get("시장_판단"),
        "swap_agree": o.get("swap_agree"),
        "structure_candidates": json.dumps(o.get("구조_후보") or [],
                                           ensure_ascii=False),
        "analyze_model": model,
        "gate_vs_llm": gate_vs_llm(gate_label, o.get("시장_판단")),
        "analyze_failed": bool(failed),
    }


# ═══════════════ [U12 2026-09-15] L2 · 금지어
#
# 🔴 L1 은 **숫자·이름**이 자료에 있는지 본다(이미 있다). L2 는 **승자·확신이
#    코드 값과 글자 그대로 같은지** 본다. 둘은 다른 것을 잡는다 —
#    L1 을 통과해도 서술이 다른 팀을 고를 수 있다(7432 사건).

#: 🔴 카드에 나오면 안 되는 말. 확정·보장·단정은 우리가 낼 수 없는 말이다.
#   ⚠️ 목록을 늘릴 때는 **오탐**을 재라 — 정상 문장을 반려하면 카드가 0장이 된다.
BANNED = ("확실", "무조건", "보장", "100%", "절대", "필승", "몰빵",
          "올인", "따논", "쉬운 돈")


def l2(out: dict | None, *, code_winner: str | None,
       code_level: str | None) -> tuple:
    """L2 — 서술의 승자·확신이 **코드 값과 같은가.** `(통과, 사유)`.

    🔴 P0-1 에서 고친 것이 여기서 다시 샐 수 있다. 서술이 코드와 다른 팀을
       말하면 카드가 자기 모순이다 — 반려한다.
    """
    o = out or {}
    w = str(o.get("승자") or "").strip()
    lv = str(o.get("확신") or "").strip()
    if code_winner and w and w != str(code_winner).strip():
        return False, f"서술 승자 {w!r} 가 코드 승자 {code_winner!r} 와 다르다"
    if code_level and lv and lv != str(code_level).strip():
        return False, f"서술 확신 {lv!r} 가 코드 확신 {code_level!r} 와 다르다"
    return True, ""


def banned_words(text: str | None) -> list:
    """금지어. 하나라도 있으면 반려한다."""
    t = str(text or "")
    return [w for w in BANNED if w in t]


# ═══════════════ [U12 2026-09-15] 3단 배선 — 추출 → 스왑 → 서술
#
# 🔴 이 모듈은 두 달 전에 만들어졌는데 **호출부가 0건**이었다(실측: app/ 전체
#    grep 결과 테스트 하나뿐). 그래서 결정축·시장 판단·구조 후보가 전부
#    NULL 이었다. 여기가 그 배선이다.
#
# 🔴 **발송을 켜지 않는다.** 결과를 원장에만 남긴다 — 경로 전환은 U14 다.
# 🔴 **게이트 대상에만** 돌린다. 전 경기에 돌리면 무료 한도가 즉시 터진다
#    (CHN-1 실측: groq 8,000 TPM · 판정 1콜이 그 한도를 넘는다).

#: L1 반려가 이 횟수를 넘으면 ② 없이 ③ 으로 간다(기존 상수 재사용).
SWAP_TRIES = 2


async def run(jg: dict, blk: dict, *, gate_label: str | None,
              code_winner: str | None = None, code_level: str | None = None,
              role: str | None = None) -> dict:
    """게이트 대상 한 경기 → 분석 JSON + 검사 결과.

    반환 `{out, swap_agree, l1, l2, banned, ledger, skipped}`.

    ⚠️ 실패는 결측이다 — 예외를 올리지 않는다. 판정이 이미 서 있고 이건 서술이다.
    """
    from app.config import get_settings
    from app.engine import gate as G
    from app.engine.team_form import complete_json, parse_json_object
    from app.llm.judge_route import PRELIM_ROLE

    out = {"out": None, "swap_agree": None, "l1": None, "l2": None,
           "banned": [], "ledger": None, "skipped": None}
    if gate_label not in (G.OVER, G.DOUBT):
        out["skipped"] = f"게이트가 {gate_label!r} — 분석 대상이 아니다"
        return out

    s = get_settings()
    # 🔴 [ANL-2] **출력 지시를 붙여서 묻는다.** 종전에는 자료 블록만 줬고,
    #    그래서 실측 6/6 이 마크다운 산문으로 왔다(1033자). JSON 을 내라고
    #    말한 적 없이 JSON 이 아니라고 버리고 있었다.
    prompt = build_input(blk, with_schema=True)
    try:
        text = await complete_json(prompt, model=s.matchup_model,
                                   max_tokens=int(s.matchup_max_tokens),
                                   role=role or PRELIM_ROLE, mock=False)
    except Exception as exc:
        logger.warning("[analyze] 호출 실패 %s: %s", jg.get("game_id"), exc)
        out["skipped"] = f"호출 실패: {type(exc).__name__}"
        out["ledger"] = to_ledger(None, model=None, gate_label=gate_label,
                                  failed=True)
        return out

    parsed = parse_json_object(text or "")
    if not isinstance(parsed, dict):
        out["skipped"] = "JSON 이 아니다"
        out["ledger"] = to_ledger(None, model=s.matchup_model,
                                  gate_label=gate_label, failed=True)
        return out

    ok1, why1 = l1(parsed, blk)
    ok2, why2 = l2(parsed, code_winner=code_winner, code_level=code_level)
    bad = banned_words(parsed.get("서술"))
    out.update({"out": parsed, "l1": (ok1, why1), "l2": (ok2, why2),
                "banned": bad})
    led = to_ledger(parsed, model=s.matchup_model, gate_label=gate_label)

    # 🔴 `main_axis` 는 **U8 코드 값이 정본**이다. 다르면 기록만 하고 코드를 쓴다.
    code_axes = (jg.get("axes") or {}).get("main_axis")
    if code_axes and led.get("main_axis") and led["main_axis"] not in code_axes:
        led["axis_disagree"] = f"코드 {code_axes} vs 분석 {led['main_axis']!r}"
        logger.info("[analyze] game=%s 결정축 불일치 — 코드 값을 쓴다: %s",
                    jg.get("game_id"), led["axis_disagree"])
        led["main_axis"] = code_axes[0]
    out["ledger"] = led
    logger.info("[analyze] game=%s L1=%s L2=%s 금지어=%s",
                jg.get("game_id"), ok1, ok2, bad or "없음")
    return out
