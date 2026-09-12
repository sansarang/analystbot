"""[SRCH-2] Anthropic 웹 검색 — 질문을 받아 **오늘 것만** 돌려준다.

사용자 지시 2026-09-12:
  "x seach 삭제....그자리에 안트로픽 서치로" · "퍼플릭스와 안트로픽"
  "경기당 1회 질문 3개로 해라"

🔴 **왜 날짜를 코드가 검사하는가.** 실측 2026-09-12, 게이트 없이 던졌을 때:

     질문   "삼성 구자욱의 최근 결장 사유가 부상인가 컨디션 관리인가"
     답     "좌측 가슴뼈 미세골절 — 2루 슬라이딩 역동작"  (인용까지 붙었다)
     실제   그 부상은 **2026년 4월**이다. 오늘 사유는 "훈련 중 등 담 증세로
            긴급 제외"(2026-09-12) 였고 김헌곤이 9번 좌익수로 들어갔다.

   인용이 붙은 확신 있는 오답은 "수집 실패"보다 나쁘다. 카드가 5개월 전
   부상을 오늘 일로 말하게 된다.

🔴 **프롬프트만으로는 부족하다.** 같은 날 `grok-4.20` 에게 "2026-09-10 이후
   기사만"이라고 적어 주었더니 **9월 8일 기사를 근거일자로 적었고**, 기사가
   아니라 "성격이 강함"이라는 추론으로 답을 채웠다. 지시는 어겨진다.

⚠️ 반대 위험 — **게이트가 멀쩡한 답을 버리면 그게 더 나쁘다.** 그래서 폐기는
   조용하지 않다: 사유별로 세어 돌려주고 로그에 남긴다. 허용 범위 3일은
   **근거가 약하다**(아래 `MAX_AGE_DAYS` 주석). 집계가 쌓이면 조정한다.

⚠️ 캐시를 일부러 만들지 않는다. "오늘 바뀐 것"을 묻는 자리라 캐시가 곧
   오래된 답이다 — 이 모듈이 막으려는 바로 그것이다. 호출 횟수는 부르는
   쪽(SRCH-3)이 경기당 1회로 묶는다.
"""

from __future__ import annotations

import logging
import re
from datetime import date as _date

logger = logging.getLogger(__name__)

#: 이 채널의 행 라벨. 수집 출처 집계에 그대로 쓰인다.
SOURCE = "anthropic"

#: 경기당 질문 수 (사용자 결정 2026-09-12 "경기당 1회 질문 3개로 해라").
#  🔴 **이 상수 하나가 원본이다** — 프롬프트에도 `TOOL` 에도 숫자를 또 적지
#     않는다. `max_uses` 는 API 가 자른다. 프롬프트는 부탁이고 API 는 강제다.
MAX_ASKS = 3

#: 검색 도구. 🔴 실측 2026-09-12로 **기본(`web_search_20250305`)을 고른다** —
#  동적 필터판(`web_search_20260318`)이 더 비싸고 느렸다:
#    20250305   3초 · 입력 13,713 · 출력 114
#    20260318  11초 · 입력 20,024 · 출력 443   ← 코드 실행을 끼워 넣는다
#  규격 출처: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool
TOOL = {"type": "web_search_20250305", "name": "web_search",
        "max_uses": MAX_ASKS}

#: 근거 기사의 허용 나이(일).
#  🔴 **이 값의 근거는 약하다.** "오늘 바뀐 것"을 묻는 자리라 짧아야 한다는
#     것 말고 실측이 없다. 폐기 사유별 집계가 쌓이면 조정한다 —
#     지금 이 값이 정답이라고 주장하지 않는다(영향지도 SRCH-2 ④).
MAX_AGE_DAYS = 3

#: 단가. 🔴 **외부 사실이라 우리 코드에 원본이 없다 — 여기 한 곳에만 적는다.**
#  출처: https://platform.claude.com/docs/en/about-claude/pricing (확인 2026-09-12)
#    Claude Sonnet 5  입력 $2 / MTok · 출력 $10 / MTok
#    web_search       $10 / 1,000 검색
#  ⚠️ 모델을 바꾸면 이 값도 바뀐다. `cost()` 는 sonnet-5 기준이다.
PRICE_IN = 2.0 / 1_000_000
PRICE_OUT = 10.0 / 1_000_000
PRICE_SEARCH = 10.0 / 1_000

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")

#: 질문을 던지는 프롬프트. 🔴 날짜를 **두 번** 박는다 — 오늘과 허용 하한.
#  ⚠️ 질문 수를 여기 적지 않는다. 자르는 것은 코드와 API 다.
ASK = """오늘은 **{today}** 이다. 아래 질문에 웹 검색으로 답하라.

[경기] {league} · {away} (원정) @ {home} (홈) — **아직 시작 전이다.**

[질문]
{questions}

🔴 **근거는 {floor} 이후 기사만 쓴다.** 그보다 오래된 기사는 오늘을 설명하지
   못한다. 실측 2026-09-12: "최근 결장 사유"를 물었더니 **5개월 전** 부상
   기사를 인용해 답한 일이 있었다. 그것이 이 규칙이 있는 이유다.
🔴 **답마다 `근거일자` 를 적는다** — 기사에 적힌 날짜다. 오늘 날짜를 그냥
   옮겨 적지 마라. 기사 날짜를 모르면 그 답은 쓰지 마라.
🔴 **{floor} 이후 기사를 못 찾았으면 `"답": "모름"` 으로 두어라.**
   오래된 기사로 채우지 마라 — 그게 가장 나쁜 답이다. 모른다고 적는 편이
   우리에게 훨씬 쓸모 있다.
🔴 **성적을 가져오지 마라.** 시즌 성적·평균자책점·팀 타율·OPS·통산 전적은
   어느 날에나 같은 값이고 오늘을 설명하지 않는다.
🔴 아직 일어나지 않은 일을 적지 마라. 이 경기는 시작 전이고, 결과·이닝·
   실점은 **존재하지 않는다.**

[출력] 아래 JSON만 출력한다. 다른 텍스트, 마크다운 백틱 금지.
{{"답": [{{"번호": 1, "답": "한 문장", "근거일자": "YYYY-MM-DD",
        "소스유형": "공식|기록|뉴스", "url": "..."}}]}}"""


def _row(answer: str, *, question: str = "", kind: str = "", when: str = "",
         url: str = "") -> dict:
    """수집 행 하나. 🔴 모양의 원본은 `engine.gather._row` 다 — 계약 테스트가
    키 집합을 대조한다. 여기서 임포트하지 않는 것은 collectors 가 engine 을
    거꾸로 당기지 않게 하려는 것이다."""
    return {"질문": question, "답": answer, "소스": SOURCE, "소스유형": kind,
            "시점": when, "계정": "", "url": url}


def cost(*, input_tokens: int, output_tokens: int, searches: int) -> float:
    """이 호출에 든 돈. 🔴 **검색 수만 세면 8할을 놓친다** — 실측 2026-09-12
    입력 31,069 토큰이 비용의 61% 였다(검색 3회는 29%)."""
    return (input_tokens * PRICE_IN + output_tokens * PRICE_OUT
            + searches * PRICE_SEARCH)


def _parse_date(s: str) -> _date:
    m = _DATE_RE.match((s or "").strip())
    if not m:
        raise ValueError(f"날짜가 아니다: {s!r}")
    return _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _floor(today: str, days: int = MAX_AGE_DAYS) -> str:
    """허용 하한(포함). `today - days`."""
    from datetime import timedelta

    return (_parse_date(today) - timedelta(days=days)).isoformat()


def build_prompt(jg: dict, questions: list[str], today: str) -> str:
    """질문을 프롬프트로. 🔴 **코드가 먼저 자른다** — 상한은 `MAX_ASKS`."""
    qs = [str(q).strip() for q in (questions or []) if str(q).strip()][:MAX_ASKS]
    return ASK.format(
        today=today, floor=_floor(today),
        league=jg.get("league") or (jg.get("sport") or "").upper(),
        away=jg.get("away") or "", home=jg.get("home") or "",
        questions="\n".join(f"{i}. {q}" for i, q in enumerate(qs, 1)) or "(없음)")


def parse_answers(text: str, today: str, *,
                  questions: list[str] | None = None,
                  max_age_days: int = MAX_AGE_DAYS) -> tuple[list[dict], dict]:
    """응답을 행으로. **날짜 게이트가 여기 있다.**

    반환 `(행들, 계측)`. 계측은
    `{받음, 채택, 모름, 폐기, 폐기_오래됨, 폐기_날짜없음, 폐기_미래}`.

    🔴 **`모름` 은 폐기가 아니다.** 정직한 답이다 — 폐기로 세면 게이트가
       억울하게 나빠 보이고, "게이트를 넓혀야 하나"를 잘못 묻게 된다.
    🔴 **조용히 버리지 않는다.** 반대 위험(멀쩡한 답 폐기)을 재려면
       사유별 숫자가 있어야 한다.
    """
    from app.engine.team_form import parse_json_object

    m = {"받음": 0, "채택": 0, "모름": 0, "폐기": 0,
         "폐기_오래됨": 0, "폐기_날짜없음": 0, "폐기_미래": 0}
    got = parse_json_object(text or "")
    items = (got or {}).get("답") if isinstance(got, dict) else None
    if not isinstance(items, list):
        # 🔴 200 OK 산문은 데이터가 아니다(저장소 전례: 재료 0인 분석).
        if (text or "").strip():
            logger.warning("[websearch] 응답이 JSON 이 아니다 · %d자 · 머리=%r",
                           len(text), text[:160])
        return [], m

    qs = [str(q).strip() for q in (questions or [])][:MAX_ASKS]
    try:
        today_d = _parse_date(today)
    except ValueError:
        logger.error("[websearch] 오늘 날짜가 잘못됐다: %r — 게이트를 걸 수 없다",
                     today)
        return [], m

    rows: list[dict] = []
    for it in items:
        m["받음"] += 1
        if not isinstance(it, dict):
            m["폐기"] += 1
            m["폐기_날짜없음"] += 1
            continue
        ans = " ".join(str(it.get("답") or "").split())
        if not ans or ans == "모름":
            # 못 찾았다고 적은 것이다. 행은 안 만들되 **폐기도 아니다.**
            m["모름"] += 1
            continue
        try:
            when = _parse_date(str(it.get("근거일자") or ""))
        except ValueError:
            m["폐기"] += 1
            m["폐기_날짜없음"] += 1
            continue
        if when > today_d:
            # 🔴 오늘보다 뒤인 기사는 존재하지 않는다 — 지어낸 것이다.
            m["폐기"] += 1
            m["폐기_미래"] += 1
            continue
        if (today_d - when).days > max_age_days:
            m["폐기"] += 1
            m["폐기_오래됨"] += 1
            continue
        no = it.get("번호")
        # 🔴 지어낸 번호로 엉뚱한 질문에 붙이면 그게 창작이다 — 공란이 낫다.
        q = qs[no - 1] if isinstance(no, int) and 1 <= no <= len(qs) else ""
        rows.append(_row(ans, question=q,
                         kind=str(it.get("소스유형") or "").strip(),
                         when=when.isoformat(),
                         url=str(it.get("url") or "").strip()))
        m["채택"] += 1

    if m["폐기"] or m["모름"]:
        logger.info("[websearch] 받음 %d · 채택 %d · 모름 %d · 폐기 %d "
                    "(오래됨 %d · 날짜없음 %d · 미래 %d)",
                    m["받음"], m["채택"], m["모름"], m["폐기"],
                    m["폐기_오래됨"], m["폐기_날짜없음"], m["폐기_미래"])
    return rows, m


def _enabled(settings) -> bool:
    return bool(getattr(settings, "websearch_enabled", False))


async def _call(prompt: str, settings) -> tuple[str, dict]:
    """Anthropic 1콜. 반환 `(본문, 계측)`.

    ⚠️ **호출 인자를 손으로 적지 않는다.** 원본은 `team_form.message_kwargs`
       다 — SDK 1.0 이 `temperature` 를 뺐고, 샘플링 되는 모델만 `extra_body`
       로 0 을 고정한다. 손으로 적었다가 `TypeError` 로 전건이 죽은 전례가 있다.
    """
    import anthropic

    from app.engine.team_form import message_kwargs

    c = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    kw = message_kwargs(getattr(settings, "websearch_model", "claude-sonnet-5"),
                        2000, prompt)
    kw["tools"] = [dict(TOOL)]
    r = await c.messages.create(**kw)
    text = "".join(getattr(b, "text", "") or "" for b in (r.content or []))
    u = getattr(r, "usage", None)
    n = getattr(getattr(u, "server_tool_use", None), "web_search_requests", 0)
    met = {"입력": int(getattr(u, "input_tokens", 0) or 0),
           "출력": int(getattr(u, "output_tokens", 0) or 0),
           "검색": int(n or 0),
           "stop": getattr(r, "stop_reason", "")}
    return text, met


async def ask(jg: dict, questions: list[str], *, today: str | None = None,
              settings=None) -> list[dict]:
    """질문 → 오늘 것만 담긴 수집 행.

    🔴 **실패해도 빈손으로 돌아온다.** 검색이 안 됐다고 판정을 멈추지 않는다 —
       재료가 줄 뿐이다. "재료 없으면 분석 생성 금지"(절대 규칙 6)의 판단은
       부르는 쪽이 한다.
    """
    from app.config import get_settings

    s = settings or get_settings()
    qs = [str(q).strip() for q in (questions or []) if str(q).strip()][:MAX_ASKS]
    if not qs:
        return []
    if not _enabled(s):
        logger.info("[websearch] 꺼져 있다 — 질문 %d개를 버린다", len(qs))
        return []

    from app.engine.credit_guard import abort_if_credit_gone, trip_credit
    from app.engine.deepsearch import _today_kst

    day = today or _today_kst()
    try:
        abort_if_credit_gone("websearch")
        text, met = await _call(build_prompt(jg, qs, day), s)
    except Exception as exc:
        # 🔴 잔액 없는 키로 계속 부르면 요금만 탄다(CLAUDE.md 규약).
        try:
            trip_credit("websearch", exc)
        except Exception:
            pass
        logger.warning("[websearch] %s@%s 호출 실패 — 빈손으로 계속한다: %s",
                       jg.get("away"), jg.get("home"), str(exc)[:160])
        return []

    rows, m = parse_answers(text, day, questions=qs)
    # 🔴 **비용을 매 호출 남긴다.** x_search 가 호출당 $0.413 을 태우는 동안
    #    이 줄이 없어서 아무도 몰랐다(실측 2026-09-12).
    logger.info("[websearch] %s@%s 질문 %d · 입력 %d · 출력 %d · 검색 %d · "
                "$%.4f · 채택 %d/%d (모름 %d · 폐기 %d) · stop=%s",
                jg.get("away"), jg.get("home"), len(qs),
                met["입력"], met["출력"], met["검색"],
                cost(input_tokens=met["입력"], output_tokens=met["출력"],
                     searches=met["검색"]),
                m["채택"], m["받음"], m["모름"], m["폐기"], met["stop"])
    return rows
