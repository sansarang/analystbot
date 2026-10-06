"""텔레그램 봇 — 명령 셋.

🔴 §17-c — **사용자와 직접 대화해 예측을 내지 않는다.** 봇이 보여주는 것은
   파이프라인이 만든 카드 그대로다. LLM 이 여기서 말을 만들지 않는다.
"""
from __future__ import annotations

import asyncio
import logging
import os

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **MPS 를 흔드는 것을 진입점에서 끈다** — 사용자 지시 2026-10-05
# ══════════════════════════════════════════════════════════════════
#
#  > 환경변수 `TOKENIZERS_PARALLELISM=false` 를 봇 진입점에서 설정.
#
#  ⚠️ `tokenizers` 는 스레드를 띄워 토크나이즈를 나눈다. 🔴 재정렬 모델은
#     **한 스레드가 소유**해야 하고(PyTorch #197805), 그 병렬이 그 전제를
#     흔든다. ⚠️ **import 보다 먼저** 걸어야 한다 — 그 라이브러리가 import
#     시점에 이 값을 읽는다.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

from app import timefmt
from app.research import rerank as _rerank
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **재정렬 모델을 여기서 올린다**(사용자 지시 2026-10-05 · 2번)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 봇 시작(`cmd_analyze` 진입 전 또는 프로세스 기동)에서 **전용 스레드로**
    #  > 모델 로드 + 더미 쌍 1개 `predict`. **지연 로드 함수 삭제.**
    #
    #  ⚠️ 지연 로드를 지웠으므로 **여기서 안 올리면 영원히 ③단**이다.
    #  🔴 두 번째 호출부터는 바로 돌아온다(`loads()` 가 1 이다).
    # 🔴🔴 **기동 검사**(지시서 §2 · M129) — 걸리는 템플릿이 있으면 **터진다.**
    #    ⚠️ 조용히 건너뛰면 그 유형이 구조적으로 0건인 채로 운영이 돈다
    #       (실측 2026-10-06: squad_rotation·national_duty_return 이 그랬다).
    from app.bot_boot import boot_checks
    boot_checks()
    # 🔴 예열도 **`rank` 를 지난다**(§8 3단계) — 재생에서는 모델을 올리지 않는다
    from app.core import rank as _rank
    _warm = _rank.warm()
    logger.info("[bot] 재정렬 예열 — %s (로드 %d회)", _warm, _rerank.loads())
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
    body = await _v6_card(pool, team=team, opponent=opponent)
    for chunk in _split(body):
        await m.answer(chunk)


async def _v6_card(pool, *, team: str, opponent: str) -> str:
    """🔴🔴 **v6 경로** — `pipeline.analyze` → `render.card_text`(§8 4단계).

    ══════════════════════════════════════════════════════════════════
    🔴 왜 갈아끼웠나 — 같은 질문으로 둘을 돌려 봤다(실측 2026-10-06)
    ══════════════════════════════════════════════════════════════════

    | 경로 | 결과 |
    |---|---|
    | 옛 `analyze.answer` | 🔴 **카드가 없다** — `openworld_not_found`(1.0분 · $0.0007) |
    | v6 `pipeline.analyze` | ✅ 카드 열 블록 · 변수 19개 · 시나리오 6개($0.0048) |

    ⚠️ 갈린 자리는 **철자 단계**다 — 이름표가 `한국` 을 모르고, 옛 ⑥-1 은 산문
       파싱이라 돌지 않았다. v6 는 `llm.ask(purpose="spell")` 로 `South Korea` 를
       받아 입구를 다시 돌린다.
    🔴 옛 경로는 **지우지 않는다** — §8 5단계가 지운다(그때까지 되돌릴 자리가 있다).
    """
    from app import net as _net_mod
    from app import search as _search
    from app.core import pipeline, render
    from app.core.schema import Ambiguous
    said = f"{team} vs {opponent}".strip() if opponent else team
    got = await pipeline.analyze(said, pool=pool, net=_net_mod.Net(),
                                 chain=_search.build_chain())
    if isinstance(got, Ambiguous):
        # 🔴 **고르지 않는다** — 사용자가 지목한다(§17-g-3 · M14)
        lines = [f"🔴 경기를 확정하지 못했다 — {got.why}"]
        lines += [f"  · {c}" for c in got.candidates]
        return "\n".join(lines)
    return render.card_text(got)


@dp.message(Command("health"))
async def cmd_health(m: Message) -> None:
    from app.version import boot_info, staleness_line
    s = get_settings()
    pool = await get_pool(s.database_url)
    # 🔴 **KST 날짜**다 — `today_kst()` 가 KST 날짜를 주므로 칸도 그렇게 잘라야
    #    짝이 맞는다(종전 `starts_kst::date` 는 세션 시간대로 돌았다).
    n = await pool.fetchval(
        f"SELECT count(*) FROM games WHERE {timefmt.sql_kst_day()} = $1",
        today_kst())
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
