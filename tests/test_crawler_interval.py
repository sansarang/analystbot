"""CRW-6 — 크롤러 실행 명령의 **사본이 원본과 어긋나지 않는가.**

🔴 실사고 2026-09-01→09-08: "10m 이 의도다"라고 결정하고 `tools/deploy.sh` 의
   문자열 두 곳을 고친 뒤 항목을 ✅ 종결로 닫았다. 그런데 그 문자열은
   `railway up` 에 전달되지 않는다(`deploy_one` 의 2번 인자는 `echo` 전용).
   실제 실행 명령은 이미지의 CMD 이고, 운영은 **일주일 내내 60분**이었다.
   운영 키가 그것을 말하고 있었다 — `crawl:kbo:...:0003·0103·0203` (정시 3분).

원본은 `crawler/Dockerfile` 의 CMD 하나다. 이 테스트는 그 값과 **사본들**
(CLAUDE.md 서비스 표 · deploy.sh 출력)이 어긋나면 실패한다.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INTERVAL_RE = re.compile(r"-interval[\"',\s]+(\d+[smh])")


def _dockerfile_interval() -> str:
    for line in (REPO / "crawler" / "Dockerfile").read_text(encoding="utf-8").splitlines():
        if line.startswith("CMD"):
            m = INTERVAL_RE.search(line)
            assert m, f"CMD 에 -interval 이 없다: {line}"
            return m.group(1)
    raise AssertionError("crawler/Dockerfile 에 CMD 가 없다")


def test_문서의_서비스표가_이미지_CMD_와_같은_주기를_말한다():
    """사본이 원본을 이기지 않게 한다 — 이 어긋남이 CRW-6 그 자체였다."""
    real = _dockerfile_interval()
    claude_md = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    row = [ln for ln in claude_md.splitlines() if "analystbot-crawler" in ln]
    assert row, "CLAUDE.md 서비스 표에 크롤러 행이 없다"
    doc = INTERVAL_RE.search(row[0])
    assert doc, f"서비스 표에 -interval 이 없다: {row[0]}"
    assert doc.group(1) == real, (
        f"문서는 {doc.group(1)} 라고 적는데 이미지 CMD 는 {real} 다 — "
        "사본이 원본과 어긋났다(CRW-6)")


def test_배포_스크립트는_주기를_손으로_적지_않는다():
    """`deploy.sh` 가 적용하지도 않는 값을 화면에 찍던 것이 사람을 속였다(DEP-2)."""
    sh = (REPO / "tools" / "deploy.sh").read_text(encoding="utf-8")
    hard = [ln for ln in sh.splitlines()
            if INTERVAL_RE.search(ln) and "Dockerfile" not in ln and not ln.strip().startswith("#")]
    assert not hard, (
        "deploy.sh 가 주기를 손으로 적고 있다 — 원본(Dockerfile CMD)에서 읽어야 한다:\n"
        + "\n".join(hard))


def test_평시_주기가_가속_주기보다_길다():
    """불변식 — 평시가 가속보다 짧으면 pace 설계가 뒤집힌다."""
    unit = {"s": 1, "m": 60, "h": 3600}
    real = _dockerfile_interval()
    idle = int(real[:-1]) * unit[real[-1]]
    pace = (REPO / "crawler" / "cmd" / "crawler" / "main.go").read_text(encoding="utf-8")
    m = re.search(r'"fast-interval",\s*(\d+)\s*\*\s*time\.Minute', pace)
    assert m, "fast-interval 기본값을 찾지 못했다"
    assert idle > int(m.group(1)) * 60, "평시 주기가 가속 주기보다 짧다"
