"""[ORD-11 · 2단계] **AI 가 거른다.**

사용자 지시 2026-09-12: "그후 ai에게 정보를 준다.ai가 거른다"

🔴 왜 필요한가. 1단계는 질문 없이 긁으므로 **잡음을 줄이지 않는다** — 설계가
   그렇다. 실측 2026-09-12 수집물: 위성 12건에 어제 경기 결과와 타팀(KIA·한화)
   기사가 섞였고, 퍼플렉시티는 티켓 예매·좌석 번호까지 물어 왔다.
   거르는 단계가 없으면 DSM-1 상태다 — **위성 76건 중 조사 인용 0건.**

🔴 **채택·기각은 번호로만 받는다.** 모델이 문장을 다시 쓰면 그것이 창작이고,
   원문이 바뀌어 카드·감사가 대조할 수 없게 된다. 원문은 우리가 갖고 있다.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DEEPSEARCH_ROLE = "deepsearch"      # 정찰이 쓰던 그 역할. 새 라우팅을 만들지 않는다.

#: [SRCH-3] 검색 질문 상한. 🔴 **원본은 `websearch.MAX_ASKS` 다** — 사용자
#  결정("경기당 1회 질문 3개")을 두 곳에 적지 않는다. 여기서 자르는 이유는
#  프롬프트가 어겨질 수 있기 때문이다(실측: grok 이 날짜 지시를 어겼다).
from app.collectors.websearch import MAX_ASKS  # noqa: E402

#: 한 항목을 프롬프트에 실을 때의 길이 상한.
_ROW_MAX = 260


def number_rows(rows: list[dict]) -> str:
    """수집물을 `번호 · [출처] · 내용` 으로. 번호는 1부터, 목록 순서 그대로."""
    out = []
    for i, r in enumerate(rows, 1):
        src = r.get("소스") or ""
        acct = f" {r.get('계정')}" if r.get("계정") else ""
        when = f"[{r.get('시점')}] " if r.get("시점") else ""
        text = " ".join(str(r.get("답") or "").split())
        if len(text) > _ROW_MAX:
            text = text[:_ROW_MAX] + "…"
        out.append(f"{i}. [{src}{acct}] {when}{text}")
    return "\n".join(out)


def _ints(seq, lo: int, hi: int) -> list[int]:
    """범위 안의 정수만. 🔴 지어낸 번호를 채택으로 받으면 없는 사실이 판정에
    들어간다 — DSM-1 에서 같은 패턴을 겪었다(근거번호 99)."""
    out = []
    for x in seq or []:
        if isinstance(x, bool) or not isinstance(x, int):
            continue
        if lo <= x <= hi and x not in out:
            out.append(x)
    return out


async def run(jg: dict, brief: str, rows: list[dict], *,
              timeout: float | None = None) -> dict | None:
    """② 선별. 반환은 아래 모양, 실패하면 None.

        {"채택": [행...], "기각": [{"행","사유"}...], "갈림길", "변수",
         "없는것", "DB요청", "검색요청", "계측": {"수집","채택","기각","미분류"}}

    ⚠️ **실패는 None 이다.** 여기서 판정을 대신 내리지 않는다 — 호출부(5단계)가
       그때 무엇을 할지 정한다.
    """
    from app.config import get_settings
    from app.engine.deepsearch import _today_kst
    from app.engine.prompts import TRIAGE

    s = get_settings()
    if s.mock_judge or not rows:
        return None
    prompt = TRIAGE.format(
        league=jg.get("league") or (jg.get("sport") or "").upper(),
        away=jg.get("away") or "", home=jg.get("home") or "",
        today=_today_kst(), brief=brief or "(없음)", rows=number_rows(rows))
    from app.llm.judge_route import chain as _chain

    routes = [r for r in _chain(DEEPSEARCH_ROLE) if r[0] != "anthropic"]
    if not routes:
        logger.error("[triage] 후보가 없다 — 선별 생략")
        return None
    import asyncio

    from app.engine.team_form import _complete_free, parse_json_object

    try:
        body = await asyncio.wait_for(
            _complete_free(routes, prompt, int(s.deepsearch_max_tokens),
                           DEEPSEARCH_ROLE),
            timeout=timeout if timeout is not None
            else float(s.deepsearch_timeout_sec))
    except Exception as exc:
        logger.warning("[triage] 실패 %s@%s: %s",
                       jg.get("away"), jg.get("home"), exc)
        return None
    data = parse_json_object(body or "")
    if not isinstance(data, dict):
        logger.warning("[triage] JSON 파싱 실패 %s@%s · %d자: %.300s",
                       jg.get("away"), jg.get("home"), len(body or ""),
                       (body or "").replace("\n", " ")[:300])
        return None

    n = len(rows)
    keep = _ints(data.get("채택"), 1, n)
    drop_raw = [d for d in (data.get("기각") or []) if isinstance(d, dict)]
    drop: list[dict] = []
    for d in drop_raw:
        no = _ints([d.get("번호")], 1, n)
        why = str(d.get("사유") or "").strip()
        # 🔴 사유 없는 기각은 세지 못한다 — 그러면 "거름이 과한가"를 못 묻는다.
        if no and no[0] not in keep and why:
            drop.append({"행": rows[no[0] - 1], "번호": no[0], "사유": why})
    # 🔴 어느 쪽에도 안 들어간 것은 **버리지 않는다.** 모델이 빠뜨린 것을
    #    조용히 기각하면 그게 가장 나쁜 손실이다 — 채택 쪽으로 남긴다.
    named = set(keep) | {d["번호"] for d in drop}
    unseen = [i for i in range(1, n + 1) if i not in named]
    out = {
        "채택": [rows[i - 1] for i in keep] + [rows[i - 1] for i in unseen],
        "기각": drop,
        "갈림길": [b for b in (data.get("갈림길") or []) if isinstance(b, dict)],
        "변수": [str(v).strip() for v in (data.get("변수") or []) if str(v).strip()],
        "없는것": [str(x).strip() for x in (data.get("없는것") or []) if str(x).strip()],
        "DB요청": [str(x).strip() for x in (data.get("DB요청") or []) if str(x).strip()],
        # 🔴 [SRCH-3] 웹에 물을 것. **코드가 자른다** — 유료다.
        "검색요청": [str(x).strip() for x in (data.get("검색요청") or [])
                     if str(x).strip()][:MAX_ASKS],
        "계측": {"수집": n, "채택": len(keep), "기각": len(drop),
                 "미분류": len(unseen)},
    }
    # 🔴 채택 0 은 "재료 없음"이다. 조용히 넘기면 ③이 아는 척 판정한다.
    if not out["채택"]:
        logger.warning("[triage] %s@%s 수집 %d건이 전부 기각됐다 — 재료 없음",
                       jg.get("away"), jg.get("home"), n)
    logger.info("[triage] %s@%s %s · 갈림길 %d · 변수 %d · 없는것 %d · "
                "DB요청 %d · 검색요청 %d",
                jg.get("away"), jg.get("home"), out["계측"],
                len(out["갈림길"]), len(out["변수"]),
                len(out["없는것"]), len(out["DB요청"]), len(out["검색요청"]))
    return out
