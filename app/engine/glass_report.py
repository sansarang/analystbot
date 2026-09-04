"""[투명 리포트 G2] 경기당 5절 문서 — 사람이 코드를 안 보고 판별하게.

🔴 **템플릿 채우기다. LLM 을 부르지 않는다.** 리포트가 재서술하면 그것이
   제2의 환각 경로가 된다 — 카드가 틀렸는지 보려고 읽는 문서가 스스로
   새 주장을 하면 검증 도구가 아니라 검증 대상이 하나 더 느는 것이다.
🔴 **재계산하지 않는다.** 확률·괴리·적중은 전부 원장(`pick_ledger`·
   `market_baseline_ledger`·`variable_ledger`·`judgement_audit`·`game_trace`)
   에 이미 있는 값을 **읽어서 옮긴다.** 여기서 다시 계산하면 카드와 다른
   숫자가 나올 수 있고, 그때 어느 쪽이 맞는지 아무도 모른다.
🔴 **없는 것은 "없음 + 사유"다.** 있는 척하지 않는다 — 빈 칸을 그럴듯하게
   메우는 순간 이 문서의 목적이 사라진다.

5절 구성 (지시서 고정):
  ① 무엇을 수집했나 — 재료 명세
  ② 무엇을 조사했나 — 딥서치
  ③ 어떻게 결론냈나 — 판정 해부 (근거 → 재료 역참조)
  ④ 시장과 어떻게 달랐나
  ⑤ 결과와 복기
"""
from __future__ import annotations

import json
import logging
import re
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

NONE_MARK = "없음"

#: 근거가 어느 자료를 가리키는지 찾는다. 판정 프롬프트가 "자료 번호를 명시하라"
#  고 요구하므로 근거 문자열 안에 번호가 들어온다.
_REF_RE = re.compile(r"자료\s*(\d{1,2})")


def refs_in(text: str) -> list[int]:
    """근거 1줄이 가리키는 자료 번호들. 없으면 빈 목록."""
    return sorted({int(m) for m in _REF_RE.findall(text or "")})


def _fmt(v, dash: str = "—") -> str:
    """표시용. **값을 바꾸지 않는다** — 자릿수만 다듬는다.

    ⚠️ 확률(0.580)과 배당(1.95)·괴리(6.8%p)는 자릿수 관습이 다르다.
       전부 소수 3자리로 찍으면 `괴리 6.800%p` 같은 읽기 나쁜 줄이 나온다.
       확률만 3자리로 고정하고 나머지는 뒤 0 을 턴다.
    """
    if v is None or v == "":
        return dash
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        if 0.0 <= v <= 1.0:
            return f"{v:.3f}"                    # 확률
        return f"{v:.2f}".rstrip("0").rstrip(".")
    try:                                          # NUMERIC 은 Decimal 로 온다
        from decimal import Decimal

        if isinstance(v, Decimal):
            return f"{float(v):.2f}".rstrip("0").rstrip(".")
    except Exception:
        pass
    return str(v)


#: 표시 시간대. 🔴 **시차를 상수로 박지 않는다** — DST 가 있으면 반드시 틀리고,
#  KST 는 DST 가 없더라도 같은 코드를 다른 리그에 복사하는 순간 틀린다.
#  (기존 `test_no_hardcoded_interleague_offsets` 가 이 실수를 잡았다)
_KST = ZoneInfo("Asia/Seoul")


def _kst(ts) -> str:
    """표시용 KST. DB 는 UTC 저장이고 변환은 표시 계층에서만 한다(절대 규칙 4)."""
    if ts is None:
        return "—"
    try:
        return ts.astimezone(_KST).strftime("%m-%d %H:%M")
    except Exception:
        return str(ts)[:16]


# ─────────────────────────── ① 재료 ───────────────────────────

#: 자료 번호 → (이름, `jg["research"]` 에서 찾을 키 접미사)
#  ⚠️ 폐지된 7·8 은 **목록에 남긴다.** 빠지면 "왜 없지?"를 매번 다시 묻는다.
MATERIALS: tuple[tuple[int, str, str], ...] = (
    (1, "3경기 박스스코어", "usage"),
    (2, "72h 뉴스태그", "news"),
    (3, "오늘 확정 라인업", "lineup"),
    (4, "선발 최근 등판", "starter_recent"),
    (5, "직전 판정", ""),
    (6, "라인업 의도(해석)", "intent"),
    (7, "선발 시즌 라인", ""),
    (8, "타선 시즌 타격", ""),
    (9, "불펜 최근 폼", "bullpen"),
    (10, "변수 참조", ""),
    (11, "이동·연전·날씨", ""),
)

#: 폐지 사유 — 리포트가 "왜 비었나"에 스스로 답한다.
RETIRED = {7: "폐지 2026-09-04 (대원칙: 시즌 누적은 판정 입력이 아니다)",
           8: "폐지 2026-09-04 (대원칙: 시즌 누적은 판정 입력이 아니다)"}


def section_materials(jg: dict, trace: list[dict]) -> str:
    r = jg.get("research") or {}
    rows = ["| 자료 | 이름 | 상태 | 요약 |", "|---|---|---|---|"]
    for num, name, key in MATERIALS:
        if num in RETIRED:
            rows.append(f"| {num} | {name} | — | {RETIRED[num]} |")
            continue
        if num == 5:
            prev = (jg.get("matchup") or {}).get("직전대비")
            rows.append(f"| 5 | {name} | {'있음' if prev else NONE_MARK} | "
                        f"{_fmt(json.dumps(prev, ensure_ascii=False) if prev else None, '최초 판정')} |")
            continue
        if num == 10:
            st = jg.get("material10_status") or "해당없음"
            rows.append(f"| 10 | {name} | {st} | "
                        f"{_summarize(jg.get('material10'))} |")
            continue
        if num == 11:
            st = jg.get("material11_status") or "해당없음"
            rows.append(f"| 11 | {name} | {st} | "
                        f"{_summarize(jg.get('material11'))} |")
            continue
        got = {s: r.get(f"{s}_{key}") for s in ("home", "away")} if key else {}
        have = any(bool(v) for v in got.values())
        rows.append(f"| {num} | {name} | {'있음' if have else NONE_MARK} | "
                    f"{_summarize(got) if have else '수집 실패 또는 미공시'} |")
    # 원장이 본 조립 시각 — 리포트가 지어내지 않고 원장에서 읽는다
    asm = [t for t in trace if t["stage"] == "조립"]
    when = _kst(asm[0]["at"]) if asm else "—"
    return ("## ① 무엇을 수집했나\n\n"
            f"조립 시각(원장): {when}\n\n" + "\n".join(rows) + "\n")


def _summarize(v, limit: int = 90) -> str:
    if not v:
        return NONE_MARK
    try:
        s = json.dumps(v, ensure_ascii=False, default=str)
    except Exception:
        s = str(v)
    s = s.replace("\n", " ")
    return (s[:limit] + "…") if len(s) > limit else s


# ─────────────────────────── ② 딥서치 ───────────────────────────

def section_deepsearch(trace: list[dict]) -> str:
    rows = [t for t in trace if t["stage"] == "딥서치"]
    if not rows:
        return ("## ② 무엇을 조사했나\n\n"
                "원장에 딥서치 행이 없다 — **호출 자체가 없었다.**\n"
                "(트리거 판별도 안 돌았다는 뜻이다. '미발동'과 다르다.)\n")
    out = ["## ② 무엇을 조사했나\n"]
    for t in rows:
        ref = t.get("ref") or {}
        out.append(f"- {_kst(t['at'])} `{t['summary']}`")
        if not ref.get("triggered"):
            out.append(f"  - **미발동** — 트리거 판별값: "
                       f"{_summarize(ref, 200)}")
        else:
            out.append(f"  - 트리거 {','.join(ref.get('triggers') or [])} · "
                       f"source={ref.get('source')} · status={ref.get('status')}")
            out.append(f"  - 검색 {ref.get('searches')}회 · "
                       f"판정 이동 {ref.get('moved_pp')}%p")
    return "\n".join(out) + "\n"


# ─────────────────────────── ③ 판정 해부 ───────────────────────────

def section_verdict(jg: dict, audit: dict | None,
                    variables: list[dict]) -> tuple[str, int]:
    """판정 해부. 반환 (본문, 역참조 실패 건수).

    🔴 역참조 실패(근거가 자료 번호를 안 가리킴)는 **환각 후보**다 —
       G3 가 이 숫자로 `W-TRACE` 를 울린다.
    """
    m = jg.get("matchup") or {}
    lines = ["## ③ 어떻게 결론냈나\n",
             f"- **p_home** {_fmt(jg.get('p_claude'))} · 우세 {_fmt(m.get('우세'))}"
             f" · 확신도 {_fmt(m.get('확신도'))} · 모델 `{_fmt(m.get('model'))}`\n",
             "### 근거\n"]
    unresolved = 0
    for i, g in enumerate(m.get("근거") or [], 1):
        nums = refs_in(str(g))
        if nums:
            tag = " · ".join(f"[→ ①의 자료{n}]" for n in nums)
        else:
            tag = "🔴 **역참조 실패 — 어느 자료인지 밝히지 않았다**"
            unresolved += 1
        lines.append(f"{i}. {g}\n   - {tag}")
    if not (m.get("근거") or []):
        lines.append(f"{NONE_MARK} — 판정이 근거를 내지 않았다.")
    lines.append("\n### 변수\n")
    if variables:
        lines.append("| 원문 | 방향 | N%p | 기반영 M%p | 근거 | 현실화 |")
        lines.append("|---|---|---|---|---|---|")
        for v in variables:
            lines.append(f"| {v.get('raw','')[:70]} | {_fmt(v.get('direction'))} "
                         f"| {_fmt(v.get('claimed_n'))} | {_fmt(v.get('claimed_m'))} "
                         f"| {_fmt(v.get('source_ref'))} | {_fmt(v.get('realized'), '미채점')} |")
    else:
        lines.append(f"{NONE_MARK} — 변수 원장에 이 경기 행이 없다.")
    lines.append("\n### L1 사실 대조\n")
    if audit:
        lines.append(f"- 확인 {audit.get('verified_n')} · 도출 {audit.get('derived_n')}"
                     f" · 미발견 {audit.get('not_found_n')} · **불일치 "
                     f"{audit.get('mismatch_n')}**")
        for d in (audit.get("mismatch_detail") or [])[:5]:
            lines.append(f"  - 🔴 {_summarize(d, 160)}")
    else:
        lines.append(f"{NONE_MARK} — 감사 기록이 없다(감시 휴면 또는 미실행).")
    return "\n".join(lines) + "\n", unresolved


# ─────────────────────────── ④ 시장 ───────────────────────────

def section_market(ledger: dict | None, market: dict | None,
                   trace: list[dict]) -> str:
    lines = ["## ④ 시장과 어떻게 달랐나\n"]
    gate = [t for t in trace if t["stage"] == "게이트"]
    if ledger:
        lines.append(f"- 배당 {_fmt(ledger.get('odds'))} · 시장확률 "
                     f"{_fmt(ledger.get('market_prob'))} · 괴리 "
                     f"{_fmt(ledger.get('divergence_pp'))}%p · 엣지 "
                     f"{_fmt(ledger.get('edge_status'))}")
        lines.append(f"- 게이트 결과: **{_fmt(ledger.get('gate_result'))}**")
    else:
        lines.append(f"{NONE_MARK} — 픽 원장에 이 경기 행이 없다.")
    if market:
        lines.append(f"- 시장 기준선(발송 시점): p_market "
                     f"{_fmt(market.get('p_market_send'))} · 스냅샷 "
                     f"{_kst(market.get('captured_at'))}")
    if gate:
        lines.append(f"- 원장 게이트 줄: `{gate[-1]['summary']}`")
    return "\n".join(lines) + "\n"


# ─────────────────────────── ⑤ 복기 ───────────────────────────

def cause_class(ledger: dict | None, audit: dict | None,
                materials_missing: bool) -> str:
    """빗나감 원인 분류. **판단하지 않고 규칙으로 라벨만 붙인다.**

      (a) 재료 부족   — 자료가 비어 있었다
      (b) 사실 오류   — L1 불일치가 있었다
      (c) 판단 오류   — 재료도 사실도 멀쩡한데 틀렸다
    ⚠️ 적중했거나 미채점이면 분류하지 않는다 — 사후 서사를 만들지 않는다.
    """
    if not ledger or ledger.get("hit") is None:
        return "미채점"
    if ledger.get("hit"):
        return "적중 — 분류 없음"
    if materials_missing:
        return "(a) 재료 부족"
    if (audit or {}).get("mismatch_n"):
        return "(b) 사실 오류 — L1 불일치"
    return "(c) 판단 오류"


def section_result(ledger: dict | None, audit: dict | None,
                   variables: list[dict], materials_missing: bool) -> str:
    lines = ["## ⑤ 결과와 복기\n"]
    if not ledger:
        return "\n".join(lines + [f"{NONE_MARK} — 픽 원장 행이 없다."]) + "\n"
    lines.append(f"- 최종 스코어 {_fmt(ledger.get('final_score'))} · 승자 "
                 f"{_fmt(ledger.get('winner'))} · 적중 "
                 f"{_fmt(ledger.get('hit'), '미채점')}")
    lines.append(f"- 원인 분류: **{cause_class(ledger, audit, materials_missing)}**")
    real = [v for v in variables if v.get("realized")]
    if real:
        for v in real:
            lines.append(f"  - 변수 현실화 `{v.get('realized')}` — "
                         f"{v.get('raw','')[:60]} (실측 {_summarize(v.get('actual'), 60)})")
    else:
        lines.append(f"  - 변수 현실화: {NONE_MARK} (미채점 또는 임계 미명시)")
    lines.append(f"- 재료에 있었나: "
                 f"{'아니오 — 비어 있던 자료가 있다' if materials_missing else '예 — 자료는 갖춰져 있었다'}")
    return "\n".join(lines) + "\n"


# ─────────────────────────── 조립 ───────────────────────────

def build(jg: dict, *, trace: list[dict], ledger: dict | None,
          audit: dict | None, variables: list[dict],
          market: dict | None = None) -> tuple[str, dict]:
    """5절 문서 전문 + 계측. **LLM 을 부르지 않는다.**

    반환 `(markdown, {"unresolved": n, "mismatch": m})`.
    `unresolved` 는 근거가 자료 번호를 못 가리킨 수 — 환각 후보이고,
    G3 가 이 숫자로 `W-TRACE` 를 울린다.
    """
    r = jg.get("research") or {}
    missing = not all(
        any((r.get(f"{s}_{k}") for s in ("home", "away")))
        for k in ("usage", "starter_recent"))
    verdict_md, unresolved = section_verdict(jg, audit, variables)
    head = (f"# {(jg.get('sport') or '').upper()} "
            f"{jg.get('away')} @ {jg.get('home')}\n\n"
            f"- 경기 ID `{jg.get('game_id')}` · 슬레이트 {jg.get('date') or ''}\n"
            f"- 이 문서는 **원장·로그의 원문 발췌**다. 생성 과정에 LLM 호출이 없다.\n")
    body = "\n".join([
        head,
        section_materials(jg, trace),
        section_deepsearch(trace),
        verdict_md,
        section_market(ledger, market, trace),
        section_result(ledger, audit, variables, missing),
        _timeline_md(trace),
    ])
    return body, {"unresolved": unresolved,
                  "mismatch": int((audit or {}).get("mismatch_n") or 0)}


def _timeline_md(trace: list[dict]) -> str:
    """부록 — 원장 원문. 위 다섯 절이 여기서만 나왔음을 보이는 자리다."""
    if not trace:
        return ("## 부록 · 원장\n\n"
                f"{NONE_MARK} — 이 경기의 `game_trace` 행이 없다.\n")
    out = ["## 부록 · 원장 (원문)\n", "| 시각(KST) | 단계 | 로그 원문 |",
           "|---|---|---|"]
    for t in trace:
        out.append(f"| {_kst(t['at'])} | {t['stage']} | `{t['summary']}` |")
    return "\n".join(out) + "\n"


def filename(jg: dict) -> str:
    """`KBO_두산_LG.md` — 슬래시·공백을 파일명에서 없앤다."""
    def _s(x):
        return re.sub(r"[^0-9A-Za-z가-힣]+", "", str(x or ""))[:20] or "미상"

    return f"{(jg.get('sport') or 'x').upper()}_{_s(jg.get('away'))}_{_s(jg.get('home'))}.md"


# ─────────────────────────── DB 로더 ───────────────────────────

async def load_sources(pool, game_id) -> dict:
    """리포트가 읽을 원장들. **재계산 없음** — 있는 행을 그대로 가져온다."""
    from app.engine.game_trace import timeline

    out: dict = {"trace": [], "ledger": None, "audit": None, "variables": [],
                 "market": None}
    if pool is None or game_id is None:
        return out
    out["trace"] = await timeline(pool, game_id)
    gid = int(game_id)
    for key, sql in (
        ("ledger", "SELECT * FROM pick_ledger WHERE game_id=$1"
                   " ORDER BY is_final DESC, id DESC LIMIT 1"),
        ("audit", "SELECT * FROM judgement_audit WHERE game_id=$1"
                  " ORDER BY id DESC LIMIT 1"),
        ("market", "SELECT * FROM market_baseline_ledger WHERE game_id=$1"
                   " ORDER BY id DESC LIMIT 1"),
    ):
        try:
            row = await pool.fetchrow(sql, gid)
            out[key] = dict(row) if row else None
        except Exception as exc:
            logger.debug("[glass] %s 조회 실패 game=%s: %s", key, game_id, exc)
    try:
        rows = await pool.fetch(
            "SELECT * FROM variable_ledger WHERE game_id=$1 ORDER BY id", gid)
        out["variables"] = [dict(r) for r in rows]
    except Exception as exc:
        logger.debug("[glass] 변수 조회 실패 game=%s: %s", game_id, exc)
    for k in ("audit",):
        blk = out.get(k)
        if blk and isinstance(blk.get("mismatch_detail"), str):
            try:
                blk["mismatch_detail"] = json.loads(blk["mismatch_detail"])
            except ValueError:
                blk["mismatch_detail"] = []
    return out
