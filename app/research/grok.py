"""Grok Live Search — X+뉴스 소스, 오늘 날짜 필터로 확정 라인업·부상·라인 급변동 요약."""

import logging

from app.collectors.base import BaseAPIClient
from app.config import get_settings

logger = logging.getLogger(__name__)

PROMPT = """Search X and news for {league} updates on {date} ONLY about these games:

{games_block}

Summarize ONLY: (1) confirmed lineups, (2) breaking injury news, (3) sharp betting line moves.
Skip opinions and predictions. Bullet points, one line each, prefix each with CONFIRMED LINEUP / INJURY / LINE MOVE / WEATHER."""


class GrokClient(BaseAPIClient):
    name = "grok"
    base_url = "https://api.x.ai/v1"
    timeout = 60.0

    def __init__(self, mock: bool | None = None):
        settings = get_settings()
        super().__init__(settings.mock_grok if mock is None else mock)
        self.api_key = settings.xai_api_key
        self.model = settings.grok_model

    async def live_briefing(
        self, games: list[dict], date: str, league: str = "MLB"
    ) -> str:
        """당일 속보 요약 텍스트 반환.

        xAI Live Search(search_parameters)는 폐기됨 → Agent Tools API
        (/v1/responses + web_search·x_search 툴) 사용. 날짜 필터는 프롬프트로 제약.
        """
        if self.mock:
            resp = self.load_mock("grok_live.json")
            return resp["choices"][0]["message"]["content"]
        games_block = "\n".join(f"- {g['away']} @ {g['home']}" for g in games)
        resp = await self._post(
            "/responses",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json_body={
                "model": self.model,
                "input": PROMPT.format(league=league, date=date, games_block=games_block),
                "tools": [{"type": "web_search"}, {"type": "x_search"}],
            },
        )
        return extract_output_text(resp)


def extract_output_text(resp: dict) -> str:
    """Responses API output 배열에서 output_text만 이어붙인다."""
    parts = [
        c["text"]
        for item in resp.get("output", [])
        for c in (item.get("content") or [])
        if c.get("type") == "output_text"
    ]
    return "\n".join(parts).strip()
