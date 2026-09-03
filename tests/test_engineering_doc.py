"""[규율] `docs/ENGINEERING.md` 가 살아 있는 문서인지 잠근다.

🔴 이 문서의 값은 **근거 커밋 해시**에 있다. 해시가 죽으면 규칙은 일반론이
   되고, 일반론은 아무도 안 읽는다.
"""
import re
import subprocess
from pathlib import Path

DOC = Path("docs/ENGINEERING.md").read_text(encoding="utf-8")
CLAUDE = Path("CLAUDE.md").read_text(encoding="utf-8")


def test_every_cited_hash_exists_in_history():
    """🔴 인용한 커밋이 실재해야 한다 — 추측한 해시는 규율이 아니라 장식이다."""
    hashes = sorted(set(re.findall(r"근거[^\]]*?([0-9a-f]{7})", DOC)))
    assert hashes, "근거 해시가 하나도 없다"
    for h in hashes:
        r = subprocess.run(["git", "cat-file", "-t", h],
                           capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout.strip() == "commit", \
            f"{h} 는 이 저장소에 없는 커밋이다"


def test_all_five_impact_questions_are_present():
    for n in ("①", "②", "③", "④", "⑤"):
        assert n in DOC, n
    assert "아마 여기만" in DOC          # ①
    assert "조용히 0건" in DOC           # ④
    assert "원본을 읽어라" in DOC        # ⑤


def test_five_repeated_defect_types_are_listed():
    for kind in ("사본 드리프트", "조용한 성공", "상태 이원화",
                 "타이밍 결합", "경계값·표기 다양성"):
        assert kind in DOC, kind


def test_deploy_rhythm_rules():
    assert "1변경 1배포" in DOC
    assert "30분 내 재배포 금지" in DOC
    assert "등록 확인은 실행 확인이 아니다" in DOC


def test_slate_is_sacred():
    assert "슬레이트 진행 중 배포 금지" in DOC
    assert "그 자리에서 고치고 싶은 충동이 이 루프의 연료다" in DOC


def test_reporting_rules_separate_observation_from_interpretation():
    assert "관측과 해석을 구분해" in DOC
    assert "서약하지 않는다" in DOC


def test_revision_rule_guards_against_bloat():
    assert "1회짜리는 추가하지 않는다" in DOC


def test_claude_md_points_at_the_procedure():
    assert "docs/ENGINEERING.md" in CLAUDE
    assert "절차를 생략한 커밋은 반려 대상이다" in CLAUDE
    # 문서 목록에도 있어야 한다 — 상단 한 줄만 있으면 못 찾는다
    assert "코드 변경 절차" in CLAUDE


def test_commit_template_carries_the_five_questions():
    tpl = Path(".gitmessage").read_text(encoding="utf-8")
    for n in ("① 읽는 곳", "② 바뀌는 상태", "③ 리그 분기",
              "④ 실패하면 시끄러운가", "⑤ 사본"):
        assert n in tpl, n
    assert "30분 내 재배포 금지" in tpl
