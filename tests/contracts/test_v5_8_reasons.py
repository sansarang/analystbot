"""🔴🔴 **v5 §8-6 — 사유 코드.** *"실패한 조건이 돌려주는 enum 이다."*

§8-6 원문:

> 실패  사유는  사람이  쓰는  문자열이  아니라  **실패한 조건이 돌려주는 enum** 이다.
> 목록: query_too_bare, duplicate_query, … out_of_window.
> **사유를 추정해서 적는 코드는 계약 실패**("날짜 창"이라 적었는데 실제는 이름
> 문제였던 사례). [#28]

══════════════════════════════════════════════════════════════════
🔴 목록을 **문서에서 자라게** 한다
══════════════════════════════════════════════════════════════════

⚠️ 손으로 지키는 목록은 언제나 한 발 늦는다(CLAUDE.md #1). 그래서 이 계약은
   `docs/fable/archive/2026-10-04_v5_solar.md` 의 §8-6 줄을 **읽어** 코드와 대조한다.
🔴 문서가 사유를 하나 더하면 **이 계약이 먼저 빨개진다.**

🔴 **§10-4 M38** — 거짓 사유(10-03) — 사유 enum · 추정 문자열 금지
   ⚠️ 이 계약이 그 줄을 집행한다(`tests/test_contract_coverage.py` 가 번호로 대조한다).
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
V5 = ROOT / "docs" / "fable" / "archive" / "2026-10-04_v5_solar.md"

#: 🔴 §8-6 목록이 적힌 자리를 **글자로** 찾는다. ⚠️ 쪽 번호로 찾지 않는다 —
#   PDF 를 다시 뽑으면 줄 번호가 바뀐다.
_ANCHOR = "query_too_bare, duplicate_query"


def _doc() -> str:
    """🔴 문서 전문. ⚠️ 조항 번호를 찾을 때 쓴다(쪽 머리글은 그대로 둔다)."""
    return V5.read_text(encoding="utf-8")


def declared_reasons() -> set[str]:
    """🔴 문서 §8-6 이 적은 사유 코드 집합."""
    text = V5.read_text(encoding="utf-8")
    i = text.index(_ANCHOR)
    # ⚠️ 목록이 **쪽 경계를 넘는다** — PDF 13쪽 끝에서 끊기고 14쪽에서 이어진다
    #    (실측: `scenario_incomplete,` 뒤에 쪽 머리글이 끼어 19개만 잡혔다).
    #    🔴 그래서 쪽 머리글·구분선·쪽 번호를 **지운 뒤** 읽는다.
    seg = text[i:i + 1200]
    for junk in ("AnalystBot v5 전환  지시문  — DeepSeek 에이전트  + 코드  검증층",
                 "---", "## PDF Page"):
        seg = seg.replace(junk, " ")
    seg = re.sub(r"Page \d+ of \d+", " ", seg)
    # 🔴 목록은 `out_of_window .` 에서 끝난다(문서가 그 뒤에 `[#28]` 을 적는다)
    end = seg.find("out_of_window")
    if end >= 0:
        seg = seg[:end + len("out_of_window")]
    # ⚠️ **숫자가 들어간 코드가 있다** — `h2h_zeroed`. `[a-z_]` 만 받으면 빠진다
    #    (실측 2026-10-04: 그 하나가 조용히 사라져 24/25 였다).
    got = set(re.findall(r"\b([a-z][a-z0-9_]{3,})\b", seg))
    # ⚠️ 설명 낱말이 섞이지 않게 — `_` 가 있거나 알려진 한 낱말 코드만 받는다
    one_word = {"conflict", "insufficient"}
    return {g for g in got if "_" in g or g in one_word}


def test_v5_8_6_문서가_사유_목록을_들고_있다():
    """🔴 이 계약이 기댈 원본이 사라지면 **여기서** 멈춘다."""
    got = declared_reasons()
    assert len(got) >= 20, sorted(got)
    for must in ("query_too_bare", "out_of_window", "budget_cut",
                 "quote_not_found", "side_mismatch"):
        assert must in got, (must, sorted(got))


def test_v5_8_6_코드_enum이_문서와_같다():
    """🔴🔴 §8-6 목록 전부가 코드 enum 에 있어야 한다.

    ⚠️ 지금 `matchref.Reason` 은 **일곱**뿐이다(입구 전용). §8-6 은 검색·검증·
       판정·예산까지 **전 구간**의 사유를 하나의 표로 요구한다.
    """
    from app.reasons import Reason
    have = {r.value for r in Reason}
    missing = sorted(declared_reasons() - have)
    assert not missing, f"🔴 문서에 있는데 코드에 없는 사유: {missing}"


def test_v5_8_6_enum_밖_사유가_없다_M38():
    """🔴 코드가 문서에 없는 사유를 **지어내지 않았나.**

    ⚠️ 입구 전용 사유(`ok`·`no_query`·`match_not_found`·`not_collected`·
       `ambiguous`)는 v4 §17-g-3 에서 왔고 §8-6 이 지우지 않았다 — 그 다섯만
       예외로 **이름을 적어** 둔다(조용히 늘지 않게).
    """
    from app.reasons import Reason
    from_v4 = {"ok", "no_query", "match_not_found", "not_collected",
               "ambiguous"}
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **조항이 요구하는데 이름을 안 준 사유** — 여기 **§ 참조와 함께**
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ §7-3 은 *"스코어·경과 분 없이 재판정 금지"* 처럼 **거절을 요구**하면서
    #     사유 코드 이름은 주지 않았다. 🔴 사유 없이 거절하면 카드가 *"왜 안
    #     했는지"* 를 못 적는다(#3 조용한 0 금지).
    #  🔴 그래서 **이름을 여기 적는다** — 조용히 늘지 않게. 각 줄은 **그것을
    #     요구한 조항**을 달아야 한다(그 조항이 없으면 지어낸 사유다).
    ours = {
        "live_no_input": "§7-3 — 스코어·경과 분 없이 재판정 금지",
        "live_weak_metric": "§7-3 — 지표 2개 이상이 같은 메커니즘일 때만 · 15분 간격",
        "live_new_market": "§7-3 — 라이브로 새 마켓을 만들지 않는다",
        # 🔴 **§3-8 모델 인터페이스**(작업 지시서 §1 · M47·M48). ⚠️ 그 문서가
        #    사유 **이름까지** 줬다 — 지어낸 것이 아니다.
        "done_parse_fail": "§3-8 — `done` 추출 2회 실패(M47)",
        "name_not_key": "§3-8 — `team` 이 이름이면 폐기(M48)",
        # 🔴 **v5-A** — 부록 §4-6 이 **이름까지** 준 여섯이다(지어낸 것이 아니다)
        "unknown_var": "§4-6 — DeepSeek 시나리오 폐기(M41)",
        "new_fact": "§4-6 — DeepSeek 가 사실을 지어냄(M41)",
        "redteam_skipped": "§4-6 — 반증 단계 건너뜀",
        "redteam_overruled": "§4-6 — 필수형이 걸리는데 impossible(M46)",
        "deepseek_unavailable": "§4-6 — DeepSeek 장애(M45)",
        "deepseek_missed_required": "§4-6 — 필수형 누락",
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **사용자 결정이 신설한 사유** (2026-10-04)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 이 사유는 v5 본문·작업 지시서 어디에도 없다 — **사용자 결정 ③**이
        #     만들었다(*"에이전트가 켜져 있으면 세포는 검색하지 않고 커버리지
        #     기록만 한다"*). 🔴 그 결정은 `docs/fable/decisions/` 에 원문으로
        #     남아 있고, **그 폴더가 그 조항의 원본**이다.
        #  🔴 지어낸 사유와 가르는 기준은 여전히 같다 — **파일에 있어야 한다**
        #     (v4 §11-1: *"파일에 없는 지시는 인용하지 않는다"*).
        "cell_search_off": "결정 ③ — 세포는 장부다(2026-10-04)",
        # 🔴 지시서(오픈월드) §1-1 이 신설했다 — *"본문 부재"* 와 *"인용 부재"* 는
        #    고칠 곳이 다르다(§8-6). ⚠️ 그 문서는 `inbox/` 에 파일로 있다.
        "body_missing": "§1-1 — 본문을 못 받았다(오픈월드 지시서 2026-10-05)",
        # 🔴 지시서 §2 ⑥-3 이 **이름을 댔다**: *"0개면 `openworld_not_found` 와
        #    시도한 검색어·URL 목록을 카드에 적는다."*
        "openworld_not_found": "§2 — 공개 페이지에서도 못 찾았다(오픈월드 §2)",
        # 🔴 사용자 지시 2026-10-05 — *"세포를 장부로 되살린다 … 네 유형이
        #    `not_tried` 면 `done` 을 거부한다"* · *"카탈로그를 에이전트에 잇는다"*
        # 🔴 **승계** — `checklist_left`(done 거부 루프의 사유)를 지웠다.
        #    커버리지 보장이 **거부에서 분할로** 이동했다(딥서치 재구축 §2
        #    하위 과제 8개). 커버리지 계약은 **M59 와 장부 `found` 배선**이
        #    승계한다(지시서 §7 의 "지우는 계약마다 승계 번호를 적는다").
        "type_off_catalog": "§3-4 — 카탈로그 밖 유형(지시 2026-10-05)",
        # 🔴 사용자 지시 2026-10-05 나-③ — *"**DeepSeek 시나리오 0개 = 실패**"*.
        #    ⚠️ v5-A §4-6 의 `deepseek_unavailable`(장애)과 **다르다**: 모델이
        #       **돌았는데 0개**를 냈다 — 고칠 곳이 프롬프트지 통신이 아니다.
        "deepseek_no_scenario": "결정 나-③ — 시나리오 0개는 실패(2026-10-05)",
        # 🔴 사용자 지시 2026-10-05 다-③ — *"킥오프가 지난 경기는 등급을 내지
        #    않는다"*. ⚠️ 고칠 곳이 **없는** 사유다(때가 지났을 뿐이다).
        "kickoff_passed": "결정 다-③ — 시작한 경기는 등급 없음(2026-10-05)",
        # 🔴 사용자 지시 2026-10-05 라 — *"어느 하나 놓치지 말고 정직하게 보고"*.
        #    ⚠️ 실측에서 한 팀 에이전트가 터졌는데 **깔때기가 그것을 숨겼다**.
        "agent_crashed": "결정 라-⑭ — 에이전트 전멸을 깔때기에 남긴다(2026-10-05)",
        # 🔴 딥서치 재구축 §4-3(M61) — *"10단어 초과 → `query_too_long` 거부.
        #    실측: 긴 문장 질의가 0건을 만들었다."* ⚠️ 그 문서가 **이름까지** 줬다.
        "query_too_long": "§4-3 — 10낱말 초과(딥서치 재구축 M61 · 2026-10-05)",
        # 🔴🔴 **전송 사유 셋** — 북아일랜드–조지아 지시서 §3 (2026-10-06 · M136).
        #    ⚠️ 그 문서가 **이름까지** 줬다: *"사유 분리 유지:
        #       `llm_timeout`·`llm_http_5xx`·`llm_429`·`budget_cut` 은 서로 다른
        #       사유다."*
        "llm_timeout": "§3 — 전송 실패 사유 분리(2026-10-06 · M136)",
        "llm_http_5xx": "§3 — 전송 실패 사유 분리(2026-10-06 · M136)",
        "llm_429": "§3 — 전송 실패 사유 분리(2026-10-06 · M136)",
        # 🔴🔴 **결장 귀속**(사용자 지시 2026-10-07) — 그 글이 세 사유를 **이름으로**
        #    요구한다: 고친 것(`team_reattached`)·못 가린 것(`team_unresolved`)·
        #    동명이인(`team_ambiguous`).
        "team_reattached": "§결장-귀속-2 — 선수 → 팀 대조(2026-10-07)",
        "team_unresolved": "§결장-귀속-2 — 선수 → 팀 대조(2026-10-07)",
        "team_ambiguous": "§결장-귀속-2 — 선수 → 팀 대조(2026-10-07)",
    }
    # 🔴 그 조항이 **v5 본문 또는 작업 지시서**에 있어야 한다. ⚠️ §3-8 은
    #    작업 지시서 §1 이 **신설**한 절이다(v5 본문에는 없다).
    import pathlib as _pl
    base = _pl.Path(__file__).resolve().parents[2] / "docs" / "fable" / "archive"
    doc = _doc()
    for extra in ("2026-10-04_workorder_gate2_deepseek.md",
                  "2026-10-04_v5A_deepseek.md",
                  # 🔴 북아일랜드–조지아 결함 전체 수정(§0: 이 문서가 이긴다)
                  "2026-10-06_workorder_nir_geo_fixes.md"):
        doc += (base / extra).read_text(encoding="utf-8")
    # 🔴 **오늘 받은 지시서도 원본이다** — `inbox/` 에 글자로 들어온 것만 본다(§11-1)
    for extra in ("2026-10-07_absence_team_attribution.md",):
        got = base.parent / "inbox" / extra
        assert got.exists(), f"🔴 지시서가 없다: {got}"
        doc += got.read_text(encoding="utf-8")
    # 🔴 **사용자 결정도 원본이다** — 대화로만 아는 지시는 인용하지 않는다(§11-1)
    dec = base.parent / "decisions"
    for f in sorted(dec.glob("*.md")) if dec.exists() else []:
        doc += f.read_text(encoding="utf-8")
    flat = doc.replace("-", "").replace(" ", "")
    for value, where in ours.items():
        sec = where.split(" ")[0].lstrip("§")
        # ⚠️ *"결정"* 으로 시작하는 것은 조항 번호가 아니라 **결정 번호**다
        if sec.startswith("결정"):
            assert "결정" in flat and "③" in doc, (
                f"🔴 `{value}` 가 기댄 **사용자 결정**을 `decisions/` 에서 "
                f"못 찾았다 — 대화로만 아는 지시는 인용하지 않는다(§11-1)")
            continue
        assert sec.replace("-", "") in flat, (
            f"🔴 `{value}` 가 기댄 조항 `{where}` 를 문서에서 못 찾았다 — "
            f"그러면 **지어낸 사유**다")
    extra = sorted({r.value for r in Reason} - declared_reasons() - from_v4
                   - set(ours))
    assert not extra, f"🔴 문서에도 v4 에도 없는 사유: {extra}"


def test_v5_8_6_사유마다_사람이_읽을_줄이_있다():
    """🔴 enum 은 기계 것이고 카드에는 사람이 읽을 줄이 가야 한다.

    ⚠️ 그 줄을 **호출부가 짓게** 두면 같은 사유가 자리마다 다른 말로 적힌다 —
       그것이 §8-6 이 막으려는 *"추정해서 적는"* 것이다.
    """
    from app.reasons import SAY, Reason
    # ⚠️ `OK` 는 **실패가 아니다** — 실패 사유 표에 들어가지 않는다.
    #    🔴 v4 계약(`tests/test_reason.py`)도 그것을 전제한다.
    missing = [r.value for r in Reason
               if r is not Reason.OK and not str(SAY.get(r) or "").strip()]
    assert not missing, f"🔴 설명이 없는 사유: {missing}"
    # 🔴 그리고 **표가 거짓말하지 않는다** — `bug` 는 *"다시 물어도 같다"* 를 적는다
    for r, text in SAY.items():
        if r.is_our_bug:
            assert "다시 물어도 같다" in text, (r.value, text)


def test_v5_8_6_사유는_고칠_곳을_가리킨다():
    """🔴 §8-6 의 뜻은 *"어디를 고쳐야 하나"* 다 — 그 칸이 있어야 한다.

    ⚠️ 실측 2026-10-03: *"창 밖"*(`out_of_window`)이라 적었는데 실제는 **이름
       문제**였다. 사용자가 두 번 헛돌았다. 🔴 그 둘은 고칠 곳이 완전히 다르다 —
       수집 vs 이름표.
    """
    from app.reasons import Reason
    for r in Reason:
        # 🔴🔴 **어휘는 `reasons.WHERE` 하나다**(#1 사본 금지).
        #    ⚠️ 종전엔 여기 손으로 베껴 뒀다 — 지시서 2026-10-06 §3 가 `망`·
        #       `서버`·`속도` 를 더하자 이 계약이 **한 발 늦었다.**
        from app.reasons import WHERE
        assert r.fix_where in WHERE, (r.value, r.fix_where, WHERE)
    # 🔴 그 실사고의 두 사유가 **다른 곳**을 가리켜야 한다
    assert Reason.OUT_OF_WINDOW.fix_where != Reason.NAME_UNRESOLVED.fix_where


def test_v5_8_6_추정_문자열을_쓰지_않는다():
    """🔴🔴 §8-6 — *"사유를 추정해서 적는 코드는 계약 실패."*

    구조 계약: `app/` 에서 사유 **문장을 직접 지어** 깔때기 탈락 칸에 넣는 자리가
    없어야 한다. ⚠️ 사유는 **enum 을 통해서만** 들어간다.
    """
    import ast
    bad = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = ast.unparse(node.func)
            if not fn.endswith("drop_why"):
                continue
            # 🔴 둘째 인자가 **enum 을 지나지 않은** 날 문자열이면 실패
            args = node.args
            if len(args) >= 2 and isinstance(args[1], ast.Constant) \
                    and isinstance(args[1].value, str):
                bad.append(f"{p.name}:{node.lineno} — {ast.unparse(node)[:80]}")
    assert not bad, (
        "🔴 사유를 날 문자열로 넣었다 — `Reason` 을 지나야 한다:\n  "
        + "\n  ".join(bad))
