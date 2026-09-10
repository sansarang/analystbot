"""[C3] 변수 원장 — 주장과 실측의 대조. **발명하지 않는다.**

🔴 변수가 서술이던 동안에는 맞았는지 틀렸는지 셀 수 없었다.
   "이닝 소화력 예측 불가"는 참도 거짓도 아니다.
"""
import pytest

from app.engine import variable_ledger as VL

JG = {"game_id": 7, "sport": "kbo", "home": "두산", "away": "LG",
      "research": {"home_pitcher": {"name": "곽빈"},
                   "away_pitcher": {"name": "박시원"}}}


def test_threshold_is_read_not_invented():
    assert VL.threshold_of("3이닝 미만 조기 강판") == {
        "value": 3.0, "unit": "이닝", "cmp": "미만"}
    assert VL.threshold_of("타선 침체가 이어질 수 있다") is None


def test_no_threshold_means_unverifiable():
    """🔴 임계가 없으면 **채점하지 않는다.** 우리가 상상해 붙이면 우리 상상을
    채점하는 것이다."""
    assert VL.judge_realized(None, {"innings": 2.0}) == VL.UNVERIFIABLE


def test_realized_true_and_false():
    thr = VL.threshold_of("3이닝 미만")
    assert VL.judge_realized(thr, {"innings": 2.1}) == VL.TRUE
    assert VL.judge_realized(thr, {"innings": 5.0}) == VL.FALSE


def test_missing_actual_is_unverifiable():
    assert VL.judge_realized(VL.threshold_of("3이닝 미만"), None) == VL.UNVERIFIABLE
    assert VL.judge_realized(VL.threshold_of("3이닝 미만"), {}) == VL.UNVERIFIABLE


def test_comparators():
    for expr, actual, want in (("5실점 이상", 5, VL.TRUE),
                               ("5실점 초과", 5, VL.FALSE),
                               ("2득점 이하", 2, VL.TRUE),
                               ("2득점 미만", 2, VL.FALSE)):
        assert VL.judge_realized(VL.threshold_of(expr), {"runs": actual}) == want, expr


def test_subject_prefers_the_pitcher_then_team():
    assert VL.subject_of("박시원 3이닝 미만", JG) == ("박시원", "pitcher")
    assert VL.subject_of("LG 타선 침체", JG) == ("LG", "team")


def test_unknown_subject_is_not_forced():
    """이름이 안 잡히면 None 이다 — 잘못된 주체로 채점하면 더 나쁘다."""
    assert VL.subject_of("날씨 변수", JG) == (None, None)


class Pool:
    def __init__(self):
        self.rows = []

    async def execute(self, sql, *a):
        self.rows.append(a)


@pytest.mark.asyncio
async def test_format_violation_is_stored_not_dropped():
    """🔴 파싱 실패도 **행으로 남긴다** — 형식 위반율을 재는 게 절반이다."""
    pool = Pool()
    jg = {**JG, "matchup": {"변수": ["예측 불가 (종전 서술형)"]}}
    assert await VL.record(pool, jg) == 1
    args = pool.rows[0]
    assert args[3] == "예측 불가 (종전 서술형)"          # raw 보존
    assert args[7] is None and args[8] is None           # claimed_n/m 없음
    assert args[10] == VL.UNVERIFIABLE


@pytest.mark.asyncio
async def test_quantified_variable_is_stored_with_numbers():
    pool = Pool()
    jg = {**JG, "matchup": {"변수": [
        "박시원 3이닝 미만 조기 강판 — 발생 시 홈 방향 약 8%p · "
        "현재 p에 3%p 기반영 · 근거 자료10"]}}
    await VL.record(pool, jg)
    a = pool.rows[0]
    assert a[4] == "박시원" and a[5] == "pitcher"
    assert a[6] == "home" and float(a[7]) == 8.0 and float(a[8]) == 3.0
    assert a[9] == "자료10" and a[10] is None            # 채점 전이다


@pytest.mark.asyncio
async def test_record_without_pool_is_safe():
    assert await VL.record(None, JG) == 0


def test_grading_runs_inside_the_existing_job():
    """따로 돌면 한쪽만 밀린다 — 픽 채점과 같은 잡에서 돈다."""
    from pathlib import Path

    src = Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    assert "from app.engine.variable_ledger import grade" in src


def test_grade_pending_return_contract_is_unchanged():
    """🔴 `{graded, void}` 는 호출부·테스트가 정확히 비교하는 계약이다."""
    from pathlib import Path

    src = Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    assert 'out["variables"]' not in src


def test_record_hook_is_after_the_judge_call():
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    seg = src[src.index("async def _run_baseball_matchups"):]
    assert seg.index("await judge_matchup") < seg.index("variable_ledger import record")


# ═══════════════ 지시어를 실제 주체로 읽는다 (2026-09-07)
#
# 🔴 실측 638건 분해: 임계O·주체X **16건(2.5%)**. 전부 같은 모양이었다 —
#    "홈 선발이 5이닝 이하로 조기강판 시…". 임계는 명시했는데 이름 대신
#    자리를 가리켰고, `subject_of` 는 이름 문자열만 찾아 통째로 버렸다.
#    그 자리에 누가 있는지는 **이미 우리가 아는 사실**이다.

_JG = {"home": "Cincinnati Reds", "away": "Milwaukee Brewers",
       "home_pitcher": "Brady Singer", "away_pitcher": "Quinn Priester"}


@pytest.mark.parametrize("risk,want", [
    ("홈 선발이 5이닝 이하로 조기강판 시 추가 실점", ("Brady Singer", "pitcher")),
    ("원정 선발 조기 강판 리스크", ("Quinn Priester", "pitcher")),
    ("어웨이 선발이 4이닝 미만", ("Quinn Priester", "pitcher")),
    ("홈 타선 3경기 연속 2득점 이하 부진", ("Cincinnati Reds", "team")),
    ("원정 불펜 조기 가동", ("Milwaukee Brewers", "team")),
])
def test_지시어를_그_경기의_주체로_읽는다(risk, want):
    from app.engine.variable_ledger import subject_of

    assert subject_of(risk, _JG) == want


def test_이름이_지시어를_이긴다():
    """이름이 있으면 그게 더 정확하다."""
    from app.engine.variable_ledger import subject_of

    assert subject_of("원정 선발 Brady Singer 조기강판", _JG) \
        == ("Brady Singer", "pitcher")


@pytest.mark.parametrize("risk", [
    "선발이 흔들릴 수 있다",          # 어느 쪽인지 없다
    "홈 날씨 변수",                   # 역할어가 없다
    "경기 흐름이 바뀔 수 있다",
])
def test_모르면_여전히_버린다(risk):
    """⚠️ 관대함이 창작이 되면 안 된다. 잘못된 주체로 채점하면 더 나쁘다."""
    from app.engine.variable_ledger import subject_of

    assert subject_of(risk, _JG) == (None, None)


def test_선발을_모르면_팀으로_넘기지_않는다():
    from app.engine.variable_ledger import subject_of

    jg = {"home": "Cincinnati Reds", "away": "Milwaukee Brewers"}
    assert subject_of("홈 선발이 5이닝 이하", jg) == (None, None)


# ── [VAR-2 2026-09-11 사용자 지시] 변수를 채점 가능하게 만든다 ─────────────
#   🔴 실측(운영 변수 871건, 왜 채점이 안 되는지 전수 분류):
#        임계 표현이 아예 없다      777건 (85.1%)   ← 서술형 문장
#        임계는 있는데 주체 못 잡음  14건 ( 1.5%)   ← 성(姓)만 써서 매칭 실패
#        실측값 없음                35건 ( 3.8%)
#        ✅ 채점됨                  85건 ( 9.3%)
#      채점이 안 되면 "우리 변수가 맞나"를 영원히 잴 수 없다.
#
#   실사고 2026-09-10 텍사스@시애틀(❌ 3:4 홈승): 갈림길에 "길버트가 5이닝을
#      3실점 이하로 막는가 · 발생 확률 70%"라고 써놓고 그대로 일어났는데,
#      변수 원장은 그 예측이 맞았는지 기록조차 못 했다.

def test_subject_matches_surname_only():
    """실측 예시: `Gilbert 5이닝 미만` — 성만 써도 오늘 선발로 잡아야 한다."""
    from app.engine.variable_ledger import subject_of

    jg = {"home": "Seattle Mariners", "away": "Texas Rangers",
          "research": {"home_pitcher": {"name": "Logan Gilbert"},
                       "away_pitcher": {"name": "Jacob deGrom"}}}
    name, kind = subject_of("Gilbert 5이닝 미만 또는 4실점 이상", jg)
    assert kind == "pitcher" and name == "Logan Gilbert", (name, kind)


def test_surname_match_does_not_grab_short_tokens():
    """⚠️ 반대 위험 — 짧은 토큰이 아무 문장에나 걸리면 **틀린 주체**로 채점된다."""
    from app.engine.variable_ledger import subject_of

    jg = {"home": "Seattle Mariners", "away": "Texas Rangers",
          "research": {"home_pitcher": {"name": "Ha Ru"},
                       "away_pitcher": {"name": "Jo An"}}}
    name, kind = subject_of("홈 타선이 3득점 이하", jg)
    assert kind != "pitcher", f"두 글자 토큰이 잘못 걸렸다: {name}"


def test_prompt_requires_gradeable_threshold():
    """프롬프트가 **채점기가 읽는 형태**를 명시적으로 요구하는가.

    🔴 사본 금지: 요구 문구를 손으로 베끼지 않고 `VARIABLE_GRADEABLE` 상수를
       원본으로 읽는다. 채점기가 실제로 읽는 단위·비교어와 대조한다.
    """
    from app.engine.prompts import MATCHUP as P, VARIABLE_GRADEABLE
    from app.engine import variable_ledger as VL

    assert VARIABLE_GRADEABLE in P, "채점 가능 요구 블록이 프롬프트에 없다"
    pat = VL._THRESHOLD.pattern
    for unit in ("이닝", "실점", "득점"):
        assert unit in pat and unit in VARIABLE_GRADEABLE, unit
    for cmpw in ("미만", "이하", "이상", "초과"):
        assert cmpw in pat and cmpw in VARIABLE_GRADEABLE, cmpw


def test_prompt_gives_an_exit_instead_of_faking():
    """⚠️ 반대 위험 — 임계를 못 만드는 리스크에 숫자를 **지어내면** 더 나쁘다.

    버릴 곳이 아니라 **옮길 곳**을 알려줘야 한다(근거·판단으로).
    """
    from app.engine.prompts import VARIABLE_GRADEABLE as G

    assert "지어내지" in G, "임계 날조 금지가 없다"
    assert "근거" in G and "판단" in G, "옮길 곳을 안 알려준다"


def test_gradeable_example_actually_parses():
    """프롬프트가 든 예시가 **채점기를 실제로 통과**해야 한다.

    예시가 파서를 못 통과하면 그 프롬프트는 거짓말을 가르치는 것이다.
    """
    from app.engine.prompts import VARIABLE_GRADEABLE as G
    from app.engine.variable_ledger import threshold_of

    import re
    ex = re.findall(r"·\s*예\)\s*(.+)", G)
    assert ex, "프롬프트에 예시가 없다"
    for line in ex:
        assert threshold_of(line), f"예시가 채점기를 못 통과한다: {line!r}"
