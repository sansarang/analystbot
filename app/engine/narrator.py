"""[B] 서술 단계 — 판정 결과를 '분석 글'로 바꾼다.

판정(judge)은 숫자와 결론을 낸다. 그 JSON을 그대로 문장화하면
"시장 55%. 모델 53.5%. 전문가 3명."처럼 **필드 나열**이 된다.
이 모듈은 판정 결과 + 리서치 원본을 받아 사람이 읽는 글을 쓰는 별도 단계다.

서술이 반드시 담아야 할 3요소:
  ① 맥락 — 순위·연승연패·이적·데뷔전·시리즈 상황 등 이 경기를 특별하게 만드는 배경
  ② 인과 — 숫자를 사건으로 연결 ("ERA 5.06" X → "ERA 5.06에 이닝도 못 먹어 불펜이 일찍 돈다" O)
  ③ 승부처 — 이 경기가 어디서 갈리는지 한 문장

실패하거나 목 모드면 서술 없이 결정적 렌더로 폴백한다 (키 부재로 크래시 금지).
"""

import json
import logging
import re


from app.config import get_settings

logger = logging.getLogger(__name__)

NARRATE_BATCH = 5          # 한 호출당 경기 수 (판정과 같은 이유 — 토큰 여유 확보)
MAX_TOKENS = 8000

NARRATIVE_TOOL = {
    "name": "narrative",
    "description": "경기별 한국어 서술 3요소를 제출한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "games": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "game_id": {"type": "integer"},
                        "context": {
                            "type": "string",
                            "description": "① 맥락 — 순위·연승연패·이적·데뷔전·시리즈 상황 등 "
                                           "이 경기를 특별하게 만드는 배경 한 문장. "
                                           "리서치에 재료가 없으면 빈 문자열.",
                        },
                        "causal": {
                            "type": "string",
                            "description": "② 인과 — 핵심 수치를 '그래서 무슨 일이 벌어지는가'까지 "
                                           "연결한 1~2문장. 수치 나열 금지.",
                        },
                        "decider": {
                            "type": "string",
                            "description": "③ 승부처 — 이 경기가 어디서 갈리는지 한 문장.",
                        },
                        "adjustment_case": {
                            "type": "string",
                            "description": "⑤ 승률 조정 근거 — win_prob_adjustment에서 가장 크게 "
                                           "움직인 항목을 사건으로 설명한 한 문장. "
                                           "예: '핵심 불펜 3명이 이탈해 기본 승률에서 6%p를 깎았다.' "
                                           "조정이 없었으면 빈 문자열.",
                        },
                        "market_case": {
                            "type": "string",
                            "description": "④ 추천 마켓 — 마켓 보드에서 등급이 가장 높은 마켓을 "
                                           "왜 그 마켓으로 보는지 인과로 설명한 한 문장. "
                                           "예: '두 선발 모두 QS 기대치가 낮아 난타전 가능성이 "
                                           "커서 오버 9.0에 무게가 실린다.' 승인 마켓이 없으면 "
                                           "왜 전 마켓이 기준 미달인지 한 문장.",
                        },
                        "expert_note": {
                            "type": "string",
                            "description": "전문가 픽 요약 1줄(한국어, 핵심 수치만). 없으면 빈 문자열.",
                        },
                        "missing": {
                            "type": "string",
                            "description": "재료가 부족해 짧게 썼다면 '무엇이 없어서 짧은지'. "
                                           "충분하면 빈 문자열.",
                        },
                    },
                    "required": ["game_id", "causal", "decider", "market_case"],
                },
            }
        },
        "required": ["games"],
    },
}

GOOD_EXAMPLE = (
    "피츠버그 @ 다저스 — 트레이드 마감일에 디트로이트에서 이적한 스쿠발의 홈 등판이다. "
    "113.2이닝 135탈삼진에 볼넷이 20개뿐(WHIP 0.96)이라 승수(7승 7패)만 빼면 리그 최정상급이다. "
    "다저스는 4연승에 팀 득점 2위로 공수가 모두 돌아가는 중. 피츠버그도 팀 득점 3위로 타선은 "
    "좋지만 선발 존스가 ERA 4.78로 기복이 있어, 존스가 초반 다저스 상위 타선을 버텨내느냐가 승부처다."
)

BAD_EXAMPLE = (
    "시장: 홈 55%. 모델: 53.5%. 전문가: [PickDawgz] David Racey: totals:Over:8.5. "
    "조심할 점: 부상·라인업 변수는 킥오프 직전에 바뀔 수 있습니다."
)

SYSTEM = f"""너는 스포츠 분석 리포트의 **서술** 담당이다. 판정(결론·확률)은 이미 끝났다.
네 일은 그 결론과 리서치 재료를 사람이 읽는 한국어 분석 글로 쓰는 것이다.

[좋은 예시 — 이 수준을 목표로 하라]
{GOOD_EXAMPLE}

[나쁜 예시 — 절대 이렇게 쓰지 마라]
{BAD_EXAMPLE}
나쁜 이유: 필드를 나열했을 뿐 아무 사건도 설명하지 않는다. 전문가 픽을 원문 그대로 붙였다.
"부상·라인업 변수는 바뀔 수 있습니다"는 어느 경기에나 해당하는 빈말이다.

규칙:
1. 모든 수치는 "그래서 무슨 일이 벌어지는가"까지 써라. "ERA 5.06"만 쓰지 말고
   "ERA 5.06에 최근엔 이닝도 못 먹어 불펜이 일찍 가동된다"처럼 사건으로 연결하라.
2. 맥락(순위·연승연패·이적·데뷔전·시리즈 상황)이 리서치에 있으면 반드시 써라. 없으면 비워라.
3. 승부처는 "누가 무엇을 해내느냐"의 형태로 한 문장.
4. 전문가 픽은 원문 복붙 금지 — 한국어 1~2줄로 압축하고 핵심 수치만 남겨라.
5. 각주 마커([1][3][6] 등)를 절대 쓰지 마라.
6. "시장 55%. 모델 53.5%." 같은 확률 나열을 쓰지 마라 (그 숫자는 다른 칸에서 이미 보여준다).
7. 범용 문구("부상 변수는 바뀔 수 있다", "변수가 많은 경기다") 금지. 그 경기 고유의
   숫자나 선수 이름이 없는 문장은 아예 쓰지 마라.
8. 재료가 부족하면 길이를 채우지 말고 짧게 쓰되, missing에 무엇이 없는지 밝혀라.
9. 사실을 지어내지 마라. 입력에 없는 이적·부상·기록을 만들어내면 안 된다.

10-0. **홈/원정을 헷갈리지 마라.** win_prob_adjustment의 확률은 **전부 홈팀 기준**이다.
    추천 마켓이 원정팀이면 그 팀의 승률은 (100% − 홈 승률)이다. win_prob_home /
    win_prob_away에 양쪽 값이 이미 계산돼 있으니 **그 값을 그대로 인용**하고,
    "홈팀 기준 수치이며 실제로는…" 같은 변명 문장을 쓰지 마라. 조정 항목의 부호도
    홈팀 기준이므로, 원정팀을 말할 때는 방향을 뒤집어 서술하라.
10. **승률 조정 근거를 반드시 인용하라.** 입력의 win_prob_adjustment는 기준 승률에서
    무엇이 몇 %p를 움직였는지를 담은 계산 과정이다. 그중 가장 크게 움직인 항목을
    서술에 그대로 녹여라. 예: "파드리스는 핵심 불펜 3명이 이탈해 기본 승률에서 6%p를
    깎았다. 그럼에도 54%로 앞서는 건 레이의 최근 5경기 ERA 2.80이 애쉬크래프트(4.10)를
    크게 앞서기 때문이다."
11. **배당·시장 확률을 서술에 쓰지 마라.** 승률과 경기력 근거로만 말한다.
    (배당은 다른 칸에서 "1만 원당 얼마"로 이미 보여준다)
12. **최고 등급 마켓의 근거를 서술에 반드시 녹여라.** market_board에서 등급이 가장 높은
    마켓(🟢 > 🟡 > 🔴)이 왜 그 자리인지 인과로 설명하라 — 배당·EV 숫자를 반복하지 말고
    "왜 그 마켓인가"를 써라. 예: "두 선발 모두 QS 기대치가 낮아 난타전 가능성이 크고,
    이 때문에 오버 9.0에 무게가 실린다."

서술은 **맥락 → 인과 → 승부처 → 추천 마켓** 순서로 읽히게 쓰고, 전체 4~6줄 분량으로 맞춰라.

반드시 narrative 도구를 정확히 한 번 호출해 제출하라."""

_FOOTNOTE_RE = re.compile(r"\[\d+\](?:\[\d+\])*")
_ENUM_RE = re.compile(r"(시장|모델|판정)\s*[:：]\s*\d|\bp_(final|model|claude)\b")

# 어느 경기에나 해당하는 빈말 — 그 경기 고유 정보가 없는 문장은 줄째로 버린다
_BANNED = (
    "부상·라인업 변수", "변수가 많은 경기", "지켜봐야 한다", "예측하기 어렵다",
    "흥미로운 승부", "치열한 승부", "관심이 집중", "기대를 모은다", "팬들의 관심",
    "결과를 예단하기", "중요한 경기다", "쉽지 않은 경기",
)
# 수치가 없다면 최소한 이만큼은 구체적 서술이어야 한다.
# 승부처 문장("존스가 초반을 버티느냐가 승부처다")은 짧으므로 문턱을 낮게 잡는다.
_MIN_TOKENS = 4
_TOKEN_RE = re.compile(r"[가-힣A-Za-z][가-힣A-Za-z0-9.]*")


def clean_line(text) -> str:
    """서술 1줄 정제 — 각주 제거, 필드 나열·범용 문구 차단."""
    s = _FOOTNOTE_RE.sub("", str(text or "")).strip()
    s = re.sub(r"\s{2,}", " ", s)
    if not s:
        return ""
    if _ENUM_RE.search(s):
        logger.warning("[narrator] 필드 나열 문장 차단: %s", s[:60])
        return ""
    if any(b in s for b in _BANNED):
        logger.warning("[narrator] 범용 문구 차단: %s", s[:60])
        return ""
    # 수치도 없고 서술도 짧으면 내용이 없는 빈말이다 ("중요한 경기다.")
    if not re.search(r"\d", s) and len(_TOKEN_RE.findall(s)) < _MIN_TOKENS:
        logger.warning("[narrator] 내용 없는 짧은 문장 차단: %s", s[:60])
        return ""
    return s


def _payload_game(jg: dict, research: dict) -> dict:
    """서술 입력 — 판정 결론 + 리서치 원본(재료). 확률 나열은 최소화한다."""
    board = [
        {"desc": c["desc"], "odds": c["odds"], "ev": c["ev"],
         "grade": c.get("grade"), "note": c.get("grade_note")}
        for c in (jg.get("market_board") or [])[:6]
    ]
    return {
        "game_id": jg["game_id"],
        "matchup": f"{jg['away']} @ {jg['home']}",
        # [5] 승률이 어떻게 조정됐는지 — 서술이 이 근거를 반드시 인용해야 한다.
        #     확률은 **홈팀 기준**이므로 추천 팀과 방향이 다를 수 있다 → 명시해서 넘긴다.
        "win_prob_adjustment": (jg.get("prob_adjust") or {}).get("trace"),
        "win_prob_basis": "위 확률은 모두 홈팀 기준이다. 원정팀 승률은 (100% - 홈 승률)이다.",
        "win_prob_home": (jg.get("prob_adjust") or {}).get("p_home"),
        "win_prob_away": (jg.get("prob_adjust") or {}).get("p_away"),
        "recommended_side": ((jg.get("pick_summary") or {}).get("desc")),
        "unused_material": (jg.get("prob_adjust") or {}).get("unused"),
        "lineup_status": jg.get("lineup_status"),
        "league": jg.get("league"),
        "starts_at_kst": jg.get("starts_at_kst"),
        "verdict": jg.get("verdict"),
        "reversal_factor": jg.get("reversal_factor"),
        "judge_confidence": jg.get("judge_confidence"),
        "market_board": board,
        "stats": jg.get("stats"),
        "research": research,
        "expert_picks": [
            {"expert": ep.get("expert"), "site": ep.get("site"), "pick": ep.get("pick"),
             "reasoning": ep.get("reasoning"), "record": ep.get("record")}
            for ep in (jg.get("expert_picks") or [])[:4]
        ],
    }


class Narrator:
    def __init__(self, mock: bool | None = None):
        self.settings = get_settings()
        self.mock = self.settings.mock_judge if mock is None else mock
        # [B-4] 실제로 응답한 provider. 폴백이 조용히 일어나면 문체·품질이
        #       바뀐 것을 아무도 모른다 — 리포트까지 따라가야 한다.
        self.last_provider: str = ""

    async def narrate(self, games: list[dict], sport: str) -> dict[int, dict]:
        """[{jg}] → {game_id: {context, causal, decider, expert_note, missing}}.

        실패하면 빈 dict를 돌려 결정적 렌더로 폴백한다 (분석을 막지 않는다).
        """
        from app.research.validate import sanitize_research

        targets = [g for g in games if g.get("status") == "scheduled"]
        if self.mock or not targets:
            return {}
        out: dict[int, dict] = {}
        for i in range(0, len(targets), NARRATE_BATCH):
            batch = targets[i:i + NARRATE_BATCH]
            payload = {
                "sport": "MLB 야구" if sport == "mlb" else "축구",
                "games": [
                    _payload_game(g, sanitize_research(g.get("research") or {}, sport)[0])
                    for g in batch
                ],
            }
            try:
                out.update(await self._call(payload))
            except Exception as exc:
                logger.warning("[narrator] 서술 실패(폴백 렌더 사용) %d~%d: %s",
                               i + 1, i + len(batch), exc)
        logger.info("[narrator] 서술 %d/%d경기", len(out), len(targets))
        return out

    async def _call(self, payload: dict) -> dict[int, dict]:
        """[B-1] provider 계층을 거친다 — `.env`의 `NARRATOR_PROVIDER`로 갈아끼운다.

        ⚠️ 어느 provider가 서술했는지 `self.last_provider`에 남긴다.
           폴백이 조용히 일어나면 문체·품질이 바뀐 것을 아무도 모른다.
        """
        from app.llm import complete

        res = await complete(
            "narrator",
            [{"role": "user",
              "content": json.dumps(payload, ensure_ascii=False, default=str)}],
            system=SYSTEM, schema=NARRATIVE_TOOL["input_schema"],
            max_tokens=MAX_TOKENS, settings=self.settings)
        self.last_provider = res.label
        if res.data is None:
            raise RuntimeError("narrator did not return a narrative payload")
        return _normalize(res.data)


def _normalize(raw: dict) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for g in (raw or {}).get("games") or []:
        try:
            gid = int(g["game_id"])
        except (KeyError, TypeError, ValueError):
            continue
        out[gid] = {
            "context": clean_line(g.get("context")),
            "causal": clean_line(g.get("causal")),
            "decider": clean_line(g.get("decider")),
            "adjustment_case": clean_line(g.get("adjustment_case")),
            "market_case": clean_line(g.get("market_case")),
            "expert_note": clean_line(g.get("expert_note")),
            "missing": clean_line(g.get("missing")),
        }
    return out


async def attach_narratives(games: list[dict], sport: str) -> int:
    """경기 객체에 서술을 부착. 반환: 서술이 붙은 경기 수."""
    narratives = await Narrator().narrate(games, sport)
    for g in games:
        n = narratives.get(g.get("game_id"))
        if n:
            g["narrative"] = n
    return len(narratives)
