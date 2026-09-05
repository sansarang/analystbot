"""[C5 2026-09-05] BvP 금지 명문화 + 팀별 보정 스텁.

🔴 BvP(타자 대 투수 상대 전적)는 수십 타석의 **통산 기록**이고, 우리 자료에
   들어 있지도 않다. 모델이 기억에서 끌어오면 그것은 자료가 아니라 사전 지식이다.
🔴 팀별 보정은 **스텁으로 둔다.** 2026-09-05 기준 대장 채점 114건 중
   현실화 판정 가능은 5건뿐(나머지는 임계 미명시로 `unverifiable`).
   팀별로 쪼개면 팀당 한 자리 수가 되고, 한 자리 수로 만든 보정은 잡음이다.
"""
from pathlib import Path

import pytest

PROMPT = Path("app/engine/prompts.py").read_text(encoding="utf-8")
JUDGE_PATH = ("app/engine/matchup.py", "app/engine/prompts.py",
              "app/engine/context_recent.py", "app/engine/variable_ref.py")


# ─────────────────── 금지 명문화 ───────────────────

@pytest.mark.parametrize("phrase", [
    "타자 대 투수 상대 전적(BvP)을 쓰지 마라",
    "팀 간 상대 전적",
    "스플릿 성적",
])
def test_ban_is_written_in_the_prompt(phrase):
    assert phrase in PROMPT


def test_ban_says_why_not_just_what():
    """금지만 적으면 다음 사람이 이유를 몰라 되돌린다."""
    assert "네 사전 지식" in PROMPT
    assert "지난 맞대결의 그 사람들이 아니다" in PROMPT


# ─────────────────── 유입 0건 증명 ───────────────────

@pytest.mark.parametrize("field", [
    "bvp", "vs_pitcher", "head_to_head", "h2h", "batter_vs",
])
def test_no_bvp_field_reaches_the_judgement_path(field):
    """🔴 문구만 금지하고 필드가 흐르면 소용없다 — 경로에 없음을 증명한다.

    ⚠️ **금지 문구 자체가 있는 줄은 뺀다.** 프롬프트에 "BvP 를 쓰지 마라"가
       적혀 있으므로 단순 문자열 검사는 그 줄에 걸린다 — 금지를 적었다는
       이유로 금지 검사가 실패하면, 다음 사람은 금지 문구를 지운다.
    """
    BAN = ("마라", "않는다", "아니다", "같다", "금지", "쓰지")
    for f in JUDGE_PATH:
        for i, line in enumerate(Path(f).read_text(encoding="utf-8").splitlines(), 1):
            if field in line.lower() and not any(b in line for b in BAN):
                raise AssertionError(f"{f}:{i} 에 {field} 유입: {line.strip()[:70]}")


def test_only_ban_text_mentions_head_to_head():
    """'맞대결'이 나오는 곳은 **금지 문구 자체**뿐이어야 한다."""
    hits = []
    for f in JUDGE_PATH:
        for i, line in enumerate(Path(f).read_text(encoding="utf-8").splitlines(), 1):
            if "맞대결" in line and not any(
                    w in line for w in ("마라", "않는다", "아니다", "같다")):
                hits.append(f"{f}:{i}")
    assert not hits, hits


# ─────────────────── 팀별 스텁 ───────────────────

def test_stub_refuses_to_publish_a_rate_below_the_sample_floor():
    """🔴 얇은 표본의 비율은 보는 순간 믿게 된다 — 숫자를 만들지 않는다."""
    from app.engine.variable_ledger import TEAM_MIN_SAMPLE

    assert TEAM_MIN_SAMPLE >= 20


@pytest.mark.asyncio
async def test_team_report_marks_insufficient_sample():
    from app.engine.variable_ledger import team_report

    class _Pool:
        async def fetch(self, sql, *a):
            return [{"team": "Kia Tigers", "n": 30, "realized": 2, "unver": 25},
                    {"team": "KT Wiz", "n": 40, "realized": 9, "unver": 5}]

    rows = await team_report(_Pool(), ("kbo",))
    thin = next(r for r in rows if r["team"] == "Kia Tigers")
    thick = next(r for r in rows if r["team"] == "KT Wiz")
    assert thin["rate"] is None and "표본 부족" in thin["status"]
    assert "5/20" in thin["status"], "얼마나 모자란지 보여야 한다"
    assert thick["rate"] == round(9 / 35, 3) and thick["status"] == "집계"


@pytest.mark.asyncio
async def test_team_report_survives_db_failure():
    from app.engine.variable_ledger import team_report

    class _Boom:
        async def fetch(self, *a):
            raise RuntimeError("DB")

    assert await team_report(_Boom(), ("kbo",)) == []
    assert await team_report(None, ("kbo",)) == []


def test_stub_never_flows_into_judgement():
    """🔴 표시 전용이다 — 판정·게이트가 이걸 읽으면 층이 무너진다."""
    import inspect

    from app.engine.variable_ledger import team_report

    src = inspect.getsource(team_report)
    for banned in ("p_home", "clip", "gate", "matchup", "judge"):
        assert banned not in src, banned
    for f in ("app/engine/matchup.py", "app/engine/value_gate.py"):
        assert "team_report" not in Path(f).read_text(encoding="utf-8"), f
