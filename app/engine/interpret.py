"""[§8-31][B-5] 대조군 판정 — 판정 A와 **나란히 기록**되는 두 번째 판정.

왜 만드는가:
  판정(p_claude)이 λ와 50:50으로 섞이는데, **그 절반이 맞는지 한 번도 측정된
  적이 없다.** 안트로픽을 지우자는 판단도 남기자는 판단도 근거가 없었다.
  → 같은 페이로드를 두 모델에 넣고 같은 형식으로 받아 나란히 기록한다.
    어느 쪽이 나은지는 표본이 쌓인 뒤에 데이터가 말한다.

[B-1] provider를 직접 알지 않는다. 역할 `judge_b`로만 부르며, 어떤 모델을
      쓸지는 `.env`(`JUDGE_B_PROVIDER`/`JUDGE_B_MODEL`)가 정한다.
      기본은 **꺼짐** — 비용이 드는 병렬 호출을 기본값으로 켜지 않는다.

⚠️ **프롬프트와 출력 스키마를 복제하지 않는다.** `judge.SYSTEM`과
   `judge.VERDICT_TOOL`을 그대로 가져다 쓴다. 둘이 갈리는 순간 비교는
   "모델 차이"가 아니라 "프롬프트 차이"를 재는 것이 돼 무의미해진다.

⚠️ **검색 도구를 붙이지 않는다.** 판정 중 웹 검색을 켜면
     · 과거 경기를 블라인드로 재현할 때 **결과를 그대로 찾아낼 수 있고**(누출),
     · 판정 A는 못 보는 정보를 보게 돼 **대조가 성립하지 않는다.**
   검색을 켠 판정이 필요하면 그것은 별도의 세 번째 계열로 따로 기록해야 한다.
"""

import json
import logging

from app.config import get_settings
from app.engine.judge import JUDGE_BATCH, SYSTEM, VERDICT_TOOL
from app.llm import complete, role_enabled

logger = logging.getLogger(__name__)

ROLE = "judge_b"


class SecondJudge:
    """판정 B — 역할 기반. 어느 provider든 될 수 있다."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.last_provider: str = ""

    @property
    def enabled(self) -> bool:
        return role_enabled(ROLE, self.settings)

    async def judge(self, payload: dict) -> dict:
        """payload → {"games": [...]}. 판정 A와 **같은 형식**.

        배치 분할도 같은 기준(JUDGE_BATCH)을 쓴다 — 배치 크기가 다르면
        한쪽만 절단돼 비교가 오염된다.
        """
        if not self.enabled:
            return {"games": []}
        games = payload.get("games") or []
        if not games:
            return {"games": []}
        if len(games) <= JUDGE_BATCH:
            return await self._once(payload)
        merged: list[dict] = []
        for i in range(0, len(games), JUDGE_BATCH):
            batch = games[i:i + JUDGE_BATCH]
            try:
                merged += (await self._once({**payload, "games": batch})).get("games") or []
            except Exception as exc:      # 배치 실패가 전체를 죽이지 않는다
                logger.error("[judge_b] 배치 %d~%d 실패 — 나머지 계속: %s",
                             i + 1, i + len(batch), exc)
        return {"games": merged}

    async def _once(self, payload: dict) -> dict:
        res = await complete(
            ROLE,
            [{"role": "user",
              "content": json.dumps(payload, ensure_ascii=False, default=str)}],
            system=SYSTEM, schema=VERDICT_TOOL["input_schema"],
            max_tokens=8000, settings=self.settings)
        self.last_provider = res.label
        verdict = res.data or {}
        n_in, n_out = len(payload.get("games") or []), len(verdict.get("games") or [])
        logger.info("[judge_b] %s — 요청 %d경기 → 판정 %d경기", res.label, n_in, n_out)
        if n_out < n_in:
            logger.warning("[judge_b] 판정 누락 %d경기", n_in - n_out)
        return verdict


# 이전 이름 — 호출부가 있으면 계속 동작하게 둔다(이름만 바뀐 것이다).
GrokJudge = SecondJudge
