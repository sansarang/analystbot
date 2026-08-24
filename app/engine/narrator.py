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

import anthropic

from app.collectors.base import ApiQuotaError, is_quota_error
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
                    "required": ["game_id", "causal", "decider"],
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
        self._client: anthropic.AsyncAnthropic | None = None

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        return self._client

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
        try:
            resp = await self.client.messages.create(
                model=self.settings.report_model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM,
                tools=[NARRATIVE_TOOL],
                tool_choice={"type": "tool", "name": "narrative"},
                messages=[{"role": "user",
                           "content": json.dumps(payload, ensure_ascii=False, default=str)}],
            )
        except anthropic.APIStatusError as exc:
            if is_quota_error(exc.status_code, str(exc)):
                raise ApiQuotaError("anthropic(narrator)", str(exc)) from exc
            raise
        for block in resp.content:
            if block.type == "tool_use" and block.name == "narrative":
                return _normalize(block.input)
        raise RuntimeError("narrator did not return a narrative tool call")


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
