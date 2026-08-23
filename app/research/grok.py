"""Grok Live Search — X+뉴스 소스, 오늘 날짜 필터로 확정 라인업·부상·라인 급변동 요약."""

import logging

from app.collectors.base import BaseAPIClient
from app.config import get_settings

logger = logging.getLogger(__name__)

PROMPT = """Search X and news for {league} updates on {date} STRICTLY LIMITED to these games (do NOT report on any other league or match):

{games_block}

Summarize ONLY: (1) confirmed lineups, (2) breaking injury news, (3) sharp betting line moves, (4) weather issues.
Skip opinions and predictions.

출력 규칙 (반드시 준수):
- 전부 한국어로 작성하라. 영어 문장 출력 금지. 선수 이름만 원어 병기 허용.
- 형식: 한 줄에 하나, "확정 라인업: ..." / "부상: ..." / "라인 이동: ..." / "날씨: ..." 접두어.
- 위 경기 목록에 없는 경기·리그는 절대 언급하지 마라."""

KOREAN_RETRY_SUFFIX = "\n\n이전 답변에 영어 문장이 포함됐다. 반드시 전부 한국어로만 다시 작성하라 (선수 이름 원어만 허용)."


COUNTER_PROMPT = """You are a research assistant (NOT a judge). For each verdict below, search X and news for CONCRETE COUNTER-EVIDENCE only — facts that would weaken the stated conclusion (injuries, lineup changes, form data, sharp line moves). Do NOT give your own prediction.

{items}

Reply in Korean, one bullet per game: "- {{매치업}}: {{반대 근거 팩트}} (출처)". If no substantive counter-evidence exists for a game, write "- {{매치업}}: 반대 근거 없음". Keep it under 12 lines total."""

DELTA_PROMPT = """Compare the situation NOW against this earlier briefing for {date} games:

--- EARLIER BRIEFING ---
{old_news}
--- GAMES ---
{games_block}

Search X and news for MATERIAL changes since then, ONLY these categories:
starter pitcher scratched/replaced, confirmed lineup missing a key player, odds moved 5%+ sharply, weather turned bad.

Output ONLY a JSON array (no prose). Empty array [] if nothing material changed:
[{{"game": "<away> @ <home>", "change": "<한국어 한 줄: 무엇이 바뀌었나>"}}]"""


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
        prompt = PROMPT.format(league=league, date=date, games_block=games_block)
        text = await self._search_call(prompt)
        # 한국어 규율 검증 — 영어 문장 검출 시 1회 재생성
        from app.pipeline import contains_english_sentence

        if contains_english_sentence(text):
            logger.warning("[grok] english detected in briefing — regenerating once")
            text = await self._search_call(prompt + KOREAN_RETRY_SUFFIX)
            if contains_english_sentence(text):
                logger.warning("[grok] english still present after retry")
        return text

    async def _search_call(self, prompt: str) -> str:
        resp = await self._post(
            "/responses",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json_body={
                "model": self.model,
                "input": prompt,
                "tools": [{"type": "web_search"}, {"type": "x_search"}],
            },
        )
        return extract_output_text(resp)

    async def counter_briefing(self, items: list[str]) -> str:
        """[정보 수집 전용] 논쟁 경기 판정의 '반대 근거' 팩트만 수집 (판정 아님)."""
        if self.mock:
            return ""  # 목 모드: 반대 근거 없음 → 재판정 스킵
        return await self._search_call(COUNTER_PROMPT.format(items="\n".join(items)))

    async def delta_check(self, old_news: str, games: list[dict], date: str) -> list[dict]:
        """이전 브리핑 대비 중대 변화만 JSON으로. 변화 없으면 []."""
        if self.mock:
            return []
        games_block = "\n".join(f"- {g['away']} @ {g['home']}" for g in games)
        text = await self._search_call(
            DELTA_PROMPT.format(date=date, old_news=old_news[:2500], games_block=games_block)
        )
        import json as _json
        import re as _re

        m = _re.search(r"\[.*\]", text, _re.S)
        if not m:
            return []
        try:
            data = _json.loads(m.group(0))
            return [d for d in data if isinstance(d, dict) and d.get("game") and d.get("change")]
        except _json.JSONDecodeError:
            return []


def extract_output_text(resp: dict) -> str:
    """Responses API output 배열에서 output_text만 이어붙인다."""
    parts = [
        c["text"]
        for item in resp.get("output", [])
        for c in (item.get("content") or [])
        if c.get("type") == "output_text"
    ]
    return "\n".join(parts).strip()
