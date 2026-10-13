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
from aiogram.types import CallbackQuery, Message

from app import secrets_mask, timefmt
from app.research import rerank as _rerank
from app.config import SLATE_DAYS, get_settings
from app.db import get_pool

logger = logging.getLogger("bot")

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **로그에서 비밀을 가린다** — 옛 진입점(`app/run.py`)이 부르던 자리다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ §8 5단계에서 그 진입점을 지웠다(사용자 지시 2026-10-06 ⑧). 🔴 그러면서 이
#     호출이 **아무 데서도 안 불리게** 됐다 — 배선 계약이 그것을 이름으로 잡았다
#     (`app.secrets_mask.install_log_filter`). 그래서 **여기** 로 옮긴다:
#     봇이 유일한 진입점이므로 제자리다.
secrets_mask.install_log_filter()
dp = Dispatcher()


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
    # 🔴🔴 **가름 규칙은 `pipeline.split_asked` 하나다**(사본 금지 · #1)
    #    ⚠️ 실사고 2026-10-11: 같은 규칙이 여기와 `pipeline._question` 에 **사본**
    #       으로 있어, `시애틀 사운더스` 를 고칠 때 **한쪽만 고쳤고** `--deep`
    #       경로는 그대로 깨져 있었다.
    from app.core.pipeline import split_asked
    team, opponent = split_asked(arg)
    pool = await get_pool(s.database_url)
    # 🔴 **보드 글**(§4) — 질문 아래 줄에 `보드:`·`추가:` 가 오면 그 글을 넘긴다.
    #    ⚠️ 배당 숫자는 파서가 **받지 않는다**(`app/core/board.py`).
    lines = (m.text or "").splitlines()
    board_text = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
    body, got = await _v6_card(pool, team=team, opponent=opponent,
                               board_text=board_text, want_ref=True)
    await _send_card(m, body, got, asked=arg, board_text=board_text)


async def _send_card(m: Message, body: str, got, *, asked: str,
                     board_text: str = "") -> None:
    """🔴🔴 **카드와 버튼을 함께 보낸다** — 사용자 지시 2026-10-10 §1-3·§2-3.

    ⚠️ 실측 2026-10-10: 봇에 인라인 키보드가 **하나도 없었다** — 카드 밑 글자는
       누를 수 없었다. 🔴 그래서 §2-3 의 *"사용자가 누른 경기만 돈다"* 를 지킬
       방법 자체가 없었다.
    🔴 버튼은 **마지막 조각**에만 붙인다(카드가 길면 여러 조각으로 나간다).
    """
    from app.bot import keys, pending
    from app.core.schema import Ambiguous
    ask = pending.Ask(asked=asked, board_text=board_text)
    if isinstance(got, Ambiguous):
        ask.picks = list(got.picks or [])
        token = pending.new(ask)
        kb = keys.pick_keys(token, ask.picks)
    else:
        ask.key = str(getattr(getattr(got, "match", None), "id", "") or "")
        token = pending.new(ask)
        # 🔴 §2-3 — **확정 XI 전이면** 라인업 감시 버튼을 더한다
        kb = keys.card_keys(token=token, watch=_xi_open(got))
    chunks = _split(body)
    for chunk in chunks[:-1]:
        await m.answer(chunk)
    sent = await m.answer(chunks[-1], reply_markup=kb)
    ask.chat_id = getattr(getattr(sent, "chat", None), "id", None)
    ask.message_id = getattr(sent, "message_id", None)


def _xi_open(card) -> bool:
    """🔴 §2-3 — **확정 XI 전인가**(그때만 감시 버튼을 낸다).

    🔴 판정은 `layer1.xi_confirmed` 하나다(사본 금지) — 여기서 다시 세지 않는다.
    """
    try:
        from app.core import layer1
        return not layer1.xi_confirmed(card)
    except Exception:                                       # noqa: BLE001
        return False


@dp.message(Command("reanalyze", "재분석"))
async def cmd_reanalyze(m: Message) -> None:
    """`/재분석 <팀> vs <상대>` — 🔴🔴 **확정 XI 로 다시 낸다**(축구 §4).

    > 기사 검색(s3)·추출(s4)은 **다시 하지 않는다** — 비용·시간을 아끼고 변수가
    > 회차마다 흔들리지 않게. s2 만 다시 돌고 s6·s7 을 다시 돈다.

    ⚠️ 마지막 실행이 없거나 24시간을 넘었으면 **전체를 새로** 돈다(§4-5).
    """
    s = get_settings()
    from app.bot_boot import boot_checks
    boot_checks()
    from app.core import rank as _rank
    logger.info("[bot] 재정렬 예열 — %s", _rank.warm())
    arg = " ".join((m.text or "").split()[1:]).strip()
    if not arg:
        await m.answer("`/재분석 <팀> vs <상대>` — 어느 경기인지 적어라")
        return
    pool = await get_pool(s.database_url)
    for chunk in _split(await _v6_card(pool, said=arg, again=True)):
        await m.answer(chunk)


@dp.message(Command("deep", "자세히"))
async def cmd_deep(m: Message) -> None:
    """`/자세히 <팀> vs <상대>` — 🔴 **열네 블록 긴 카드**(1겹의 `📖 자세히`).

    🔴 **마지막 실행을 다시 쓴다**(`reanalyze` 입구) — 긴 카드를 보려고 s3·s4 를
       다시 돌려 돈을 쓰지 않는다. 실행이 없으면 그 입구가 전체를 새로 돈다(§4-5).
    """
    s = get_settings()
    from app.bot_boot import boot_checks
    boot_checks()
    arg = " ".join((m.text or "").split()[1:]).strip()
    if not arg:
        await m.answer("`/자세히 <팀> vs <상대>` — 어느 경기인지 적어라")
        return
    pool = await get_pool(s.database_url)
    for chunk in _split(await _v6_card(pool, said=arg, again=True, deep=True)):
        await m.answer(chunk)


@dp.message(Command("debug", "디버그"))
async def cmd_debug(m: Message) -> None:
    """`/디버그 <팀> vs <상대>` — 🔴 **같은 카드에 근거 번호·양상 비중**(지시 ④).

    ⚠️ 숫자는 **똑같다** — 보이는 줄만 늘어난다(`render.debug_text`).
    🔴 **마지막 실행을 다시 쓴다**(`reanalyze` 입구) — 디버그를 보려고 s3·s4 를
       다시 돌려 돈을 쓰지 않는다. 실행이 없으면 그 입구가 전체를 새로 돈다(§4-5).
    """
    s = get_settings()
    from app.bot_boot import boot_checks
    boot_checks()
    arg = " ".join((m.text or "").split()[1:]).strip()
    if not arg:
        await m.answer("`/디버그 <팀> vs <상대>` — 어느 경기인지 적어라")
        return
    pool = await get_pool(s.database_url)
    for chunk in _split(await _v6_card(pool, said=arg, again=True, debug=True)):
        await m.answer(chunk)


#: 🔴🔴 **사람이 준 라인업 캡처 경로**(도구가 넣는다 · 운영에서는 빈 글자다).
#  ⚠️ 텔레그램 입구는 사진을 받으면 여기 대신 `analyze(xi_image=…)` 로 바로 준다.
XI_IMAGE: str = ""


async def _v6_card(pool, *, team: str = "", opponent: str = "", said: str = "",
                   again: bool = False, board_text: str = "",
                   debug: bool = False, deep: bool = False,
                   pick_key: str = "", want_ref: bool = False):
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
    asked = said or (f"{team} vs {opponent}".strip() if opponent else team)
    # 🔴 **재분석은 다른 입구다**(§4) — s3·s4 를 다시 돌지 않는다
    fn = pipeline.reanalyze if again else pipeline.analyze
    # 🔴🔴 **P0** — 카드 실행은 **하루 캐시**를 쓴다(팀 페이지·대회 일정·순위표).
    #    ⚠️ XI·결장·뉴스 주소는 그 목록에 없어 **늘 새로 받는다**(`Net.DAY_CACHE`).
    got = await fn(asked, pool=pool,
                   net=_net_mod.Net(cache=True, day_cache=True),
                   chain=_search.build_chain(),
                   # 🔴 **사람이 준 라인업 캡처**는 두 길에 다 간다(실사고
                   #    2026-10-11: `--deep` 은 재분석 길이라 안 갔다)
                   xi_image=XI_IMAGE,
                   **({} if again else {"board_text": board_text,
                                        "pick_key": pick_key}))
    if isinstance(got, Ambiguous):
        # 🔴 **고르지 않는다** — 사용자가 지목한다(§17-g-3 · M14)
        lines = [f"🔴 경기를 확정하지 못했다 — {got.why}"]
        lines += [f"  · {c}" for c in got.candidates]
        # 🔴 §1-3 — 버튼으로 고를 수 있으면 그 사실을 알린다(버튼은 호출부가 붙인다)
        if got.picks:
            lines.append(f"👇 **아래 버튼에서 고르면** 그 경기로 분석한다"
                         f"(후보 {len(got.picks)}개)")
        out = "\n".join(lines)
        return (out, got) if want_ref else out
    if debug:
        said = render.debug_text(got)
        return (said, got) if want_ref else said
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **1겹이 기본이다**(사용자 지시 2026-10-09(3차) §1)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 읽는 사람이 **첫 세 줄**에서 결론과 이유를 얻게 한다.
    #
    #  🔴 긴 카드는 **버튼 뒤**다(`📖 자세히` → `deep=True`). ⚠️ 종전에는 1겹이
    #     없어서 열네 블록이 한꺼번에 나갔다.
    said = render.card_text(got) if deep else render.layer1_text(got)
    return (said, got) if want_ref else said


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **버튼이 실제로 일한다** — 사용자 지시 2026-10-10(재작성) §1-3·§2-3
# ══════════════════════════════════════════════════════════════════


@dp.callback_query()
async def on_button(cb: CallbackQuery) -> None:
    """🔴 카드·후보 버튼 한 곳. ⚠️ **여기서 말을 만들지 않는다**(§17-c) —
    파이프라인이 만든 카드를 그대로 낸다.

    | 버튼 | 무엇 |
    |---|---|
    | `pick` | §1-3 — 후보를 고른다. 🔴 그 열쇠로 **못 박아** 분석한다 |
    | `deep`·`scen`·`market` | 1겹의 뒤쪽(긴 카드) — 마지막 실행을 다시 쓴다 |
    | `again` | 🔄 즉시 한 번 재분석 |
    | `watch`·`unwatch` | §2-3 — **라인업 감시**를 켜고 끈다 |
    """
    from app.bot import keys, pending
    action, arg = keys.unpack(cb.data)
    if not action:
        await cb.answer("🔴 못 알아보는 버튼이다(봇이 다시 켜졌다) — 다시 물어라")
        return
    token = arg.split(":")[0]
    ask = pending.get(token)
    if ask is None:
        await cb.answer("🔴 그 카드를 더는 들고 있지 않다 — 다시 물어라",
                        show_alert=True)
        return
    s = get_settings()
    pool = await get_pool(s.database_url)
    if action == "pick":
        await _on_pick(cb, ask, arg, pool=pool)
        return
    if action in ("watch", "unwatch"):
        await _on_watch(cb, ask, token, on=(action == "watch"), pool=pool)
        return
    if action in ("deep", "scen", "market", "again"):
        await cb.answer("돌린다…")
        body, got = await _v6_card(pool, said=ask.asked, again=True,
                                  deep=(action != "again"), want_ref=True)
        await _send_card(cb.message, body, got, asked=ask.asked,
                         board_text=ask.board_text)
        return
    await cb.answer(f"🔴 아직 안 이은 버튼이다 — `{action}`")


async def _on_pick(cb: CallbackQuery, ask, arg: str, *, pool) -> None:
    """🔴🔴 §1-3 — **후보를 고르면 그 경기로 못 박아** 분석한다.

    > 고르기 전에 분석하지 않는다.

    🔴 못 박는 길은 `pipeline.analyze(pick_key=…)` 다 — 다시 찾으면 또 여럿이
       나와 **같은 자리에서 멈춘다**.
    """
    try:
        i = int(arg.split(":")[1])
    except (IndexError, ValueError):
        await cb.answer("🔴 버튼 번호를 못 읽었다")
        return
    picks = list(ask.picks or [])
    if not 0 <= i < len(picks):
        await cb.answer("🔴 그 후보가 없다 — 다시 물어라")
        return
    box = dict(picks[i])
    key = str(box.get("key") or "")
    await cb.answer(f"{box.get('home')} vs {box.get('away')} — 분석한다")
    said = f"{box.get('home')} vs {box.get('away')}"
    body, got = await _v6_card(pool, said=said, pick_key=key, want_ref=True,
                              board_text=ask.board_text)
    await _send_card(cb.message, body, got, asked=said,
                     board_text=ask.board_text)


async def _on_watch(cb: CallbackQuery, ask, token: str, *, on: bool,
                    pool) -> None:
    """🔴🔴 §2-3 — **라인업 감시**를 켜고 끈다.

    > 사용자가 **누른 경기만** 그 시각부터 5분 간격으로 사다리를 돌고, 확정되면
    > 재분석해서 **원래 메시지를 고쳐 쓴다**. 누르지 않으면 돌지 않는다
    > (자동 분석 아님).
    """
    from app.bot import watch as _watch
    if not on:
        said = _watch.stop(ask)
        await cb.answer(said)
        return
    said = _watch.start(cb.bot, ask, pool=pool, card=lambda: _v6_card(
        pool, said=ask.asked, again=True, want_ref=True))
    await cb.answer(said)


@dp.message(Command("status", "상태"))
async def cmd_status(m: Message) -> None:
    """`/상태` — 🔴 **총평 검열 통과율과 위반 상위 3종**(사용자 지시 2026-10-07 §4-4).

    ⚠️ 운영자용이다 — 카드에는 검열 과정이 나가지 않는다(§4-3).
    """
    from app import auditlog
    from app.core import autoleague
    # 🔴 §1 — 리그 **상한을 걷었다**(사용자 결정 2026-10-10). 그래서 자동 등록
    #    목록이 운영자의 **유일한 눈**이다 — 여기 함께 적는다.
    from app.bot import pending
    # 🔴 §2-3 — *"사용자가 누른 경기만 돈다"* 를 사람이 확인하는 자리다
    await m.answer(auditlog.stats() + "\n\n" + autoleague.report()
                   + "\n\n" + pending.report())


@dp.message(Command("health"))
async def cmd_health(m: Message) -> None:
    from app.version import boot_info, staleness_line
    s = get_settings()
    pool = await get_pool(s.database_url)
    # 🔴 **KST 날짜**다 — `today_kst()` 가 KST 날짜를 주므로 칸도 그렇게 잘라야
    #    짝이 맞는다(종전 `starts_kst::date` 는 세션 시간대로 돌았다).
    n = await pool.fetchval(
        f"SELECT count(*) FROM games WHERE {timefmt.sql_kst_day()} = $1",
        timefmt.today_kst())
    unk = await pool.fetchval(
        "SELECT COALESCE(sum(cardinality(unknowns)), 0) FROM runs "
        "WHERE slate_date = $1", timefmt.today_kst()) or 0
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
