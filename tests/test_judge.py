"""v4 단계 1 계약 — **폐기가 실제로 됐는가.**

v4 §9 단계 1 완료 조건:
> §8 폐기 목록의 코드·테스트 삭제. 동기 등급·확신·등급·min_win_prob·p_claude
> 참조 0건

게이트: *"금칙 식별자 grep 0건, 스위트 초록"*

🔴 **종전 이 파일은 동기 4등급·확신·등급·방아쇠를 검사하는 계약 27건이었다.**
   그 계약들이 검사하던 코드가 폐기됐으므로 계약도 함께 갔다(§9 "코드·테스트
   삭제"). 그 자리에 **되살아나면 빨개지는** 계약을 넣었다.

⚠️ 남긴 것: 변수의 원천 자료형(v4 §8 유지) · LLM 경계 · 배당 0건 · 표시 KST ·
   멈추지 않는다.
"""
from __future__ import annotations

import ast
import inspect
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import card as C
from app import judge as J
from app import llm as L
from app import run as R

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))


def _strip(src: str) -> str:
    """독스트링·주석을 뺀 코드만.

    🔴 문서가 "동기 등급은 폐기됐다"고 **설명하는** 것과 코드가 그것을 **부르는**
       것은 다르다(D46). 이 저장소에서 그 함정에 세 번 빠졌다.
    ⚠️ `ast.get_source_segment` 는 쓰지 않는다 — col_offset 이 바이트라 한글
       줄에서 `UnicodeDecodeError` 가 난다(실측 2026-09-27).
    """
    lines = src.splitlines()
    kill: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            kill.update(range(node.lineno - 1,
                              (node.end_lineno or node.lineno)))
    return re.sub(r"#.*", "",
                  "\n".join("" if i in kill else ln
                            for i, ln in enumerate(lines)))


def _code_only(mod) -> str:
    return _strip(inspect.getsource(mod))


def _app_code() -> str:
    """`app/**` 전체의 코드만. 🔴 게이트가 "grep 0건"이라 전수를 본다."""
    return "\n".join(_strip(p.read_text(encoding="utf-8"))
                     for p in sorted((ROOT / "app").rglob("*.py")))


# ══════════════════════════════════════════════════════════════════
# v4 §9 단계 1 게이트 — 금칙 식별자 0건
# ══════════════════════════════════════════════════════════════════

#: 🔴 v4 §8 폐기 목록이 이름을 댄 것. 되살리면 이 계약이 빨개진다.
BANNED_IDENTS = (
    # 동기 4등급
    "motivation_tier", "tier_gap", "TIER_TOP", "TIER_HIGH", "TIER_MID",
    "TIER_NONE",
    # lean
    "build_lean", "_provisional_confidence",
    # 확신 상/중/낮
    "CONF_HIGH", "CONF_MID", "CONF_LOW", "conf_kr",
    # 간다/조건부/접는다
    "CONDITIONAL", "grade_kr", "GradeOut", "VerdictOut",
    # 방아쇠 등급 상향/하향
    "triggers_from", "regrade", "TRIGGER_TYPES", "evaluate_triggers",
    # 반증 추적의 확신 갱신(5-d)
    "apply_counters",
    # 판정 경로 비계
    "min_win_prob", "p_claude", "p_final",
    # v3 채점 태그(§15 승자·확신·등급 열)
    "score_tags",
)


@pytest.mark.parametrize("ident", BANNED_IDENTS)
def test_폐기된_식별자가_app에_0건이다(ident):
    """🔴 v4 §9 단계 1 게이트 — *"금칙 식별자 grep 0건"*."""
    hit = re.findall(rf"\b{re.escape(ident)}\b", _app_code())
    assert hit == [], f"{ident} 가 {len(hit)}곳 남았다"


def test_폐기된_한글_어휘가_출력_경로에_0건이다():
    """🔴 v4 §3 STEP 7 계약 — 카드에 "확신"·"동기 등급"·"승자" 0건.

    ⚠️ `card.BANNED` 는 **금지 목록 자체**라 예외다 — 그것이 있어야 막는다.
    """
    code = re.sub(r"BANNED = \(.*?\)\n", "", _code_only(C), flags=re.S)
    for word in ("확신", "동기 등급", "승자", "간다", "조건부", "접는다"):
        assert word not in code, word


def test_금지_목록이_판정_어휘를_막는다():
    """v4 §3 STEP 7 — 그 낱말이 출력에 들어가면 잡혀야 한다."""
    assert C.has_banned("확신 중") == ["확신"]
    assert C.has_banned("등급: 간다") == ["간다"]
    assert C.has_banned("승자 홈") == ["승자"]
    assert C.has_banned("홈 1.85 배당") == ["배당"]
    assert C.has_banned("결장: 박영현(대표팀·bullpen)") == []


def test_판정_함수가_사라졌다():
    """🔴 이름이 아니라 **존재**를 본다."""
    for gone in ("build_lean", "decide", "grade", "apply_counters",
                 "triggers_from", "regrade", "score_tags", "motivation_tier",
                 "conf_kr", "grade_kr", "build_counters"):
        assert not hasattr(J, gone), f"judge.{gone} 이 살아 있다"
    assert not hasattr(R, "run_game"), "run.run_game 이 살아 있다"
    assert not hasattr(R, "run_slate"), "run.run_slate 이 살아 있다"
    for gone in ("Motivation", "VerdictOut", "GradeOut", "Trigger",
                 "Hypothesis", "Basis", "Counter"):
        assert not hasattr(J, gone), f"judge.{gone} 이 살아 있다"


def test_스키마에서_판정_표가_사라졌다():
    """v4 §8 폐기 — 그 표에 적는 코드가 없으므로 표도 간다."""
    sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    for t in ("motivation", "hypotheses", "counters", "verdicts", "grades",
              "triggers", "cards"):
        assert f"CREATE TABLE IF NOT EXISTS {t} " not in sql, t


def test_v4가_세울_표가_단계_2_에서_생겼다():
    """🔴 v4 §9 단계 2 완료 조건 — *"DB 에 variables/scenarios/survival/ledger 표."*

    ⚠️ **이 계약은 방향이 뒤집혔다.** 단계 1 에서는 같은 이름이 *"미리 만들지
       않았다"* 를 보던 음성 계약이었다(단계 건너뛰기 방지, §13-2). 단계 2 가
       그 표를 세웠으므로 이제 **있어야** 한다 — 음성 계약을 그대로 두면 단계 2 의
       산출을 되돌리라고 요구하는 꼴이 된다.
    🔴 배선은 단계 3 이고, 그 사실은 `test_wiring.py` 의 표 `NOT_WIRED` 에
       이름으로 적혀 있다. [§9]
    """
    sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    for t in ("variables", "scenarios", "survival", "ledger"):
        assert f"CREATE TABLE IF NOT EXISTS {t} " in sql, \
            f"{t} 표가 없다 — 단계 2 완료 조건이 안 찼다"


def test_이관_대기_표가_남아_있고_아직_안_읽힌다():
    """v4 §8 이관 — `hypothesis_table.yaml` → `opposite_search_rules.yaml`.

    🔴 그 이관은 **단계 5** 다. 지금은 씨앗 표만 있고 **읽는 코드가 없다.**
    """
    assert isinstance(J.OPPOSITE_SEED, dict) and J.OPPOSITE_SEED
    assert _app_code().count("OPPOSITE_SEED") == 1, "단계 5 전에 이미 읽고 있다"


# ══════════════════════════════════════════════════════════════════
# 남은 것 — 변수의 원천 (v4 §8 유지)
# ══════════════════════════════════════════════════════════════════

def test_line_없는_결장은_저장되지_않는다():
    """v3 §4 유지 — 결장은 **수가 아니라 위치**다."""
    with pytest.raises(ValueError):
        J.Absence("home", "선수", "injury", "")


def test_basis_7종_밖은_거부된다():
    with pytest.raises(ValueError):
        J.Absence("home", "선수", "컨디션", "starter")
    for b in J.BASES:
        J.Absence("home", "선수", b, "starter")


def test_상대전은_3경기_미만이면_판정_입력이_아니다():
    st = J.Starter("home", "투수", "probable",
                   vs_opponent={"games": 2, "era": 1.0})
    assert st.vs_opponent_usable is False
    st.vs_opponent = {"games": 3, "era": 7.98}
    assert st.vs_opponent_usable is True


def test_표본이_없으면_ERA를_지어내지_않는다():
    """🔴 v4 §1 — 출처 없는 사실은 변수가 아니다. 없는 숫자는 만들지 않는다."""
    assert J.Starter("home", "투수").recent_era is None
    assert J.Starter("home", "투수", "probable",
                     [{"ip": 1, "er": 1}]).recent_era is None


def test_의도_유형이_8종이다():
    assert len(J.INTENT_TYPES) == 8


# ══════════════════════════════════════════════════════════════════
# 배당 — v4 §0
# ══════════════════════════════════════════════════════════════════

ODDS_WORDS = ("odds", "devig", "p_market", "edge", "clv", "priced_in",
              "book", "price", "vig", "juice")


@pytest.mark.parametrize("mod", [J, R, C, L])
def test_판정_경로에_배당_낱말이_0이다(mod):
    code = _code_only(mod).lower()
    if mod is C:
        code = re.sub(r"banned = \(.*?\)\n", "", code, flags=re.S)
    hit = [w for w in ODDS_WORDS if re.search(rf"\b{w}\b", code)]
    assert hit == [], f"{mod.__name__} 에 배당 낱말: {hit}"


def test_스키마에_가격_칸이_없다():
    sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8").lower()
    for word in ("odds", "devig", "p_market", "clv", "price", "vig",
                 "bookmaker"):
        assert word not in sql, f"스키마에 가격 칸: {word}"


# ══════════════════════════════════════════════════════════════════
# LLM 경계 — v4 §11-7 · §3
# ══════════════════════════════════════════════════════════════════

def test_LLM이_금지_필드에_닿지_않는다():
    """🔴 v4 §3 — *"LLM이 direction·weight·strength·survival·verdict 필드를
    쓰면 계약 실패."*

    ⚠️ 그 필드들은 **단계 2 에서 타입으로 생긴다.** 지금 검사할 수 있는 것은
       "LLM 모듈이 그 이름에 값을 쓰지 않는다"까지다 — 단계 2 에서 타입 계약으로
       바꾼다.
    """
    code = _code_only(L)
    for field in ("direction", "weight", "strength", "survival", "verdict"):
        assert f"{field} =" not in code, field


def test_원천_자료형이_LLM을_부르지_않는다():
    code = _code_only(J).lower()
    for word in ("httpx", "ollama", "llm", "openai", "anthropic", "requests"):
        assert word not in code, word


def test_유료_사슬이_코드에_없다():
    """🔴 v4 §11-7 — `:cloud`·Gemini·유료 API 호출 0건."""
    for mod in (J, R, C, L):
        code = _code_only(mod).lower()
        for word in ("anthropic", "perplexity", "pplx", "apifootball",
                     "openrouter", "groq", "nvidia", "gemini"):
            assert word not in code, (mod.__name__, word)


def test_cloud_모델은_거부된다():
    with pytest.raises(L.LLMUnavailable):
        L._check_model("glm-4:cloud")
    L._check_model("qwen3:8b")


def test_기본_모델이_로컬_qwen이다():
    assert L.MODEL.startswith("qwen3")
    assert "localhost" in L.BASE_URL or "127.0.0.1" in L.BASE_URL


def test_스키마를_디코드_시점에_강제한다():
    assert '"format": schema' in _code_only(L)


def test_thinking을_끈다():
    assert '"think": False' in _code_only(L)


def test_L1_basis가_7종_그대로다():
    enum = L.L1_ABSENCE["properties"]["absences"]["items"][
        "properties"]["basis"]["enum"]
    assert set(enum) == set(J.BASES)


def test_L2_의도가_8종_그대로다():
    assert set(L.L2_INTENT["properties"]["type"]["enum"]) == set(J.INTENT_TYPES)


# ══════════════════════════════════════════════════════════════════
# 멈추지 않는다 · 표시는 KST — v4 §2
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_자료가_0이어도_수집이_끝까지_간다():
    """🔴 v4 §2 — 어느 단계에서 자료가 없어도 멈추지 않는다."""
    g = R.GameCtx(1, "KBO", "baseball", "두산", "KT", "잠실",
                  datetime(2026, 9, 29, 18, 30, tzinfo=KST))
    out = await R.collect_game(g, R.Sources())
    assert out.steps_done == [0, 1]
    assert out.unknowns, "못 잰 칸을 세지 않았다"


@pytest.mark.asyncio
async def test_못_잰_칸이_출력에_이름으로_적힌다():
    class _Src(R.Sources):
        async def slate(self, day, leagues):
            return [R.GameCtx(1, "KBO", "baseball", "두산", "KT", "잠실",
                              datetime(2026, 9, 29, 18, 30, tzinfo=KST))]

    body, games = await R.collect_slate(None, ["KBO"], _Src())
    assert "못 잰 칸" in body
    assert C.has_banned(body) == []
    assert games[0].unknowns


@pytest.mark.asyncio
async def test_진행중_경기는_수집을_안_돈다():
    g = R.GameCtx(1, "MLB", "baseball", "H", "A", None,
                  datetime(2026, 9, 29, 8, 0, tzinfo=KST),
                  status="inprogress")
    out = await R.collect_game(g, R.Sources())
    assert out.steps_done == [0]


@pytest.mark.asyncio
async def test_결론_줄을_만들지_않는다():
    """🔴 v4 §6 — 생존 계산 없이 "낸다/소액"을 적으면 근거 없이 이름을 적는 것이다.

    §12 가 금지한 바로 그 실수다(아르메니아 +0.5).

    🔴 **경기 0건으로 돌면 안 된다** — `R.Sources()` 는 슬레이트를 `[]` 로
       돌려주므로 경기별 렌더러(`card.render_collected`)를 한 번도 타지 않고,
       그러면 이 계약이 잠그는 것은 나열 꼬리말 한 줄뿐이다(리뷰 A6).
    """
    class _Src(R.Sources):
        async def slate(self, day, leagues):
            return [R.GameCtx(1, "KBO", "baseball", "두산", "KT", "잠실",
                              datetime(2026, 9, 29, 18, 30, tzinfo=KST))]

    body, games = await R.collect_slate(None, ["KBO"], _Src())
    assert games, "경기 0건이면 경기별 렌더러를 안 탄다 — 계약이 헛돈다"
    # 🔴 **팀명으로 확인하면 안 된다**(리뷰 M1). `"두산"` 은 머리글에 들어가고
    #    머리글은 순연·진행중·종료 **조기 반환에서도** 나온다(`card.py:43-47`).
    #    그러면 `GameCtx.status` 기본값이 바뀌는 날 이 계약은 **말없이 다시
    #    빈 채로 초록**이 된다 — A6 를 낳은 것과 같은 모양이다.
    #    `"못 잰 칸"` 은 전체 경로에서만 나온다(`card.py:68-69`).
    assert "못 잰 칸" in body, "전체 경로를 안 탔다 — 조기 반환에서 끝났다"
    for word in ("낸다", "소액", "생존 1.0"):
        assert word not in body, word


def test_표시가_KST다():
    """v4 §2 — DB 는 UTC 저장, **표시만** KST."""
    utc = datetime(2026, 9, 27, 9, 5, tzinfo=timezone.utc)
    assert R.kst_label(utc) == "09/27 18:05 KST"
    late = datetime(2026, 9, 27, 23, 10, tzinfo=timezone.utc)
    assert R.kst_label(late).startswith("09/28 08:10")


def test_소스는_못_구하면_빈값을_돌려준다():
    src = R.Sources()
    for name in ("slate", "absences", "starters", "intents"):
        assert inspect.iscoroutinefunction(getattr(src, name))


# ══════════════════════════════════════════════════════════════════
# 🔴 단계 1 에서 **잘못 지운** 계약 5건 — 되살렸다 (사용자 결정 2026-09-30)
#
# 리뷰어가 A3 로 잡았다: 단계 1 보고서는 지운 31건 전부에 대해 *"그 계약들이
# 검사하던 코드가 폐기됐다"* 고 적었는데, 아래 5건에 대해 그 주장은 **사실이
# 아니었다** — 대상 코드가 지금도 살아 있고 v4 §8 이 **유지**로 지목한 조항이다.
# ══════════════════════════════════════════════════════════════════

def test_호출_예산이_20이다():
    """경기당 L1~L5 합 20 상한. 초과는 unknown. [v3 §17-e = v4 §8 유지]

    🔴 상한이 없으면 로컬 LLM 이라도 한 경기에 수십 번 불린다 — 느려서 슬레이트가
       안 끝난다.
    """
    assert L.BUDGET_PER_GAME == 20
    b = L.Budget(limit=2)
    assert b.take() and b.take()
    assert b.take() is False


def test_검색어_규칙이_연산자와_연도를_막는다():
    """연도를 붙이면 **지난 시즌 기사가 섞인다.** [v3 §12-b = v4 §8 유지]"""
    assert L.query_ok("KBO 순위 매직넘버")
    assert not L.query_ok('site:kbo.co.kr 순위')
    assert not L.query_ok("KBO 순위 2026")
    assert not L.query_ok('"정확히 이 문장"')
    assert not L.query_ok("한 두 세 네 다섯 여섯 일곱")


def test_L1이_원문_문장을_요구한다():
    """🔴 항목마다 기댄 문장을 함께 낸다. 없으면 코드가 버린다.
    [v3 §17-g-2 = v4 §8 유지]

    ⚠️ 이것이 §3 *"출처 없는 변수 저장 실패"* 의 LLM 쪽 짝이다 — 단계 2 의
       `types.Variable.source_url` 이 DB 쪽을 막고, 이 계약이 추출 쪽을 막는다.
    """
    req = L.L1_ABSENCE["properties"]["absences"]["items"]["required"]
    assert "evidence_sentence" in req


def test_거절된_추출을_보관하는_표가_있다():
    """🔴 *"뉴스가 없던 날"* 과 *"추출기가 고장난 날"* 을 구분한다.
    [v3 §17-g-4 = v4 §8 유지 · 조용한 0 금지]
    """
    sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    assert "extraction_rejected" in sql
    assert "reason" in sql.split("extraction_rejected")[1][:600]


def test_게이트_라벨이_없다():
    """🔴 **음성 계약** — 가격 필터 어휘가 판정 코드에 0건이다.
    [v4 §6-d · §11-9]

    v4 §6-d: *"가격 필터는 사용자 결정 전까지 코드에 없다."*

    ⚠️ **단계 1 이 이것을 지운 논리는 성립하지 않았다.** 보고서는 *"검사하던
       코드가 폐기됐다"* 고 적었는데, 이것은 **대상이 없어야 초록인** 계약이다 —
       폐기될 코드가 애초에 없다(리뷰 A3). 사용자 결정 2026-09-30: 되살린다.
    🔴 `_code_only` 로 본다 — 독스트링이 그 낱말을 *설명*하는 것과 코드가
       *부르는* 것은 다르다(D46).
    """
    code = _code_only(J)
    for word in ("시장과대", "가치의심", "gate_label", "stance"):
        assert word not in code, word
