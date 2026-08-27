"""[§9 2단] 해석봇 — 사실을 ▲▼로 바꾼다. **한 팀의 한 칸씩만 본다.**

이 모듈의 존재 이유는 **정보 차단벽**이다.
  한 번에 시키면 LLM은 먼저 결론을 세우고 칸을 거기 맞춘다. λ가 한쪽으로
  기울자 모든 서술이 그쪽으로 정렬됐던 실패가 그것이다. 프롬프트로는 못 막는다.
  → 2단은 **상대가 누군지 모른다.** 승패를 모르니 편들 수가 없다.

⚠️ **사실 칸에 쓰지 못한다.** 입력은 `facts` 문자열 목록뿐이고, 출력은
   기호와 사유뿐이다. 이 모듈 어디에도 사실을 수정하는 경로가 없다.

⚠️ **인용 강제.** 사유에 그 칸 사실의 숫자나 이름이 하나도 없으면 그 칸을
   버린다("컨디션이 좋아 보인다"는 통과하지 못한다). 근거 없는 부호는
   3단에서 사실처럼 읽히므로, 여기서 걸러야 한다.

⚠️ **배칭.** 같은 팀의 다섯 칸을 한 콜로 묶는다(150콜 → 30콜). 칸마다 부르면
   비용이 5배가 되고, 프롬프트가 짧아지는 이점도 없다.
"""

import json
import logging
import re

from app.config import get_settings
from app.engine.card import CELLS
from app.llm import complete, role_enabled

logger = logging.getLogger(__name__)

ROLE = "interpreter"
SYMBOLS = ("▲", "▼", "=")

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "cells": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string",
                            "description": "칸 키 (bullpen/starter/batting/recent3/weight)"},
                    "symbol": {"type": "string", "enum": list(SYMBOLS),
                               "description": "▲ 유리 · ▼ 불리 · = 특이사항 없음"},
                    "reason": {"type": "string",
                               "description": "한 줄. **그 칸 사실의 숫자나 이름을 반드시 인용**한다"},
                },
                "required": ["key", "symbol", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["cells"],
    "additionalProperties": False,
}

SYSTEM = """너는 야구 분석가다. **한 팀의 상태만** 본다.

[네가 모르는 것]
- 상대가 누구인지 모른다. 상대 정보는 주어지지 않는다.
- 승패 확률·배당·예측을 모른다. 그런 것을 만들어내지 마라.
- 그러므로 "이 팀이 이긴다/진다"를 판단하지 마라. 그건 다음 단계의 일이다.

[네가 하는 일]
각 칸의 **사실만 보고** 그 팀의 상태가 평소보다 좋은지 나쁜지를 표시한다.
- ▲ 평소보다 유리한 상태
- ▼ 평소보다 불리한 상태
- = 특이사항 없음 (판단 근거가 약하면 주저 없이 =를 쓴다)

[반드시 지킬 것]
1. **사유에 그 칸 사실의 숫자나 선수 이름을 인용하라.** 인용이 없으면 그 칸은
   버려진다. "컨디션이 좋다" 같은 문장은 근거가 아니다.
2. 주어진 사실에 없는 수치를 만들어내지 마라.
3. 사실이 애매하면 =를 써라. 억지로 부호를 만드는 것이 가장 나쁘다.
4. 한국어로, 한 줄로 쓴다.

[칸별 방향 — 이 지표가 커지면 어느 쪽인가]
- 불펜 가용: **투입 인원·상대 타자 수·연투 인원이 많을수록 ▼** (많이 던졌다 = 소모가 크다)
- 선발 상태: **ERA·WHIP가 낮을수록 ▲**, **평균 이닝이 길수록 ▲**
- 타선: **팀 OPS가 높을수록 ▲**
- 최근 3경기: **득점이 많고 실점이 적을수록 ▲**
- 무게: **순위 경쟁 중일수록 ▲** (선두·5위와 가까울수록). 단 양쪽이 모두
  경쟁권 밖이면 순위 차이가 동기 차이가 아니므로 =다.

⚠️ 방향을 반대로 읽는 것이 가장 흔한 실수다. "구원 37타자를 상대했다"는
   **많이 던졌다 = ▼**이지 "적게 던졌다"가 아니다.

[해석의 예]
- "직전 경기 투수 9명 투입 · 구원 6.33이닝 37타자" → ▼
  "직전 경기에 투수 9명·구원 37타자를 썼다 — 오늘 뒷문이 얇다"
- "2경기 연속 등판 없음" → ▲  "연투 투수가 없어 불펜이 온전하다"
- "최근 3경기 LLL · 5득점 25실점" → ▼  "3경기 5득점 25실점으로 타선이 식었다"

⚠️ 같은 사실도 맥락에 따라 부호가 다르다. "5선발을 당겨썼다"는 로테이션
   붕괴일 수도, 이 경기를 잡겠다는 의지일 수도 있다. 확신이 없으면 =를 써라."""


def build_payload(card_side: dict, team_kr: str) -> dict:
    """[차단벽] LLM에 넘길 입력. **그 팀의 사실만** 담는다.

    ⚠️ 상대 팀·확률·배당·경기 결과는 **한 조각도** 들어가지 않는다.
       이 함수가 차단벽의 실체이며, 테스트가 이것을 직접 검사한다.
    """
    return {
        "team": team_kr,
        "cells": [{"key": key, "label": label,
                   "facts": list((card_side.get(key) or {}).get("facts") or [])}
                  for key, label in CELLS
                  if (card_side.get(key) or {}).get("facts")],
    }


_TOKEN = re.compile(r"\d+(?:\.\d+)?|[가-힣]{2,}|[A-Za-z]{2,}")
# 인용으로 인정하지 않는 흔한 말 — 이것만 겹치는 것은 인용이 아니다.
_STOP = {"경기", "최근", "직전", "투수", "이닝", "타자", "상대", "연속", "등판",
         "없음", "시즌", "평균", "구원", "선발", "득점", "실점", "회당", "잔여",
         "위와", "선두", "게임차", "구종", "투입", "명이", "우완", "좌완"}


def cites_facts(reason: str, facts: list[str]) -> bool:
    """사유가 그 칸 사실을 실제로 인용했는가.

    숫자 하나만 겹쳐도 인용으로 본다 — 숫자는 그 칸 고유값이라 우연히 겹치기
    어렵다. 반면 '경기'·'투수' 같은 흔한 말은 인용이 아니다.
    """
    if not reason or not facts:
        return False
    have = {t for f in facts for t in _TOKEN.findall(f)} - _STOP
    used = {t for t in _TOKEN.findall(reason)} - _STOP
    return bool(have & used)


def direction_check(key: str, metrics: dict, baselines: dict,
                    symbol: str) -> str | None:
    """[§9-2단] 수치가 가리키는 방향과 LLM 판정이 **반대인가**. 반대면 사유.

    실사고(2026-08-27): KIA 불펜 사실이 "직전 9명 투입·구원 37타자·연투 3명"
    (= 명백한 과소모)인데 모델이 "사용량이 적어 유리" **▲**로 읽었다.
    숫자는 인용했으므로 인용 강제를 통과했다 — **인용 강제는 지어내기를 막지,
    그 숫자를 어떻게 읽는지는 못 막는다.**

    ⚠️ `=`는 오독으로 치지 않는다. 판단 보류이지 반대가 아니다.
    ⚠️ 기준선이 없거나 지표가 없으면 **검증하지 않는다** — 못 재는 것을
       틀렸다고 하면 정상 판정을 버린다.
    """
    from app.engine.card import CELL_METRICS

    if symbol not in ("▲", "▼"):
        return None
    votes = []
    detail = []
    for name, higher_is_better in CELL_METRICS.get(key, ()):
        val, band = metrics.get(name), baselines.get(name)
        if val is None or not isinstance(band, dict):
            continue
        q1, q3 = band.get("q1"), band.get("q3")
        if q1 is None or q3 is None:
            continue
        # ⚠️ **사분위 안은 "평소"다.** 중앙값보다 조금 크다고 불리로 세면
        #    0.004 차이도 오독으로 잡혀 정상 판정을 버린다(실측 2026-08-27).
        if q1 <= val <= q3:
            continue
        high = val > q3
        favorable = high == higher_is_better
        votes.append(favorable)
        detail.append(f"{name} {val:g}({'상위' if high else '하위'} "
                      f"사분위 {q1:g}~{q3:g})")
    if not votes:
        return None
    # 지표가 **한 방향으로 일치**할 때만 판정한다. 갈리면 사람도 애매한 칸이다.
    if all(votes) and symbol == "▼":
        return f"수치는 유리를 가리킨다 — {' · '.join(detail)}"
    if not any(votes) and symbol == "▲":
        return f"수치는 불리를 가리킨다 — {' · '.join(detail)}"
    return None


async def interpret_side(card_side: dict, team_kr: str, settings=None,
                         baselines: dict | None = None) -> dict:
    """한 팀의 다섯 칸 → {칸키: {"symbol", "reason"}}. **한 콜.**

    인용이 없는 칸은 **버린다** — 반환에 들어가지 않으므로 3단은 그 칸을
    "해석 없음"으로 본다.
    """
    s = settings or get_settings()
    payload = build_payload(card_side, team_kr)
    if not payload["cells"]:
        return {}
    if not role_enabled(ROLE, s):
        logger.info("[2단] 해석봇 비활성 — 부호 없이 사실만 나간다")
        return {}
    res = await complete(
        ROLE, [{"role": "user",
                "content": json.dumps(payload, ensure_ascii=False)}],
        system=SYSTEM, schema=VERDICT_SCHEMA, max_tokens=1500, settings=s)
    out: dict = {}
    # 폐기 사유를 **구분해서** 센다 — 지어내기와 오독은 다른 문제이고
    # 대응도 다르다(전자는 인용 강제, 후자는 방향 규칙·채점).
    dropped: dict[str, list[str]] = {"인용 없음": [], "방향 오독": []}
    facts_of = {c["key"]: c["facts"] for c in payload["cells"]}
    base = baselines or {}
    for row in (res.data or {}).get("cells") or []:
        key, sym, why = row.get("key"), row.get("symbol"), (row.get("reason") or "").strip()
        if key not in facts_of or sym not in SYMBOLS:
            continue
        if not cites_facts(why, facts_of[key]):
            dropped["인용 없음"].append(key)
            continue
        metrics = (card_side.get(key) or {}).get("metrics") or {}
        wrong = direction_check(key, metrics, base, sym)
        if wrong:
            dropped["방향 오독"].append(key)
            logger.warning("[2단] %s/%s 방향 오독 — 판정 %s · %s | 사유: %s",
                           team_kr, key, sym, wrong, why[:70])
            continue
        out[key] = {"symbol": sym, "reason": why, "provider": res.label}
    for why_dropped, keys in dropped.items():
        if keys:
            logger.info("[2단] %s — %s 폐기: %s", team_kr, why_dropped, ", ".join(keys))
    return out


async def interpret_slate(pairs: list, settings=None, pool=None) -> dict:
    """슬레이트 전체를 한 번에 해석한다. `pairs`는 [(jg, research), ...].

    **왜 슬레이트 단위인가.** 방향 검증의 기준선(리그 사분위)은 그날 슬레이트의
    전 팀 지표에서 나온다. 경기 하나만 보고는 "평소보다 많이 던졌다"를 말할 수
    없다 — 비교 대상이 없기 때문이다.

    돌려주는 값: {game_id: {"home": {...}, "away": {...}}}
    아울러 pool이 있으면 판정을 `cell_verdicts`에 적재한다(#63).
    """
    from app.engine.card import build_card, league_baselines
    from app.engine.cell_grade import record_verdicts

    baselines = league_baselines([(res, side) for _, res in pairs
                                  for side in ("home", "away")])
    out: dict = {}
    for jg, res in pairs:
        card = build_card(jg, res)
        per_game: dict = {}
        for side in ("home", "away"):
            try:
                v = await interpret_side(card[side], jg.get(f"{side}_kr")
                                         or jg.get(side), settings=settings,
                                         baselines=baselines)
            except Exception as exc:      # 한 팀이 죽어도 슬레이트는 계속 간다
                logger.warning("[2단] %s 판정 실패: %s", jg.get(side), exc)
                v = {}
            per_game[side] = v
            gid = jg.get("db_id") or jg.get("game_id")
            if pool and v and gid:
                try:
                    await record_verdicts(pool, gid, side,
                                          jg.get(f"{side}_kr") or jg.get(side),
                                          v, card[side])
                except Exception as exc:
                    logger.warning("[2단] 칸 판정 기록 실패 %s/%s: %s",
                                   gid, side, exc)
        out[jg.get("game_id")] = per_game
    return out

# ---------------------------------------------------------------- 카드 대조 규칙


def out_of_contention(standing: dict, settings=None) -> bool:
    """순위 경쟁권 밖인가 — **선두와도 컷과도** 멀어졌을 때만.

    ⚠️ 선두 게임차만 보면 안 된다. 선두와 16게임 차여도 5위와 1게임 차면
       그 팀은 명백히 경쟁 중이다(실측 2026-08-27: 한화 선두차 16.5 · 컷차 9.0).
    """
    s = settings or get_settings()
    gb, gc = (standing or {}).get("games_behind"), (standing or {}).get("games_behind_cut")
    if gb is None or gc is None:
        return False          # 모르면 경쟁권 밖이라고 단정하지 않는다
    return gb >= s.contention_gb and gc >= s.contention_gb


def apply_weight_rule(home: dict, away: dict, research: dict, settings=None) -> str | None:
    """[카드 ④칸] **양쪽 무의미** 규칙. 적용했으면 사유를, 아니면 None.

    두 팀이 모두 경쟁권 밖이면 **순위 차이가 동기 차이를 뜻하지 않는다.**
    그런데도 순위가 높은 쪽에 ▲를 주면 **없는 동기 차이를 만들어내는 것**이다.
    → 양쪽 모두 "="로 되돌린다.

    ⚠️ 이것은 **결정적 규칙**이지 해석이 아니다. LLM이 문턱을 판단하게 두면
       측정되지 않은 튜닝이 된다. 문턱은 config(`contention_gb`)이며 아직
       실측되지 않았다 — 채점 데이터가 쌓이면 교체한다.
    """
    s = settings or get_settings()
    hs = research.get("home_standing") or {}
    as_ = research.get("away_standing") or {}
    if not (out_of_contention(hs, s) and out_of_contention(as_, s)):
        return None
    note = (f"양쪽 모두 순위 경쟁권 밖 "
            f"(선두차 {hs.get('games_behind')}·{as_.get('games_behind')}G, "
            f"{s.contention_cut_rank}위차 {hs.get('games_behind_cut')}·"
            f"{as_.get('games_behind_cut')}G) — 순위 차이가 동기 차이가 아니다")
    for side in (home, away):
        side["weight"] = {"symbol": "=", "reason": note, "rule": "양쪽 무의미"}
    return note
