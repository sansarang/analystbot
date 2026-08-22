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

    async def live_briefing(
        self, games: list[dict], date: str, league: str = "MLB"
    ) -> str:
        """당일 속보 요약 텍스트 반환."""
        if self.mock:
            resp = self.load_mock("grok_live.json")
        else:
            games_block = "\n".join(f"- {g['away']} @ {g['home']}" for g in games)
            resp = await self._post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json_body={
                    "model": "grok-3-latest",
                    "messages": [{
                        "role": "user",
                        "content": PROMPT.format(
                            league=league, date=date, games_block=games_block
                        ),
                    }],
                    "search_parameters": {
                        "mode": "on",
                        "sources": [{"type": "x"}, {"type": "news"}],
                        "from_date": date,
                        "to_date": date,
                    },
                },
            )
        return resp["choices"][0]["message"]["content"]
