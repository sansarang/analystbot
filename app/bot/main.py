"""텔레그램 봇 — 명령 셋.

🔴 §17-c — **사용자와 직접 대화해 예측을 내지 않는다.** 봇이 보여주는 것은
   파이프라인이 만든 카드 그대로다. LLM 이 여기서 말을 만들지 않는다.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

from app import analyze as A
from app import slate as S
from app.config import SLATE_DAYS, get_settings
from app.db import get_pool
from app.run import collect_slate
from app.scheduler import today_kst
from app.sources import DbSources

logger = logging.getLogger("bot")
dp = Dispatcher()


@dp.message(Command("slate"))
async def cmd_slate(m: Message) -> None:
    """`/slate [리그] [YYYY-MM-DD]` — 🔴 **요청받은 날짜·리그만**(§14-9)."""
    s = get_settings()
    parts = (m.text or "").split()[1:]
    day = today_kst()
    leagues: list[str] = []
    for p in parts:
        try:
            day = datetime.strptime(p, "%Y-%m-%d").date()
        except ValueError:
            leagues.append(p.upper() if p.isascii() else p)
    pool = await get_pool(s.database_url)
    body, games = await collect_slate(day, leagues or list(s.slate_leagues),
                                     DbSources(pool))
    if not games:
        await m.answer(f"{day} 슬레이트가 0경기다. "
                       f"(리그: {', '.join(leagues or s.slate_leagues)})")
        return
    for chunk in _split(body):
        await m.answer(chunk)


@dp.message(Command("games"))
async def cmd_games(m: Message) -> None:
    """`/games [팀|종목|리그]` — 🔴 **쌓아 둔 것에서 바로 답한다.**

    사용자 지시 2026-10-01: *"사용자가 경기에 대해 질문을 했을 때 바로 답할 수 있고"*

    🔴 **웹에 나가지 않는다.** 스케줄러가 미리 쌓은 `games` 표만 읽는다 — 물을
       때마다 검색하면 느리고, 무엇보다 검색 엔진 정지를 부른다(실측 2026-09-30).
    ⚠️ 못 찾으면 **왜 못 찾았는지** 답한다 — "아직 안 쌓였다"와 "그런 경기가 없다"는
       다르다(조용한 0 금지).
    """
    s = get_settings()
    arg = " ".join((m.text or "").split()[1:]).strip()
    pool = await get_pool(s.database_url)

    sport = next((k for k, ko in S.SPORT_KO.items() if arg and arg == ko), None)
    if not arg:
        found = await S.window(pool, days=SLATE_DAYS)
        title = f"오늘·내일 슬레이트"
    elif sport:
        found = await S.find(pool, sport=sport, days=SLATE_DAYS)
        title = f"{arg} — 오늘·내일"
    else:
        # 🔴 팀인지 리그인지 **모른다.** 둘 다로 찾고, 맞는 것을 전부 낸다 —
        #    하나를 골라 주면 남의 경기를 답할 수 있다(§17-g-3 · M14).
        found = await S.find(pool, team=arg, days=SLATE_DAYS)
        if not found.games:
            found = await S.find(pool, league=arg, days=SLATE_DAYS)
        title = f"`{arg}` — 오늘·내일"
    for chunk in _split(S.render(found, title=title)):
        await m.answer(chunk)


@dp.message(Command("analyze"))
async def cmd_analyze(m: Message) -> None:
    """`/analyze <팀|리그>` — 🔴 **질문 한 줄 → 카드 한 장**(사용자 출력 블록 10개).

    사용자 지시 2026-10-02: *"배선해라"* · *"최종 목표는 니가 수동으로 돌려던 거를
    자동화 하는 거다"*.

    🔴 **경기를 고르지 않는다** — 여럿이 맞으면 목록을 내고 사용자가 지목한다
       (§17-g-3 · M14: 남의 경기를 분석하면 그 카드는 통째로 거짓이다).
    ⚠️ 발송 스위치와 무관하다 — 이것은 **사용자가 물어서 돌아가는 답**이고, §11-11 이
       막는 것은 **봇이 스스로 보내는** 카드다.
    """
    s = get_settings()
    words = (m.text or "").split()[1:]
    arg = " ".join(words).strip()
    if not arg:
        await m.answer("`/analyze <팀>` 또는 `/analyze <팀> vs <상대>` — "
                       "어느 경기인지 적어라")
        return
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **두 팀을 받는다** — 봇이 표에 없는 경기를 찾으려면 상대가 필요하다
    # ══════════════════════════════════════════════════════════════════
    #
    #  `중국 vs 팔레스타인` · `중국 팔레스타인` 둘 다 받는다. 🔴 상대를 모르면
    #  `findgame` 의 *"그 경기 페이지인가"* 검사가 **우리 팀만** 보게 되어 약해지고
    #  (§13-c ② 약한 검사), 같은 팀의 다른 날 경기를 가져올 수 있다.
    #  ⚠️ 한 단어면 상대는 없다 — 그래도 돈다. 검사가 약하다는 사실이 사유로 남는다.
    team, opponent = arg, ""
    low = arg.lower()
    for sep in (" vs ", " vs. ", " - ", " 대 ", " : "):
        if sep in low:
            i = low.index(sep)
            team, opponent = arg[:i].strip(), arg[i + len(sep):].strip()
            break
    else:
        if len(words) == 2:
            team, opponent = words[0], words[1]
    pool = await get_pool(s.database_url)
    body = await A.answer(pool, team=team, opponent=opponent or None,
                          days=SLATE_DAYS)
    for chunk in _split(body):
        await m.answer(chunk)


@dp.message(Command("health"))
async def cmd_health(m: Message) -> None:
    from app.version import boot_info, staleness_line
    s = get_settings()
    pool = await get_pool(s.database_url)
    n = await pool.fetchval(
        "SELECT count(*) FROM games WHERE starts_kst::date = $1", today_kst())
    unk = await pool.fetchval(
        "SELECT COALESCE(sum(cardinality(unknowns)), 0) FROM runs "
        "WHERE slate_date = $1", today_kst()) or 0
    stale = staleness_line()
    await m.answer(
        f"commit {boot_info().short}\n"
        f"오늘 {n}경기 · 못 잰 칸 {unk}\n"
        + (f"{stale}\n" if stale else "")
        + f"발송 {'켜짐' if s.send_enabled else '꺼짐'}\n"
        + f"LLM {s.ollama_model} @ {s.ollama_base_url}")


def _split(text: str, limit: int = 3800) -> list[str]:
    """텔레그램 한 건 상한. 🔴 **자르는 것을 조용히 하지 않는다.**"""
    if len(text) <= limit:
        return [text]
    out, cur = [], ""
    for line in text.splitlines(True):
        if len(cur) + len(line) > limit:
            out.append(cur + f"\n… (이어짐 {len(out) + 1})")
            cur = ""
        cur += line
    if cur:
        out.append(cur)
    return out


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    s = get_settings()
    if not s.telegram_bot_token:
        logger.warning("[bot] 토큰이 없다 — 목 모드로 그냥 산다")
        while True:
            await asyncio.sleep(3600)
    bot = Bot(token=s.telegram_bot_token)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
