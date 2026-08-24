"""Claude 판정(judge) — Anthropic SDK, JUDGE_MODEL + adaptive thinking, tool_use 구조화 출력.

- 모델: .env JUDGE_MODEL (기본 claude-opus-4-6). 모델이 없으면(404) 사용 가능한
  최상위 모델로 폴백한다 (models API 조회).
- 시스템 지시: 입력 JSON의 숫자만 사용, 새 수치 생성 금지. ①전문가 픽 수치가
  stats와 모순되면 제외+사유 ②시장/모델/전문가 충돌 시 판정+근거 ③경기별 p_claude.
- 구조화 출력: strict verdict 도구 호출을 요구. adaptive thinking과 강제
  tool_choice는 함께 쓸 수 없으므로 1차는 thinking+auto로 호출하고, 도구 호출이
  누락되면 thinking을 끄고 tool_choice로 강제해 1회 재시도한다.
- ANTHROPIC_API_KEY 없으면 결정적 목 판정으로 폴백.
"""

import json
import logging

import anthropic

from app.collectors.base import ApiQuotaError, is_quota_error
from app.config import get_settings

logger = logging.getLogger(__name__)

# 폴백 우선순위 (최상위 → 하위). judge_model이 404일 때 이 순서로 시도.
MODEL_LADDER = [
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
]

VERDICT_TOOL = {
    "name": "verdict",
    "description": "슬레이트 전체에 대한 최종 구조화 판정을 제출한다. 분석이 끝나면 정확히 한 번 호출할 것.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "games": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "game_id": {"type": "integer"},
                        "p_claude": {"type": "number", "description": "홈팀 승리 확률 0~1"},
                        "verdict": {"type": "string", "description": "3자 대조·승패/가치 분리 판단·저분산 대안·리스크 (근거 수치 포함)"},
                        "pass_recommended": {
                            "type": "boolean",
                            "description": "⑤에서 '패스 권장' 결론이면 true — 이 경기 픽은 추천 목록에서 제외된다",
                        },
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "판정 신뢰도. 데이터가 반반이거나 부실하면 low — low는 추천에서 제외된다",
                        },
                        "reversal_factor": {
                            "type": "string",
                            "description": "2차 반박 검증에서 발견된 실체적 반전 요인 (한국어, 근거 수치 포함). 없으면 빈 문자열",
                        },
                        "conclusion_revised": {
                            "type": "boolean",
                            "description": "반박 검증으로 1차 잠정 결론이 수정되었으면 true — 신호등이 한 단계 보수화된다",
                        },
                        "excluded_picks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "expert": {"type": "string"},
                                    "reason": {"type": "string"},
                                },
                                "required": ["expert", "reason"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["game_id", "p_claude", "verdict", "pass_recommended",
                                 "confidence", "reversal_factor", "conclusion_revised",
                                 "excluded_picks"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["games"],
        "additionalProperties": False,
    },
}

SYSTEM = """너는 20년 경력의 스포츠 베팅 수석 애널리스트다. 입력 JSON(경기·기록·배당·모델확률·전문가픽·속보)만을 근거로 심층 분석을 작성한다. 다음 원칙을 반드시 지켜라.

[데이터 규율]
1. 입력에 없는 수치를 만들어내지 마라. 없는 정보는 "미수집"으로 정직하게 표기한다.
2. 전문가 픽의 수치가 입력 stats와 모순되면 그 픽을 제외하고 사유를 남겨라.
3. 모든 주장에는 근거 수치를 병기하라. "우세"라고만 쓰는 것은 금지 — "원정 ERA 4.31 vs 홈 2.32라 우세"처럼 쓴다.

[분석 구조 — 경기당 이 순서로]
① 스토리라인 한 줄: 이 경기를 특별하게 만드는 맥락을 먼저 잡아라 (이적 후 첫 등판, 데뷔전, 연승/연패 충돌, 순위 경쟁, 개막전 등). 없으면 생략.
② 전력 비교: 양 팀 최근 폼·핵심 선수·홈원정 스플릿을 수치로. 야구는 선발투수 대결이 중심, 축구는 최근 5경기 득실과 상대전적이 중심.
③ 3자 대조: 시장(배당 암시확률) vs 모델 확률 vs 전문가 컨센서스를 나란히 놓고, 셋이 일치하는지 갈리는지를 명시하라. 갈리는 경기는 "왜 갈리는지"가 분석의 핵심이다 — 각 진영의 근거를 대조하라.
④ 전문가 인용: "[사이트] 이름(전적): 픽 — 근거" 형식의 한국어 1~2줄. 전적이 좋은 전문가(적중률 60%+ 또는 ROI 플러스)의 픽은 무게를 실어 다루고, 전적이 나쁜 전문가는 픽 자체보다 인용된 데이터만 취하라. 전적 미상이면 "(전적 미상)"으로 표기.
⑤ 판단: 반드시 두 가지를 분리해서 결론 내라 — (a) 누가 이길 것인가 (b) 배당 대비 가치가 있는가. "이길 확률은 높지만 배당 1.45라 가치는 없다" 같은 결론이 정상이며 자주 나와야 한다. EV가 +20%를 넘으면 가치가 아니라 데이터 오류를 의심하고 플래그를 세워라.
⑥ 저분산 대안: 승패 단식이 고분산이면 핸디캡(+1.5 런라인, 더블찬스)이나 토탈 중 근거가 있는 저분산 마켓을 하나 제시하라.
⑦ 리스크 한 줄: 이 판단이 틀린다면 무엇 때문일지를 스스로 명시하라 (표본 부족, 불펜 소모, 로테이션 피로, 신인 변동성 등).

[2단 판정 — 반박 의무 (전 경기)]
모든 경기에서 반드시 두 단계로 판단하라.
(1차) 입력 데이터로 잠정 결론을 세운다.
(2차) 그 결론을 "반박"하는 데이터를 research(최근 폼·선발 최근 성적·결장·불펜)에서 의도적으로 찾아라. 특히 form_reversal 플래그(시즌 평균-최근 폼 역전)는 반드시 검토한다. 반박이 실체적이면 결론을 수정하고 reversal_factor에 근거 수치와 함께 명시하며 conclusion_revised=true로 제출한다. 시즌 평균이 좋아도 최근 폼이 무너진 픽(예: 선발 시즌 ERA 3.86 vs 최근5 5.40)은 승패 추천을 접고 대안 마켓 또는 패스로 전환하는 것이 정상이다. 반박이 실체가 없으면 reversal_factor는 빈 문자열, conclusion_revised=false.

[전문가 전적 분리]
각 expert_picks 항목에 ledger(마켓별 전적: graded/hit_rate/roi)와 adopted 플래그가 있다. adopted=false(해당 마켓 전적 마이너스)인 픽은 "불채택 — 인용 데이터만 참고"로 처리하고 판단문에 그렇게 명시하라. 전적 미상 전문가는 0.5표 가중으로만 취급한다.

[문체]
- 한국어. 팀명은 한국어 표기 통일. 시각은 KST.
- 판단은 단정적이되 근거와 함께. 얼버무리지 마라. 단, 데이터가 반반이면 "저신뢰 경기, 패스 권장"이라고 정직하게 써라.

[출력 방식 — 구조화 제출]
위 원칙으로 분석을 마치면 반드시 verdict 도구를 정확히 한 번 호출해 제출한다:
- 경기별 p_claude: 홈팀 승리 확률(0~1).
- verdict: ③3자 대조 결론 + ⑤(a)승패/(b)가치 분리 판단 + ⑥저분산 대안 + ⑦리스크를 근거 수치와 함께 압축한 한국어 문장.
- 전문가 픽 수치가 stats와 모순되면 excluded_picks에 {expert, reason}으로 넣는다.
도구 호출 외 장문 출력은 불필요하다."""


class Judge:
    def __init__(self, mock: bool | None = None):
        self.settings = get_settings()
        self.mock = self.settings.mock_judge if mock is None else mock
        logger.info("[judge] mode: %s", "MOCK" if self.mock else "LIVE")
        self._client: anthropic.AsyncAnthropic | None = None
        self._model: str | None = None

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        return self._client

    async def _resolve_fallback_model(self) -> str:
        """JUDGE_MODEL이 404일 때 사용 가능한 최상위 모델로 폴백."""
        available = {m.id async for m in self.client.models.list()}
        for candidate in MODEL_LADDER:
            if candidate in available:
                logger.warning("[judge] falling back to model %s", candidate)
                return candidate
        return sorted(available)[0]

    async def _create(self, payload_json: str, *, force_tool: bool) -> anthropic.types.Message:
        kwargs: dict = {
            "model": self._model,
            "max_tokens": 16000,
            "system": SYSTEM,
            "tools": [VERDICT_TOOL],
            "messages": [{"role": "user", "content": payload_json}],
        }
        if force_tool:
            # 강제 tool_choice는 extended thinking과 병행 불가 → thinking 없이 강제
            kwargs["tool_choice"] = {"type": "tool", "name": "verdict"}
        else:
            kwargs["thinking"] = {"type": "adaptive"}
        return await self.client.messages.create(**kwargs)

    async def judge(self, payload: dict) -> dict:
        """payload → {"games": [{game_id, p_claude, verdict, excluded_picks}]}"""
        if self.mock:
            return self._mock_verdict(payload)

        if self._model is None:
            self._model = self.settings.judge_model
        payload_json = json.dumps(payload, ensure_ascii=False, default=str)

        try:
            try:
                response = await self._create(payload_json, force_tool=False)
            except anthropic.NotFoundError:
                self._model = await self._resolve_fallback_model()
                response = await self._create(payload_json, force_tool=False)
        except anthropic.APIStatusError as exc:
            if is_quota_error(exc.status_code, str(exc)):
                raise ApiQuotaError("anthropic(judge)", str(exc)) from exc
            raise

        verdict = self._extract_verdict(response)
        if verdict is None:
            logger.warning("[judge] no tool_use in response — retrying with forced tool_choice")
            response = await self._create(payload_json, force_tool=True)
            verdict = self._extract_verdict(response)
        if verdict is None:
            raise RuntimeError("judge did not return a verdict tool call")
        return verdict

    @staticmethod
    def _extract_verdict(response: anthropic.types.Message) -> dict | None:
        for block in response.content:
            if block.type == "tool_use" and block.name == "verdict":
                return block.input
        return None

    @staticmethod
    def _mock_verdict(payload: dict) -> dict:
        """결정적 목 판정: p_claude = (p_model + p_market) / 2.

        research.form_reversal 플래그가 있으면 2단 판정 규칙대로 결론을 보수 전환
        (승패 패스 + 대안 마켓) — 회귀 테스트의 결정적 재현 경로.
        """
        games = []
        for g in payload.get("games", []):
            p_model = float(g.get("p_model", 0.5))
            p_market = float(g.get("p_market") or 0.5)
            p = max(0.05, min(0.95, (p_model + p_market) / 2))
            reversal = (g.get("research") or {}).get("form_reversal") or []
            if reversal:
                games.append({
                    "game_id": g["game_id"], "p_claude": round(p, 4),
                    "verdict": (f"[mock] 반전 요인: {reversal[0]} — 잠정 '승 소액' 결론을 "
                                "철회, 승패 패스. 대안 마켓(더블찬스·토탈)만 검토"),
                    "pass_recommended": True, "confidence": "medium",
                    "reversal_factor": str(reversal[0]), "conclusion_revised": True,
                    "excluded_picks": [],
                })
                continue
            games.append({
                "game_id": g["game_id"],
                "p_claude": round(p, 4),
                "verdict": "[mock] 모델과 시장 확률의 평균을 채택 (목 모드 판정)",
                "pass_recommended": False,
                "confidence": "medium",
                "reversal_factor": "",
                "conclusion_revised": False,
                "excluded_picks": [],
            })
        return {"games": games}
