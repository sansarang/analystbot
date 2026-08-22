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
                        "verdict": {"type": "string", "description": "시장/모델/전문가 충돌 판정과 근거"},
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
                    "required": ["game_id", "p_claude", "verdict", "excluded_picks"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["games"],
        "additionalProperties": False,
    },
}

SYSTEM = """너는 스포츠 분석 챗봇의 판정관(judge)이다. 입력으로 경기별 stats, 시장 확률(p_market), 모델 확률(p_model), 전문가 픽, 속보 요약이 담긴 JSON을 받는다.

규칙:
- 입력 JSON에 있는 숫자만 사용한다. 새로운 수치(배당, 스탯, 전적)를 만들어내지 않는다.
- ① 전문가 픽의 reasoning 속 수치 주장이 입력 stats와 모순되면 그 픽을 excluded_picks에 넣고 사유를 적는다.
- ② 시장(p_market)/모델(p_model)/전문가 컨센서스가 충돌하는 경기는 verdict에 어느 쪽을 신뢰하는지와 근거를 적는다.
- ③ 모든 경기에 대해 자체 홈팀 승리 확률 p_claude(0~1)를 산출한다.
- 분석이 끝나면 반드시 verdict 도구를 정확히 한 번 호출해 결과를 제출한다. 도구 호출 외 장문 출력은 불필요하다."""


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
        """결정적 목 판정: p_claude = (p_model + p_market) / 2."""
        games = []
        for g in payload.get("games", []):
            p_model = float(g.get("p_model", 0.5))
            p_market = float(g.get("p_market", 0.5))
            p = max(0.05, min(0.95, (p_model + p_market) / 2))
            games.append({
                "game_id": g["game_id"],
                "p_claude": round(p, 4),
                "verdict": "[mock] 모델과 시장 확률의 평균을 채택 (목 모드 판정)",
                "excluded_picks": [],
            })
        return {"games": games}
