"""[§8-31] Grok 판정 — 안트로픽 judge의 **병렬 대조군**.

왜 만드는가:
  판정(p_claude)이 λ와 50:50으로 섞이는데, **그 절반이 맞는지 한 번도 측정된 적이
  없다.** 안트로픽을 지우자는 판단도, 남기자는 판단도 근거가 없었다.
  → 같은 페이로드를 두 모델에 넣고 같은 형식으로 받아 **나란히 기록**한다.
    어느 쪽이 나은지는 표본이 쌓인 뒤에 데이터가 말한다.

⚠️ **프롬프트와 출력 스키마를 복제하지 않는다.** `judge.SYSTEM`과
   `judge.VERDICT_TOOL`을 그대로 가져다 쓴다. 둘이 갈리는 순간 비교는
   "모델 차이"가 아니라 "프롬프트 차이"를 재는 것이 돼 무의미해진다.

⚠️ **검색 도구는 기본 꺼짐(search=False).** Grok은 web_search·x_search를 붙일 수
   있지만, 판정 중 검색을 켜면
     · 과거 경기를 블라인드로 재현할 때 **결과를 그대로 찾아낼 수 있고**(누출),
     · 안트로픽은 못 보는 정보를 보게 돼 **대조가 성립하지 않는다.**
   검색을 켠 판정이 필요하면 그것은 별도의 세 번째 계열로 따로 기록해야 한다.
"""

import json
import logging

from app.collectors.base import ApiQuotaError, BaseAPIClient
from app.config import get_settings
from app.engine.judge import JUDGE_BATCH, SYSTEM, VERDICT_TOOL

logger = logging.getLogger(__name__)


class GrokJudge(BaseAPIClient):
    """xAI의 OpenAI 호환 chat/completions + function calling."""

    name = "grok-judge"
    base_url = "https://api.x.ai/v1"
    timeout = 120.0

    def __init__(self, mock: bool | None = None):
        s = get_settings()
        super().__init__(s.mock_grok if mock is None else mock)
        self.settings = s
        self.api_key = s.xai_api_key
        self.model = s.grok_model

    # ------------------------------------------------------------------ 공개
    async def judge(self, payload: dict, *, search: bool = False) -> dict:
        """payload → {"games": [...]}. 안트로픽 `Judge.judge`와 **같은 형식**.

        배치 분할도 같은 기준(JUDGE_BATCH)을 쓴다 — 배치 크기가 다르면
        한쪽만 절단돼 비교가 오염된다.
        """
        games = payload.get("games") or []
        if self.mock:
            from app.engine.judge import Judge

            return Judge._mock_verdict(payload)
        if not games:
            return {"games": []}
        if len(games) > JUDGE_BATCH:
            merged: list[dict] = []
            for i in range(0, len(games), JUDGE_BATCH):
                batch = games[i:i + JUDGE_BATCH]
                try:
                    part = await self._once({**payload, "games": batch}, search)
                    merged += part.get("games") or []
                except Exception as exc:      # 배치 실패가 전체를 죽이지 않는다
                    logger.error("[grok-judge] 배치 %d~%d 실패 — 나머지 계속: %s",
                                 i + 1, i + len(batch), exc)
            return {"games": merged}
        return await self._once(payload, search)

    # ------------------------------------------------------------------ 내부
    async def _once(self, payload: dict, search: bool) -> dict:
        tools = [{
            "type": "function",
            "function": {
                "name": VERDICT_TOOL["name"],
                "description": VERDICT_TOOL["description"],
                "parameters": VERDICT_TOOL["input_schema"],
            },
        }]
        if search:
            # 켤 때는 **의도적으로만.** 기본 경로에서는 도달하지 않는다.
            tools += [{"type": "web_search"}, {"type": "x_search"}]
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user",
                 "content": json.dumps(payload, ensure_ascii=False, default=str)},
            ],
            "tools": tools,
            "tool_choice": {"type": "function",
                            "function": {"name": VERDICT_TOOL["name"]}},
        }
        try:
            resp = await self._post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json_body=body,
            )
        except ApiQuotaError:
            raise
        verdict = self._extract(resp)
        if verdict is None:
            raise RuntimeError("grok-judge did not return a verdict tool call")
        n_in, n_out = len(payload.get("games") or []), len(verdict.get("games") or [])
        logger.info("[grok-judge] 요청 %d경기 → 판정 %d경기", n_in, n_out)
        if n_out < n_in:
            logger.warning("[grok-judge] 판정 누락 %d경기", n_in - n_out)
        return verdict

    @staticmethod
    def _extract(resp: dict) -> dict | None:
        """tool_calls에서 verdict 인자를 꺼낸다. 형식이 어긋나면 None."""
        for choice in resp.get("choices") or []:
            for call in (choice.get("message") or {}).get("tool_calls") or []:
                fn = call.get("function") or {}
                if fn.get("name") != VERDICT_TOOL["name"]:
                    continue
                args = fn.get("arguments")
                if isinstance(args, dict):
                    return args
                try:
                    return json.loads(args or "")
                except (TypeError, ValueError):
                    logger.warning("[grok-judge] 도구 인자 파싱 실패")
        return None
