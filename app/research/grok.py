"""Grok Live Search — X+뉴스 소스, 오늘 날짜 필터로 확정 라인업·부상·라인 급변동 요약."""

import logging

from app.collectors.base import BaseAPIClient
from app.config import get_settings

logger = logging.getLogger(__name__)

# [§8-16] 리그별 현지 소스 지시. "KBO"만 주면 MLB 기사를 물어온다 —
#   팀명이 실제로 겹친다(Lotte·Tigers·Giants). 라인업은 현지 매체가 가장 빠르다.
LOCALE_HINT = {
    "KBO": ("Search in KOREAN. Prefer 스포츠조선·OSEN·엠스플뉴스·네이버스포츠·"
            "각 구단 공식 X 계정. This is Korean baseball, NOT MLB."),
    "NPB": ("Search in JAPANESE. Prefer 日刊スポーツ·スポニチ·デイリースポーツ·"
            "Yahoo!スポーツ·各球団公式X. This is Japanese baseball, NOT MLB."),
}

PROMPT = """Search X and news for {league} updates on {date} STRICTLY LIMITED to these games (do NOT report on any other league or match):

{games_block}

{locale_hint}
Summarize ONLY these, from the clubs' own accounts and local beat reporters:
(1) CONFIRMED starting lineups (batting order / XI) and the actual starting pitcher —
    say explicitly whether it is confirmed or still projected,
(2) same-day scratches, late injuries and returns from injury, with the player's role,
(3) team mood — quotes after a winning/losing streak, internal issues, manager comments,
(4) beat reporter observations that would change how the game is played,
(5) weather at game time.
Skip opinions, predictions and betting advice.

출력 규칙 (반드시 준수):
- 전부 한국어로 작성하라. 영어 문장 출력 금지. 선수 이름만 원어 병기 허용.
- 형식: 한 줄에 하나, 다음 접두어를 쓴다:
  "확정 라인업: ..." (확정일 때만) / "예상 라인업: ..." (미확정)
  / "부상: ..." / "복귀: ..." / "팀 분위기: ..." / "기자: ..." / "날씨: ..." / "라인 이동: ..."
- **확정과 예상을 절대 섞지 마라.** 공식 발표 전이면 반드시 "예상 라인업"으로 쓴다.
- 각 줄 앞에 해당 팀명을 붙여라 (다른 경기와 섞이지 않도록).
- 위 경기 목록에 없는 경기·리그는 절대 언급하지 마라."""

# [§8-21] 여론·심리 수집 — **속보 프롬프트와 분리한다.**
#   실사고(2026-08-26): KBO 조사 목표에 항목을 얹었더니 채움률이 6/10 → 0/10으로
#   붕괴했다. 한 프롬프트에 요구를 쌓으면 모델이 검색을 포기하고 변명을 쓴다.
#   → 심리는 **별도 호출**로 짧게 묻는다.
#
# ⚠️ 여론은 **사실이 아니다.** 두 가지로 해석될 수 있다:
#     동조 신호 — 팬이 아는 걸 우리가 몰랐다(부상 목격담 등)
#     역행 신호 — 팬심은 원래 홈팀·인기팀으로 쏠린다(편향)
#   어느 쪽인지는 측정 전엔 모른다. 그래서 **확률 계수로 만들지 않고**
#   판정이 읽는 재료로만 넘기며, 병렬 채점으로 값어치를 잰다.
SENTIMENT_PROMPT = """X(트위터)와 {league} 팬 커뮤니티에서 {date} 아래 경기들에 대한 팬 반응을 찾아라.

{games_block}

{locale_hint}
{community_hint}

각 경기별로 한국어 4줄 이내로 요약하라:
- 확정 라인업이 올라왔으면 그대로 (구단 공식 계정 우선)
- 팬들이 화제로 삼는 것 (복귀·부상·컨디션·감독 기용)
- 최근 몇 시간 사이 분위기가 뒤집혔으면 그 계기
- 승패 예상이 한쪽으로 쏠려 있으면 그 방향

⚠️ 기사·공식 발표로 확인된 것은 "(확인)", 커뮤니티에서만 도는 이야기는 "(미확인)"을 붙여라.
예측·베팅 조언은 쓰지 마라. 정말 아무것도 없으면 "특이사항 없음"이라고만 써라."""

# 리그별 커뮤니티 — 라인업·부상 목격담이 기사보다 빠른 곳
COMMUNITY_HINT = {
    "KBO": "Check 네이버 응원톡, MLBPARK KBO 게시판, DC 야구 갤러리, 각 구단 팬 커뮤니티.",
    "NPB": "Check なんJ, 5ch 野球板, 各球団ファンコミュニティ.",
    "MLB": "Check r/baseball, r/fantasybaseball, team subreddits.",
}

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
        prompt = PROMPT.format(league=league, date=date, games_block=games_block,
                               locale_hint=LOCALE_HINT.get(league, ""))
        text = await self._search_call(prompt)
        # 한국어 규율 검증 — 영어 문장 검출 시 1회 재생성
        from app.pipeline import contains_english_sentence

        if contains_english_sentence(text):
            logger.warning("[grok] english detected in briefing — regenerating once")
            text = await self._search_call(prompt + KOREAN_RETRY_SUFFIX)
            if contains_english_sentence(text):
                logger.warning("[grok] english still present after retry")
        return text

    async def sentiment(self, games: list[dict], date: str,
                        league: str = "MLB") -> str:
        """[§8-21] X·커뮤니티 여론. 속보와 **별도 호출**이다(프롬프트 과잉 방지).

        반환 텍스트는 그대로 판정에 넘어간다 — 여기서 확률로 바꾸지 않는다.
        """
        if self.mock:
            return "여론: 특이사항 없음 (목)"
        if not games:
            return ""
        games_block = "\n".join(f"- {g['away']} @ {g['home']}" for g in games)
        prompt = SENTIMENT_PROMPT.format(
            league=league, date=date, games_block=games_block,
            locale_hint=LOCALE_HINT.get(league, ""),
            community_hint=COMMUNITY_HINT.get(league, ""))
        text = await self._search_call(prompt)
        from app.pipeline import contains_english_sentence

        if contains_english_sentence(text):
            text = await self._search_call(prompt + KOREAN_RETRY_SUFFIX)
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

    async def search_with_citations(self, prompt: str) -> tuple[str, list[str]]:
        """[ORD-8] 본문과 **x.com 인용 목록**을 함께 돌려준다.

        🔴 왜 필요한가. 진단 실측 2026-09-12: x_search 는 정상 작동 중인데
           (`x_search_calls` 9 · `web_search_calls` 0) 우리가 받은 본문은
           `{"답": []}` 였다. 게시물 주소는 본문이 아니라 **annotations** 로
           오고, 우리 프롬프트가 `url` 을 필수로 걸어 모델이 전부 버렸다.
        ⚠️ `_search_call` 은 건드리지 않는다 — 브리핑·여론·델타·속보 넷이 쓴다.
        """
        resp = await self._post(
            "/responses",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json_body={
                "model": self.model,
                "input": prompt,
                "tools": [{"type": "web_search"}, {"type": "x_search"}],
            },
        )
        urls: list[str] = []
        for item in resp.get("output") or []:
            for ct in (item.get("content") or []):
                for a in (ct.get("annotations") or []):
                    u = a.get("url") or ""
                    if "x.com" in u or "twitter.com" in u:
                        urls.append(u)
        return extract_output_text(resp), urls

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
